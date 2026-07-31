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

from sqlalchemy import desc, func, or_, select
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

# Base do "Score de Oportunidade" por sinal do ultimo snapshot. Quanto maior,
# mais o canal vale a pena estudar pra replica. `unknown`/None fica num meio
# termo (nao penaliza tanto quanto saturado, mas nao premia como aquecendo).
_SCORE_SIGNAL_BASE: dict[str, int] = {
    "heating": 45,
    "promising": 38,
    "stable": 22,
    "saturated": 8,
}


def opportunity_score(snap: Optional[ChannelSnapshot]) -> int:
    """
    Score 0–100 de "oportunidade de réplica", derivado SOMENTE do último
    snapshot do canal (barato e em lote — sem queries extras).

    Combina:
      - sinal (base): aquecendo > promissor > estável > saturado;
      - momento do VPD (`delta_avg_vpd` relativo ao VPD atual);
      - crescimento de inscritos no último ciclo (`delta_subscribers`);
      - tendência de VPD (`vpd_trend`).

    Mantido propositalmente simples e explicável. Não substitui o
    `channel_summary` (que tem janelas 7/30/90d), serve pra ranquear a lista
    inteira sem custo de N queries por canal.
    """
    if snap is None:
        return 0
    score = float(_SCORE_SIGNAL_BASE.get(snap.signal or "", 15))

    avg_vpd = snap.avg_vpd_recent or 0.0
    if snap.delta_avg_vpd and snap.delta_avg_vpd > 0:
        if avg_vpd > 0:
            pct = (snap.delta_avg_vpd / avg_vpd) * 100.0
            score += min(25.0, max(0.0, pct / 4.0))
        else:
            score += 5.0

    if snap.delta_subscribers and snap.delta_subscribers > 0:
        score += 8.0

    if snap.vpd_trend and snap.vpd_trend > 0:
        score += 7.0

    return max(0, min(100, round(score)))


def _channel_query(db: Session, status: Optional[str]):
    # Candidatos (sugestões em observação automática) nunca aparecem no
    # Analytics — nem no filtro "all". Eles vivem só na página Sugestões.
    query = db.query(Channel).filter(Channel.status != "candidate")
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


def _videos_accelerating_rows(
    db: Session, channel_ids: Optional[set[int]] = None
) -> list[dict]:
    """
    Videos ativos cujo VPD subiu do penultimo pro ultimo snapshot.

    Devolve linhas cruas `{tracked_video_id, vpd_now, vpd_prev}` — o contador
    do /overview e a listagem do /highlights compartilham esta funcao pra a
    regra de "acelerando" ser literalmente a mesma nos dois lugares.
    """
    query = db.query(TrackedVideo.id).filter(TrackedVideo.status == "active")
    if channel_ids is not None:
        if not channel_ids:
            return []
        query = query.filter(TrackedVideo.channel_id.in_(channel_ids))

    rows: list[dict] = []
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
            rows.append(
                {
                    "tracked_video_id": tracked_video_id,
                    "vpd_now": last_two[0].vpd,
                    "vpd_prev": last_two[1].vpd,
                }
            )
    return rows


def _count_videos_accelerating(db: Session, channel_ids: Optional[set[int]] = None) -> int:
    return len(_videos_accelerating_rows(db, channel_ids=channel_ids))


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


# =============================================================================
# Highlights — listas por tras dos contadores do Dashboard
# =============================================================================
# Cada "kind" corresponde a um card do Dashboard. Os tres primeiros olham o
# sinal do ultimo snapshot do canal; o ultimo olha os videos rastreados.
HIGHLIGHT_KINDS = ("heating", "promising", "saturated", "videos_accelerating")

# Teto de linhas devolvidas por aba. Alto o bastante pra caber a base atual
# (dezenas/centenas de canais) e baixo o bastante pra o JSON nao explodir.
HIGHLIGHT_MAX_LIMIT = 200


