from datetime import timedelta
from types import SimpleNamespace
import mongomock
import pytest
import collector,contract
import remote.projection as projection
from test_collector import learning,post,sink
from test_observatory import NOW
from observatory.sampler import queue_wait_metrics,oldest_due_age


def test_object_state_and_canonical_string_have_same_hash(sink):
    e=learning('operation_succeeded',operation='push',state_after={'z':2,'a':1})
    assert post(e).status_code==202
    assert sink[-1][2]['details']['state_after']=='{"a":1,"z":2}'
    e['details']['state_after']='{"a":1,"z":2}'
    assert post(e).status_code==202
    assert sink[0][2]['payload_hash']==sink[1][2]['payload_hash']


def test_state_limits_and_types_preserved(sink):
    assert post(learning('operation_succeeded',operation='x',state_after={'a':'x'*512})).status_code==422
    assert post(learning('operation_succeeded',operation='x',state_after=[1,2])).status_code==422


def test_only_explicit_guest_identity_can_auto_provision(monkeypatch):
    import common.settings as settings
    monkeypatch.setattr(settings,'get',lambda:SimpleNamespace(remote_allow_guests=True))
    ident='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    assert projection.member_binding(ident,{}) is None
    guest=projection.member_binding('guest:'+ident,{})
    assert guest['external_member_key']=='game:member:guest:'+ident
    assert guest['identity_kind']=='guest' and guest['verified'] and guest['create_if_missing']
    with pytest.raises(projection.Conflict,match='invalid_guest_id'):
        projection.member_binding('guest:not-a-uuid',{})


def test_guest_optin_and_existing_mapping_take_precedence(monkeypatch):
    import common.settings as settings
    monkeypatch.setattr(settings,'get',lambda:SimpleNamespace(remote_allow_guests=False))
    assert projection.member_binding('guest:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',{}) is None
    binding={'external_member_key':'game:member:known'}
    assert projection.member_binding('id',{'members':{'id':binding}}) is binding


def test_unknown_uuid_guest_provision_is_optin_and_namespaced(monkeypatch):
    import common.settings as settings
    monkeypatch.setattr(settings,'get',lambda:SimpleNamespace(remote_allow_guests=True))
    class Cursor:
        def __init__(self):self.calls=[]
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,q,args):self.calls.append((q,args))
        def fetchall(self):return []
    class SQL:
        def __init__(self):self.c=Cursor()
        def cursor(self):return self.c
        def commit(self):pass
        def rollback(self):pass
    sql=SQL();player='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    ident=projection._resolve_member(sql,player,{})
    inserted=[args for q,args in sql.c.calls if q.startswith('INSERT')]
    assert len(inserted)==1 and len(inserted[0][0])==32
    assert inserted[0][1]=='game:member:guest:'+player
    assert ident==str(__import__('uuid').UUID(inserted[0][0]))


def test_total_queue_wait_is_not_retry_schedule_lateness(monkeypatch):
    d=mongomock.MongoClient(tz_aware=True).local.remote_event_outbox
    d.create_index([('state',1),('next_attempt_at',1)])
    assert queue_wait_metrics(d,NOW)['oldest_queued_age_s'] is None
    d.create_index([('state',1),('queued_at',1)],name='observatory_queue_age_v1')
    # mongomock does not implement find_one(hint=...); real indexes are checked in integration.
    original=d.find_one
    def find_one(*args,**kwargs):
        kwargs.pop('hint',None)
        return original(*args,**kwargs)
    monkeypatch.setattr(d,'find_one',find_one)
    d.insert_one({'state':'pending','queued_at':NOW-timedelta(minutes=20),'next_attempt_at':NOW+timedelta(seconds=40)})
    assert oldest_due_age(d,NOW)==0
    metrics=queue_wait_metrics(d,NOW)
    assert metrics['oldest_queued_age_s']==1200 and metrics['next_retry_in_s']==40
