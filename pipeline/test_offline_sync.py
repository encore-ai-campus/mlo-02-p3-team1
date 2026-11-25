import gzip,json,uuid
from datetime import datetime,timedelta,timezone
import mongomock,pytest,httpx
from fastapi.testclient import TestClient
import collector,contract
import offline.api as api
from offline.protocol import Manifest,digest,decode,MAX_EXPANDED
from offline.client import Queue
from remote.worker import claim_batch

KEY='offline-test-key-longer-than-24-characters'
HEAD={'X-API-Key':KEY}

def events(days=30):
    base=dict(schema_version=2,player_id=str(uuid.uuid4()),session_id=str(uuid.uuid4()),run_id=str(uuid.uuid4()),
      minigame_id='ST01',category='DS',build_version='0.3.0',content_version='base')
    attempt=str(uuid.uuid4());at=datetime.now(timezone.utc)-timedelta(days=days)
    rows=[]
    for seq,kind in enumerate(['problem_started','attempt_started','operation_succeeded','attempt_succeeded','problem_completed'],1):
        r=dict(base,event_id=str(uuid.uuid4()),sequence=seq,event_type=kind,
          occurred_at=(at+timedelta(milliseconds=seq)).isoformat(timespec='milliseconds').replace('+00:00','Z'),details={})
        if seq in [2,3,4]:r['attempt_id']=attempt
        if seq==3:r['details']={'operation':'push','state_after':{'items':1}}
        rows.append(r)
    return rows

@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('INGEST_KEY',KEY);monkeypatch.setenv('OFFLINE_ENABLED','1')
    database=mongomock.MongoClient().test
    monkeypatch.setattr(api,'db',lambda:database);monkeypatch.setattr(collector,'send',lambda *a,**k:None)
    return TestClient(collector.app),database

def prepare(client,rows,bodies=None):
    bodies=bodies or [{'events':rows}]
    m=Manifest(installation_id=uuid.uuid4(),player_id=rows[0]['player_id'],session_id=rows[0]['session_id'],
      first_sequence=rows[0]['sequence'],event_count=len(rows),chunk_hashes=[digest(b) for b in bodies])
    path='/v2/offline/uploads/'+str(uuid.uuid4())
    assert client.put(path,json=m.model_dump(mode='json'),headers=HEAD).status_code==200
    return path,bodies

def test_old_online_rejected_offline_preserves_date_hash_and_resumes(setup):
    c,db=setup;rows=events();assert c.post('/v2/events',json=rows[0],headers=HEAD).status_code==422
    path,bodies=prepare(c,rows,[{'events':rows[:2]},{'events':rows[2:]}])
    assert c.put(path+'/chunks/1',json=bodies[1],headers=HEAD).status_code==200
    assert c.post(path+'/seal',headers=HEAD).status_code==409
    assert c.put(path+'/chunks/0',json=bodies[0],headers=HEAD).status_code==200
    assert c.put(path+'/chunks/0',json=bodies[0],headers=HEAD).status_code==200
    assert c.post(path+'/seal',headers=HEAD).status_code==202
    assert c.post(path+'/seal',headers=HEAD).status_code==202
    assert db.offline_chunks.count_documents({})==2
    record=db.offline_chunks.find_one({'index':0})['records'][0]
    assert record['occurred_at']==rows[0]['occurred_at']
    expected=contract.to_record(contract.LearningEventV2.model_validate(rows[0]),datetime.now(timezone.utc))
    assert record['payload_hash']==expected['payload_hash']
    assert not c.get(path,headers=HEAD).json()['remote_complete']

def test_conflict_and_unknown_code_never_overwrite(setup):
    c,db=setup;rows=events();path,bodies=prepare(c,rows)
    assert c.put(path+'/chunks/0',json=bodies[0],headers=HEAD).status_code==200
    changed=json.loads(json.dumps(rows));changed[0]['details']={'level':2}
    other,b=prepare(c,changed)
    assert c.put(other+'/chunks/0',json=b[0],headers=HEAD).status_code==409
    assert db.offline_chunks.count_documents({})==1
    rows=events();rows[0]['event_type']=999;path,b=prepare(c,rows)
    assert c.put(path+'/chunks/0',json=b[0],headers=HEAD).status_code==422

def test_compression_limits_auth_and_dictionary(setup):
    c,_=setup;rows=events();path,b=prepare(c,rows)
    assert c.put(path+'/chunks/0',json=b[0]).status_code==401
    assert c.put(path+'/chunks/0',content=gzip.compress(json.dumps(b[0]).encode()),headers={**HEAD,'Content-Encoding':'gzip'}).status_code==200
    with pytest.raises(ValueError):decode(gzip.compress(b'x'*(MAX_EXPANDED+1)),'gzip')
    with pytest.raises(ValueError):decode(b'bad','gzip')
    m=Manifest(installation_id=uuid.uuid4(),player_id=rows[0]['player_id'],session_id=rows[0]['session_id'],first_sequence=1,event_count=5,chunk_hashes=[digest(b[0])]).model_dump(mode='json')
    m['dictionary_version']=2
    assert c.put('/v2/offline/uploads/'+str(uuid.uuid4()),json=m,headers=HEAD).status_code==422

def test_compact_codes_decode_and_91_days_refused(setup):
    c,db=setup;rows=events();rows[0]['event_type']=1;rows[2]['details']['operation']=1
    path,b=prepare(c,rows);assert c.put(path+'/chunks/0',json=b[0],headers=HEAD).status_code==200
    canonical=db.offline_chunks.find_one({'index':0})['records']
    assert canonical[0]['event_type']=='problem_started' and canonical[2]['details']['operation']=='push'
    path,b=prepare(c,events(91));assert c.put(path+'/chunks/0',json=b[0],headers=HEAD).status_code==422

