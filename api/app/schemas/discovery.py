from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    terms: list[str] = Field(..., min_length=1, description="Termos de busca, 1+")
    window_days: Optional[int] = None
    min_views: Optional[int] = None
    min_vpd: Optional[int] = None
    min_duration_seconds: Optional[int] = None
    languages: Optional[list[str]] = None
    pages_per_term: Optional[int] = None


class DefaultFiltersRead(BaseModel):
    window_days: int
    min_views: int
    min_vpd: int
    min_duration_seconds: int
    languages: list[str]
    pages_per_term: int


class ResultVideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    youtube_video_id: str
    youtube_channel_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    duration_seconds: Optional[int] = None
    published_at: Optional[datetime] = None
    vpd: Optional[float] = None
    matched_term: Optional[str] = None
    captured_at: datetime
    reviewed_at: Optional[datetime] = None


class ResultChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    youtube_channel_id: str
    title: str
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    subscribers: Optional[int] = None
    views_total: Optional[int] = None
    video_count: Optional[int] = None
    captured_at: datetime
    reviewed_at: Optional[datetime] = None


class DiscoveryRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    terms: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    channels_found: int
    videos_found: int
    notes: Optional[str] = None


class ReviewProgress(BaseModel):
    """Quantos itens já foram triados pelo usuário num run."""
    channels_total: int
    channels_reviewed: int
    videos_total: int
    videos_reviewed: int


class DiscoveryRunWithProgress(DiscoveryRunSummary):
    progress: ReviewProgress


class DiscoveryRunRead(DiscoveryRunSummary):
    filters_json: Optional[str] = None
    channel_results: list[ResultChannelRead] = []
    video_results: list[ResultVideoRead] = []
    progress: ReviewProgress


class ReviewItemRequest(BaseModel):
    """Marca um item como revisado/não-revisado."""
    reviewed: bool = True


class BlacklistEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    youtube_channel_id: str
    reason: Optional[str] = None
    blacklisted_at: datetime
