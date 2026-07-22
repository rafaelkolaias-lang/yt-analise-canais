"""Pydantic schemas para /api/suggestions."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class MonitorSuggestion(BaseModel):
    """Canal descoberto que vale a pena monitorar."""
    youtube_channel_id: str
    title: str
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    subscribers: Optional[int] = None
    video_count: Optional[int] = None
    avg_vpd_recent: Optional[float] = None
    channel_published_at: Optional[str] = None
    discovery_result_id: int
    matched_term: Optional[str] = None
    suggestion_kind: str
    top_video_title: Optional[str] = None
    top_video_url: Optional[str] = None
    top_video_views: Optional[int] = None
    top_video_vpd: Optional[float] = None
    reason: str


class CandidateChannel(BaseModel):
    """Sugestão em observação automática (status=candidate) com evolução."""
    channel_id: int
    youtube_channel_id: str
    title: str
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    days_observed: int
    snapshots_count: int
    subscribers: Optional[int] = None
    first_vpd: Optional[float] = None
    last_vpd: Optional[float] = None
    vpd_delta_pct: Optional[float] = None
    signal: Optional[str] = None
    first_snapshot_at: Optional[str] = None
    last_snapshot_at: Optional[str] = None


class DismissSuggestionRequest(BaseModel):
    youtube_channel_id: str


class SuggestionOpResponse(BaseModel):
    ok: bool


class DeadChannelSuggestion(BaseModel):
    """Canal já monitorado que parece morto (recomendação, não ação)."""
    channel_id: int
    youtube_channel_id: str
    title: str
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: str
    last_snapshot_at: Optional[str] = None
    last_upload_at: Optional[str] = None
    days_since_last_upload: Optional[int] = None
    avg_vpd_recent: Optional[float] = None
    signal: Optional[str] = None
    reason: str
