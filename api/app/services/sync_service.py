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

import json
import logging
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import AppSetting, Channel, SyncRun, TrackedVideo
from app.services import (
    monitoring_service,
    notifications_service,
    suggestions_service_v2,
    youtube_client,
)

log = logging.getLogger(__name__)

SyncType = Literal["manual", "scheduled"]


# Chave em app_settings que guarda a ultima contagem de sugestoes vista pelo
# sync. Usada pra decidir se uma rodada deve emitir notificacao
# "Sugestoes mudaram".
_LAST_SUGGESTIONS_KEY = "notifications.last_suggestions_count"


def _check_suggestions_changed(db: Session) -> None:
    """
    Conta sugestoes atuais (to-monitor + to-remove), compara com a ultima
    contagem persistida em `app_settings.notifications.last_suggestions_count`,
    e cria uma notificacao `type=suggestions_changed` se ALGUM dos dois
    aumentou. Atualiza a contagem persistida no fim.

    Tudo via `safe_upsert` — falha aqui nunca derruba o sync (que ja esta
    finalizado e commitado quando esta funcao roda).
    """
    try:
        to_monitor = len(suggestions_service_v2.list_monitor_suggestions(db, limit=10_000))
        to_remove = len(suggestions_service_v2.list_dead_suggestions(db, limit=10_000))
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "suggestions_changed: contagem de sugestoes falhou: %s", exc, exc_info=True
        )
        notifications_service.safe_system_alert(
            db,
            source_key="ops:suggestions_check_failed",
            title="Detecção de sugestões degradada",
            message=(
                "Não foi possível contar sugestões após o sync. "
                "Você pode deixar de receber o card de novas sugestões "
                f"até que isso seja resolvido. Erro: {exc!s:.200}"
            ),
        )
        return

    row = db.query(AppSetting).filter_by(key=_LAST_SUGGESTIONS_KEY).one_or_none()
    last: dict[str, int] = {}
    if row and row.value:
        try:
            parsed = json.loads(row.value)
            if isinstance(parsed, dict):
                last = {
                    "to_monitor": int(parsed.get("to_monitor", 0) or 0),
                    "to_remove": int(parsed.get("to_remove", 0) or 0),
                }
        except (ValueError, TypeError):
            last = {}

    last_monitor = int(last.get("to_monitor", 0))
    last_remove = int(last.get("to_remove", 0))
    increased_monitor = max(0, to_monitor - last_monitor)
    increased_remove = max(0, to_remove - last_remove)

    if increased_monitor > 0 or increased_remove > 0:
        parts: list[str] = []
        if increased_monitor > 0:
            parts.append(f"+{increased_monitor} para monitorar")
        if increased_remove > 0:
            parts.append(f"+{increased_remove} para remover")
        message = (
            ", ".join(parts)
            + f" (total: {to_monitor} para monitorar, {to_remove} para remover)"
        )
        notifications_service.safe_upsert(
            db,
            type="suggestions_changed",
            status="info",
            title="Novas sugestões disponíveis",
            message=message,
            metadata={
                "to_monitor": to_monitor,
                "to_remove": to_remove,
                "increased_monitor": increased_monitor,
                "increased_remove": increased_remove,
            },
            # Sem source_key: cada novidade vira uma row nova (auditoria
            # historica). Cap FIFO 20 do service garante que nao acumula sem
            # limite.
        )

    # Atualiza estado persistido. Tudo via try/except amplo — sem source_key
    # ou helper especifico, escrevemos direto na row de AppSetting.
    try:
        new_value = json.dumps(
            {"to_monitor": to_monitor, "to_remove": to_remove},
            separators=(",", ":"),
        )
        if row is None:
            db.add(
                AppSetting(
                    key=_LAST_SUGGESTIONS_KEY,
                    value=new_value,
                    value_type="json",
                )
            )
        else:
            row.value = new_value
        db.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "suggestions_changed: persistir contagem falhou: %s", exc, exc_info=True
        )
        try:
            db.rollback()
        except Exception:
            pass
        notifications_service.safe_system_alert(
            db,
            source_key="ops:suggestions_check_failed",
            title="Detecção de sugestões degradada",
            message=(
                "Não foi possível persistir a contagem de sugestões após o "
                "sync — o próximo card de novas sugestões pode disparar "
                f"errado. Erro: {exc!s:.200}"
            ),
        )


