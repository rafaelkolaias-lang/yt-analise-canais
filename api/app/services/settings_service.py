"""
Service layer para app_settings.

Regras:
  - Para `is_secret=True`, o `value` no banco é cifrado com Fernet.
  - Leitura NUNCA retorna o valor em texto plano — só `mask()`.
  - Escrita cifra antes de persistir. `value` vazio/None → limpa o campo.
  - `has_value` sempre reflete se existe algo persistido (mesmo que cifrado).
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.core.crypto import encrypt, mask
from app.models import AppSetting
from app.schemas.settings import AppSettingRead
from app.services.settings_help import get_help

# Chaves de uso INTERNO do sistema (estado, não configuração do usuário). Não
# devem aparecer nem ser editáveis pela API pública de settings — o backend as
# escreve direto. Editá-las à mão corromperia cota/contadores.
INTERNAL_KEYS = frozenset(
    {
        "youtube.quota_usage_today",
        "notifications.last_suggestions_count",
    }
)

# Tokens aceitos para value_type="bool".
_BOOL_TOKENS = {"1", "0", "true", "false", "yes", "no", "on", "off"}


def _validate_value(value_type: str, raw_value: str) -> None:
    """
    Valida que `raw_value` (não vazio) é coerente com `value_type`. Levanta
    ValueError com mensagem amigável quando não for — assim o usuário recebe
    um 400 claro em vez de salvar uma config que será silenciosamente ignorada
    na leitura (que cai no default).
    """
    if value_type == "int":
        try:
            int(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f"Valor inválido para tipo inteiro: {raw_value!r}")
    elif value_type == "float":
        try:
            float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f"Valor inválido para tipo número: {raw_value!r}")
    elif value_type == "bool":
        if raw_value.strip().lower() not in _BOOL_TOKENS:
            raise ValueError(
                f"Valor inválido para tipo booleano: {raw_value!r} "
                "(use true/false)."
            )
    elif value_type == "json":
        try:
            json.loads(raw_value)
        except (TypeError, ValueError):
            raise ValueError("Valor inválido: JSON malformado.")
    # str/secret/csv: sem validação específica.


def _to_read(setting: AppSetting) -> AppSettingRead:
    """Converte o row do banco no DTO de leitura (mascara secrets)."""
    has_value = setting.value is not None and setting.value != ""

    if setting.is_secret:
        display_value = mask("x" * 12) if has_value else None
    else:
        display_value = setting.value

    return AppSettingRead(
        key=setting.key,
        value=display_value,
        value_type=setting.value_type,
        is_secret=setting.is_secret,
        has_value=has_value,
        description=setting.description,
        help=get_help(setting.key),
        updated_at=setting.updated_at,
    )


def list_settings(db: Session) -> list[AppSettingRead]:
    rows = db.query(AppSetting).order_by(AppSetting.key).all()
    # Esconde chaves internas (estado do sistema) da API pública.
    return [_to_read(r) for r in rows if r.key not in INTERNAL_KEYS]


def get_setting(db: Session, key: str) -> Optional[AppSettingRead]:
    if key in INTERNAL_KEYS:
        return None  # router devolve 404 — chave interna não é exposta
    row = db.query(AppSetting).filter_by(key=key).one_or_none()
    return _to_read(row) if row else None


def update_setting(db: Session, key: str, raw_value: Optional[str]) -> Optional[AppSettingRead]:
    """
    Atualiza `value` de uma setting existente.
    - secrets: cifra antes de persistir; valor vazio/None limpa.
    - normais: salva como texto.
    Retorna None se a key não existir (router devolve 404).
    """
    if key in INTERNAL_KEYS:
        return None  # router devolve 404 — chave interna não é editável

    row = db.query(AppSetting).filter_by(key=key).one_or_none()
    if row is None:
        return None

    value_to_store: Optional[str]

    is_empty = raw_value is None or raw_value == ""

    # Valida o valor contra o tipo ANTES de gravar (exceto quando limpando).
    # Sem isso, um valor inválido era salvo e depois ignorado em silêncio na
    # leitura (caía no default), enganando o usuário.
    if not is_empty and not row.is_secret:
        _validate_value(row.value_type, raw_value)  # raise ValueError → 400

    if row.is_secret:
        value_to_store = None if is_empty else encrypt(raw_value)
    else:
        value_to_store = None if is_empty else raw_value

    row.value = value_to_store
    db.commit()
    db.refresh(row)

    # Side-effect: mudar sync_interval_hours → re-agendar o scheduler em runtime.
    # Import aqui dentro pra evitar ciclo de import (scheduler → sync_service → models).
    if key == "sync_interval_hours" and value_to_store:
        try:
            from app.core import scheduler
            scheduler.reschedule(int(value_to_store))
        except (ValueError, ImportError):
            pass

    return _to_read(row)
