from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import scheduler
from app.core.config import get_settings
from app.routers import (
    analytics,
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

APP_VERSION = "0.1.0"

# `started_at` deve ser FIXO durante a vida do processo. Define-se uma vez no
# lifespan; o frontend usa esse valor para detectar redeploy (mudou → reload).
APP_STARTED_AT: datetime | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global APP_STARTED_AT
    APP_STARTED_AT = datetime.utcnow()
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
# Tambem expoe os mesmos endpoints sob /api/* para alinhar com o restante da
# API (que e onde o NotificationsCenter chama /api/health/ops). Sem isso, o
# frontend recebia 404 → cards "API degradada" falsamente.
app.include_router(health.router, prefix="/api")
app.include_router(settings_router.router)
app.include_router(discovery.router)
app.include_router(monitoring.router)
app.include_router(sync_router.router)
app.include_router(analytics.router)
app.include_router(suggestions.router)
app.include_router(notifications.router)
app.include_router(youtube_keys.router)


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