def highlights(
    db: Session,
    kind: str,
    status: Optional[str] = "active",
    limit: int = 50,
) -> dict:
    """
    Lista COMPACTA por tras de cada contador do /overview.

    Diferente de `channels_paginated`, aqui nao ha series temporais nem
    `channel_summary` por canal — so o que cabe numa linha de tabela. Assim o
    Dashboard abre a aba sem pagar o custo da tela de Analytics.

    IMPORTANTE: usa exatamente os mesmos filtros do `overview` (mesmo `status`,
    mesmo sinal do ultimo snapshot, mesma regra de video acelerando), pra o
    numero do card sempre bater com a quantidade de linhas da aba.
    """
    if kind not in HIGHLIGHT_KINDS:
        raise ValueError(f"kind invalido: {kind}")
    if limit < 1:
        limit = 1
    if limit > HIGHLIGHT_MAX_LIMIT:
        limit = HIGHLIGHT_MAX_LIMIT

    if kind == "videos_accelerating":
        return _highlights_videos(db, status=status, limit=limit)
    return _highlights_channels(db, signal=kind, status=status, limit=limit)


def _highlights_channels(
    db: Session, signal: str, status: Optional[str], limit: int
) -> dict:
    query = _channel_query(db, status)
    if query is None:
        return {"kind": signal, "total": 0, "channels": [], "videos": []}

    channels = query.all()
    latest_by_channel = {
        snap.channel_id: snap for snap in _latest_snapshots(db, {c.id for c in channels})
    }

    matched = [
        c
        for c in channels
        if (latest_by_channel.get(c.id).signal if latest_by_channel.get(c.id) else None)
        == signal
    ]

    # Melhor oportunidade primeiro; VPD e created_at como desempate (mesma
    # logica do sort "score" da tela de Analytics).
    def _sort_key(ch: Channel) -> tuple:
        snap = latest_by_channel.get(ch.id)
        score = opportunity_score(snap)
        vpd = snap.avg_vpd_recent if snap and snap.avg_vpd_recent is not None else -1.0
        created = ch.created_at.timestamp() if ch.created_at else 0.0
        return (-score, -float(vpd), -created)

    matched.sort(key=_sort_key)

    rows = []
    for ch in matched[:limit]:
        snap = latest_by_channel.get(ch.id)
        rows.append(
            {
                "id": ch.id,
                "youtube_channel_id": ch.youtube_channel_id,
                "title": ch.title,
                "url": ch.url,
                "thumbnail_url": ch.thumbnail_url,
                "status": ch.status,
                "is_favorite": ch.is_favorite,
                "signal": snap.signal if snap else None,
                "signal_reason": snap.signal_reason if snap else None,
                "opportunity_score": opportunity_score(snap),
                "subscribers": snap.subscribers if snap else None,
                "avg_vpd_recent": snap.avg_vpd_recent if snap else None,
                "delta_avg_vpd": snap.delta_avg_vpd if snap else None,
                "uploads_per_week": snap.uploads_per_week if snap else None,
                "captured_at": (
                    snap.captured_at.isoformat() if snap and snap.captured_at else None
                ),
            }
        )

    return {"kind": signal, "total": len(matched), "channels": rows, "videos": []}


def _highlights_videos(db: Session, status: Optional[str], limit: int) -> dict:
    channel_ids = _filter_channel_ids_by_status(db, status)
    accelerating = _videos_accelerating_rows(db, channel_ids=channel_ids)
    if not accelerating:
        return {"kind": "videos_accelerating", "total": 0, "channels": [], "videos": []}

    # Maior salto de VPD primeiro — o que mais acelerou aparece no topo.
    accelerating.sort(key=lambda r: (r["vpd_now"] - r["vpd_prev"]), reverse=True)
    page = accelerating[:limit]

    # Hidrata titulo/thumb/canal das linhas da pagina numa unica query.
    videos_by_id = {
        v.id: v
        for v in db.query(TrackedVideo)
        .filter(TrackedVideo.id.in_([r["tracked_video_id"] for r in page]))
        .all()
    }
    channels_by_id = {
        c.id: c
        for c in db.query(Channel)
        .filter(Channel.id.in_({v.channel_id for v in videos_by_id.values()}))
        .all()
    }

    rows = []
    for r in page:
        video = videos_by_id.get(r["tracked_video_id"])
        if video is None:
            continue
        channel = channels_by_id.get(video.channel_id)
        rows.append(
            {
                "id": video.id,
                "youtube_video_id": video.youtube_video_id,
                "title": video.title,
                "url": video.url,
                "thumbnail_url": video.thumbnail_url,
                "channel_id": video.channel_id,
                "channel_title": channel.title if channel else "—",
                "vpd_now": r["vpd_now"],
                "vpd_prev": r["vpd_prev"],
                "vpd_delta": round(r["vpd_now"] - r["vpd_prev"], 2),
                "last_seen_views": video.last_seen_views,
                "last_seen_at": (
                    video.last_seen_at.isoformat() if video.last_seen_at else None
                ),
            }
        )

    return {
        "kind": "videos_accelerating",
        "total": len(accelerating),
        "channels": [],
        "videos": rows,
    }


