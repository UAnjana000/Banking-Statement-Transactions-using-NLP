"""Tests for the tiered merchant categorizer."""

from __future__ import annotations

import importlib

import pytest

from finunderwrite.merchant.categorize import CATEGORIES, Categorizer

categorize_mod = importlib.import_module("finunderwrite.merchant.categorize")


def test_tier1_merchant_override(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    cat = Categorizer(settings=isolated_settings)
    category, confidence = cat.categorize("Amazon", "amazon order 123")
    assert category == "Shopping"
    assert confidence >= 0.9


def test_tier1_keyword_match(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    cat = Categorizer(settings=isolated_settings)
    category, confidence = cat.categorize(None, "HPCL petrol pump fuel")
    assert category == "Fuel"
    assert confidence >= 0.5


def test_tier1_mcc_match(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    cat = Categorizer(settings=isolated_settings)
    category, confidence = cat.categorize(None, "unknown narration", mcc="5411")
    assert category == "Groceries"
    assert confidence >= 0.8


def test_tier2_classifier_prediction(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    cat = Categorizer(settings=isolated_settings)
    path = cat.train()
    assert path.exists()
    # Something with no direct Tier 1 keyword still yields a valid category.
    category, confidence = cat.categorize(None, "zzqw random unseen text")
    assert category in CATEGORIES
    assert 0.0 <= confidence <= 1.0


def test_tier3_disabled_by_default(isolated_settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    isolated_settings.llm_enrich_enabled = False

    def _boom(text: str, settings) -> None:  # type: ignore[no-untyped-def]
        raise AssertionError("LLM must not be called when flag is off")

    monkeypatch.setattr(categorize_mod, "_llm_classify", _boom)
    cat = Categorizer(settings=isolated_settings)
    category, _ = cat.categorize("Amazon", "amazon order")
    assert category == "Shopping"


def test_tier3_invoked_and_cached(isolated_settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Force escalation past tiers 1 and 2.
    isolated_settings.llm_enrich_enabled = True
    isolated_settings.category_confidence_threshold = 1.0
    isolated_settings.llm_confidence_threshold = 1.0

    calls = {"n": 0}

    def _fake_llm(text: str, settings):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return "Food", 0.99

    monkeypatch.setattr(categorize_mod, "_llm_classify", _fake_llm)

    cat = Categorizer(settings=isolated_settings)
    category, confidence = cat.categorize("Amazon", "amazon order")
    assert category == "Food"
    assert confidence == pytest.approx(0.99)
    assert calls["n"] == 1

    # Second identical call is served from the DB cache (no new LLM call).
    category2, _ = cat.categorize("Amazon", "amazon order")
    assert category2 == "Food"
    assert calls["n"] == 1


def test_default_category_fallback(isolated_settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    cat = Categorizer(settings=isolated_settings)
    # Make Tier 2 unavailable to exercise the final fallback path.
    monkeypatch.setattr(cat, "_tier2_safe", lambda *a, **k: None)
    category, confidence = cat.categorize(None, "")
    assert category == "Others"
    assert confidence <= 0.5
