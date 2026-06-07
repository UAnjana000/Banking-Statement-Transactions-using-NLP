"""Tests for merchant enrichment (all HTTP mocked)."""

from __future__ import annotations

import httpx

from finunderwrite.merchant.enrich import (
    LiveEnricher,
    NullEnricher,
    enrich_batch,
    get_enricher,
)
from finunderwrite.persistence import repository


def _mock_client(handler) -> httpx.Client:  # type: ignore[no-untyped-def]
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_null_enricher_noop() -> None:
    result = NullEnricher().enrich("Amazon")
    assert result.success is False
    assert result.source == "null"


def test_get_enricher_factory(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    isolated_settings.enricher = "null"
    assert isinstance(get_enricher(isolated_settings), NullEnricher)
    isolated_settings.enricher = "live"
    assert isinstance(get_enricher(isolated_settings), LiveEnricher)


def test_live_enricher_cache_hit(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    repository.upsert_cache(
        "Amazon",
        {"category": "Shopping", "website": "amazon.in"},
        source="live",
        success=True,
    )
    enricher = LiveEnricher(isolated_settings)
    result = enricher.enrich("Amazon")
    assert result.success is True
    assert result.category == "Shopping"
    assert result.website == "amazon.in"


def test_live_enricher_cache_miss_queues(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    enricher = LiveEnricher(isolated_settings)
    result = enricher.enrich("BrandNewMerchant")
    assert result.success is False
    assert result.source == "queued"
    assert "BrandNewMerchant" in repository.list_queue()


def test_enrichment_failure_degrades_gracefully(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    isolated_settings.enrichment_api_base = "https://enrich.test/api"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("robots.txt"):
            return httpx.Response(404)
        return httpx.Response(500)

    enricher = LiveEnricher(isolated_settings, client=_mock_client(handler))
    # Must not raise even though the endpoint errors.
    result = enricher.fetch_and_cache("FailingMerchant")
    assert result.success is False


def test_enrich_batch_populates_cache(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    isolated_settings.enrichment_api_base = "https://enrich.test/api"
    repository.enqueue("Zepto")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("robots.txt"):
            return httpx.Response(404)
        return httpx.Response(200, json={"category": "Groceries", "website": "zepto.in"})

    counts = enrich_batch(isolated_settings, client=_mock_client(handler))
    assert counts["processed"] == 1
    assert counts["succeeded"] == 1

    cached = repository.get_cached("Zepto")
    assert cached is not None
    assert cached["success"] is True
    assert cached["payload"]["category"] == "Groceries"
    # Queue drained after success.
    assert "Zepto" not in repository.list_queue()


def test_request_path_never_hits_network(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    isolated_settings.enrichment_api_base = "https://enrich.test/api"

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("request path must not perform network I/O")

    enricher = LiveEnricher(isolated_settings, client=_mock_client(handler))
    result = enricher.enrich("SomeMerchant")
    assert result.success is False
