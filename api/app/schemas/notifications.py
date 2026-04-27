"""Pydantic schemas para /api/notifications."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


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


# ---------------------------------------------------------------------------
# Notificações persistentes (tabela `notifications`)
# ---------------------------------------------------------------------------
class NotificationRead(BaseModel):
    """DTO de leitura de uma notificação para o frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    title: str
    message: Optional[str] = None
    progress_pct: Optional[int] = None
    metadata_json: Optional[str] = None
    source_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    read_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None


class NotificationsListResponse(BaseModel):
    items: list[NotificationRead]
    unread_count: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class NotificationOpResponse(BaseModel):
    id: int
    changed: bool
