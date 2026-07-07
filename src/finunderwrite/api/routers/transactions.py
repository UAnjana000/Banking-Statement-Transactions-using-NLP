"""Normalized transactions listing endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Query

from finunderwrite.api.schemas import TransactionListResponse, TransactionOut
from finunderwrite.persistence import repository

router = APIRouter(tags=["transactions"])


@router.get("/transactions", response_model=TransactionListResponse)
def list_transactions(
    customer_id: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> TransactionListResponse:
    rows = repository.list_transactions(
        customer_id=customer_id, category=category, limit=limit, offset=offset
    )
    return TransactionListResponse(
        customer_id=customer_id,
        count=len(rows),
        transactions=[TransactionOut(**row) for row in rows],
    )