def run_sync(db: Session, sync_type: SyncType = "manual") -> SyncRun:
    """
    Executa um sync. Persiste SyncRun e retorna.
    Tolera falhas individuais de canal/vídeo — registra em notes e continua.

    Notificações:
      - sync manual: cria card de progresso no início, atualiza por canal,
        finaliza com success/error. Sempre visível.
      - sync scheduled: nunca cria card no início; só cria card final se for
        partial/failed (sucesso passa silencioso).
    """
    run = SyncRun(type=sync_type, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    # Source key permite atualizar a MESMA notification durante a execução
    # (em vez de empilhar uma por evento).
    notif_source = f"sync_{sync_type}:{run.id}"

    if sync_type == "manual":
        notifications_service.safe_upsert(
            db,
            type="task_progress",
            status="running",
            title="Verificação manual em andamento",
            message="Iniciando…",
            progress_pct=0,
            metadata={"sync_run_id": run.id},
            source_key=notif_source,
        )

    errors: list[str] = []
    channels_processed = 0
    videos_processed = 0

    try:
        # Validação antecipada de API key — se falhar, erra já aqui e encerra
        youtube_client.build_from_db(db)

        active_channels = (
            db.query(Channel).filter(Channel.is_active.is_(True)).all()
        )
        active_videos = (
            db.query(TrackedVideo).filter(TrackedVideo.status == "active").all()
        )
        total_units = len(active_channels) + len(active_videos)
        done_units = 0

        def _progress_message() -> str:
            return f"{channels_processed} canais e {videos_processed} vídeos sincronizados…"

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

            done_units += 1
            if sync_type == "manual" and total_units > 0 and done_units % 5 == 0:
                # Atualiza a barra a cada 5 itens pra evitar overhead de DB.
                pct = int(done_units * 100 / total_units)
                notifications_service.safe_upsert(
                    db,
                    type="task_progress",
                    status="running",
                    title="Verificação manual em andamento",
                    message=_progress_message(),
                    progress_pct=pct,
                    metadata={"sync_run_id": run.id},
                    source_key=notif_source,
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

            done_units += 1
            if sync_type == "manual" and total_units > 0 and done_units % 5 == 0:
                pct = int(done_units * 100 / total_units)
                notifications_service.safe_upsert(
                    db,
                    type="task_progress",
                    status="running",
                    title="Verificação manual em andamento",
                    message=_progress_message(),
                    progress_pct=pct,
                    metadata={"sync_run_id": run.id},
                    source_key=notif_source,
                )

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

        # Notificação final.
        # - Manual: sempre vira card final (sucesso ou partial).
        # - Scheduled: só cria card se NÃO foi success (silencioso quando ok).
        should_notify_final = (
            sync_type == "manual" or run.status != "success"
        )
        if should_notify_final:
            if run.status == "success":
                notifications_service.safe_upsert(
                    db,
                    type="task_done",
                    status="success",
                    title="Verificação concluída",
                    message=(
                        f"{channels_processed} canais e {videos_processed} vídeos sincronizados."
                    ),
                    progress_pct=100,
                    metadata={"sync_run_id": run.id},
                    source_key=notif_source,
                )
            else:
                problems_summary = (
                    "; ".join(blocking_errors)[:200] if blocking_errors else "concluído com avisos"
                )
                notifications_service.safe_upsert(
                    db,
                    type="task_error",
                    status="error",
                    title=(
                        "Verificação manual concluída com falhas"
                        if sync_type == "manual"
                        else "Sync automático concluído com falhas"
                    ),
                    message=(
                        f"{channels_processed} canais e {videos_processed} vídeos. "
                        f"Erros: {problems_summary}"
                    ),
                    progress_pct=100,
                    metadata={"sync_run_id": run.id, "errors_count": len(blocking_errors)},
                    source_key=notif_source,
                )

        # Etapa pós-sync: descoberta automática. Roda em try/except próprio
        # para que uma falha aqui NUNCA contamine o status do sync (que ja
        # esta finalizado e commitado acima). Import tardio evita ciclo.
        try:
            from app.services import auto_discovery_service
            auto_discovery_service.run_auto_discovery(db)
        except Exception as exc:  # noqa: BLE001
            log.warning("auto-discovery pos-sync falhou: %s", exc, exc_info=True)
            # Auto-discovery silenciosa antes só ia pro log. Vira alerta
            # operacional pra o usuario perceber que a descoberta automatica
            # parou de rodar (sync ainda foi sucesso, isso aqui é etapa pós).
            notifications_service.safe_system_alert(
                db,
                source_key="ops:auto_discovery_failed",
                title="Descoberta automática falhou",
                message=(
                    "O sync concluiu, mas a etapa de descoberta automática "
                    f"posterior quebrou. Erro: {exc!s:.200}"
                ),
                metadata={"phase": "auto_discovery", "sync_run_id": run.id},
            )

        # Etapa pós-sync: detecta novidades em sugestoes. Tem que vir DEPOIS
        # da auto-discovery (que pode ter criado novas sugestoes). Engole
        # qualquer falha — nao derruba sync.
        try:
            _check_suggestions_changed(db)
        except Exception as exc:  # noqa: BLE001
            log.warning("suggestions_changed: checagem falhou: %s", exc)

        # Re-ancora o job automatico em `started_at + intervalo`, para que o
        # "proximo sync" exibido nunca seja anterior ao ultimo run (manual
        # ou agendado). Engole falha — re-ancorar nao e critico para o run.
        try:
            from app.core import scheduler

            ok = scheduler.reanchor(anchor=run.started_at)
            if not ok:
                # Trigger nao foi atualizado: o "proximo sync" exibido pode
                # estar mentindo, e o sync automatico pode ficar fora do ritmo.
                err = scheduler.last_error() or "scheduler retornou false"
                notifications_service.safe_system_alert(
                    db,
                    source_key="ops:scheduler_reanchor_failed",
                    title="Agendador degradado",
                    message=(
                        "Não foi possível reagendar o sync automático após o "
                        "último run. O 'próximo sync' exibido no dashboard "
                        f"pode estar incorreto. Erro: {err!s:.200}"
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("scheduler reanchor pos-sync falhou: %s", exc, exc_info=True)
            notifications_service.safe_system_alert(
                db,
                source_key="ops:scheduler_reanchor_failed",
                title="Agendador degradado",
                message=(
                    "Não foi possível reagendar o sync automático após o "
                    f"último run. Erro: {exc!s:.200}"
                ),
            )

        return run

    except Exception as exc:
        run.status = "failed"
        run.notes = str(exc)[:2000]
        run.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
        # Notifica falha total (qualquer tipo de sync).
        notifications_service.safe_upsert(
            db,
            type="task_error",
            status="error",
            title=(
                "Verificação manual falhou"
                if sync_type == "manual"
                else "Sync automático falhou"
            ),
            message=str(exc)[:200],
            progress_pct=100,
            metadata={"sync_run_id": run.id},
            source_key=notif_source,
        )
        # Mesmo em failure, re-ancora: started_at do run existe e a regra
        # "proximo = ultimo + intervalo" precisa valer pra qualquer run.
        try:
            from app.core import scheduler

            ok = scheduler.reanchor(anchor=run.started_at)
            if not ok:
                err = scheduler.last_error() or "scheduler retornou false"
                notifications_service.safe_system_alert(
                    db,
                    source_key="ops:scheduler_reanchor_failed",
                    title="Agendador degradado",
                    message=(
                        "Não foi possível reagendar o sync automático após "
                        f"falha do run. Erro: {err!s:.200}"
                    ),
                )
        except Exception as reanchor_exc:  # noqa: BLE001
            log.warning(
                "scheduler reanchor pos-sync (failed) falhou: %s",
                reanchor_exc,
                exc_info=True,
            )
            notifications_service.safe_system_alert(
                db,
                source_key="ops:scheduler_reanchor_failed",
                title="Agendador degradado",
                message=(
                    "Não foi possível reagendar o sync automático após "
                    f"falha do run. Erro: {reanchor_exc!s:.200}"
                ),
            )
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
