"""
Discovery service — busca canais/vídeos no YouTube, aplica filtros básicos,
persiste DiscoveryRun + DiscoveryResultChannel/Video.

MVP enxuto (Fase 3):
  - Filtros suportados: janela (dias), views mínimas, VPD mínimo, duração
    mínima, idiomas, páginas por termo.
  - Não faz scoring composto (Fase 6), nem mutação de termos, nem related,
    nem trending — esses ficam para fases posteriores.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    ChannelBlacklist,
    DiscoveryResultChannel,
    DiscoveryResultVideo,
    DiscoveryRun,
)
from app.services import settings_reader, youtube_client


def get_blacklisted_channel_ids(db: Session) -> set[str]:
    """IDs de canal na blacklist — usado para descartar resultados."""
    rows = db.query(ChannelBlacklist.youtube_channel_id).all()
    return {r[0] for r in rows}


def build_video_thumbnail_url(youtube_video_id: str | None) -> Optional[str]:
    """Thumbnail previsivel de video quando a API nao vier com uma melhor."""
    if not youtube_video_id:
        return None
    return f"https://i.ytimg.com/vi/{youtube_video_id}/hqdefault.jpg"


@dataclass
class DiscoveryFilters:
    terms: list[str]
    window_days: int
    min_views: int
    min_vpd: int
    min_duration_seconds: int
    languages: list[str]
    pages_per_term: int
    # Janela de idade do CANAL (não do vídeo). Canais cuja idade em dias está
    # fora de [min_channel_age_days, max_channel_age_days] são descartados
    # junto com seus vídeos. None em qualquer um dos dois desliga o limite
    # correspondente.
    min_channel_age_days: Optional[int] = None
    max_channel_age_days: Optional[int] = None


# =============================================================================
# Utilitários
# =============================================================================
_ISO_DURATION_RE = re.compile(
    r"PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?"
)


def parse_iso8601_duration(s: str) -> int:
    """PT1H2M3S -> segundos. Retorna 0 se não parsear."""
    if not s:
        return 0
    m = _ISO_DURATION_RE.fullmatch(s)
    if not m:
        return 0
    h = int(m.group("h") or 0)
    mi = int(m.group("m") or 0)
    se = int(m.group("s") or 0)
    return h * 3600 + mi * 60 + se


def parse_iso_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_vpd(views: int, published_at: Optional[datetime]) -> float:
    """Views per day desde a publicação. Mínimo 1 dia pra evitar /0."""
    if not published_at or views <= 0:
        return 0.0
    age = datetime.now(timezone.utc) - published_at
    days = max(age.total_seconds() / 86400.0, 1.0)
    return round(views / days, 2)


def pick_thumbnail(snippet: dict) -> Optional[str]:
    """Pega a maior thumbnail disponivel de um snippet do YouTube."""
    if not isinstance(snippet, dict):
        return None
    thumbs = snippet.get("thumbnails") or {}
    for key in ("high", "medium", "default"):
        item = thumbs.get(key)
        if isinstance(item, dict) and item.get("url"):
            return str(item["url"])[:512]
    return None


def _filter_channels_by_age(
    channels_by_id: dict,
    min_age_days: Optional[int],
    max_age_days: Optional[int],
) -> set[str]:
    """
    Devolve o conjunto de channel_ids que passam no filtro de idade.

    Regra: idade do canal = (agora UTC) - snippet.publishedAt, em dias.
    O canal é aceito quando `min_age_days <= idade <= max_age_days`.
    Se um dos limites for None, ele é ignorado (sem corte naquele lado).
    Canal sem `publishedAt` é mantido — não temos como avaliar e descartar
    seria perder cobertura à toa.
    """
    if min_age_days is None and max_age_days is None:
        return set(channels_by_id.keys())

    now = datetime.now(timezone.utc)
    accepted: set[str] = set()
    for cid, channel in channels_by_id.items():
        snippet = (channel.get("snippet") or {}) if isinstance(channel, dict) else {}
        published = parse_iso_dt(snippet.get("publishedAt") or "")
        if published is None:
            accepted.add(cid)
            continue
        age_days = (now - published).total_seconds() / 86400.0
        if min_age_days is not None and age_days < min_age_days:
            continue
        if max_age_days is not None and age_days > max_age_days:
            continue
        accepted.add(cid)
    return accepted


def load_default_filters(db: Session) -> dict:
    """Lê defaults das app_settings para usar como fallback na UI."""
    return {
        "window_days": settings_reader.get_int(db, "search.window_days", 14),
        "min_views": settings_reader.get_int(db, "search.min_views", 5000),
        "min_vpd": settings_reader.get_int(db, "search.min_vpd", 500),
        "min_duration_seconds": settings_reader.get_int(db, "search.min_duration_seconds", 60),
        "languages": settings_reader.get_csv(db, "search.languages", ["pt", "en", "es"]),
        "pages_per_term": settings_reader.get_int(db, "search.pages_per_term", 2),
        "min_channel_age_days": settings_reader.get_int(db, "channel.min_age_days", 30),
        "max_channel_age_days": settings_reader.get_int(db, "channel.max_age_days", 3650),
    }


# =============================================================================
# Execução
# =============================================================================
def run_discovery(db: Session, filters: DiscoveryFilters) -> DiscoveryRun:
    """
    Executa uma descoberta síncrona. Persiste a DiscoveryRun no início (status=running),
    grava resultados, fecha como success/failed.
    """
    run = DiscoveryRun(
        terms=", ".join(filters.terms),
        filters_json=json.dumps(
            {
                "window_days": filters.window_days,
                "min_views": filters.min_views,
                "min_vpd": filters.min_vpd,
                "min_duration_seconds": filters.min_duration_seconds,
                "languages": filters.languages,
                "pages_per_term": filters.pages_per_term,
                "min_channel_age_days": filters.min_channel_age_days,
                "max_channel_age_days": filters.max_channel_age_days,
            }
        ),
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        client = youtube_client.build_from_db(db)

        published_after = datetime.now(timezone.utc) - timedelta(days=filters.window_days)
        published_after_iso = published_after.strftime("%Y-%m-%dT%H:%M:%SZ")

        # 1) busca vídeos por termo × idioma
        video_ids: list[str] = []
        video_term_map: dict[str, str] = {}
        for term in filters.terms:
            for lang in filters.languages or [None]:
                page_token: Optional[str] = None
                for _ in range(max(filters.pages_per_term, 1)):
                    data = client.search_videos(
                        query=term,
                        published_after_iso=published_after_iso,
                        language=lang,
                        max_results=50,
                        page_token=page_token,
                    )
                    for item in data.get("items", []):
                        vid = item.get("id", {}).get("videoId")
                        if vid and vid not in video_term_map:
                            video_ids.append(vid)
                            video_term_map[vid] = term
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break

        # 2) hidrata vídeos (stats + duração)
        videos = client.videos_by_ids(video_ids) if video_ids else []

        # 3) filtra e coleta channel IDs únicos (excluindo blacklist)
        blacklist = get_blacklisted_channel_ids(db)
        filtered_videos: list[tuple[dict, str]] = []  # (video_item, matched_term)
        channel_ids_seen: set[str] = set()
        for v in videos:
            vid = v.get("id")
            snippet = v.get("snippet", {}) or {}
            stats = v.get("statistics", {}) or {}
            content = v.get("contentDetails", {}) or {}

            views = int(stats.get("viewCount", 0) or 0)
            duration_s = parse_iso8601_duration(content.get("duration", ""))
            published_at = parse_iso_dt(snippet.get("publishedAt", ""))
            vpd = compute_vpd(views, published_at)

            if views < filters.min_views:
                continue
            if duration_s < filters.min_duration_seconds:
                continue
            if vpd < filters.min_vpd:
                continue

            ch_id = snippet.get("channelId")
            if ch_id and ch_id in blacklist:
                continue
            if ch_id:
                channel_ids_seen.add(ch_id)

            filtered_videos.append((v, video_term_map.get(vid, "")))

        # 4) hidrata canais únicos (blacklist já foi filtrada acima)
        channels = client.channels_by_ids(list(channel_ids_seen)) if channel_ids_seen else []
        channels_by_id = {c.get("id"): c for c in channels}

        # 4.1) filtro de idade do CANAL — descarta canais fora da janela
        # [min_channel_age_days, max_channel_age_days] e tudo que veio deles.
        # Canal sem `publishedAt` (raro) é mantido pra não perder cobertura.
        accepted_channel_ids = _filter_channels_by_age(
            channels_by_id,
            min_age_days=filters.min_channel_age_days,
            max_age_days=filters.max_channel_age_days,
        )
        channels_by_id = {
            cid: c for cid, c in channels_by_id.items() if cid in accepted_channel_ids
        }
        filtered_videos = [
            (v, term)
            for v, term in filtered_videos
            if (v.get("snippet", {}) or {}).get("channelId") in accepted_channel_ids
        ]

        # 5) persiste video results
        for v, matched_term in filtered_videos:
            snippet = v.get("snippet", {}) or {}
            stats = v.get("statistics", {}) or {}
            content = v.get("contentDetails", {}) or {}
            views = int(stats.get("viewCount", 0) or 0)
            likes = int(stats.get("likeCount", 0) or 0) if stats.get("likeCount") else None
            duration_s = parse_iso8601_duration(content.get("duration", ""))
            published_at = parse_iso_dt(snippet.get("publishedAt", ""))
            vpd = compute_vpd(views, published_at)

            db.add(
                DiscoveryResultVideo(
                    run_id=run.id,
                    youtube_video_id=v.get("id"),
                    youtube_channel_id=snippet.get("channelId"),
                    title=(snippet.get("title") or "")[:512],
                    url=f"https://www.youtube.com/watch?v={v.get('id')}",
                    thumbnail_url=pick_thumbnail(snippet) or build_video_thumbnail_url(v.get("id")),
                    views=views,
                    likes=likes,
                    duration_seconds=duration_s,
                    published_at=published_at.replace(tzinfo=None) if published_at else None,
                    vpd=vpd,
                    matched_term=matched_term[:255] if matched_term else None,
                )
            )

        # 6) persiste channel results (um por canal único encontrado)
        for ch_id, c in channels_by_id.items():
            c_snippet = c.get("snippet", {}) or {}
            c_stats = c.get("statistics", {}) or {}
            subs = int(c_stats.get("subscriberCount", 0) or 0) if not c_stats.get("hiddenSubscriberCount") else None
            views_total = int(c_stats.get("viewCount", 0) or 0)
            video_count = int(c_stats.get("videoCount", 0) or 0)
            channel_published_at = parse_iso_dt(c_snippet.get("publishedAt", ""))

            db.add(
                DiscoveryResultChannel(
                    run_id=run.id,
                    youtube_channel_id=ch_id,
                    title=(c_snippet.get("title") or "")[:255],
                    url=f"https://www.youtube.com/channel/{ch_id}",
                    thumbnail_url=pick_thumbnail(c_snippet),
                    subscribers=subs,
                    views_total=views_total,
                    video_count=video_count,
                    channel_published_at=(
                        channel_published_at.replace(tzinfo=None)
                        if channel_published_at
                        else None
                    ),
                )
            )

        run.channels_found = len(channels_by_id)
        run.videos_found = len(filtered_videos)
        run.status = "success"
        run.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
        return run

    except Exception as exc:
        run.status = "failed"
        run.notes = str(exc)[:2000]
        run.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
        raise
