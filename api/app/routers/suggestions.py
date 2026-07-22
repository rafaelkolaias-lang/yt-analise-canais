"""
Router /api/suggestions — recomendações de monitoramento (NUNCA executa
ação no canal; só sugere).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.monitoring import ChannelRead
from app.schemas.suggestions import (
    CandidateChannel,
    DeadChannelSuggestion,
    DismissSuggestionRequest,
    MonitorSuggestion,
    SuggestionOpResponse,
)
from app.services import suggestion_candidates_service
from app.services import suggestions_service_v2 as suggestions_service

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


@router.post("/dismiss", response_model=SuggestionOpResponse)
def dismiss_suggestion(
    req: DismissSuggestionRequest, db: Session = Depends(get_db)
) -> SuggestionOpResponse:
    """Dispensa uma sugestão (blacklist) — não volta a ser sugerida."""
    changed = suggestion_candidates_service.dismiss_suggestion(
        db, req.youtube_channel_id
    )
    return SuggestionOpResponse(ok=changed)


# ---------------------------------------------------------------------------
# Candidatos (sugestões em observação automática)
# ---------------------------------------------------------------------------
@router.get("/candidates", response_model=list[CandidateChannel])
def list_candidates(db: Session = Depends(get_db)) -> list[CandidateChannel]:
    return [
        CandidateChannel(**c)
        for c in suggestion_candidates_service.list_candidates(db)
    ]


@router.post("/candidates/{channel_id}/promote", response_model=ChannelRead)
def promote_candidate(channel_id: int, db: Session = Depends(get_db)) -> ChannelRead:
    """Candidato aprovado → vira canal monitorado normal."""
    try:
        ch = suggestion_candidates_service.promote(db, channel_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    return ChannelRead.model_validate(ch)


@router.post("/candidates/{channel_id}/dismiss", response_model=SuggestionOpResponse)
def dismiss_candidate(
    channel_id: int, db: Session = Depends(get_db)
) -> SuggestionOpResponse:
    """Candidato dispensado → apagado + blacklist (não volta a ser sugerido)."""
    try:
        suggestion_candidates_service.dismiss(db, channel_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    return SuggestionOpResponse(ok=True)
