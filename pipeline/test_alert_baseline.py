"""Failure-spike alert baseline (follow-up review 2026-11-21 #1).

The baseline must use the same late-event rule and the same failure-rate formula as the current 5-minute window:
it is read from the alert query's own on-time windows (k-30, k-25, ..., k-5), not from gold.minigame_1m."""
import importlib.util
import sys
from datetime import datetime, timedelta

import pytest

if importlib.util.find_spec("pyspark") is None:
    pytest.skip("pyspark not installed", allow_module_level=True)

sys.path.insert(0, "spark")


@pytest.fixture(scope="module")
def spark():
    from pyspark.sql import SparkSession
    s = (SparkSession.builder.master("local[1]").appName("alert-baseline-test")
         .config("spark.sql.shuffle.partitions", "1").config("spark.ui.enabled", "false")
         .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    yield s
    s.stop()


K = datetime(2026, 11, 24, 12, 0)


def _cur(spark, rows):
    from pyspark.sql import functions as F
    df = spark.createDataFrame(
        [(K + timedelta(minutes=m), K + timedelta(minutes=m + 5), g, "stack", a, s, f) for m, g, a, s, f in rows],
        "window_start timestamp, window_end timestamp, minigame_id string, category string, "
        "attempts long, successes long, failures long")
    return df.withColumn("failure_rate", F.when((F.col("successes") + F.col("failures")) > 0,
                                                F.col("failures") / (F.col("successes") + F.col("failures"))))


def _hist(spark, rows):
    return spark.createDataFrame([(g, K + timedelta(minutes=m), s, f) for m, g, s, f in rows],
                                 "h_game string, h_start timestamp, h_s long, h_f long")


def _by_game(df):
    return {r.minigame_id: r for r in df.collect()}


def test_baseline_uses_six_non_overlapping_windows_only(spark):
    import gold
    cur = _cur(spark, [(0, "g1", 40, 10, 30)])
    # windows that tile [k-30, k): -30, -25, ..., -5 ; overlapping sliding windows (-29, -4, ...) and the
    # current window itself must not be counted, or the same event would be counted up to five times
    tiles = [(m, "g1", 9, 1) for m in (-30, -25, -20, -15, -10, -5)]
    noise = [(-29, "g1", 0, 100), (-4, "g1", 0, 100), (-1, "g1", 0, 100), (0, "g1", 0, 100), (-35, "g1", 0, 100),
             (-10, "other", 0, 100)]
    r = _by_game(gold.with_baseline(cur, _hist(spark, tiles + noise)))["g1"]
    assert r.baseline_rate == pytest.approx(6 / 60)
    assert r.alert is True  # 0.75 >= 0.4 and >= 1.5 x 0.1


def test_late_backlog_no_longer_hides_a_real_spike(spark):
    """Old behaviour: a late offline backlog of failures counted in gold.minigame_1m raised the baseline to ~0.9,
    so a real 0.75 spike was not >= 1.5 x baseline. The alert query's own windows exclude late events, so the
    baseline stays at the on-time rate and the spike is caught."""
    import gold
    cur = _cur(spark, [(0, "g1", 40, 10, 30)])
    on_time = [(m, "g1", 18, 2) for m in (-30, -25, -20, -15, -10, -5)]
    r = _by_game(gold.with_baseline(cur, _hist(spark, on_time)))["g1"]
    assert r.baseline_rate == pytest.approx(0.1) and r.alert is True


def test_no_history_means_no_baseline_and_absolute_rule_only(spark):
    import gold
    cur = _cur(spark, [(0, "g1", 40, 10, 30), (0, "g2", 5, 0, 5)])
    rows = _by_game(gold.with_baseline(cur, _hist(spark, [])))
    assert rows["g1"].baseline_rate is None and rows["g1"].alert is True
    assert rows["g2"].alert is False  # below ALERT_MIN_ATTEMPTS


def test_steady_high_failure_rate_is_not_a_spike(spark):
    import gold
    cur = _cur(spark, [(0, "g1", 40, 10, 30)])
    r = _by_game(gold.with_baseline(cur, _hist(spark, [(m, "g1", 5, 15) for m in (-30, -25, -20, -15, -10, -5)])))
    assert r["g1"].baseline_rate == pytest.approx(0.75) and r["g1"].alert is False


def test_window_updated_in_this_batch_replaces_its_stored_value(spark, tmp_path, monkeypatch):
    """alert_history: a k-5 window updated in the same batch is read with its new counts, not the stored ones."""
    import gold
    import tables as tb
    path = str(tmp_path / "alerts")
    monkeypatch.setattr(tb, "path", lambda name: path)
    stored = _cur(spark, [(-5, "g1", 10, 10, 0)]).selectExpr(
        "*", "CAST(NULL AS DOUBLE) AS baseline_rate", "false AS alert", "current_timestamp() AS updated_at")
    stored.write.format("parquet").save(path)
    cur = _cur(spark, [(-5, "g1", 30, 10, 20), (0, "g1", 40, 10, 30)])
    hist = gold.alert_history(spark, cur, K - timedelta(minutes=5), reader=lambda s, p: s.read.parquet(p))
    got = {(r.h_start, r.h_game): (r.h_s, r.h_f) for r in hist.collect()}
    assert got[(K - timedelta(minutes=5), "g1")] == (10, 20)  # the batch's value, not the stored (10, 0)
    assert len(got) == 2
