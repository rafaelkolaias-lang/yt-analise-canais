from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------
class AddChannelRequest(BaseModel):
    youtube_channel_id: str


class AddVideoRequest(BaseModel):
    youtube_video_id: str


class StatusUpdateRequest(BaseModel):
    status: Literal["active", "paused", "removed"]


class ResolveRequest(BaseModel):
    """Input do usuário (link YouTube ou ID puro) que vai virar canal ou vídeo."""
    raw: str


class ResolveResponse(BaseModel):
    kind: Literal["channel", "video"]
    youtube_id: str


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    youtube_channel_id: str
    title: str
    url: Optional[str] = None
    custom_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: str
    notes: Optional[str] = None
    is_active: bool
    source: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ChannelWithStats(ChannelRead):
    """Canal + dados do último snapshot (para a tabela da UI)."""
    subscribers: Optional[int] = None
    views_total: Optional[int] = None
    video_count: Optional[int] = None
    avg_vpd_recent: Optional[float] = None
    delta_subscribers: Optional[int] = None
    delta_views_total: Optional[int] = None
    last_snapshot_at: Optional[datetime] = None


class TrackedVideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    youtube_video_id: str
    title: str
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    unavailable_reason: Optional[str] = None
    unavailable_since: Optional[datetime] = None
    channel_title: Optional[str] = None
    channel_url: Optional[str] = None
    status: str
    tracking_source: Optional[str] = None
    first_tracked_at: datetime
    first_tracked_vpd: Optional[float] = None
    last_seen_vpd: Optional[float] = None
    last_seen_views: Optional[int] = None
    last_seen_at: Optional[datetime] = None


class ChannelSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    subscribers: Optional[int] = None
    views_total: Optional[int] = None
    video_count: Optional[int] = None
    avg_vpd_recent: Optional[float] = None
    delta_subscribers: Optional[int] = None
    delta_views_total: Optional[int] = None
    captured_at: datetime


class VideoSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tracked_video_id: int
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    vpd: Optional[float] = None
    delta_views: Optional[int] = None
    delta_likes: Optional[int] = None
    delta_comments: Optional[int] = None
    captured_at: datetime


# ---------------------------------------------------------------------------
# Operações em lote (bulk)
# ---------------------------------------------------------------------------
class BulkIdsRequest(BaseModel):
    ids: list[int]


class BulkStatusRequest(BaseModel):
    ids: list[int]
    status: Literal["active", "paused", "removed"]


class BulkOperationError(BaseModel):
    id: int
    message: str


class BulkOperationResponse(BaseModel):
    total: int
    success_count: int
    error_count: int
    processed_ids: list[int]
    errors: list[BulkOperationError]
