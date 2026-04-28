"""
Analytics service - agregacoes sobre snapshots e videos rastreados.

Este modulo evita chamadas ao YouTube. Tudo aqui eh derivado do banco:
  - snapshots de canal
  - snapshots/videos rastreados
  - tags
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import Channel, ChannelSnapshot, ChannelTag, Tag, TrackedVideo, VideoSnapshot
from app.services import settings_reader

ALLOWED_STATUS_FILTERS = ("all", "active", "paused", "removed")
ALLOWED_SIGNAL_FILTERS = ("all", "heating", "promising", "stable", "saturated", "unknown")

# Ordem do MELHOR para o PIOR. Indice menor = prioridade maior.
# `unknown` cobre canais sem snapshot e snapshots com signal nulo/desconhecido.
SIGNAL_PRIORITY: dict[str, int] = {
    "heating": 0,
    "promising": 1,
    "stable": 2,
    "saturated": 3,
    "unknown": 4,
}


def _channel_query(db: Session, status: Optional[str]):
    query = db.query(Channel)
    if status and status != "all":
        if status not in ALLOWED_STATUS_FILTERS:
            return None
        query = query.filter(Channel.status == status)
    return query


def _filter_channel_ids_by_status(db: Session, status: Optional[str]) -> Optional[set[int]]:
    query = _channel_query(db, status)
    if query is None:
        return set()
    if not status or status == "all":
        return None
    return {row[0] for row in query.with_entities(Channel.id).all()}


def _latest_snapshot_at_subquery():
    return (
        select(
            ChannelSnapshot.channel_id.label("channel_id"),
            func.max(ChannelSnapshot.captured_at).label("max_at"),
        )
        .group_by(ChannelSnapshot.channel_id)
        .subquery()
    )


def _latest_snapshots(db: Session, channel_ids: Optional[set[int]] = None) -> list[ChannelSnapshot]:
    latest_at = _latest_snapshot_at_subquery()
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


def _count_videos_accelerating(db: Session, channel_ids: Optional[set[int]] = None) -> int:
    query = db.query(TrackedVideo.id).filter(TrackedVideo.status == "active")
    if channel_ids is not None:
        if not channel_ids:
            return 0
        query = query.filter(TrackedVideo.channel_id.in_(channel_ids))

    count = 0
    for (tracked_video_id,) in query.all():
        last_two = (
            db.query(VideoSnapshot)
            .filter_by(tracked_video_id=tracked_video_id)
            .order_by(desc(VideoSnapshot.captured_at))
            .limit(2)
            .all()
        )
        if len(last_two) != 2:
            continue
        if last_two[0].vpd is None or last_two[1].vpd is None:
            continue
        if last_two[0].vpd > last_two[1].vpd:
            count += 1
    return count


def overview(db: Session, status: Optional[str] = None) -> dict:
    query = _channel_query(db, status)
    if query is None:
        return {
            "channels_total": 0,
            "channels_accelerating": 0,
            "channels_promising": 0,
            "channels_saturated": 0,
            "channels_stable": 0,
            "channels_unknown": 0,
            "videos_accelerating": 0,
        }

    channels = query.all()
    latest_by_channel = {snap.channel_id: snap for snap in _latest_snapshots(db, {c.id for c in channels})}
    counts = {"heating": 0, "promising": 0, "saturated": 0, "stable": 0, "unknown": 0}

    for channel in channels:
        snap = latest_by_channel.get(channel.id)
        key = snap.signal if snap and snap.signal in counts else "unknown"
        counts[key] += 1

    channel_ids = {c.id for c in channels} if status and status != "all" else _filter_channel_ids_by_status(db, status)
    videos_accelerating = _count_videos_accelerating(db, channel_ids=channel_ids)

    return {
        "channels_total": len(channels),
        "channels_accelerating": counts["heating"],
        "channels_promising": counts["promising"],
        "channels_saturated": counts["saturated"],
        "channels_stable": counts["stable"],
        "channels_unknown": counts["unknown"],
        "videos_accelerating": videos_accelerating,
    }


ALLOWED_METRICS = {
    "subscribers": ChannelSnapshot.subscribers,
    "views_total": ChannelSnapshot.views_total,
    "avg_vpd_recent": ChannelSnapshot.avg_vpd_recent,
    "uploads_per_week": ChannelSnapshot.uploads_per_week,
}


def timeseries(db: Session, channel_id: int, metric: str) -> list[dict]:
    if metric not in ALLOWED_METRICS:
        raise ValueError(f"metric invalida: {metric}")
    col = ALLOWED_METRICS[metric]
    rows = (
        db.query(ChannelSnapshot.captured_at, col)
        .filter(ChannelSnapshot.channel_id == channel_id)
        .order_by(ChannelSnapshot.captured_at.asc())
        .all()
    )
    return [{"captured_at": row[0].isoformat() if row[0] else None, "value": row[1]} for row in rows]


def _growth_pct(curr: Optional[float], past: Optional[float]) -> Optional[float]:
    if curr is None or past is None or past == 0:
        return None
    return round(((curr - past) / past) * 100.0, 2)


def _snapshot_at_or_before(db: Session, channel_id: int, when: datetime) -> Optional[ChannelSnapshot]:
    return (
        db.query(ChannelSnapshot)
        .filter(ChannelSnapshot.channel_id == channel_id)
        .filter(ChannelSnapshot.captured_at <= when)
        .order_by(desc(ChannelSnapshot.captured_at))
        .first()
    )


def _growth_pair(
    last: Optional[ChannelSnapshot],
    ref_7d: Optional[ChannelSnapshot],
    ref_30d: Optional[ChannelSnapshot],
    ref_90d: Optional[ChannelSnapshot],
    field: str,
) -> dict:
    curr = getattr(last, field) if last else None
    past_7d = getattr(ref_7d, field) if ref_7d else None
    past_30d = getattr(ref_30d, field) if ref_30d else None
    past_90d = getattr(ref_90d, field) if ref_90d else None
    return {
        "current": curr,
        "pct_7d": _growth_pct(curr, past_7d),
        "pct_30d": _growth_pct(curr, past_30d),
        "pct_90d": _growth_pct(curr, past_90d),
    }


def _growth_consistency(pair: dict) -> dict:
    windows = [pair.get("pct_7d"), pair.get("pct_30d"), pair.get("pct_90d")]
    available = [value for value in windows if value is not None]
    positive = [value for value in available if value > 0]
    if not available:
        label = "sem dados"
    elif len(positive) == len(available):
        label = "forte"
    elif positive:
        label = "mista"
    else:
        label = "fraca"
    return {
        "positive_windows": len(positive),
        "available_windows": len(available),
        "label": label,
    }


def _last_known_video_views(db: Session, tracked_video: TrackedVideo) -> Optional[int]:
    if tracked_video.last_seen_views is not None:
        return tracked_video.last_seen_views
    snap = (
        db.query(VideoSnapshot.views)
        .filter(VideoSnapshot.tracked_video_id == tracked_video.id)
        .order_by(desc(VideoSnapshot.captured_at))
        .first()
    )
    return snap[0] if snap and snap[0] is not None else None


def _recent_upload_view_stats(db: Session, channel_id: int, sample_size: int) -> tuple[Optional[float], int]:
    videos = (
        db.query(TrackedVideo)
        .filter(TrackedVideo.channel_id == channel_id)
        .order_by(desc(TrackedVideo.first_tracked_at))
        .limit(sample_size)
        .all()
    )
    views = [value for value in (_last_known_video_views(db, video) for video in videos) if value is not None]
    if not views:
        return (None, 0)
    return (float(median(views)), len(views))


def _breakout_reason(
    subscribers: Optional[int],
    median_recent_views: Optional[float],
    max_subscribers: int,
    min_median_views: int,
    ratio_threshold: float,
) -> Optional[str]:
    if subscribers is None or median_recent_views is None:
        return None
    if subscribers > max_subscribers or median_recent_views < min_median_views:
        return None
    ratio = median_recent_views / max(subscribers, 1)
    if ratio < ratio_threshold:
        return None
    return (
        f"canal pequeno ({subscribers} inscritos) com mediana recente de "
        f"{int(median_recent_views)} views ({ratio:.1f}x inscritos)"
    )


def channel_summary(db: Session, channel_id: int) -> dict:
    channel = db.query(Channel).filter_by(id=channel_id).one_or_none()
    if channel is None:
        raise LookupError(f"canal id={channel_id} nao existe")

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
    ref_90d = _snapshot_at_or_before(db, channel_id, now - timedelta(days=90))

    subscribers_pair = _growth_pair(last, ref_7d, ref_30d, ref_90d, "subscribers")
    views_pair = _growth_pair(last, ref_7d, ref_30d, ref_90d, "views_total")
    vpd_pair = _growth_pair(last, ref_7d, ref_30d, ref_90d, "avg_vpd_recent")

    sample_size = settings_reader.get_int(db, "analytics.recent_uploads_sample_size", 5)
    median_recent_views, recent_uploads_considered = _recent_upload_view_stats(db, channel_id, sample_size)

    breakout_reason = _breakout_reason(
        subscribers=subscribers_pair["current"],
        median_recent_views=median_recent_views,
        max_subscribers=settings_reader.get_int(db, "analytics.breakout_max_subscribers", 10000),
        min_median_views=settings_reader.get_int(db, "analytics.breakout_min_median_views", 50000),
        ratio_threshold=settings_reader.get_float(db, "analytics.breakout_views_to_subs_ratio", 5.0),
    )

    return {
        "channel_id": channel_id,
        "total_snapshots": int(total_snaps),
        "last_captured_at": last.captured_at.isoformat() if last and last.captured_at else None,
        "signal": last.signal if last else None,
        "signal_reason": last.signal_reason if last else None,
        "subscribers": subscribers_pair,
        "views_total": views_pair,
        "avg_vpd_recent": vpd_pair,
        "uploads_per_week": last.uploads_per_week if last else None,
        "median_recent_views": median_recent_views,
        "recent_uploads_considered": recent_uploads_considered,
        "subscribers_consistency": _growth_consistency(subscribers_pair),
        "views_consistency": _growth_consistency(views_pair),
        "breakout_candidate": breakout_reason is not None,
        "breakout_reason": breakout_reason,
    }


def niches(db: Session) -> list[dict]:
    tags = db.query(Tag).all()
    if not tags:
        return []

    latest_by_channel = {snap.channel_id: snap for snap in _latest_snapshots(db)}
    out: list[dict] = []

    for tag in tags:
        tagged_channel_ids = [row.channel_id for row in db.query(ChannelTag).filter_by(tag_id=tag.id).all()]
        if not tagged_channel_ids:
            continue

        with_snapshot = [latest_by_channel[cid] for cid in tagged_channel_ids if cid in latest_by_channel]
        if not with_snapshot:
            continue

        subs_vals = [snap.subscribers for snap in with_snapshot if snap.subscribers is not None]
        vpd_vals = [snap.avg_vpd_recent for snap in with_snapshot if snap.avg_vpd_recent is not None]

        out.append(
            {
                "tag_id": tag.id,
                "tag_name": tag.name,
                "channels_count": len(with_snapshot),
                "avg_subscribers": round(sum(subs_vals) / len(subs_vals)) if subs_vals else None,
                "avg_vpd": round(sum(vpd_vals) / len(vpd_vals), 2) if vpd_vals else None,
            }
        )

    out.sort(key=lambda row: (row["avg_vpd"] or 0), reverse=True)
    return out


def channels_paginated(
    db: Session,
    page: int,
    page_size: int,
    status: Optional[str] = None,
    signal: Optional[str] = None,
) -> dict:
    """
    Lista canais paginada com filtros opcionais de `status` (situacao do
    canal) e `signal` (sinal do ULTIMO snapshot). Independente do filtro,
    a lista vem ORDENADA do melhor sinal para o pior, com criterios
    secundarios estaveis. A ordenacao e feita ANTES da paginacao para que
    a primeira pagina sempre traga os canais mais interessantes.

    Critério de ordenação:
      1. SIGNAL_PRIORITY do sinal do ultimo snapshot (heating < promising
         < stable < saturated < unknown).
      2. `avg_vpd_recent` desc (canais com mais movimento primeiro dentro
         do mesmo grupo).
      3. `created_at` desc (mais recentes primeiro como desempate final).
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 50:
        page_size = 50

    if signal and signal not in ALLOWED_SIGNAL_FILTERS:
        signal = "all"

    base = _channel_query(db, status)
    if base is None:
        return {"page": page, "page_size": page_size, "total": 0, "total_pages": 0, "items": []}

    # Carrega todos os canais que passam no filtro de status, junto com
    # o sinal do ultimo snapshot. O custo extra do "carregar todos antes
    # de paginar" e aceitavel: a base ativa hoje e ~dezenas/centenas de
    # canais e precisamos do sinal pra ordenar. Se a base crescer muito,
    # vale criar uma materialized view ou cache do "sinal atual por canal".
    channels = base.all()
    latest_by_channel = {snap.channel_id: snap for snap in _latest_snapshots(db, {c.id for c in channels})}

    def _signal_of(ch: Channel) -> str:
        snap = latest_by_channel.get(ch.id)
        if snap and snap.signal in SIGNAL_PRIORITY:
            return snap.signal
        return "unknown"

    # Filtro por sinal (depois de derivar o sinal de cada canal).
    if signal and signal != "all":
        channels = [c for c in channels if _signal_of(c) == signal]

    # Ordenacao por prioridade de sinal -> avg_vpd -> created_at desc.
    def _sort_key(ch: Channel) -> tuple:
        snap = latest_by_channel.get(ch.id)
        sig = _signal_of(ch)
        priority = SIGNAL_PRIORITY.get(sig, SIGNAL_PRIORITY["unknown"])
        # avg_vpd_recent desc: negativo pra inverter (None vira -inf efetivo).
        vpd = snap.avg_vpd_recent if snap and snap.avg_vpd_recent is not None else -1.0
        # created_at desc: usa timestamp; canais sem created_at (nao deveria
        # acontecer) vao pro fim.
        created = ch.created_at.timestamp() if ch.created_at else 0.0
        return (priority, -float(vpd), -created)

    channels.sort(key=_sort_key)

    total = len(channels)
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size
    page_channels = channels[start : start + page_size]

    items: list[dict] = []
    for channel in page_channels:
        summary = channel_summary(db, channel.id)
        items.append(
            {
                "channel": {
                    "id": channel.id,
                    "youtube_channel_id": channel.youtube_channel_id,
                    "title": channel.title,
                    "url": channel.url,
                    "thumbnail_url": channel.thumbnail_url,
                },
                "summary": summary,
                "subscribers_series": timeseries(db, channel.id, "subscribers"),
                "views_series": timeseries(db, channel.id, "views_total"),
                "vpd_series": timeseries(db, channel.id, "avg_vpd_recent"),
                "uploads_series": timeseries(db, channel.id, "uploads_per_week"),
            }
        )

    return {
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "total_pages": int(total_pages),
        "items": items,
    }
