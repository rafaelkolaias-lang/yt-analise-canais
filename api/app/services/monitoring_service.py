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

import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import (
    Channel,
    ChannelBlacklist,
    ChannelSnapshot,
    TrackedVideo,
    VideoSnapshot,
)
from app.services import settings_reader, youtube_client
from app.services.discovery_service import (
    build_video_thumbnail_url,
    compute_vpd,
    parse_iso_dt,
    parse_iso8601_duration,
    pick_thumbnail,
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


class PermanentlyUnavailableError(RuntimeError):
    """Item tratado como indisponivel permanente e removido do retry."""


class ChannelUnavailableError(PermanentlyUnavailableError):
    pass


class VideoUnavailableError(PermanentlyUnavailableError):
    pass


def _upsert_blacklist(db: Session, youtube_channel_id: str, reason: str) -> None:
    existing = (
        db.query(ChannelBlacklist).filter_by(youtube_channel_id=youtube_channel_id).one_or_none()
    )
    if existing is None:
        db.add(ChannelBlacklist(youtube_channel_id=youtube_channel_id, reason=reason))
    elif not existing.reason:
        existing.reason = reason


def _remove_from_blacklist(db: Session, youtube_channel_id: str) -> bool:
    """
    Remove o canal da blacklist se estiver lá. Usado quando o usuário decide
    EXPLICITAMENTE re-monitorar um canal que havia removido — senão ele ficaria
    "monitorado E na blacklist" ao mesmo tempo (a descoberta automática
    continuaria tratando como banido). Retorna True se removeu algo.
    """
    row = (
        db.query(ChannelBlacklist)
        .filter_by(youtube_channel_id=youtube_channel_id)
        .one_or_none()
    )
    if row is None:
        return False
    db.delete(row)
    return True


def _mark_channel_unavailable(db: Session, channel: Channel, reason: str) -> str:
    message = (
        f"Canal indisponivel/removido no YouTube. "
        f"Canal: {channel.title}. URL: {channel.url or '-'} . "
        f"ID: {channel.youtube_channel_id}. Motivo: {reason}"
    )[:2000]
    channel.status = "removed"
    channel.is_active = False
    channel.notes = message
    _upsert_blacklist(db, channel.youtube_channel_id, "youtube_unavailable")
    for tracked in channel.tracked_videos:
        tracked.status = "removed"
        tracked.unavailable_reason = "channel_unavailable"
        tracked.unavailable_since = datetime.utcnow()
    db.commit()
    return message


def _mark_video_unavailable(db: Session, video: TrackedVideo, reason: str) -> str:
    message = (
        f"Video indisponivel/removido no YouTube. "
        f"Canal: {video.channel.title if video.channel else '-'} . "
        f"URL: {video.url or '-'} . "
        f"ID: {video.youtube_video_id}. Motivo: {reason}"
    )[:2000]
    video.status = "removed"
    video.unavailable_reason = "video_unavailable"
    video.unavailable_since = datetime.utcnow()
    db.commit()
    return message


def _get_or_create_channel_from_youtube(
    db: Session, yt_channel_id: str, client: Optional[youtube_client.YouTubeClient] = None
) -> Channel:
    existing = db.query(Channel).filter_by(youtube_channel_id=yt_channel_id).one_or_none()
    if existing:
        # Re-monitorar explicitamente um canal que estava na blacklist deve
        # tirá-lo de lá (estado coerente).
        if _remove_from_blacklist(db, yt_channel_id):
            db.commit()
        return existing

    yt_client = client or youtube_client.build_from_db(db)
    items = yt_client.channels_by_ids([yt_channel_id])
    if not items:
        raise ChannelUnavailableError(
            f"Canal {yt_channel_id} indisponivel no YouTube ao tentar cadastrar."
        )
    c = items[0]
    snippet = c.get("snippet", {}) or {}

    channel = Channel(
        youtube_channel_id=yt_channel_id,
        title=(snippet.get("title") or "")[:255] or yt_channel_id,
        url=f"https://www.youtube.com/channel/{yt_channel_id}",
        custom_url=(snippet.get("customUrl") or "")[:255] or None,
        thumbnail_url=pick_thumbnail(snippet),
        status="active",
        source="discovery",
        is_active=True,
    )
    db.add(channel)
    # Saindo da blacklist no mesmo commit (caso o canal tenha sido removido antes).
    _remove_from_blacklist(db, yt_channel_id)
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
        raise VideoUnavailableError(
            f"Video {yt_video_id} indisponivel no YouTube ao tentar cadastrar."
        )
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
        thumbnail_url=pick_thumbnail(snippet) or build_video_thumbnail_url(yt_video_id),
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
    """
    Remoção dura — cascata apaga snapshots, tracked_videos e channel_tags.

    Adicionalmente registra o canal na blacklist (idempotente) para que a
    descoberta automática não o reaceite. Se o usuário quiser voltar a
    monitorar, deve remover da blacklist explicitamente (UI futura ou
    direto na tabela).
    """
    channel = db.query(Channel).filter_by(id=channel_id).one_or_none()
    if channel is None:
        raise LookupError(f"canal id={channel_id} não existe")

    yt_id = channel.youtube_channel_id
    db.delete(channel)

    _upsert_blacklist(db, yt_id, "user_removed")

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
def _recent_upload_metrics(
    client: youtube_client.YouTubeClient,
    channel: Channel,
    sample_size: int,
    weekly_window_days: int = 30,
) -> tuple[Optional[dict], Optional[float]]:
    """
    Usa a uploads playlist do canal para calcular duas métricas com a mesma
    leitura da API:
      - melhor vídeo recente (maior VPD entre os uploads amostrados)
      - uploads/semana real, baseado em quantos uploads o canal publicou nos
        últimos `weekly_window_days`

    Como playlistItems e videos.list custam 1 unit cada até 50 itens, buscamos
    até 50 uploads recentes de uma vez e reaproveitamos o mesmo lote para ambas
    as métricas.
    """
    playlist_id = client.uploads_playlist_id(channel.youtube_channel_id)
    items = client.playlist_items(playlist_id, max_results=max(sample_size, 50))
    video_ids = [
        (i.get("contentDetails") or {}).get("videoId")
        for i in items
        if (i.get("contentDetails") or {}).get("videoId")
    ]
    if not video_ids:
        return (None, None)

    videos = client.videos_by_ids(video_ids)
    # `published` vem tz-aware do parse_iso_dt (`...Z` -> +00:00). Usamos
    # `datetime.now(timezone.utc)` aqui para o cutoff tambem ser tz-aware,
    # caso contrario `published >= cutoff` quebra com "can't compare
    # offset-naive and offset-aware datetimes" e o snapshot do canal falha.
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=weekly_window_days)

    best = None
    best_vpd = -1.0
    uploads_in_window = 0
    for v in videos:
        stats = v.get("statistics") or {}
        snippet = v.get("snippet") or {}
        views = int(stats.get("viewCount", 0) or 0)
        published = parse_iso_dt(snippet.get("publishedAt", ""))
        if published is not None and published >= cutoff:
          uploads_in_window += 1
        vpd = compute_vpd(views, published)
        if vpd > best_vpd:
            best_vpd = vpd
            best = v
    uploads_per_week = None
    if uploads_in_window > 0:
        uploads_per_week = round(uploads_in_window / (weekly_window_days / 7), 2)
    return (best, uploads_per_week)


