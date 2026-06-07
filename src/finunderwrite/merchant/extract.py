"""Merchant + payment_mode extraction from transaction descriptions.

Patterns are driven entirely by config/merchant_rules.yaml. The extractor is
defensive: any failure yields ``merchant=None`` with zero confidence rather
than raising.
"""

from __future__ import annotations

import re
from functools import lru_cache

from config.settings import Settings, get_settings
from config.yaml_loader import load_yaml
from loguru import logger
from pydantic import BaseModel
from rapidfuzz import fuzz, process

from finunderwrite.contracts.transaction import CanonicalTransaction

_SPLIT_RE = re.compile(r"[\\/*|:;,>_@#\-]+")
_MULTISPACE_RE = re.compile(r"\s+")


class MerchantExtraction(BaseModel):
    """Result of extracting a merchant from a description."""

    merchant: str | None = None
    payment_mode: str | None = None
    confidence: float = 0.0
    cleaned: str = ""


class MerchantExtractor:
    """Rules-driven merchant extractor with fuzzy canonicalization."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        rules = load_yaml(self._settings.merchant_rules_path)

        self._payment_modes: list[tuple[str, re.Pattern[str]]] = [
            (str(item["mode"]), re.compile(str(item["regex"])))
            for item in rules.get("payment_modes", [])
        ]
        self._strip_patterns: list[re.Pattern[str]] = [
            re.compile(str(p)) for p in rules.get("strip_tokens", [])
        ]
        self._upi_handle_patterns: list[re.Pattern[str]] = [
            re.compile(str(p)) for p in rules.get("upi_handle_regex", [])
        ]
        self._routing_tokens: set[str] = {str(t).upper() for t in rules.get("routing_tokens", [])}
        self._canonical: list[str] = [str(m) for m in rules.get("canonical_merchants", [])]
        self._canonical_upper = {m.upper(): m for m in self._canonical}
        self._aliases: dict[str, str] = {
            str(k).upper(): str(v) for k, v in (rules.get("aliases") or {}).items()
        }
        self._threshold = self._settings.merchant_fuzzy_threshold

    def detect_payment_mode(self, description: str) -> str | None:
        for mode, pattern in self._payment_modes:
            if pattern.search(description):
                return mode
        return None

    def extract(self, description: str) -> MerchantExtraction:
        """Extract merchant + payment_mode; never raises."""
        try:
            return self._extract(description)
        except Exception as exc:  # defensive: extraction must never crash
            logger.warning("Merchant extraction failed for {!r}: {}", description, exc)
            return MerchantExtraction()

    def _extract(self, description: str) -> MerchantExtraction:
        if not description or not description.strip():
            return MerchantExtraction()

        payment_mode = self.detect_payment_mode(description)
        candidate = self._clean(description)

        if not candidate:
            return MerchantExtraction(payment_mode=payment_mode, cleaned="")

        merchant, confidence = self._canonicalize(candidate)
        return MerchantExtraction(
            merchant=merchant,
            payment_mode=payment_mode,
            confidence=confidence,
            cleaned=candidate,
        )

    def _clean(self, description: str) -> str:
        text = description.strip()

        # Keep the local-part of any UPI VPA handle, drop the "@handle" suffix.
        for pattern in self._upi_handle_patterns:
            text = pattern.sub(" ", text)

        for pattern in self._strip_patterns:
            text = pattern.sub(" ", text)

        tokens = [t for t in _SPLIT_RE.split(text) if t]
        kept: list[str] = []
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            upper = token.upper()
            if upper in self._routing_tokens:
                continue
            if token.isdigit():
                continue
            if len(token) <= 1:
                continue
            kept.append(token)

        return _MULTISPACE_RE.sub(" ", " ".join(kept)).strip()

    def _canonicalize(self, candidate: str) -> tuple[str | None, float]:
        upper = candidate.upper()

        if upper in self._aliases:
            return self._aliases[upper], 0.95
        if upper in self._canonical_upper:
            return self._canonical_upper[upper], 0.95

        # Alias match on any word within the candidate.
        for word in upper.split():
            if word in self._aliases:
                return self._aliases[word], 0.9
            if word in self._canonical_upper:
                return self._canonical_upper[word], 0.9

        if self._canonical:
            match = process.extractOne(
                candidate,
                self._canonical,
                scorer=fuzz.token_set_ratio,
            )
            if match is not None:
                name, score, _ = match
                if score >= self._threshold:
                    return name, round(score / 100.0, 3)

        # Fallback: title-case the cleaned candidate with low confidence.
        return candidate.title(), 0.4

    def apply_to_transaction(self, transaction: CanonicalTransaction) -> CanonicalTransaction:
        """Return a copy of *transaction* with merchant/payment_mode filled in."""
        result = self.extract(transaction.description)
        update: dict[str, object] = {}
        if result.merchant is not None:
            update["merchant"] = result.merchant
        if transaction.payment_mode is None and result.payment_mode is not None:
            update["payment_mode"] = result.payment_mode
        if not update:
            return transaction
        return transaction.model_copy(update=update)


@lru_cache(maxsize=1)
def _default_extractor() -> MerchantExtractor:
    return MerchantExtractor()


def extract_merchant(description: str) -> MerchantExtraction:
    """Module-level convenience using a cached default extractor."""
    return _default_extractor().extract(description)


def apply_to_transaction(transaction: CanonicalTransaction) -> CanonicalTransaction:
    """Module-level convenience using a cached default extractor."""
    return _default_extractor().apply_to_transaction(transaction)
