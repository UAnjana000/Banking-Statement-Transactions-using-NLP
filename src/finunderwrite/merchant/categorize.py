"""Hybrid transaction categorizer (rules -> scikit-learn -> optional LLM).

Tier 1: deterministic rules from config/category_map.yaml.
Tier 2: a char n-gram TF-IDF + LogisticRegression pipeline (scikit-learn),
        persisted with joblib. This is the "semantic" layer. No torch.
Tier 3: optional LLM fallback (default Groq, OpenAI-compatible), feature-flagged
        OFF via settings.llm_enrich_enabled, invoked only for low-confidence
        results and cached in the DB.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from config.settings import Settings, get_settings
from config.yaml_loader import load_yaml
from loguru import logger

CATEGORIES = (
    "Food",
    "Groceries",
    "Fuel",
    "Healthcare",
    "Travel",
    "Entertainment",
    "Utilities",
    "Investments",
    "Salary",
    "Rent",
    "Education",
    "Insurance",
    "Shopping",
    "Transfers",
    "ATM",
    "Loan",
    "EMI",
    "Government",
    "Tax",
    "Subscription",
    "Telecom",
    "Others",
)

_DEFAULT_CATEGORY = "Others"


@dataclass
class CategoryRules:
    """Tier 1 lookup tables built from category_map.yaml."""

    keyword_to_category: list[tuple[str, str]]
    mcc_to_category: dict[str, str]
    merchant_overrides: dict[str, str]

    @classmethod
    def load(cls, path: Path) -> CategoryRules:
        raw = load_yaml(path)
        keyword_to_category: list[tuple[str, str]] = []
        mcc_to_category: dict[str, str] = {}
        for entry in raw.get("categories", []):
            category = str(entry["category"])
            for kw in entry.get("keywords", []) or []:
                keyword_to_category.append((str(kw).lower(), category))
            for mcc in entry.get("mcc", []) or []:
                mcc_to_category[str(mcc)] = category
        # Longer keywords first so specific matches win over generic ones.
        keyword_to_category.sort(key=lambda kv: len(kv[0]), reverse=True)
        merchant_overrides = {
            str(k): str(v) for k, v in (raw.get("merchant_overrides") or {}).items()
        }
        return cls(keyword_to_category, mcc_to_category, merchant_overrides)

    def training_samples(self) -> tuple[list[str], list[str]]:
        """Return (texts, labels) seed data for the Tier 2 classifier."""
        texts: list[str] = []
        labels: list[str] = []
        for keyword, category in self.keyword_to_category:
            texts.append(keyword)
            labels.append(category)
        for merchant, category in self.merchant_overrides.items():
            texts.append(merchant.lower())
            labels.append(category)
        return texts, labels


class Tier2Model:
    """Lazy-loading wrapper around the persisted scikit-learn pipeline."""

    def __init__(self, settings: Settings, rules: CategoryRules) -> None:
        self._settings = settings
        self._rules = rules
        self._pipeline: Any = None
        self._loaded = False

    def _build_and_train(self) -> Any:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline

        texts, labels = self._rules.training_samples()
        texts = texts + _FIXTURE_TRAINING_TEXTS
        labels = labels + _FIXTURE_TRAINING_LABELS

        pipeline = Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1),
                ),
                ("clf", LogisticRegression(max_iter=1000)),
            ]
        )
        pipeline.fit(texts, labels)
        return pipeline

    def train_and_persist(self) -> Path:
        """Train the pipeline and persist it to the configured path."""
        import joblib

        pipeline = self._build_and_train()
        path = self._settings.categorizer_model_path
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipeline, path)
        self._pipeline = pipeline
        self._loaded = True
        logger.info("Persisted Tier 2 categorizer model to {}", path)
        return path

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        import joblib

        path = self._settings.categorizer_model_path
        if path.exists():
            try:
                self._pipeline = joblib.load(path)
                self._loaded = True
                return
            except Exception as exc:  # corrupt/incompatible model -> retrain
                logger.warning("Failed to load model at {}: {}; retraining", path, exc)
        self.train_and_persist()

    def predict(self, text: str) -> tuple[str, float]:
        self._ensure_loaded()
        assert self._pipeline is not None
        proba = self._pipeline.predict_proba([text])[0]
        classes = self._pipeline.classes_
        best_idx = int(proba.argmax())
        return str(classes[best_idx]), float(proba[best_idx])


# Small fixtures seed so the classifier has richer training text than bare keywords.
_FIXTURE_TRAINING_TEXTS = [
    "swiggy order food delivery",
    "zomato dinner",
    "amazon shopping order",
    "flipkart purchase",
    "netflix monthly subscription",
    "spotify premium",
    "uber ride trip",
    "irctc train ticket",
    "hpcl petrol pump fuel",
    "bigbasket grocery order",
    "zepto instant grocery",
    "salary credit from employer",
    "monthly house rent payment",
    "lic insurance premium",
    "atm cash withdrawal",
    "jio mobile recharge",
    "airtel broadband bill",
    "electricity utility bill",
    "zerodha stock investment",
    "income tax payment",
]
_FIXTURE_TRAINING_LABELS = [
    "Food",
    "Food",
    "Shopping",
    "Shopping",
    "Entertainment",
    "Entertainment",
    "Travel",
    "Travel",
    "Fuel",
    "Groceries",
    "Groceries",
    "Salary",
    "Rent",
    "Insurance",
    "ATM",
    "Telecom",
    "Telecom",
    "Utilities",
    "Investments",
    "Tax",
]


class Categorizer:
    """Tiered categorizer returning (category, confidence)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._rules = CategoryRules.load(self._settings.category_map_path)
        self._tier2 = Tier2Model(self._settings, self._rules)

    def train(self) -> Path:
        """Force (re)training and persistence of the Tier 2 model."""
        return self._tier2.train_and_persist()

    def categorize(
        self,
        merchant: str | None,
        description: str,
        mcc: str | None = None,
    ) -> tuple[str, float]:
        """Return (category, category_confidence)."""
        tier1 = self._tier1(merchant, description, mcc)
        if tier1 is not None:
            category, confidence = tier1
            if confidence >= self._settings.category_confidence_threshold:
                return category, confidence
            best = tier1
        else:
            best = None

        tier2 = self._tier2_safe(merchant, description)
        if tier2 is not None and (best is None or tier2[1] > best[1]):
            best = tier2

        if best is not None and best[1] >= self._settings.llm_confidence_threshold:
            return best

        tier3 = self._tier3(merchant, description)
        if tier3 is not None and (best is None or tier3[1] > best[1]):
            best = tier3

        return best if best is not None else (_DEFAULT_CATEGORY, 0.1)

    def _tier1(
        self, merchant: str | None, description: str, mcc: str | None
    ) -> tuple[str, float] | None:
        if merchant and merchant in self._rules.merchant_overrides:
            return self._rules.merchant_overrides[merchant], 0.95
        if mcc and mcc in self._rules.mcc_to_category:
            return self._rules.mcc_to_category[mcc], 0.85
        haystack = f"{merchant or ''} {description or ''}".lower()
        for keyword, category in self._rules.keyword_to_category:
            if keyword in haystack:
                return category, 0.8
        return None

    def _tier2_safe(self, merchant: str | None, description: str) -> tuple[str, float] | None:
        text = f"{merchant or ''} {description or ''}".strip()
        if not text:
            return None
        try:
            return self._tier2.predict(text)
        except Exception as exc:
            logger.warning("Tier 2 categorization failed: {}", exc)
            return None

    def _tier3(self, merchant: str | None, description: str) -> tuple[str, float] | None:
        if not self._settings.llm_enrich_enabled:
            return None
        text = f"{merchant or ''} {description or ''}".strip()
        key = _cache_key(text)

        from finunderwrite.persistence import repository

        try:
            cached = repository.get_llm_category(key)
        except Exception as exc:
            logger.warning("LLM cache read failed: {}", exc)
            cached = None
        if cached is not None:
            return cached

        result = _llm_classify(text, self._settings)
        if result is None:
            return None
        try:
            repository.put_llm_category(key, result[0], result[1], merchant=merchant)
        except Exception as exc:
            logger.warning("LLM cache write failed: {}", exc)
        return result


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.lower().encode("utf-8")).hexdigest()


