"""Tests for merchant extraction."""

from __future__ import annotations

from datetime import datetime

import pytest

from finunderwrite.contracts.transaction import CanonicalTransaction
from finunderwrite.merchant.extract import MerchantExtractor


@pytest.fixture(scope="module")
def extractor() -> MerchantExtractor:
    return MerchantExtractor()


def test_messy_upi_extraction(extractor: MerchantExtractor) -> None:
    result = extractor.extract("UPI/DR/501763002832/ZEPTO/HDFC")
    assert result.merchant == "Zepto"
    assert result.payment_mode == "UPI"
    assert result.confidence >= 0.9


def test_netflix_india(extractor: MerchantExtractor) -> None:
    result = extractor.extract("NETFLIX INDIA")
    assert result.merchant == "Netflix"


def test_swiggy_star_order(extractor: MerchantExtractor) -> None:
    result = extractor.extract("SWIGGY*ORDER")
    assert result.merchant == "Swiggy"


def test_pos_payment_mode(extractor: MerchantExtractor) -> None:
    result = extractor.extract("POS/ZOMATO/12345678")
    assert result.payment_mode == "POS"
    assert result.merchant == "Zomato"


@pytest.mark.parametrize(
    "raw",
    ["AMZN", "AMAZON PAY", "AMAZON", "AMAZON IN"],
)
def test_fuzzy_variant_collapse_amazon(extractor: MerchantExtractor, raw: str) -> None:
    result = extractor.extract(raw)
    assert result.merchant == "Amazon"


def test_unparseable_returns_none(extractor: MerchantExtractor) -> None:
    assert extractor.extract("").merchant is None
    assert extractor.extract("   ").merchant is None
    # digits-only content is stripped, leaving nothing to match.
    numeric = extractor.extract("999999 500000123")
    assert numeric.merchant is None
    assert numeric.confidence == 0.0


def test_never_raises_on_weird_input(extractor: MerchantExtractor) -> None:
    for weird in ["///", "@@@", "\n\t", "UPI//", "12/34/56"]:
        result = extractor.extract(weird)
        assert isinstance(result.confidence, float)


def test_apply_to_transaction_sets_merchant(extractor: MerchantExtractor) -> None:
    txn = CanonicalTransaction(
        transaction_id="t1",
        date=datetime(2025, 1, 1),
        description="UPI/DR/501763002832/ZEPTO/HDFC",
    )
    updated = extractor.apply_to_transaction(txn)
    assert updated.merchant == "Zepto"
    assert updated.payment_mode == "UPI"
    # Original stays unchanged (frozen contract, immutable copy).
    assert txn.merchant is None


def test_apply_preserves_existing_payment_mode(extractor: MerchantExtractor) -> None:
    txn = CanonicalTransaction(
        transaction_id="t2",
        date=datetime(2025, 1, 1),
        description="NETFLIX INDIA",
        payment_mode="NEFT",
    )
    updated = extractor.apply_to_transaction(txn)
    assert updated.merchant == "Netflix"
    assert updated.payment_mode == "NEFT"
