from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(
    title="youtube-analyzer API",
    version="0.1.0",
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
