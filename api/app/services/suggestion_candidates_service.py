"""
Candidatos — "pré-monitoramento" automático das melhores sugestões.

Ideia (do usuário): as sugestões fortes não deviam ficar paradas esperando
decisão — o sistema as observa sozinho por um tempo pra ver se confirmam.

Implementação (opção A): o canal sugerido vira uma row normal em `channels`
com `status="candidate"` e `is_active=True` — assim o sync de 12h já tira
snapshots dele com toda a máquina existente (VPD médio, sinal, gráficos).
Candidatos ficam ESCONDIDOS do Monitoramento e do Analytics; aparecem apenas
na página Sugestões, mostrando a evolução desde a entrada em observação.

Ciclo de vida:
  - Auto-add: após cada sync, as top sugestões viram candidatos até encher o
    teto (`suggestions.max_candidates`, default 10).
  - "Monitorar" (promote): vira canal ativo normal.
  - "Dispensar" (dismiss): apaga o canal + blacklist — não volta a ser
    sugerido nem re-observado.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Channel, ChannelBlacklist, ChannelSnapshot
from app.services import monitoring_service, settings_reader, suggestions_service_v2

log = logging.getLogger(__name__)

CANDIDATE_STATUS = "candidate"


def _max_candidates(db: Session) -> int:
    return settings_reader.get_int(db, "suggestions.max_candidates", 10)


def _auto_enabled(db: Session) -> bool:
    return settings_reader.get_bool(db, "suggestions.auto_candidates_enabled", True)


def list_candidates(db: Session) -> list[dict]:
    """
    Candidatos com evolução: primeiro vs último snapshot (VPD médio e
    inscritos). Ordenado pelo maior crescimento de VPD (%) — os que estão
    confirmando sobem pro topo.
    """
    rows = (
        db.query(Channel)
        .filter(Channel.status == CANDIDATE_STATUS)
        .order_by(Channel.created_at.desc())
        .all()
    )
    out: list[dict] = []
    for ch in rows:
        snaps = (
            db.query(ChannelSnapshot)
            .filter(ChannelSnapshot.channel_id == ch.id)
            .order_by(ChannelSnapshot.captured_at.asc())
            .all()
        )
        first = snaps[0] if snaps else None
        last = snaps[-1] if snaps else None

        first_vpd = first.avg_vpd_recent if first else None
        last_vpd = last.avg_vpd_recent if last else None
        vpd_delta_pct: Optional[float] = None
        if first_vpd and last_vpd is not None and first_vpd > 0:
            vpd_delta_pct = round((last_vpd - first_vpd) / first_vpd * 100.0, 1)

        days = max(0, (datetime.utcnow() - ch.created_at).days) if ch.created_at else 0
        out.append(
            {
                "channel_id": ch.id,
                "youtube_channel_id": ch.youtube_channel_id,
                "title": ch.title,
                "url": ch.url,
                "thumbnail_url": ch.thumbnail_url,
                "days_observed": days,
                "snapshots_count": len(snaps),
                "subscribers": last.subscribers if last else None,
                "first_vpd": first_vpd,
                "last_vpd": last_vpd,
                "vpd_delta_pct": vpd_delta_pct,
                "signal": last.signal if last else None,
                "first_snapshot_at": (
                    first.captured_at.isoformat() if first else None
                ),
                "last_snapshot_at": last.captured_at.isoformat() if last else None,
            }
        )

    # Maior crescimento primeiro; sem base de comparação vai pro fim.
    out.sort(
        key=lambda c: (
            c["vpd_delta_pct"] is None,
            -(c["vpd_delta_pct"] or 0),
            -(c["last_vpd"] or 0),
        )
    )
    return out


def promote(db: Session, channel_id: int) -> Channel:
    """Candidato aprovado → vira canal monitorado normal (status=active)."""
    ch = db.query(Channel).filter_by(id=channel_id, status=CANDIDATE_STATUS).one_or_none()
    if ch is None:
        raise LookupError(f"Candidato id={channel_id} não existe.")
    ch.status = "active"
    ch.is_active = True
    ch.source = ch.source or "suggestion_auto"
    db.commit()
    db.refresh(ch)
    return ch


def dismiss(db: Session, channel_id: int) -> None:
    """
    Candidato dispensado → apaga (com histórico) e coloca na blacklist para
    nunca mais ser sugerido nem re-observado.
    """
    ch = db.query(Channel).filter_by(id=channel_id, status=CANDIDATE_STATUS).one_or_none()
    if ch is None:
        raise LookupError(f"Candidato id={channel_id} não existe.")
    yt_id = ch.youtube_channel_id
    db.delete(ch)
    if (
        db.query(ChannelBlacklist).filter_by(youtube_channel_id=yt_id).one_or_none()
        is None
    ):
        db.add(ChannelBlacklist(youtube_channel_id=yt_id, reason="suggestion_dismissed"))
    db.commit()


def dismiss_suggestion(db: Session, youtube_channel_id: str) -> bool:
    """
    Dispensa uma sugestão que AINDA não virou candidato: só blacklist.
    Retorna False se já estava na blacklist.
    """
    existing = (
        db.query(ChannelBlacklist)
        .filter_by(youtube_channel_id=youtube_channel_id)
        .one_or_none()
    )
    if existing is not None:
        return False
    db.add(
        ChannelBlacklist(
            youtube_channel_id=youtube_channel_id, reason="suggestion_dismissed"
        )
    )
    db.commit()
    return True


def auto_add_from_suggestions(db: Session) -> int:
    """
    Preenche as vagas de candidato com as top sugestões atuais. Chamado após
    cada sync (tolerante a falha — nunca derruba o sync). Retorna quantos
    canais entraram em observação.

    Cada admissão custa ~4 units de cota (dados do canal + snapshot inicial),
    limitado pelo teto de vagas — irrelevante perto da cota diária.
    """
    if not _auto_enabled(db):
        return 0

    current = (
        db.query(Channel).filter(Channel.status == CANDIDATE_STATUS).count()
    )
    slots = _max_candidates(db) - current
    if slots <= 0:
        return 0

    # A lista já vem ordenada do melhor pro pior e já exclui monitorados,
    # candidatos (são rows de Channel) e blacklist.
    suggestions = suggestions_service_v2.list_monitor_suggestions(db, limit=slots * 3)

    added = 0
    for s in suggestions:
        if added >= slots:
            break
        try:
            ch = monitoring_service.add_channel(db, s["youtube_channel_id"])
            if ch.status != CANDIDATE_STATUS:
                ch.status = CANDIDATE_STATUS
                ch.is_active = True
                ch.source = "suggestion_auto"
                db.commit()
            # Snapshot imediato: ancora a linha de base da observação já na
            # admissão (senão só no próximo sync, 12h depois).
            try:
                monitoring_service.snapshot_channel(db, ch.id)
            except Exception:  # noqa: BLE001 — baseline pode esperar o sync
                db.rollback()
            added += 1
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "[candidates] falha ao admitir %s: %s",
                s.get("youtube_channel_id"),
                exc,
            )
            try:
                db.rollback()
            except Exception:
                pass
    if added:
        log.info("[candidates] %d canais entraram em observação", added)
    return added
