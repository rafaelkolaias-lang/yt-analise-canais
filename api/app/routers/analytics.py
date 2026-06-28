"""
Router /api/analytics — agregações sobre snapshots.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.analytics import (
    AnalyticsOverview,
    ChannelAnalyticsSummary,
    NicheRow,
    PaginatedChannelAnalytics,
    PaginatedVideosByChannel,
    TimeseriesPoint,
)
from app.services import analytics_service_v2 as analytics_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


_STATUS_PATTERN = "^(all|active|paused|removed)$"
_SIGNAL_PATTERN = "^(all|heating|promising|stable|saturated|unknown)$"
_SORT_PATTERN = "^(signal|score)$"


@router.get("/overview", response_model=AnalyticsOverview)
def get_overview(
    status: str = Query("active", pattern=_STATUS_PATTERN),
    db: Session = Depends(get_db),
) -> AnalyticsOverview:
    data = analytics_service.overview(db, status=status)
    return AnalyticsOverview(**data)


@router.get("/channels", response_model=PaginatedChannelAnalytics)
def get_channels_paginated(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    status: str = Query("active", pattern=_STATUS_PATTERN),
    signal: str = Query("all", pattern=_SIGNAL_PATTERN),
    sort: str = Query("signal", pattern=_SORT_PATTERN),
    db: Session = Depends(get_db),
) -> PaginatedChannelAnalytics:
    data = analytics_service.channels_paginated(
        db, page, page_size, status=status, signal=signal, sort=sort
    )
    return PaginatedChannelAnalytics(**data)


@router.get("/channels/{channel_id}/timeseries", response_model=list[TimeseriesPoint])
def get_channel_timeseries(
    channel_id: int,
    metric: str = Query("avg_vpd_recent"),
    db: Session = Depends(get_db),
) -> list[TimeseriesPoint]:
    try:
        rows = analytics_service.timeseries(db, channel_id, metric)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return [TimeseriesPoint(**r) for r in rows]


@router.get("/channels/{channel_id}/summary", response_model=ChannelAnalyticsSummary)
def get_channel_summary(
    channel_id: int, db: Session = Depends(get_db)
) -> ChannelAnalyticsSummary:
    try:
        data = analytics_service.channel_summary(db, channel_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ChannelAnalyticsSummary(**data)


@router.get("/niches", response_model=list[NicheRow])
def get_niches(db: Session = Depends(get_db)) -> list[NicheRow]:
    return [NicheRow(**r) for r in analytics_service.niches(db)]


@router.get("/videos-by-channel", response_model=PaginatedVideosByChannel)
def get_videos_by_channel(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=20),
    channel_status: str = Query("active", pattern=_STATUS_PATTERN),
    db: Session = Depends(get_db),
) -> PaginatedVideosByChannel:
    data = analytics_service.videos_by_channel(
        db, page, page_size, channel_status=channel_status
    )
    return PaginatedVideosByChannel(**data)
