"""
Modelagem de domínio — youtube-analyzer

Entidades cobertas:
  - channels / channel_snapshots          (canais monitorados e histórico)
  - tracked_videos / video_snapshots      (vídeos acompanhados e histórico)
  - sync_runs                             (execuções de sincronização)
  - discovery_runs / discovery_results_*  (buscas por termos e resultados)
  - tags / channel_tags                   (nichos)
  - app_settings                          (configurações globais)

Convenções:
  - Timestamps em UTC, nomeados `*_at`.
  - IDs internos em BIGINT (`id`), IDs do YouTube em VARCHAR (`youtube_*_id`).
  - Campos numéricos de contagem em BIGINT (inscritos, views) — podem passar de 2B.
  - Métricas calculadas (VPD, delta) em FLOAT — precisão suficiente para analytics.
  - Unique constraints garantem idempotência de sync (mesmo canal não duplica).
  - InnoDB default com utf8mb4 para suportar emojis em títulos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# =============================================================================
# Canais
# =============================================================================
class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (
        # Filtros quentes: analytics/monitoramento filtram por status e o sync
        # varre por is_active. Sem índice viravam table scan.
        Index("ix_channels_status", "status"),
        Index("ix_channels_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    youtube_channel_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(512))
    custom_url: Mapped[Optional[str]] = mapped_column(String(255))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(512))

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(String(64))

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Favorito do usuário (estrela no Monitoramento). A observação/nota livre
    # do usuário reusa a coluna `notes` acima.
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Alerta de pico de views (por canal, ligado manualmente pelo usuário).
    # Regra: ganho de views nas últimas 24h >= multiplier × média diária dos
    # 7 dias anteriores. `spike_last_alert_at` implementa cooldown de 24h.
    spike_alert_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    spike_alert_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    spike_last_alert_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    snapshots: Mapped[list["ChannelSnapshot"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
    tracked_videos: Mapped[list["TrackedVideo"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
    tags: Mapped[list["ChannelTag"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


class ChannelSnapshot(Base):
    __tablename__ = "channel_snapshots"
    __table_args__ = (
        Index("ix_channel_snapshots_channel_captured", "channel_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )

    subscribers: Mapped[Optional[int]] = mapped_column(BigInteger)
    views_total: Mapped[Optional[int]] = mapped_column(BigInteger)
    video_count: Mapped[Optional[int]] = mapped_column(Integer)

    uploads_per_week: Mapped[Optional[float]] = mapped_column(Float)
    avg_vpd_recent: Mapped[Optional[float]] = mapped_column(Float)
    vpd_trend: Mapped[Optional[float]] = mapped_column(Float)

    delta_subscribers: Mapped[Optional[int]] = mapped_column(BigInteger)
    delta_views_total: Mapped[Optional[int]] = mapped_column(BigInteger)
    delta_avg_vpd: Mapped[Optional[float]] = mapped_column(Float)

    signal: Mapped[Optional[str]] = mapped_column(String(32))
    signal_reason: Mapped[Optional[str]] = mapped_column(Text)

    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    channel: Mapped["Channel"] = relationship(back_populates="snapshots")


# =============================================================================
# Vídeos monitorados
# =============================================================================
class TrackedVideo(Base):
    __tablename__ = "tracked_videos"
    __table_args__ = (
        UniqueConstraint("channel_id", "youtube_video_id", name="uq_tracked_video"),
        # Analytics conta vídeos por status="active"; sync filtra por status.
        Index("ix_tracked_videos_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )

    youtube_video_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(512))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(512))
    unavailable_reason: Mapped[Optional[str]] = mapped_column(String(64))
    unavailable_since: Mapped[Optional[datetime]] = mapped_column(DateTime)

    tracking_source: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    first_tracked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    first_tracked_vpd: Mapped[Optional[float]] = mapped_column(Float)

    last_seen_vpd: Mapped[Optional[float]] = mapped_column(Float)
    last_seen_views: Mapped[Optional[int]] = mapped_column(BigInteger)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    channel: Mapped["Channel"] = relationship(back_populates="tracked_videos")
    snapshots: Mapped[list["VideoSnapshot"]] = relationship(
        back_populates="tracked_video", cascade="all, delete-orphan"
    )


class VideoSnapshot(Base):
    __tablename__ = "video_snapshots"
    __table_args__ = (
        Index("ix_video_snapshots_video_captured", "tracked_video_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tracked_video_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tracked_videos.id", ondelete="CASCADE"), nullable=False
    )

    views: Mapped[Optional[int]] = mapped_column(BigInteger)
    likes: Mapped[Optional[int]] = mapped_column(BigInteger)
    comments: Mapped[Optional[int]] = mapped_column(BigInteger)

    vpd: Mapped[Optional[float]] = mapped_column(Float)

    delta_views: Mapped[Optional[int]] = mapped_column(BigInteger)
    delta_likes: Mapped[Optional[int]] = mapped_column(BigInteger)
    delta_comments: Mapped[Optional[int]] = mapped_column(BigInteger)

    recent_velocity: Mapped[Optional[float]] = mapped_column(Float)

    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    tracked_video: Mapped["TrackedVideo"] = relationship(back_populates="snapshots")


# =============================================================================
# Sync runs (execuções de sincronização — automática ou manual)
# =============================================================================
class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    type: Mapped[str] = mapped_column(String(32), nullable=False)  # manual | scheduled
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    channels_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    videos_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    notes: Mapped[Optional[str]] = mapped_column(Text)


# =============================================================================
# Descoberta (buscas por termos)
# =============================================================================
class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    terms: Mapped[str] = mapped_column(Text, nullable=False)
    filters_json: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    channels_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    videos_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    notes: Mapped[Optional[str]] = mapped_column(Text)

    channel_results: Mapped[list["DiscoveryResultChannel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    video_results: Mapped[list["DiscoveryResultVideo"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class DiscoveryResultChannel(Base):
    __tablename__ = "discovery_results_channels"
    __table_args__ = (
        Index("ix_discovery_ch_run_ytid", "run_id", "youtube_channel_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("discovery_runs.id", ondelete="CASCADE"), nullable=False
    )

    youtube_channel_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(512))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(512))

    subscribers: Mapped[Optional[int]] = mapped_column(BigInteger)
    views_total: Mapped[Optional[int]] = mapped_column(BigInteger)
    video_count: Mapped[Optional[int]] = mapped_column(Integer)
    avg_vpd_recent: Mapped[Optional[float]] = mapped_column(Float)

    score: Mapped[Optional[float]] = mapped_column(Float)
    matched_term: Mapped[Optional[str]] = mapped_column(String(255))

    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Data real da criação do canal no YouTube (vinda de channels.list).
    # Pode ser NULL para registros antigos (pré-2026-04-26) — backfill
    # natural conforme o auto-discovery re-encontra os canais.
    channel_published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    run: Mapped["DiscoveryRun"] = relationship(back_populates="channel_results")


class DiscoveryResultVideo(Base):
    __tablename__ = "discovery_results_videos"
    __table_args__ = (
        Index("ix_discovery_vid_run_ytid", "run_id", "youtube_video_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("discovery_runs.id", ondelete="CASCADE"), nullable=False
    )

    youtube_video_id: Mapped[str] = mapped_column(String(32), nullable=False)
    youtube_channel_id: Mapped[Optional[str]] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(512))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(512))

    views: Mapped[Optional[int]] = mapped_column(BigInteger)
    likes: Mapped[Optional[int]] = mapped_column(BigInteger)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    vpd: Mapped[Optional[float]] = mapped_column(Float)
    score: Mapped[Optional[float]] = mapped_column(Float)
    matched_term: Mapped[Optional[str]] = mapped_column(String(255))

    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    run: Mapped["DiscoveryRun"] = relationship(back_populates="video_results")


# =============================================================================
# Tags / Nichos
# =============================================================================
class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    channels: Mapped[list["ChannelTag"]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )


class ChannelTag(Base):
    __tablename__ = "channel_tags"
    __table_args__ = (
        UniqueConstraint("channel_id", "tag_id", name="uq_channel_tag"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    channel: Mapped["Channel"] = relationship(back_populates="tags")
    tag: Mapped["Tag"] = relationship(back_populates="channels")


# =============================================================================
# App settings (configurações globais + secrets cifrados)
# =============================================================================
class AppSetting(Base):
    """
    Par chave/valor tipado para configurações globais.

    - `value_type`: int | float | bool | str | json | secret
    - `is_secret`: True quando `value` está cifrado com Fernet (ver crypto.py).
      O código de leitura deve descifrar antes de usar. API keys do YouTube
      são armazenadas com is_secret=True.
    """
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    value: Mapped[Optional[str]] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False, default="str")
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


# =============================================================================
# Blacklist — canais removidos pelo usuário não voltam por discovery
# =============================================================================
class ChannelBlacklist(Base):
    """
    Canais que o usuário removeu explicitamente. Discovery filtra por aqui
    antes de hidratar resultados (economiza quota) e nunca os reaceita.
    """
    __tablename__ = "channel_blacklist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    youtube_channel_id: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    reason: Mapped[Optional[str]] = mapped_column(String(64))
    blacklisted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


# =============================================================================
# Notificações persistentes
# =============================================================================
class Notification(Base):
    """
    Eventos persistentes mostrados na central de notificações da UI.

    Tipos comuns:
      - task_progress     — barra de progresso ativa (status="running")
      - task_done         — operação terminou com sucesso (status="success")
      - task_error        — operação falhou ou parcial (status="error")
      - system_alert      — mensagem informativa do sistema (status="info")
      - suggestions_changed — backend detectou novas sugestões (status="info")

    `source_key` permite atualizar uma notificação existente em vez de criar
    nova (ex: o sync manual cria com source_key="sync_manual:<run_id>" e atualiza
    progresso na mesma row).

    `metadata_json` é JSON livre para o frontend (ex: link de destino, ids).
    """
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_dismissed_created", "dismissed_at", "created_at"),
        Index("ix_notifications_source_key", "source_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text)
    progress_pct: Mapped[Optional[int]] = mapped_column(Integer)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    source_key: Mapped[Optional[str]] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


# =============================================================================
# Autenticação (usuários + sessões opacas)
# =============================================================================
class User(Base):
    """
    Usuário do sistema. `password_hash` no formato
    `pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>` (ver core/security.py).
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    """
    Sessão de login com token opaco. O token em claro NUNCA é persistido —
    só o SHA-256 dele (`token_hash`). `client` distingue "web" de "desktop"
    (o desktop ganha expiração mais longa pra não pedir login toda hora).
    """
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    client: Mapped[str] = mapped_column(String(32), nullable=False, default="web")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="sessions")
