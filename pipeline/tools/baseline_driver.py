"""Synthetic RF3 end-to-end baseline client. Refuses any non-baseline DB host/name."""
from __future__ import annotations
import concurrent.futures, contextlib, json, math, os, threading, time, uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import httpx
from pymongo import MongoClient
import pymysql

OUT=Path('/results')
STOP=threading.Event()


def utc(): return datetime.now(timezone.utc)
def iso(d): return d.isoformat(timespec='milliseconds').replace('+00:00','Z')
def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values)*p)-1)] if values else None
def stats(values):
    return {'n':len(values),'p50':percentile(values,.5),'p95':percentile(values,.95),'max':max(values) if values else None}
def eid():
    b=bytearray(int(time.time()*1000).to_bytes(6,'big')+os.urandom(10));b[6]=(b[6]&15)|112;b[8]=(b[8]&63)|128
    return str(uuid.UUID(bytes=bytes(b)))


def main():
    assert os.environ['DIRECT_MYSQL_HOST']=='target-mysql'
    assert os.environ['DIRECT_MYSQL_DATABASE']=='baseline'
    assert os.environ['MONGO_URI']=='mongodb://mongo:27017' and os.environ['MONGO_DB']=='baseline_local'
    assert os.environ['DIRECT_MONGO_URI']=='mongodb://target-mongo:27017'
    local=MongoClient('mongodb://mongo:27017',tz_aware=True)['baseline_local']
    remote=MongoClient('mongodb://target-mongo:27017',tz_aware=True)['baseline_remote']
    assert local.remote_event_outbox.count_documents({})==0, 'Refuse nonempty test data'
    assert remote.gameplay_events.count_documents({})==0, 'Refuse nonempty target events'
    sql=pymysql.connect(host='target-mysql',user='root',password=os.environ['DIRECT_MYSQL_PASSWORD'],database='baseline')
    players=[str(uuid.uuid4()) for _ in range(50)]
    with sql.cursor() as c:
        c.execute('CREATE TABLE IF NOT EXISTS game_members(member_id CHAR(32) PRIMARY KEY,external_member_key VARCHAR(150) UNIQUE,nickname VARCHAR(80),data_source VARCHAR(20),registered_at DATETIME)')
        c.execute('SELECT COUNT(*) FROM game_members')
        assert c.fetchone()[0]==0, 'Refuse nonempty member table'
        c.executemany('INSERT INTO game_members VALUES(%s,%s,%s,%s,%s)',[(uuid.UUID(p).hex,'game:member:baseline:'+p,'baseline-test','live',utc().replace(tzinfo=None)) for p in players])
    sql.commit();sql.close()
    # Readiness means all streams are active in a fresh report, not merely a running JVM.
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        try:
            progress=json.loads((OUT/'progress.json').read_text())
            if len(progress['queries'])==8 and all(q['active'] for q in progress['queries']): break
        except (OSError,ValueError,KeyError): pass
        time.sleep(2)
    else: raise RuntimeError('Spark not ready in 240 seconds')
    results=[]; errors=[]; sample_file=OUT/'samples.jsonl'
    def sample():
        with sample_file.open('w') as f:
            while not STOP.is_set():
                try:
                    counts={r['_id']:r['n'] for r in local.remote_event_outbox.aggregate([{'$group':{'_id':'$state','n':{'$sum':1}}}])}
                    p=json.loads((OUT/'progress.json').read_text())
                    row={'at':iso(utc()),'states':counts,'remote_events':remote.gameplay_events.count_documents({}),
                         'progress':p}
                    f.write(json.dumps(row,default=str)+'\n');f.flush()
                except Exception as e: errors.append(type(e).__name__)
                STOP.wait(2)
    sampler=threading.Thread(target=sample,daemon=True);sampler.start()
    try:
        for label,total,rate in [('warmup',100,20),('low',500,25),('medium',2000,100),('high',8000,400)]:
            t0=time.monotonic(); started=utc();ids=[];http_ms=[];statuses=Counter();lock=threading.Lock();next_slot=[t0]
            base=remote.gameplay_events.count_documents({})
            thread_clients=threading.local(); clients=[]
            def get_client():
                if not hasattr(thread_clients,'client'):
                    thread_clients.client=httpx.Client(timeout=20)
                    with lock:clients.append(thread_clients.client)
                return thread_clients.client
            def send_session(n):
                session,run,attempt=[str(uuid.uuid4()) for _ in range(3)]
                with contextlib.nullcontext(get_client()) as client:
                    for seq,typ in enumerate(['problem_started','attempt_started','operation_succeeded','attempt_succeeded','problem_completed'],1):
                        with lock:
                            slot=max(next_slot[0],time.monotonic());next_slot[0]=slot+1/rate
                        time.sleep(max(0,slot-time.monotonic()))
                        ident=eid(); body={'schema_version':2,'event_id':ident,'player_id':players[n%len(players)],
                          'session_id':session,'run_id':run,'minigame_id':'ST01','category':'DS','build_version':'0.3.0',
                          'content_version':'base','event_type':typ,'occurred_at':iso(utc()),'sequence':seq,'details':{}}
                        if seq in (2,3,4):body['attempt_id']=attempt
                        if seq==3:body['details']={'operation':'push','state_after':{'items':1}}
                        sent=time.monotonic()
                        try:
                            response=client.post('http://collector:8000/v2/events',json=body,headers={'X-API-Key':os.environ['INGEST_KEY']})
                            status=str(response.status_code)
                        except Exception as e:status=type(e).__name__
                        with lock:ids.append(ident);statuses[status]+=1;http_ms.append((time.monotonic()-sent)*1000)
            print(json.dumps({'stage':label,'status':'sending','events':total,'target_rate':rate}),flush=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                list(pool.map(send_session,range(total//5)))
            for client in clients:client.close()
            send_seconds=time.monotonic()-t0; drained=False; deadline=time.monotonic()+300
            while time.monotonic()<deadline:
                done=remote.gameplay_events.count_documents({})-base
                if done>=total:drained=True;break
                time.sleep(2)
            ended=utc(); elapsed=time.monotonic()-t0
            rows=[]
            for off in range(0,len(ids),500):
                rows.extend(local.remote_event_outbox.find({'_id':{'$in':ids[off:off+500]}},
                  {'state':1,'queued_at':1,'completed_at':1,'event.received_at':1,'attempts':1}))
            states=Counter(r['state'] for r in rows);e2e=[];queue=[]
            for r in rows:
                if r['state']!='stored':continue
                received=datetime.fromisoformat(r['event']['received_at'].replace('Z','+00:00'))
                e2e.append((r['completed_at']-received).total_seconds()*1000)
                queue.append((r['completed_at']-r['queued_at']).total_seconds()*1000)
            count=0;archives=0
            for off in range(0,len(ids),500):
                query={'_id':{'$in':ids[off:off+500]}}
                count+=remote.gameplay_events.count_documents(query);archives+=remote.pipeline_learning_events.count_documents(query)
            record={'stage':label,'events':total,'target_rate':rate,'started_at':iso(started),'ended_at':iso(ended),
              'send_seconds':send_seconds,'actual_ack_rate':statuses['202']/send_seconds,'http_statuses':dict(statuses),
              'http_ms':stats(http_ms),'drained':drained,'drain_after_send_s':elapsed-send_seconds,
              'wall_seconds':elapsed,'completion_rate_wall':count/elapsed,'states':dict(states),
              'remote_events':count,'remote_archives':archives,'received_to_stored_ms':stats(e2e),'queue_to_stored_ms':stats(queue),
              'retries':sum(max(0,r.get('attempts',1)-1) for r in rows)}
            results.append(record);(OUT/'results.json').write_text(json.dumps({'stages':results,'sampling_errors':errors},indent=2))
            print(json.dumps(record),flush=True)
            if not drained or statuses!={'202':total} or states!={'stored':total} or archives!=total:
                raise RuntimeError('Stage integrity/drain failed; stop escalation')
        # Replay exactly the warm-free high stage bodies is deliberately separate; baseline measures unique events only.
    finally:
        STOP.set();sampler.join(5)


if __name__=='__main__': main()
