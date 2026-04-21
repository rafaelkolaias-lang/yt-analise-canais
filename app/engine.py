# -*- coding: utf-8 -*-
"""Orquestrador: pipeline Scored e RAW + helpers de fallback."""
import csv
import json
import random
from datetime import datetime, timezone, timedelta
from dateutil.parser import isoparse

from . import config
from . import results_store
from .utils import QuotaExceeded, log, human_age_days, human_date, days_since


def _block_to_channel_dict(blk):
    """Converte um 'block' (usado no Excel) em dict serializável para results_store."""
    ci = blk.get("channel_info") or {}
    cons = blk.get("consistency") or {}
    best = blk.get("best_video") or {}
    best_video = best.get("video") or {}
    best_metrics = best.get("metrics") or {}
    return {
        "channel_id": blk.get("channel_id"),
        "channel_title": ci.get("title"),
        "channel_url": f"https://www.youtube.com/channel/{blk.get('channel_id','')}",
        "custom_url": ci.get("customUrl"),
        "created_at": ci.get("publishedAt"),
        "age_days": human_age_days(ci["publishedAt"]) if ci.get("publishedAt") else None,
        "subscribers": ci.get("subscriberCount"),
        "views_total": ci.get("viewCount"),
        "video_count": ci.get("videoCount"),
        "views_per_video": (
            int((ci.get("viewCount") or 0) / ci["videoCount"]) if ci.get("videoCount") else None
        ),
        "consistency": cons,
        "approved_count": blk.get("approved_count"),
        "avg_views_approved": blk.get("avg_views_approved"),
        "avg_dur_approved": blk.get("avg_dur_approved"),
        "score": best.get("score"),
        "best_video": {
            "video_id": best_video.get("video_id") or (best_video.get("url", "").split("v=")[-1] if best_video.get("url") else None),
            "title": best_video.get("title"),
            "url": best_video.get("url"),
            "published_at": best_video.get("publishedAt"),
            "views": best_video.get("views"),
            "metrics": best_metrics,
        },
        "top_videos": [
            {
                "video_id": v.get("video_id"),
                "title": v.get("video_title"),
                "url": v.get("video_url"),
                "published_at": v.get("video_published_at"),
                "duration_min": v.get("video_duration_min"),
                "views": v.get("video_views"),
                "likes": v.get("video_likes"),
                "comments": v.get("video_comments"),
                "potential_score": v.get("_potential_score"),
            }
            for v in (blk.get("top_videos") or [])
        ],
    }


def _videos_from_blocks(blocks):
    """Lista plana de vídeos (para aba 'Vídeos' da janela de resultados)."""
    out = []
    for blk in blocks:
        ci = blk.get("channel_info") or {}
        for v in (blk.get("top_videos") or []):
            out.append({
                "video_id": v.get("video_id"),
                "channel_id": blk.get("channel_id"),
                "channel_title": ci.get("title"),
                "title": v.get("video_title"),
                "url": v.get("video_url"),
                "published_at": v.get("video_published_at"),
                "duration_min": v.get("video_duration_min"),
                "views": v.get("video_views"),
                "likes": v.get("video_likes"),
                "comments": v.get("video_comments"),
                "potential_score": v.get("_potential_score"),
                "vpd": (v.get("video_views") / max(1, days_since(v.get("video_published_at"))))
                       if v.get("video_published_at") else None,
            })
    return out


def _finalize_scored_run(blocks_sorted, params, terms_used, uploads_sample, status_cb, mode="scored"):
    """Persiste um run Scored/Monitor no results_store e opcionalmente gera Excel."""
    run_id = results_store.new_run_id()
    channels = [_block_to_channel_dict(b) for b in blocks_sorted]
    videos = _videos_from_blocks(blocks_sorted)

    excel_path = None
    if config.CFG.get("AUTO_EXPORT_EXCEL", False):
        excel_path = config.output_xlsx_path()
        status_cb(f"💾 Gerando Excel: {excel_path.name} ...")
        write_excel(excel_path, blocks_sorted, params=params,
                    terms_used=terms_used, uploads_sample=uploads_sample)
        excel_path = str(excel_path)

    run = {
        "run_id": run_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "params": params,
        "terms_used": terms_used,
        "uploads_sample": uploads_sample,
        "quota_used": config.quota_used_total(),
        "channels_count": len(channels),
        "videos_count": len(videos),
        "excel_path": excel_path,
        "channels": channels,
        "videos": videos,
    }
    results_store.append_run(run)
    status_cb(f"💾 Run salvo (id={run_id}) com {len(channels)} canal(is) e {len(videos)} vídeo(s).")
    if not config.CFG.get("AUTO_EXPORT_EXCEL", False):
        status_cb("ℹ️ Excel NÃO gerado automaticamente (AUTO_EXPORT_EXCEL=False). Exporte sob demanda.")
    return {
        "run_id": run_id,
        "mode": mode,
        "channels_count": len(channels),
        "videos_count": len(videos),
        "excel_path": excel_path,
    }


def _finalize_raw_run(raw_rows, params, terms_used, status_cb):
    """Persiste um run RAW no results_store e opcionalmente gera Excel."""
    run_id = results_store.new_run_id()

    videos = []
    channels_map = {}
    for r in raw_rows:
        ch_id = r.get("channelId")
        videos.append({
            "video_id": r.get("videoId"),
            "channel_id": ch_id,
            "channel_title": r.get("channel_title"),
            "title": r.get("title"),
            "url": r.get("video_url"),
            "published_at": r.get("publishedAt"),
            "duration_min": r.get("duration_min"),
            "views": r.get("views"),
            "likes": r.get("likes"),
            "comments": r.get("comments"),
            "vpd": r.get("vpd"),
            "lang_hint": r.get("lang_hint"),
        })
        if ch_id and ch_id not in channels_map:
            channels_map[ch_id] = {
                "channel_id": ch_id,
                "channel_title": r.get("channel_title"),
                "channel_url": f"https://www.youtube.com/channel/{ch_id}",
                "subscribers": r.get("subscriberCount"),
                "views_total": r.get("channel_viewCount"),
                "video_count": r.get("channel_videoCount"),
                "views_per_video": (
                    int((r.get("channel_viewCount") or 0) / r["channel_videoCount"])
                    if r.get("channel_videoCount") else None
                ),
            }

    excel_path = None
    if config.CFG.get("AUTO_EXPORT_EXCEL", False):
        excel_path = config.output_xlsx_raw_path()
        status_cb(f"💾 Gerando Excel (RAW): {excel_path.name} ...")
        write_excel_raw(excel_path, raw_rows, params=params, terms_used=terms_used)
        excel_path = str(excel_path)

    run = {
        "run_id": run_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "raw",
        "params": params,
        "terms_used": terms_used,
        "quota_used": config.quota_used_total(),
        "channels_count": len(channels_map),
        "videos_count": len(videos),
        "excel_path": excel_path,
        "channels": list(channels_map.values()),
        "videos": videos,
    }
    results_store.append_run(run)
    status_cb(f"💾 Run RAW salvo (id={run_id}) com {len(videos)} vídeo(s).")
    if not config.CFG.get("AUTO_EXPORT_EXCEL", False):
        status_cb("ℹ️ Excel NÃO gerado automaticamente (AUTO_EXPORT_EXCEL=False).")
    return {
        "run_id": run_id,
        "mode": "raw",
        "channels_count": len(channels_map),
        "videos_count": len(videos),
        "excel_path": excel_path,
    }


