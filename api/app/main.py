import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import scheduler
from app.core.auth import require_auth
from app.core.config import get_settings
from app.routers import (
    analytics,
    auth as auth_router,
    discovery,
    health,
    monitoring,
    notifications,
    settings as settings_router,
    suggestions,
    sync as sync_router,
    youtube_keys,
)

settings = get_settings()

log = logging.getLogger(__name__)

APP_VERSION = "0.1.0"

# `started_at` deve ser FIXO durante a vida do processo. Define-se uma vez no
# lifespan; o frontend usa esse valor para detectar redeploy (mudou → reload).
APP_STARTED_AT: datetime | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global APP_STARTED_AT
    APP_STARTED_AT = datetime.utcnow()
    # Aviso de segurança: APP_SECRET_KEY fraca/ausente deixa as API keys
    # cifradas mais vulneráveis (a derivação é SHA-256). Não trocamos a
    # derivação aqui pra não inutilizar segredos já cifrados no banco — só
    # alertamos no log pra o operador gerar uma chave forte.
    if len(settings.app_secret_key or "") < 32:
        log.warning(
            "APP_SECRET_KEY ausente ou curta (<32 chars). As API keys cifradas "
            "ficam mais vulneraveis. Gere uma forte: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(
    title="youtube-analyzer API",
    version=APP_VERSION,
    description="API do sistema web youtube-analyzer (descoberta, monitoramento e analytics de canais).",
    lifespan=lifespan,
)

# `allow_credentials=True` combinado com origem "*" é inseguro (e o navegador
# nem aceita). Se alguém configurar CORS_ORIGINS="*", desligamos credenciais.
_cors_origins = settings.cors_origins_list
_allow_credentials = "*" not in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
# Tambem expoe os mesmos endpoints sob /api/* para alinhar com o restante da
# API (que e onde o NotificationsCenter chama /api/health/ops). Sem isso, o
# frontend recebia 404 → cards "API degradada" falsamente.
app.include_router(health.router, prefix="/api")
# Auth fica FORA da proteção global: /login precisa ser acessível deslogado
# (as demais rotas do router exigem token individualmente).
app.include_router(auth_router.router)

# Routers de dados exigem Bearer token válido (site, app do Windows e docs).
_protected = [Depends(require_auth)]
app.include_router(settings_router.router, dependencies=_protected)
app.include_router(discovery.router, dependencies=_protected)
app.include_router(monitoring.router, dependencies=_protected)
app.include_router(sync_router.router, dependencies=_protected)
app.include_router(analytics.router, dependencies=_protected)
app.include_router(suggestions.router, dependencies=_protected)
app.include_router(notifications.router, dependencies=_protected)
app.include_router(youtube_keys.router, dependencies=_protected)


@app.get("/", tags=["root"])
def root() -> dict:
    return {
        "app": settings.app_name,
        "env": settings.app_env,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/api/version", tags=["root"])
def app_version() -> dict:
    """
    Informa a versao do app e o instante em que o processo subiu.

    O frontend faz polling deste endpoint para detectar:
      - **API offline**: 3 falhas consecutivas → notif local "API offline há Xs".
      - **API atualizada**: `started_at` mudou → notif local "API atualizada
        — recarregue" com botao reload.

    `started_at` e fixado no `lifespan` no boot do processo, por isso muda
    SEMPRE que ha redeploy.
    """
    return {
        "version": APP_VERSION,
        "started_at": APP_STARTED_AT.isoformat() if APP_STARTED_AT else None,
    }
