"""Application settings loaded from environment variables."""

from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_LOG_LEVELS = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
_VALID_ENRICHERS = {"null", "live"}


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FINUNDERWRITE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"
    data_raw: Path = Field(default_factory=lambda: _project_root() / "data" / "raw")
    data_interim: Path = Field(default_factory=lambda: _project_root() / "data" / "interim")
    data_processed: Path = Field(default_factory=lambda: _project_root() / "data" / "processed")
    config_dir: Path = Field(default_factory=lambda: _project_root() / "config")
    tesseract_cmd: str | None = None
    poppler_path: str | None = None
    fuzzy_match_threshold: int = 85

    # Persistence
    database_url: str | None = None

    # API / web — 50 MB covers multi-page bank statement PDFs (~30 MB common)
    max_upload_bytes: int = 50 * 1024 * 1024
    api_default_customer_id: str = "default"

    # Merchant extraction
    merchant_fuzzy_threshold: int = 88

    # Categorization
    categorizer_model_path: Path = Field(
        default_factory=lambda: _project_root() / "models" / "merchant_categorizer.joblib"
    )
    category_confidence_threshold: float = 0.5

    # Tier 3 LLM enrichment (OFF by default)
    llm_enrich_enabled: bool = False
    llm_api_base: str = "https://api.groq.com/openai/v1"
    llm_model: str = "llama-3.1-8b-instant"
    llm_api_key: str | None = None
    llm_confidence_threshold: float = 0.5

    # Live enrichment
    enricher: str = "null"
    enrichment_api_base: str | None = None
    enrichment_timeout_seconds: float = 3.0
    enrichment_rate_limit_per_sec: float = 1.0
    enrichment_max_attempts: int = 3
    enrichment_user_agent: str = "finunderwrite/0.1 (+https://example.invalid)"
    respect_robots: bool = True

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        upper = value.upper()
        if upper not in _VALID_LOG_LEVELS:
            msg = f"Invalid log_level {value!r}; choose from {sorted(_VALID_LOG_LEVELS)}"
            raise ValueError(msg)
        return upper

    @field_validator("enricher")
    @classmethod
    def _validate_enricher(cls, value: str) -> str:
        lower = value.lower()
        if lower not in _VALID_ENRICHERS:
            msg = f"Invalid enricher {value!r}; choose from {sorted(_VALID_ENRICHERS)}"
            raise ValueError(msg)
        return lower

    @field_validator("max_upload_bytes")
    @classmethod
    def _validate_upload_limit(cls, value: int) -> int:
        if value <= 0:
            msg = "max_upload_bytes must be positive"
            raise ValueError(msg)
        return value

    @property
    def max_upload_mb(self) -> float:
        """Upload cap in megabytes (for user-facing messages)."""
        return round(self.max_upload_bytes / (1024 * 1024), 1)

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = _project_root() / "local.db"
        return f"sqlite:///{db_path.as_posix()}"

    @property
    def column_synonyms_path(self) -> Path:
        return self.config_dir / "column_synonyms.yaml"

    @property
    def merchant_rules_path(self) -> Path:
        return self.config_dir / "merchant_rules.yaml"

    @property
    def category_map_path(self) -> Path:
        return self.config_dir / "category_map.yaml"


_settings: Settings | None = None


def _emit_debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "508052",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with Path("debug-508052.log").open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass
    # endregion


def get_settings() -> Settings:
    global _settings
    _emit_debug_log(
        run_id="pre-fix",
        hypothesis_id="H2",
        location="config/settings.py:get_settings",
        message="Settings requested",
        data={"cache_hit": _settings is not None},
    )
    if _settings is None:
        _settings = Settings()
        _emit_debug_log(
            run_id="pre-fix",
            hypothesis_id="H2",
            location="config/settings.py:get_settings",
            message="Settings initialized",
            data={"log_level": _settings.log_level},
        )
    return _settings
