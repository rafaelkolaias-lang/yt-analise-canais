"""
Router /api/notifications — central de notificações da UI.

Dois grupos de endpoint:
  - `/quota-summary` (legado, mantido) — resumo agregado da cota YouTube. NÃO
    é evento, é estado; será movido pra sidebar na Fase 2.
  - `/` e `/{id}/...` — CRUD de notificações persistentes (tabela
    `notifications`). Eventos históricos com badge, leitura, dispensa.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.notifications import (
    NotificationOpResponse,
    NotificationRead,
    NotificationsListResponse,
    QuotaSummary,
    UnreadCountResponse,
)
from app.services import notifications_service, youtube_client

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ---------------------------------------------------------------------------
# Quota (legado — vira sidebar na Fase 2)
# ---------------------------------------------------------------------------
@router.get("/quota-summary", response_model=QuotaSummary)
def get_quota_summary(db: Session = Depends(get_db)) -> QuotaSummary:
    """
    Resumo agregado da cota da YouTube API somando todas as keys cadastradas.
    Lê só o estado persistido em `app_settings.youtube.quota_usage_today` —
    não dispara nenhuma chamada externa.
    """
    return QuotaSummary(**youtube_client.read_quota_summary(db))


# ---------------------------------------------------------------------------
# Notificações persistentes
# ---------------------------------------------------------------------------
@router.get("", response_model=NotificationsListResponse)
def list_notifications(
    limit: int = 50,
    db: Session = Depends(get_db),
) -> NotificationsListResponse:
    """Lista notificações não-dispensadas, mais recentes primeiro."""
    items = notifications_service.list_visible(db, limit=limit)
    return NotificationsListResponse(
        items=[NotificationRead.model_validate(it) for it in items],
        unread_count=notifications_service.unread_count(db),
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
def get_unread_count(db: Session = Depends(get_db)) -> UnreadCountResponse:
    """Conta notificações não-lidas — endpoint leve para o badge do sino."""
    return UnreadCountResponse(unread_count=notifications_service.unread_count(db))


@router.post("/{notification_id}/read", response_model=NotificationOpResponse)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
) -> NotificationOpResponse:
    changed = notifications_service.mark_read(db, notification_id)
    return NotificationOpResponse(id=notification_id, changed=changed)


@router.post("/read-all", response_model=NotificationOpResponse)
def mark_all_read(db: Session = Depends(get_db)) -> NotificationOpResponse:
    count = notifications_service.mark_all_read(db)
    return NotificationOpResponse(id=0, changed=count > 0)


@router.post("/{notification_id}/dismiss", response_model=NotificationOpResponse)
def dismiss_notification(
    notification_id: int,
    db: Session = Depends(get_db),
) -> NotificationOpResponse:
    changed = notifications_service.dismiss(db, notification_id)
    return NotificationOpResponse(id=notification_id, changed=changed)


@router.post("/dismiss-all", response_model=NotificationOpResponse)
def dismiss_all_notifications(db: Session = Depends(get_db)) -> NotificationOpResponse:
    count = notifications_service.dismiss_all(db)
    return NotificationOpResponse(id=0, changed=count > 0)
