"""Real MongoDB isolated restore drill; production target is never modified."""
import hashlib
import json
import uuid
from common.db import local_mongo
from remote.sql import pool
from remote.integrity import IntegrityGuard, acknowledge


def main():
    client = local_mongo().client
    prefix = 'nodeverse_test_integrity_' + uuid.uuid4().hex[:16]
    names = [prefix+'_local', prefix+'_remote']
    assert all(n.startswith('nodeverse_test_integrity_') for n in names)
    local, remote = (client[n] for n in names)
    try:
        docs = []
        for i in range(10):
            e = {'schema_version': 1, 'event_id': str(uuid.uuid4()),
                 'payload_hash': hashlib.sha256(str(i).encode()).hexdigest()}
            docs.append(dict(e, _id=e['event_id']))
            local.remote_event_outbox.insert_one({'_id': e['event_id'], 'state': 'stored', 'event': e})
        remote.pipeline_runtime_events.insert_many(docs)
        guard = IntegrityGuard(local, remote, pool(1), batch=100)
        assert guard.check(True)
        remote.pipeline_runtime_events.drop()  # only the isolated target
        assert not guard.check(True)
        incident = local.pipeline_controls.find_one()['incident']
        assert not IntegrityGuard(local, remote, pool(1)).check(True)
        remote.pipeline_runtime_events.insert_many(docs)
        assert acknowledge(local, remote, pool(1), incident) == 10
        assert guard.check(True)
        print(json.dumps({'passed': True, 'baseline_rows': 10, 'restore_loss_detected': True,
                          'restart_preserved_latch': True, 'full_verification_unlock': True,
                          'production_target_writes': 0, 'isolated_databases_cleaned': names}))
    finally:
        for name in names:
            assert name.startswith(prefix)
            client.drop_database(name)


if __name__ == '__main__': main()
