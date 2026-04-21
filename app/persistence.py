# -*- coding: utf-8 -*-
"""Persistência: canais vistos, termos, log de execuções."""
import csv
import json
from datetime import datetime

from . import config


def load_seen_channels() -> set:
    seen = set()
    if config.SEEN_CHANNELS_CSV.exists():
        with open(config.SEEN_CHANNELS_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("channel_id"):
                    seen.add(row["channel_id"])
    return seen


def append_seen_channels(channels):
    newf = not config.SEEN_CHANNELS_CSV.exists()
    with open(config.SEEN_CHANNELS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["channel_id", "channel_title", "first_seen"])
        if newf:
            w.writeheader()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for ch_id, title in channels:
            w.writerow({"channel_id": ch_id, "channel_title": title or "", "first_seen": now})


def load_terms():
    if config.TERMS_JSON.exists():
        with open(config.TERMS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "base": _SEED_TERMS,
        "learned": [],
        "last_updated": None,
    }


def save_terms(obj):
    with open(config.TERMS_JSON, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def log_run(stats: dict):
    newf = not config.RUNS_CSV.exists()
    with open(config.RUNS_CSV, "a", newline="", encoding="utf-8") as f:
        cols = ["when", "new_channels", "min_views", "janela_dias", "quota_used", "modes_mix", "terms_used"]
        w = csv.DictWriter(f, fieldnames=cols)
        if newf:
            w.writeheader()
        w.writerow({
            "when": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "new_channels": stats.get("new_channels"),
            "min_views": stats.get("min_views"),
            "janela_dias": stats.get("janela_dias"),
            "quota_used": stats.get("quota_used"),
            "modes_mix": stats.get("modes_mix"),
            "terms_used": "; ".join(stats.get("terms_used", []))[:300],
        })


_SEED_TERMS = [
    # Gerais (PT)
    "tutorial", "review", "como fazer", "curso", "dica", "guia",
    "passo a passo", "explicado", "entrevista", "podcast", "análise",
    "para iniciantes", "completo", "do zero", "vlog",
    # Gerais (EN)
    "tutorial", "review", "how to", "guide", "tips", "explained",
    "for beginners", "beginners guide", "full course", "masterclass",
    "interview", "podcast", "analysis", "breakdown", "walkthrough",
    # Gerais (ES)
    "tutorial", "reseña", "cómo hacer", "curso", "consejos", "guía",
    "paso a paso", "explicado", "entrevista", "podcast", "análisis",
    "para principiantes", "desde cero", "completo",
]
