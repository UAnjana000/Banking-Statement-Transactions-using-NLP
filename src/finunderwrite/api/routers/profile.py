"""Customer profile endpoint (built on demand from stored transactions)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from finunderwrite.api.pipeline import record_to_transaction
from finunderwrite.api.schemas import ProfileResponse
from finunderwrite.persistence import repository
from finunderwrite.profile.builder import build_profile

router = APIRouter(tags=["profile"])


@router.get("/profile/{customer_id}", response_model=ProfileResponse)
def get_profile(customer_id: str) -> ProfileResponse:
    stored = repository.get_profile(customer_id)
    if stored is not None:
        return ProfileResponse(**stored)

    records = repository.list_transactions(customer_id=customer_id, limit=100000)
    if not records:
        raise HTTPException(status_code=404, detail=f"No data for customer {customer_id}")

    transactions = [record_to_transaction(r) for r in records]
    profile = build_profile(customer_id, transactions)
    payload = profile.model_dump(mode="json")
    repository.save_profile(customer_id, payload)
    return ProfileResponse(**payload)
