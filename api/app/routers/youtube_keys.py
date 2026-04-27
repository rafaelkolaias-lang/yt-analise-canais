"""
Router /api/youtube/keys — gerenciamento individual de chaves da YouTube API.

Diferença pro router genérico /api/settings/{key}:
  - Lá, `youtube.api_keys` é tratada como uma string opaca (substituir tudo).
  - Aqui, cada chave tem identidade própria via fingerprint, e dá pra
    adicionar/remover/reativar UMA chave sem mexer nas outras.

Comportamento esperado da UI:
  - GET   /api/youtube/keys                → lista com status (ok/quota/burned).
  - POST  /api/youtube/keys                → adiciona chave nova (idempotente).
  - DELETE /api/youtube/keys/{fingerprint} → remove pelo fingerprint.
  - POST  /api/youtube/keys/{fingerprint}/unburn → tira marca de queimada.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.youtube_keys import (
    YouTubeKeyAdd,
    YouTubeKeyAddResponse,
    YouTubeKeyEntry,
    YouTubeKeyOpResponse,
    YouTubeKeysHealth,
)
from app.services import youtube_keys_service

router = APIRouter(prefix="/api/youtube/keys", tags=["youtube-keys"])


@router.get("", response_model=list[YouTubeKeyEntry])
def list_keys(db: Session = Depends(get_db)) -> list[YouTubeKeyEntry]:
    return [YouTubeKeyEntry(**entry) for entry in youtube_keys_service.list_keys(db)]


@router.get("/health", response_model=YouTubeKeysHealth)
def keys_health(db: Session = Depends(get_db)) -> YouTubeKeysHealth:
    """Resumo agregado de saúde das chaves, usado pela central de notificações."""
    return YouTubeKeysHealth(**youtube_keys_service.health_summary(db))


@router.post("", response_model=YouTubeKeyAddResponse, status_code=status.HTTP_201_CREATED)
def add_key(
    payload: YouTubeKeyAdd,
    db: Session = Depends(get_db),
) -> YouTubeKeyAddResponse:
    try:
        entry, created = youtube_keys_service.add_key(db, payload.key)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return YouTubeKeyAddResponse(entry=YouTubeKeyEntry(**entry), created=created)


@router.delete("/{fingerprint}", response_model=YouTubeKeyOpResponse)
def remove_key(
    fingerprint: str,
    db: Session = Depends(get_db),
) -> YouTubeKeyOpResponse:
    changed = youtube_keys_service.remove_key(db, fingerprint)
    return YouTubeKeyOpResponse(fingerprint=fingerprint, changed=changed)


@router.post("/{fingerprint}/unburn", response_model=YouTubeKeyOpResponse)
def unburn_key(
    fingerprint: str,
    db: Session = Depends(get_db),
) -> YouTubeKeyOpResponse:
    changed = youtube_keys_service.unburn_key(db, fingerprint)
    return YouTubeKeyOpResponse(fingerprint=fingerprint, changed=changed)
