from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AppSettingRead(BaseModel):
    """
    DTO de leitura. Para settings com `is_secret=True`, `value` é retornado
    mascarado (nunca em texto plano), e `has_value` indica se há algo salvo.
    Para settings normais, `value` é o valor atual (como string).

    `description` é o texto curto exibido ao lado do campo. `help` é o texto
    longo (didático) exibido no tooltip do ícone "?". `help` vive em código
    (`app.services.settings_help`) — não no banco — para evitar migration por
    mudança puramente textual.
    """
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Optional[str] = None
    value_type: str
    is_secret: bool
    has_value: bool
    description: Optional[str] = None
    help: Optional[str] = None
    updated_at: datetime


class AppSettingUpdate(BaseModel):
    """
    PUT /api/settings/{key} — atualiza o valor de uma setting.
    Para `is_secret=True`, `value` é cifrado no backend antes de persistir.
    Use `value=None` ou string vazia para limpar um secret.
    """
    value: Optional[str] = None
