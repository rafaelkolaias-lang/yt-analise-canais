"""Pydantic schemas para /api/analytics."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AnalyticsOverview(BaseModel):
    channels_total: int
    channels_accelerating: int
    channels_promising: int
    channels_saturated: int
    channels_stable: int
    channels_unknown: int
    videos_accelerating: int


class TimeseriesPoint(BaseModel):
    captured_at: Optional[str]
    value: Optional[float]


class GrowthPair(BaseModel):
    current: Optional[float] = None
    pct_7d: Optional[float] = None
    pct_30d: Optional[float] = None


class ChannelAnalyticsSummary(BaseModel):
    channel_id: int
    total_snapshots: int
    last_captured_at: Optional[str] = None
    signal: Optional[str] = None
    signal_reason: Optional[str] = None
    subscribers: GrowthPair
    views_total: GrowthPair
    avg_vpd_recent: GrowthPair
    uploads_per_week: Optional[float] = None


class NicheRow(BaseModel):
    tag_id: int
    tag_name: str
    channels_count: int
    avg_subscribers: Optional[int] = None
    avg_vpd: Optional[float] = None