ALLOWED_METRICS = {
    "subscribers": ChannelSnapshot.subscribers,
    "views_total": ChannelSnapshot.views_total,
    "avg_vpd_recent": ChannelSnapshot.avg_vpd_recent,
    "uploads_per_week": ChannelSnapshot.uploads_per_week,
}


# Span mínimo (em dias) entre pontos da série "VPD do canal". Snapshots muito
# próximos (ex.: sync manual minutos depois do automático) extrapolam qualquer
# ruído pra números absurdos de views/dia — então acumulamos até ter >= 6h.
_CHANNEL_VPD_MIN_SPAN_DAYS = 0.25


def channel_vpd_series(db: Session, channel_id: int) -> list[dict]:
    """
    Série "VPD do canal": ganho de views do CANAL INTEIRO por dia, derivado
    dos snapshots de `views_total` já coletados (zero custo de YouTube).

    Diferente do `avg_vpd_recent` (VPD do melhor vídeo dos últimos uploads),
    aqui cada ponto é (views_total atual - anterior) / dias entre snapshots.
    Valores negativos são possíveis e reais (canal perdeu views — ex.: vídeos
    apagados/privados); mostramos como estão.
    """
    rows = (
        db.query(ChannelSnapshot.captured_at, ChannelSnapshot.views_total)
        .filter(
            ChannelSnapshot.channel_id == channel_id,
            ChannelSnapshot.views_total.isnot(None),
        )
        .order_by(ChannelSnapshot.captured_at.asc())
        .all()
    )
    out: list[dict] = []
    anchor_at: Optional[datetime] = None
    anchor_views: Optional[int] = None
    for captured_at, views_total in rows:
        if captured_at is None:
            continue
        if anchor_at is None:
            anchor_at = captured_at
            anchor_views = views_total
            continue
        span_days = (captured_at - anchor_at).total_seconds() / 86400.0
        if span_days < _CHANNEL_VPD_MIN_SPAN_DAYS:
            continue
        gain = (views_total or 0) - (anchor_views or 0)
        out.append(
            {
                "captured_at": captured_at.isoformat(),
                "value": round(gain / span_days, 2),
            }
        )
        anchor_at = captured_at
        anchor_views = views_total
    return out


def uploads_events_series(db: Session, channel_id: int) -> list[dict]:
    """
    Série do gráfico "Uploads/semana": em vez de um ponto por snapshot (o sync
    roda várias vezes ao dia e polui o gráfico com barras repetidas), só emite
    ponto quando um upload novo foi detectado — isto é, quando o `video_count`
    do canal aumentou em relação ao snapshot anterior. O valor plotado continua
    sendo o ritmo `uploads_per_week` daquele momento. Queda no `video_count`
    (vídeo apagado/privado) só rebaixa a base, sem gerar ponto.
    """
    rows = (
        db.query(
            ChannelSnapshot.captured_at,
            ChannelSnapshot.video_count,
            ChannelSnapshot.uploads_per_week,
        )
        .filter(
            ChannelSnapshot.channel_id == channel_id,
            ChannelSnapshot.video_count.isnot(None),
        )
        .order_by(ChannelSnapshot.captured_at.asc())
        .all()
    )
    out: list[dict] = []
    baseline: Optional[int] = None
    for captured_at, video_count, uploads_per_week in rows:
        if captured_at is None:
            continue
        if baseline is not None and video_count > baseline:
            out.append(
                {
                    "captured_at": captured_at.isoformat(),
                    "value": uploads_per_week,
                }
            )
        baseline = video_count
    return out


def timeseries(db: Session, channel_id: int, metric: str) -> list[dict]:
    # Métricas derivadas (não são colunas do snapshot): views/dia do canal
    # inteiro e uploads/semana só nas datas com upload detectado.
    if metric == "channel_vpd":
        return channel_vpd_series(db, channel_id)
    if metric == "uploads_events":
        return uploads_events_series(db, channel_id)
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


