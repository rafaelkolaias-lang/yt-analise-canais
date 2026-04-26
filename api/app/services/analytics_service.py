"""
Analytics service — agregações sobre os snapshots já coletados.

Sem chamadas ao YouTube: só leitura do banco. O enriquecimento (signal,
vpd_trend, uploads_per_week) é feito no momento do snapshot em
`monitoring_service.snapshot_channel`, então aqui só agregamos.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import (
    Channel,
    ChannelSnapshot,
    ChannelTag,
    Tag,
    TrackedVideo,
    VideoSnapshot,
)


# Filtro de status reusado por /overview e /channels (paginação).
# `all` = sem filtro. Outros valores casam exatamente com Channel.status.
ALLOWED_STATUS_FILTERS = ("all", "active", "paused", "removed")


def _filter_channel_ids_by_status(db: Session, status: Optional[str]) -> Optional[set[int]]:
    """
    Devolve o conjunto de Channel.id que casam com o status pedido. Retorna
    None quando o filtro for 'all' (= não filtrar). Centralizado pra que
    overview e listagem apliquem a mesma regra.
    """
    if not status or status == "all":
        return None
    if status not in ALLOWED_STATUS_FILTERS:
        return set()
    rows = db.query(Channel.id).filter(Channel.status == status).all()
    return {row[0] for row in rows}


# =============================================================================
# Helpers internos
# =============================================================================
def _latest_snapshot_ids_subquery(db: Session):
    """
    Subquery com o id do último ChannelSnapshot de cada canal.
    Usamos max(captured_at) agrupado por channel_id e reencontramos o id.
    """
    # MAX(captured_at) por canal
    latest_at = (
        select(
            ChannelSnapshot.channel_id.label("channel_id"),
            func.max(ChannelSnapshot.captured_at).label("max_at"),
        )
        .group_by(ChannelSnapshot.channel_id)
        .subquery()
    )
    return latest_at


def _latest_snapshots(
    db: Session, channel_ids: Optional[set[int]] = None
) -> list[ChannelSnapshot]:
    latest_at = _latest_snapshot_ids_subquery(db)
    query = db.query(ChannelSnapshot).join(
        latest_at,
        (ChannelSnapshot.channel_id == latest_at.c.channel_id)
        & (ChannelSnapshot.captured_at == latest_at.c.max_at),
    )
    if channel_ids is not None:
        if not channel_ids:
            return []
        query = query.filter(ChannelSnapshot.channel_id.in_(channel_ids))
    return query.all()


def _count_videos_accelerating(
    db: Session, channel_ids: Optional[set[int]] = None
) -> int:
    """
    Conta TrackedVideo cujo penúltimo vs último VideoSnapshot mostram VPD crescendo.
    Faz uma passada simples: pega os 2 últimos por vídeo.
    """
    query = db.query(TrackedVideo.id).filter(TrackedVideo.status == "active")
    if channel_ids is not None:
        if not channel_ids:
            return 0
        query = query.filter(TrackedVideo.channel_id.in_(channel_ids))
    videos = query.all()
    count = 0
    for (tv_id,) in videos:
        last_two = (
            db.query(VideoSnapshot)
            .filter_by(tracked_video_id=tv_id)
            .order_by(desc(VideoSnapshot.captured_at))
            .limit(2)
            .all()
        )
        if len(last_two) == 2 and last_two[0].vpd is not None and last_two[1].vpd is not None:
            if last_two[0].vpd > last_two[1].vpd:
                count += 1
    return count


# =============================================================================
# Overview — contadores para Dashboard e topo da página /analytics
# =============================================================================
def overview(db: Session, status: Optional[str] = None) -> dict:
    """
    Agregados de canais/vídeos para o topo da tela. `status` filtra pelo
    Channel.status (`active`/`paused`/`removed`); `all` ou None = todos.
    """
    channel_ids = _filter_channel_ids_by_status(db, status)
    latest = _latest_snapshots(db, channel_ids=channel_ids)

    counts = {"heating": 0, "promising": 0, "saturated": 0, "stable": 0, "unknown": 0}
    for snap in latest:
        key = snap.signal if snap.signal in counts else "unknown"
        counts[key] += 1

    videos_accelerating = _count_videos_accelerating(db, channel_ids=channel_ids)

    return {
        "channels_total": len(latest),
        "channels_accelerating": counts["heating"],
        "channels_promising": counts["promising"],
        "channels_saturated": counts["saturated"],
        "channels_stable": counts["stable"],
        "channels_unknown": counts["unknown"],
        "videos_accelerating": videos_accelerating,
    }


# =============================================================================
# Timeseries de um canal
# =============================================================================
ALLOWED_METRICS = {
    "subscribers": ChannelSnapshot.subscribers,
    "views_total": ChannelSnapshot.views_total,
    "avg_vpd_recent": ChannelSnapshot.avg_vpd_recent,
    "uploads_per_week": ChannelSnapshot.uploads_per_week,
}


def timeseries(db: Session, channel_id: int, metric: str) -> list[dict]:
    if metric not in ALLOWED_METRICS:
        raise ValueError(f"metric inválida: {metric}")
    col = ALLOWED_METRICS[metric]

    rows = (
        db.query(ChannelSnapshot.captured_at, col)
        .filter(ChannelSnapshot.channel_id == channel_id)
        .order_by(ChannelSnapshot.captured_at.asc())
        .all()
    )
    return [{"captured_at": r[0].isoformat() if r[0] else None, "value": r[1]} for r in rows]


# =============================================================================
# Summary de um canal — crescimento % 7d/30d + uploads/sem
# =============================================================================
def _growth_pct(curr: Optional[float], past: Optional[float]) -> Optional[float]:
    if curr is None or past is None or past == 0:
        return None
    return round(((curr - past) / past) * 100.0, 2)


def _snapshot_at_or_before(
    db: Session, channel_id: int, when: datetime
) -> Optional[ChannelSnapshot]:
    return (
        db.query(ChannelSnapshot)
        .filter(ChannelSnapshot.channel_id == channel_id)
        .filter(ChannelSnapshot.captured_at <= when)
        .order_by(desc(ChannelSnapshot.captured_at))
        .first()
    )


def channel_summary(db: Session, channel_id: int) -> dict:
    channel = db.query(Channel).filter_by(id=channel_id).one_or_none()
    if channel is None:
        raise LookupError(f"canal id={channel_id} não existe")

    total_snaps = (
        db.query(func.count(ChannelSnapshot.id))
        .filter(ChannelSnapshot.channel_id == channel_id)
        .scalar()
    ) or 0

    last = (
        db.query(ChannelSnapshot)
        .filter_by(channel_id=channel_id)
        .order_by(desc(ChannelSnapshot.captured_at))
        .first()
    )

    now = datetime.utcnow()
    ref_7d = _snapshot_at_or_before(db, channel_id, now - timedelta(days=7))
    ref_30d = _snapshot_at_or_before(db, channel_id, now - timedelta(days=30))

    def _pair(field: str):
        curr = getattr(last, field) if last else None
        past_7d = getattr(ref_7d, field) if ref_7d else None
        past_30d = getattr(ref_30d, field) if ref_30d else None
        return {
            "current": curr,
            "pct_7d": _growth_pct(curr, past_7d),
            "pct_30d": _growth_pct(curr, past_30d),
        }

    return {
        "channel_id": channel_id,
        "total_snapshots": int(total_snaps),
        "last_captured_at": last.captured_at.isoformat() if last and last.captured_at else None,
        "signal": last.signal if last else None,
        "signal_reason": last.signal_reason if last else None,
        "subscribers": _pair("subscribers"),
        "views_total": _pair("views_total"),
        "avg_vpd_recent": _pair("avg_vpd_recent"),
        "uploads_per_week": last.uploads_per_week if last else None,
    }


# =============================================================================
# Niches — agregação por tag
# =============================================================================
def niches(db: Session) -> list[dict]:
    """
    Para cada tag com >= 1 canal, calcula channels_count, avg_vpd e avg_subscribers
    usando o ÚLTIMO snapshot de cada canal da tag.
    """
    tags = db.query(Tag).all()
    if not tags:
        return []

    latest = _latest_snapshots(db)
    latest_by_channel = {s.channel_id: s for s in latest}

    out: list[dict] = []
    for tag in tags:
        channel_ids = [
            ct.channel_id
            for ct in db.query(ChannelTag).filter_by(tag_id=tag.id).all()
        ]
        if not channel_ids:
            continue

        subs_vals: list[int] = []
        vpd_vals: list[float] = []
        for cid in channel_ids:
            snap = latest_by_channel.get(cid)
            if snap is None:
                continue
            if snap.subscribers is not None:
                subs_vals.append(snap.subscribers)
            if snap.avg_vpd_recent is not None:
                vpd_vals.append(snap.avg_vpd_recent)

        avg_subs = round(sum(subs_vals) / len(subs_vals)) if subs_vals else None
        avg_vpd = round(sum(vpd_vals) / len(vpd_vals), 2) if vpd_vals else None

        out.append(
            {
                "tag_id": tag.id,
                "tag_name": tag.name,
                "channels_count": len(channel_ids),
                "avg_subscribers": avg_subs,
                "avg_vpd": avg_vpd,
            }
        )

    out.sort(key=lambda r: (r["avg_vpd"] or 0), reverse=True)
    return out


# =============================================================================
# Bundle paginado de canais para a aba /analytics
# =============================================================================
def channels_paginated(
    db: Session,
    page: int,
    page_size: int,
    status: Optional[str] = None,
) -> dict:
    """
    Retorna uma página de canais com summary + 4 séries já agregadas no
    backend, evitando o fan-out de 5 requests por canal no frontend.

    Ordem dos canais: mesma do GET /api/monitoring/channels (created_at desc),
    para coerência visual com a tela de monitoramento.

    `status` filtra pelo Channel.status (`active`/`paused`/`removed`); `all`
    ou None = todos. Default da UI é `active`.
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 50:
        page_size = 50

    base = db.query(Channel)
    if status and status != "all":
        if status not in ALLOWED_STATUS_FILTERS:
            return {
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
                "items": [],
            }
        base = base.filter(Channel.status == status)

    total = base.with_entities(func.count(Channel.id)).scalar() or 0
    total_pages = (total + page_size - 1) // page_size if total else 0

    offset = (page - 1) * page_size
    rows = (
        base.order_by(desc(Channel.created_at))
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items: list[dict] = []
    for ch in rows:
        try:
            summary = channel_summary(db, ch.id)
        except LookupError:
            continue

        items.append(
            {
                "channel": {
                    "id": ch.id,
                    "youtube_channel_id": ch.youtube_channel_id,
                    "title": ch.title,
                    "url": ch.url,
                    "thumbnail_url": ch.thumbnail_url,
                },
                "summary": summary,
                "subscribers_series": timeseries(db, ch.id, "subscribers"),
                "views_series": timeseries(db, ch.id, "views_total"),
                "vpd_series": timeseries(db, ch.id, "avg_vpd_recent"),
                "uploads_series": timeseries(db, ch.id, "uploads_per_week"),
            }
        )

    return {
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "total_pages": int(total_pages),
        "items": items,
    }
