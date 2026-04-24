"""
Scheduler in-process — APScheduler BackgroundScheduler.

Roda o sync automático a cada `sync_interval_hours` (lido de app_settings no
startup). Para aplicar intervalo novo sem restart, chame `reschedule()` após
alterar a setting.

Design:
  - Um único job chamado 'auto_sync'.
  - Misfire grace 15 min (se o app estava dormindo e perdeu o horário, roda na
    volta, mas não enfileira N execuções atrasadas).
  - coalesce=True: se houver múltiplos trigger times pendentes, executa apenas
    1 na volta.
  - max_instances=1: evita rodadas concorrentes se o sync anterior ainda estiver
    em execução (snapshot de muitos canais pode demorar).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.database import SessionLocal
from app.services import settings_reader, sync_service

log = logging.getLogger(__name__)

JOB_ID = "auto_sync"

_scheduler: Optional[BackgroundScheduler] = None


def _current_interval_hours() -> int:
    db = SessionLocal()
    try:
        return settings_reader.get_int(db, "sync_interval_hours", 12)
    finally:
        db.close()


def _run_job() -> None:
    """Entry point do job agendado."""
    log.info("[scheduler] disparando sync automático")
    try:
        run = sync_service.run_sync_in_new_session(sync_type="scheduled")
        log.info(
            "[scheduler] sync terminou: id=%s status=%s canais=%s videos=%s",
            run.id, run.status, run.channels_processed, run.videos_processed,
        )
    except Exception as exc:
        log.exception("[scheduler] sync falhou: %s", exc)


def start() -> None:
    """Chamada uma vez no startup do FastAPI."""
    global _scheduler
    if _scheduler is not None:
        return

    hours = _current_interval_hours()
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_job,
        trigger=IntervalTrigger(hours=hours),
        id=JOB_ID,
        name="auto_sync",
        misfire_grace_time=15 * 60,
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    _scheduler.start()
    log.info("[scheduler] iniciado com intervalo de %sh", hours)


def shutdown() -> None:
    """Chamada no shutdown do FastAPI."""
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    log.info("[scheduler] desligado")


def reschedule(new_hours: int) -> None:
    """Re-agenda o job sem restart. Usado quando a setting `sync_interval_hours` muda."""
    if _scheduler is None:
        return
    if new_hours < 1:
        new_hours = 1
    _scheduler.reschedule_job(JOB_ID, trigger=IntervalTrigger(hours=new_hours))
    log.info("[scheduler] reagendado para %sh", new_hours)


def next_run_time() -> Optional[datetime]:
    """Próxima execução prevista em UTC (ou None se scheduler desligado)."""
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    if job is None or job.next_run_time is None:
        return None
    # APScheduler retorna tz-aware; normalizamos pra UTC naive para alinhar
    # com datetime.utcnow() persistido no banco.
    return job.next_run_time.astimezone(timezone.utc).replace(tzinfo=None)


def current_interval_hours() -> int:
    """Intervalo atualmente configurado no scheduler (não o da setting)."""
    if _scheduler is None:
        return _current_interval_hours()
    job = _scheduler.get_job(JOB_ID)
    if job is None:
        return _current_interval_hours()
    trig = job.trigger
    if isinstance(trig, IntervalTrigger):
        return int(trig.interval.total_seconds() // 3600) or 1
    return _current_interval_hours()
