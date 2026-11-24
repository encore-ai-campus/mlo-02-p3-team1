"""Synthetic parallel writer check; requires isolated Mongo and MySQL containers."""
import hashlib
import importlib.util
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

from common import settings
from remote import sql
from remote.outbox import stage
from remote.worker import Worker

cfg = settings.get()
assert cfg.direct_mysql_host == 'mysql' and cfg.mongo_uri == 'mongodb://mongo:27017'
assert cfg.direct_mongo_uri == 'mongodb://mongo:27017' and cfg.mongo_db == 'writer_local_test'
assert cfg.direct_mongo_db == 'writer_remote_test' and cfg.direct_mysql_db == 'writer_test'
conn = sql.connect()
with conn.cursor() as c:
    c.execute('CREATE TABLE IF NOT EXISTS game_members (member_id VARCHAR(32) PRIMARY KEY, external_member_key VARCHAR(150) UNIQUE, nickname VARCHAR(80), data_source VARCHAR(20), registered_at DATETIME)')
    c.execute('SELECT COUNT(*) FROM game_members')
    assert c.fetchone()[0] == 0, 'Refusing nonempty test DB'
    c.execute('INSERT INTO game_members VALUES (%s,%s,%s,%s,%s)', ('a'*32, 'game:member:writer-fixture', 'isolated-test', 'live', datetime.now(timezone.utc).replace(tzinfo=None)))
conn.commit(); conn.close()
w = Worker()
assert not w.local.list_collection_names() and not w.remote.list_collection_names(), 'Refusing nonempty test Mongo DB'
w._ensure_indexes()
start = datetime.now(timezone.utc).replace(microsecond=0)
events = []
for _ in range(100):
    session, run, attempt = [str(uuid.uuid4()) for _ in range(3)]
    for i, kind in enumerate(('problem_started','attempt_started','operation_succeeded','attempt_succeeded','problem_completed'), 1):
        eid = str(uuid.uuid4()); at = (start+timedelta(milliseconds=i)).isoformat()
        events.append({'schema_version':2,'event_id':eid,'payload_hash':hashlib.sha256(eid.encode()).hexdigest(),
                       'player_id':'writer-fixture','session_id':session,'run_id':run,'attempt_id':attempt,
                       'minigame_id':'ST03','category':'DS','build_version':'0.3.0','content_version':'base',
                       'event_type':kind,'sequence':i,'occurred_at':at,'received_at':at,
                       'details':{'level':1,'operation':'push'}})
events.sort(key=lambda e:e['sequence'])
stage(events, db=w.local)
# A previous deployed projector creates the first two events of ten sessions. This
# uses the historical code only when mounted into the explicitly isolated test.
legacy_path = '/legacy/projection.py'
try:
    spec = importlib.util.spec_from_file_location('legacy_projection', legacy_path)
    legacy = importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
except FileNotFoundError:
    legacy = None
if legacy is not None:
    first_sessions = {e['session_id'] for e in events if e['sequence']==1}
    first_sessions = set(sorted(first_sessions)[:10])
    old_events = [e for e in events if e['session_id'] in first_sessions and e['sequence']<=2]
    old_events.sort(key=lambda e:(e['session_id'],e['sequence']))
    legacy_sql=sql.connect()
    try:
        for event in old_events:
            legacy.Projector(w.local,w.remote,legacy_sql,{}).project(event)
            w.local.remote_event_outbox.update_one({'_id':event['event_id']},{'$set':{'state':'stored'}})
    finally:
        legacy_sql.close()
started=time.monotonic(); deadline=started+120
try:
    while time.monotonic()<deadline:
        w.run_once()
        if w.local.remote_event_outbox.count_documents({'state':'stored'}) == len(events): break
        time.sleep(.25)
    states={s:w.local.remote_event_outbox.count_documents({'state':s}) for s in ('stored','pending','waiting_context','blocked','quarantined','parked','retrying','processing')}
    assert states['stored']==len(events), states
    assert w.remote.pipeline_learning_events.count_documents({})==len(events)
    assert w.remote.gameplay_events.count_documents({})==len(events)
    assert w.remote.problem_runs.count_documents({'status':'completed'})==100
    assert w.remote.solution_attempts.count_documents({'outcome':'success'})==100
    stage(events,db=w.local)
    assert w.local.remote_event_outbox.count_documents({'state':'stored'})==len(events)
    print('WRITER_CHECK '+json.dumps({'passed':True,'events':len(events),'sessions':100,'seconds':round(time.monotonic()-started,2),'states':states,'legacy_events':len(old_events) if legacy else 0}),flush=True)
finally:
    w.executor.shutdown(wait=True);w.release()
