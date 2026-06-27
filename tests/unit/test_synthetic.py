"""Tests for offline synthetic generation.

The generation smoke test auto-skips when the ML stack (sdv/torch) is absent,
so this suite runs green in the lightweight environment.
"""

from __future__ import annotations

import pytest
from tests.helpers.synthetic_txns import build_known_history

from finunderwrite.behaviour.summary import analyze_behaviour
from finunderwrite.features.vectorizer import build_feature_table
from finunderwrite.profile.builder import build_profile
from finunderwrite.synthetic import is_available

_ML_AVAILABLE = is_available()


def _feature_table(n_customers: int = 30):
    pairs = []
    for i in range(n_customers):
        txns = build_known_history(months=6)
        cid = f"cust-{i}"
        pairs.append((build_profile(cid, txns), analyze_behaviour(txns, cid)))
    return build_feature_table(pairs)


def test_import_guard_when_ml_absent() -> None:
    if _ML_AVAILABLE:
        pytest.skip("ML stack installed; guard not exercised")
    with pytest.raises(RuntimeError, match="OFFLINE-ONLY"):
        import finunderwrite.synthetic.generate  # noqa: F401


def test_is_available_returns_bool() -> None:
    assert isinstance(is_available(), bool)


@pytest.mark.skipif(not _ML_AVAILABLE, reason="sdv/torch not installed")
def test_generation_smoke_small_n(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from config import settings as settings_mod

    from finunderwrite.persistence import database

    s = settings_mod.Settings(
        database_url=f"sqlite:///{(tmp_path / 'synth.sqlite3').as_posix()}",
        data_processed=tmp_path,
    )
    monkeypatch.setattr(settings_mod, "_settings", s)
    database.reset_engine()

    from finunderwrite.synthetic.generate import learn_and_generate

    table = _feature_table(30)
    result = learn_and_generate(table, n=50, method="gaussian_copula", settings=s)

    assert result.path.exists()
    assert result.fidelity["overall_quality_score"] >= 0.0
    assert result.privacy["n_synthetic"] == 50
    database.reset_engine()
