"""Durable export worker. Never resets existing 'stored' history or target data.

Throughput design (2026-11-20, BN-5/BN-7 in docs/DATA_FLOW_AND_GAPS.md):
  - MySQL connections come from a DBCP-style pool (DBUtils PooledDB) instead of one connect per event.
  - The cross-tool writer lock (GET_LOCK) is held once by a dedicated connection for the worker's lifetime,
    instead of being taken per event on a fresh connection (which also serialised every event).
  - Due outbox rows are claimed in batches and grouped by source session. Events of one session are
    processed in sequence order on one thread; different sessions run in parallel.
  - rt_* metrics are mirrored on their own thread, only rows changed since the last copy, with bulk writes.
A single lease still guarantees one worker process; parallelism is inside that process.
"""
import json
import os
import socket
import time
import atexit
import signal
import threading
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pymysql
from pymongo import MongoClient, ReturnDocument, UpdateOne
from pymongo.errors import DuplicateKeyError
from remote.projection import Projector, Waiting, Conflict, dt

DUE_STATES = ["pending", "retrying", "waiting_context"]
METRIC_COLLECTIONS = ["rt_minigame_1m", "rt_alerts", "rt_updates", "rt_versions", "rt_summary"]
WRITER_LOCK = "nodeverse_direct_loader"
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def now():
    return datetime.now(timezone.utc)


def _sql_params():
    return dict(host=os.environ["DIRECT_MYSQL_HOST"], port=int(os.getenv("DIRECT_MYSQL_PORT", "3306")),
                user=os.environ["DIRECT_MYSQL_USER"], password=os.environ["DIRECT_MYSQL_PASSWORD"],
                database=os.getenv("DIRECT_MYSQL_DATABASE", "nodeverse"), charset="utf8mb4",
                connect_timeout=5, read_timeout=6, write_timeout=6, autocommit=False)


def sql_connect():
    return pymysql.connect(**_sql_params())


def sql_pool(size):
    """DBCP-style pool: reuse up to `size` connections, block when all are busy, ping before reuse."""
    from dbutils.pooled_db import PooledDB
    return PooledDB(creator=pymysql, mincached=1, maxcached=size, maxconnections=size, blocking=True,
                    ping=1, reset=True, **_sql_params())


def contexts():
    p = Path(os.getenv("REMOTE_CONTEXT_PATH", "/run/private/remote-context.json"))
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"members": {}}


def claim(local):
    # Earliest due work wins; a low-sequence context retry must not starve arrivals.
    return local.remote_event_outbox.find_one_and_update(
        {"state": {"$in": DUE_STATES}, "next_attempt_at": {"$lte": now()}},
        {"$set": {"state": "processing", "updated_at": now()}, "$inc": {"attempts": 1}},
        sort=[("next_attempt_at", 1), ("queued_at", 1), ("sequence", 1), ("_id", 1)],
        return_document=ReturnDocument.AFTER)


def claim_batch(local, limit):
    """Claim up to `limit` due rows in one round trip pair. Safe because the lease allows one worker process."""
    rows = list(local.remote_event_outbox.find(
        {"state": {"$in": DUE_STATES}, "next_attempt_at": {"$lte": now()}},
        sort=[("next_attempt_at", 1), ("queued_at", 1), ("sequence", 1), ("_id", 1)], limit=limit))
    if not rows:
        return []
    stamp = now()
    ids = [r["_id"] for r in rows]
    local.remote_event_outbox.update_many({"_id": {"$in": ids}, "state": {"$in": DUE_STATES}},
                                          {"$set": {"state": "processing", "updated_at": stamp}, "$inc": {"attempts": 1}})
    for r in rows:
        r["attempts"] = r.get("attempts", 0) + 1
        r["state"] = "processing"
    return rows


def group_by_session(jobs):
    """Session events stay in sequence order on one thread; other jobs are independent groups."""
    groups = defaultdict(list)
    for job in jobs:
        groups[job.get("source_session_id") or job["_id"]].append(job)
    for g in groups.values():
        g.sort(key=lambda j: (j.get("sequence", 0), j.get("queued_at") or EPOCH, j["_id"]))
    return list(groups.values())


def acquire(local, owner):
    try:
        doc = local.remote_worker_lease.find_one_and_update(
            {"_id": "writer", "$or": [{"owner": owner}, {"expires_at": {"$lte": now()}}]},
            {"$set": {"owner": owner, "expires_at": now() + timedelta(seconds=45)}},
            upsert=True, return_document=ReturnDocument.AFTER)
        return doc.get("owner") == owner
    except DuplicateKeyError:
        return False