def test_sqlite_lost_response_restart_and_no_early_delete(setup,tmp_path):
    c,db=setup;q=Queue(tmp_path/'queue.db');ident=q.enqueue(str(uuid.uuid4()),events())
    class LostResponse:
        failed=False
        def put(self,path,**kw):
            response=c.put(path,**kw)
            if '/chunks/' in path and not self.failed:self.failed=True;raise httpx.ReadTimeout('lost response after durable write')
            return response
        def get(self,*a,**kw):return c.get(*a,**kw)
        def post(self,*a,**kw):return c.post(*a,**kw)
    with pytest.raises(httpx.ReadTimeout):q.sync(ident,LostResponse(),KEY)
    q=Queue(tmp_path/'queue.db');status=q.sync(ident,c,KEY)
    assert status['received_chunks']==[0] and not status['remote_complete']
    assert db.offline_chunks.count_documents({})==1
    with pytest.raises(ValueError):q.prune_completed(ident)
    db.offline_uploads.update_one({'_id':ident},{'$set':{'state':'staged','confirmed_events':5,'delivery_confirmed_at':datetime.now(timezone.utc)}})
    assert q.sync(ident,c,KEY)['remote_complete']
    q.prune_completed(ident)

def test_live_priority_includes_legacy_rows():
    db=mongomock.MongoClient().test;at=datetime.now(timezone.utc)-timedelta(days=1)
    for ident,lane in [('offline','offline'),('legacy',None),('live','live')]:
        row={'_id':ident,'state':'pending','queued_at':at,'next_attempt_at':at,'sequence':1}
        if lane:row['delivery_lane']=lane
        db.remote_event_outbox.insert_one(row)
    assert {r['_id'] for r in claim_batch(db,2)}=={'legacy','live'}

def test_per_event_disk_queue_survives_restart_and_atomic_window(setup,tmp_path):
    c,_=setup;rows=events();q=Queue(tmp_path/'events.db');installation=q.installation_id
    for e in rows[:3]:q.append(e)
    q=Queue(tmp_path/'events.db');assert q.installation_id==installation
    for e in rows[3:]:q.append(e)
    ident=q.prepare(rows[0]['session_id']);assert ident
    assert q.prepare(rows[0]['session_id']) is None
    q.append(rows[0])  # same canonical event already prepared: no new pending event
    assert q.prepare(rows[0]['session_id']) is None
    changed=dict(rows[0],details={'level':2})
    with pytest.raises(ValueError,match='conflict'):q.append(changed)
    assert q.sync(ident,c,KEY)['received_chunks']==[0]

def test_pending_quota_preserves_existing_records(tmp_path):
    rows=events();q=Queue(tmp_path/'quota.db',max_bytes=1500)
    q.append(rows[0])
    with pytest.raises(ValueError,match='quota'):
        for e in rows[1:]:q.append(e)
    with q.connect() as c:assert c.execute('SELECT COUNT(*) FROM pending').fetchone()[0]>=1

def processor_class(monkeypatch):
    import importlib.util,sys
    from types import SimpleNamespace
    from pathlib import Path
    monkeypatch.setitem(sys.modules,'tables',SimpleNamespace())
    spec=importlib.util.spec_from_file_location('offline_processor_test',Path(__file__).parent/'offline/processor.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.Processor

def test_processor_live_gate_and_owner_fencing(monkeypatch):
    cls=processor_class(monkeypatch);db=mongomock.MongoClient(tz_aware=True).test;p=cls(None,db)
    assert p.acquire();other=cls(None,db);assert not other.acquire()
    at=datetime.now(timezone.utc);rows=[contract.to_record(contract.LearningEventV2.model_validate(r),at) for r in events()]
    db.offline_uploads.insert_one({'_id':'job','state':'queued','created_at':at,'next_attempt_at':at,'manifest':{'event_count':5}})
    db.offline_chunks.insert_one({'upload_id':'job','index':0,'records':rows})
    p.bronze=lambda *a:None;p.publish_history=lambda *a:None
    db.remote_event_outbox.insert_one({'_id':'live','state':'pending'})
    p.tick();assert db.remote_event_outbox.count_documents({'delivery_lane':'offline'})==0
    db.remote_event_outbox.delete_one({'_id':'live'})
    db.offline_uploads.update_one({'_id':'job'},{'$set':{'next_attempt_at':at}})
    p.tick();assert db.remote_event_outbox.count_documents({'delivery_lane':'offline'})==5
    db.remote_event_outbox.update_many({'delivery_lane':'offline'},{'$set':{'state':'stored'}})
    db.offline_uploads.update_one({'_id':'job'},{'$set':{'next_attempt_at':at}})
    p.tick();assert db.offline_uploads.find_one({'_id':'job'})['confirmed_events']==5
    with pytest.raises(RuntimeError,match='ownership'):p.update('job',{'state':'queued'})

def test_global_offline_rate_applies_across_uploads(monkeypatch):
    cls=processor_class(monkeypatch);db=mongomock.MongoClient(tz_aware=True).test;p=cls(None,db);assert p.acquire()
    p.bronze=lambda *a:None;p.publish_history=lambda *a:None;at=datetime.now(timezone.utc)
    for i in range(2):
        rows=[contract.to_record(contract.LearningEventV2.model_validate(r),at) for r in events()]
        db.offline_uploads.insert_one({'_id':str(i),'state':'queued','created_at':at,'next_attempt_at':at,'manifest':{'event_count':5}})
        db.offline_chunks.insert_one({'upload_id':str(i),'index':0,'records':rows})
    p.tick();p.tick()
    assert db.remote_event_outbox.count_documents({'delivery_lane':'offline'})==5