def update_monitored(status_cb=log):
    """Coleta snapshot atual de todos os canais e vídeos monitorados.

    Para cada canal: dados atuais + métricas de consistência + delta vs último snapshot.
    Para cada vídeo: views/likes/comments atuais + delta + velocidade recente.
    Persiste em snapshots_monitoramento.json.
    """
    config.reset_quota()
    config._current_key_idx = 0

    monitored = results_store.load_monitored()
    mon_channels = monitored.get("channels", []) or []
    mon_videos = monitored.get("videos", []) or []

    if not mon_channels and not mon_videos:
        status_cb("⚠️ Nenhum canal/vídeo monitorado.")
        return None

    snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    uploads_sample = max(3, config.CFG["UPLOADS_SAMPLE"])
    min_views = config.CFG["BASE_MIN_VIEWS"]
    min_dur = config.CFG["BASE_MIN_DURATION_MIN"]

    snap_channels = []
    if mon_channels:
        status_cb(f"📡 Atualizando {len(mon_channels)} canal(is) monitorado(s)...")
        ch_ids = [c.get("channel_id") for c in mon_channels if c.get("channel_id")]
        try:
            cinfos = get_channels_info(ch_ids)
        except QuotaExceeded:
            status_cb("Cota esgotada antes de coletar canais.")
            cinfos = {}

        for ch in mon_channels:
            ch_id = ch.get("channel_id")
            ci = cinfos.get(ch_id)
            if not ci:
                continue
            recent = {}
            if ci.get("uploadsPlaylistId"):
                try:
                    rv = get_playlist_recent_video_ids(ci["uploadsPlaylistId"], limit=uploads_sample)
                    if rv:
                        recent = hydrate_videos(rv)
                except QuotaExceeded:
                    status_cb("Cota esgotada coletando uploads recentes.")
                    break
            ccons = channel_consistency_metrics(recent, min_dur, min_views)

            best = None
            for v in recent.values():
                if not v.get("publishedAt"):
                    continue
                vpd = (v.get("views") or 0) / max(1, days_since(v["publishedAt"]))
                if best is None or vpd > best["vpd"]:
                    best = {"vpd": vpd, "title": v.get("title", ""), "video_id": None,
                            "views": v.get("views"), "publishedAt": v.get("publishedAt")}

            avg_vpd = None
            recent_with_pub = [v for v in recent.values() if v.get("publishedAt")]
            if recent_with_pub:
                avg_vpd = round(
                    sum((v.get("views") or 0) / max(1, days_since(v["publishedAt"]))
                        for v in recent_with_pub) / len(recent_with_pub), 2)

            # Tier (sinal de nicho)
            subs = ci.get("subscriberCount") or 0
            vpd_trend = ccons.get("vpd_trend") or 0
            if subs >= 500_000 and (avg_vpd or 0) < 1000:
                signal = "Saturado"
            elif (vpd_trend and vpd_trend > 1.3):
                signal = "Aquecendo"
            elif subs < 50_000 and (avg_vpd or 0) >= 500:
                signal = "Promissor"
            else:
                signal = "Estável"

            snap_ch = {
                "channel_id": ch_id,
                "title": ci.get("title"),
                "subscribers": ci.get("subscriberCount"),
                "views_total": ci.get("viewCount"),
                "video_count": ci.get("videoCount"),
                "uploads_per_week": ccons.get("uploads_per_week"),
                "vpd_trend": ccons.get("vpd_trend"),
                "views_median_recent": ccons.get("views_median"),
                "avg_vpd_recent": avg_vpd,
                "best_recent": best,
                "signal": signal,
            }

            # Delta vs snapshot anterior
            prev = results_store.snapshots_for_channel(ch_id)
            if prev:
                p = prev[0]  # mais recente (snapshots são prepended)
                snap_ch["delta_subscribers"] = (
                    (snap_ch["subscribers"] or 0) - (p.get("subscribers") or 0)
                    if snap_ch["subscribers"] is not None and p.get("subscribers") is not None else None
                )
                snap_ch["delta_views_total"] = (
                    (snap_ch["views_total"] or 0) - (p.get("views_total") or 0)
                    if snap_ch["views_total"] is not None and p.get("views_total") is not None else None
                )
                snap_ch["delta_video_count"] = (
                    (snap_ch["video_count"] or 0) - (p.get("video_count") or 0)
                    if snap_ch["video_count"] is not None and p.get("video_count") is not None else None
                )
                if snap_ch.get("avg_vpd_recent") is not None and p.get("avg_vpd_recent") is not None:
                    snap_ch["delta_avg_vpd"] = round(snap_ch["avg_vpd_recent"] - p["avg_vpd_recent"], 2)

            snap_channels.append(snap_ch)

    snap_videos = []
    if mon_videos:
        status_cb(f"📡 Atualizando {len(mon_videos)} vídeo(s) monitorado(s)...")
        vids_ids = [v.get("video_id") for v in mon_videos if v.get("video_id")]
        try:
            vstats = hydrate_videos(vids_ids)
        except QuotaExceeded:
            status_cb("Cota esgotada coletando vídeos.")
            vstats = {}

        for v in mon_videos:
            vid = v.get("video_id")
            st = vstats.get(vid)
            if not st:
                continue
            vpd = (st.get("views") or 0) / max(1, days_since(st["publishedAt"])) if st.get("publishedAt") else 0
            snap_v = {
                "video_id": vid,
                "channel_id": st.get("channelId"),
                "title": st.get("title"),
                "publishedAt": st.get("publishedAt"),
                "duration_min": st.get("duration_min"),
                "views": st.get("views"),
                "likes": st.get("likes"),
                "comments": st.get("comments"),
                "vpd_current": round(vpd, 2),
                "status": v.get("status", "active"),
            }

            prev = results_store.snapshots_for_video(vid)
            if prev:
                p = prev[0]
                snap_v["delta_views"] = (snap_v.get("views") or 0) - (p.get("views") or 0)
                snap_v["delta_likes"] = (snap_v.get("likes") or 0) - (p.get("likes") or 0)
                snap_v["delta_comments"] = (snap_v.get("comments") or 0) - (p.get("comments") or 0)
                # Velocidade: delta_views / dias entre snapshots
                try:
                    dt_now = datetime.strptime(snap_created, "%Y-%m-%d %H:%M:%S")
                    dt_prev = datetime.strptime(p.get("created_at"), "%Y-%m-%d %H:%M:%S")
                    days_between = max(1.0 / 24.0, (dt_now - dt_prev).total_seconds() / 86400.0)
                    snap_v["recent_velocity"] = round(snap_v["delta_views"] / days_between, 2)
                except Exception:
                    pass
            snap_videos.append(snap_v)

    snapshot = {
        "snapshot_id": snapshot_id,
        "created_at": snap_created,
        "channels": snap_channels,
        "videos": snap_videos,
    }
    results_store.append_snapshot(snapshot)
    status_cb(f"✅ Snapshot {snapshot_id}: {len(snap_channels)} canais, {len(snap_videos)} vídeos.")
    status_cb(f"ℹ️ Cota (estimada): {config.quota_used_total()}/{config.quota_total_budget()}")
    return snapshot


