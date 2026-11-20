"""P3 Silver (docs/DECISIONS.md D19, D23).

Two kinds of streams read Bronze:
  silver_<table>  dashboard path. State-store dedup on event_id (dropDuplicatesWithinWatermark, 7 days on
                  kafka_ts = Kafka retention) -> insert-only MERGE into Silver, bounded to the batch's
                  event_date range (BN-1) -> optional remote outbox staging.
  silver_audit    quarantine path. Keeps topic:event_id -> payload_hash in the state store and writes
                  id_conflict / invalid_json / invalid_schema rows to silver.quarantine.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

import sinks
import tables as tb
from audit_state import DECISION_SCHEMA, STATE_SCHEMA, audit
from common import settings

log = logging.getLogger("silver")

LOOKBACK_DAYS = 7  # >= collector MAX_EVENT_AGE (6 days) and Kafka retention (7 days)
LATE_SECONDS = 300  # event_time falls back to received_at when the clock gap exceeds 5 minutes
SPECS = {
    # topic: (json schema, table)
    "nv.learning.v2": (tb.LEARNING_JSON, "silver.learning_events"),
    "nv.update.v1": (tb.UPDATE_JSON, "silver.update_events"),
}


def complete():
    """Rows Silver accepts. A function: Column objects need an active SparkSession."""
    return (F.col("event_id").isNotNull() & F.col("payload_hash").isNotNull() & F.col("player_id").isNotNull()
            & F.col("event_type").isNotNull() & F.col("occurred_at").isNotNull()
            & F.col("received_at").isNotNull() & (F.col("schema_version") == 2))


def parse(df: DataFrame, schema) -> DataFrame:
    return (df.withColumn("j", F.from_json("value", schema))
            .select("value", F.col("topic").alias("kafka_topic"), F.col("partition").alias("kafka_partition"),
                    F.col("offset").alias("kafka_offset"), "kafka_ts", "j.*")
            .withColumn("occurred_at", F.to_timestamp("occurred_at"))
            .withColumn("received_at", F.to_timestamp("received_at")))


def merge_condition(lo, hi) -> str:
    """Insert-only MERGE key, bounded to the event_date partitions a legal duplicate can live in.

    The MERGE is the second line of defence behind the state-store dedup (e.g. after a checkpoint rebuild).
    event_time falls back to received_at for late events, so a resend can land on a later event_date than
    the original. Events older than 6 days are rejected by the collector (MAX_EVENT_AGE) and Kafka keeps
    7 days, so the original of any duplicate lies within 7 days before the batch: scan [lo - 7d, hi + 1d]
    instead of the whole table (BN-1, see DELTA_REQUIREMENTS_REVIEW section 5)."""
    cond = "t.event_id = s.event_id"
    if lo is not None and hi is not None:
        cond += (f" AND t.event_date BETWEEN DATE '{(lo - timedelta(days=LOOKBACK_DAYS)).isoformat()}'"
                 f" AND DATE '{(hi + timedelta(days=1)).isoformat()}'")
    return cond


def _write_silver(table: str, name: str):
    def write(batch: DataFrame, batch_id: int) -> None:
        from delta.tables import DeltaTable
        spark = batch.sparkSession
        started = time.monotonic()
        merged = staged = started
        # Events are immutable: replay inserts no extra rows; conflicting payloads never overwrite.
        source = batch.drop("kafka_ts").persist()
        try:
            if not source.isEmpty():
                lo, hi = source.agg(F.min("event_date"), F.max("event_date")).first()
                (DeltaTable.forPath(spark, tb.path(table)).alias("t")
                 .merge(source.alias("s"), merge_condition(lo, hi))
                 .whenNotMatchedInsertAll().execute())
                merged = time.monotonic()
                if settings.get().remote_export_enabled:
                    sinks.stage_outbox(row.asDict(recursive=True) for row in source.toLocalIterator())
                staged = time.monotonic()
        finally:
            source.unpersist()
        log.info("silver %s batch %s in %.1fs (merge %.1fs, outbox %.1fs)", name, batch_id,
                 time.monotonic() - started, max(0.0, merged - started), max(0.0, staged - merged))
    return write


def start_silver(spark, topic: str):
    s = settings.get()
    schema, table = SPECS[topic]
    name = table.split(".")[1]
    rows = (parse(spark.readStream.format("delta").load(tb.path("bronze.game_events"))
                  .where(F.col("topic") == topic), schema)
            .where(complete())
            .withWatermark("kafka_ts", f"{s.dedup_ttl_hours} hours")
            .dropDuplicatesWithinWatermark(["event_id"])
            .withColumn("event_time",
                        F.when(F.abs(F.col("occurred_at").cast("long") - F.col("received_at").cast("long"))
                               > LATE_SECONDS, F.col("received_at")).otherwise(F.col("occurred_at")))
            .withColumn("event_date", F.to_date("event_time"))
            # kafka_ts (the watermark column) must stay in the streaming plan; it is dropped per batch
            .select(*tb.SCHEMAS[table][0].fieldNames(), "kafka_ts"))
    return (rows.writeStream.queryName("silver_" + name).foreachBatch(_write_silver(table, name))
            .option("checkpointLocation", tb.checkpoint(f"silver-{name}-v2"))
            .trigger(processingTime=s.stage_trigger).start())


def start_silver_learning(spark):
    return start_silver(spark, "nv.learning.v2")


def start_silver_update(spark):
    return start_silver(spark, "nv.update.v1")


def _append(df: DataFrame, table: str, app: str, batch_id: int) -> None:
    # idempotent append: a replayed batch_id is skipped by Delta (txnAppId/txnVersion)
    (df.write.format("delta").mode("append")
     .option("txnAppId", app).option("txnVersion", batch_id).save(tb.path(table)))


def to_quarantine(decisions: DataFrame, batch_id: int) -> None:
    started = time.monotonic()
    decisions = decisions.persist()
    try:
        q = (decisions.where(F.col("action") != "first")
             .select(F.col("topic").alias("kafka_topic"), F.col("partition").alias("kafka_partition"),
                     F.col("offset").alias("kafka_offset"),
                     F.when(F.col("action") == "id_conflict", F.lit("id_conflict"))
                      .when(F.get_json_object("value", "$").isNull(), F.lit("invalid_json"))
                      .otherwise(F.lit("invalid_schema")).alias("reason"),
                     "event_id", "value", F.current_timestamp().alias("detected_at")))
        # first copies that the silver stream rejects as incomplete are invalid_schema too
        for topic, (schema, _) in SPECS.items():
            first = parse(decisions.where((F.col("action") == "first") & (F.col("topic") == topic))
                          .withColumn("kafka_ts", F.current_timestamp()), schema)
            q = q.unionByName(first.where(~complete()).select(
                "kafka_topic", "kafka_partition", "kafka_offset", F.lit("invalid_schema").alias("reason"),
                "event_id", "value", F.current_timestamp().alias("detected_at")))
        q = q.persist()
        if q.limit(1).count():
            _append(q, "silver.quarantine", "silver-quarantine-v2", batch_id)
        q.unpersist()
    finally:
        decisions.unpersist()
    log.info("audit batch %s in %.1fs", batch_id, time.monotonic() - started)


def start_silver_audit(spark):
    from pyspark.sql.streaming.state import GroupStateTimeout
    bronze = (spark.readStream.format("delta").load(tb.path("bronze.game_events"))
              .where(F.col("topic").isin(*SPECS)))
    eid = F.get_json_object("value", "$.event_id")
    phash = F.get_json_object("value", "$.payload_hash")
    keyed = bronze.select(
        F.when(eid.isNotNull() & phash.isNotNull(), F.concat_ws(":", "topic", eid))
         .otherwise(F.concat_ws(":", F.lit("bad"), "topic", "partition", "offset")).alias("key"),
        "value", "topic", "partition", "offset", eid.alias("event_id"), phash.alias("hash"))
    decisions = keyed.groupBy("key").applyInPandasWithState(
        audit, outputStructType=DECISION_SCHEMA, stateStructType=STATE_SCHEMA,
        outputMode="append", timeoutConf=GroupStateTimeout.ProcessingTimeTimeout)
    return (decisions.writeStream.queryName("silver_audit").foreachBatch(to_quarantine)
            .option("checkpointLocation", tb.checkpoint("silver-audit-v2"))
            .trigger(processingTime=settings.get().audit_trigger).start())
