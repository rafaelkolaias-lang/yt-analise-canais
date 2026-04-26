"""
Sync service — orquestra a sincronização de todos os canais e vídeos ativos.

Um "sync run" pega snapshots de:
  - todos Channel com is_active=True
  - todos TrackedVideo com status='active'

Cada snapshot é um POST independente para a YouTube API, com tolerância a falha
individual: se um canal quebrar, o run continua e registra o erro em notes.

Cost estimate:
  ~3 units por canal (channels + playlistItems + videos)
  ~1 unit por vídeo (videos)

Com 50 canais + 100 vídeos: ~250 units por run. Default de 12h → ~500/dia.
Margem confortável dentro dos 10.000 units/dia por key.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Channel, SyncRun, TrackedVideo
from app.services import monitoring_service, youtube_client

log = logging.getLogger(__name__)

SyncType = Literal["manual", "scheduled"]


def run_sync(db: Session, sync_type: SyncType = "manual") -> SyncRun:
    """
    Executa um sync. Persiste SyncRun e retorna.
    Tolera falhas individuais de canal/vídeo — registra em notes e continua.
    """
    run = SyncRun(type=sync_type, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    errors: list[str] = []
    channels_processed = 0
    videos_processed = 0

    try:
        # Validação antecipada de API key — se falhar, erra já aqui e encerra
        youtube_client.build_from_db(db)

        active_channels = (
            db.query(Channel).filter(Channel.is_active.is_(True)).all()
        )
        for ch in active_channels:
            try:
                monitoring_service.snapshot_channel(db, ch.id)
                channels_processed += 1
            except monitoring_service.PermanentlyUnavailableError as exc:
                channels_processed += 1
                msg = f"info: canal removido tratado: {exc}"
                log.info("sync indisponibilidade persistente: %s", msg)
                errors.append(msg)
            except Exception as exc:
                msg = f"canal id={ch.id} ({ch.title[:40]}): {exc}"
                log.warning("sync falha: %s", msg)
                errors.append(msg)

        active_videos = (
            db.query(TrackedVideo).filter(TrackedVideo.status == "active").all()
        )
        for tv in active_videos:
            try:
                monitoring_service.snapshot_video(db, tv.id)
                videos_processed += 1
            except monitoring_service.PermanentlyUnavailableError as exc:
                videos_processed += 1
                msg = f"info: video removido tratado: {exc}"
                log.info("sync indisponibilidade persistente: %s", msg)
                errors.append(msg)
            except Exception as exc:
                msg = f"video id={tv.id}: {exc}"
                log.warning("sync falha: %s", msg)
                errors.append(msg)

        run.channels_processed = channels_processed
        run.videos_processed = videos_processed
        blocking_errors = [msg for msg in errors if not msg.startswith("info: ")]
        info_notes = [msg[6:] for msg in errors if msg.startswith("info: ")]
        run.status = "success" if not blocking_errors else "partial"
        if errors:
            run.notes = "; ".join(info_notes + blocking_errors)[:2000]
        run.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(run)

        # Etapa pós-sync: descoberta automática. Roda em try/except próprio
        # para que uma falha aqui NUNCA contamine o status do sync (que ja
        # esta finalizado e commitado acima). Import tardio evita ciclo.
        try:
            from app.services import auto_discovery_service
            auto_discovery_service.run_auto_discovery(db)
        except Exception as exc:  # noqa: BLE001
            log.warning("auto-discovery pos-sync falhou: %s", exc)

        return run

    except Exception as exc:
        run.status = "failed"
        run.notes = str(exc)[:2000]
        run.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
        raise


def run_sync_in_new_session(sync_type: SyncType = "scheduled") -> SyncRun:
    """
    Wrapper pra uso pelo APScheduler — abre uma Session própria.
    Sessões do FastAPI via Depends(get_db) não valem em jobs background.
    """
    db = SessionLocal()
    try:
        return run_sync(db, sync_type=sync_type)
    finally:
        db.close()
