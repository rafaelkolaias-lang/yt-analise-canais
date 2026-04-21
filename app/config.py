# -*- coding: utf-8 -*-
"""Configuração, paths e estado mutável global do app."""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

APP_NAME = "YouTube Discovery (Canais & Métricas)"

# Quando rodando via PyInstaller --onefile, __file__ aponta para uma pasta temporária
# (_MEIxxxxx). Ancora em sys.executable nesse caso para que dados/ fique ao lado do .exe.
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "dados"; DATA_DIR.mkdir(exist_ok=True)
CFG_PATH = DATA_DIR / "config.json"

SEEN_CHANNELS_CSV = DATA_DIR / "canais_listados.csv"
TERMS_JSON = DATA_DIR / "termos.json"
RUNS_CSV = DATA_DIR / "execucoes.csv"

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
QUOTA_COST = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1}

DEFAULT_CONFIG = {
    "REGION_CODE": None,
    "SELECTED_LANGS": ["pt", "es", "en"],
    "QUOTA_BUDGET": 1000,
    "QUOTA_BUDGET_PER_KEY": 8000,
    "REQUEST_PAUSE": 0.10,

    "TARGET_NEW_CHANNELS": 15,
    "BASE_PUBLISHED_AFTER_DAYS": 90,
    "BASE_MAX_CHANNEL_AGE_DAYS": 365,
    "BASE_MIN_CHANNEL_AGE_DAYS": 30,
    "BASE_MIN_DURATION_MIN": 8,
    "BASE_MIN_VIEWS": 5000,
    "BASE_MIN_VPD": 300,
    "VPD_SATURATION": 50000,
    "SEARCH_ORDER": "relevance",
    "MONITOR_CHANNEL_IDS": [],

    "SEARCH_PAGES_PER_TERM": 1,
    "SEARCH_TERMS_PER_RUN": 8,
    "RELATED_EXPLORE_LIMIT": 10,
    "TRENDING_CATEGORIES": [27, 28, 25],

    "UPLOADS_SAMPLE": 6,

    "MIN_CHANNELS_PER_SHEET": 5,

    "ALLOW_REPEATED_AS_LAST_RESORT": False,
    "ALLOW_OLDER_AS_LAST_RESORT": True,
    "OLDER_MAX_CHANNEL_AGE_DAYS": 365,
    "LAST_RESORT_MIN_VIEWS": 5000,
    "FORCE_TOO_OLD_BEFORE_FAILSAFE": True,

    "RAW_EXPORT_MODE": False,
    "RAW_LIMIT": 250,
    "RAW_SORT_BY": "views_per_day",
    "RAW_INCLUDE_TRENDING": True,
    "RAW_INCLUDE_RELATED": False,
    "STRICT_WINDOW_IN_RAW": True,

    "STRICT_LANGUAGE": False,

    "AUTO_EXPORT_EXCEL": False,

    "API_KEYS": [],
}


def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if CFG_PATH.exists():
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg.update(data)
        except Exception:
            pass
    env_keys = os.getenv("YOUTUBE_API_KEYS") or os.getenv("YOUTUBE_API_KEY") or ""
    env_list = [k.strip() for k in env_keys.split(",") if len(k.strip()) >= 20]
    if env_list:
        cfg["API_KEYS"] = env_list
    return cfg


def save_config(cfg: dict):
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def output_xlsx_path():
    return DATA_DIR / f"relatorio_canais_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"


def output_xlsx_raw_path():
    return DATA_DIR / f"videos_raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"


CFG = load_config()
CUSTOM_SEARCH_TERMS = []

API_KEYS = CFG.get("API_KEYS") or []
if not API_KEYS:
    _dflt = os.getenv("YOUTUBE_API_KEY") or ""
    if len(_dflt) >= 20:
        API_KEYS = [_dflt]
_current_key_idx = 0

# Cota rastreada POR KEY. QUOTA_USED é lista paralela a API_KEYS.
# Mantemos também QUOTA_USED_TOTAL para compat com código que lê o total.
QUOTA_USED = [0] * len(API_KEYS)


def quota_budget_per_key() -> int:
    return int(CFG.get("QUOTA_BUDGET_PER_KEY", CFG.get("QUOTA_BUDGET", 1000)))


def quota_total_budget() -> int:
    n = max(1, len(API_KEYS))
    return quota_budget_per_key() * n


def quota_used_total() -> int:
    return sum(QUOTA_USED) if QUOTA_USED else 0


def quota_left_on_key(idx: int) -> int:
    if idx < 0 or idx >= len(QUOTA_USED):
        return 0
    return max(0, quota_budget_per_key() - QUOTA_USED[idx])


def quota_left_total() -> int:
    return max(0, quota_total_budget() - quota_used_total())


def reset_quota():
    """Reseta contadores locais (não afeta o servidor). Chamar no início de cada run."""
    global QUOTA_USED
    QUOTA_USED = [0] * len(API_KEYS)


def resize_quota_for_keys():
    """Redimensiona a lista QUOTA_USED para casar com API_KEYS. Usado quando GUI salva keys novas."""
    global QUOTA_USED
    n = len(API_KEYS)
    if len(QUOTA_USED) == n:
        return
    if len(QUOTA_USED) < n:
        QUOTA_USED = QUOTA_USED + [0] * (n - len(QUOTA_USED))
    else:
        QUOTA_USED = QUOTA_USED[:n]


def quota_left() -> int:
    """Compat: cota total restante (soma sobre todas as keys)."""
    return quota_left_total()


def planned_terms_for_budget(langs_count: int, pages_per_term: int) -> int:
    """Quantos termos cabem no orçamento de cota atual.

    Se SEARCH_TERMS_PER_RUN <= 0 → "programa decide": usa tudo que couber.
    Senão → teto do usuário OU o cap por cota, o que for menor.
    """
    if langs_count <= 0:
        langs_count = 1
    cost_per_term = 100 * langs_count * max(1, pages_per_term)
    user_limit = int(CFG.get("SEARCH_TERMS_PER_RUN", 0) or 0)
    if cost_per_term <= 0:
        return user_limit if user_limit > 0 else 1
    safe_quota = int(quota_left_total() * 0.8)
    cap = max(1, safe_quota // cost_per_term)
    if user_limit <= 0:
        return cap
    return max(1, min(user_limit, cap))
