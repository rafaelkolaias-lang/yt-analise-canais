# -*- coding: utf-8 -*-
"""Geração de planilhas .xlsx (modo Scored e modo RAW)."""
from datetime import datetime

from .utils import human_date, human_age_days, days_since


def write_excel(path, blocks, params, terms_used, uploads_sample):
    import xlsxwriter
    wb = xlsxwriter.Workbook(str(path))
    ws = wb.add_worksheet("Canais (Resumo)")
    wv = wb.add_worksheet("Vídeos")
    meta = wb.add_worksheet("Insights")

    fmt_h = wb.add_format({"bold": True, "bg_color": "#F2F2F2", "border": 1})
    fmt_i = wb.add_format({"num_format": "#,##0"})
    fmt_d1 = wb.add_format({"num_format": "0.0"})
    fmt_d2 = wb.add_format({"num_format": "0.00"})
    fmt_pct = wb.add_format({"num_format": "0.0%"})
    fmt_link = wb.add_format({"font_color": "blue", "underline": 1})

    cols = ["Posição", "Canal", "URL", "Custom URL", "Criado", "Idade (dias)", "Inscritos", "Views canal",
            "Views/Video (canal)", "Vídeos",
            "Mediana views (últimos)", "% longos", "% ≥ min_views", "Janela uploads", "Qtd aprovados",
            "Média views aprov.", "Média duração (min)", "Score", "Melhor vídeo", "URL vídeo",
            "Publicado", "Views", "Views/dia", "Views/inscrito", "Like rate", "Comment rate", "TitleScore", "Novidade",
            "Uploads/sem", "Tendência VPD"]
    ws.write_row(0, 0, cols, fmt_h)

    widths = [8, 40, 18, 18, 12, 12, 12, 14, 16, 12, 22, 12, 14, 20, 14, 18, 18, 10, 45, 16, 12, 12, 12, 12, 12, 10, 10, 12, 12]
    for i, w in enumerate(widths):
        ws.set_column(i, i, w)

    ws.freeze_panes(1, 0)

    for pos, blk in enumerate(blocks, start=1):
        ci = blk["channel_info"]; cons = blk["consistency"]; best = blk["best_video"]
        v = best["video"]; met = best["metrics"]; score = best["score"]
        ch_id = blk["channel_id"]; ch_url = f"https://www.youtube.com/channel/{ch_id}"
        row = pos
        ws.write_number(row, 0, pos, fmt_i)
        ws.write(row, 1, ci.get("title") or "—")
        ws.write_url(row, 2, ch_url, fmt_link, "Abrir canal")
        ws.write(row, 3, ci.get("customUrl") or "")
        ws.write(row, 4, human_date(ci.get("publishedAt")) if ci.get("publishedAt") else "—")
        ws.write_number(row, 5, human_age_days(ci.get("publishedAt")) if ci.get("publishedAt") else 0, fmt_i)

        ws.write_number(row, 6, ci.get("subscriberCount") or 0, fmt_i)
        ws.write_number(row, 7, ci.get("viewCount") or 0, fmt_i)

        try:
            ch_views = ci.get("viewCount") or 0
            ch_videos = ci.get("videoCount") or 0
            vv = (ch_views / ch_videos) if ch_videos > 0 else 0
        except Exception:
            vv = 0
        ws.write_number(row, 8, int(vv), fmt_i)

        ws.write_number(row, 9, ci.get("videoCount") or 0, fmt_i)

        ws.write_number(row, 10, cons.get("views_median") or 0, fmt_i)
        ws.write_number(row, 11, cons.get("pct_long") or 0, fmt_pct)
        ws.write_number(row, 12, cons.get("pct_over") or 0, fmt_pct)
        ws.write(row, 13, f"{cons.get('date_min') or '—'} → {cons.get('date_max') or '—'}")
        ws.write_number(row, 14, blk["approved_count"], fmt_i)
        ws.write_number(row, 15, int(blk["avg_views_approved"]), fmt_i)
        ws.write_number(row, 16, int(blk["avg_dur_approved"]), fmt_i)
        ws.write_number(row, 17, score, fmt_d1)

        ws.write(row, 18, v["title"])
        ws.write_url(row, 19, v["url"], fmt_link, "Abrir vídeo")
        ws.write(row, 20, human_date(v["publishedAt"]))
        ws.write_number(row, 21, v["views"], fmt_i)
        ws.write_number(row, 22, met["vpd"], fmt_d2)
        ws.write(row, 23, met["vps"] if met["vps"] is not None else "—")
        ws.write_number(row, 24, met["like"], fmt_d2)
        ws.write_number(row, 25, met["comm"], fmt_d2)
        ws.write_number(row, 26, met["title"], fmt_d2)
        ws.write_number(row, 27, met["novelty"], fmt_d2)

        upw = cons.get("uploads_per_week")
        ws.write_number(row, 28, upw if upw is not None else 0, fmt_d2)
        trend = cons.get("vpd_trend")
        ws.write_number(row, 29, trend if trend is not None else 0, fmt_d2)

    ws.conditional_format(1, 17, len(blocks), 17, {"type": "3_color_scale"})
    if len(blocks) > 0:
        ws.conditional_format(1, 29, len(blocks), 29, {"type": "3_color_scale"})
        ws.autofilter(0, 0, len(blocks), 29)
    ws.conditional_format(1, 5, len(blocks), 5, {"type": "3_color_scale"})

    cols2 = ["Canal", "Canal ID", "Vídeo", "URL", "Publicado", "Duração (min)", "Views", "Likes", "Comentários", "Score (estimado)"]
    wv.write_row(0, 0, cols2, fmt_h)
    wv.freeze_panes(1, 0)
    wv.set_column(0, 0, 40); wv.set_column(1, 1, 24); wv.set_column(2, 2, 60); wv.set_column(3, 3, 16)
    wv.set_column(4, 9, 14)
    r = 1
    for blk in blocks:
        ci = blk["channel_info"]; ch_id = blk["channel_id"]; ch_title = ci.get("title") or "—"
        for v in blk["top_videos"]:
            wv.write(r, 0, ch_title); wv.write(r, 1, ch_id)
            wv.write(r, 2, v["video_title"]); wv.write_url(r, 3, v["video_url"], fmt_link, "Abrir")
            wv.write(r, 4, human_date(v["video_published_at"]))
            wv.write_number(r, 5, v["video_duration_min"], fmt_i)
            wv.write_number(r, 6, v["video_views"], fmt_i)
            wv.write_number(r, 7, v.get("video_likes") or 0, fmt_i)
            wv.write_number(r, 8, v.get("video_comments") or 0, fmt_i)
            wv.write_number(r, 9, v.get("_potential_score", 0), fmt_d1)
            r += 1

    meta.write(0, 0, "Gerado em:"); meta.write(0, 1, datetime.now().strftime("%Y-%m-%d %H:%M"))
    meta.write(1, 0, "Critérios efetivos")
    meta.write(2, 0, "Janela (dias)"); meta.write_number(2, 1, params["janela_dias"], fmt_i)
    meta.write(3, 0, "Idade máx. canal (dias)"); meta.write_number(3, 1, params["canal_age_max"], fmt_i)
    meta.write(4, 0, "Views mín. vídeo"); meta.write_number(4, 1, params["min_views"], fmt_i)
    meta.write(5, 0, "Uploads amostrados"); meta.write_number(5, 1, uploads_sample, fmt_i)
    meta.write(7, 0, "Termos usados:")
    for i, t in enumerate(terms_used, start=8):
        meta.write(i, 0, t)

    wb.close()


