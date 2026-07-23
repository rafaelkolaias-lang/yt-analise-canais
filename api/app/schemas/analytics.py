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
    pct_90d: Optional[float] = None


class GrowthConsistency(BaseModel):
    positive_windows: int = 0
    available_windows: int = 0
    label: str = "sem dados"


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
    median_recent_views: Optional[float] = None
    recent_uploads_considered: int = 0
    subscribers_consistency: GrowthConsistency
    views_consistency: GrowthConsistency
    breakout_candidate: bool = False
    breakout_reason: Optional[str] = None


class NicheRow(BaseModel):
    tag_id: int
    tag_name: str
    channels_count: int
    avg_subscribers: Optional[int] = None
    avg_vpd: Optional[float] = None


# =============================================================================
# Bundle paginado para a tela /analytics
# =============================================================================
class ChannelBasic(BaseModel):
    id: int
    youtube_channel_id: str
    title: str
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    # Estado do alerta de pico — permite o sino no card do Analytics.
    spike_alert_enabled: bool = False
    spike_alert_multiplier: float = 2.0
    # Metadados do usuário — estrela e observação também no Analytics.
    is_favorite: bool = False
    notes: Optional[str] = None


class ChannelAnalyticsBundle(BaseModel):
    channel: ChannelBasic
    opportunity_score: int = 0
    summary: ChannelAnalyticsSummary
    subscribers_series: list[TimeseriesPoint]
    views_series: list[TimeseriesPoint]
    vpd_series: list[TimeseriesPoint]
    uploads_series: list[TimeseriesPoint]


class PaginatedChannelAnalytics(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    items: list[ChannelAnalyticsBundle]


# =============================================================================
# Analytics de vídeos por canal
# =============================================================================
class VideoSnapshotPoint(BaseModel):
    captured_at: Optional[str] = None
    value: Optional[float] = None


class VideoAnalyticsItem(BaseModel):
    id: int
    youtube_video_id: str
    title: str
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: str
    first_tracked_at: Optional[str] = None
    first_tracked_vpd: Optional[float] = None
    last_seen_vpd: Optional[float] = None
    last_seen_views: Optional[int] = None
    last_seen_at: Optional[str] = None
    unavailable_reason: Optional[str] = None
    unavailable_since: Optional[str] = None
    vpd_series: list[VideoSnapshotPoint]
    views_series: list[VideoSnapshotPoint]


class ChannelBasicWithStatus(BaseModel):
    id: int
    youtube_channel_id: str
    title: str
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: str


class ChannelVideoBundle(BaseModel):
    channel: ChannelBasicWithStatus
    videos: list[VideoAnalyticsItem]


class PaginatedVideosByChannel(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    items: list[ChannelVideoBundle]
