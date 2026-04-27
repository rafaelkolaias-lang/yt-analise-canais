"""
Service layer para app_settings.

Regras:
  - Para `is_secret=True`, o `value` no banco é cifrado com Fernet.
  - Leitura NUNCA retorna o valor em texto plano — só `mask()`.
  - Escrita cifra antes de persistir. `value` vazio/None → limpa o campo.
  - `has_value` sempre reflete se existe algo persistido (mesmo que cifrado).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.crypto import encrypt, mask
from app.models import AppSetting
from app.schemas.settings import AppSettingRead
from app.services.settings_help import get_help


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
    return [_to_read(r) for r in rows]


def get_setting(db: Session, key: str) -> Optional[AppSettingRead]:
    row = db.query(AppSetting).filter_by(key=key).one_or_none()
    return _to_read(row) if row else None


def update_setting(db: Session, key: str, raw_value: Optional[str]) -> Optional[AppSettingRead]:
    """
    Atualiza `value` de uma setting existente.
    - secrets: cifra antes de persistir; valor vazio/None limpa.
    - normais: salva como texto.
    Retorna None se a key não existir (router devolve 404).
    """
    row = db.query(AppSetting).filter_by(key=key).one_or_none()
    if row is None:
        return None

    value_to_store: Optional[str]

    is_empty = raw_value is None or raw_value == ""

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