def video_timeseries(db: Session, tracked_video_id: int) -> dict[str, list[dict]]:
    snaps = (
        db.query(VideoSnapshot)
        .filter(VideoSnapshot.tracked_video_id == tracked_video_id)
        .order_by(VideoSnapshot.captured_at.asc())
        .all()
    )
    return {
        "vpd_series": [
            {"captured_at": s.captured_at.isoformat() if s.captured_at else None, "value": s.vpd}
            for s in snaps
        ],
        "views_series": [
            {
                "captured_at": s.captured_at.isoformat() if s.captured_at else None,
                "value": float(s.views) if s.views is not None else None,
            }
            for s in snaps
        ],
    }


def videos_by_channel(
    db: Session,
    page: int,
    page_size: int,
    channel_status: Optional[str] = None,
    q: Optional[str] = None,
    only_rising: bool = False,
) -> dict:
    """
    Lista canais paginada (pelo canal) com seus vídeos monitorados e séries
    temporais. Evita N+1: busca canais, depois vídeos e snapshots em lote.

    `only_rising=True` deixa passar SÓ os vídeos que estão subindo (VPD do
    último snapshot > penúltimo) — mesma regra do card "Vídeos acelerando" do
    Dashboard (`_videos_accelerating_rows`). Canais que ficariam sem nenhum
    vídeo saem da lista, então `total` continua batendo com o que é exibido.
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 20:
        page_size = 20

    base = _channel_query(db, channel_status)
    if base is None:
        return {"page": page, "page_size": page_size, "total": 0, "total_pages": 0, "items": []}

    # Busca: inclui o canal se o NOME do canal casar OU se ele tiver algum
    # VÍDEO cujo título case (case-insensitive). Assim "pesquisar nome do
    # canal/vídeo" funciona nesta aba organizada por canal.
    if q and q.strip():
        like = f"%{q.strip()}%"
        vid_channel_ids = select(TrackedVideo.channel_id).where(
            TrackedVideo.title.ilike(like)
        )
        base = base.filter(
            or_(Channel.title.ilike(like), Channel.id.in_(vid_channel_ids))
        )

    # Filtro "só os que estão subindo": restringe a paginação aos canais que
    # têm ao menos um vídeo em alta e guarda os ids pra podar os vídeos depois.
    rising_ids: Optional[set[int]] = None
    if only_rising:
        rising_ids = {r["tracked_video_id"] for r in _videos_accelerating_rows(db)}
        if not rising_ids:
            return {
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
                "items": [],
            }
        base = base.filter(
            Channel.id.in_(
                select(TrackedVideo.channel_id).where(TrackedVideo.id.in_(rising_ids))
            )
        )

    total: int = base.count()
    total_pages = (total + page_size - 1) // page_size if total else 0
    offset = (page - 1) * page_size
    channels = (
        base.order_by(desc(Channel.created_at))
        .offset(offset)
        .limit(page_size)
        .all()
    )

    if not channels:
        return {"page": page, "page_size": page_size, "total": total, "total_pages": total_pages, "items": []}

    channel_ids = [c.id for c in channels]

    videos_query = db.query(TrackedVideo).filter(
        TrackedVideo.channel_id.in_(channel_ids)
    )
    if rising_ids is not None:
        videos_query = videos_query.filter(TrackedVideo.id.in_(rising_ids))
    videos = videos_query.order_by(
        TrackedVideo.channel_id, desc(TrackedVideo.last_seen_vpd)
    ).all()

    video_ids = [v.id for v in videos]
    if video_ids:
        snapshots = (
            db.query(VideoSnapshot)
            .filter(VideoSnapshot.tracked_video_id.in_(video_ids))
            .order_by(VideoSnapshot.tracked_video_id, VideoSnapshot.captured_at.asc())
            .all()
        )
    else:
        snapshots = []

    snaps_by_video: dict[int, list[VideoSnapshot]] = {}
    for snap in snapshots:
        snaps_by_video.setdefault(snap.tracked_video_id, []).append(snap)

    videos_by_channel_id: dict[int, list[TrackedVideo]] = {}
    for video in videos:
        videos_by_channel_id.setdefault(video.channel_id, []).append(video)

    items: list[dict] = []
    for channel in channels:
        ch_videos = videos_by_channel_id.get(channel.id, [])
        video_items = []
        for v in ch_videos:
            v_snaps = snaps_by_video.get(v.id, [])
            video_items.append(
                {
                    "id": v.id,
                    "youtube_video_id": v.youtube_video_id,
                    "title": v.title,
                    "url": v.url,
                    "thumbnail_url": v.thumbnail_url,
                    "status": v.status,
                    "first_tracked_at": v.first_tracked_at.isoformat() if v.first_tracked_at else None,
                    "first_tracked_vpd": v.first_tracked_vpd,
                    "last_seen_vpd": v.last_seen_vpd,
                    "last_seen_views": v.last_seen_views,
                    "last_seen_at": v.last_seen_at.isoformat() if v.last_seen_at else None,
                    "unavailable_reason": v.unavailable_reason,
                    "unavailable_since": v.unavailable_since.isoformat() if v.unavailable_since else None,
                    "vpd_series": [
                        {"captured_at": s.captured_at.isoformat() if s.captured_at else None, "value": s.vpd}
                        for s in v_snaps
                    ],
                    "views_series": [
                        {
                            "captured_at": s.captured_at.isoformat() if s.captured_at else None,
                            "value": float(s.views) if s.views is not None else None,
                        }
                        for s in v_snaps
                    ],
                }
            )
        items.append(
            {
                "channel": {
                    "id": channel.id,
                    "youtube_channel_id": channel.youtube_channel_id,
                    "title": channel.title,
                    "url": channel.url,
                    "thumbnail_url": channel.thumbnail_url,
                    "status": channel.status,
                },
                "videos": video_items,
            }
        )

    return {
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "total_pages": int(total_pages),
        "items": items,
    }


ALLOWED_SORTS = ("signal", "score")


def channels_paginated(
    db: Session,
    page: int,
    page_size: int,
    status: Optional[str] = None,
    signal: Optional[str] = None,
    sort: Optional[str] = None,
    q: Optional[str] = None,
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
    if sort not in ALLOWED_SORTS:
        sort = "signal"

    base = _channel_query(db, status)
    if base is None:
        return {"page": page, "page_size": page_size, "total": 0, "total_pages": 0, "items": []}

    # Busca por nome do canal (case-insensitive). Aplicada no SQL pra reduzir o
    # conjunto carregado em memória antes de derivar sinal/ordenar.
    if q and q.strip():
        base = base.filter(Channel.title.ilike(f"%{q.strip()}%"))

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

    # Score de oportunidade por canal (derivado do ultimo snapshot, em lote).
    score_by_channel: dict[int, int] = {
        c.id: opportunity_score(latest_by_channel.get(c.id)) for c in channels
    }

    # Ordenacao. Default ("signal"): prioridade de sinal -> avg_vpd ->
    # created_at desc. "score": maior score de oportunidade primeiro, com
    # avg_vpd e created_at como desempate.
    def _signal_sort_key(ch: Channel) -> tuple:
        snap = latest_by_channel.get(ch.id)
        sig = _signal_of(ch)
        priority = SIGNAL_PRIORITY.get(sig, SIGNAL_PRIORITY["unknown"])
        # avg_vpd_recent desc: negativo pra inverter (None vira -inf efetivo).
        vpd = snap.avg_vpd_recent if snap and snap.avg_vpd_recent is not None else -1.0
        # created_at desc: usa timestamp; canais sem created_at (nao deveria
        # acontecer) vao pro fim.
        created = ch.created_at.timestamp() if ch.created_at else 0.0
        return (priority, -float(vpd), -created)

    def _score_sort_key(ch: Channel) -> tuple:
        snap = latest_by_channel.get(ch.id)
        score = score_by_channel.get(ch.id, 0)
        vpd = snap.avg_vpd_recent if snap and snap.avg_vpd_recent is not None else -1.0
        created = ch.created_at.timestamp() if ch.created_at else 0.0
        return (-score, -float(vpd), -created)

    channels.sort(key=_score_sort_key if sort == "score" else _signal_sort_key)

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
                    "spike_alert_enabled": channel.spike_alert_enabled,
                    "spike_alert_multiplier": channel.spike_alert_multiplier,
                    "is_favorite": channel.is_favorite,
                    "notes": channel.notes,
                },
                "opportunity_score": score_by_channel.get(channel.id, 0),
                "summary": summary,
                "subscribers_series": timeseries(db, channel.id, "subscribers"),
                "views_series": timeseries(db, channel.id, "views_total"),
                "vpd_series": timeseries(db, channel.id, "avg_vpd_recent"),
                "channel_vpd_series": channel_vpd_series(db, channel.id),
                "uploads_series": uploads_events_series(db, channel.id),
            }
        )

    return {
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "total_pages": int(total_pages),
        "items": items,
    }
