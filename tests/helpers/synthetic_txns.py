"""Builders for synthetic multi-month transaction histories with KNOWN patterns.

Used by behaviour/recurring/profile tests. Deterministic (fixed seed).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from finunderwrite.contracts.transaction import CanonicalTransaction


def _txn(
    date: datetime,
    *,
    description: str,
    merchant: str | None = None,
    debit: Decimal | None = None,
    credit: Decimal | None = None,
    balance: Decimal | None = None,
    category: str | None = None,
    payment_mode: str | None = None,
) -> CanonicalTransaction:
    return CanonicalTransaction(
        transaction_id=str(uuid.uuid4()),
        date=date,
        merchant=merchant,
        description=description,
        debit=debit,
        credit=credit,
        balance=balance,
        category=category,
        payment_mode=payment_mode,
    )


def build_known_history(
    *,
    months: int = 6,
    start: datetime | None = None,
    salary: Decimal = Decimal("60000"),
    rent: Decimal = Decimal("18000"),
) -> list[CanonicalTransaction]:
    """Build a history with a fixed salary, rent, and two subscriptions per month.

    Known ground truth per month:
    - 1 salary credit (~salary) on day 1 -> category Salary, monthly cadence
    - 1 rent debit (~rent, small drift) on day 3 -> category Rent, monthly
    - Netflix 499 on day 5 -> Subscription, monthly
    - Spotify 119 on day 7 -> Subscription, monthly
    - a couple of variable discretionary spends
    """
    start = start or datetime(2025, 1, 1)
    txns: list[CanonicalTransaction] = []
    balance = Decimal("50000")

    for m in range(months):
        base = _add_months(start, m)

        balance += salary
        txns.append(
            _txn(
                base,
                description="NEFT-SALARY-ACME CORP",
                merchant="Acme Corp",
                credit=salary,
                balance=balance,
                category="Salary",
                payment_mode="NEFT",
            )
        )

        # Rent drifts by a few rupees month to month but should still group.
        rent_amt = rent + Decimal(m * 3)
        balance -= rent_amt
        txns.append(
            _txn(
                base + timedelta(days=2),
                description="UPI-RENT-LANDLORD",
                merchant="Landlord",
                debit=rent_amt,
                balance=balance,
                category="Rent",
                payment_mode="UPI",
            )
        )

        balance -= Decimal("499")
        txns.append(
            _txn(
                base + timedelta(days=4),
                description="UPI-NETFLIX SUBSCRIPTION",
                merchant="Netflix",
                debit=Decimal("499"),
                balance=balance,
                category="Subscription",
                payment_mode="UPI",
            )
        )

        balance -= Decimal("119")
        txns.append(
            _txn(
                base + timedelta(days=6),
                description="UPI-SPOTIFY SUBSCRIPTION",
                merchant="Spotify",
                debit=Decimal("119"),
                balance=balance,
                category="Subscription",
                payment_mode="UPI",
            )
        )

        # Two discretionary spends (variable amount/merchant).
        spend1 = Decimal(str(1000 + m * 50))
        balance -= spend1
        txns.append(
            _txn(
                base + timedelta(days=10),
                description="POS-SWIGGY ORDER",
                merchant="Swiggy",
                debit=spend1,
                balance=balance,
                category="Food",
                payment_mode="POS",
            )
        )

        spend2 = Decimal(str(2500 + m * 25))
        balance -= spend2
        txns.append(
            _txn(
                base + timedelta(days=15),
                description="ATM-CASH WITHDRAWAL",
                merchant=None,
                debit=spend2,
                balance=balance,
                category="ATM",
                payment_mode="ATM",
            )
        )

    return txns


def _add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    return dt.replace(year=year, month=month)