class WriterLock:
    """Holds MySQL GET_LOCK on one dedicated connection so other direct loaders stay excluded."""

    def __init__(self, connect=sql_connect):
        self._connect = connect
        self._conn = None

    def ensure(self):
        try:
            if self._conn is not None:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT IS_USED_LOCK(%s) = CONNECTION_ID()", (WRITER_LOCK,))
                    if cur.fetchone()[0] == 1:
                        return True
            self.release()
            self._conn = self._connect()
            with self._conn.cursor() as cur:
                cur.execute("SELECT GET_LOCK(%s, 0)", (WRITER_LOCK,))
                if cur.fetchone()[0] == 1:
                    return True
        except Exception:
            pass
        self.release()
        return False

    def release(self):
        if self._conn is not None:
            try:
                self._conn.close()  # closing the session releases GET_LOCK
            except Exception:
                pass
        self._conn = None


def mirror_metrics(local, remote, since=None):
    """Copy rt_* rows changed since `since` (per collection) with an atomic newer-wins guard.

    Returns the new high-water marks. `since=None` copies everything (first run)."""
    marks = dict(since or {})
    for name in METRIC_COLLECTIONS:
        query = {"updated_at": {"$type": "date"}}
        if marks.get(name):
            # small overlap: a writer may commit an older updated_at slightly after a newer one
            query = {"updated_at": {"$gte": marks[name] - timedelta(seconds=30)}}
        ops, top = [], marks.get(name)
        for source in local[name].find(query):
            if not isinstance(source.get("updated_at"), datetime):
                continue
            doc = dict(source, sink_source="nodeverse-v2")
            # Atomic timestamp guard: a delayed older projection must not overwrite a newer aggregate.
            ops.append(UpdateOne({"_id": doc["_id"]}, [{"$replaceWith": {"$cond": [
                {"$gte": [{"$literal": doc["updated_at"]}, {"$ifNull": ["$updated_at", EPOCH]}]},
                {"$literal": doc}, "$$ROOT"]}}], upsert=True))
            u = doc["updated_at"] if doc["updated_at"].tzinfo else doc["updated_at"].replace(tzinfo=timezone.utc)
            top = u if top is None or u > top else top
        if ops:
            remote[name].bulk_write(ops, ordered=False)
        if top is not None:
            marks[name] = top
    keep = [x["_id"] for x in local.rt_versions.find({}, {"_id": 1})]
    remote.rt_versions.delete_many({"sink_source": "nodeverse-v2", "_id": {"$nin": keep}})
    return marks


def process_job(job, local, remote, pool, ctx, have_lock):
    """Project one outbox row and record its terminal or retry state. Never raises."""
    try:
        event = job["event"]
        Projector(local, remote, None, {}).archive(event)
        local.remote_event_outbox.update_one({"_id": job["_id"], "remote_archive_stored_at": {"$exists": False}},
                                             {"$set": {"archive_stored": True, "remote_archive_stored_at": now()}})
        sql = None
        try:
            if event.get("schema_version") == 2 and event.get("session_id"):
                if not have_lock:
                    raise Waiting("other_database_writer_active")
                sql = pool.connection()
            result = Projector(local, remote, sql, ctx).project(event)
        finally:
            if sql is not None:
                sql.close()  # back to the pool
        state = "quarantined" if result.get("scope") == "learning_quarantine" else "stored"
        completed = now()
        local.remote_event_outbox.update_one({"_id": job["_id"]}, {"$set": {
            "state": state, "completed_at": completed,
            ("quarantined_at" if state == "quarantined" else "stored_at"): completed,
            "updated_at": completed, "result": result, "archive_stored": True,
            "queue_to_terminal_ms": max(0, int((completed - job["queued_at"]).total_seconds() * 1000))},
            "$unset": {"reason": "", "last_error": ""}})
    except Waiting as e:
        archived = remote["pipeline_learning_events"].find_one({"_id": job["_id"]}, {"_id": 1}) is not None
        local.remote_event_outbox.update_one({"_id": job["_id"]}, {"$set": {
            "state": "waiting_context", "reason": str(e), "archive_stored": archived,
            "updated_at": now(), "next_attempt_at": now() + timedelta(seconds=min(60, 5 * 2 ** min(job["attempts"] - 1, 4)))}})
    except (Conflict, ValueError, KeyError, TypeError) as e:
        local.remote_event_outbox.update_one({"_id": job["_id"]}, {"$set": {
            "state": "blocked", "reason": str(e)[:200], "updated_at": now()}})
    except Exception as e:
        local.remote_event_outbox.update_one({"_id": job["_id"]}, {"$set": {
            "state": "retrying", "last_error": type(e).__name__, "updated_at": now(),
            "next_attempt_at": now() + timedelta(seconds=min(60, 2 ** min(job["attempts"], 5)))}})


