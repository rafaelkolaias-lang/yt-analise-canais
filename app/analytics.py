# -*- coding: utf-8 -*-
"""Analytics sobre runs salvos e canais/vídeos monitorados.

Funções puras que leem do results_store e devolvem rankings/agregados
prontos para exibir em tabelas.
"""
from collections import defaultdict
from statistics import median

from . import results_store


# ---------- Iteração sobre runs ----------

def all_channels_from_runs(runs=None):
    """Lista de (channel_dict, run_meta) para todos os canais de todos os runs."""
    runs = runs if runs is not None else results_store.load_runs().get("runs", [])
    out = []
    for run in runs:
        meta = {k: run.get(k) for k in ("run_id", "created_at", "mode", "terms_used")}
        for c in run.get("channels", []) or []:
            out.append((c, meta))
    return out


def all_videos_from_runs(runs=None):
    """Lista de (video_dict, run_meta) para todos os vídeos de todos os runs."""
    runs = runs if runs is not None else results_store.load_runs().get("runs", [])
    out = []
    for run in runs:
        meta = {k: run.get(k) for k in ("run_id", "created_at", "mode", "terms_used")}
        for v in run.get("videos", []) or []:
            out.append((v, meta))
    return out


def latest_channel_view(runs=None):
    """Para cada channel_id, retorna o último registro encontrado nos runs."""
    pairs = all_channels_from_runs(runs)
    by_id = {}
    for c, meta in pairs:
        cid = c.get("channel_id")
        if not cid:
            continue
        existing = by_id.get(cid)
        if existing is None or (meta.get("created_at") or "") > (existing[1].get("created_at") or ""):
            by_id[cid] = (c, meta)
    return list(by_id.values())


# ---------- Snapshots ----------

def latest_snapshot_per_channel():
    """Mais recente snapshot por canal (usa snapshots prepended)."""
    out = {}
    for snap in results_store.load_snapshots().get("snapshots", []):
        for c in snap.get("channels", []) or []:
            cid = c.get("channel_id")
            if cid and cid not in out:
                out[cid] = {"snapshot_id": snap.get("snapshot_id"),
                            "created_at": snap.get("created_at"),
                            **c}
    return out


def latest_snapshot_per_video():
    out = {}
    for snap in results_store.load_snapshots().get("snapshots", []):
        for v in snap.get("videos", []) or []:
            vid = v.get("video_id")
            if vid and vid not in out:
                out[vid] = {"snapshot_id": snap.get("snapshot_id"),
                            "created_at": snap.get("created_at"),
                            **v}
    return out


# ---------- Rankings ----------

def top_channels_by(field, n=10, source="monitored"):
    """Top N canais por campo. source: 'monitored' usa snapshots, 'runs' usa últimos runs."""
    if source == "monitored":
        items = list(latest_snapshot_per_channel().values())
    else:
        items = [c for c, _ in latest_channel_view()]

    def keyfn(it):
        v = it.get(field)
        return v if isinstance(v, (int, float)) else -1

    return sorted(items, key=keyfn, reverse=True)[:n]


def top_videos_by(field, n=10, source="monitored"):
    if source == "monitored":
        items = list(latest_snapshot_per_video().values())
    else:
        items = [v for v, _ in all_videos_from_runs()]

    def keyfn(it):
        v = it.get(field)
        return v if isinstance(v, (int, float)) else -1

    return sorted(items, key=keyfn, reverse=True)[:n]


def channels_accelerating(min_trend=1.2, n=20):
    """Canais cujo último snapshot tem vpd_trend >= min_trend."""
    out = []
    for c in latest_snapshot_per_channel().values():
        trend = c.get("vpd_trend") or 0
        if trend >= min_trend:
            out.append(c)
    return sorted(out, key=lambda x: -(x.get("vpd_trend") or 0))[:n]


def videos_accelerated(n=20):
    """Vídeos com maior recent_velocity (delta_views / dias) no último snapshot."""
    out = [v for v in latest_snapshot_per_video().values() if v.get("recent_velocity") is not None]
    return sorted(out, key=lambda x: -(x.get("recent_velocity") or 0))[:n]


# ---------- Tags / Nichos ----------

def niche_summary():
    """Agrupa canais monitorados por tag e devolve estatísticas agregadas."""
    monitored = results_store.load_monitored()
    snap_by_ch = latest_snapshot_per_channel()
    by_tag = defaultdict(list)
    for c in monitored.get("channels", []) or []:
        snap = snap_by_ch.get(c.get("channel_id")) or {}
        for tag in (c.get("tags") or ["(sem tag)"]):
            by_tag[tag].append({
                "channel_id": c.get("channel_id"),
                "title": c.get("title") or snap.get("title"),
                "subscribers": snap.get("subscribers"),
                "avg_vpd_recent": snap.get("avg_vpd_recent"),
                "vpd_trend": snap.get("vpd_trend"),
                "uploads_per_week": snap.get("uploads_per_week"),
            })

    out = []
    for tag, items in by_tag.items():
        vpds = [i["avg_vpd_recent"] for i in items if isinstance(i.get("avg_vpd_recent"), (int, float))]
        subs = [i["subscribers"] for i in items if isinstance(i.get("subscribers"), (int, float))]
        out.append({
            "tag": tag,
            "channels_count": len(items),
            "avg_vpd": round(sum(vpds) / len(vpds), 2) if vpds else None,
            "median_vpd": round(median(vpds), 2) if vpds else None,
            "median_subs": int(median(subs)) if subs else None,
            "channels": items,
        })
    return sorted(out, key=lambda x: -(x.get("avg_vpd") or 0))


def overview():
    """Resumo geral para a aba 'Resumo' do Analytics."""
    monitored = results_store.load_monitored()
    runs = results_store.load_runs().get("runs", [])
    return {
        "total_runs": len(runs),
        "total_monitored_channels": len(monitored.get("channels", []) or []),
        "total_monitored_videos": len(monitored.get("videos", []) or []),
        "total_snapshots": len(results_store.load_snapshots().get("snapshots", []) or []),
        "top_channels_by_avg_vpd": top_channels_by("avg_vpd_recent", n=10),
        "top_channels_by_delta_subs": top_channels_by("delta_subscribers", n=10),
        "top_videos_by_velocity": videos_accelerated(n=10),
        "niches": niche_summary(),
    }
