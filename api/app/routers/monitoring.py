from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

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
    SpikeAlertUpdateRequest,
    StatusUpdateRequest,
    TrackedVideoRead,
    VideoSnapshotRead,
)
from app.services import monitoring_service, youtube_client

# Limite por request no endpoint batch /channels/best-videos.
# Mantido baixo o suficiente pra a query IN (...) ser rapida e o JSON nao
# explodir, mas grande o suficiente pra cobrir uma pagina inteira da UI
# (50 canais por pagina) com folga.
BEST_VIDEOS_BATCH_MAX_IDS = 200


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
def _latest_snapshots_by_channel(
    db: Session, channel_ids: list[int]
) -> dict[int, ChannelSnapshot]:
    """
    Busca o ULTIMO snapshot de cada canal em UMA query (evita N+1).

    Antes, `list_channels` fazia 1 SELECT por canal pra pegar o snapshot mais
    recente — 50 canais = 50 queries. Aqui um subquery agrupa o `max(captured_at)`
    por canal e o join traz só as rows correspondentes de uma vez.
    """
    if not channel_ids:
        return {}
    latest_at = (
        select(
            ChannelSnapshot.channel_id.label("channel_id"),
            func.max(ChannelSnapshot.captured_at).label("max_at"),
        )
        .where(ChannelSnapshot.channel_id.in_(channel_ids))
        .group_by(ChannelSnapshot.channel_id)
        .subquery()
    )
    rows = (
        db.query(ChannelSnapshot)
        .join(
            latest_at,
            (ChannelSnapshot.channel_id == latest_at.c.channel_id)
            & (ChannelSnapshot.captured_at == latest_at.c.max_at),
        )
        .all()
    )
    # Em caso raro de captured_at duplicado pro mesmo canal, fica com o ultimo
    # — irrelevante porque sao do mesmo instante.
    return {snap.channel_id: snap for snap in rows}


def _channel_with_stats(c: Channel, last: ChannelSnapshot | None) -> ChannelWithStats:
    return ChannelWithStats(
        id=c.id,
        youtube_channel_id=c.youtube_channel_id,
        title=c.title,
        url=c.url,
        custom_url=c.custom_url,
        thumbnail_url=c.thumbnail_url,
        status=c.status,
        notes=c.notes,
        is_active=c.is_active,
        source=c.source,
        spike_alert_enabled=c.spike_alert_enabled,
        spike_alert_multiplier=c.spike_alert_multiplier,
        spike_last_alert_at=c.spike_last_alert_at,
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


def _video_read(tv: TrackedVideo) -> TrackedVideoRead:
    return TrackedVideoRead(
        id=tv.id,
        channel_id=tv.channel_id,
        youtube_video_id=tv.youtube_video_id,
        title=tv.title,
        url=tv.url,
        thumbnail_url=tv.thumbnail_url,
        unavailable_reason=tv.unavailable_reason,
        unavailable_since=tv.unavailable_since,
        channel_title=tv.channel.title if tv.channel else None,
        channel_url=tv.channel.url if tv.channel else None,
        status=tv.status,
        tracking_source=tv.tracking_source,
        first_tracked_at=tv.first_tracked_at,
        first_tracked_vpd=tv.first_tracked_vpd,
        last_seen_vpd=tv.last_seen_vpd,
        last_seen_views=tv.last_seen_views,
        last_seen_at=tv.last_seen_at,
    )


@router.get("/channels", response_model=list[ChannelWithStats])
def list_channels(db: Session = Depends(get_db)) -> list[ChannelWithStats]:
    # Candidatos (status="candidate") ficam fora do Monitoramento — eles são
    # sugestões em observação automática e vivem na página Sugestões.
    rows = (
        db.query(Channel)
        .filter(Channel.status != "candidate")
        .order_by(Channel.created_at.desc())
        .all()
    )
    latest = _latest_snapshots_by_channel(db, [c.id for c in rows])
    return [_channel_with_stats(c, latest.get(c.id)) for c in rows]


@router.post("/channels", response_model=ChannelRead, status_code=status.HTTP_201_CREATED)
def add_channel(req: AddChannelRequest, db: Session = Depends(get_db)) -> ChannelRead:
    try:
        return monitoring_service.add_channel(db, req.youtube_channel_id)
    except monitoring_service.PermanentlyUnavailableError as exc:
        raise HTTPException(status.HTTP_410_GONE, detail=str(exc))
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


@router.get(
    "/channels/best-videos",
    response_model=dict[int, list[TrackedVideoRead]],
)
def channels_best_videos_batch(
    ids: str = Query(..., description="Lista CSV de channel ids, ex: '1,2,3'"),
    db: Session = Depends(get_db),
) -> dict[int, list[TrackedVideoRead]]:
    """
    Retorna os 'melhores videos detectados' de varios canais em UMA query SQL.

    Forma da resposta: `{ "<channel_id>": [TrackedVideoRead, ...], ... }`.
    Canais sem nenhum melhor detectado aparecem com `[]`. Canais inexistentes
    sao ignorados (nao estouram).

    Limite: BEST_VIDEOS_BATCH_MAX_IDS por request.
    """
    raw_ids = [chunk.strip() for chunk in ids.split(",") if chunk.strip()]
    parsed_ids: list[int] = []
    for raw in raw_ids:
        try:
            parsed_ids.append(int(raw))
        except ValueError:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"id invalido em 'ids': {raw!r}",
            )

    if not parsed_ids:
        return {}
    if len(parsed_ids) > BEST_VIDEOS_BATCH_MAX_IDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"limite de {BEST_VIDEOS_BATCH_MAX_IDS} ids por request "
                f"(recebido {len(parsed_ids)})"
            ),
        )

    rows = monitoring_service.list_best_videos_for_channels(db, parsed_ids)
    out: dict[int, list[TrackedVideoRead]] = {cid: [] for cid in parsed_ids}
    for row in rows:
        out.setdefault(row.channel_id, []).append(_video_read(row))
    return out


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


