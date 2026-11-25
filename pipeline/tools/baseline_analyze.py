"""Summarize synthetic baseline samples without raw event/member identifiers or credentials."""
import argparse,json,re
from datetime import datetime
from pathlib import Path

def date(s):return datetime.fromisoformat(s.replace('Z','+00:00'))
def memory(s):
    n,unit=re.match(r'([\d.]+)(\w+)',s.split('/')[0].strip()).groups()
    return float(n)*{'B':1,'KiB':1024,'MiB':1024**2,'GiB':1024**3}.get(unit,1)/1024**2
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
    stages=json.loads((out/'results.json').read_text())['stages']
    samples=[json.loads(l) for l in (out/'samples.jsonl').read_text().splitlines()]
    resources=[json.loads(l) for l in (out/'resources.jsonl').read_text().splitlines()]
    result=[]
    for s in stages:
        lo,hi=map(date,[s['started_at'],s['ended_at']]);window=[r for r in samples if lo<=date(r['at'])<=hi]
        batches={};timings={};peak_queue=0;restarts={};sink_errors=0
        for r in window:
            peak_queue=max(peak_queue,sum(n for k,n in r['states'].items() if k!='stored'))
            progress=r['progress'];restarts.update(progress.get('query_restarts',{}));sink_errors=max(sink_errors,progress.get('sink_failures',{}).get('count',0))
            for q in progress.get('queries',[]):
                v=q.get('progress') or {}
                if v.get('numInputRows',0)>0:batches[(q['name'],v.get('batchId'))]=v
            for name,t in progress.get('stage_timings',{}).items():
                if lo<=date(t['completed_at'])<=hi:timings[(name,t.get('batch_id'))]=t
        query_stats={}
        for (name,b),v in batches.items():
            if lo<=date(v['timestamp'])<=hi:
                x=query_stats.setdefault(name,{'observed_nonempty_batches':0,'max_trigger_ms':0,'max_input_rows':0})
                x['observed_nonempty_batches']+=1
                x['max_trigger_ms']=max(x['max_trigger_ms'],v.get('durationMs',{}).get('triggerExecution',0))
                x['max_input_rows']=max(x['max_input_rows'],v.get('numInputRows',0))
        resource={}
        for r in resources:
            if not lo<=date(r['at'])<=hi:continue
            for c in r['containers']:
                if not c['Name'].startswith('nv-baseline-'):continue
                v=resource.setdefault(c['Name'],{'peak_cpu_percent':0,'peak_memory_mib':0,'samples':0})
                v['samples']+=1;v['peak_cpu_percent']=max(v['peak_cpu_percent'],float(c['CPUPerc'].rstrip('%')))
                v['peak_memory_mib']=max(v['peak_memory_mib'],memory(c['MemUsage']))
        row=dict(s,peak_sampled_outbox_nonstored=peak_queue,query_observations=query_stats,
                 stage_observations=list(timings.values()),resources=resource,query_restarts=restarts,sink_failures=sink_errors)
        result.append(row)
    (out/'analysis.json').write_text(json.dumps({'stages':result},indent=2))
    print(json.dumps({'stages':[{k:r[k] for k in ['stage','events','actual_ack_rate','peak_sampled_outbox_nonstored','received_to_stored_ms','query_observations']} for r in result]},indent=2))

if __name__=='__main__':main()
