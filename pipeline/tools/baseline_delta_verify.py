"""Read-only Delta counts/history after stopping the isolated baseline Spark writer."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,'/app');sys.path.insert(0,'/opt/nodeverse')
import tables as tb
from delta.tables import DeltaTable

assert Path('/results/results.json').is_file()
expected=sum(s['events'] for s in json.loads(Path('/results/results.json').read_text())['stages'])
spark=tb.spark_session('baseline-readonly-verification',2)
try:
    result={}
    for name in ('bronze.game_events','silver.learning_events','silver.quarantine','gold.minigame_1m','gold.failure_alerts'):
        df=spark.read.format('delta').load(tb.path(name));count=df.count()
        commits=DeltaTable.forPath(spark,tb.path(name)).history().select('operation','operationMetrics').collect()
        result[name]={'rows':count,'optimize_commits':sum(r.operation=='OPTIMIZE' for r in commits),
          'merge_commits':sum(r.operation=='MERGE' for r in commits)}
        if name=='silver.learning_events':result[name]['unique_event_ids']=df.select('event_id').distinct().count()
        if name=='gold.minigame_1m':
            totals=df.selectExpr('sum(attempts) attempts','sum(successes) successes','sum(failures) failures').first().asDict()
            result[name]['totals']=totals
    result['expected_events']=expected
    Path('/results/delta-verification.json').write_text(json.dumps(result,indent=2));print('BASELINE_DELTA '+json.dumps(result),flush=True)
    assert result['bronze.game_events']['rows']==expected
    assert result['silver.learning_events']['rows']==result['silver.learning_events']['unique_event_ids']==expected
    assert result['silver.quarantine']['rows']==0
    assert result['gold.minigame_1m']['totals']=={'attempts':expected//5,'successes':expected//5,'failures':0}
finally:spark.stop()