@router.patch("/channels/{channel_id}/spike-alert", response_model=ChannelRead)
def update_channel_spike_alert(
    channel_id: int, req: SpikeAlertUpdateRequest, db: Session = Depends(get_db)
) -> ChannelRead:
    """
    Configura o alerta de pico de views do canal: `enabled` liga/desliga e
    `multiplier` define o gatilho (ex.: 2.0 = disparar quando o ganho de views
    das últimas 24h for 2x a média diária dos 7 dias anteriores).
    """
    ch = db.query(Channel).filter_by(id=channel_id).one_or_none()
    if ch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Canal id={channel_id} não existe.")
    if req.enabled is not None:
        ch.spike_alert_enabled = req.enabled
    if req.multiplier is not None:
        ch.spike_alert_multiplier = req.multiplier
    db.commit()
    db.refresh(ch)
    return ChannelRead.model_validate(ch)


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
    except monitoring_service.PermanentlyUnavailableError as exc:
        raise HTTPException(status.HTTP_410_GONE, detail=str(exc))
    except youtube_client.NoAPIKeyConfigured as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/channels/{channel_id}/best-videos", response_model=list[TrackedVideoRead])
def channel_best_videos(channel_id: int, db: Session = Depends(get_db)) -> list[TrackedVideoRead]:
    return [_video_read(row) for row in monitoring_service.list_best_videos_for_channel(db, channel_id)]


# ---------------------------------------------------------------------------
# Vídeos
# ---------------------------------------------------------------------------
@router.get("/videos", response_model=list[TrackedVideoRead])
def list_videos(db: Session = Depends(get_db)) -> list[TrackedVideoRead]:
    # joinedload do canal evita N+1: `_video_read` acessa `tv.channel.title`/
    # `.url` por linha, o que dispararia 1 query por video sem o eager load.
    rows = (
        db.query(TrackedVideo)
        .options(joinedload(TrackedVideo.channel))
        .order_by(TrackedVideo.first_tracked_at.desc())
        .all()
    )
    return [_video_read(row) for row in rows]


@router.post("/videos", response_model=TrackedVideoRead, status_code=status.HTTP_201_CREATED)
def add_video(req: AddVideoRequest, db: Session = Depends(get_db)) -> TrackedVideoRead:
    try:
        return _video_read(monitoring_service.add_video(db, req.youtube_video_id))
    except monitoring_service.PermanentlyUnavailableError as exc:
        raise HTTPException(status.HTTP_410_GONE, detail=str(exc))
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
        return _video_read(monitoring_service.set_video_status(db, video_id, req.status))
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
    except monitoring_service.PermanentlyUnavailableError as exc:
        raise HTTPException(status.HTTP_410_GONE, detail=str(exc))
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
