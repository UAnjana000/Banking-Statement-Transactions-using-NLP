"""Tests for the feature vectorizer."""

from __future__ import annotations

from tests.helpers.synthetic_txns import build_known_history

from finunderwrite.behaviour.summary import analyze_behaviour
from finunderwrite.features.vectorizer import (
    FEATURE_COLUMNS,
    build_feature_row,
    build_feature_table,
)
from finunderwrite.profile.builder import build_profile


def test_feature_row_has_full_schema() -> None:
    txns = build_known_history(months=6)
    profile = build_profile("cust-1", txns)
    summary = analyze_behaviour(txns, "cust-1")
    row = build_feature_row(profile, summary)

    assert set(row.keys()) == set(FEATURE_COLUMNS)
    assert row["customer_id"] == "cust-1"
    assert abs(row["avg_income"] - 60000) < 1
    assert 0.0 <= row["savings_rate"] <= 1.0
    assert row["subscription_count"] >= 2
    assert row["upi_frequency"] >= 0.0


def test_feature_table_one_row_per_customer() -> None:
    pairs = []
    for cid in ("a", "b", "c"):
        txns = build_known_history(months=4)
        pairs.append((build_profile(cid, txns), analyze_behaviour(txns, cid)))

    table = build_feature_table(pairs)
    assert list(table.columns) == list(FEATURE_COLUMNS)
    assert len(table) == 3
    assert set(table["customer_id"]) == {"a", "b", "c"}


def test_empty_feature_table() -> None:
    table = build_feature_table([])
    assert list(table.columns) == list(FEATURE_COLUMNS)
    assert len(table) == 0


def test_deterministic_output() -> None:
    txns = build_known_history(months=5)
    profile = build_profile("cust-x", txns)
    summary = analyze_behaviour(txns, "cust-x")
    row1 = build_feature_row(profile, summary)
    row2 = build_feature_row(profile, summary)
    assert row1 == row2


def test_online_spend_ratio_bounds() -> None:
    txns = build_known_history(months=3)
    profile = build_profile("cust-y", txns)
    summary = analyze_behaviour(txns, "cust-y")
    row = build_feature_row(profile, summary)
    assert 0.0 <= row["online_spend_ratio"] <= 1.0
    assert row["avg_monthly_spend"] > 0
    assert isinstance(row["avg_income"], float)


def test_handles_missing_income() -> None:
    txns = [t for t in build_known_history(months=2) if t.category != "Salary"]
    profile = build_profile("cust-z", txns)
    summary = analyze_behaviour(txns, "cust-z")
    row = build_feature_row(profile, summary)
    assert row["avg_income"] == 0.0
    assert row["income_consistency"] == 0.0