def write_excel_raw(path, rows, params, terms_used):
    import xlsxwriter
    wb = xlsxwriter.Workbook(str(path))
    wv = wb.add_worksheet("Vídeos (Raw)")
    meta = wb.add_worksheet("Meta")

    fmt_h = wb.add_format({"bold": True, "bg_color": "#F2F2F2", "border": 1})
    fmt_i = wb.add_format({"num_format": "#,##0"})
    fmt_d1 = wb.add_format({"num_format": "0.0"})
    fmt_d2 = wb.add_format({"num_format": "0.00"})
    fmt_link = wb.add_format({"font_color": "blue", "underline": 1})

    cols = [
        "Vídeo", "URL", "Publicado", "Idade (dias)", "Duração (min)",
        "Views", "Views/dia", "Likes", "Comentários",
        "Canal", "Canal ID", "URL Canal", "Inscritos", "Views Canal", "Views/Video (canal)", "Qtd Vídeos",
        "Idioma (API)",
    ]
    wv.write_row(0, 0, cols, fmt_h)
    wv.freeze_panes(1, 0)
    widths = [60, 16, 12, 12, 14, 14, 12, 10, 12, 40, 24, 18, 14, 14, 16, 12, 14]
    for i, w in enumerate(widths):
        wv.set_column(i, i, w)

    r = 1
    for v in rows:
        ch_url = f"https://www.youtube.com/channel/{v.get('channelId','')}"
        wv.write(r, 0, v.get("title", ""))
        wv.write_url(r, 1, v.get("video_url", ""), fmt_link, "Abrir")
        wv.write(r, 2, human_date(v["publishedAt"]))
        wv.write_number(r, 3, days_since(v["publishedAt"]), fmt_i)
        wv.write_number(r, 4, v.get("duration_min") or 0, fmt_i)
        wv.write_number(r, 5, v.get("views") or 0, fmt_i)
        wv.write_number(r, 6, v.get("vpd") or 0.0, fmt_d2)
        wv.write_number(r, 7, v.get("likes") or 0, fmt_i)
        wv.write_number(r, 8, v.get("comments") or 0, fmt_i)
        wv.write(r, 9, v.get("channel_title") or "—")
        wv.write(r, 10, v.get("channelId") or "")
        if v.get("channelId"):
            wv.write_url(r, 11, ch_url, fmt_link, "Abrir canal")
        else:
            wv.write(r, 11, "")
        wv.write_number(r, 12, v.get("subscriberCount") or 0, fmt_i)
        wv.write_number(r, 13, v.get("channel_viewCount") or 0, fmt_i)

        try:
            ch_views = v.get("channel_viewCount") or 0
            ch_videos = v.get("channel_videoCount") or 0
            vv = (ch_views / ch_videos) if ch_videos > 0 else 0
        except Exception:
            vv = 0
        wv.write_number(r, 14, int(vv), fmt_i)

        wv.write_number(r, 15, v.get("channel_videoCount") or 0, fmt_i)
        wv.write(r, 16, v.get("lang_hint") or "")

        r += 1

    meta.write(0, 0, "Gerado em:"); meta.write(0, 1, datetime.now().strftime("%Y-%m-%d %H:%M"))
    i = 2
    for k, v in params.items():
        meta.write(i, 0, str(k)); meta.write(i, 1, str(v)); i += 1
    meta.write(i + 1, 0, "Termos usados:")
    for j, t in enumerate(terms_used, start=i + 2):
        meta.write(j, 0, t)

    wb.close()
