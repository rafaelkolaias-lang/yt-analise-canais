"""
Scheduler in-process — APScheduler BackgroundScheduler.

Roda o sync automático a cada `sync_interval_hours` (lido de app_settings no
startup). O job é re-ancorado APÓS CADA `SyncRun` (manual ou scheduled) e ao
mudar a setting de intervalo, de modo que:

    proximo_sync = ultimo_sync.started_at + sync_interval_hours

Design:
  - Um único job chamado 'auto_sync'.
  - Misfire grace 15 min (se o app estava dormindo e perdeu o horário, roda na
    volta, mas não enfileira N execuções atrasadas).
  - coalesce=True: se houver múltiplos trigger times pendentes, executa apenas
    1 na volta.
  - max_instances=1: evita rodadas concorrentes se o sync anterior ainda estiver
    em execução (snapshot de muitos canais pode demorar).
  - Re-ancoragem usa `IntervalTrigger(start_date=ultimo_sync.started_at, hours=N)`
    de modo que o próximo `next_run_time` cai exatamente em
    `ultimo_sync + N` — nunca antes, mesmo que `now` já tenha passado.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import SyncRun
from app.services import settings_reader

log = logging.getLogger(__name__)

JOB_ID = "auto_sync"

_scheduler: Optional[BackgroundScheduler] = None


def _current_interval_hours() -> int:
    """
    Lê `sync_interval_hours` do banco. Se a tabela `app_settings` ainda não
    existe (primeiro boot em produção, antes de `alembic upgrade head`), cai
    no fallback do env var SYNC_INTERVAL_HOURS para não crashar o startup.
    """
    fallback = get_settings().sync_interval_hours
    db = SessionLocal()
    try:
        return settings_reader.get_int(db, "sync_interval_hours", fallback)
    except Exception as exc:
        log.warning(
            "[scheduler] não foi possível ler sync_interval_hours do banco "
            "(%s). Usando fallback %sh. Rode `alembic upgrade head` + seed.",
            exc, fallback,
        )
        return fallback
    finally:
        db.close()


def _last_sync_started_at() -> Optional[datetime]:
    """Retorna `started_at` do SyncRun mais recente, ou None se não houver."""
    db = SessionLocal()
    try:
        last = db.query(SyncRun).order_by(SyncRun.started_at.desc()).first()
        return last.started_at if last else None
    except Exception as exc:
        log.warning("[scheduler] falha ao ler ultimo SyncRun: %s", exc)
        return None
    finally:
        db.close()


def _build_trigger(hours: int, anchor: Optional[datetime]) -> IntervalTrigger:
    """
    Constrói o IntervalTrigger.

    Se `anchor` (último sync) for fornecido, usa `start_date = anchor + hours`
    para que `next_run_time` caia em `anchor + hours`. Quando esse instante já
    passou, APScheduler avança em múltiplos de `hours` até o próximo futuro
    (com `misfire_grace_time` cobrindo a janela). Sem âncora, usa o
    comportamento default (próximo trigger em `now + hours`).
    """
    if hours < 1:
        hours = 1
    if anchor is None:
        return IntervalTrigger(hours=hours, timezone=timezone.utc)
    # SyncRun.started_at é naive em UTC; vira tz-aware para o trigger.
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    next_at = anchor + timedelta(hours=hours)
    return IntervalTrigger(hours=hours, start_date=next_at, timezone=timezone.utc)


def _run_job() -> None:
    """Entry point do job agendado."""
    log.info("[scheduler] disparando sync automático")
    try:
        # Import tardio evita ciclo (sync_service importa scheduler indiretamente
        # quando faz reanchor pós-run).
        from app.services import sync_service

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
    anchor = _last_sync_started_at()
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_job,
        trigger=_build_trigger(hours, anchor),
        id=JOB_ID,
        name="auto_sync",
        misfire_grace_time=15 * 60,
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    _scheduler.start()
    if anchor is not None:
        log.info(
            "[scheduler] iniciado com intervalo de %sh, ancorado em ultimo sync %s",
            hours, anchor.isoformat(),
        )
    else:
        log.info("[scheduler] iniciado com intervalo de %sh (sem sync anterior)", hours)


def shutdown() -> None:
    """Chamada no shutdown do FastAPI."""
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    log.info("[scheduler] desligado")


def reanchor(anchor: Optional[datetime] = None, hours: Optional[int] = None) -> None:
    """
    Re-ancora o job auto_sync.

    Use depois de cada run_sync (manual ou scheduled) e quando a setting
    `sync_interval_hours` mudar. Sem `anchor` explícito, lê o último SyncRun
    do banco. Sem `hours` explícito, lê a setting atual.

    Quando não há nenhum SyncRun no banco, mantém o trigger em `now + hours`.
    """
    if _scheduler is None:
        return
    if hours is None:
        hours = _current_interval_hours()
    if anchor is None:
        anchor = _last_sync_started_at()
    try:
        _scheduler.reschedule_job(JOB_ID, trigger=_build_trigger(hours, anchor))
        log.info(
            "[scheduler] reagendado: %sh, ancorado em %s",
            hours, anchor.isoformat() if anchor else "now",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("[scheduler] reanchor falhou: %s", exc)


def reschedule(new_hours: int) -> None:
    """
    Re-agenda o job sem restart. Usado quando a setting `sync_interval_hours`
    muda. Mantém o `started_at` do último sync como âncora — só recalcula com
    o novo intervalo.
    """
    if _scheduler is None:
        return
    if new_hours < 1:
        new_hours = 1
    reanchor(hours=new_hours)


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
