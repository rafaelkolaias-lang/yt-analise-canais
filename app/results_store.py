# -*- coding: utf-8 -*-
"""Persistência interna de runs, canais/vídeos monitorados e snapshots temporais.

Arquivos em dados/:
- resultados_buscas.json  : histórico consolidado de runs (Scored/RAW/Monitor)
- monitorados.json        : canais e vídeos marcados para acompanhamento
- snapshots_monitoramento.json : snapshots temporais dos monitorados

Gravação atômica: escreve em .tmp e depois substitui o arquivo final.
"""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from . import config


RUNS_PATH = config.DATA_DIR / "resultados_buscas.json"
MONITOR_PATH = config.DATA_DIR / "monitorados.json"
SNAPSHOTS_PATH = config.DATA_DIR / "snapshots_monitoramento.json"


def _atomic_write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ---------- RUNS ----------

def load_runs() -> dict:
    return _load_json(RUNS_PATH, {"runs": []})


def save_runs(obj: dict):
    _atomic_write_json(RUNS_PATH, obj)


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def append_run(run: dict):
    """Adiciona um run ao histórico (mais recentes primeiro)."""
    obj = load_runs()
    runs = obj.setdefault("runs", [])
    runs.insert(0, run)
    save_runs(obj)


def remove_run(run_id: str) -> bool:
    obj = load_runs()
    runs = obj.get("runs", [])
    before = len(runs)
    obj["runs"] = [r for r in runs if r.get("run_id") != run_id]
    save_runs(obj)
    return len(obj["runs"]) < before


def get_run(run_id: str):
    for r in load_runs().get("runs", []):
        if r.get("run_id") == run_id:
            return r
    return None


# ---------- MONITORADOS ----------

def load_monitored() -> dict:
    return _load_json(MONITOR_PATH, {"channels": [], "videos": []})


def save_monitored(obj: dict):
    _atomic_write_json(MONITOR_PATH, obj)


def is_channel_monitored(channel_id: str) -> bool:
    return any(c.get("channel_id") == channel_id for c in load_monitored().get("channels", []))


def is_video_monitored(video_id: str) -> bool:
    return any(v.get("video_id") == video_id for v in load_monitored().get("videos", []))


def add_monitored_channel(channel_id: str, title: str = "", source: str = "resultado",
                          tags=None, notes: str = "") -> bool:
    obj = load_monitored()
    chs = obj.setdefault("channels", [])
    if any(c.get("channel_id") == channel_id for c in chs):
        return False
    chs.append({
        "channel_id": channel_id,
        "title": title or "",
        "source": source,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tags": list(tags or []),
        "notes": notes or "",
        "status": "active",
    })
    save_monitored(obj)
    return True


def add_monitored_video(video_id: str, channel_id: str = "", title: str = "",
                        source: str = "resultado", tags=None, notes: str = "") -> bool:
    obj = load_monitored()
    vids = obj.setdefault("videos", [])
    if any(v.get("video_id") == video_id for v in vids):
        return False
    vids.append({
        "video_id": video_id,
        "channel_id": channel_id or "",
        "title": title or "",
        "source": source,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tags": list(tags or []),
        "notes": notes or "",
        "status": "active",
    })
    save_monitored(obj)
    return True


def remove_monitored_channel(channel_id: str) -> bool:
    obj = load_monitored()
    chs = obj.get("channels", [])
    before = len(chs)
    obj["channels"] = [c for c in chs if c.get("channel_id") != channel_id]
    save_monitored(obj)
    return len(obj["channels"]) < before


def remove_monitored_video(video_id: str) -> bool:
    obj = load_monitored()
    vids = obj.get("videos", [])
    before = len(vids)
    obj["videos"] = [v for v in vids if v.get("video_id") != video_id]
    save_monitored(obj)
    return len(obj["videos"]) < before


def set_monitored_tags(kind: str, the_id: str, tags):
    """kind: 'channel' | 'video'"""
    obj = load_monitored()
    key = "channels" if kind == "channel" else "videos"
    id_key = "channel_id" if kind == "channel" else "video_id"
    for item in obj.get(key, []):
        if item.get(id_key) == the_id:
            item["tags"] = list(tags or [])
            break
    save_monitored(obj)


