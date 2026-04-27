"""
Service para a tabela `notifications`.

Modelo mental:
  - Cada row é um EVENTO histórico (sync rodou, descoberta detectou algo,
    erro persistente, etc.). Não é estado — é ocorrência.
  - `source_key` identifica eventos que devem ser ATUALIZADOS em vez de
    duplicados. Ex: durante um sync manual, `source_key="sync_manual:42"`
    permite que o progresso seja atualizado na mesma row.
  - Se você não passa `source_key`, sempre cria uma nova row.

Convenções:
  - status="running" + type="task_progress" → barra de progresso ativa.
  - status="success" + type="task_done"     → operação ok.
  - status="error"   + type="task_error"    → falha ou parcial.
  - status="info"    + type="system_alert"  → mensagem genérica.
  - status="info"    + type="suggestions_changed" → novas sugestões detectadas.

Cap de "rows visíveis":
  - O usuário pediu cap de 20 não-dispensadas (FIFO). Em `_enforce_cap` a
    cada criação, dispensamos automaticamente as mais antigas além do limite.
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Notification

# Tamanho maximo do traceback embutido em metadata.error. ~6KB cobre stack
# tipico sem inflar `notifications.metadata_json`.
_ERROR_DETAIL_MAX = 6000

log = logging.getLogger(__name__)

# Quantas notificações NÃO-DISPENSADAS o usuário vê por vez.
VISIBLE_CAP = 20


# ---------------------------------------------------------------------------
# Internas
# ---------------------------------------------------------------------------
def _enforce_cap(db: Session) -> None:
    """
    Mantém no máximo VISIBLE_CAP rows não-dispensadas. As mais antigas além do
    limite são auto-dispensadas (não deletadas — a auditoria fica preservada).
    """
    rows = (
        db.query(Notification)
        .filter(Notification.dismissed_at.is_(None))
        .order_by(Notification.created_at.desc())
        .all()
    )
    if len(rows) <= VISIBLE_CAP:
        return
    excess = rows[VISIBLE_CAP:]
    now = datetime.utcnow()
    for row in excess:
        row.dismissed_at = now
    db.flush()


def _serialize_metadata(metadata: Optional[dict]) -> Optional[str]:
    if metadata is None:
        return None
    try:
        return json.dumps(metadata, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Criação / atualização (upsert por source_key)
# ---------------------------------------------------------------------------
def upsert(
    db: Session,
    *,
    type: str,
    status: str,
    title: str,
    message: Optional[str] = None,
    progress_pct: Optional[int] = None,
    metadata: Optional[dict] = None,
    source_key: Optional[str] = None,
) -> Notification:
    """
    Cria ou atualiza uma notificação.

    - Se `source_key` é fornecido E já existe uma row NÃO-DISPENSADA com a
      mesma source_key, ela é atualizada (resetando read_at, pois virou novidade).
    - Caso contrário, cria nova.

    Tolerante a falha — qualquer exceção é logada e retorna None implicitamente
    (o caller decide se isso é fatal ou cosmético).
    """
    existing: Optional[Notification] = None
    if source_key:
        existing = (
            db.query(Notification)
            .filter(
                Notification.source_key == source_key,
                Notification.dismissed_at.is_(None),
            )
            .order_by(Notification.created_at.desc())
            .first()
        )

    metadata_json = _serialize_metadata(metadata)

    if existing is not None:
        existing.type = type
        existing.status = status
        existing.title = title
        if message is not None:
            existing.message = message
        if progress_pct is not None:
            existing.progress_pct = progress_pct
        if metadata_json is not None:
            existing.metadata_json = metadata_json
        # Atualização vira novidade pra UI: reabre o estado de não-lida.
        existing.read_at = None
        db.commit()
        db.refresh(existing)
        return existing

    row = Notification(
        type=type,
        status=status,
        title=title,
        message=message,
        progress_pct=progress_pct,
        metadata_json=metadata_json,
        source_key=source_key,
    )
    db.add(row)
    db.flush()
    _enforce_cap(db)
    db.commit()
    db.refresh(row)
    return row


def create(
    db: Session,
    *,
    type: str,
    status: str,
    title: str,
    message: Optional[str] = None,
    progress_pct: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> Notification:
    """Atalho para upsert sem source_key (= sempre cria nova)."""
    return upsert(
        db,
        type=type,
        status=status,
        title=title,
        message=message,
        progress_pct=progress_pct,
        metadata=metadata,
        source_key=None,
    )


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def list_visible(db: Session, limit: int = 50) -> list[Notification]:
    """Lista notificações não-dispensadas, mais recentes primeiro."""
    return (
        db.query(Notification)
        .filter(Notification.dismissed_at.is_(None))
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )


def unread_count(db: Session) -> int:
    """Conta notificações não-lidas E não-dispensadas (pra badge do sino)."""
    return (
        db.query(Notification)
        .filter(
            Notification.dismissed_at.is_(None),
            Notification.read_at.is_(None),
        )
        .count()
    )


# ---------------------------------------------------------------------------
# Mutação por id
# ---------------------------------------------------------------------------
def mark_read(db: Session, notification_id: int) -> bool:
    row = db.query(Notification).filter_by(id=notification_id).one_or_none()
    if row is None or row.read_at is not None:
        return False
    row.read_at = datetime.utcnow()
    db.commit()
    return True


def mark_all_read(db: Session) -> int:
    rows = (
        db.query(Notification)
        .filter(
            Notification.dismissed_at.is_(None),
            Notification.read_at.is_(None),
        )
        .all()
    )
    now = datetime.utcnow()
    for row in rows:
        row.read_at = now
    if rows:
        db.commit()
    return len(rows)


def dismiss(db: Session, notification_id: int) -> bool:
    row = db.query(Notification).filter_by(id=notification_id).one_or_none()
    if row is None or row.dismissed_at is not None:
        return False
    row.dismissed_at = datetime.utcnow()
    if row.read_at is None:
        row.read_at = row.dismissed_at
    db.commit()
    return True


def dismiss_all(db: Session) -> int:
    rows = (
        db.query(Notification)
        .filter(Notification.dismissed_at.is_(None))
        .all()
    )
    now = datetime.utcnow()
    for row in rows:
        row.dismissed_at = now
        if row.read_at is None:
            row.read_at = now
    if rows:
        db.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# Helper "tolerante" para uso em código de produção
# ---------------------------------------------------------------------------
def safe_upsert(
    db: Session,
    **kwargs: Any,
) -> Optional[Notification]:
    """
    Mesmo `upsert`, mas engole qualquer exceção. Para chamada a partir de
    código onde a notificação é cosmética (ex: dentro do sync) e nunca deve
    derrubar a operação principal.
    """
    try:
        return upsert(db, **kwargs)
    except Exception as exc:  # pragma: no cover
        # exc_info=True garante stack completo no container — necessário pra
        # diagnosticar quebra da própria tabela de notificações (caso em que
        # o canal de aviso primário fica cego e só sobra log estruturado).
        log.warning("notifications.safe_upsert falhou: %s", exc, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Alerta operacional (falha não-fatal em job/serviço)
# ---------------------------------------------------------------------------
def _build_error_metadata(
    exc: BaseException, extra: Optional[dict] = None
) -> dict:
    """
    Constrói o metadata padrão de um alerta operacional embutindo:
      - `error_type`: nome da classe da exceção (ex: `OperationalError`).
      - `error`: `repr(exc)` curto (linha única) — bom pra ler no card.
      - `traceback`: stack completo formatado (até `_ERROR_DETAIL_MAX` chars),
        consumido pelo botão "Ver detalhes" no frontend.

    Mantém entradas em `extra` (`phase`, `sync_run_id`, `fingerprint`, …) sem
    sobrescrever as chaves padrão.
    """
    tb = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    if len(tb) > _ERROR_DETAIL_MAX:
        # Mantém o final do stack (onde está o frame que estourou) e marca
        # truncamento.
        tb = "[...truncado...]\n" + tb[-_ERROR_DETAIL_MAX:]
    out: dict = {
        "error_type": type(exc).__name__,
        "error": repr(exc)[:500],
        "traceback": tb,
    }
    if extra:
        for k, v in extra.items():
            out.setdefault(k, v)
    return out


def safe_system_alert(
    db: Session,
    *,
    source_key: str,
    title: str,
    message: Optional[str] = None,
    metadata: Optional[dict] = None,
    status: str = "error",
    exc: Optional[BaseException] = None,
) -> Optional[Notification]:
    """
    Cria/atualiza uma notificação `type="system_alert"` para falhas operacionais
    não-fatais (auto-discovery, scheduler, persistência de cota, etc.).

    `source_key` deve ser estável por área de falha (ex: `ops:auto_discovery_failed`)
    pra evitar spam: mesma falha repetida atualiza a mesma row em vez de criar
    uma nova a cada ciclo.

    Quando `exc` é passada, o metadata é enriquecido automaticamente com
    `error_type`, `error` (repr curto) e `traceback` completo — o frontend
    consome essas chaves no botão "Ver detalhes". `metadata` extra é mesclado
    sem sobrescrever as chaves padrão.

    Engole qualquer exceção — esta função é ela mesma um caminho de resiliência
    e não pode derrubar o fluxo que a chamou.
    """
    final_metadata: Optional[dict]
    if exc is not None:
        final_metadata = _build_error_metadata(exc, extra=metadata)
    else:
        final_metadata = metadata

    return safe_upsert(
        db,
        type="system_alert",
        status=status,
        title=title,
        message=message,
        metadata=final_metadata,
        source_key=source_key,
    )
