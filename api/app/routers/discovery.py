from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import DiscoveryRun
from app.schemas.discovery import (
    DefaultFiltersRead,
    DiscoveryRunRead,
    DiscoveryRunSummary,
    SearchRequest,
)
from app.services import discovery_service, youtube_client
from app.services.discovery_service import DiscoveryFilters

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


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

    return run


@router.get("/runs", response_model=list[DiscoveryRunSummary])
def list_runs(
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[DiscoveryRunSummary]:
    rows = (
        db.query(DiscoveryRun)
        .order_by(DiscoveryRun.started_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return rows


@router.get("/runs/{run_id}", response_model=DiscoveryRunRead)
def get_run(run_id: int, db: Session = Depends(get_db)) -> DiscoveryRunRead:
    row = db.query(DiscoveryRun).filter_by(id=run_id).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"run {run_id} not found")
    return row
