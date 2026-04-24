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
    TimeseriesPoint,
)
from app.services import analytics_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverview)
def get_overview(db: Session = Depends(get_db)) -> AnalyticsOverview:
    data = analytics_service.overview(db)
    return AnalyticsOverview(**data)


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
