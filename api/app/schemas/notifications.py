"""Pydantic schemas para /api/notifications."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class QuotaUsageEvent(BaseModel):
    at: str
    label: str
    cost: int
    key_index: int


class QuotaSummary(BaseModel):
    date_utc: str
    keys_count: int
    daily_quota_per_key: int
    total_quota: int
    used: int
    remaining: int
    used_per_key: list[int]
    last_event: Optional[QuotaUsageEvent] = None
