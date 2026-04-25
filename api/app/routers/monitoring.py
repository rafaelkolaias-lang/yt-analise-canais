from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Channel, ChannelSnapshot, TrackedVideo
from app.schemas.monitoring import (
    AddChannelRequest,
    AddVideoRequest,
    BulkIdsRequest,
    BulkOperationError,
    BulkOperationResponse,
    BulkStatusRequest,
    ChannelRead,
    ChannelSnapshotRead,
    ChannelWithStats,
    ResolveRequest,
    ResolveResponse,
    StatusUpdateRequest,
    TrackedVideoRead,
    VideoSnapshotRead,
)
from app.services import monitoring_service, youtube_client


def _run_bulk(ids: list[int], op: Callable[[int], None]) -> BulkOperationResponse:
    """
    Itera item a item executando `op(id)`. Falha individual nao trava o lote;
    cada erro vira BulkOperationError(id, message).
    """
    total = len(ids)
    processed: list[int] = []
    errors: list[BulkOperationError] = []
    for item_id in ids:
        try:
            op(item_id)
            processed.append(item_id)
        except LookupError as exc:
            errors.append(BulkOperationError(id=item_id, message=str(exc)))
        except ValueError as exc:
            errors.append(BulkOperationError(id=item_id, message=str(exc)))
        except youtube_client.NoAPIKeyConfigured as exc:
            errors.append(BulkOperationError(id=item_id, message=str(exc)))
        except Exception as exc:  # noqa: BLE001
            errors.append(BulkOperationError(id=item_id, message=str(exc) or type(exc).__name__))
    return BulkOperationResponse(
        total=total,
        success_count=len(processed),
        error_count=len(errors),
        processed_ids=processed,
        errors=errors,
    )


router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


# ---------------------------------------------------------------------------
# Canais
# ---------------------------------------------------------------------------
def _channel_with_stats(db: Session, c: Channel) -> ChannelWithStats:
    last = (
        db.query(ChannelSnapshot)
        .filter_by(channel_id=c.id)
        .order_by(desc(ChannelSnapshot.captured_at))
        .first()
    )
    return ChannelWithStats(
        id=c.id,
        youtube_channel_id=c.youtube_channel_id,
        title=c.title,
        url=c.url,
        custom_url=c.custom_url,
        thumbnail_url=c.thumbnail_url,
        status=c.status,
        is_active=c.is_active,
        source=c.source,
        created_at=c.created_at,
        updated_at=c.updated_at,
        subscribers=last.subscribers if last else None,
        views_total=last.views_total if last else None,
        video_count=last.video_count if last else None,
        avg_vpd_recent=last.avg_vpd_recent if last else None,
        delta_subscribers=last.delta_subscribers if last else None,
        delta_views_total=last.delta_views_total if last else None,
        last_snapshot_at=last.captured_at if last else None,
    )


@router.get("/channels", response_model=list[ChannelWithStats])
def list_channels(db: Session = Depends(get_db)) -> list[ChannelWithStats]:
    rows = db.query(Channel).order_by(Channel.created_at.desc()).all()
    return [_channel_with_stats(db, c) for c in rows]


