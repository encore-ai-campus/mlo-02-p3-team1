"""Driver timers: rt_summary (10 s), gold.version_adoption -> rt_versions (60 s), progress file."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from pyspark.sql import functions as F

import sinks
import tables as tb
from common import settings
from common.timeutil import iso_ms, utc_now

log = logging.getLogger("periodic")


def refresh_summary(spark) -> None:
    recent = (spark.read.format("delta").load(tb.path("silver.learning_events"))
              .where(F.col("event_date") >= F.date_sub(F.current_date(), 1)))
    r = recent.agg(
        F.sum(F.when(F.col("received_at") >= F.expr("current_timestamp() - INTERVAL 1 MINUTE"), 1).otherwise(0))
        .alias("events_last_1m"),
        F.countDistinct(F.when(F.col("received_at") >= F.expr("current_timestamp() - INTERVAL 5 MINUTES"),
                               F.col("session_id"))).alias("active_sessions_5m")).first()
    sinks.upsert("rt_summary", [{"_id": "global", "events_last_1m": int(r.events_last_1m or 0),
                                 "active_sessions_5m": int(r.active_sessions_5m or 0),
                                 "updated_at": utc_now()}])


def refresh_version_adoption(spark) -> None:
    from delta.tables import DeltaTable
    tb.register_names(spark)
    latest = spark.sql("""
        SELECT player_id, build_version, content_version,
               row_number() OVER (PARTITION BY player_id ORDER BY event_time DESC) AS rn
        FROM (SELECT player_id, build_version, content_version, event_time FROM silver.learning_events
              WHERE event_date >= date_sub(current_date(), 1)
              UNION ALL
              SELECT player_id, build_version, content_version, event_time FROM silver.update_events
              WHERE event_date >= date_sub(current_date(), 1))
        WHERE event_time >= current_timestamp() - INTERVAL 24 HOURS""").where("rn = 1")
    latest = latest.persist()
    try:
        total = latest.count()
        per = (latest.select(F.lit("build").alias("kind"), F.col("build_version").alias("version"))
               .unionByName(latest.select(F.lit("content").alias("kind"), F.col("content_version").alias("version")))
               .groupBy("kind", "version").agg(F.count(F.lit(1)).alias("installs"))
               .withColumn("share", F.col("installs") / F.lit(total if total else 1))
               .withColumn("updated_at", F.current_timestamp())).persist()
        try:
            (DeltaTable.forPath(spark, tb.path("gold.version_adoption")).alias("t")
             .merge(per.alias("s"), "t.kind = s.kind AND t.version = s.version")
             .whenMatchedUpdateAll().whenNotMatchedInsertAll().whenNotMatchedBySourceDelete().execute())
            docs = [dict(r.asDict(), _id=f"{r.kind}:{r.version}") for r in per.collect()]
            sinks.upsert("rt_versions", docs)
            # versions with no install in the last 24 h are removed in Delta and in MongoDB (D12)
            sinks.delete_missing("rt_versions", [d["_id"] for d in docs])
        finally:
            per.unpersist()
    finally:
        latest.unpersist()


def write_progress(spark, restarts: dict) -> None:
    """Observability outside stdout; rows/rates are per query, not end-to-end throughput."""
    destination = Path(settings.get().progress_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = {"updated_at": iso_ms(), "sink_failures": sinks.failures(), "query_restarts": restarts,
              "queries": [{"name": q.name, "active": q.isActive, "status": q.status, "progress": q.lastProgress}
                          for q in spark.streams.active]}
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, default=str), encoding="utf-8")
    temporary.replace(destination)


def run(spark, stop: threading.Event, restarts: dict) -> None:
    last_versions = 0.0
    while not stop.wait(10):
        try:
            write_progress(spark, restarts)
            refresh_summary(spark)
            if time.monotonic() - last_versions >= 60:
                refresh_version_adoption(spark)
                last_versions = time.monotonic()
        except Exception:  # keep the streams alive; next tick retries
            log.exception("periodic refresh failed")
