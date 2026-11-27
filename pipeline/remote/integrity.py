"""Bounded target reconciliation with a persistent recovery latch. Never repairs/deletes targets."""
import argparse
import json
import time
import uuid
from common.timeutil import utc_now
from remote.projection import Projector, Conflict

KEY = 'remote_integrity'


def verify_batch(local, remote, conn, jobs):
    """Bulk fetch references once per collection; no per-event remote round trips."""
    groups = {}
    for job in jobs:
        groups.setdefault('pipeline_'+Projector.kind(job['event'])+'_events', set()).add(job['event']['event_id'])
    dashboard = [j for j in jobs if j.get('result', {}).get('scope') == 'dashboard_records']
    for collection, key in [('gameplay_events', 'event_id'), ('problem_runs', 'run_id'),
                            ('game_sessions', 'session_id'), ('solution_attempts', 'attempt_id')]:
        groups[collection] = {j['result'][key] for j in dashboard if j['result'].get(key)}
    data = {name: {d['_id']: d for d in remote[name].find({'_id': {'$in': list(ids)}})} for name, ids in groups.items()}
    ids = {d['task_id'] for d in data['problem_runs'].values() if d.get('task_id')}
    data['game_problems'] = {d['_id']: d for d in remote.game_problems.find({'_id': {'$in': list(ids)}})}
    members = {uuid.UUID(j['result']['member_id']).hex for j in dashboard}
    if members:
        with conn.cursor() as cur:
            cur.execute('SELECT member_id, data_source FROM game_members WHERE member_id IN ('+
                        ','.join(['%s']*len(members))+')', tuple(sorted(members)))
            found = {r[0].lower() for r in cur.fetchall() if r[1] == 'live'}
        if found != members: raise Conflict('remote_mysql_member_missing_or_changed')
    class Collection:
        def __init__(self, rows): self.rows = rows
        def find_one(self, query): return self.rows.get(query['_id'])
    class Cache:
        def __getitem__(self, name): return Collection(data.get(name, {}))
        def __getattr__(self, name): return self[name]
    for job in jobs:
        verify_job(local, Cache(), conn, job, {j['result']['member_id'] for j in dashboard})


def verify_job(local, remote, conn, job, members):
    event = job['event']
    archive = remote['pipeline_' + Projector.kind(event) + '_events'].find_one({'_id': event['event_id']})
    if not archive or archive.get('payload_hash') != event['payload_hash']:
        raise Conflict('remote_archive_missing_or_changed')
    result = job.get('result', {})
    if result.get('scope') == 'dashboard_records':
        Projector(local, remote, None, {}).verify_receipt(event, result)
        member = result['member_id']
        if member not in members:
            with conn.cursor() as cur:
                cur.execute('SELECT member_id, data_source FROM game_members WHERE member_id=%s',
                            (uuid.UUID(member).hex,))
                row = cur.fetchone()
            if not row or row[0].lower() != uuid.UUID(member).hex or row[1] != 'live':
                raise Conflict('remote_mysql_member_missing_or_changed')
            members.add(member)


class IntegrityGuard:
    def __init__(self, local, remote, pool, interval=30, batch=100):
        self.local, self.remote, self.pool = local, remote, pool
        self.interval, self.batch, self.next_check = interval, batch, 0
        self.allowed = False

    def check(self, force=False):
        saved = self.local.pipeline_controls.find_one({'_id': KEY}) or {}
        if saved.get('state') == 'recovery_required':
            self.allowed = False
            return False
        if not force and time.monotonic() < self.next_check:
            return self.allowed
        self.next_check = time.monotonic() + self.interval
        query = {'state': 'stored'}
        if saved.get('cursor'): query['_id'] = {'$gt': saved['cursor']}
        jobs = list(self.local.remote_event_outbox.find(query).sort('_id', 1).limit(self.batch))
        # A rollback usually loses newest writes first: also verify a small latest-write sample each round.
        # Historical partial loss still needs the rotating full sweep; do not claim instantaneous detection.
        recent = list(self.local.remote_event_outbox.find({'state': 'stored'}).sort('stored_at', -1).limit(10))
        verify = list({j['_id']: j for j in [*jobs, *recent]}.values())
        state, conn, job = dict(saved, interval_s=self.interval, batch_limit=self.batch), None, None
        try:
            self.remote.command('ping')
            conn = self.pool.connection()
            with conn.cursor() as cur:
                cur.execute('SELECT 1'); cur.fetchone()
            verify_batch(self.local, self.remote, conn, verify)
            state.update(state='ok', checked_at=utc_now(), checked_rows=len(jobs),
                         cursor=jobs[-1]['_id'] if jobs else None,
                         recent_sample_rows=len(recent), checked_total=state.get('checked_total', 0)+len(verify))
            if len(jobs) < self.batch:
                state.update(cursor=None, cycle_completed_at=utc_now(), cycles=state.get('cycles', 0)+1)
            state.pop('error_type', None)
            self.allowed = True
        except Conflict as exc:
            state.update(state='recovery_required', reason=str(exc), incident=uuid.uuid4().hex,
                         detected_at=utc_now(), checked_at=utc_now())
            self.allowed = False
        except Exception as exc:
            state.update(state='unavailable', error_type=type(exc).__name__, checked_at=utc_now())
            self.allowed = False
        finally:
            if conn is not None: conn.close()
        state['_id'] = KEY
        self.local.pipeline_controls.replace_one({'_id': KEY}, state, upsert=True)
        return self.allowed


def validate_all(local, remote, pool):
    """Explicit indexed full reconciliation with bounded client batches; never unlocks by itself."""
    conn, checked, batch = pool.connection(), 0, []
    try:
        for job in local.remote_event_outbox.find({'state': 'stored'}).sort('_id', 1).batch_size(100):
            batch.append(job)
            if len(batch) >= 100:
                verify_batch(local, remote, conn, batch); checked += len(batch); batch = []
        if batch:
            verify_batch(local, remote, conn, batch); checked += len(batch)
    finally: conn.close()
    return checked


def acknowledge(local, remote, pool, incident):
    old = local.pipeline_controls.find_one({'_id': KEY}) or {}
    if old.get('state') != 'recovery_required' or old.get('incident') != incident:
        raise ValueError('incident does not match current recovery latch')
    count = validate_all(local, remote, pool)
    result = local.pipeline_controls.update_one({'_id': KEY, 'state': 'recovery_required', 'incident': incident},
        {'$set': {'state': 'ok', 'cursor': None, 'checked_at': utc_now(), 'acknowledged_at': utc_now(),
                  'full_verified_rows': count}, '$unset': {'reason': '', 'event_id': ''}})
    if result.matched_count != 1: raise ValueError('recovery state changed during verification')
    return count


def main():
    from common.db import local_mongo, remote_mongo
    from remote.sql import pool
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['status', 'verify', 'acknowledge']); p.add_argument('--incident')
    a = p.parse_args(); local = local_mongo()
    if a.action == 'status':
        print(json.dumps(local.pipeline_controls.find_one({'_id': KEY}) or {'state': 'not_checked'}, default=str)); return
    if a.action == 'verify': result = {'verified_rows': validate_all(local, remote_mongo(), pool(1)), 'unlocked': False}
    else:
        if not a.incident: p.error('--incident is required')
        result = {'verified_rows': acknowledge(local, remote_mongo(), pool(1), a.incident), 'unlocked': True}
    print(json.dumps(result))


if __name__ == '__main__': main()