def export_run_to_excel(run_id, status_cb=log):
    """Exporta um run salvo no results_store para Excel (sob demanda)."""
    run = results_store.get_run(run_id)
    if not run:
        status_cb(f"❌ Run não encontrado: {run_id}")
        return None

    mode = run.get("mode", "scored")
    terms_used = run.get("terms_used") or []
    params = run.get("params") or {}

    if mode == "raw":
        videos = run.get("videos") or []
        # Reconstrói o shape esperado por write_excel_raw
        ch_map = {c.get("channel_id"): c for c in (run.get("channels") or []) if c.get("channel_id")}
        raw_rows = []
        for v in videos:
            ch = ch_map.get(v.get("channel_id"), {})
            raw_rows.append({
                "videoId": v.get("video_id"),
                "video_url": v.get("url"),
                "channelId": v.get("channel_id"),
                "title": v.get("title"),
                "publishedAt": v.get("published_at"),
                "duration_min": v.get("duration_min") or 0,
                "views": v.get("views") or 0,
                "likes": v.get("likes"),
                "comments": v.get("comments"),
                "vpd": v.get("vpd") or 0,
                "lang_hint": v.get("lang_hint") or "",
                "channel_title": ch.get("channel_title"),
                "subscriberCount": ch.get("subscribers"),
                "channel_viewCount": ch.get("views_total"),
                "channel_videoCount": ch.get("video_count"),
            })
        path = config.output_xlsx_raw_path()
        write_excel_raw(path, raw_rows, params=params, terms_used=terms_used)
        status_cb(f"✅ Excel RAW exportado: {path}")
        return str(path)

    # Scored / Monitor: reconstruir blocks a partir do JSON
    channels = run.get("channels") or []
    blocks = []
    for c in channels:
        ci = {
            "title": c.get("channel_title"),
            "publishedAt": c.get("created_at"),
            "customUrl": c.get("custom_url"),
            "subscriberCount": c.get("subscribers"),
            "viewCount": c.get("views_total"),
            "videoCount": c.get("video_count"),
        }
        best = c.get("best_video") or {}
        blocks.append({
            "channel_id": c.get("channel_id"),
            "channel_info": ci,
            "consistency": c.get("consistency") or {},
            "approved_count": c.get("approved_count") or 0,
            "avg_views_approved": c.get("avg_views_approved") or 0,
            "avg_dur_approved": c.get("avg_dur_approved") or 0,
            "top_videos": [
                {
                    "video_id": v.get("video_id"),
                    "video_title": v.get("title"),
                    "video_url": v.get("url"),
                    "video_published_at": v.get("published_at"),
                    "video_duration_min": v.get("duration_min") or 0,
                    "video_views": v.get("views") or 0,
                    "video_likes": v.get("likes"),
                    "video_comments": v.get("comments"),
                    "_potential_score": v.get("potential_score") or 0,
                }
                for v in (c.get("top_videos") or [])
            ],
            "best_video": {
                "score": c.get("score") or 0,
                "metrics": best.get("metrics") or {},
                "video": {
                    "title": best.get("title") or "",
                    "url": best.get("url") or "",
                    "publishedAt": best.get("published_at") or "",
                    "views": best.get("views") or 0,
                },
            },
        })

    path = config.output_xlsx_path()
    write_excel(path, blocks, params=params,
                terms_used=terms_used,
                uploads_sample=run.get("uploads_sample", 6))
    status_cb(f"✅ Excel exportado: {path}")
    return str(path)


def _user_terms_cap(pool_len: int) -> int:
    """Retorna o teto de termos definido pelo usuário (SEARCH_TERMS_PER_RUN).
    0 ou negativo = 'programa decide' → devolve o tamanho total do pool.
    """
    lim = int(config.CFG.get("SEARCH_TERMS_PER_RUN", 0) or 0)
    if lim <= 0:
        return pool_len
    return min(lim, pool_len)


def _video_passes(st, min_views, min_vpd, min_dur):
    """True se o vídeo passa nos filtros combinados (views OR vpd)."""
    if st.get("duration_min", 0) < min_dur:
        return False
    views = st.get("views", 0)
    pub = st.get("publishedAt")
    vpd = (views / max(1, days_since(pub))) if pub else 0.0
    return (views >= min_views) or (vpd >= min_vpd)


def _channel_age_ok(ci, max_age, min_age):
    """True se a idade do canal está dentro de [min_age, max_age]."""
    if not ci or not ci.get("publishedAt"):
        return False
    age = human_age_days(ci["publishedAt"])
    return min_age <= age <= max_age
from .persistence import load_seen_channels, append_seen_channels, load_terms, save_terms, log_run
from .youtube_api import (
    discover_trending, search_videos, hydrate_videos, discover_related,
    get_channels_info, get_playlist_recent_video_ids,
)
from .terms import (
    filter_terms_by_lang, mutate_terms, extract_learned_terms_from_titles, language_ok,
    _guess_lang,
)
from .scoring import channel_consistency_metrics, compute_score
from .excel_export import write_excel, write_excel_raw


