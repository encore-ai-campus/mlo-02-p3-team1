from datetime import datetime, timedelta, timezone
import pytest
from observatory.sampler import AlertBook, findings, oldest_due_age

NOW = datetime(2026, 11, 23, tzinfo=timezone.utc)


class Queue:
    def __init__(self, rows): self.rows = rows
    def find_one(self, query, projection, sort, hint, max_time_ms):
        assert hint == 'state_1_next_attempt_at_1' and sort == [('next_attempt_at', 1)]
        matches = [r for r in self.rows if r['state'] == query['state'] and
                   r.get('next_attempt_at') is not None and r['next_attempt_at'] <= query['next_attempt_at']['$lte']]
        return min(matches, key=lambda r: r['next_attempt_at']) if matches else None


def test_processing_and_future_work_do_not_trigger_false_queue_age():
    q = Queue([{'state': 'processing', 'queued_at': NOW-timedelta(hours=4)},
               {'state': 'pending', 'next_attempt_at': NOW+timedelta(seconds=30)},
               {'state': 'waiting_context', 'next_attempt_at': NOW+timedelta(seconds=10)}])
    assert oldest_due_age(q, NOW) == 0


def test_due_waiting_context_is_included_like_worker_claim():
    q = Queue([{'state': 'pending', 'next_attempt_at': NOW-timedelta(seconds=10)},
               {'state': 'waiting_context', 'next_attempt_at': NOW-timedelta(seconds=70)},
               {'state': 'retrying', 'next_attempt_at': NOW-timedelta(seconds=20)}])
    assert oldest_due_age(q, NOW) == 70


def test_real_due_backlog_triggers_and_recovers_alert():
    book = AlertBook()
    q = Queue([{'state': 'pending', 'next_attempt_at': NOW-timedelta(seconds=61)}])
    snapshot = {'progress': {'state': 'ok'}, 'mongo': {'state': 'ok'}, 'collector': {'state': 'ok'},
                'remote': {'state': 'ok'}, 'queries': [], 'queue': {'counts': {}, 'oldest_due_age_s': oldest_due_age(q, NOW)}}
    for i in range(3): active, events = book.update(findings(snapshot), NOW+timedelta(seconds=10*i))
    assert [x['id'] for x in active] == ['queue-age']
    snapshot['queue']['oldest_due_age_s'] = 0
    active, events = book.update(findings(snapshot), NOW+timedelta(seconds=30))
    assert not active and events[0]['phase'] == 'resolved'


def test_missing_index_never_misreported_as_zero():
    class Broken:
        def find_one(self, *args, **kwargs): raise RuntimeError('index unavailable')
    with pytest.raises(RuntimeError): oldest_due_age(Broken(), NOW)


def test_stale_processing_has_separate_warning():
    s = {'progress': {'state': 'ok'}, 'mongo': {'state': 'ok'}, 'collector': {'state': 'ok'},
         'remote': {'state': 'ok'}, 'queries': [],
         'queue': {'counts': {}, 'oldest_due_age_s': 0, 'stale_processing': True}}
    alerts = findings(s)
    assert [x['id'] for x in alerts] == ['processing-stale']