def process_group(jobs, *args):
    for job in jobs:
        process_job(job, *args)


def main():
    workers = int(os.getenv("REMOTE_WORKERS", "8"))
    batch = int(os.getenv("REMOTE_BATCH", "200"))
    pool_size = int(os.getenv("REMOTE_SQL_POOL_SIZE", str(workers)))
    lc = MongoClient(os.getenv("MONGO_URI", "mongodb://mongo:27017"), tz_aware=True, serverSelectionTimeoutMS=5000,
                     socketTimeoutMS=7000, maxPoolSize=workers * 2 + 4)
    local = lc[os.getenv("MONGO_DB", "nodeverse_logs")]
    rc = MongoClient(os.environ["DIRECT_MONGO_URI"], tz_aware=True, serverSelectionTimeoutMS=5000,
                     socketTimeoutMS=7000, maxPoolSize=workers * 2 + 4)
    remote = rc[os.getenv("DIRECT_MONGO_DATABASE", "nodeverse_logs")]
    owner = socket.gethostname() + ":" + str(uuid.uuid4())
    local.remote_event_outbox.create_index([("state", 1), ("next_attempt_at", 1)])
    pool = sql_pool(pool_size)
    lock = WriterLock()
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sink")
    recovered = False
    stop = threading.Event()
    leased = threading.Event()

    def release():
        stop.set()
        lock.release()
        try:
            local.remote_worker_lease.delete_one({"_id": "writer", "owner": owner})
        except Exception:
            pass
    atexit.register(release)

    def shutdown(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)

    def heartbeat():
        while not stop.wait(10):
            try:
                local.remote_worker_lease.update_one({"_id": "writer", "owner": owner},
                                                     {"$set": {"expires_at": now() + timedelta(seconds=45)}})
            except Exception:
                pass

    def metrics_loop():
        marks = None
        while not stop.wait(5):
            if not leased.is_set():
                continue
            try:
                marks = mirror_metrics(local, remote, marks)
            except Exception as e:
                print(json.dumps({"component": "remote_sink", "task": "mirror_metrics", "error": type(e).__name__}), flush=True)

    threading.Thread(target=heartbeat, daemon=True).start()
    threading.Thread(target=metrics_loop, daemon=True, name="metrics").start()
    print(json.dumps({"component": "remote_sink", "workers": workers, "batch": batch, "sql_pool": pool_size}), flush=True)
    while True:
        try:
            if not acquire(local, owner):
                leased.clear()
                time.sleep(2)
                continue
            leased.set()
            local.remote_event_outbox.update_many(
                {"state": "processing", "updated_at": {"$lt": now() - timedelta(minutes=5)}},
                {"$set": {"state": "pending", "next_attempt_at": now()}})
            if not recovered:
                local.remote_event_outbox.update_many({"state": "processing"}, {"$set": {"state": "pending", "next_attempt_at": now()}})
                recovered = True
            jobs = claim_batch(local, batch)
            if not jobs:
                local.remote_sink_health.update_one({"_id": "worker"}, {"$set": {"state": "ready", "updated_at": now()}}, upsert=True)
                time.sleep(0.5)
                continue
            local.remote_sink_health.update_one({"_id": "worker"}, {"$set": {"state": "processing", "updated_at": now()}}, upsert=True)
            needs_sql = any(j["event"].get("schema_version") == 2 and j["event"].get("session_id") for j in jobs)
            have_lock = lock.ensure() if needs_sql else True
            ctx = contexts()
            futures = [executor.submit(process_group, g, local, remote, pool, ctx, have_lock) for g in group_by_session(jobs)]
            wait(futures)
            for f in futures:
                if f.exception() is not None:  # process_job never raises; keep the loop alive regardless
                    print(json.dumps({"component": "remote_sink", "error": type(f.exception()).__name__}), flush=True)
        except Exception as e:
            # Never log credentials/connection strings or raw DB error text.
            try:
                local.remote_sink_health.update_one({"_id": "worker"}, {"$set": {
                    "state": "error", "error_type": type(e).__name__, "updated_at": now()}}, upsert=True)
            except Exception:
                pass
            print(json.dumps({"component": "remote_sink", "error": type(e).__name__}), flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