def try_relax_and_refill(terms_obj, min_views_local, janela_local, max_age_days_local,
                         SELECTED_LANGS, duration_order=("long", "medium", "any"), steps=5):
    """Retorna: (qualified_extra, new_min_views, new_janela, new_max_age, used_duration)"""
    plan = [
        {"min_views": int(min_views_local * 0.7), "duration": "long",   "janela": janela_local,                "max_age": max_age_days_local},
        {"min_views": int(min_views_local * 0.6), "duration": "medium", "janela": min(janela_local + 30, 180), "max_age": max_age_days_local},
        {"min_views": int(min_views_local * 0.5), "duration": "any",    "janela": min(janela_local + 60, 240), "max_age": max(max_age_days_local, 180)},
        {"min_views": int(min_views_local * 0.4), "duration": "any",    "janela": min(janela_local + 120, 365), "max_age": max(max_age_days_local, 240)},
        {"min_views": max(config.CFG["LAST_RESORT_MIN_VIEWS"], int(min_views_local * 0.3)),
         "duration": "any", "janela": 365, "max_age": max(max_age_days_local, config.CFG.get("OLDER_MAX_CHANNEL_AGE_DAYS", 365))},
    ]

    for step in plan[:steps]:
        try_items = []
        published_after_new = (datetime.now(timezone.utc) - timedelta(days=step["janela"])).isoformat()
        filtered_base = filter_terms_by_lang(terms_obj["base"], SELECTED_LANGS)
        filtered_learned = filter_terms_by_lang(terms_obj.get("learned", []), SELECTED_LANGS)
        terms_more = mutate_terms(filtered_base, filtered_learned, 30)
        random.shuffle(terms_more)

        terms_cap = config.planned_terms_for_budget(len(SELECTED_LANGS) or 1, 1)
        for t in terms_more[:max(5, terms_cap)]:
            langs_round = SELECTED_LANGS[:] if SELECTED_LANGS else [None]
            random.shuffle(langs_round)
            for lang in langs_round:
                if config.quota_left() < 100:
                    break
                try:
                    it = search_videos(t, published_after_new, page_limit=1, lang=lang, duration_mode=step["duration"])
                    try_items.extend(it)
                except QuotaExceeded:
                    break

        if not try_items:
            continue

        stats = hydrate_videos([x["videoId"] for x in try_items])
        extra = []
        for x in try_items:
            st = stats.get(x["videoId"])
            if not st:
                continue
            if _video_passes(st, step["min_views"], config.CFG.get("BASE_MIN_VPD", 300), config.CFG["BASE_MIN_DURATION_MIN"]) and language_ok(st, SELECTED_LANGS, config.CFG.get("STRICT_LANGUAGE", False)):
                extra.append({
                    "videoId": x["videoId"],
                    "channelId": st["channelId"],
                    "duration_min": st["duration_min"],
                    "views": st["views"],
                    "likes": st.get("likes"),
                    "comments": st.get("comments"),
                    "publishedAt": st["publishedAt"],
                    "title": st.get("title", ""),
                })
        if extra:
            return extra, step["min_views"], step["janela"], step["max_age"], step["duration"]

    return [], min_views_local, janela_local, max_age_days_local, "long"


def fill_minimum_from_any(qualified, cinfos, seen_channels, base_max_age, need,
                          allow_repeated, allow_older, older_max_age, min_age=0):
    pick = []
    picked_ids = set()
    qualified_sorted = sorted(qualified, key=lambda r: -r.get("views", 0))
    for q in qualified_sorted:
        ch_id = q["channelId"]
        if ch_id in picked_ids:
            continue
        if (not allow_repeated) and (ch_id in seen_channels):
            continue
        ci = cinfos.get(ch_id)
        if not ci or not ci.get("publishedAt"):
            continue
        age = human_age_days(ci["publishedAt"])
        if age < min_age:
            continue
        if age <= base_max_age:
            pass
        else:
            if not allow_older:
                continue
            if age > older_max_age:
                continue
        picked_ids.add(ch_id)
        pick.append((ch_id, q, ci))
        if len(pick) >= need:
            break

    return [_row_from_pick(ch_id, q, ci) for ch_id, q, ci in pick]


def explain_drop_reasons(qualified, cinfos, seen_channels, base_max_age):
    stats = {"ok": 0, "seen": 0, "too_old": 0, "no_pub": 0}
    for q in qualified:
        ch_id = q["channelId"]
        ci = cinfos.get(ch_id)
        if ch_id in seen_channels:
            stats["seen"] += 1; continue
        if not ci or not ci.get("publishedAt"):
            stats["no_pub"] += 1; continue
        age = human_age_days(ci["publishedAt"])
        if age > base_max_age:
            stats["too_old"] += 1; continue
        stats["ok"] += 1
    return stats


def fill_from_too_old_only(qualified, cinfos, seen_channels, base_max_age, need, allow_repeated, min_age=0):
    pick = []
    picked_ids = set()
    qualified_sorted = sorted(qualified, key=lambda r: -r.get("views", 0))
    for q in qualified_sorted:
        ch_id = q["channelId"]
        if ch_id in picked_ids:
            continue
        if (not allow_repeated) and (ch_id in seen_channels):
            continue
        ci = cinfos.get(ch_id)
        if not ci or not ci.get("publishedAt"):
            continue
        age = human_age_days(ci["publishedAt"])
        if age < min_age:
            continue
        if age <= base_max_age:
            continue
        picked_ids.add(ch_id)
        pick.append((ch_id, q, ci))
        if len(pick) >= need:
            break

    return [_row_from_pick(ch_id, q, ci) for ch_id, q, ci in pick]


def _row_from_pick(ch_id, q, ci):
    return {
        "channel_id": ch_id,
        "channel_title": ci["title"],
        "channel_custom_url": ci.get("customUrl") or "",
        "channel_created_at": ci["publishedAt"],
        "channel_subs": ci.get("subscriberCount"),
        "channel_views_total": ci.get("viewCount"),
        "channel_video_count": ci.get("videoCount"),
        "uploads_playlist": ci.get("uploadsPlaylistId"),
        "video_id": q["videoId"],
        "video_url": f"https://www.youtube.com/watch?v={q['videoId']}",
        "video_published_at": q["publishedAt"],
        "video_duration_min": q["duration_min"],
        "video_views": q["views"],
        "video_likes": q.get("likes"),
        "video_comments": q.get("comments"),
        "video_title": q.get("title", ""),
    }


