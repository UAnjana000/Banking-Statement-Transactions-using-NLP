"""Serve PRE-GENERATED synthetic datasets only (no generation at request time)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from finunderwrite.api.schemas import SyntheticResponse
from finunderwrite.persistence import repository

router = APIRouter(tags=["synthetic"])

_ALLOWED_N = {100, 1000, 10000}


@router.get("/synthetic", response_model=SyntheticResponse)
def get_synthetic(
    n: int = Query(100),
    limit: int = Query(100, ge=1, le=10000),
) -> SyntheticResponse:
    if n not in _ALLOWED_N:
        raise HTTPException(status_code=400, detail="n must be one of 100, 1000, 10000")

    dataset = repository.get_synthetic_dataset(n)
    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No pre-generated dataset for n={n}. Generate offline with "
                "'finunderwrite synth-generate'."
            ),
        )

    path = Path(dataset["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Registered dataset file is missing")

    df = pd.read_csv(path).head(limit)
    rows = df.to_dict(orient="records")
    return SyntheticResponse(
        n=n,
        method=dataset["method"],
        count=len(rows),
        metrics=dataset.get("metrics", {}),
        rows=rows,
    )
