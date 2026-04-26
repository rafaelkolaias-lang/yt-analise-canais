"""
Router /api/suggestions — recomendações de monitoramento (NUNCA executa
ação no canal; só sugere).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.suggestions import DeadChannelSuggestion, MonitorSuggestion
from app.services import suggestions_service

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


@router.get("/to-monitor", response_model=list[MonitorSuggestion])
def get_monitor_suggestions(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[MonitorSuggestion]:
    return [MonitorSuggestion(**r) for r in suggestions_service.list_monitor_suggestions(db, limit)]


@router.get("/to-remove", response_model=list[DeadChannelSuggestion])
def get_dead_channel_suggestions(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[DeadChannelSuggestion]:
    return [DeadChannelSuggestion(**r) for r in suggestions_service.list_dead_suggestions(db, limit)]
