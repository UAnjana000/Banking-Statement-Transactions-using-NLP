"""Underwriting feature endpoint (built on demand)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from finunderwrite.api.pipeline import record_to_transaction
from finunderwrite.api.schemas import FeatureResponse
from finunderwrite.behaviour.summary import analyze_behaviour
from finunderwrite.features.vectorizer import build_feature_row
from finunderwrite.persistence import repository
from finunderwrite.profile.builder import build_profile

router = APIRouter(tags=["features"])


@router.get("/features/{customer_id}", response_model=FeatureResponse)
def get_features(customer_id: str) -> FeatureResponse:
    stored = repository.get_feature(customer_id)
    if stored is not None:
        return FeatureResponse(customer_id=customer_id, features=stored)

    records = repository.list_transactions(customer_id=customer_id, limit=100000)
    if not records:
        raise HTTPException(status_code=404, detail=f"No data for customer {customer_id}")

    transactions = [record_to_transaction(r) for r in records]
    profile = build_profile(customer_id, transactions)
    summary = analyze_behaviour(transactions, customer_id)
    row = build_feature_row(profile, summary)
    repository.save_feature(customer_id, row)
    return FeatureResponse(customer_id=customer_id, features=row)
