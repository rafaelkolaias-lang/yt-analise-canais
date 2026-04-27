"""Schemas Pydantic para o gerenciamento individual de chaves YouTube."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class YouTubeKeyEntry(BaseModel):
    """
    Representa UMA chave da API YouTube na visão da UI.

    `fingerprint` é a identidade estável (SHA-256[:16] da chave) — é o que
    a UI usa para chamar DELETE/unburn. A chave em si nunca é exposta.
    `masked` mostra os últimos 4 caracteres pra ajudar o usuário a distinguir
    visualmente entre chaves cadastradas.
    """

    fingerprint: str
    masked: str
    index: int
    status: str  # "ok" | "quota_exhausted" | "burned"
    used_today: int
    daily_quota: int
    burned_at: Optional[str] = None
    burned_reason: Optional[str] = None
    burned_label: Optional[str] = None


class YouTubeKeyAdd(BaseModel):
    """POST /api/youtube/keys — body."""

    key: str = Field(..., min_length=1, description="Chave da API YouTube em texto plano.")


class YouTubeKeyAddResponse(BaseModel):
    entry: YouTubeKeyEntry
    created: bool  # False = chave já existia (idempotente)


class YouTubeKeyOpResponse(BaseModel):
    """Resposta genérica de DELETE / unburn."""

    fingerprint: str
    changed: bool


class YouTubeKeysHealth(BaseModel):
    """Resumo de saúde das chaves para a central de notificações."""

    total: int
    ok: int
    quota_exhausted: int
    burned: int
    last_burned_at: Optional[str] = None
    last_burned_reason: Optional[str] = None
