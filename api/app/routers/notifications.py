"""
Router /api/notifications — informações operacionais agregadas para a
central de notificações da UI (ícone fixo no canto inferior esquerdo).

Hoje só expõe `quota-summary`, mas o endpoint raiz é genérico para receber
novas notificações no futuro sem refatoração da estrutura do componente.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.notifications import QuotaSummary
from app.services import youtube_client

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/quota-summary", response_model=QuotaSummary)
def get_quota_summary(db: Session = Depends(get_db)) -> QuotaSummary:
    """
    Resumo agregado da cota da YouTube API somando todas as keys cadastradas.
    Lê só o estado persistido em `app_settings.youtube.quota_usage_today` —
    não dispara nenhuma chamada externa.
    """
    return QuotaSummary(**youtube_client.read_quota_summary(db))
