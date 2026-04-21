# -*- coding: utf-8 -*-
"""Monitoramento diário automático: roda update_monitored no 1º login do dia e avisa só se houver novidades."""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from . import config
from . import results_store


DAILY_STATE_PATH = config.DATA_DIR / "daily_state.json"

# Limiares para considerar "novidade"
TREND_ACCEL = 1.20
MIN_DELTA_SUBS = 100
MIN_RECENT_VELOCITY = 500


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load_state() -> dict:
    if not DAILY_STATE_PATH.exists():
        return {"last_run": None}
    try:
        with open(DAILY_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_run": None}


def _save_state(state: dict):
    DAILY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=DAILY_STATE_PATH.name, dir=str(DAILY_STATE_PATH.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(DAILY_STATE_PATH))
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def should_run_today() -> bool:
    return _load_state().get("last_run") != _today()


def mark_ran_today():
    state = _load_state()
    state["last_run"] = _today()
    state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save_state(state)


def _summarize_snapshot(snapshot):
    """Extrai novidades relevantes do snapshot. Retorna (highlights_list, totals_dict)."""
    if not snapshot:
        return [], {"channels": 0, "videos": 0}

    channels = snapshot.get("channels", []) or []
    videos = snapshot.get("videos", []) or []

    highlights = []
    for c in channels:
        trend = c.get("vpd_trend") or 0
        delta_subs = c.get("delta_subscribers") or 0
        signal = c.get("signal") or ""
        title = c.get("title") or c.get("channel_id", "?")

        if signal in ("Aquecendo", "Promissor"):
            highlights.append(f"🔥 {signal}: {title}")
        elif trend >= TREND_ACCEL:
            highlights.append(f"📈 Tendência VPD {trend:.2f}× em {title}")
        elif delta_subs >= MIN_DELTA_SUBS:
            highlights.append(f"👥 +{delta_subs} inscritos em {title}")

    for v in videos:
        vel = v.get("recent_velocity") or 0
        title = v.get("title") or v.get("video_id", "?")
        if vel >= MIN_RECENT_VELOCITY:
            highlights.append(f"🚀 {int(vel)} views/dia no vídeo: {title[:60]}")

    return highlights, {"channels": len(channels), "videos": len(videos)}


def show_notification(highlights, totals, on_open_app, on_close):
    """Mostra janela Tk com novidades e botões 'Abrir programa' / 'OK'."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Monitoramento diário — YouTube Discovery")
    root.geometry("560x420")
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    root.resizable(False, False)

    frm = ttk.Frame(root, padding=14)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="Canais / vídeos monitorados",
              font=("Segoe UI", 13, "bold")).pack(anchor="w")
    ttk.Label(
        frm,
        text=f"Checados: {totals['channels']} canal(is) e {totals['videos']} vídeo(s).",
        foreground="#888",
    ).pack(anchor="w", pady=(2, 8))

    body = tk.Text(frm, height=12, wrap="word")
    body.pack(fill="both", expand=True)
    if highlights:
        body.insert("1.0", "Novidades encontradas:\n\n" + "\n".join("• " + h for h in highlights))
    else:
        body.insert("1.0", "Nenhuma novidade relevante hoje.\n\n"
                            "Critérios: tendência VPD ≥ 1.20×, Δ inscritos ≥ 100, "
                            f"ou velocidade recente ≥ {MIN_RECENT_VELOCITY} views/dia.")
    body.configure(state="disabled")

    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=(10, 0))

    def _open():
        root.destroy()
        on_open_app()

    def _ok():
        root.destroy()
        on_close()

    ttk.Button(btns, text="Abrir programa", command=_open).pack(side="left", padx=4)
    ttk.Button(btns, text="OK", command=_ok).pack(side="right", padx=4)

    root.protocol("WM_DELETE_WINDOW", _ok)
    root.mainloop()


def run_if_due(status_cb=None):
    """Ponto de entrada para o modo --daily-check.

    Se já rodou hoje, sai sem fazer nada.
    Senão: roda update_monitored, mostra notificação, marca como rodado.
    """
    def _log(msg):
        if status_cb:
            status_cb(msg)
        else:
            print(msg, flush=True)

    if not should_run_today():
        _log("Monitoramento diário já executado hoje. Nada a fazer.")
        return "already_ran"

    # Se não há monitorados, não gastamos cota
    mon = results_store.load_monitored()
    if not (mon.get("channels") or mon.get("videos")):
        _log("Sem canais/vídeos monitorados. Marcando como rodado e saindo.")
        mark_ran_today()
        return "no_monitored"

    # Import local para evitar ciclo em módulos que não precisam do engine
    from .engine import update_monitored

    _log("🚀 Rodando update_monitored...")
    snapshot = update_monitored(status_cb=_log)
    mark_ran_today()

    highlights, totals = _summarize_snapshot(snapshot)

    # Trava de "novidade": se não tem highlight, pula a notificação
    if not highlights:
        _log("Sem novidades relevantes — notificação suprimida.")
        return "no_news"

    opened = {"value": False}

    def _on_open():
        opened["value"] = True

    def _on_close():
        pass

    show_notification(highlights, totals, _on_open, _on_close)

    if opened["value"]:
        _log("Usuário pediu para abrir o programa.")
        # O main.py cuida de abrir a GUI quando `run_if_due` retorna "open_app"
        return "open_app"
    return "closed"


if __name__ == "__main__":
    sys.exit(0 if run_if_due() else 1)