def _llm_classify(text: str, settings: Settings) -> tuple[str, float] | None:
    """Call an OpenAI-compatible LLM (default Groq) to classify *text*."""
    import httpx

    if not settings.llm_api_key:
        logger.warning("LLM enrichment enabled but no API key configured")
        return None

    prompt = (
        "Classify the bank transaction into exactly one of these categories: "
        + ", ".join(CATEGORIES)
        + ". Respond with a compact JSON object "
        + '{"category": <one category>, "confidence": <0..1 float>}.\n'
        + f"Transaction: {text}"
    )
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    url = f"{settings.llm_api_base.rstrip('/')}/chat/completions"

    try:
        with httpx.Client(timeout=settings.enrichment_timeout_seconds) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        category = str(parsed["category"])
        confidence = float(parsed.get("confidence", 0.7))
        if category not in CATEGORIES:
            category = _DEFAULT_CATEGORY
        return category, confidence
    except Exception as exc:
        logger.warning("LLM classification failed: {}", exc)
        return None


@lru_cache(maxsize=1)
def _default_categorizer() -> Categorizer:
    return Categorizer()


def categorize(
    merchant: str | None,
    description: str,
    mcc: str | None = None,
) -> tuple[str, float]:
    """Module-level convenience using a cached default categorizer."""
    return _default_categorizer().categorize(merchant, description, mcc)
