import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db

router = APIRouter(tags=["health"])

log = logging.getLogger(__name__)

# Tabelas que precisam existir pra o app operar minimamente. Migrations.
ESSENTIAL_TABLES = ("app_settings", "notifications", "sync_runs")

# Mensagem genérica devolvida ao cliente em falhas. O texto cru da exceção
# (que pode conter host/usuário/schema do banco ou internals do driver) vai
# SÓ para o log do servidor — estes endpoints são públicos/sem autenticação.
_GENERIC_DETAIL = "Falha interna — verifique os logs do servidor."


@router.get("/health")
def healthcheck(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
    }


@router.get("/health/db")
def healthcheck_db(db: Session = Depends(get_db)) -> JSONResponse:
    """
    Saúde do banco. Retorna HTTP 503 quando inacessível pra que monitor
    externo (load balancer, EasyPanel) classifique corretamente — antes
    devolvíamos 200 mesmo com banco fora.
    """
    try:
        db.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok", "db": "reachable"})
    except Exception as exc:
        log.warning("/health/db: banco inacessivel: %s", exc, exc_info=True)
        return JSONResponse(
            {"status": "error", "db": "unreachable", "detail": _GENERIC_DETAIL},
            status_code=503,
        )


@router.get("/health/notifications")
def healthcheck_notifications(db: Session = Depends(get_db)) -> JSONResponse:
    """
    Saúde do canal principal de notificações. Valida que a tabela `notifications`
    está acessível em LEITURA. Sem isso, `safe_upsert` engole erro e a UI
    deixa de receber qualquer alerta — incluindo o aviso da própria falha.
    """
    try:
        # Import tardio para evitar ciclo (notifications_service importa Notification).
        from app.models import Notification

        db.query(Notification.id).limit(1).all()
        return JSONResponse({"status": "ok", "notifications": "reachable"})
    except Exception as exc:
        log.warning(
            "/health/notifications: tabela inacessivel: %s", exc, exc_info=True
        )
        return JSONResponse(
            {
                "status": "error",
                "notifications": "unreachable",
                "detail": _GENERIC_DETAIL,
            },
            status_code=503,
        )


@router.get("/health/ops")
def healthcheck_ops(db: Session = Depends(get_db)) -> JSONResponse:
    """
    Saúde operacional agregada: banco, tabelas essenciais, scheduler ativo
    com job registrado, decrypt das chaves YouTube quando há valor salvo.

    Retorna 200 quando tudo está OK e 503 quando qualquer item falha.
    Pensado pra monitor externo / liveness probe que precisa de sinal real
    em vez de "API responde HTTP".
    """
    checks: dict[str, dict] = {}
    overall_ok = True

    # 1) banco acessível
    try:
        db.execute(text("SELECT 1"))
        checks["db"] = {"ok": True}
    except Exception as exc:
        log.warning("/health/ops db check falhou: %s", exc, exc_info=True)
        checks["db"] = {"ok": False, "detail": _GENERIC_DETAIL}
        overall_ok = False

    # 2) tabelas essenciais existem
    try:
        inspector = inspect(db.get_bind())
        existing = set(inspector.get_table_names())
        missing = [t for t in ESSENTIAL_TABLES if t not in existing]
        if missing:
            checks["tables"] = {"ok": False, "missing": missing}
            overall_ok = False
        else:
            checks["tables"] = {"ok": True}
    except Exception as exc:
        log.warning("/health/ops tables check falhou: %s", exc, exc_info=True)
        checks["tables"] = {"ok": False, "detail": _GENERIC_DETAIL}
        overall_ok = False

    # 3) scheduler vivo + job registrado
    try:
        from app.core import scheduler

        running = scheduler.is_running()
        next_at = scheduler.next_run_time()
        sched_err = scheduler.last_error()
        ok = running and sched_err is None and next_at is not None
        checks["scheduler"] = {
            "ok": ok,
            "running": running,
            "next_run_at": next_at.isoformat() if next_at else None,
            "error": sched_err,
        }
        if not ok:
            overall_ok = False
    except Exception as exc:
        log.warning("/health/ops scheduler check falhou: %s", exc, exc_info=True)
        checks["scheduler"] = {"ok": False, "detail": _GENERIC_DETAIL}
        overall_ok = False

    # 4) decrypt das chaves YouTube quando ha valor salvo. "Sem chave" e
    #    estado valido (usuario ainda nao configurou) → ok=True. "Decrypt
    #    falhou" e configuracao quebrada → ok=False.
    try:
        from app.services import youtube_client

        try:
            youtube_client._decrypt_keys_from_db(db)
            checks["youtube_keys_decrypt"] = {"ok": True}
        except youtube_client.APIKeyDecryptError as exc:
            log.warning("/health/ops decrypt das chaves falhou: %s", exc, exc_info=True)
            checks["youtube_keys_decrypt"] = {"ok": False, "detail": _GENERIC_DETAIL}
            overall_ok = False
    except Exception as exc:
        log.warning("/health/ops youtube_keys check falhou: %s", exc, exc_info=True)
        checks["youtube_keys_decrypt"] = {"ok": False, "detail": _GENERIC_DETAIL}
        overall_ok = False

    body = {"status": "ok" if overall_ok else "error", "checks": checks}
    return JSONResponse(body, status_code=200 if overall_ok else 503)