def run_engine(status_cb=log):
    """Executa o discovery e gera o Excel. status_cb: função para logar mensagens."""
    config.reset_quota()
    config._current_key_idx = 0

    random.seed()

    seen_channels = load_seen_channels()
    terms_obj = load_terms()

    min_views = config.CFG["BASE_MIN_VIEWS"]
    min_vpd = config.CFG.get("BASE_MIN_VPD", 300)
    min_dur = config.CFG["BASE_MIN_DURATION_MIN"]
    janela = config.CFG["BASE_PUBLISHED_AFTER_DAYS"]
    base_max_age = config.CFG["BASE_MAX_CHANNEL_AGE_DAYS"]
    base_min_age = config.CFG.get("BASE_MIN_CHANNEL_AGE_DAYS", 0)
    uploads_sample = config.CFG["UPLOADS_SAMPLE"]
    min_channels = config.CFG["MIN_CHANNELS_PER_SHEET"]

    if config.CUSTOM_SEARCH_TERMS:
        status_cb(f"🔤 Usando termos manuais literalmente ({len(config.CUSTOM_SEARCH_TERMS)} termo(s)).")
        terms_pool = config.CUSTOM_SEARCH_TERMS[:]
        terms_used = terms_pool[:_user_terms_cap(len(terms_pool))]
    else:
        base_all = terms_obj["base"]
        learned_all = terms_obj.get("learned", [])
        filtered_base = filter_terms_by_lang(base_all, config.CFG["SELECTED_LANGS"])
        filtered_learned = filter_terms_by_lang(learned_all, config.CFG["SELECTED_LANGS"])
        mut_target = max(40, int(config.CFG.get("SEARCH_TERMS_PER_RUN", 40) or 40) * 2)
        terms_pool = mutate_terms(filtered_base, filtered_learned, mut_target)
        random.shuffle(terms_pool)
        terms_used = terms_pool[:_user_terms_cap(len(terms_pool))]

    published_after = (datetime.now(timezone.utc) - timedelta(days=janela)).isoformat()

    # ====== MODO RAW (DUMP) ======
    if config.CFG.get("RAW_EXPORT_MODE", False):
        return _run_raw(status_cb, terms_used, published_after, janela, min_views)

    # ====== MODO SCORED ======
    if config.RUNS_CSV.exists():
        try:
            with open(config.RUNS_CSV, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            if rows:
                last = rows[-1]
                last_new = int(last.get("new_channels") or 0)
                if last_new < config.CFG["TARGET_NEW_CHANNELS"] // 2:
                    min_views = max(10_000, int(config.CFG["BASE_MIN_VIEWS"] * 0.8))
                    janela = min(120, config.CFG["BASE_PUBLISHED_AFTER_DAYS"] + 15)
                elif last_new > config.CFG["TARGET_NEW_CHANNELS"] * 2:
                    min_views = int(config.CFG["BASE_MIN_VIEWS"] * 1.3)
                    janela = max(30, config.CFG["BASE_PUBLISHED_AFTER_DAYS"] - 15)
        except Exception:
            pass

    published_after = (datetime.now(timezone.utc) - timedelta(days=janela)).isoformat()
    candidates = []

    status_cb("🔎 Coletando trending...")
    try:
        cats = config.CFG["TRENDING_CATEGORIES"][:]
        random.shuffle(cats)
        trending_sample = discover_trending(cats)
        candidates.extend([{"videoId": x["videoId"], "channelId": x["channelId"]} for x in trending_sample])
    except QuotaExceeded:
        status_cb("Cota insuficiente para trending, seguindo...")

    status_cb("🔎 Buscando por termos (multi-idioma) com orçamento...")
    langs_round_base = config.CFG["SELECTED_LANGS"][:] if config.CFG["SELECTED_LANGS"] else [None]
    langs_round = langs_round_base[:]
    random.shuffle(langs_round)

    terms_budget = config.planned_terms_for_budget(len(langs_round), config.CFG["SEARCH_PAGES_PER_TERM"])
    terms_to_use = terms_pool[:_user_terms_cap(len(terms_pool))]
    terms_used = terms_to_use[:terms_budget] if terms_budget < len(terms_to_use) else terms_to_use

    if terms_budget < len(terms_to_use):
        status_cb(f"💡 Ajuste por cota: termos de {len(terms_to_use)} → {terms_budget}.")

    for t in terms_used:
        if config.quota_left() < (100 * len(langs_round) * config.CFG["SEARCH_PAGES_PER_TERM"]):
            langs_round = [random.choice(langs_round_base)]
        for lang in langs_round:
            try:
                items = search_videos(
                    t, published_after,
                    page_limit=config.CFG["SEARCH_PAGES_PER_TERM"],
                    lang=lang, duration_mode="long",
                )
                candidates.extend(items)
            except QuotaExceeded:
                status_cb("Cota insuficiente durante buscas; prosseguindo com o que temos.")
                break

    # Dedup
    seen_vids = set(); unique_candidates = []
    for v in candidates:
        if v["videoId"] not in seen_vids:
            seen_vids.add(v["videoId"])
            unique_candidates.append(v)

    if not unique_candidates:
        status_cb("Sem candidatos nesta rodada. Ajuste cota/termos.")
        return None

    status_cb(f"ℹ️ Candidatos únicos: {len(unique_candidates)} — hidratando vídeos...")
    vstats = hydrate_videos([v["videoId"] for v in unique_candidates])

    status_cb("✅ Filtrando por duração + (views mín. OU VPD mín.) + idioma...")
    qualified = []
    for v in unique_candidates:
        st = vstats.get(v["videoId"])
        if not st:
            continue
        if (_video_passes(st, min_views, min_vpd, min_dur) and
                language_ok(st, config.CFG["SELECTED_LANGS"], config.CFG.get("STRICT_LANGUAGE", False))):
            qualified.append({
                "videoId": v["videoId"],
                "channelId": st["channelId"],
                "duration_min": st["duration_min"],
                "views": st["views"],
                "likes": st.get("likes"),
                "comments": st.get("comments"),
                "publishedAt": st["publishedAt"],
                "title": st.get("title", ""),
            })

    status_cb(f"📌 Pós-filtro: qualificados={len(qualified)} | min_views={min_views} OU min_vpd={min_vpd} | min_dur={min_dur}min")

    random.shuffle(qualified)
    status_cb("🔁 Explorando relacionados...")
    for seed in qualified[:config.CFG["RELATED_EXPLORE_LIMIT"]]:
        try:
            rel_items = discover_related(seed["videoId"], published_after)
            if not rel_items:
                continue
            rel_stats = hydrate_videos([x["videoId"] for x in rel_items])
            for it in rel_items:
                st = rel_stats.get(it["videoId"])
                if not st:
                    continue
                if (_video_passes(st, min_views, min_vpd, min_dur) and
                        language_ok(st, config.CFG["SELECTED_LANGS"], config.CFG.get("STRICT_LANGUAGE", False))):
                    qualified.append({
                        "videoId": it["videoId"],
                        "channelId": st["channelId"],
                        "duration_min": st["duration_min"],
                        "views": st["views"],
                        "likes": st.get("likes"),
                        "comments": st.get("comments"),
                        "publishedAt": st["publishedAt"],
                        "title": st.get("title", ""),
                    })
        except QuotaExceeded:
            status_cb("Parando relacionados por cota.")
            break

    status_cb(f"🔁 Após relacionados: vídeos qualificados={len(qualified)}")

    if not qualified:
        status_cb("Nenhum vídeo qualificado no critério principal. Iniciando fallback global...")
        extra, min_views, janela, base_max_age, _dur_used = try_relax_and_refill(
            terms_obj, min_views, janela, base_max_age, config.CFG["SELECTED_LANGS"]
        )
        qualified.extend(extra)
        if not extra:
            status_cb("Mesmo após fallback, não foi possível encontrar vídeos qualificados.")
            return None

    status_cb("ℹ️ Coletando info dos canais...")
    cinfos = get_channels_info([q["channelId"] for q in qualified])

    approved_rows = []
    drop_stats = explain_drop_reasons(qualified, cinfos, seen_channels, base_max_age)
    status_cb(f"🧮 Funil: qualificados={len(qualified)} | aprov.mesmos critérios={drop_stats['ok']} | vistos={drop_stats['seen']} | sem_publishedAt={drop_stats['no_pub']} | muito_antigos(>{base_max_age}d)={drop_stats['too_old']}")

    for q in qualified:
        ch_id = q["channelId"]
        if ch_id in seen_channels:
            continue
        ci = cinfos.get(ch_id)
        if _channel_age_ok(ci, base_max_age, base_min_age):
            approved_rows.append(_row_from_pick(ch_id, q, ci))

    status_cb(f"✅ Aprovados iniciais: {len(set(r['channel_id'] for r in approved_rows))} canais (idade {base_min_age}-{base_max_age}d)")

    # ---------- Fallback A ----------
    unique_approved = len(set([r["channel_id"] for r in approved_rows]))
    if unique_approved < min_channels:
        status_cb("⚙️ Fallback: relaxando e tentando mais candidatos...")
        extra, min_views, janela, base_max_age, _dur_used = try_relax_and_refill(
            terms_obj, min_views, janela, base_max_age, config.CFG["SELECTED_LANGS"]
        )
        if extra:
            qualified.extend(extra)
            cinfos = get_channels_info([q["channelId"] for q in qualified])
            approved_rows = []
            for q in qualified:
                ch_id = q["channelId"]
                if ch_id in seen_channels:
                    continue
                ci = cinfos.get(ch_id)
                if _channel_age_ok(ci, base_max_age, base_min_age):
                    approved_rows.append(_row_from_pick(ch_id, q, ci))

    # ---------- Fallback B ----------
    unique_approved = len(set([r["channel_id"] for r in approved_rows]))
    if unique_approved < min_channels:
        need = min_channels - unique_approved
        status_cb("⚠️ Último recurso: repetidos/mais antigos (com teto).")
        extra_rows = fill_minimum_from_any(
            qualified=qualified,
            cinfos=cinfos,
            seen_channels=seen_channels,
            base_max_age=base_max_age,
            need=need,
            allow_repeated=config.CFG.get("ALLOW_REPEATED_AS_LAST_RESORT", False),
            allow_older=config.CFG.get("ALLOW_OLDER_AS_LAST_RESORT", True),
            older_max_age=config.CFG.get("OLDER_MAX_CHANNEL_AGE_DAYS", 365),
            min_age=base_min_age,
        )
        ids_existing = set([r["channel_id"] for r in approved_rows])
        add_b = 0
        for r in extra_rows:
            if r["channel_id"] not in ids_existing:
                approved_rows.append(r)
                ids_existing.add(r["channel_id"])
                add_b += 1
        status_cb(f"➕ Complemento (config / teto): +{add_b} | total={len(set(x['channel_id'] for x in approved_rows))}")

    # ---------- Fallback C ----------
    unique_approved = len(set([r["channel_id"] for r in approved_rows]))
    if config.CFG.get("FORCE_TOO_OLD_BEFORE_FAILSAFE", True) and unique_approved < min_channels:
        need = min_channels - unique_approved
        status_cb("🧩 Fallback C: 'muito antigos' (sem teto).")
        extra_rows_c = fill_from_too_old_only(
            qualified=qualified,
            cinfos=cinfos,
            seen_channels=seen_channels,
            base_max_age=base_max_age,
            need=need,
            allow_repeated=config.CFG.get("ALLOW_REPEATED_AS_LAST_RESORT", False),
            min_age=base_min_age,
        )
        ids_existing = set([r["channel_id"] for r in approved_rows])
        add_c = 0
        for r in extra_rows_c:
            if r["channel_id"] not in ids_existing:
                approved_rows.append(r)
                ids_existing.add(r["channel_id"])
                add_c += 1
        status_cb(f"➕ Complemento (muito antigos / sem teto): +{add_c} | total={len(set(x['channel_id'] for x in approved_rows))}")

    # ---------- Fail-safe ----------
    if not approved_rows:
        status_cb("🛟 Fail-safe: ignorando 'visto' e 'idade' (top por views).")
        force_rows = fill_minimum_from_any(
            qualified=qualified,
            cinfos=cinfos,
            seen_channels=set(),
            base_max_age=10**9,
            need=max(1, config.CFG["MIN_CHANNELS_PER_SHEET"]),
            allow_repeated=True,
            allow_older=True,
            older_max_age=10**9,
        )
        approved_rows.extend(force_rows)
        status_cb(f"🛟 Fail-safe adicionou {len(force_rows)} canais.")

    if not approved_rows:
        status_cb("Nenhum canal aprovado após todos os fallbacks (incluindo fail-safe).")
        return None

    seen_keys = set()
    deduped = []
    for r in approved_rows:
        k = (r["channel_id"], r["video_id"])
        if k in seen_keys:
            continue
        seen_keys.add(k)
        deduped.append(r)
    approved_rows = deduped

    # Consistência + Scores por canal
    blocks = []
    by_channel = {}
    for r in approved_rows:
        by_channel.setdefault(r["channel_id"], []).append(r)

    status_cb("📊 Calculando métricas de consistência e pontuação...")
    for ch_id, vids in by_channel.items():
        ci = cinfos.get(ch_id, {})
        recent = {}
        if ci.get("uploadsPlaylistId") and uploads_sample > 0:
            try:
                rv_ids = get_playlist_recent_video_ids(ci["uploadsPlaylistId"], limit=uploads_sample)
                if rv_ids:
                    recent = hydrate_videos(rv_ids)
            except QuotaExceeded:
                pass
        ccons = channel_consistency_metrics(recent, config.CFG["BASE_MIN_DURATION_MIN"], min_views)

        best = None
        for r in vids:
            full = {
                "views": r["video_views"],
                "publishedAt": r["video_published_at"],
                "title": r["video_title"],
                "likes": r.get("video_likes"),
                "comments": r.get("video_comments"),
            }
            s, metrics = compute_score(full, ci, ccons, min_views)
            r["_potential_score"] = s
            if (best is None) or (s > best["score"]):
                best = {"score": s, "metrics": metrics, "video": {
                    "title": r["video_title"],
                    "url": r["video_url"],
                    "publishedAt": r["video_published_at"],
                    "views": r["video_views"],
                }}

        n = len(vids)
        avg_views = sum(v["video_views"] for v in vids) / n if n else 0
        avg_dur = sum(v["video_duration_min"] for v in vids) / n if n else 0
        dates = sorted(v["video_published_at"] for v in vids)
        blocks.append({
            "channel_id": ch_id,
            "channel_info": ci,
            "consistency": ccons,
            "approved_count": n,
            "avg_views_approved": avg_views,
            "avg_dur_approved": avg_dur,
            "approved_date_min": human_date(dates[0]) if dates else "—",
            "approved_date_max": human_date(dates[-1]) if dates else "—",
            "top_videos": sorted(vids, key=lambda r: -r["video_views"])[:5],
            "best_video": best,
        })

    blocks_sorted = sorted(blocks, key=lambda b: -b["best_video"]["score"])

    top_titles = [b["best_video"]["video"]["title"] for b in blocks_sorted[:min(20, len(blocks_sorted))]]
    pt_titles = [t for t in top_titles if _guess_lang(t) == "pt"]
    learned = extract_learned_terms_from_titles(pt_titles, top_k=20) if pt_titles else []
    terms_obj["learned"] = list(dict.fromkeys((learned + terms_obj.get("learned", []))))[:60]
    terms_obj["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_terms(terms_obj)

    append_seen_channels([(b["channel_id"], b["channel_info"].get("title") or "") for b in blocks_sorted])

    stats = {
        "new_channels": len(blocks_sorted),
        "min_views": min_views,
        "janela_dias": janela,
        "quota_used": config.quota_used_total(),
        "modes_mix": json.dumps({"trending": True, "search": True, "related": True}),
        "terms_used": terms_used,
    }
    log_run(stats)

    result = _finalize_scored_run(
        blocks_sorted,
        params={"janela_dias": janela, "canal_age_max": base_max_age, "min_views": min_views,
                "min_vpd": min_vpd, "min_dur": min_dur, "search_order": config.CFG.get("SEARCH_ORDER")},
        terms_used=terms_used, uploads_sample=uploads_sample,
        status_cb=status_cb, mode="scored",
    )
    status_cb(f"✅ OK! {result['channels_count']} canais, {result['videos_count']} vídeos.")
    status_cb(f"ℹ️ Cota (estimada): {config.quota_used_total()}/{config.quota_total_budget()}")
    status_cb("🧠 Termos aprendidos atualizados em dados/termos.json")
    return result


def run_monitor(channel_ids, status_cb=log):
    """Reanalisa uma lista de canais específicos (sem busca/trending/related). Gera Excel Scored."""
    config.reset_quota()
    config._current_key_idx = 0
    random.seed()

    channel_ids = [c.strip() for c in channel_ids if c and c.strip()]
    if not channel_ids:
        status_cb("⚠️ Nenhum channel_id informado.")
        return None

    status_cb(f"📡 Monitorando {len(channel_ids)} canal(is)...")
    min_views = config.CFG["BASE_MIN_VIEWS"]
    min_vpd = config.CFG.get("BASE_MIN_VPD", 300)
    min_dur = config.CFG["BASE_MIN_DURATION_MIN"]
    uploads_sample = max(3, config.CFG["UPLOADS_SAMPLE"])

    cinfos = get_channels_info(channel_ids)
    if not cinfos:
        status_cb("❌ Nenhum canal encontrado pelos IDs informados.")
        return None

    # Auto-adiciona canais analisados à lista de monitorados (fluxo "Monitorar IDs" já monitora).
    added_mon = 0
    for ch_id, ci in cinfos.items():
        if results_store.add_monitored_channel(ch_id, title=ci.get("title") or "",
                                               source="monitor_ids"):
            added_mon += 1
    if added_mon > 0:
        status_cb(f"👀 {added_mon} canal(is) adicionado(s) à lista de monitorados.")

    approved_rows = []
    for ch_id, ci in cinfos.items():
        if not ci.get("uploadsPlaylistId"):
            status_cb(f"⚠️ {ch_id}: sem uploadsPlaylistId — pulando")
            continue
        try:
            recent_ids = get_playlist_recent_video_ids(ci["uploadsPlaylistId"], limit=uploads_sample)
        except QuotaExceeded:
            status_cb("Cota esgotada durante monitor.")
            break
        if not recent_ids:
            continue
        vstats = hydrate_videos(recent_ids)
        for vid, st in vstats.items():
            if not _video_passes(st, min_views, min_vpd, min_dur):
                continue
            approved_rows.append(_row_from_pick(ch_id, {
                "videoId": vid,
                "channelId": ch_id,
                "duration_min": st["duration_min"],
                "views": st["views"],
                "likes": st.get("likes"),
                "comments": st.get("comments"),
                "publishedAt": st["publishedAt"],
                "title": st.get("title", ""),
            }, ci))

    if not approved_rows:
        status_cb("Nenhum vídeo passou no filtro views/VPD nos canais monitorados.")
        return None

    # Dedup (defensivo)
    seen_keys = set(); deduped = []
    for r in approved_rows:
        k = (r["channel_id"], r["video_id"])
        if k in seen_keys:
            continue
        seen_keys.add(k); deduped.append(r)
    approved_rows = deduped

    by_channel = {}
    for r in approved_rows:
        by_channel.setdefault(r["channel_id"], []).append(r)

    blocks = []
    for ch_id, vids in by_channel.items():
        ci = cinfos.get(ch_id, {})
        recent = {}
        if ci.get("uploadsPlaylistId"):
            try:
                rv_ids = get_playlist_recent_video_ids(ci["uploadsPlaylistId"], limit=uploads_sample)
                if rv_ids:
                    recent = hydrate_videos(rv_ids)
            except QuotaExceeded:
                pass
        ccons = channel_consistency_metrics(recent, min_dur, min_views)

        best = None
        for r in vids:
            full = {
                "views": r["video_views"],
                "publishedAt": r["video_published_at"],
                "title": r["video_title"],
                "likes": r.get("video_likes"),
                "comments": r.get("video_comments"),
            }
            s, metrics = compute_score(full, ci, ccons, min_views)
            r["_potential_score"] = s
            if (best is None) or (s > best["score"]):
                best = {"score": s, "metrics": metrics, "video": {
                    "title": r["video_title"],
                    "url": r["video_url"],
                    "publishedAt": r["video_published_at"],
                    "views": r["video_views"],
                }}

        n = len(vids)
        avg_views = sum(v["video_views"] for v in vids) / n if n else 0
        avg_dur = sum(v["video_duration_min"] for v in vids) / n if n else 0
        dates = sorted(v["video_published_at"] for v in vids)
        blocks.append({
            "channel_id": ch_id,
            "channel_info": ci,
            "consistency": ccons,
            "approved_count": n,
            "avg_views_approved": avg_views,
            "avg_dur_approved": avg_dur,
            "approved_date_min": human_date(dates[0]) if dates else "—",
            "approved_date_max": human_date(dates[-1]) if dates else "—",
            "top_videos": sorted(vids, key=lambda r: -r["video_views"])[:5],
            "best_video": best,
        })

    blocks_sorted = sorted(blocks, key=lambda b: -b["best_video"]["score"])
    result = _finalize_scored_run(
        blocks_sorted,
        params={"janela_dias": 0, "canal_age_max": 10**9, "min_views": min_views,
                "min_vpd": min_vpd, "min_dur": min_dur, "monitor_ids": channel_ids},
        terms_used=[f"[monitor] {c}" for c in channel_ids],
        uploads_sample=uploads_sample,
        status_cb=status_cb, mode="monitor",
    )
    status_cb(f"✅ OK! {result['channels_count']} canais analisados.")
    status_cb(f"ℹ️ Cota (estimada): {config.quota_used_total()}/{config.quota_total_budget()}")
    return result


def _run_raw(status_cb, terms_used, published_after, janela, min_views):
    """Modo Dump: vídeos crus, sem aprovações/idade/visto."""
    status_cb("🟢 Modo Dump (vídeos crus) ATIVADO: sem aprovações, sem idade de canal, sem 'visto'.")
    candidates = []

    if config.CFG.get("RAW_INCLUDE_TRENDING", True):
        status_cb("🔎 Coletando Trending (amostra)...")
        try:
            cats = config.CFG["TRENDING_CATEGORIES"][:]
            random.shuffle(cats)
            trending_sample = discover_trending(cats)
            candidates.extend([{"videoId": x["videoId"], "channelId": x["channelId"]} for x in trending_sample])
        except QuotaExceeded:
            status_cb("Cota insuficiente para Trending, pulando...")

    status_cb("🔎 Buscando por termos (RAW)...")
    langs_round_base = config.CFG["SELECTED_LANGS"][:] if config.CFG["SELECTED_LANGS"] else [None]
    langs_round = langs_round_base[:]
    random.shuffle(langs_round)

    terms_budget = config.planned_terms_for_budget(len(langs_round), config.CFG["SEARCH_PAGES_PER_TERM"])
    if terms_budget < len(terms_used):
        status_cb(f"💡 Ajuste por cota: termos de {len(terms_used)} → {terms_budget}.")
        terms_used = terms_used[:terms_budget]

    for t in terms_used:
        if config.quota_left() < (100 * len(langs_round) * config.CFG["SEARCH_PAGES_PER_TERM"]):
            langs_round = [random.choice(langs_round_base)]
        for lang in langs_round:
            try:
                items = search_videos(
                    t, published_after,
                    page_limit=config.CFG["SEARCH_PAGES_PER_TERM"],
                    lang=lang, duration_mode="long",
                )
                candidates.extend(items)
            except QuotaExceeded:
                status_cb("Cota insuficiente durante buscas RAW; seguindo com o que temos.")
                break

    if config.CFG.get("RAW_INCLUDE_RELATED", False):
        status_cb("🔁 Explorando relacionados (RAW)...")
        seeds = list({v["videoId"] for v in candidates[:50]})
        for seed in seeds[:config.CFG["RELATED_EXPLORE_LIMIT"]]:
            try:
                rel_items = discover_related(seed, published_after)
                candidates.extend(rel_items)
            except QuotaExceeded:
                break

    seen_vids = set(); unique_candidates = []
    for v in candidates:
        vid = v["videoId"]
        if vid not in seen_vids:
            seen_vids.add(vid)
            unique_candidates.append(v)

    if not unique_candidates:
        status_cb("Sem candidatos nesta rodada (RAW). Ajuste cota/termos.")
        return None

    status_cb(f"ℹ️ Candidatos únicos (RAW): {len(unique_candidates)} — hidratando vídeos...")
    vstats = hydrate_videos([v["videoId"] for v in unique_candidates])

    status_cb("✅ Filtrando RAW por janela de publicação, duração e views mínimas...")
    raw_rows = []
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=janela)
    for v in unique_candidates:
        st = vstats.get(v["videoId"])
        if not st:
            continue
        if config.CFG.get("STRICT_WINDOW_IN_RAW", True):
            try:
                if st["publishedAt"] and isoparse(st["publishedAt"]) < cutoff_dt:
                    continue
            except Exception:
                pass
        if (_video_passes(st, min_views, config.CFG.get("BASE_MIN_VPD", 300), config.CFG["BASE_MIN_DURATION_MIN"]) and
                language_ok(st, config.CFG["SELECTED_LANGS"], config.CFG.get("STRICT_LANGUAGE", False))):
            vpd = (st["views"] / max(1, days_since(st["publishedAt"]))) if st.get("publishedAt") else 0.0
            raw_rows.append({
                "videoId": v["videoId"],
                "video_url": f"https://www.youtube.com/watch?v={v['videoId']}",
                "channelId": st["channelId"],
                "title": st.get("title", ""),
                "publishedAt": st["publishedAt"],
                "duration_min": st["duration_min"],
                "views": st["views"],
                "likes": st.get("likes"),
                "comments": st.get("comments"),
                "vpd": round(vpd, 3),
                "lang_hint": (st.get("defaultAudioLanguage") or st.get("defaultLanguage") or ""),
            })

    if not raw_rows:
        status_cb("Nenhum vídeo passou nos filtros RAW. Tente reduzir min_views/duração ou ampliar a janela.")
        return None

    status_cb("ℹ️ Coletando infos de canais (RAW)...")
    cinfos = get_channels_info([r["channelId"] for r in raw_rows])
    for r in raw_rows:
        ci = cinfos.get(r["channelId"], {})
        r["channel_title"] = ci.get("title")
        r["subscriberCount"] = ci.get("subscriberCount")
        r["channel_viewCount"] = ci.get("viewCount")
        r["channel_videoCount"] = ci.get("videoCount")

    sort_mode = config.CFG.get("RAW_SORT_BY", "views_per_day")
    if sort_mode == "views_per_day":
        raw_rows.sort(key=lambda x: x.get("vpd", 0.0), reverse=True)
    elif sort_mode == "views":
        raw_rows.sort(key=lambda x: x.get("views", 0), reverse=True)
    elif sort_mode == "date_desc":
        raw_rows.sort(key=lambda x: x.get("publishedAt") or "", reverse=True)
    elif sort_mode == "random":
        random.shuffle(raw_rows)
    else:
        raw_rows.sort(key=lambda x: x.get("vpd", 0.0), reverse=True)

    limit = int(config.CFG.get("RAW_LIMIT", 250) or 250)
    raw_rows = raw_rows[:limit]

    stats = {
        "new_channels": len(set(r["channelId"] for r in raw_rows)),
        "min_views": min_views,
        "janela_dias": janela,
        "quota_used": config.quota_used_total(),
        "modes_mix": json.dumps({"trending": config.CFG.get("RAW_INCLUDE_TRENDING", True),
                                  "search": True,
                                  "related": config.CFG.get("RAW_INCLUDE_RELATED", False)}),
        "terms_used": terms_used,
    }
    log_run(stats)

    result = _finalize_raw_run(
        raw_rows,
        params={
            "janela_publicados_dias": janela,
            "min_views": min_views,
            "min_dur_min": config.CFG["BASE_MIN_DURATION_MIN"],
            "sort_by": sort_mode,
            "include_trending": config.CFG.get("RAW_INCLUDE_TRENDING", True),
            "include_related": config.CFG.get("RAW_INCLUDE_RELATED", False),
            "langs": ",".join(config.CFG["SELECTED_LANGS"]) if config.CFG.get("SELECTED_LANGS") else "—",
        },
        terms_used=terms_used, status_cb=status_cb,
    )
    status_cb(f"✅ OK! {result['videos_count']} vídeos.")
    status_cb(f"ℹ️ Cota (estimada): {config.quota_used_total()}/{config.quota_total_budget()}")
    status_cb("🧠 Termos aprendidos atualizados em dados/termos.json")
    return result
