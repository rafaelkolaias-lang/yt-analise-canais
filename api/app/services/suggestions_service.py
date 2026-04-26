"""
Suggestions service — recomendações de monitoramento (sem ação automática).

Duas listas:
  - to_monitor: canais descobertos (em discovery_results_channels) que ainda
    NÃO estão monitorados, atendem critérios de "vale a pena monitorar"
    (VPD recente alto E canal jovem). Filtra blacklist.
  - to_remove: canais JÁ monitorados que parecem mortos (regra composta:
    sem uploads recentes E VPD baixo E sinal estagnado). Recomendação
    apenas — o sistema NÃO remove sozinho.

Thresholds editáveis em /configuracoes (prefixo `suggestions.*`).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, desc, func, not_
from sqlalchemy.orm import Session

from app.models import (
    Channel,
    ChannelBlacklist,
    ChannelSnapshot,
    DiscoveryResultChannel,
    TrackedVideo,
)
from app.services import settings_reader


# =============================================================================
# Sugestões: canais para MONITORAR
# =============================================================================
def list_monitor_suggestions(db: Session, limit: int = 100) -> list[dict]:
    """
    Canais em discovery_results_channels que:
      - NÃO estão na tabela `channels` (ainda não monitorados)
      - NÃO estão na blacklist
      - têm VPD recente >= `suggestions.monitor_min_vpd`
      - têm idade <= `suggestions.monitor_max_age_days` (channel_published_at)

    Como o mesmo `youtube_channel_id` pode aparecer em vários runs, escolhe
    o registro mais recente (`MAX(captured_at)`). Resultado ordenado por
    VPD desc.
    """
    min_vpd = settings_reader.get_int(db, "suggestions.monitor_min_vpd", 10000)
    max_age_days = settings_reader.get_int(db, "suggestions.monitor_max_age_days", 60)

    cutoff_age = datetime.utcnow() - timedelta(days=max_age_days)

    # Subquery: canais já monitorados (qualquer status, inclusive paused/removed
    # — quem foi removido entra na blacklist e cai no filtro abaixo).
    monitored_ids = db.query(Channel.youtube_channel_id).subquery()
    blacklisted_ids = db.query(ChannelBlacklist.youtube_channel_id).subquery()

    # Pega o último registro de cada `youtube_channel_id` em
    # discovery_results_channels (pode ter sido descoberto em vários runs).
    latest_per_yt_id = (
        db.query(
            DiscoveryResultChannel.youtube_channel_id.label("yt_id"),
            func.max(DiscoveryResultChannel.captured_at).label("max_at"),
        )
        .group_by(DiscoveryResultChannel.youtube_channel_id)
        .subquery()
    )

    rows = (
        db.query(DiscoveryResultChannel)
        .join(
            latest_per_yt_id,
            and_(
                DiscoveryResultChannel.youtube_channel_id == latest_per_yt_id.c.yt_id,
                DiscoveryResultChannel.captured_at == latest_per_yt_id.c.max_at,
            ),
        )
        .filter(
            not_(DiscoveryResultChannel.youtube_channel_id.in_(monitored_ids)),
            not_(DiscoveryResultChannel.youtube_channel_id.in_(blacklisted_ids)),
            DiscoveryResultChannel.avg_vpd_recent.isnot(None),
            DiscoveryResultChannel.avg_vpd_recent >= min_vpd,
            DiscoveryResultChannel.channel_published_at.isnot(None),
            DiscoveryResultChannel.channel_published_at >= cutoff_age,
        )
        .order_by(desc(DiscoveryResultChannel.avg_vpd_recent))
        .limit(limit)
        .all()
    )

    return [
        {
            "youtube_channel_id": r.youtube_channel_id,
            "title": r.title,
            "url": r.url,
            "subscribers": r.subscribers,
            "video_count": r.video_count,
            "avg_vpd_recent": r.avg_vpd_recent,
            "channel_published_at": (
                r.channel_published_at.isoformat() if r.channel_published_at else None
            ),
            "discovery_result_id": r.id,
            "matched_term": r.matched_term,
            # Razão legível para o card.
            "reason": (
                f"VPD {int(r.avg_vpd_recent)} ≥ {min_vpd} · "
                f"canal com {_age_days(r.channel_published_at)}d de idade"
            ),
        }
        for r in rows
    ]


def _age_days(dt: Optional[datetime]) -> int:
    if dt is None:
        return 0
    return max(0, (datetime.utcnow() - dt).days)


# =============================================================================
# Sugestões: canais MONITORADOS para REMOVER (mortos)
# =============================================================================
def list_dead_suggestions(db: Session, limit: int = 100) -> list[dict]:
    """
    Canais já monitorados que parecem mortos. Regra composta (TODAS valem):
      - sem novos TrackedVideo há >= `suggestions.dead_min_days_no_uploads`
      - último ChannelSnapshot.avg_vpd_recent <= `suggestions.dead_max_vpd`
      - último ChannelSnapshot.signal in ("stable", "unknown", NULL)

    Canais sem nenhum snapshot são ignorados (não temos sinal pra julgar).
    Recomendação apenas — caller decide se pausa/remove.
    """
    min_days_no_uploads = settings_reader.get_int(
        db, "suggestions.dead_min_days_no_uploads", 60
    )
    max_vpd = settings_reader.get_int(db, "suggestions.dead_max_vpd", 2000)

    cutoff_uploads = datetime.utcnow() - timedelta(days=min_days_no_uploads)

    # Último ChannelSnapshot por canal.
    latest_snap = (
        db.query(
            ChannelSnapshot.channel_id.label("ch_id"),
            func.max(ChannelSnapshot.captured_at).label("max_at"),
        )
        .group_by(ChannelSnapshot.channel_id)
        .subquery()
    )

    # Último upload (TrackedVideo.first_tracked_at) por canal.
    latest_upload = (
        db.query(
            TrackedVideo.channel_id.label("ch_id"),
            func.max(TrackedVideo.first_tracked_at).label("max_upload"),
        )
        .group_by(TrackedVideo.channel_id)
        .subquery()
    )

    candidates = (
        db.query(Channel, ChannelSnapshot, latest_upload.c.max_upload)
        .join(latest_snap, Channel.id == latest_snap.c.ch_id)
        .join(
            ChannelSnapshot,
            and_(
                ChannelSnapshot.channel_id == latest_snap.c.ch_id,
                ChannelSnapshot.captured_at == latest_snap.c.max_at,
            ),
        )
        .outerjoin(latest_upload, latest_upload.c.ch_id == Channel.id)
        .filter(Channel.status == "active")
        .all()
    )

    out: list[dict] = []
    for channel, last_snap, last_upload_at in candidates:
        # Regra 1: sem uploads recentes (NULL = nunca teve upload tracked,
        # também conta como "sem upload recente").
        if last_upload_at is not None and last_upload_at > cutoff_uploads:
            continue

        # Regra 2: VPD baixo.
        if last_snap.avg_vpd_recent is None or last_snap.avg_vpd_recent > max_vpd:
            continue

        # Regra 3: sinal estagnado/desconhecido.
        if last_snap.signal not in (None, "stable", "unknown"):
            continue

        days_since_upload = (
            (datetime.utcnow() - last_upload_at).days
            if last_upload_at is not None
            else None
        )

        out.append(
            {
                "channel_id": channel.id,
                "youtube_channel_id": channel.youtube_channel_id,
                "title": channel.title,
                "url": channel.url,
                "thumbnail_url": channel.thumbnail_url,
                "status": channel.status,
                "last_snapshot_at": (
                    last_snap.captured_at.isoformat() if last_snap.captured_at else None
                ),
                "last_upload_at": (
                    last_upload_at.isoformat() if last_upload_at else None
                ),
                "days_since_last_upload": days_since_upload,
                "avg_vpd_recent": last_snap.avg_vpd_recent,
                "signal": last_snap.signal,
                "reason": _dead_reason(
                    days_since_upload,
                    last_snap.avg_vpd_recent,
                    last_snap.signal,
                    max_vpd,
                ),
            }
        )

    # Ordena por "mais morto primeiro": VPD ascendente, dias-sem-upload desc.
    out.sort(
        key=lambda x: (
            x["avg_vpd_recent"] or 0,
            -(x["days_since_last_upload"] or 0),
        )
    )
    return out[:limit]


def _dead_reason(
    days_since_upload: Optional[int],
    vpd: Optional[float],
    signal: Optional[str],
    max_vpd: int,
) -> str:
    upload_part = (
        f"{days_since_upload}d sem upload"
        if days_since_upload is not None
        else "sem uploads tracked"
    )
    vpd_part = f"VPD {int(vpd or 0)} ≤ {max_vpd}"
    signal_part = f"sinal '{signal or 'desconhecido'}'"
    return f"{upload_part} · {vpd_part} · {signal_part}"
