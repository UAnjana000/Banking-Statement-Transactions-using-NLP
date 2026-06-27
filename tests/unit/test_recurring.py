"""Tests for recurring-transaction detection."""

from __future__ import annotations

from tests.helpers.synthetic_txns import build_known_history

from finunderwrite.behaviour.recurring import detect_recurring


def test_detects_known_recurring_groups() -> None:
    txns = build_known_history(months=6)
    items = detect_recurring(txns)

    by_category: dict[str, list] = {}
    for it in items:
        by_category.setdefault(it.category, []).append(it)

    assert "Salary" in by_category
    assert "Rent" in by_category
    assert "Subscription" in by_category

    salary = by_category["Salary"][0]
    assert salary.direction == "credit"
    assert salary.cadence == "monthly"
    assert salary.occurrences >= 5
    assert abs(salary.median_amount - 60000) < 1

    # Two distinct subscriptions (Netflix + Spotify).
    sub_merchants = {it.merchant for it in by_category["Subscription"]}
    assert "netflix" in sub_merchants
    assert "spotify" in sub_merchants


def test_rent_with_drift_still_groups() -> None:
    txns = build_known_history(months=6)
    items = detect_recurring(txns)
    rent = next(it for it in items if it.category == "Rent")
    assert rent.cadence == "monthly"
    assert rent.occurrences >= 5  # small monthly drift still clusters


def test_confidence_bounded() -> None:
    txns = build_known_history(months=6)
    items = detect_recurring(txns)
    assert items
    for it in items:
        assert 0.0 <= it.confidence <= 1.0


def test_insufficient_history_returns_empty() -> None:
    txns = build_known_history(months=1)
    items = detect_recurring(txns)
    # One occurrence each -> below the minimum-occurrence threshold.
    assert items == []
