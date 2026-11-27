import hashlib
from types import SimpleNamespace
import mongomock
import pytest
from remote.integrity import IntegrityGuard, acknowledge, validate_all, KEY
from remote.projection import Conflict


class Conn:
    def __init__(self, missing=False): self.missing=missing
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def execute(self,sql,args=None): self.args=args
    def fetchone(self): return None if self.missing else (1,)
    def fetchall(self): return [] if self.missing else [(x,'live') for x in self.args]
    def close(self): pass


def setup():
    c=mongomock.MongoClient(tz_aware=True);l,r=c.local,c.remote
    for i in range(3):
        event={'schema_version':1,'event_id':str(i),'payload_hash':hashlib.sha256(str(i).encode()).hexdigest()}
        r.pipeline_runtime_events.insert_one(dict(event,_id=str(i)))
        l.remote_event_outbox.insert_one({'_id':str(i),'state':'stored','event':event})
    return l,r,SimpleNamespace(connection=lambda:Conn())


def test_scan_is_bounded_and_persistent():
    l,r,p=setup();g=IntegrityGuard(l,r,p,batch=2)
    assert g.check(True)
    assert l.pipeline_controls.find_one()['checked_rows']==2
    g=IntegrityGuard(l,r,p,batch=2)
    assert g.check(True)
    assert l.pipeline_controls.find_one()['cycles']==1
    assert validate_all(l,r,p)==3


def test_restore_detected_without_new_events_and_latched():
    l,r,p=setup();g=IntegrityGuard(l,r,p,batch=2)
    r.pipeline_runtime_events.delete_one({'_id':'0'})
    assert not g.check(True)
    state=l.pipeline_controls.find_one();incident=state['incident']
    assert state['state']=='recovery_required'
    assert not IntegrityGuard(l,r,p).check(True)  # restart cannot clear it
    with pytest.raises(ValueError):acknowledge(l,r,p,'wrong')
    with pytest.raises(Conflict):acknowledge(l,r,p,incident)
    event=l.remote_event_outbox.find_one({'_id':'0'})['event']
    r.pipeline_runtime_events.insert_one(dict(event,_id='0'))
    assert acknowledge(l,r,p,incident)==3
    assert IntegrityGuard(l,r,p).check(True)


def test_outage_does_not_become_a_false_zero_or_corruption_latch():
    l,r,p=setup()
    def unavailable():raise OSError('test outage')
    g=IntegrityGuard(l,r,SimpleNamespace(connection=unavailable))
    assert not g.check(True)
    assert l.pipeline_controls.find_one()['state']=='unavailable'
    g.pool=p
    assert g.check(True)


def test_mysql_member_loss_latches_with_mongo_records_intact(monkeypatch):
    import remote.projection as projection
    from test_remote_projection import rows
    monkeypatch.setattr(projection,'resolve_member',lambda *a:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
    c=mongomock.MongoClient(tz_aware=True);l,r=c.local,c.remote
    for event in rows():
        result=projection.Projector(l,r,None,{}).project(event)
        l.remote_event_outbox.insert_one({'_id':event['event_id'],'state':'stored','event':event,'result':result})
    g=IntegrityGuard(l,r,SimpleNamespace(connection=lambda:Conn(missing=True)))
    assert not g.check(True)
    assert l.pipeline_controls.find_one()['reason']=='remote_mysql_member_missing_or_changed'
    assert r.gameplay_events.count_documents({})==5
