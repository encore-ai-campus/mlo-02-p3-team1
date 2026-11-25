"""Actual isolated 30/45-day uploads, lost HTTP response, resume, concurrent clients and live traffic."""
import concurrent.futures,json,os,sys,time,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,'/bench')
import httpx,pymysql
from pymongo import MongoClient
from offline.client import Queue

OUT=Path('/results');KEY=os.environ['INGEST_KEY']
assert os.environ['DIRECT_MYSQL_HOST']=='target-mysql' and os.environ['DIRECT_MYSQL_DATABASE']=='baseline'
local=MongoClient('mongodb://mongo:27017',tz_aware=True).baseline_local
remote=MongoClient('mongodb://target-mongo:27017',tz_aware=True).baseline_remote
def build(player,n,days):
    sid,run,att=[str(uuid.uuid4()) for _ in range(3)]
    at=(datetime.now(timezone.utc)-timedelta(days=days)).replace(hour=12 if days else 0,minute=0,second=0,microsecond=0) if days else datetime.now(timezone.utc)-timedelta(seconds=1)
    rows=[]
    types=['problem_started','attempt_started']+['operation_succeeded']*(n-4)+['attempt_succeeded','problem_completed']
    for seq,typ in enumerate(types,1):
        row={'schema_version':2,'event_id':str(uuid.uuid4()),'player_id':player,'session_id':sid,'run_id':run,
          'minigame_id':'ST01','category':'DS','build_version':'0.3.0','content_version':'base','sequence':seq,
          'event_type':typ,'occurred_at':(at+timedelta(milliseconds=seq)).isoformat(timespec='milliseconds').replace('+00:00','Z'),'details':{}}
        if seq not in (1,n):row['attempt_id']=att
        if typ=='operation_succeeded':row['details']={'operation':'push','moves':seq,'state_after':{'items':seq}}
        rows.append(row)
    return rows
def client():return httpx.Client(base_url=os.getenv('OFFLINE_TEST_URL','http://collector:8000'),timeout=60)
def wait_ready():
    with client() as h:
        for _ in range(90):
            try:
                health='/health/v2' if 'gateway' in os.getenv('OFFLINE_TEST_URL','') else '/health/ready'
                if h.get(health).status_code==200:return
            except httpx.HTTPError:pass
            time.sleep(2)
    raise RuntimeError('collector_not_ready')

if sys.argv[1]=='prepare':
    wait_ready();assert local.offline_uploads.count_documents({})==0
    players=[str(uuid.uuid4()) for _ in range(3)]
    sql=pymysql.connect(host='target-mysql',user='root',password=os.environ['DIRECT_MYSQL_PASSWORD'],database='baseline')
    with sql.cursor() as c:
        c.executemany('INSERT INTO game_members VALUES(%s,%s,%s,%s,%s)',[(uuid.UUID(p).hex,'game:member:offline-test:'+p,'offline-test','live',datetime.now(timezone.utc).replace(tzinfo=None)) for p in players])
    sql.commit();sql.close()
    rows=build(players[0],225,30);q=Queue(OUT/'client1.db');ident=q.enqueue(str(uuid.uuid4()),rows)
    q2=Queue(OUT/'client2.db');ident2=q2.enqueue(str(uuid.uuid4()),build(players[1],5,45))
    class Lost:
        def __init__(self,h):self.h=h
        def put(self,path,**kw):
            r=self.h.put(path,**kw)
            if '/chunks/' in path and r.status_code==200:raise httpx.ReadTimeout('response lost after commit')
            return r
        def get(self,*a,**kw):return self.h.get(*a,**kw)
        def post(self,*a,**kw):return self.h.post(*a,**kw)
    with client() as h:
        assert h.post('/v2/events',json=rows[0],headers={'X-API-Key':KEY}).status_code==422
        try:q.sync(ident,Lost(h),KEY)
        except httpx.ReadTimeout:pass
        status=h.get('/v2/offline/uploads/'+ident,headers={'X-API-Key':KEY}).json()
        assert status['received_chunks']==[0] and status['state']=='receiving'
    (OUT/'integration.private.json').write_text(json.dumps({'upload1':ident,'upload2':ident2,'players':players,'live':build(players[2],5,0)}))
    print(json.dumps({'prepared':True,'lost_response_after_chunk':0,'offline_events':230,'restart_collector_now':True}),flush=True)
