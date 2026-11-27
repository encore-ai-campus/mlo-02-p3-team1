"""Exercise maintenance dispatch without starting another Spark process."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from common import settings


def load(monkeypatch, name):
    monkeypatch.setitem(sys.modules, 'tables', SimpleNamespace())
    spec=importlib.util.spec_from_file_location('review_'+name, Path(__file__).parent/'spark'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_default_never_runs_optimize_in_streaming(monkeypatch):
    monkeypatch.delenv('COMPACTION_MODE',raising=False)
    s=settings.Settings()
    assert s.compaction_mode=='maintenance'
    module=load(monkeypatch,'compaction')
    monkeypatch.setattr(settings,'get',lambda:s)
    def unexpected(*a,**k):pytest.fail('streaming must not execute OPTIMIZE in maintenance mode')
    monkeypatch.setattr(module,'_optimize',unexpected)
    module.compact_after_write(None,'silver.learning_events','event_date',['2026-11-27'])
    module.compact_append_only(None)


def test_explicit_legacy_inline_mode_still_works(monkeypatch):
    monkeypatch.setenv('COMPACTION_MODE','inline')
    monkeypatch.setenv('COMPACT_EVERY_BATCHES','1')
    s=settings.Settings();monkeypatch.setattr(settings,'get',lambda:s)
    module=load(monkeypatch,'compaction');calls=[]
    monkeypatch.setattr(module,'_optimize',lambda *a:calls.append(a))
    module.compact_after_write(None,'silver.learning_events','event_date',['2026-11-27'])
    assert calls==[(None,'silver.learning_events',"event_date IN (DATE '2026-11-27')")]


def test_bad_mode_fails_configuration(monkeypatch):
    monkeypatch.setenv('COMPACTION_MODE','typo')
    with pytest.raises(ValueError,match='COMPACTION_MODE'):settings.Settings()


def test_gold_maintenance_plan_and_date_validation(monkeypatch):
    module=load(monkeypatch,'maintain')
    assert module.statements('gold.failure_alerts')=='OPTIMIZE gold.failure_alerts'
    assert module.statements('silver.learning_events','2026-11-27').startswith("OPTIMIZE silver.learning_events WHERE event_date = DATE '2026-11-27' ZORDER")
    with pytest.raises(ValueError,match='--date'):module.statements('gold.failure_alerts','2026-11-27')
