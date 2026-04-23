from __future__ import annotations

from datetime import date as LocalDate
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, Field


class EntryCreate(BaseModel):
    type: Literal["credit", "debit"]
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    date: LocalDate = Field(default_factory=LocalDate.today)
    description: str | None = Field(default=None, max_length=255)


class EntryRead(BaseModel):
    id: str
    type: Literal["credit", "debit"]
    amount: Decimal
    date: LocalDate
    description: str | None
    created_at: datetime


class BalanceRead(BaseModel):
    date: LocalDate
    balance: Decimal
    updated_at: datetime


class BacklogProcessResult(BaseModel):
    processed_entries: int
    pending_entries: int


class HealthRead(BaseModel):
    service: str
    status: Literal["ok"]
    pending_backlog_entries: int


def amount_to_cents(amount: Decimal) -> int:
    normalized_amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(normalized_amount * 100)


def cents_to_decimal(amount_cents: int) -> Decimal:
    return (Decimal(amount_cents) / Decimal("100")).quantize(Decimal("0.01"))
