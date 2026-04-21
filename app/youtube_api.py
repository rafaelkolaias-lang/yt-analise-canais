# -*- coding: utf-8 -*-
"""Cliente YouTube Data API v3 com rotação automática de API keys."""
import time
import requests
from dateutil.parser import isoparse

from . import config
from .utils import QuotaExceeded, _sleep_backoff, iso8601_duration_to_minutes, chunked


def _find_key_with_budget(est: int) -> int:
    """Retorna o índice da key atual se ainda couber `est`, senão procura outra. -1 se nenhuma couber."""
    n = len(config.API_KEYS)
    if n == 0:
        return -1
    # Garantir que QUOTA_USED está sincronizado com API_KEYS
    if len(config.QUOTA_USED) != n:
        config.resize_quota_for_keys()
    # Tenta a key atual primeiro
    idx = config._current_key_idx % n
    for _ in range(n):
        if config.quota_left_on_key(idx) >= est:
            return idx
        idx = (idx + 1) % n
    return -1


def yt_get(endpoint: str, **params):
    """
    Chama YouTube API com rotação de API_KEYS.
    - Orçamento rastreado POR KEY (config.QUOTA_USED é lista paralela a API_KEYS).
    - Antes de chamar: escolhe a key que ainda tem cota local suficiente para `est`.
    - Se retornar 403 quotaExceeded: marca a key como esgotada (QUOTA_USED[idx] = budget)
      e tenta a próxima. Só levanta QuotaExceeded quando nenhuma key tem cota.
    """
    est = config.QUOTA_COST.get(endpoint, 1)
    if not config.API_KEYS:
        raise SystemExit("Nenhuma API key definida. Configure YOUTUBE_API_KEYS em .env/ambiente ou no GUI.")

    url = f"{config.YOUTUBE_API}/{endpoint}"

    # max_total_attempts: 2 tentativas por key (rede/5xx), não por cota
    max_total_attempts = 2 * max(1, len(config.API_KEYS))
    attempts = 0
    budget_per_key = config.quota_budget_per_key()

    while attempts < max_total_attempts:
        attempts += 1

        idx = _find_key_with_budget(est)
        if idx < 0:
            raise QuotaExceeded(
                f"Sem cota local em nenhuma das {len(config.API_KEYS)} chave(s) para endpoint={endpoint}."
            )
        config._current_key_idx = idx
        params["key"] = config.API_KEYS[idx]

        try:
            r = requests.get(url, params=params, timeout=30)
        except requests.RequestException as ex:
            if attempts < max_total_attempts:
                _sleep_backoff(attempts)
                continue
            raise RuntimeError(f"Erro de rede em {endpoint}: {ex}")

        if r.status_code == 200:
            config.QUOTA_USED[idx] += est
            time.sleep(config.CFG["REQUEST_PAUSE"])
            return r.json()

        txt = (r.text or "").lower()
        if r.status_code == 403 and ("quota" in txt or "daily limit" in txt or "forbidden" in txt):
            # Marca a key atual como esgotada (o servidor sabe mais do que nosso contador local)
            config.QUOTA_USED[idx] = budget_per_key
            # Tenta próxima no próximo loop
            continue

        if r.status_code in (500, 503):
            _sleep_backoff(attempts)
            continue

        raise RuntimeError(f"Erro API {endpoint}: {r.status_code} - {r.text}")

    raise QuotaExceeded(f"Sem sucesso após {max_total_attempts} tentativas em {endpoint}.")


def discover_trending(categories, max_per_cat=30):
    results = []
    for cat in categories:
        before = len(results)
        params = {
            "part": "snippet,contentDetails,statistics",
            "chart": "mostPopular",
            "maxResults": 50,
            "videoCategoryId": str(cat),
        }
        if config.CFG["REGION_CODE"]:
            params["regionCode"] = config.CFG["REGION_CODE"]
        try:
            data = yt_get("videos", **params)
        except RuntimeError as e:
            if "404" in str(e) or "notfound" in str(e).lower():
                try:
                    alt = {
                        "part": "snippet,contentDetails,statistics",
                        "chart": "mostPopular",
                        "maxResults": 50,
                    }
                    if config.CFG["REGION_CODE"]:
                        alt["regionCode"] = config.CFG["REGION_CODE"]
                    data = yt_get("videos", **alt)
                except Exception:
                    continue
            else:
                raise

        for it in data.get("items", []):
            sn = it.get("snippet", {})
            st = it.get("statistics", {})
            if len(results) - before >= max_per_cat:
                break
            results.append({
                "videoId": it.get("id"),
                "channelId": sn.get("channelId"),
                "title": sn.get("title", ""),
                "publishedAt": sn.get("publishedAt"),
                "duration_min": iso8601_duration_to_minutes(it["contentDetails"]["duration"]),
                "views": int(st.get("viewCount", 0)),
                "likes": int(st["likeCount"]) if "likeCount" in st else None,
                "comments": int(st["commentCount"]) if "commentCount" in st else None,
            })

    return results