def set_monitored_notes(kind: str, the_id: str, notes: str):
    obj = load_monitored()
    key = "channels" if kind == "channel" else "videos"
    id_key = "channel_id" if kind == "channel" else "video_id"
    for item in obj.get(key, []):
        if item.get(id_key) == the_id:
            item["notes"] = notes or ""
            break
    save_monitored(obj)


# ---------- SNAPSHOTS ----------

def load_snapshots() -> dict:
    return _load_json(SNAPSHOTS_PATH, {"snapshots": []})


def save_snapshots(obj: dict):
    _atomic_write_json(SNAPSHOTS_PATH, obj)


def append_snapshot(snapshot: dict):
    obj = load_snapshots()
    snaps = obj.setdefault("snapshots", [])
    snaps.insert(0, snapshot)
    save_snapshots(obj)


def snapshots_for_channel(channel_id: str) -> list:
    out = []
    for snap in load_snapshots().get("snapshots", []):
        for c in snap.get("channels", []):
            if c.get("channel_id") == channel_id:
                out.append({"snapshot_id": snap.get("snapshot_id"),
                            "created_at": snap.get("created_at"),
                            **c})
    return out


def purge_channel(channel_id: str) -> dict:
    """Remove um canal e todos os seus vídeos de runs, monitorados e snapshots.

    Retorna dict com contagens do que foi removido.
    """
    if not channel_id:
        return {"runs_touched": 0, "channels_removed": 0, "videos_removed": 0,
                "snapshots_touched": 0, "monitor_channel_removed": False,
                "monitor_videos_removed": 0}

    # --- Runs ---
    runs_obj = load_runs()
    runs_touched = channels_removed = videos_removed = 0
    for run in runs_obj.get("runs", []):
        chs = run.get("channels") or []
        vids = run.get("videos") or []
        new_chs = [c for c in chs if c.get("channel_id") != channel_id]
        new_vids = [v for v in vids if v.get("channel_id") != channel_id]
        if len(new_chs) != len(chs) or len(new_vids) != len(vids):
            runs_touched += 1
            channels_removed += (len(chs) - len(new_chs))
            videos_removed += (len(vids) - len(new_vids))
            run["channels"] = new_chs
            run["videos"] = new_vids
            run["channels_count"] = len(new_chs)
            run["videos_count"] = len(new_vids)
    save_runs(runs_obj)

    # --- Monitorados ---
    mon = load_monitored()
    mon_chs = mon.get("channels", []) or []
    monitor_channel_removed = any(c.get("channel_id") == channel_id for c in mon_chs)
    mon["channels"] = [c for c in mon_chs if c.get("channel_id") != channel_id]
    mon_vids = mon.get("videos", []) or []
    vids_to_remove = [v for v in mon_vids if v.get("channel_id") == channel_id]
    monitor_videos_removed = len(vids_to_remove)
    mon["videos"] = [v for v in mon_vids if v.get("channel_id") != channel_id]
    save_monitored(mon)

    # --- Snapshots ---
    snap_obj = load_snapshots()
    snapshots_touched = 0
    for snap in snap_obj.get("snapshots", []):
        sc = snap.get("channels", []) or []
        sv = snap.get("videos", []) or []
        new_sc = [c for c in sc if c.get("channel_id") != channel_id]
        new_sv = [v for v in sv if v.get("channel_id") != channel_id]
        if len(new_sc) != len(sc) or len(new_sv) != len(sv):
            snapshots_touched += 1
            snap["channels"] = new_sc
            snap["videos"] = new_sv
    save_snapshots(snap_obj)

    return {
        "runs_touched": runs_touched,
        "channels_removed": channels_removed,
        "videos_removed": videos_removed,
        "snapshots_touched": snapshots_touched,
        "monitor_channel_removed": monitor_channel_removed,
        "monitor_videos_removed": monitor_videos_removed,
    }


def snapshots_for_video(video_id: str) -> list:
    out = []
    for snap in load_snapshots().get("snapshots", []):
        for v in snap.get("videos", []):
            if v.get("video_id") == video_id:
                out.append({"snapshot_id": snap.get("snapshot_id"),
                            "created_at": snap.get("created_at"),
                            **v})
    return out