@router.post("/channels", response_model=ChannelRead, status_code=status.HTTP_201_CREATED)
def add_channel(req: AddChannelRequest, db: Session = Depends(get_db)) -> ChannelRead:
    try:
        return monitoring_service.add_channel(db, req.youtube_channel_id)
    except youtube_client.NoAPIKeyConfigured as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Canais — operações em lote (registradas ANTES das rotas /{channel_id} para
# evitar que o roteador tente casar 'bulk-status' contra o parametro int)
# ---------------------------------------------------------------------------
@router.patch("/channels/bulk-status", response_model=BulkOperationResponse)
def bulk_update_channel_status(
    req: BulkStatusRequest, db: Session = Depends(get_db)
) -> BulkOperationResponse:
    def _op(cid: int) -> None:
        monitoring_service.set_channel_status(db, cid, req.status)
    return _run_bulk(req.ids, _op)


@router.post("/channels/bulk-snapshot", response_model=BulkOperationResponse)
def bulk_snapshot_channels(
    req: BulkIdsRequest, db: Session = Depends(get_db)
) -> BulkOperationResponse:
    def _op(cid: int) -> None:
        monitoring_service.snapshot_channel(db, cid)
    return _run_bulk(req.ids, _op)


@router.post("/channels/bulk-delete", response_model=BulkOperationResponse)
def bulk_delete_channels(
    req: BulkIdsRequest, db: Session = Depends(get_db)
) -> BulkOperationResponse:
    def _op(cid: int) -> None:
        monitoring_service.delete_channel(db, cid)
    return _run_bulk(req.ids, _op)


@router.patch("/channels/{channel_id}", response_model=ChannelRead)
def update_channel_status(
    channel_id: int, req: StatusUpdateRequest, db: Session = Depends(get_db)
) -> ChannelRead:
    try:
        return monitoring_service.set_channel_status(db, channel_id, req.status)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_channel(channel_id: int, db: Session = Depends(get_db)) -> None:
    try:
        monitoring_service.delete_channel(db, channel_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/channels/{channel_id}/snapshot",
    response_model=ChannelSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def snapshot_channel(channel_id: int, db: Session = Depends(get_db)) -> ChannelSnapshotRead:
    try:
        return monitoring_service.snapshot_channel(db, channel_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    except youtube_client.NoAPIKeyConfigured as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/channels/{channel_id}/best-videos", response_model=list[TrackedVideoRead])
def channel_best_videos(channel_id: int, db: Session = Depends(get_db)) -> list[TrackedVideoRead]:
    return monitoring_service.list_best_videos_for_channel(db, channel_id)


# ---------------------------------------------------------------------------
# Vídeos
# ---------------------------------------------------------------------------
@router.get("/videos", response_model=list[TrackedVideoRead])
def list_videos(db: Session = Depends(get_db)) -> list[TrackedVideoRead]:
    return db.query(TrackedVideo).order_by(TrackedVideo.first_tracked_at.desc()).all()


@router.post("/videos", response_model=TrackedVideoRead, status_code=status.HTTP_201_CREATED)
def add_video(req: AddVideoRequest, db: Session = Depends(get_db)) -> TrackedVideoRead:
    try:
        return monitoring_service.add_video(db, req.youtube_video_id)
    except youtube_client.NoAPIKeyConfigured as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Vídeos — operações em lote (registradas ANTES das rotas /{video_id})
# ---------------------------------------------------------------------------
@router.patch("/videos/bulk-status", response_model=BulkOperationResponse)
def bulk_update_video_status(
    req: BulkStatusRequest, db: Session = Depends(get_db)
) -> BulkOperationResponse:
    def _op(vid: int) -> None:
        monitoring_service.set_video_status(db, vid, req.status)
    return _run_bulk(req.ids, _op)


@router.post("/videos/bulk-snapshot", response_model=BulkOperationResponse)
def bulk_snapshot_videos(
    req: BulkIdsRequest, db: Session = Depends(get_db)
) -> BulkOperationResponse:
    def _op(vid: int) -> None:
        monitoring_service.snapshot_video(db, vid)
    return _run_bulk(req.ids, _op)


@router.post("/videos/bulk-delete", response_model=BulkOperationResponse)
def bulk_delete_videos(
    req: BulkIdsRequest, db: Session = Depends(get_db)
) -> BulkOperationResponse:
    def _op(vid: int) -> None:
        monitoring_service.delete_video(db, vid)
    return _run_bulk(req.ids, _op)


@router.patch("/videos/{video_id}", response_model=TrackedVideoRead)
def update_video_status(
    video_id: int, req: StatusUpdateRequest, db: Session = Depends(get_db)
) -> TrackedVideoRead:
    try:
        return monitoring_service.set_video_status(db, video_id, req.status)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_video(video_id: int, db: Session = Depends(get_db)) -> None:
    try:
        monitoring_service.delete_video(db, video_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/videos/{video_id}/snapshot",
    response_model=VideoSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def snapshot_video(video_id: int, db: Session = Depends(get_db)) -> VideoSnapshotRead:
    try:
        return monitoring_service.snapshot_video(db, video_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    except youtube_client.NoAPIKeyConfigured as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Resolve (link/ID → tipo + youtube_id)
# ---------------------------------------------------------------------------
@router.post("/resolve", response_model=ResolveResponse)
def resolve_input(
    req: ResolveRequest, db: Session = Depends(get_db)
) -> ResolveResponse:
    """
    Recebe um link YouTube ou ID puro e devolve o tipo (channel|video) +
    youtube_id resolvido. Custa 0 units pra IDs e URLs com ID embutido,
    1 unit pra handles (@nome).
    """
    try:
        kind, yt_id = monitoring_service.resolve_youtube_input(db, req.raw)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except youtube_client.NoAPIKeyConfigured as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ResolveResponse(kind=kind, youtube_id=yt_id)
