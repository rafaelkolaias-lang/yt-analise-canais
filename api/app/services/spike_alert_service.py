"""
Alerta de pico de views por canal.

Regra (definida pelo usuário):
  ganho de views nas últimas ~24h >= multiplicador × média diária dos
  ~7 dias anteriores do PRÓPRIO canal (ex.: 2.0 = "cresceu 2x o normal dele").

Como o sync roda a cada N horas (default 12), trabalhamos com os snapshots
disponíveis: o "ganho recente" usa o snapshot mais próximo de 24h atrás
(tolerância 12h–48h) normalizado por dia, e a "média" usa a janela anterior a
ele (mínimo 3 dias de histórico).

Salvaguardas:
  - Cooldown de 24h por canal (`channels.spike_last_alert_at`) — sem spam.
  - Piso de 100 views/dia na média: canal parado não dispara com qualquer
    migalha de crescimento.
  - Tudo é chamado via `safe_check_channel` dentro do sync — falha aqui NUNCA
    derruba a sincronização.

O alerta vira uma Notification `type="view_spike"` (uma row nova por evento —
histórico preservado; o cooldown limita o volume). O metadata carrega o canal
e um `link` pro Analytics — consumido pelo card da central e pelo app do
Windows (popup clicável).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models import Channel, ChannelSnapshot
from app.services import notifications_service

log = logging.getLogger(__name__)

_COOLDOWN = timedelta(hours=24)

# Janela do "ganho recente": snapshot base mais próximo de 24h atrás, aceito
# entre 12h e 48h (sync de 12h em 12h nunca tem um ponto exato de 24h).
_RECENT_TARGET = timedelta(hours=24)
_RECENT_MIN = timedelta(hours=12)
_RECENT_MAX = timedelta(hours=48)

# Janela da média histórica: do snapshot base até ~7 dias antes dele.
# Exige pelo menos 3 dias de span pra média ter significado.
_BASELINE_TARGET = timedelta(days=7)
_BASELINE_MIN_SPAN_DAYS = 3.0

# Piso da média diária (views/dia). Canal sem crescimento histórico não pode
# ter média ~0 — senão qualquer ganho dispararia o alerta.
_BASELINE_FLOOR_VPD = 100.0


def _fmt_int(n: float) -> str:
    """1234567 → '1.234.567' (padrão pt-BR)."""
    return f"{int(round(n)):,}".replace(",", ".")


def _closest_to(
    snapshots: list[ChannelSnapshot], target: datetime
) -> Optional[ChannelSnapshot]:
    if not snapshots:
        return None
    return min(snapshots, key=lambda s: abs((s.captured_at - target).total_seconds()))


def check_channel(db: Session, channel: Channel) -> Optional[dict]:
    """
    Avalia o canal e, se houver pico, cria a Notification e atualiza o
    cooldown. Retorna dict com os números do pico, ou None se não disparou.
    """
    if not channel.spike_alert_enabled:
        return None

    now = datetime.utcnow()
    if channel.spike_last_alert_at is not None and (
        now - channel.spike_last_alert_at
    ) < _COOLDOWN:
        return None

    multiplier = float(channel.spike_alert_multiplier or 2.0)
    if multiplier <= 1.0:
        multiplier = 1.0

    # Snapshots com views dos últimos ~9 dias, mais recente primeiro.
    since = now - (_BASELINE_TARGET + _RECENT_MAX)
    snaps = (
        db.query(ChannelSnapshot)
        .filter(
            ChannelSnapshot.channel_id == channel.id,
            ChannelSnapshot.captured_at >= since,
            ChannelSnapshot.views_total.isnot(None),
        )
        .order_by(ChannelSnapshot.captured_at.desc())
        .all()
    )
    if len(snaps) < 3:
        return None

    latest = snaps[0]

    # Ponto base do ganho recente: mais próximo de 24h antes do latest.
    recent_candidates = [
        s
        for s in snaps[1:]
        if _RECENT_MIN
        <= (latest.captured_at - s.captured_at)
        <= _RECENT_MAX
    ]
    base24 = _closest_to(recent_candidates, latest.captured_at - _RECENT_TARGET)
    if base24 is None:
        return None

    recent_span_days = (latest.captured_at - base24.captured_at).total_seconds() / 86400.0
    if recent_span_days <= 0:
        return None
    gain_recent = (latest.views_total or 0) - (base24.views_total or 0)
    gain_daily_recent = gain_recent / recent_span_days
    if gain_daily_recent <= 0:
        return None

    # Ponto antigo da média: mais próximo de 7 dias antes do base24, com span
    # mínimo de 3 dias.
    old_candidates = [
        s
        for s in snaps
        if (base24.captured_at - s.captured_at).total_seconds() / 86400.0
        >= _BASELINE_MIN_SPAN_DAYS
    ]
    old = _closest_to(old_candidates, base24.captured_at - _BASELINE_TARGET)
    if old is None:
        return None

    baseline_span_days = (base24.captured_at - old.captured_at).total_seconds() / 86400.0
    baseline_daily = ((base24.views_total or 0) - (old.views_total or 0)) / baseline_span_days

    # Média negativa ou zero = canal PERDEU views na janela (vídeos apagados/
    # privados, limpeza do YouTube). Não há base honesta de comparação — sem
    # ela o piso de 100 viraria divisor fictício e qualquer ganho normal
    # dispararia como "milhares de x" (alerta falso). Nesse caso, não dispara.
    if baseline_daily <= 0:
        return None

    # Piso só pro caso original: canal parado com média positiva minúscula.
    baseline_eff = max(baseline_daily, _BASELINE_FLOOR_VPD)

    ratio = gain_daily_recent / baseline_eff
    if ratio < multiplier:
        return None

    ratio_txt = f"{ratio:.1f}".replace(".", ",")
    result = {
        "channel_id": channel.id,
        "youtube_channel_id": channel.youtube_channel_id,
        "channel_title": channel.title,
        "thumbnail_url": channel.thumbnail_url,
        "ratio": round(ratio, 2),
        "multiplier": multiplier,
        "gain_24h": int(gain_recent),
        "gain_daily_recent": round(gain_daily_recent, 1),
        "baseline_daily": round(baseline_daily, 1),
        # Média efetivamente usada no ratio (com piso aplicado) — é ela que a
        # mensagem exibe, senão os números do alerta não fecham entre si.
        "baseline_used": round(baseline_eff, 1),
        # Deep-link consumido pelo card da central e pelo app do Windows.
        "link": f"/analytics?q={quote(channel.title)}",
    }

    notifications_service.safe_upsert(
        db,
        type="view_spike",
        status="info",
        title=f"Pico de views: {channel.title}",
        message=(
            f"Ganhou {_fmt_int(gain_recent)} views nas últimas 24h — "
            f"{ratio_txt}x a média diária dos 7 dias anteriores "
            f"({_fmt_int(baseline_eff)} views/dia)."
        ),
        metadata=result,
        # Sem source_key: cada pico é um evento novo (o cooldown segura o volume).
    )

    channel.spike_last_alert_at = now
    db.commit()
    log.info(
        "[spike] canal id=%s '%s': %.1fx (gatilho %.1fx)",
        channel.id,
        channel.title[:40],
        ratio,
        multiplier,
    )
    return result


def safe_check_channel(db: Session, channel: Channel) -> Optional[dict]:
    """check_channel que engole qualquer exceção (uso dentro do sync)."""
    try:
        return check_channel(db, channel)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "[spike] checagem falhou para canal id=%s: %s",
            getattr(channel, "id", "?"),
            exc,
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return None
