from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import (
    ChannelBlacklist,
    DiscoveryResultChannel,
    DiscoveryResultVideo,
    DiscoveryRun,
)
from app.schemas.discovery import (
    BlacklistEntryRead,
    DefaultFiltersRead,
    DiscoveryRunRead,
    DiscoveryRunWithProgress,
    ReviewItemRequest,
    ReviewProgress,
    SearchRequest,
)
from app.services import discovery_service, youtube_client
from app.services.discovery_service import DiscoveryFilters

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


def _compute_progress(db: Session, run_id: int) -> ReviewProgress:
    """Conta total e reviewed para canais e vídeos de um run."""
    ch_total, ch_reviewed = (
        db.query(
            func.count(DiscoveryResultChannel.id),
            func.count(DiscoveryResultChannel.reviewed_at),
        )
        .filter(DiscoveryResultChannel.run_id == run_id)
        .one()
    )
    vd_total, vd_reviewed = (
        db.query(
            func.count(DiscoveryResultVideo.id),
            func.count(DiscoveryResultVideo.reviewed_at),
        )
        .filter(DiscoveryResultVideo.run_id == run_id)
        .one()
    )
    return ReviewProgress(
        channels_total=int(ch_total or 0),
        channels_reviewed=int(ch_reviewed or 0),
        videos_total=int(vd_total or 0),
        videos_reviewed=int(vd_reviewed or 0),
    )


@router.get("/defaults", response_model=DefaultFiltersRead)
def get_defaults(db: Session = Depends(get_db)) -> DefaultFiltersRead:
    return DefaultFiltersRead(**discovery_service.load_default_filters(db))


@router.post("/search", response_model=DiscoveryRunRead)
def search(req: SearchRequest, db: Session = Depends(get_db)) -> DiscoveryRunRead:
    defaults = discovery_service.load_default_filters(db)
    filters = DiscoveryFilters(
        terms=[t.strip() for t in req.terms if t.strip()],
        window_days=req.window_days if req.window_days is not None else defaults["window_days"],
        min_views=req.min_views if req.min_views is not None else defaults["min_views"],
        min_vpd=req.min_vpd if req.min_vpd is not None else defaults["min_vpd"],
        min_duration_seconds=req.min_duration_seconds
        if req.min_duration_seconds is not None
        else defaults["min_duration_seconds"],
        languages=req.languages if req.languages is not None else defaults["languages"],
        pages_per_term=req.pages_per_term if req.pages_per_term is not None else defaults["pages_per_term"],
        min_channel_age_days=req.min_channel_age_days
        if req.min_channel_age_days is not None
        else defaults["min_channel_age_days"],
        max_channel_age_days=req.max_channel_age_days
        if req.max_channel_age_days is not None
        else defaults["max_channel_age_days"],
    )
    if not filters.terms:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Informe pelo menos um termo.")

    try:
        run = discovery_service.run_discovery(db, filters)
    except youtube_client.NoAPIKeyConfigured as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except youtube_client.InvalidAPIKey as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except youtube_client.QuotaExceeded as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    progress = _compute_progress(db, run.id)
    return DiscoveryRunRead(
        id=run.id,
        terms=run.terms,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        channels_found=run.channels_found,
        videos_found=run.videos_found,
        notes=run.notes,
        filters_json=run.filters_json,
        channel_results=list(run.channel_results),
        video_results=list(run.video_results),
        progress=progress,
    )


@router.get("/runs", response_model=list[DiscoveryRunWithProgress])
def list_runs(
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[DiscoveryRunWithProgress]:
    rows = (
        db.query(DiscoveryRun)
        .order_by(DiscoveryRun.started_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        DiscoveryRunWithProgress(
            id=r.id,
            terms=r.terms,
            status=r.status,
            started_at=r.started_at,
            finished_at=r.finished_at,
            channels_found=r.channels_found,
            videos_found=r.videos_found,
            notes=r.notes,
            progress=_compute_progress(db, r.id),
        )
        for r in rows
    ]


@router.get("/runs/{run_id}", response_model=DiscoveryRunRead)
def get_run(run_id: int, db: Session = Depends(get_db)) -> DiscoveryRunRead:
    row = db.query(DiscoveryRun).filter_by(id=run_id).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"run {run_id} not found")
    progress = _compute_progress(db, row.id)
    return DiscoveryRunRead(
        id=row.id,
        terms=row.terms,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        channels_found=row.channels_found,
        videos_found=row.videos_found,
        notes=row.notes,
        filters_json=row.filters_json,
        channel_results=list(row.channel_results),
        video_results=list(row.video_results),
        progress=progress,
    )


# ---------------------------------------------------------------------------
# Marcacao de revisao por item
# ---------------------------------------------------------------------------
@router.patch("/runs/{run_id}/channels/{result_id}/review")
def mark_channel_reviewed(
    run_id: int,
    result_id: int,
    req: ReviewItemRequest,
    db: Session = Depends(get_db),
) -> dict:
    row = (
        db.query(DiscoveryResultChannel)
        .filter_by(id=result_id, run_id=run_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="result not found")
    row.reviewed_at = datetime.utcnow() if req.reviewed else None
    db.commit()
    return {"id": result_id, "reviewed_at": row.reviewed_at}


@router.patch("/runs/{run_id}/videos/{result_id}/review")
def mark_video_reviewed(
    run_id: int,
    result_id: int,
    req: ReviewItemRequest,
    db: Session = Depends(get_db),
) -> dict:
    row = (
        db.query(DiscoveryResultVideo)
        .filter_by(id=result_id, run_id=run_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="result not found")
    row.reviewed_at = datetime.utcnow() if req.reviewed else None
    db.commit()
    return {"id": result_id, "reviewed_at": row.reviewed_at}


# ---------------------------------------------------------------------------
# Blacklist (canais que o usuario removeu — discovery nao reaceita)
# ---------------------------------------------------------------------------
@router.get("/blacklist", response_model=list[BlacklistEntryRead])
def list_blacklist(db: Session = Depends(get_db)) -> list[BlacklistEntryRead]:
    return (
        db.query(ChannelBlacklist)
        .order_by(ChannelBlacklist.blacklisted_at.desc())
        .all()
    )


@router.delete(
    "/blacklist/{youtube_channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unblacklist(
    youtube_channel_id: str, db: Session = Depends(get_db)
) -> None:
    row = (
        db.query(ChannelBlacklist)
        .filter_by(youtube_channel_id=youtube_channel_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not in blacklist")
    db.delete(row)
    db.commit()
