# -*- coding: utf-8 -*-
"""Métricas de consistência e score composto 0-100."""
import math
from statistics import median, pstdev

from . import config
from .utils import safe_ratio, days_since, human_age_days, human_date


WEIGHT_VPD = 0.35
WEIGHT_VPS = 0.20
WEIGHT_ENG = 0.25
WEIGHT_CONS = 0.10
WEIGHT_TITLE = 0.05
WEIGHT_NOVO = 0.05


def channel_consistency_metrics(recent_stats: dict, min_dur, min_views):
    if not recent_stats:
        return {"count": 0, "views_median": None, "views_mean": None, "views_std": None,
                "pct_long": None, "pct_over": None, "date_min": None, "date_max": None,
                "uploads_per_week": None, "vpd_trend": None}
    views_list = [v["views"] for v in recent_stats.values() if isinstance(v.get("views"), int)]
    dur_list = [v["duration_min"] for v in recent_stats.values() if isinstance(v.get("duration_min"), int)]
    dates = sorted([v["publishedAt"] for v in recent_stats.values() if v.get("publishedAt")])
    count = len(views_list)
    views_median = median(views_list) if views_list else None
    views_mean = sum(views_list) // count if views_list else None
    views_std = pstdev(views_list) if len(views_list) > 1 else 0
    pct_long = safe_ratio(sum(1 for d in dur_list if d and d >= min_dur), len(dur_list)) if dur_list else None
    pct_over = safe_ratio(sum(1 for v in views_list if v >= min_views), len(views_list)) if views_list else None
    date_min = human_date(dates[0]) if dates else None
    date_max = human_date(dates[-1]) if dates else None

    # Uploads por semana: (N vídeos) / (dias entre o mais antigo e o mais novo / 7)
    uploads_per_week = None
    if len(dates) >= 2:
        span_days = max(1, days_since(dates[0]) - days_since(dates[-1]))
        uploads_per_week = round(len(dates) / (span_days / 7.0), 2)
    elif len(dates) == 1:
        uploads_per_week = 0.0

    # Tendência VPD: VPD do vídeo mais recente vs. mediana do restante.
    # >1.0 = acelerando, <1.0 = desacelerando.
    vpd_trend = None
    ordered = sorted(
        [v for v in recent_stats.values() if v.get("publishedAt") and isinstance(v.get("views"), int)],
        key=lambda x: x["publishedAt"], reverse=True,
    )
    if len(ordered) >= 2:
        newest = ordered[0]
        rest = ordered[1:]
        newest_vpd = newest["views"] / max(1, days_since(newest["publishedAt"]))
        rest_vpds = [v["views"] / max(1, days_since(v["publishedAt"])) for v in rest]
        med = median(rest_vpds) if rest_vpds else 0
        if med > 0:
            vpd_trend = round(newest_vpd / med, 2)

    return {"count": count, "views_median": views_median, "views_mean": views_mean, "views_std": views_std,
            "pct_long": pct_long, "pct_over": pct_over, "date_min": date_min, "date_max": date_max,
            "uploads_per_week": uploads_per_week, "vpd_trend": vpd_trend}


def score_title(title: str) -> float:
    if not title:
        return 0.5
    t = title.strip()
    L = len(t)
    score = 1.0
    if L < 15:
        score -= 0.30
    elif L > 80:
        score -= 0.25
    letters = [c for c in t if c.isalpha()]
    if letters:
        caps = sum(1 for c in letters if c.isupper())
        if caps / len(letters) > 0.60:
            score -= 0.25
    return max(0.0, min(1.0, score))


def compute_score(v, cinfo, cconsist, min_views):
    views = v["views"]
    v_days = days_since(v["publishedAt"])
    vpd = views / v_days if v_days > 0 else views
    subs = cinfo.get("subscriberCount")
    vps = (views / subs) if subs and subs > 0 else None
    like_rate = safe_ratio(v.get("likes"), views)
    comm_rate = safe_ratio(v.get("comments"), views)
    sat = max(1000, int(config.CFG.get("VPD_SATURATION", 50000)))
    norm_vpd = min(1.0, math.log1p(vpd) / math.log1p(sat))
    norm_vps = min(1.0, (vps or 0) / 5.0)
    norm_like = min(1.0, (like_rate or 0) / 0.05)
    norm_comm = min(1.0, (comm_rate or 0) / 0.003)
    norm_eng = 0.7 * norm_like + 0.3 * norm_comm
    cons_med = cconsist.get("views_median") or 0
    norm_cons = min(1.0, cons_med / max(1, min_views))
    tscore = score_title(v.get("title", ""))
    age_days = human_age_days(cinfo["publishedAt"]) if cinfo.get("publishedAt") else 9999
    novelty = 1.0 if age_days <= 30 else (0.6 if age_days <= 60 else (0.3 if age_days <= 90 else 0.0))
    s01 = (WEIGHT_VPD * norm_vpd + WEIGHT_VPS * norm_vps + WEIGHT_ENG * norm_eng +
           WEIGHT_CONS * norm_cons + WEIGHT_TITLE * tscore + WEIGHT_NOVO * novelty)
    return round(s01 * 100, 1), {
        "vpd": round(vpd, 2),
        "vps": round(vps, 4) if vps is not None else None,
        "like": round(like_rate or 0, 4),
        "comm": round(comm_rate or 0, 4),
        "title": round(tscore, 2),
        "novelty": novelty,
    }
