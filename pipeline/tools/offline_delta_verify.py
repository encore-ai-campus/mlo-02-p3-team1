"""Read-only lane isolation/duplicates check against the isolated offline integration lake."""
import json,sys
from pathlib import Path
sys.path.insert(0,'/app');sys.path.insert(0,'/opt/nodeverse')
import tables as tb
from delta.tables import DeltaTable
from pyspark.sql import functions as F
spark=tb.spark_session('offline-readonly-verification',2)
try:
    result={}
    for name in ['bronze.game_events','silver.learning_events','offline.bronze_learning','offline.silver_learning']:
        frame=spark.read.format('delta').load(tb.path(name));result[name]={'rows':frame.count()}
        if 'event_id' in frame.columns:result[name]['unique_ids']=frame.select('event_id').distinct().count()
        elif name=='bronze.game_events':result[name]['unique_ids']=frame.select(F.get_json_object('value','$.event_id')).distinct().count()
        result[name]['partitions']=DeltaTable.forPath(spark,tb.path(name)).detail().first().partitionColumns
    totals=spark.read.format('delta').load(tb.path('gold.minigame_1m')).selectExpr('sum(attempts) attempts','sum(successes) successes').first().asDict()
    result['live_gold_totals']=totals
    old=spark.read.format('delta').load(tb.path('offline.silver_learning'))
    result['historical_play_dates']=[str(r[0]) for r in old.select('event_date').distinct().orderBy('event_date').collect()]
    assert result['bronze.game_events']['rows']>=5 and result['bronze.game_events']['unique_ids']==5
    assert result['silver.learning_events']['rows']==result['silver.learning_events']['unique_ids']==5
    assert result['offline.bronze_learning']['rows']==result['offline.silver_learning']['rows']==result['offline.silver_learning']['unique_ids']==735
    assert totals=={'attempts':1,'successes':1}
    assert result['offline.silver_learning']['partitions']==['event_date']
    result['verification_passed']=True
    Path('/results/offline-delta-result.json').write_text(json.dumps(result,indent=2));print('OFFLINE_DELTA '+json.dumps(result),flush=True)
finally:spark.stop()