def _accumulate_best_video(
    db: Session, channel: Channel, best_video_item: Optional[dict]
) -> Optional[TrackedVideo]:
    """
    Se `best_video_item` é de fato um novo melhor (ainda não monitorado no canal),
    cria um TrackedVideo com tracking_source='best_from_channel'. Acumulativo:
    não remove antigos. Retorna o TrackedVideo criado, ou None se já existia ou
    não havia candidato.

    NÃO comita: apenas faz `db.add`. O commit é responsabilidade do
    `snapshot_channel`, que grava best-video + thumbnail + snapshot do canal
    numa ÚNICA transação (atomicidade — evita best-video/thumbnail salvos sem
    o snapshot da rodada quando a coleta falha no meio).
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
        thumbnail_url=pick_thumbnail(snippet) or build_video_thumbnail_url(yt_video_id),
        tracking_source="best_from_channel",
        status="active",
        first_tracked_at=datetime.utcnow(),
    )
    db.add(tv)
    return tv


def _last_channel_snapshot(db: Session, channel_id: int) -> Optional[ChannelSnapshot]:
    return (
        db.query(ChannelSnapshot)
        .filter_by(channel_id=channel_id)
        .order_by(desc(ChannelSnapshot.captured_at))
        .first()
    )


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


def snapshot_channel(
    db: Session,
    channel_id: int,
    sample_size: Optional[int] = None,
    client: Optional[youtube_client.YouTubeClient] = None,
) -> ChannelSnapshot:
    """
    Puxa estado atual do canal no YouTube + detecta melhor vídeo dos últimos uploads
    (acumulativo) + grava ChannelSnapshot com deltas vs último snapshot.

    Custo de quota:
      - channels.list: 1
      - playlistItems: 1
      - videos.list: 1
      Total ~3 units por canal.

    `sample_size`: quantos uploads recentes usar como amostra para detectar o
    melhor VPD e calcular `uploads_per_week`. Quando None (padrão), lê de
    `app_settings.monitor.best_videos_sample_size` (default 10). Permite
    overide explícito por chamadores que queiram outra janela.
    """
    channel = db.query(Channel).filter_by(id=channel_id).one_or_none()
    if channel is None:
        raise LookupError(f"canal id={channel_id} não existe")

    if sample_size is None:
        sample_size = settings_reader.get_int(db, "monitor.best_videos_sample_size", 10)

    # Reusa o client passado pelo run de sync (1 por run) ou cria um próprio
    # quando chamado isoladamente (endpoint de snapshot individual).
    client = client or youtube_client.build_from_db(db)

    # 1) estado atual do canal
    ch_items = client.channels_by_ids([channel.youtube_channel_id])
    if not ch_items:
        raise ChannelUnavailableError(
            _mark_channel_unavailable(
                db,
                channel,
                "channels.list nao retornou o canal; provavelmente removido, privado ou inexistente.",
            )
        )
    c = ch_items[0]
    stats = c.get("statistics") or {}
    subscribers = None
    if not stats.get("hiddenSubscriberCount"):
        subscribers = int(stats.get("subscriberCount", 0) or 0)
    views_total = int(stats.get("viewCount", 0) or 0)
    video_count = int(stats.get("videoCount", 0) or 0)

    # Atualiza thumbnail (canal pode trocar avatar) — sem custo de quota extra,
    # já temos os dados do channels.list aqui.
    new_thumb = pick_thumbnail(c.get("snippet") or {})
    if new_thumb and new_thumb != channel.thumbnail_url:
        channel.thumbnail_url = new_thumb

    # 2) uploads recentes reais do canal (mesmo lote usado para "melhor vídeo"
    # e para a frequência semanal de uploads)
    best, uploads_per_week = _recent_upload_metrics(client, channel, sample_size)
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


def snapshot_video(
    db: Session,
    tracked_video_id: int,
    client: Optional[youtube_client.YouTubeClient] = None,
) -> VideoSnapshot:
    """
    Puxa estado atual do vídeo no YouTube e grava VideoSnapshot com deltas.
    Também atualiza TrackedVideo.last_seen_* para leitura rápida.
    """
    tv = db.query(TrackedVideo).filter_by(id=tracked_video_id).one_or_none()
    if tv is None:
        raise LookupError(f"vídeo id={tracked_video_id} não existe")

    client = client or youtube_client.build_from_db(db)
    items = client.videos_by_ids([tv.youtube_video_id])
    if not items:
        raise VideoUnavailableError(
            _mark_video_unavailable(
                db,
                tv,
                "videos.list nao retornou o video; provavelmente removido, privado ou inexistente.",
            )
        )
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
    new_thumb = pick_thumbnail(snippet) or build_video_thumbnail_url(tv.youtube_video_id)
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


def list_best_videos_for_channels(
    db: Session, channel_ids: list[int]
) -> list[TrackedVideo]:
    """
    Versao em lote do anterior: 1 unica query SQL com `IN (...)` para todos os
    canais. Retorna a lista plana ja ordenada por `first_tracked_at desc`; o
    caller agrupa por `channel_id`.
    """
    if not channel_ids:
        return []
    return (
        db.query(TrackedVideo)
        .filter(
            TrackedVideo.channel_id.in_(channel_ids),
            TrackedVideo.tracking_source == "best_from_channel",
        )
        .order_by(desc(TrackedVideo.first_tracked_at))
        .all()
    )


# =============================================================================
# Resolução de input do usuário (link ou ID) → tipo + youtube_id
# =============================================================================
ResolveKind = Literal["channel", "video"]

# UC + 22 chars (base64-url-safe), formato fixo do YouTube
_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
# Video ID: 11 chars (base64-url-safe sem padding)
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _extract_video_id(text: str) -> Optional[str]:
    """
    Extrai um youtube_video_id de uma URL ou retorna None.
    Aceita:
      - youtube.com/watch?v=ID[&...]
      - youtu.be/ID
      - youtube.com/shorts/ID
      - youtube.com/embed/ID
    """
    patterns = [
        r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def _extract_channel_id(text: str) -> Optional[str]:
    """Extrai um UC... de uma URL `youtube.com/channel/UC...` ou retorna None."""
    m = re.search(r"(?:youtube\.com/channel/)(UC[A-Za-z0-9_-]{22})", text)
    return m.group(1) if m else None


def _extract_handle(text: str) -> Optional[str]:
    """
    Extrai o handle (`@nome`) de uma URL `youtube.com/@nome` (sem `@` retornado).
    Também aceita variantes `/c/nome` e `/user/nome` (raras hoje, deprecadas
    mas válidas) — tentaremos resolver via handle.
    """
    m = re.search(r"youtube\.com/@([A-Za-z0-9._-]+)", text)
    if m:
        return m.group(1)
    m = re.search(r"youtube\.com/(?:c|user)/([A-Za-z0-9._-]+)", text)
    if m:
        return m.group(1)
    return None


def resolve_youtube_input(
    db: Session, raw: str
) -> tuple[ResolveKind, str]:
    """
    Recebe input do usuário (link ou ID) e devolve (kind, youtube_id) pronto
    para chamar add_channel/add_video. Levanta ValueError com mensagem
    amigável se não der pra resolver.

    Custo de quota:
      - ID puro ou URL com ID: 0 units (parsing local).
      - Handle (`@nome`, `/c/`, `/user/`): 1 unit (channels.list?forHandle).
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("Informe um link ou ID.")

    # 1) ID puro (canal ou vídeo)
    if _CHANNEL_ID_RE.match(text):
        return ("channel", text)
    if _VIDEO_ID_RE.match(text):
        return ("video", text)

    # 2) URL com vídeo embutido (watch, shorts, youtu.be, embed)
    vid = _extract_video_id(text)
    if vid:
        return ("video", vid)

    # 3) URL com /channel/UC...
    cid = _extract_channel_id(text)
    if cid:
        return ("channel", cid)

    # 4) URL com handle (@nome, /c/, /user/) — precisa resolver via API
    handle = _extract_handle(text)
    if handle:
        client = youtube_client.build_from_db(db)
        resolved = client.resolve_handle(handle)
        if resolved:
            return ("channel", resolved)
        raise ValueError(
            f"Handle '@{handle}' não encontrado no YouTube."
        )

    raise ValueError(
        "Formato não reconhecido. Cole um ID (UC... ou de vídeo), "
        "um link de vídeo (watch?v=, youtu.be, shorts) ou de canal "
        "(/channel/UC..., /@handle)."
    )