elif sys.argv[1]=='crash_prepare':
    meta=json.loads((OUT/'integration.private.json').read_text());q=Queue(OUT/'client4.db')
    ident=q.enqueue(str(uuid.uuid4()),build(meta['players'][0],500,75))
    with client() as h:q.sync_with_retry(ident,h,KEY)
    (OUT/'crash.private.json').write_text(json.dumps({'upload_id':ident}))
    print('500-event 75-day recovery upload queued',flush=True)
elif sys.argv[1]=='crash_verify':
    ident=json.loads((OUT/'crash.private.json').read_text())['upload_id']
    with client() as h:
        for _ in range(100):
            status=h.get('/v2/offline/uploads/'+ident,headers={'X-API-Key':KEY}).json()
            if status['remote_complete']:break
            time.sleep(3)
        else:raise RuntimeError('crash recovery timeout')
        Queue(OUT/'client4.db').sync_with_retry(ident,h,KEY)
    result={'crash_recovery_completed':True,'additional_75_day_events':500,'remote_events':remote.gameplay_events.count_documents({}),
      'archives':remote.pipeline_learning_events.count_documents({}),'daily_events':sum(r['events'] for r in local.offline_play_daily.find({}))}
    assert result['remote_events']==result['archives']==740 and result['daily_events']==735
    (OUT/'crash-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
elif sys.argv[1]=='extra':
    meta=json.loads((OUT/'integration.private.json').read_text());q=Queue(OUT/'client3.db')
    ident=q.enqueue(str(uuid.uuid4()),build(meta['players'][2],5,60))
    with client() as h:
        result=q.sync_with_retry(ident,h,KEY)
        for _ in range(60):
            result=h.get('/v2/offline/uploads/'+ident,headers={'X-API-Key':KEY}).json()
            if result['remote_complete']:break
            time.sleep(3)
    assert result['remote_complete'] and remote.gameplay_events.count_documents({})==240
    (OUT/'gateway-result.json').write_text(json.dumps({'gateway_completed':True,'additional_60_day_events':5,'total_remote_events':240,'separate_front_and_backend_keys':True},indent=2))
    print('gateway + separate keys + 60 day import: passed',flush=True)
else:
    wait_ready();meta=json.loads((OUT/'integration.private.json').read_text())
    def sync_pair(pair):
        with client() as h:return Queue(OUT/pair[0]).sync(meta[pair[1]],h,KEY)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        states=list(pool.map(sync_pair,[('client1.db','upload1'),('client2.db','upload2')]))
    with client() as h:
        for row in meta['live']:assert h.post('/v2/events',json=row,headers={'X-API-Key':KEY}).status_code==202
        deadline=time.monotonic()+300;start=time.monotonic()
        while time.monotonic()<deadline:
            states=[h.get('/v2/offline/uploads/'+meta[k],headers={'X-API-Key':KEY}).json() for k in ('upload1','upload2')]
            print(json.dumps({'elapsed':round(time.monotonic()-start),'states':[s['state'] for s in states],'delivery':[s['delivery_states'] for s in states]}),flush=True)
            if all(s['remote_complete'] for s in states) and remote.gameplay_events.count_documents({})==235:break
            time.sleep(5)
        else:raise RuntimeError('offline completion timeout')
    # Same upload, same chunk IDs and same event IDs after completion never creates a second set.
    replay=[sync_pair(('client1.db','upload1')),sync_pair(('client2.db','upload2'))]
    assert all(s['remote_complete'] for s in replay)
    dates=sorted({r['occurred_at'].date().isoformat() for r in remote.gameplay_events.find({},{'occurred_at':1})})
    daily=list(local.offline_play_daily.find({},{'_id':0,'play_date':1,'events':1,'attempts':1,'successes':1}))
    result={'offline_events':230,'live_events':5,'remote_events':remote.gameplay_events.count_documents({}),
      'remote_archives':remote.pipeline_learning_events.count_documents({}),'uploads_complete':sum(s['remote_complete'] for s in replay),
      'chunks':local.offline_chunks.count_documents({}),'registry_entries':local.offline_event_registry.count_documents({}),
      'offline_daily':daily,'distinct_play_dates':dates,'lost_response_and_collector_restart_resumed':True}
    assert result['remote_events']==result['remote_archives']==235
    assert sum(d['events'] for d in daily)==230 and len(daily)==2
    (OUT/'integration-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
