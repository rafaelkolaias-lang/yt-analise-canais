"""
Suggestions service - recomendacoes para monitorar ou pausar/remover canais.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, desc, func, not_, select
from sqlalchemy.orm import Session

from app.models import (
    Channel,
    ChannelBlacklist,
    ChannelSnapshot,
    DiscoveryResultChannel,
    DiscoveryResultVideo,
    TrackedVideo,
)
from app.services import settings_reader


def list_monitor_suggestions(db: Session, limit: int = 100) -> list[dict]:
    min_vpd = settings_reader.get_int(db, "suggestions.monitor_min_vpd", 10000)
    max_age_days = settings_reader.get_int(db, "suggestions.monitor_max_age_days", 60)
    breakout_max_subscribers = settings_reader.get_int(
        db, "suggestions.monitor_breakout_max_subscribers", 10000
    )
    breakout_max_age_days = settings_reader.get_int(
        db, "suggestions.monitor_breakout_max_age_days", 30
    )
    breakout_max_video_count = settings_reader.get_int(
        db, "suggestions.monitor_breakout_max_video_count", 3
    )
    breakout_min_views = settings_reader.get_int(
        db, "suggestions.monitor_breakout_min_views", 50000
    )
    breakout_min_vpd = settings_reader.get_int(
        db, "suggestions.monitor_breakout_min_vpd", 2000
    )

    cutoff_age = datetime.utcnow() - timedelta(days=max_age_days)
    monitored_ids = select(Channel.youtube_channel_id)
    blacklisted_ids = select(ChannelBlacklist.youtube_channel_id)

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
            DiscoveryResultChannel.channel_published_at.isnot(None),
        )
        .all()
    )

    out: list[dict] = []
    for row in rows:
        age_days = _age_days(row.channel_published_at)
        best_video = _best_discovery_video_for_channel(db, row.youtube_channel_id)

        young_high_vpd = (
            row.avg_vpd_recent is not None
            and row.avg_vpd_recent >= min_vpd
            and row.channel_published_at is not None
            and row.channel_published_at >= cutoff_age
        )
        early_breakout = (
            age_days <= breakout_max_age_days
            and row.subscribers is not None
            and row.subscribers <= breakout_max_subscribers
            and row.video_count is not None
            and row.video_count <= breakout_max_video_count
            and best_video is not None
            and best_video.views is not None
            and best_video.views >= breakout_min_views
            and best_video.vpd is not None
            and best_video.vpd >= breakout_min_vpd
        )

        if not young_high_vpd and not early_breakout:
            continue

        suggestion_kind = "young_high_vpd"
        reason_parts: list[str] = []
        if young_high_vpd:
            reason_parts.append(
                f"VPD {int(row.avg_vpd_recent or 0)} >= {min_vpd} · canal com {age_days}d"
            )
        if early_breakout:
            suggestion_kind = "early_breakout" if not young_high_vpd else "mixed"
            reason_parts.append(
                "breakout precoce: "
                f"{row.video_count or 0} video(s), {row.subscribers or 0} inscritos e "
                f"top video com {int(best_video.views or 0)} views"
            )

        out.append(
            {
                "youtube_channel_id": row.youtube_channel_id,
                "title": row.title,
                "url": row.url,
                "thumbnail_url": row.thumbnail_url,
                "subscribers": row.subscribers,
                "video_count": row.video_count,
                "avg_vpd_recent": row.avg_vpd_recent,
                "channel_published_at": (
                    row.channel_published_at.isoformat() if row.channel_published_at else None
                ),
                "discovery_result_id": row.id,
                "matched_term": row.matched_term,
                "suggestion_kind": suggestion_kind,
                "top_video_title": best_video.title if best_video else None,
                "top_video_url": best_video.url if best_video else None,
                "top_video_views": best_video.views if best_video else None,
                "top_video_vpd": best_video.vpd if best_video else None,
                "reason": " · ".join(reason_parts),
            }
        )

    out.sort(
        key=lambda item: (
            0 if item["suggestion_kind"] == "mixed" else 1,
            -(item["top_video_views"] or 0),
            -(item["avg_vpd_recent"] or 0),
        )
    )
    return out[:limit]


def _best_discovery_video_for_channel(
    db: Session, youtube_channel_id: str
) -> Optional[DiscoveryResultVideo]:
    return (
        db.query(DiscoveryResultVideo)
        .filter(DiscoveryResultVideo.youtube_channel_id == youtube_channel_id)
        .order_by(
            desc(DiscoveryResultVideo.views),
            desc(DiscoveryResultVideo.vpd),
            desc(DiscoveryResultVideo.captured_at),
        )
        .first()
    )


def _age_days(dt: Optional[datetime]) -> int:
    if dt is None:
        return 0
    return max(0, (datetime.utcnow() - dt).days)


def list_dead_suggestions(db: Session, limit: int = 100) -> list[dict]:
    min_days_no_uploads = settings_reader.get_int(
        db, "suggestions.dead_min_days_no_uploads", 60
    )
    max_vpd = settings_reader.get_int(db, "suggestions.dead_max_vpd", 2000)
    cutoff_uploads = datetime.utcnow() - timedelta(days=min_days_no_uploads)

    latest_snap = (
        db.query(
            ChannelSnapshot.channel_id.label("ch_id"),
            func.max(ChannelSnapshot.captured_at).label("max_at"),
        )
        .group_by(ChannelSnapshot.channel_id)
        .subquery()
    )
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
        if last_upload_at is not None and last_upload_at > cutoff_uploads:
            continue
        if last_snap.avg_vpd_recent is None or last_snap.avg_vpd_recent > max_vpd:
            continue
        if last_snap.signal not in (None, "stable", "unknown"):
            continue

        days_since_upload = (
            (datetime.utcnow() - last_upload_at).days if last_upload_at is not None else None
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
                "last_upload_at": last_upload_at.isoformat() if last_upload_at else None,
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

    out.sort(
        key=lambda item: (
            item["avg_vpd_recent"] or 0,
            -(item["days_since_last_upload"] or 0),
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
    vpd_part = f"VPD {int(vpd or 0)} <= {max_vpd}"
    signal_part = f"sinal '{signal or 'desconhecido'}'"
    return f"{upload_part} · {vpd_part} · {signal_part}"
