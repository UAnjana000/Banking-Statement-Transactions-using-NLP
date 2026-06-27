"""OFFLINE synthetic customer generation.

This module is offline-only and MUST NOT be importable on the web dyno. It
raises ``RuntimeError`` at import time if the heavy ML stack (sdv / torch) is
absent, so it can never accidentally load in the serving runtime. Install the
optional stack with ``pip install -r requirements-ml.txt``.

Implements both a statistical synthesizer (GaussianCopula) and deep
synthesizers (CTGAN, TVAE), plus SDV fidelity/diagnostic reports and a
nearest-neighbor privacy check.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# --- import-time runtime guard: never load in the serving runtime -----------
_MISSING = [name for name in ("sdv", "torch") if importlib.util.find_spec(name) is None]
if _MISSING:  # pragma: no cover - exercised only when ML stack is absent
    msg = (
        "finunderwrite.synthetic.generate is OFFLINE-ONLY and requires the ML "
        f"stack (missing: {', '.join(_MISSING)}). Install requirements-ml.txt. "
        "This module must never be imported on the web dyno."
    )
    raise RuntimeError(msg)

import pandas as pd  # noqa: E402
from config.settings import Settings, get_settings  # noqa: E402
from loguru import logger  # noqa: E402
from sklearn.neighbors import NearestNeighbors  # noqa: E402

VALID_N = (100, 1000, 10000)
VALID_METHODS = ("gaussian_copula", "ctgan", "tvae")


@dataclass
class GenerationResult:
    method: str
    n: int
    path: Path
    fidelity: dict[str, Any] = field(default_factory=dict)
    privacy: dict[str, Any] = field(default_factory=dict)


def _build_metadata(real: pd.DataFrame) -> Any:
    from sdv.metadata import SingleTableMetadata

    metadata = SingleTableMetadata()
    metadata.detect_from_dataframe(real)
    return metadata


def _make_synthesizer(method: str, metadata: Any) -> Any:
    if method == "gaussian_copula":
        from sdv.single_table import GaussianCopulaSynthesizer

        return GaussianCopulaSynthesizer(metadata)
    if method == "ctgan":
        from sdv.single_table import CTGANSynthesizer

        return CTGANSynthesizer(metadata)
    if method == "tvae":
        from sdv.single_table import TVAESynthesizer

        return TVAESynthesizer(metadata)
    msg = f"Unknown method: {method}. Choose from {VALID_METHODS}."
    raise ValueError(msg)


def _fidelity_report(real: pd.DataFrame, synthetic: pd.DataFrame, metadata: Any) -> dict[str, Any]:
    from sdv.evaluation.single_table import (
        evaluate_quality,
        run_diagnostic,
    )

    quality = evaluate_quality(real, synthetic, metadata)
    diagnostic = run_diagnostic(real, synthetic, metadata)
    return {
        "overall_quality_score": float(quality.get_score()),
        "diagnostic_score": float(diagnostic.get_score()),
    }


def _privacy_check(
    real: pd.DataFrame,
    synthetic: pd.DataFrame,
    *,
    min_distance: float = 1e-6,
) -> dict[str, Any]:
    """Nearest-neighbor distance; assert no synthetic row duplicates a real row."""
    numeric_cols = [c for c in real.columns if pd.api.types.is_numeric_dtype(real[c])]
    real_num = real[numeric_cols].to_numpy(dtype=float)
    synth_num = synthetic[numeric_cols].to_numpy(dtype=float)

    ranges = real_num.max(axis=0) - real_num.min(axis=0)
    ranges[ranges == 0] = 1.0
    real_scaled = real_num / ranges
    synth_scaled = synth_num / ranges

    nn = NearestNeighbors(n_neighbors=1).fit(real_scaled)
    distances, _ = nn.kneighbors(synth_scaled)
    min_nn = float(distances.min())

    if min_nn <= min_distance:
        msg = (
            f"Privacy check failed: a synthetic row is a near-duplicate of a real "
            f"row (min NN distance {min_nn:.2e} <= {min_distance:.2e})."
        )
        raise AssertionError(msg)

    return {
        "min_nn_distance": min_nn,
        "mean_nn_distance": float(distances.mean()),
        "n_synthetic": int(len(synthetic)),
    }


def learn_and_generate(
    feature_table: pd.DataFrame,
    n: int,
    method: str = "gaussian_copula",
    settings: Settings | None = None,
) -> GenerationResult:
    """Fit *method* on *feature_table* and sample *n* synthetic rows."""
    if feature_table.empty:
        msg = "Cannot learn distributions from an empty feature table"
        raise ValueError(msg)
    if method not in VALID_METHODS:
        msg = f"Unknown method: {method}. Choose from {VALID_METHODS}."
        raise ValueError(msg)

    settings = settings or get_settings()

    # Drop identifier columns before modeling.
    real = feature_table.drop(columns=[c for c in ("customer_id",) if c in feature_table.columns])

    metadata = _build_metadata(real)
    synthesizer = _make_synthesizer(method, metadata)
    logger.info("Fitting {} on {} real rows", method, len(real))
    synthesizer.fit(real)
    synthetic = synthesizer.sample(num_rows=n)

    fidelity = _fidelity_report(real, synthetic, metadata)
    privacy = _privacy_check(real, synthetic)

    out_dir = settings.data_processed / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"synthetic_{method}_{n}.csv"
    synthetic.insert(0, "synthetic_id", [f"syn-{i:06d}" for i in range(len(synthetic))])
    synthetic.to_csv(out_path, index=False)

    result = GenerationResult(method=method, n=n, path=out_path, fidelity=fidelity, privacy=privacy)
    _write_report(out_dir, result)
    _register_dataset(settings, result)
    logger.info("Generated {} rows via {} -> {}", n, method, out_path)
    return result


def _write_report(out_dir: Path, result: GenerationResult) -> None:
    report_path = out_dir / f"report_{result.method}_{result.n}.json"
    report_path.write_text(
        json.dumps(
            {
                "method": result.method,
                "n": result.n,
                "path": str(result.path),
                "fidelity": result.fidelity,
                "privacy": result.privacy,
                "generated_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _register_dataset(settings: Settings, result: GenerationResult) -> None:
    """Register the dataset in the DB so the API can serve it."""
    try:
        from finunderwrite.persistence import repository
        from finunderwrite.persistence.database import init_db

        init_db(settings)
        repository.register_synthetic_dataset(
            name=f"{result.method}_{result.n}",
            n=result.n,
            method=result.method,
            path=str(result.path),
            metrics={"fidelity": result.fidelity, "privacy": result.privacy},
        )
    except Exception as exc:  # registration is best-effort
        logger.warning("Could not register synthetic dataset: {}", exc)


def benchmark(
    feature_table: pd.DataFrame,
    settings: Settings | None = None,
) -> list[GenerationResult]:
    """Run all methods at all N and return their results."""
    results: list[GenerationResult] = []
    for method in VALID_METHODS:
        for n in VALID_N:
            results.append(learn_and_generate(feature_table, n, method, settings))
    return results
