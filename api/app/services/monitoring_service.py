"""
Monitoring service — adiciona canais e vídeos ao monitoramento persistente.

Fluxo típico:
  - UI mostra resultado de uma DiscoveryRun.
  - Usuário clica 'Monitorar canal' / 'Monitorar vídeo' em uma linha.
  - Backend resolve dados atuais do YouTube (se ainda não tem Channel cadastrado)
    e cria as rows em `channels` / `tracked_videos`. Idempotente: se já existe,
    retorna o existente.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import Channel, ChannelSnapshot, TrackedVideo, VideoSnapshot
from app.services import settings_reader, youtube_client
from app.services.discovery_service import (
    compute_vpd,
    parse_iso_dt,
    parse_iso8601_duration,
)


def _pick_thumbnail(snippet: dict) -> Optional[str]:
    """
    YouTube devolve thumbnails em 3 tamanhos (default 88px, medium 240px, high 800px).
    Pegamos a maior disponível — o frontend redimensiona via CSS pra cada uso.
    """
    thumbs = (snippet.get("thumbnails") or {}) if isinstance(snippet, dict) else {}
    for key in ("high", "medium", "default"):
        item = thumbs.get(key)
        if isinstance(item, dict) and item.get("url"):
            return str(item["url"])[:512]
    return None


def _get_or_create_channel_from_youtube(
    db: Session, yt_channel_id: str, client: Optional[youtube_client.YouTubeClient] = None
) -> Channel:
    existing = db.query(Channel).filter_by(youtube_channel_id=yt_channel_id).one_or_none()
    if existing:
        return existing

    yt_client = client or youtube_client.build_from_db(db)
    items = yt_client.channels_by_ids([yt_channel_id])
    if not items:
        raise ValueError(f"Canal {yt_channel_id} não encontrado no YouTube.")
    c = items[0]
    snippet = c.get("snippet", {}) or {}

    channel = Channel(
        youtube_channel_id=yt_channel_id,
        title=(snippet.get("title") or "")[:255] or yt_channel_id,
        url=f"https://www.youtube.com/channel/{yt_channel_id}",
        custom_url=(snippet.get("customUrl") or "")[:255] or None,
        thumbnail_url=_pick_thumbnail(snippet),
        status="active",
        source="discovery",
        is_active=True,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def add_channel(db: Session, yt_channel_id: str) -> Channel:
    """Adiciona (ou retorna o existente) canal ao monitoramento."""
    return _get_or_create_channel_from_youtube(db, yt_channel_id)


def add_video(db: Session, yt_video_id: str) -> TrackedVideo:
    """
    Adiciona vídeo ao monitoramento. Resolve canal dono automaticamente e garante
    que o canal também esteja cadastrado.
    """
    client = youtube_client.build_from_db(db)
    videos = client.videos_by_ids([yt_video_id])
    if not videos:
        raise ValueError(f"Vídeo {yt_video_id} não encontrado no YouTube.")

    v = videos[0]
    snippet = v.get("snippet", {}) or {}
    yt_channel_id = snippet.get("channelId")
    if not yt_channel_id:
        raise ValueError(f"Vídeo {yt_video_id} sem channelId.")

    channel = _get_or_create_channel_from_youtube(db, yt_channel_id, client=client)

    existing = (
        db.query(TrackedVideo)
        .filter_by(channel_id=channel.id, youtube_video_id=yt_video_id)
        .one_or_none()
    )
    if existing:
        return existing

    tv = TrackedVideo(
        channel_id=channel.id,
        youtube_video_id=yt_video_id,
        title=(snippet.get("title") or "")[:512] or yt_video_id,
        url=f"https://www.youtube.com/watch?v={yt_video_id}",
        thumbnail_url=_pick_thumbnail(snippet),
        tracking_source="discovery",
        status="active",
        first_tracked_at=datetime.utcnow(),
    )
    db.add(tv)
    db.commit()
    db.refresh(tv)
    return tv


# =============================================================================
# Toggles de status (canal e vídeo)
# =============================================================================
def set_channel_status(db: Session, channel_id: int, status: str) -> Channel:
    """status: 'active' | 'paused' | 'removed'"""
    if status not in ("active", "paused", "removed"):
        raise ValueError(f"Status inválido: {status}")
    channel = db.query(Channel).filter_by(id=channel_id).one_or_none()
    if channel is None:
        raise LookupError(f"canal id={channel_id} não existe")
    channel.status = status
    channel.is_active = status == "active"
    db.commit()
    db.refresh(channel)
    return channel


def set_video_status(db: Session, video_id: int, status: str) -> TrackedVideo:
    """status: 'active' | 'paused' | 'removed'"""
    if status not in ("active", "paused", "removed"):
        raise ValueError(f"Status inválido: {status}")
    video = db.query(TrackedVideo).filter_by(id=video_id).one_or_none()
    if video is None:
        raise LookupError(f"vídeo id={video_id} não existe")
    video.status = status
    db.commit()
    db.refresh(video)
    return video


def delete_channel(db: Session, channel_id: int) -> None:
    """Remoção dura — cascata apaga snapshots, tracked_videos e channel_tags."""
    channel = db.query(Channel).filter_by(id=channel_id).one_or_none()
    if channel is None:
        raise LookupError(f"canal id={channel_id} não existe")
    db.delete(channel)
    db.commit()


def delete_video(db: Session, video_id: int) -> None:
    video = db.query(TrackedVideo).filter_by(id=video_id).one_or_none()
    if video is None:
        raise LookupError(f"vídeo id={video_id} não existe")
    db.delete(video)
    db.commit()


# =============================================================================
# Snapshots
# =============================================================================
def _pick_best_recent_upload(
    client: youtube_client.YouTubeClient, channel: Channel, sample_size: int
) -> Optional[dict]:
    """
    Pega os últimos `sample_size` uploads do canal (via playlistItems da uploads
    playlist), hidrata com statistics/contentDetails e retorna o vídeo com maior
    VPD. Retorna None se não houver uploads elegíveis.
    """
    playlist_id = client.uploads_playlist_id(channel.youtube_channel_id)
    items = client.playlist_items(playlist_id, max_results=sample_size)
    video_ids = [
        (i.get("contentDetails") or {}).get("videoId")
        for i in items
        if (i.get("contentDetails") or {}).get("videoId")
    ]
    if not video_ids:
        return None

    videos = client.videos_by_ids(video_ids)

    best = None
    best_vpd = -1.0
    for v in videos:
        stats = v.get("statistics") or {}
        snippet = v.get("snippet") or {}
        views = int(stats.get("viewCount", 0) or 0)
        published = parse_iso_dt(snippet.get("publishedAt", ""))
        vpd = compute_vpd(views, published)
        if vpd > best_vpd:
            best_vpd = vpd
            best = v
    return best


def _accumulate_best_video(
    db: Session, channel: Channel, best_video_item: Optional[dict]
) -> Optional[TrackedVideo]:
    """
    Se `best_video_item` é de fato um novo melhor (ainda não monitorado no canal),
    cria um TrackedVideo com tracking_source='best_from_channel'. Acumulativo:
    não remove antigos. Retorna o TrackedVideo criado, ou None se já existia ou
    não havia candidato.
    """
    if not best_video_item:
        return None
    yt_video_id = best_video_item.get("id")
    if not yt_video_id:
        return None

    existing = (
        db.query(TrackedVideo)
        .filter_by(channel_id=channel.id, youtube_video_id=yt_video_id)
        .one_or_none()
    )
    if existing:
        return None

    snippet = best_video_item.get("snippet", {}) or {}
    tv = TrackedVideo(
        channel_id=channel.id,
        youtube_video_id=yt_video_id,
        title=(snippet.get("title") or "")[:512] or yt_video_id,
        url=f"https://www.youtube.com/watch?v={yt_video_id}",
        thumbnail_url=_pick_thumbnail(snippet),
        tracking_source="best_from_channel",
        status="active",
        first_tracked_at=datetime.utcnow(),
    )
    db.add(tv)
    db.commit()
    db.refresh(tv)
    return tv


def _last_channel_snapshot(db: Session, channel_id: int) -> Optional[ChannelSnapshot]:
    return (
        db.query(ChannelSnapshot)
        .filter_by(channel_id=channel_id)
        .order_by(desc(ChannelSnapshot.captured_at))
        .first()
    )


def _uploads_per_week_from_tracked(db: Session, channel_id: int) -> Optional[float]:
    """
    Aproxima uploads/semana contando TrackedVideo.first_tracked_at nos últimos 30 dias.
    Sem custo de quota adicional — reaproveita o que o snapshot já detecta.
    """
    cutoff = datetime.utcnow() - timedelta(days=30)
    count = (
        db.query(TrackedVideo)
        .filter(TrackedVideo.channel_id == channel_id, TrackedVideo.first_tracked_at >= cutoff)
        .count()
    )
    if count == 0:
        return None
    return round(count / (30 / 7), 2)


def _classify_signal(
    *,
    subscribers: Optional[int],
    avg_vpd_recent: Optional[float],
    delta_subs: Optional[int],
    prev: Optional[ChannelSnapshot],
    vpd_saturation: int,
    promising_max_subs: int,
    promising_vpd_ratio: float,
) -> tuple[str, str]:
    """
    Retorna (signal, signal_reason).

    Ordem de precedência:
      1. saturated  — VPD médio > vpd_saturation (canal grande e consolidado).
      2. heating    — delta_subs crescente E avg_vpd crescente vs snapshot anterior.
      3. promising  — canal pequeno (< promising_max_subs) com VPD alto
                      (>= vpd_saturation * promising_vpd_ratio).
      4. stable     — demais.
    """
    vpd_promising_floor = vpd_saturation * promising_vpd_ratio

    if avg_vpd_recent is not None and avg_vpd_recent > vpd_saturation:
        return (
            "saturated",
            f"VPD médio {int(avg_vpd_recent)} acima da saturação ({vpd_saturation}).",
        )

    accelerating_subs = (
        prev is not None
        and prev.delta_subscribers is not None
        and delta_subs is not None
        and delta_subs > prev.delta_subscribers
    )
    accelerating_vpd = (
        prev is not None
        and prev.avg_vpd_recent is not None
        and avg_vpd_recent is not None
        and avg_vpd_recent > prev.avg_vpd_recent
    )
    if accelerating_subs and accelerating_vpd:
        return (
            "heating",
            "Inscritos e VPD acelerando vs snapshot anterior.",
        )

    if (
        subscribers is not None
        and subscribers < promising_max_subs
        and avg_vpd_recent is not None
        and avg_vpd_recent >= vpd_promising_floor
    ):
        return (
            "promising",
            f"Canal pequeno ({subscribers} subs) com VPD {int(avg_vpd_recent)} — candidato dark.",
        )

    return ("stable", "Sem variação relevante.")


def _last_video_snapshot(db: Session, tracked_video_id: int) -> Optional[VideoSnapshot]:
    return (
        db.query(VideoSnapshot)
        .filter_by(tracked_video_id=tracked_video_id)
        .order_by(desc(VideoSnapshot.captured_at))
        .first()
    )


def snapshot_channel(db: Session, channel_id: int, sample_size: int = 10) -> ChannelSnapshot:
    """
    Puxa estado atual do canal no YouTube + detecta melhor vídeo dos últimos uploads
    (acumulativo) + grava ChannelSnapshot com deltas vs último snapshot.

    Custo de quota:
      - channels.list: 1
      - playlistItems: 1
      - videos.list: 1
      Total ~3 units por canal.
    """
    channel = db.query(Channel).filter_by(id=channel_id).one_or_none()
    if channel is None:
        raise LookupError(f"canal id={channel_id} não existe")

    client = youtube_client.build_from_db(db)

    # 1) estado atual do canal
    ch_items = client.channels_by_ids([channel.youtube_channel_id])
    if not ch_items:
        raise ValueError(f"Canal {channel.youtube_channel_id} não encontrado no YouTube.")
    c = ch_items[0]
    stats = c.get("statistics") or {}
    subscribers = None
    if not stats.get("hiddenSubscriberCount"):
        subscribers = int(stats.get("subscriberCount", 0) or 0)
    views_total = int(stats.get("viewCount", 0) or 0)
    video_count = int(stats.get("videoCount", 0) or 0)

    # Atualiza thumbnail (canal pode trocar avatar) — sem custo de quota extra,
    # já temos os dados do channels.list aqui.
    new_thumb = _pick_thumbnail(c.get("snippet") or {})
    if new_thumb and new_thumb != channel.thumbnail_url:
        channel.thumbnail_url = new_thumb

    # 2) melhor upload recente (pode ser o mesmo de snapshot anterior — não duplica)
    best = _pick_best_recent_upload(client, channel, sample_size)
    _accumulate_best_video(db, channel, best)

    # 3) deltas vs último snapshot
    prev = _last_channel_snapshot(db, channel.id)
    delta_subs = None
    delta_views = None
    if prev is not None:
        if subscribers is not None and prev.subscribers is not None:
            delta_subs = subscribers - prev.subscribers
        if prev.views_total is not None:
            delta_views = views_total - prev.views_total

    avg_vpd_recent = None
    if best is not None:
        bs = best.get("statistics") or {}
        bsn = best.get("snippet") or {}
        avg_vpd_recent = compute_vpd(
            int(bs.get("viewCount", 0) or 0),
            parse_iso_dt(bsn.get("publishedAt", "")),
        )

    # 4) campos analíticos: tendência de VPD, uploads/sem, signal
    vpd_trend = None
    delta_avg_vpd = None
    if avg_vpd_recent is not None and prev is not None and prev.avg_vpd_recent is not None:
        delta_avg_vpd = avg_vpd_recent - prev.avg_vpd_recent
        vpd_trend = delta_avg_vpd

    uploads_per_week = _uploads_per_week_from_tracked(db, channel.id)

    vpd_saturation = settings_reader.get_int(db, "channel.vpd_saturation", 100000)
    promising_max_subs = settings_reader.get_int(
        db, "analytics.promising_max_subscribers", 50000
    )
    promising_vpd_ratio = settings_reader.get_float(
        db, "analytics.promising_vpd_ratio", 0.3
    )

    signal, signal_reason = _classify_signal(
        subscribers=subscribers,
        avg_vpd_recent=avg_vpd_recent,
        delta_subs=delta_subs,
        prev=prev,
        vpd_saturation=vpd_saturation,
        promising_max_subs=promising_max_subs,
        promising_vpd_ratio=promising_vpd_ratio,
    )

    snap = ChannelSnapshot(
        channel_id=channel.id,
        subscribers=subscribers,
        views_total=views_total,
        video_count=video_count,
        uploads_per_week=uploads_per_week,
        avg_vpd_recent=avg_vpd_recent,
        vpd_trend=vpd_trend,
        delta_subscribers=delta_subs,
        delta_views_total=delta_views,
        delta_avg_vpd=delta_avg_vpd,
        signal=signal,
        signal_reason=signal_reason,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def snapshot_video(db: Session, tracked_video_id: int) -> VideoSnapshot:
    """
    Puxa estado atual do vídeo no YouTube e grava VideoSnapshot com deltas.
    Também atualiza TrackedVideo.last_seen_* para leitura rápida.
    """
    tv = db.query(TrackedVideo).filter_by(id=tracked_video_id).one_or_none()
    if tv is None:
        raise LookupError(f"vídeo id={tracked_video_id} não existe")

    client = youtube_client.build_from_db(db)
    items = client.videos_by_ids([tv.youtube_video_id])
    if not items:
        raise ValueError(f"Vídeo {tv.youtube_video_id} não encontrado no YouTube.")
    v = items[0]
    stats = v.get("statistics") or {}
    snippet = v.get("snippet") or {}

    views = int(stats.get("viewCount", 0) or 0)
    likes = int(stats.get("likeCount", 0)) if stats.get("likeCount") else None
    comments = int(stats.get("commentCount", 0)) if stats.get("commentCount") else None

    published = parse_iso_dt(snippet.get("publishedAt", ""))
    vpd = compute_vpd(views, published)

    prev = _last_video_snapshot(db, tv.id)
    delta_views = views - prev.views if (prev and prev.views is not None) else None
    delta_likes = None
    if likes is not None and prev and prev.likes is not None:
        delta_likes = likes - prev.likes
    delta_comments = None
    if comments is not None and prev and prev.comments is not None:
        delta_comments = comments - prev.comments

    snap = VideoSnapshot(
        tracked_video_id=tv.id,
        views=views,
        likes=likes,
        comments=comments,
        vpd=vpd,
        delta_views=delta_views,
        delta_likes=delta_likes,
        delta_comments=delta_comments,
    )
    db.add(snap)

    # Atualiza campos de leitura rápida no TrackedVideo
    tv.last_seen_views = views
    tv.last_seen_vpd = vpd
    tv.last_seen_at = datetime.utcnow()
    if tv.first_tracked_vpd is None:
        tv.first_tracked_vpd = vpd
    new_thumb = _pick_thumbnail(snippet)
    if new_thumb and new_thumb != tv.thumbnail_url:
        tv.thumbnail_url = new_thumb

    db.commit()
    db.refresh(snap)
    return snap


# =============================================================================
# Helpers de leitura (para UI)
# =============================================================================
def list_best_videos_for_channel(db: Session, channel_id: int) -> list[TrackedVideo]:
    """Vídeos que foram detectados como 'melhor' num snapshot do canal (acumulativo)."""
    return (
        db.query(TrackedVideo)
        .filter_by(channel_id=channel_id, tracking_source="best_from_channel")
        .order_by(desc(TrackedVideo.first_tracked_at))
        .all()
    )
