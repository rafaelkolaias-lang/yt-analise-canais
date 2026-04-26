"""
Leitura de app_settings com cast de tipo.

Separado de `settings_service` porque aquele é a fachada pública da API (mascara
secrets). Este aqui é a leitura INTERNA que o backend usa pra recuperar valores
reais (incluindo decifragem de secrets quando necessário).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import AppSetting


def _cast(raw: Optional[str], value_type: str, default):
    if raw is None or raw == "":
        return default
    try:
        if value_type == "int":
            return int(raw)
        if value_type == "float":
            return float(raw)
        if value_type == "bool":
            return raw.strip().lower() in ("1", "true", "yes", "on")
    except ValueError:
        return default
    return raw


def get_int(db: Session, key: str, default: int) -> int:
    row = db.query(AppSetting).filter_by(key=key).one_or_none()
    if row is None:
        return default
    return _cast(row.value, row.value_type, default)


def get_float(db: Session, key: str, default: float) -> float:
    row = db.query(AppSetting).filter_by(key=key).one_or_none()
    if row is None:
        return default
    return _cast(row.value, row.value_type, default)


def get_str(db: Session, key: str, default: str) -> str:
    row = db.query(AppSetting).filter_by(key=key).one_or_none()
    if row is None or not row.value:
        return default
    return row.value


def get_csv(db: Session, key: str, default: list[str]) -> list[str]:
    s = get_str(db, key, "")
    if not s:
        return default
    return [part.strip() for part in s.split(",") if part.strip()]


def get_bool(db: Session, key: str, default: bool) -> bool:
    row = db.query(AppSetting).filter_by(key=key).one_or_none()
    if row is None:
        return default
    val = _cast(row.value, "bool", default)
    return bool(val)
