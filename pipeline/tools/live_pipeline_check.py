"""Explicit live load/recovery test. Adds synthetic records; never deletes production data.

Uses existing gateway credentials internally without logging them. --fault interrupts only a pipeline
process, never Kafka/DB/volumes. Output files contain only synthetic identities and measurements.
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import math
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

WRITER='nodeverse-v2-live-remote-writer-1'
SPARK='nodeverse-v2-live-spark-1'


def docker(*args):return subprocess.check_output(['docker',*args],text=True,encoding='utf-8').strip()


def events(sessions,operations):
    player='guest:'+str(uuid.uuid4());out=[]
    now=dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=5)
    for _ in range(sessions):
        sid,rid,aid=[str(uuid.uuid4()) for _ in range(3)]
        kinds=['problem_started','attempt_started']+['operation_succeeded']*operations+['attempt_succeeded','problem_completed']
        for seq,kind in enumerate(kinds,1):
            e=dict(schema_version=2,event_id=str(uuid.uuid4()),player_id=player,session_id=sid,run_id=rid,
                   minigame_id='ST03',category='DS',build_version='0.3.0',content_version='base',
                   event_type=kind,sequence=seq,occurred_at=(now+dt.timedelta(milliseconds=seq)).isoformat(timespec='milliseconds').replace('+00:00','Z'),details={'level':1})
            if kind not in ('problem_started','problem_completed'):e['attempt_id']=aid
            if kind=='operation_succeeded':e['details']['operation']='push'
            out.append(e)
    return out


PROBE="""import sys,json
from pymongo import MongoClient
from common.db import local_mongo
d=json.load(sys.stdin);ids=d['ids'];l=local_mongo();r=MongoClient(d['uri'],tz_aware=True,serverSelectionTimeoutMS=5000)[d['db']]
jobs=list(l.remote_event_outbox.find({'_id':{'$in':ids}},{'state':1,'reason':1,'event.received_at':1,'completed_at':1}))
runs=list(r.problem_runs.find({'_id':{'$in':d['runs']}},{'status':1}))
from datetime import datetime
print(json.dumps({'states':{s:sum(j['state']==s for j in jobs) for s in set(j['state'] for j in jobs)},'reasons':list(set(j.get('reason','') for j in jobs if j['state']!='stored')),'events':r.gameplay_events.count_documents({'_id':{'$in':ids}}),'archive':r.pipeline_learning_events.count_documents({'_id':{'$in':ids}}),'completed_runs':sum(x['status']=='completed' for x in runs),'latencies_s':[(j['completed_at']-datetime.fromisoformat(j['event']['received_at'].replace('Z','+00:00'))).total_seconds() for j in jobs if j.get('completed_at')]}))
"""


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sessions',type=int,default=50);p.add_argument('--operations',type=int,default=20)
    p.add_argument('--workers',type=int,default=16);p.add_argument('--fault',choices=['none','writer-stop','spark-restart'],default='none')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=600)
    a=p.parse_args();assert 1<=a.sessions<=200 and 1<=a.operations<=100 and 1<=a.workers<=32
    a.output.mkdir(parents=True,exist_ok=False)
    es=events(a.sessions,a.operations);ids=[e['event_id'] for e in es];runs=list({e['run_id'] for e in es})
    (a.output/'corpus.json').write_text(json.dumps(es),encoding='utf-8')
    env=lambda name:dict(v.split('=',1) for v in json.loads(docker('inspect',name))[0]['Config']['Env'])
    key=env('pipeline-gateway-1')['INGEST_KEY'];target=env(WRITER)
    body=json.dumps({'ids':ids,'runs':runs,'uri':target['DIRECT_MONGO_URI'],'db':target['DIRECT_MONGO_DATABASE']})
    def probe():
        cp=subprocess.run(['docker','exec','-i','nodeverse-v2-live-collector-1','python','-c',PROBE],input=body,text=True,encoding='utf-8',capture_output=True,check=True)
        return json.loads(cp.stdout)
    def send(e):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for attempt in range(4):
            req=urllib.request.Request('http://192.168.0.81:8000/v2/events',data=json.dumps(e).encode(),headers={'X-API-Key':key,'Content-Type':'application/json'})
            try:
                with opener.open(req,timeout=15) as response:return response.status
            except (urllib.error.URLError,TimeoutError):
                if attempt==3:raise
                time.sleep(1)
    stopped=False;started=time.monotonic();observed_backlog=0
    try:
        if a.fault=='writer-stop':docker('stop','-t','30',WRITER);stopped=True
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:statuses=list(pool.map(send,es))
        sent_at=time.monotonic()
        if stopped:
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                sample=probe();observed_backlog=sum(sample['states'].values())
                if observed_backlog:break
                time.sleep(3)
            assert observed_backlog,'no durable outbox backlog observed'
            docker('start',WRITER);stopped=False
        if a.fault=='spark-restart':docker('restart','-t','60',SPARK)
        deadline=time.monotonic()+a.timeout
        while True:
            result=probe()
            print(json.dumps({'elapsed_s':round(time.monotonic()-started,1),'states':result['states'],'remote_events':result['events']}),flush=True)
            if result['states'].get('stored')==len(es):break
            if time.monotonic()>deadline:raise RuntimeError('storage timeout: '+json.dumps(result['states']))
            time.sleep(5)
        first_done=time.monotonic();duplicates=es[::10]
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:replay=list(pool.map(send,duplicates))
        time.sleep(20);final=probe()
        sql="import json,sys;from remote.sql import connect;c=connect();q=c.cursor();q.execute('SELECT member_id FROM game_members WHERE external_member_key=%s',('game:member:'+sys.stdin.read(),));rows=q.fetchall();c.close();print(json.dumps({'members':len(rows)}))"
        cp=subprocess.run(['docker','exec','-i',WRITER,'python','-c',sql],input=es[0]['player_id'],text=True,capture_output=True,check=True)
        lat=sorted(final['latencies_s']);passed=(all(x==202 for x in statuses+replay) and final['states']=={'stored':len(es)} and final['events']==final['archive']==len(es) and final['completed_runs']==a.sessions and json.loads(cp.stdout)['members']==1)
        report={'passed':passed,'unique_events':len(es),'duplicate_requests':len(duplicates),'sessions':a.sessions,'fault':a.fault,
                'observed_durable_backlog':observed_backlog,'http_send_s':round(sent_at-started,3),
                'api_unique_rps':round(len(es)/(sent_at-started),2),'to_all_stored_s':round(first_done-started,3),
                'latency_p50_s':lat[len(lat)//2],'latency_p95_s':lat[math.ceil(len(lat)*.95)-1],'latency_max_s':max(lat),
                'member_count':1,'result':{k:v for k,v in final.items() if k!='latencies_s'},'player_id':es[0]['player_id']}
        (a.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
        if not passed:raise SystemExit(1)
    finally:
        if stopped:docker('start',WRITER)
        if a.fault=='spark-restart':docker('start',SPARK)


if __name__=='__main__':main()
