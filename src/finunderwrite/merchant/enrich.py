"""Merchant enrichment.

Two implementations, swappable via ``settings.enricher``:

- ``NullEnricher``: no-op, always returns an unsuccessful result.
- ``LiveEnricher``: defensive live enrichment.

The request path (``enrich``) reads the DB cache ONLY. On a cache miss it queues
the merchant for the offline batch enricher and returns an unsuccessful result,
so categorization/enrichment NEVER blocks or fails on the request path. The only
place that performs bulk network I/O is ``enrich_batch`` (the ``enrich-batch``
CLI command), which respects robots.txt and a configurable rate limit and uses
tenacity retries with exponential backoff.
"""

from __future__ import annotations

import time
import urllib.parse
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from urllib.robotparser import RobotFileParser

import httpx
from config.settings import Settings, get_settings
from loguru import logger
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from finunderwrite.persistence import repository
from finunderwrite.persistence.database import init_db


class EnrichmentResult(BaseModel):
    """Result of enriching a merchant."""

    merchant: str
    category: str | None = None
    website: str | None = None
    source: str = "none"
    success: bool = False
    fetched_at: datetime | None = None


class Enricher(ABC):
    """Merchant enricher interface."""

    @abstractmethod
    def enrich(self, merchant: str) -> EnrichmentResult:
        """Enrich *merchant* on the request path (must never raise)."""


class NullEnricher(Enricher):
    """No-op enricher."""

    def enrich(self, merchant: str) -> EnrichmentResult:
        return EnrichmentResult(merchant=merchant, source="null", success=False)


class _RateLimiter:
    """Simple minimum-interval rate limiter."""

    def __init__(self, per_second: float) -> None:
        self._min_interval = 1.0 / per_second if per_second > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last = time.monotonic()


class LiveEnricher(Enricher):
    """Cache-first enricher with an offline batch network path."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self._rate_limiter = _RateLimiter(self._settings.enrichment_rate_limit_per_sec)
        self._robots_cache: dict[str, RobotFileParser | None] = {}

    # --- request path (cache-read only) -------------------------------------

    def enrich(self, merchant: str) -> EnrichmentResult:
        """Return cached enrichment; on miss, queue and return no-op."""
        try:
            cached = repository.get_cached(merchant)
        except Exception as exc:
            logger.warning("Enrichment cache read failed for {}: {}", merchant, exc)
            return EnrichmentResult(merchant=merchant, source="error", success=False)

        if cached is not None and cached.get("success"):
            payload = cached.get("payload", {})
            return EnrichmentResult(
                merchant=merchant,
                category=payload.get("category"),
                website=payload.get("website"),
                source=cached.get("source", "cache"),
                success=True,
                fetched_at=cached.get("fetched_at"),
            )

        # Cache miss: queue for offline batch, degrade gracefully.
        try:
            repository.enqueue(merchant)
        except Exception as exc:
            logger.warning("Failed to enqueue {} for enrichment: {}", merchant, exc)
        return EnrichmentResult(merchant=merchant, source="queued", success=False)

    # --- offline batch path (the only bulk-network path) --------------------

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self._settings.enrichment_timeout_seconds,
                headers={"User-Agent": self._settings.enrichment_user_agent},
            )
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _robots_allows(self, url: str) -> bool:
        if not self._settings.respect_robots:
            return True
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        parser = self._robots_cache.get(origin)
        if parser is None and origin not in self._robots_cache:
            parser = RobotFileParser()
            robots_url = f"{origin}/robots.txt"
            try:
                resp = self._get_client().get(robots_url)
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                else:
                    parser = None  # no robots -> allow
            except Exception as exc:
                logger.debug("robots.txt fetch failed for {}: {}", origin, exc)
                parser = None
            self._robots_cache[origin] = parser
        if parser is None:
            return True
        return parser.can_fetch(self._settings.enrichment_user_agent, url)

    def _fetch(self, merchant: str) -> EnrichmentResult:
        base = self._settings.enrichment_api_base
        if not base:
            logger.debug("No enrichment_api_base configured; skipping fetch")
            return EnrichmentResult(merchant=merchant, source="unconfigured", success=False)

        url = f"{base.rstrip('/')}/{urllib.parse.quote(merchant)}"
        if not self._robots_allows(url):
            logger.info("robots.txt disallows enrichment fetch for {}", merchant)
            return EnrichmentResult(merchant=merchant, source="robots_blocked", success=False)

        self._rate_limiter.wait()

        @retry(
            stop=stop_after_attempt(self._settings.enrichment_max_attempts),
            wait=wait_exponential(multiplier=0.2, max=2.0),
            reraise=True,
        )
        def _do_request() -> httpx.Response:
            resp = self._get_client().get(url)
            resp.raise_for_status()
            return resp

        resp = _do_request()
        data = resp.json()
        return EnrichmentResult(
            merchant=merchant,
            category=data.get("category"),
            website=data.get("website"),
            source="live",
            success=True,
            fetched_at=datetime.now(UTC),
        )

    def fetch_and_cache(self, merchant: str) -> EnrichmentResult:
        """Fetch enrichment for *merchant* over the network and cache it."""
        try:
            result = self._fetch(merchant)
        except Exception as exc:
            logger.warning("Enrichment fetch failed for {}: {}", merchant, exc)
            try:
                repository.record_queue_error(merchant, str(exc))
            except Exception:  # noqa: BLE001 - never let bookkeeping crash the batch
                logger.debug("Failed to record queue error for {}", merchant)
            return EnrichmentResult(merchant=merchant, source="error", success=False)

        try:
            repository.upsert_cache(
                merchant,
                {"category": result.category, "website": result.website},
                source=result.source,
                success=result.success,
            )
            if result.success:
                repository.resolve_queue(merchant)
        except Exception as exc:
            logger.warning("Failed to cache enrichment for {}: {}", merchant, exc)
        return result


def get_enricher(
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> Enricher:
    """Return the configured enricher (null|live)."""
    settings = settings or get_settings()
    if settings.enricher.lower() == "live":
        return LiveEnricher(settings, client=client)
    return NullEnricher()


def enrich_batch(
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    """Offline: drain the enrichment queue and populate the cache.

    Returns counts of processed/succeeded/failed merchants.
    """
    settings = settings or get_settings()
    init_db(settings)
    enricher = LiveEnricher(settings, client=client)

    try:
        queued = repository.list_queue()
    except Exception as exc:
        logger.error("Failed to read enrichment queue: {}", exc)
        return {"processed": 0, "succeeded": 0, "failed": 0}

    succeeded = 0
    failed = 0
    for merchant in queued:
        result = enricher.fetch_and_cache(merchant)
        if result.success:
            succeeded += 1
        else:
            failed += 1

    if enricher._owns_client:
        enricher.close()

    counts = {"processed": len(queued), "succeeded": succeeded, "failed": failed}
    logger.info("enrich_batch complete: {}", counts)
    return counts
