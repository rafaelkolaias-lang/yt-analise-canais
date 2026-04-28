"""
Gerenciamento individual das chaves da YouTube Data API.

Modelo de armazenamento:
  - `app_settings.youtube.api_keys` continua sendo a CSV/multilinha cifrada
    (Fernet) com todas as chaves cadastradas, na ordem em que foram inseridas.
    Um único campo, sem migration de schema.
  - `app_settings.youtube.api_keys_burned` é um JSON NÃO cifrado com o estado
    "queimada" indexado por fingerprint:
        { "<fp>": { "at": "<ISO>", "reason": "keyInvalid|other", "label": "..." } }
    Não cifrar é seguro porque guarda apenas o fingerprint (hash truncado),
    nunca a chave em texto plano.

Identidade:
  - `fingerprint` = primeiros 16 hex de SHA-256 da chave. Estável e curto.
  - Mesmo cálculo usado em `youtube_client.py` (mantido em sincronia).

Status (derivado, não persistido):
  - `burned`           → presente em `youtube.api_keys_burned`.
  - `quota_exhausted`  → não queimada e `used_today >= daily_quota`.
  - `ok`               → não queimada e ainda com saldo.

Notas de UX:
  - Adicionar uma chave que já existe é idempotente (devolve a entry existente
    sem duplicar).
  - Remover uma chave também remove qualquer marca de queimada associada
    (impede que volte queimada se for readicionada depois).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt, mask
from app.models import AppSetting

API_KEYS_SETTING = "youtube.api_keys"
BURNED_SETTING = "youtube.api_keys_burned"
DAILY_QUOTA_SETTING = "youtube.api_key_daily_quota"
QUOTA_USAGE_SETTING = "youtube.quota_usage_today"

_FP_LEN = 16


def fingerprint(key: str) -> str:
    """Identidade estável da chave sem expor o segredo. Mesmo cálculo do client."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:_FP_LEN]


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def _split_keys(decrypted: str) -> list[str]:
    """Aceita CSV (`a,b`) ou multilinha (`a\\nb`). Mesma regra do client."""
    return [
        k.strip()
        for k in decrypted.replace("\r\n", "\n").replace(",", "\n").split("\n")
        if k.strip()
    ]


def _read_keys_row(db: Session) -> Optional[AppSetting]:
    return db.query(AppSetting).filter_by(key=API_KEYS_SETTING).one_or_none()


def list_keys_plaintext(db: Session) -> list[str]:
    """
    Devolve as chaves em texto plano, mantendo a ordem de inserção.
    Para uso interno do youtube_client. NUNCA expor pela API HTTP.
    """
    row = _read_keys_row(db)
    if not row or not row.value:
        return []
    try:
        return _split_keys(decrypt(row.value))
    except Exception:  # pragma: no cover
        return []


def _load_burned(db: Session) -> dict[str, dict]:
    row = db.query(AppSetting).filter_by(key=BURNED_SETTING).one_or_none()
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def _save_burned(db: Session, data: dict[str, dict]) -> None:
    """Persiste o mapa de queimadas. Cria a row se não existir."""
    row = db.query(AppSetting).filter_by(key=BURNED_SETTING).one_or_none()
    value = json.dumps(data, separators=(",", ":")) if data else "{}"
    if row is None:
        db.add(
            AppSetting(
                key=BURNED_SETTING,
                value=value,
                value_type="json",
                is_secret=False,
                description="Estado interno: chaves YouTube marcadas como queimadas (não mexa).",
            )
        )
    else:
        row.value = value
    db.commit()


def _read_daily_quota(db: Session) -> int:
    row = db.query(AppSetting).filter_by(key=DAILY_QUOTA_SETTING).one_or_none()
    if row and row.value:
        try:
            return int(row.value)
        except ValueError:
            pass
    return 10000


