"""Merchant extraction, categorization, and enrichment."""

from finunderwrite.merchant.categorize import Categorizer, categorize
from finunderwrite.merchant.enrich import (
    Enricher,
    EnrichmentResult,
    LiveEnricher,
    NullEnricher,
    enrich_batch,
    get_enricher,
)
from finunderwrite.merchant.extract import (
    MerchantExtraction,
    MerchantExtractor,
    apply_to_transaction,
    extract_merchant,
)

__all__ = [
    "Categorizer",
    "Enricher",
    "EnrichmentResult",
    "LiveEnricher",
    "MerchantExtraction",
    "MerchantExtractor",
    "NullEnricher",
    "apply_to_transaction",
    "categorize",
    "enrich_batch",
    "extract_merchant",
    "get_enricher",
]
