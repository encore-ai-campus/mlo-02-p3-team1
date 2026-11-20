"""P4 Gold windows -> Delta + MongoDB rt_* (D21: MERGE bounded by window_start)."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

import sinks
import tables as tb
from common import settings
from common.timeutil import window_key

log = logging.getLogger("gold")

ALERT_MIN_ATTEMPTS = 20
ALERT_MIN_RATE = 0.4
ALERT_BASELINE_FACTOR = 1.5


def count_of(event_type: str):
    return F.sum(F.when(F.col("event_type") == event_type, 1).otherwise(0)).cast("long")


def merge(spark, table: str, df: DataFrame, keys: list[str]) -> None:
    from delta.tables import DeltaTable
    cond = " AND ".join(f"t.{k} = s.{k}" for k in keys)
    # every Gold table is keyed by window_start: a literal lower bound lets Delta skip files of older windows
    # by their min/max stats, so the MERGE reads only recent files however long the table grows (D21)
    lo = df.agg(F.min("window_start")).first()[0]
    if lo is None:
        return
    cond += f" AND t.window_start >= TIMESTAMP '{lo.strftime('%Y-%m-%d %H:%M:%S')}'"
    (DeltaTable.forPath(spark, tb.path(table)).alias("t").merge(df.alias("s"), cond)
     .whenMatchedUpdateAll().whenNotMatchedInsertAll().execute())


def gold_minigame(agg: DataFrame, batch_id: int) -> None:
    started = time.monotonic()
    rows = (agg.select(F.col("window.start").alias("window_start"), F.col("window.end").alias("window_end"),
                       "minigame_id", "category", "attempts", "successes", "failures", "hints", "players")
            .withColumn("success_rate", F.when((F.col("successes") + F.col("failures")) > 0,
                                               F.col("successes") / (F.col("successes") + F.col("failures"))))
            .withColumn("updated_at", F.current_timestamp())).persist()
    try:
        merge(agg.sparkSession, "gold.minigame_1m", rows, ["window_start", "minigame_id"])
        sinks.upsert("rt_minigame_1m", [dict(r.asDict(), _id=f"{r.minigame_id}:{window_key(r.window_start)}")
                                        for r in rows.collect()])
    finally:
        rows.unpersist()
    log.info("gold_1m batch %s in %.1fs", batch_id, time.monotonic() - started)


def gold_alerts(agg: DataFrame, batch_id: int) -> None:
    spark = agg.sparkSession
    cur = (agg.select(F.col("window.start").alias("window_start"), F.col("window.end").alias("window_end"),
                      "minigame_id", "category", "attempts", "successes", "failures")
           .withColumn("failure_rate", F.when((F.col("successes") + F.col("failures")) > 0,
                                              F.col("failures") / (F.col("successes") + F.col("failures"))))
           .localCheckpoint())
    # baseline = failure rate over the 30 minutes before the window, from gold.minigame_1m
    lo = cur.agg(F.min("window_start")).first()[0]
    if lo is None:
        return
    hist = (spark.read.format("delta").load(tb.path("gold.minigame_1m"))
            .where(F.col("window_start") >= F.lit(lo - timedelta(minutes=30)))  # file skipping (D21)
            .select(F.col("minigame_id").alias("h_game"), F.col("window_start").alias("h_start"),
                    F.col("successes").alias("h_s"), F.col("failures").alias("h_f")))
    keys = cur.select(F.col("window_start").alias("k_start"), F.col("minigame_id").alias("k_game")).distinct()
    joined = keys.join(hist, (keys.k_game == hist.h_game)
                       & (hist.h_start >= keys.k_start - F.expr("INTERVAL 30 MINUTES"))
                       & (hist.h_start < keys.k_start), "left")
    base = (joined.groupBy("k_start", "k_game")
            .agg(F.sum("h_f").alias("bf"), F.sum(F.col("h_s") + F.col("h_f")).alias("bt"))
            .select(F.col("k_start").alias("window_start"), F.col("k_game").alias("minigame_id"),
                    F.when(F.col("bt") > 0, F.col("bf") / F.col("bt")).alias("baseline_rate")))
    rows = (cur.join(base, ["window_start", "minigame_id"], "left")
            .withColumn("alert", (F.col("attempts") >= ALERT_MIN_ATTEMPTS)
                        & F.coalesce(F.col("failure_rate") >= ALERT_MIN_RATE, F.lit(False))
                        & (F.col("baseline_rate").isNull()
                           | (F.col("failure_rate") >= F.col("baseline_rate") * ALERT_BASELINE_FACTOR)))
            .withColumn("updated_at", F.current_timestamp())
            .select(*tb.SCHEMAS["gold.failure_alerts"][0].fieldNames())).persist()
    try:
        merge(spark, "gold.failure_alerts", rows, ["window_start", "minigame_id"])
        sinks.upsert("rt_alerts", [dict(r.asDict(), _id=f"{r.minigame_id}:{window_key(r.window_start)}")
                                   for r in rows.collect()])
    finally:
        rows.unpersist()


def start_gold_1m(spark):
    silver = spark.readStream.format("delta").load(tb.path("silver.learning_events"))
    one_min = (silver.withWatermark("event_time", "2 minutes")
               .groupBy(F.window("event_time", "1 minute"), "minigame_id", "category")
               .agg(count_of("attempt_started").alias("attempts"), count_of("attempt_succeeded").alias("successes"),
                    count_of("attempt_failed").alias("failures"), count_of("hint_used").alias("hints"),
                    F.approx_count_distinct("player_id").alias("players")))
    return (one_min.writeStream.outputMode("update").queryName("gold_1m").foreachBatch(gold_minigame)
            .option("checkpointLocation", tb.checkpoint("gold-minigame-1m-v1"))
            .trigger(processingTime=settings.get().stage_trigger).start())


def start_gold_alert(spark):
    silver = spark.readStream.format("delta").load(tb.path("silver.learning_events"))
    five_min = (silver.withWatermark("event_time", "2 minutes")
                .groupBy(F.window("event_time", "5 minutes", "1 minute"), "minigame_id", "category")
                .agg(count_of("attempt_started").alias("attempts"), count_of("attempt_succeeded").alias("successes"),
                     count_of("attempt_failed").alias("failures")))
    return (five_min.writeStream.outputMode("update").queryName("gold_alert").foreachBatch(gold_alerts)
            .option("checkpointLocation", tb.checkpoint("gold-failure-alerts-v1"))
            .trigger(processingTime=settings.get().stage_trigger).start())


# ---------------------------------------------------------------- P4-2 update progress
def gold_updates(agg: DataFrame, batch_id: int) -> None:
    spark = agg.sparkSession
    cur = agg.select(F.col("window.start").alias("window_start"), F.col("window.end").alias("window_end"),
                     "target_version", "checks", "prompted", "accepted", "dismissed", "downloads_started",
                     "downloads_succeeded", "downloads_failed", "mounted", "p50_duration_ms").persist()
    try:
        bounds = cur.agg(F.min("window_start").alias("lo"), F.max("window_end").alias("hi")).first()
        if bounds is None or bounds.lo is None:
            return
        failed = (spark.read.format("delta").load(tb.path("silver.update_events"))
                  .where((F.col("event_type") == "pack_download_failed")
                         & (F.col("event_time") >= F.lit(bounds.lo)) & (F.col("event_time") < F.lit(bounds.hi)))
                  .select(F.window("event_time", "5 minutes").start.alias("window_start"),
                          F.coalesce(F.col("details.target_version"), F.lit("none")).alias("target_version"),
                          F.col("details.failure_reason").alias("reason"))
                  .groupBy("window_start", "target_version", "reason").count())
        w = Window.partitionBy("window_start", "target_version").orderBy(F.desc("count"), F.asc("reason"))
        top = (failed.withColumn("rn", F.row_number().over(w)).where("rn = 1")
               .select("window_start", "target_version", F.col("reason").alias("top_failure_reason")))
        done = F.col("downloads_succeeded") + F.col("downloads_failed")
        rows = (cur.join(top, ["window_start", "target_version"], "left")
                .withColumn("failure_rate", F.when(done > 0, F.col("downloads_failed") / done))
                .withColumn("updated_at", F.current_timestamp())
                .select(*tb.SCHEMAS["gold.update_progress_5m"][0].fieldNames())).persist()
        try:
            merge(spark, "gold.update_progress_5m", rows, ["window_start", "target_version"])
            sinks.upsert("rt_updates", [dict(r.asDict(), _id=f"{r.target_version}:{window_key(r.window_start)}")
                                        for r in rows.collect()])
        finally:
            rows.unpersist()
    finally:
        cur.unpersist()


def start_gold_update(spark):
    silver = spark.readStream.format("delta").load(tb.path("silver.update_events"))
    agg = (silver.withWatermark("event_time", "10 minutes")
           .withColumn("target_version", F.coalesce(F.col("details.target_version"), F.lit("none")))
           .groupBy(F.window("event_time", "5 minutes"), "target_version")
           .agg(count_of("update_checked").alias("checks"), count_of("update_prompted").alias("prompted"),
                count_of("update_accepted").alias("accepted"), count_of("update_dismissed").alias("dismissed"),
                count_of("pack_download_started").alias("downloads_started"),
                count_of("pack_download_succeeded").alias("downloads_succeeded"),
                count_of("pack_download_failed").alias("downloads_failed"),
                count_of("pack_mounted").alias("mounted"),
                F.percentile_approx(F.when(F.col("event_type") == "pack_download_succeeded",
                                           F.col("details.duration_ms")), 0.5).cast("long").alias("p50_duration_ms")))
    return (agg.writeStream.outputMode("update").queryName("gold_update").foreachBatch(gold_updates)
            .option("checkpointLocation", tb.checkpoint("gold-update-progress-v1"))
            .trigger(processingTime=settings.get().stage_trigger).start())