def _today_utc_str() -> str:
    """Mesma regra de `youtube_client._today_utc_str` — sincronia obrigatoria."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_used_by_fp(db: Session) -> dict[str, int]:
    """
    Le `youtube.quota_usage_today` aplicando rollover UTC. Se o `date_utc`
    salvo for diferente do dia UTC atual, devolve {} — caso contrario, sidebar
    e lista individual divergem (sidebar via `_load_persisted_state` ja zera
    no rollover, mas aqui o uso de ontem persistia e marcava chaves como
    `quota_exhausted` indevidamente).
    """
    row = db.query(AppSetting).filter_by(key=QUOTA_USAGE_SETTING).one_or_none()
    if not row or not row.value:
        return {}
    try:
        payload = json.loads(row.value)
    except (TypeError, ValueError):
        return {}

    # Rollover UTC: estado de outro dia nao conta. Mesma logica do
    # `youtube_client._load_persisted_state`.
    saved_date = str(payload.get("date_utc") or "")
    if saved_date and saved_date != _today_utc_str():
        return {}

    # Formato novo
    new = payload.get("used_by_fingerprint")
    if isinstance(new, dict):
        return {str(k): int(v) for k, v in new.items() if isinstance(v, (int, float))}
    return {}


# ---------------------------------------------------------------------------
# Escrita da lista de chaves
# ---------------------------------------------------------------------------
def _write_keys(db: Session, keys: list[str]) -> None:
    """Persiste a lista cifrada (multilinha)."""
    encrypted = encrypt("\n".join(keys)) if keys else None
    row = _read_keys_row(db)
    if row is None:
        db.add(
            AppSetting(
                key=API_KEYS_SETTING,
                value=encrypted,
                value_type="secret",
                is_secret=True,
                description="8.1 — Chaves da YouTube Data API v3 (uma por linha). Cifradas no banco.",
            )
        )
    else:
        row.value = encrypted
    db.commit()


# ---------------------------------------------------------------------------
# API pública usada pelo router
# ---------------------------------------------------------------------------
def list_keys(db: Session) -> list[dict]:
    """
    Lista todas as chaves cadastradas com status derivado.
    Não expõe a chave em texto plano — só `masked` e `fingerprint`.
    """
    keys = list_keys_plaintext(db)
    burned = _load_burned(db)
    used_by_fp = _read_used_by_fp(db)
    daily_quota = _read_daily_quota(db)

    out: list[dict] = []
    for index, k in enumerate(keys):
        fp = fingerprint(k)
        burned_entry = burned.get(fp)
        used_today = int(used_by_fp.get(fp, 0))
        if burned_entry:
            status = "burned"
        elif used_today >= daily_quota:
            status = "quota_exhausted"
        else:
            status = "ok"
        out.append(
            {
                "fingerprint": fp,
                "masked": mask(k, visible=4),
                "index": index,
                "status": status,
                "used_today": used_today,
                "daily_quota": daily_quota,
                "burned_at": burned_entry.get("at") if burned_entry else None,
                "burned_reason": burned_entry.get("reason") if burned_entry else None,
                "burned_label": burned_entry.get("label") if burned_entry else None,
            }
        )
    return out


def add_key(db: Session, raw_key: str) -> Tuple[dict, bool]:
    """
    Adiciona uma chave nova ao final da lista. Idempotente: se já existe (mesmo
    fingerprint), devolve a entry atual sem duplicar.

    Retorna (entry, created) onde created=True indica que foi inserida agora.
    """
    raw_key = raw_key.strip()
    if not raw_key:
        raise ValueError("chave vazia")

    keys = list_keys_plaintext(db)
    fp_new = fingerprint(raw_key)
    existing_fps = {fingerprint(k) for k in keys}

    created = fp_new not in existing_fps
    if created:
        keys.append(raw_key)
        _write_keys(db, keys)

    # Devolve a entry com status atualizado
    for entry in list_keys(db):
        if entry["fingerprint"] == fp_new:
            return entry, created
    raise RuntimeError("entry não encontrada após gravar (estado inconsistente)")


def remove_key(db: Session, fp: str) -> bool:
    """
    Remove a chave identificada por `fp`. Também limpa qualquer marca de
    queimada associada — assim, se a mesma chave for readicionada depois,
    começa "limpa".

    Retorna True se removeu algo.
    """
    keys = list_keys_plaintext(db)
    new_keys = [k for k in keys if fingerprint(k) != fp]
    removed_key = len(new_keys) != len(keys)
    if removed_key:
        _write_keys(db, new_keys)

    burned = _load_burned(db)
    if fp in burned:
        burned.pop(fp, None)
        _save_burned(db, burned)
        return True

    return removed_key


def mark_burned(
    db: Session,
    fp: str,
    *,
    reason: str = "other",
    label: Optional[str] = None,
) -> None:
    """
    Marca a chave como queimada. Idempotente — chamar várias vezes não duplica.

    Usado pelo `youtube_client` quando recebe HTTP 400 keyInvalid (e variantes),
    pra que a próxima request já pule essa chave automaticamente.
    """
    burned = _load_burned(db)
    burned[fp] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "label": label or reason,
    }
    _save_burned(db, burned)


def unburn_key(db: Session, fp: str) -> bool:
    """Remove a marca de queimada da chave. Retorna True se havia algo pra tirar."""
    burned = _load_burned(db)
    if fp in burned:
        burned.pop(fp, None)
        _save_burned(db, burned)
        return True
    return False


def list_burned_fingerprints(db: Session) -> set[str]:
    """Conjunto de fingerprints atualmente marcadas como queimadas."""
    return set(_load_burned(db).keys())


def count_burned(db: Session) -> int:
    """Quantas chaves estão marcadas como queimadas no momento."""
    return len(_load_burned(db))


def health_summary(db: Session) -> dict:
    """
    Resumo agregado de saúde das chaves, para a central de notificações.
    Conta status derivado e devolve o último evento de queima conhecido.
    """
    entries = list_keys(db)
    counts = {"ok": 0, "quota_exhausted": 0, "burned": 0}
    last_burned_at: Optional[str] = None
    last_burned_reason: Optional[str] = None
    for entry in entries:
        st = entry["status"]
        counts[st] = counts.get(st, 0) + 1
        if st == "burned":
            at = entry.get("burned_at")
            if at and (last_burned_at is None or at > last_burned_at):
                last_burned_at = at
                last_burned_reason = entry.get("burned_reason")
    return {
        "total": len(entries),
        "ok": counts["ok"],
        "quota_exhausted": counts["quota_exhausted"],
        "burned": counts["burned"],
        "last_burned_at": last_burned_at,
        "last_burned_reason": last_burned_reason,
    }