def resolve_handle_to_channel_id(handle: str):
    """Resolve um handle (@nome) para o channel_id (UC...). Custa 100 unidades de cota.

    Aceita formatos:
    - '@nomehandle'
    - 'nomehandle' (sem @)
    - URL completa com /@handle
    Retorna None se não achar.
    """
    if not handle:
        return None
    h = handle.strip()
    # Extrai da URL se vier inteira
    if "/@" in h:
        h = h.split("/@", 1)[1].split("/", 1)[0].split("?", 1)[0]
    h = h.lstrip("@").strip()
    if not h:
        return None

    try:
        data = yt_get(
            "search",
            part="snippet",
            type="channel",
            q=f"@{h}",
            maxResults=5,
        )
    except Exception:
        return None

    # Primeiro tenta bater exatamente pelo handle no snippet
    items = data.get("items", []) or []
    for it in items:
        sn = it.get("snippet", {}) or {}
        custom = (sn.get("customUrl") or "").lower().lstrip("@")
        title = (sn.get("title") or "").lower()
        if custom == h.lower() or title == h.lower():
            cid = (it.get("id") or {}).get("channelId") or it.get("snippet", {}).get("channelId")
            if cid:
                return cid
    # Fallback: primeiro resultado do search por channel
    if items:
        first = items[0]
        return (first.get("id") or {}).get("channelId") or first.get("snippet", {}).get("channelId")
    return None


def search_videos(term, published_after_iso, page_limit=1, lang=None, duration_mode="long", order=None):
    """
    lang: "pt" | "es" | "en" | None (None = sem viés de idioma)
    duration_mode: "long" | "medium" | "any"
    order: "relevance" | "date" | "viewCount" | "rating" | None (usa CFG["SEARCH_ORDER"])
    """
    items = []
    page_token = None
    pages = 0
    effective_order = order or config.CFG.get("SEARCH_ORDER", "relevance")
    while True:
        params = {
            "part": "snippet",
            "type": "video",
            "q": term,
            "maxResults": 50,
            "videoDuration": duration_mode,
            "publishedAfter": published_after_iso,
            "order": effective_order,
        }
        if config.CFG["REGION_CODE"]:
            params["regionCode"] = config.CFG["REGION_CODE"]
        if lang:
            params["relevanceLanguage"] = lang
        if page_token:
            params["pageToken"] = page_token

        data = yt_get("search", **params)
        pages += 1
        for it in data.get("items", []):
            vid = (it.get("id") or {}).get("videoId")
            if not vid:
                continue
            ch_id = (it.get("snippet") or {}).get("channelId")
            items.append({"videoId": vid, "channelId": ch_id})
        page_token = data.get("nextPageToken")
        if not page_token or pages >= page_limit:
            break
    return items


def hydrate_videos(video_ids):
    out = {}
    for group in chunked(video_ids, 50):
        data = yt_get("videos", part="statistics,contentDetails,snippet", id=",".join(group))
        for it in data.get("items", []):
            vid = it["id"]
            st = it.get("statistics", {})
            sn = it.get("snippet", {})
            out[vid] = {
                "views": int(st.get("viewCount", 0)),
                "likes": int(st["likeCount"]) if "likeCount" in st else None,
                "comments": int(st["commentCount"]) if "commentCount" in st else None,
                "duration_min": iso8601_duration_to_minutes(it["contentDetails"]["duration"]),
                "publishedAt": sn.get("publishedAt"),
                "channelId": sn.get("channelId"),
                "title": sn.get("title", ""),
                "defaultLanguage": sn.get("defaultLanguage"),
                "defaultAudioLanguage": sn.get("defaultAudioLanguage"),
            }
    return out


def discover_related(seed_video_id, published_after_iso):
    params = {
        "part": "snippet",
        "type": "video",
        "relatedToVideoId": seed_video_id,
        "maxResults": 50,
        "videoDuration": "long",
    }
    if config.CFG["REGION_CODE"]:
        params["regionCode"] = config.CFG["REGION_CODE"]
    try:
        data = yt_get("search", **params)
    except RuntimeError:
        return []

    items = []
    cutoff = isoparse(published_after_iso)
    for it in data.get("items", []):
        vid = (it.get("id") or {}).get("videoId")
        if not vid:
            continue
        sn = it.get("snippet", {})
        try:
            if sn.get("publishedAt") and isoparse(sn["publishedAt"]) < cutoff:
                continue
        except Exception:
            pass
        items.append({"videoId": vid, "channelId": sn.get("channelId")})
    return items


def get_channels_info(channel_ids):
    out = {}
    uniq = list(set(channel_ids))
    for group in chunked(uniq, 50):
        data = yt_get("channels", part="snippet,statistics,contentDetails", id=",".join(group))
        for it in data.get("items", []):
            ch_id = it["id"]
            sn = it["snippet"]
            st = it.get("statistics", {})
            cd = it.get("contentDetails", {})
            uploads = cd.get("relatedPlaylists", {}).get("uploads") if cd else None
            subs = None
            if not st.get("hiddenSubscriberCount"):
                try:
                    subs = int(st.get("subscriberCount")) if st.get("subscriberCount") is not None else None
                except Exception:
                    subs = None

            def _i(x):
                try:
                    return int(x)
                except Exception:
                    return None

            out[ch_id] = {
                "title": sn.get("title"),
                "publishedAt": sn.get("publishedAt"),
                "customUrl": sn.get("customUrl"),
                "subscriberCount": subs,
                "viewCount": _i(st.get("viewCount")),
                "videoCount": _i(st.get("videoCount")),
                "uploadsPlaylistId": uploads,
            }
    return out


def get_playlist_recent_video_ids(playlist_id, limit):
    ids = []
    page_token = None
    while True and len(ids) < limit:
        data = yt_get(
            "playlistItems", part="snippet", playlistId=playlist_id,
            maxResults=min(50, limit - len(ids)), pageToken=page_token or None,
        )
        for it in data.get("items", []):
            sn = it["snippet"]
            if "resourceId" in sn and "videoId" in sn["resourceId"]:
                ids.append(sn["resourceId"]["videoId"])
        page_token = data.get("nextPageToken")
        if not page_token or len(ids) >= limit:
            break
    return ids
