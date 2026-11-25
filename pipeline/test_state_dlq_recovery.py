import json
from datetime import datetime, timezone
from test_collector import learning
from tools import recover_state_dlq as recovery
import contract


def test_recovery_preserves_identity_sequence_and_original_body(monkeypatch):
    body=learning('operation_succeeded',operation='push',state_after={'stack':[1,2]})
    rejected={'reason':'schema_error','errors':[{'loc':'details.state_after'}],'raw':json.dumps(body)}
    monkeypatch.setattr(recovery,'snapshot_records',lambda topic:[rejected] if topic=='nv.dlq.v1' else [])
    result=recovery.prepare();entry=result['events'][0]
    assert not result['conflicts'] and not result['invalid']
    assert entry['event_id']==body['event_id'] and entry['sequence']==body['sequence']
    assert entry['original_body']==body and isinstance(entry['original_body']['details']['state_after'],dict)


def test_recovery_aborts_conflicting_accepted_content(monkeypatch):
    body=learning('operation_succeeded',operation='push',state_after={'stack':[1]})
    rejected={'reason':'schema_error','errors':[{'loc':'details.state_after'}],'raw':json.dumps(body)}
    accepted={'event_id':body['event_id'],'payload_hash':'different'}
    monkeypatch.setattr(recovery,'snapshot_records',lambda topic:[rejected] if topic=='nv.dlq.v1' else [accepted])
    result=recovery.prepare()
    assert result['conflicts']==[body['event_id']] and not result['events']
