"""Host-side maintenance window. Plan by default; --execute stops/restarts only the named Spark writer.

Schedule this script with Windows Task Scheduler. No Docker socket is mounted into a service.
"""
import argparse
import json
import subprocess
import sys
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SPARK='nodeverse-v2-live-spark-1'
WRITER='nodeverse-v2-live-remote-writer-1'


def next_run():
    now=datetime.now(timezone.utc)
    due=now.replace(hour=18,minute=0,second=0,microsecond=0)  # 03:00 Asia/Seoul
    return (due if due>now else due+timedelta(days=1)).isoformat()


def wait_ready(call, seconds=180):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            started=json.loads(call('inspect',SPARK))[0]['State']['StartedAt']
            code="import json;print(json.dumps(json.load(open('/data/metrics/streaming-progress.json'))))"
            report=json.loads(call('exec',SPARK,'python3','-c',code))
            if (report['updated_at']>started[:23] and len(report['queries'])==8
                and all(q['active'] for q in report['queries'])):return
        except Exception:pass
        time.sleep(2)
    raise RuntimeError('Spark readiness timeout after maintenance')


def docker(*args, timeout=900):
    return subprocess.check_output(['docker', *args], text=True, encoding='utf-8',
                                   stderr=subprocess.STDOUT, timeout=timeout).strip()


def publish(doc):
    doc=dict(doc, updated_at=datetime.now(timezone.utc).isoformat())
    if doc.get('state') in ('failed', 'resume_failed'):doc['failure_unresolved']=True
    elif doc.get('state')=='ok':doc['failure_unresolved']=False
    code="import json,sys;from datetime import datetime;from common.db import local_mongo;d=json.load(sys.stdin);d['updated_at']=datetime.fromisoformat(d['updated_at']);local_mongo().pipeline_controls.update_one({'_id':'maintenance'},{'$set':d},upsert=True)"
    subprocess.run(['docker','exec','-i',WRITER,'python','-c',code],input=json.dumps(doc),
                   text=True,encoding='utf-8',capture_output=True,check=True,timeout=15)


def plan(info, tables, day):
    assert info['Config']['Labels'].get('com.docker.compose.project')=='nodeverse-v2-live'
    assert info['State']['Running'], 'Spark must be running before the maintenance window'
    cmd=list(info['Config']['Cmd'])
    assert cmd[-1]=='/app/delta_stream.py', 'unreviewed Spark command'
    cmd[-1]='/app/maintain.py'
    cmd+=['--table',*tables,'--execute']
    if day:cmd+=['--date',day]
    args=['run','--rm','--name',SPARK+'-maintenance','--user','0:0',
          '--network',next(iter(info['NetworkSettings']['Networks'])),
          '--entrypoint','/opt/spark/bin/spark-submit']
    env=dict(x.split('=',1) for x in info['Config']['Env'])
    for key in ['LAKE_ROOT','CHECKPOINT_ROOT','TZ']:
        if key in env:args+=['-e',key+'='+env[key]]
    args+=['-e','COMPACTION_MODE=maintenance']
    for mount in info['Mounts']:
        source=mount['Name'] if mount['Type']=='volume' else mount['Source']
        args+=['-v',source+':'+mount['Destination']+('' if mount['RW'] else ':ro')]
    return [*args,info['Image'],*cmd]


def execute(info, tables, day, call=docker, status=publish):
    args=plan(info,tables,day)
    state='failed';failure=None;stopped=False
    status({'state':'running','started_at':datetime.now(timezone.utc).isoformat()})
    try:
        # Refuse concurrent jobs before stopping the production writer.
        existing=call('ps','-aq','--filter','name=^/'+SPARK+'-maintenance$')
        if existing:raise RuntimeError('another maintenance container exists')
        call('stop','-t','90',SPARK);stopped=True
        output=call(*args)
        state='ok'
        return output
    except Exception as exc:
        failure=type(exc).__name__
        raise
    finally:
        # An interrupted Docker CLI can leave its container alive. Never restart alongside it.
        resumed=True
        if stopped:
            try:
                if call('ps','-aq','--filter','name=^/'+SPARK+'-maintenance$'):
                    call('stop','-t','30',SPARK+'-maintenance')
                    call('rm',SPARK+'-maintenance')
                call('start',SPARK)
                wait_ready(call)
            except Exception:
                resumed=False;state='resume_failed'
        doc={'state':state,'error_type':failure,'spark_start_requested':resumed,
             'next_run_at':next_run()}
        if state=='ok':doc['last_success_at']=datetime.now(timezone.utc).isoformat()
        status(doc)
        if not resumed:raise RuntimeError('Spark resume failed; see maintenance status')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true');p.add_argument('--log',type=Path)
    p.add_argument('--table',nargs='+',default=['silver.learning_events','gold.minigame_1m'])
    p.add_argument('--date',default=None)
    a=p.parse_args()
    # Use the existing SQL planner to reject invalid table/date combinations before stopping anything.
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'spark'))
    from maintain import statements
    try:
        sql=[statements(t,a.date) for t in a.table]
        info=json.loads(docker('inspect',SPARK))[0]
        plan(info,a.table,a.date)
    except Exception as exc:
        if a.execute:publish({'state':'failed','error_type':type(exc).__name__,'next_run_at':next_run()})
        print(json.dumps({'state':'invalid_plan','error_type':type(exc).__name__}));raise SystemExit(1)
    if not a.execute:
        print(json.dumps({'execute':False,'sql':sql,'stops':SPARK}));return
    lock=Path(__file__).resolve().parents[1]/'results/maintenance.lock'
    lock.parent.mkdir(parents=True,exist_ok=True)
    try:
        handle=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        print(json.dumps({'state':'busy','reason':'maintenance lock exists'}));raise SystemExit(1)
    os.close(handle)
    try:
        output=execute(info,a.table,a.date)
        if a.log:
            a.log.parent.mkdir(parents=True,exist_ok=True);a.log.write_text(output,encoding='utf-8')
        print(json.dumps({'state':'ok','spark_restart_requested':True,'sql':sql}))
    except Exception as exc:
        if a.log:
            a.log.parent.mkdir(parents=True,exist_ok=True)
            a.log.write_text(getattr(exc,'output','') or type(exc).__name__,encoding='utf-8')
        print(json.dumps({'state':'failed','error_type':type(exc).__name__}));raise SystemExit(1)
    finally:
        lock.unlink()


if __name__=='__main__':main()
