# -*- coding: utf-8 -*-
"""Janela 'Ver canais/vídeos' — resultados, runs, monitorados, analytics.

Lê do results_store e exibe em tabelas ttk.Treeview filtráveis e ordenáveis.
Ações de monitoramento via clique direito + botões.
"""
import math
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox, simpledialog

try:
    from tksheet import Sheet
    _HAS_TKSHEET = True
except ImportError:
    _HAS_TKSHEET = False
    Sheet = None  # type: ignore


def _gradient_hex(ratio: float) -> str:
    """Mapeia 0.0 -> vermelho pálido, 0.5 -> amarelo, 1.0 -> verde pálido. Pastel para fundo."""
    r = max(0.0, min(1.0, ratio))
    if r < 0.5:
        # vermelho (255, 200, 200) -> amarelo (255, 245, 180)
        t = r / 0.5
        R = 255
        G = int(200 + t * (245 - 200))
        B = int(200 + t * (180 - 200))
    else:
        # amarelo (255, 245, 180) -> verde (190, 230, 190)
        t = (r - 0.5) / 0.5
        R = int(255 + t * (190 - 255))
        G = int(245 + t * (230 - 245))
        B = int(180 + t * (190 - 180))
    return f"#{R:02x}{G:02x}{B:02x}"


def _rank_ratio(values: list, invert: bool = False, log_scale: bool = False):
    """Retorna lista de ratios 0..1 para `values`. Valores None ficam com ratio None.
    invert=True: menor valor = ratio mais alto (ex.: idade).
    log_scale=True: aplica log1p antes (bom para métricas com cauda longa como views)."""
    nums = [(i, v) for i, v in enumerate(values) if isinstance(v, (int, float))]
    if not nums:
        return [None] * len(values)
    transformed = [(i, math.log1p(v) if log_scale and v >= 0 else v) for i, v in nums]
    vals_only = [v for _, v in transformed]
    lo, hi = min(vals_only), max(vals_only)
    out = [None] * len(values)
    if hi == lo:
        for i, _ in transformed:
            out[i] = 0.5
        return out
    for i, v in transformed:
        r = (v - lo) / (hi - lo)
        out[i] = (1.0 - r) if invert else r
    return out

from . import results_store
from . import analytics
from .engine import update_monitored, export_run_to_excel
from .utils import QuotaExceeded, human_date, human_age_days


# ---------- helpers ----------

def _safe(v, default="—"):
    if v is None or v == "":
        return default
    return v


def _fmt_num(v):
    if v is None or v == "":
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", ".")
    try:
        return f"{int(v):,}".replace(",", ".")
    except Exception:
        return str(v)


def _copy_to_clipboard(root, text):
    root.clipboard_clear()
    root.clipboard_append(text or "")


def _open_url(url):
    if url:
        webbrowser.open(url)


# ---------- window ----------

def open_results_window(parent):
    win = tk.Toplevel(parent)
    win.title("Ver canais / vídeos")
    win.geometry("1420x780")
    win.transient(parent)

    top = ttk.Frame(win, padding=8)
    top.pack(side="top", fill="x")

    # Filtros globais
    var_search = tk.StringVar()
    var_mode = tk.StringVar(value="Todos")
    var_only_mon = tk.StringVar(value="Todos")
    var_min_score = tk.StringVar(value="")
    var_min_vpd = tk.StringVar(value="")
    var_min_views = tk.StringVar(value="")

    ttk.Label(top, text="Busca:").grid(row=0, column=0, padx=4)
    ttk.Entry(top, textvariable=var_search, width=22).grid(row=0, column=1, padx=4)
    ttk.Label(top, text="Modo:").grid(row=0, column=2, padx=4)
    ttk.Combobox(top, textvariable=var_mode,
                 values=["Todos", "scored", "raw", "monitor"],
                 width=10, state="readonly").grid(row=0, column=3, padx=4)
    ttk.Label(top, text="Monitorados:").grid(row=0, column=4, padx=4)
    ttk.Combobox(top, textvariable=var_only_mon,
                 values=["Todos", "Apenas monitorados", "Apenas não monitorados"],
                 width=22, state="readonly").grid(row=0, column=5, padx=4)

    ttk.Label(top, text="Score mín.:").grid(row=1, column=0, padx=4, pady=(4, 0))
    ttk.Entry(top, textvariable=var_min_score, width=8).grid(row=1, column=1, padx=4, pady=(4, 0), sticky="w")
    ttk.Label(top, text="VPD mín.:").grid(row=1, column=2, padx=4, pady=(4, 0))
    ttk.Entry(top, textvariable=var_min_vpd, width=8).grid(row=1, column=3, padx=4, pady=(4, 0), sticky="w")
    ttk.Label(top, text="Views mín.:").grid(row=1, column=4, padx=4, pady=(4, 0))
    ttk.Entry(top, textvariable=var_min_views, width=10).grid(row=1, column=5, padx=4, pady=(4, 0), sticky="w")

    btn_reload = ttk.Button(top, text="Recarregar / aplicar filtros")
    btn_reload.grid(row=0, column=6, rowspan=2, padx=8)

    nb = ttk.Notebook(win)
    nb.pack(fill="both", expand=True, padx=8, pady=4)

    tab_channels = ttk.Frame(nb); nb.add(tab_channels, text="Canais")
    tab_videos = ttk.Frame(nb); nb.add(tab_videos, text="Vídeos")
    tab_runs = ttk.Frame(nb); nb.add(tab_runs, text="Runs")
    tab_monitored = ttk.Frame(nb); nb.add(tab_monitored, text="Monitorados")
    tab_analytics = ttk.Frame(nb); nb.add(tab_analytics, text="Analytics")

    # ---------- Canais ----------
    ch_cols = ("mon", "score", "title", "age", "subs", "views_total", "vpv",
               "upw", "trend", "best_title", "best_vpd", "run")
    ch_headings = {
        "mon": "Mon",
        "score": "Score",
        "title": "Canal",
        "age": "Idade",
        "subs": "Inscritos",
        "views_total": "Views canal",
        "vpv": "Views/vídeo",
        "upw": "Uploads/sem",
        "trend": "Tendência VPD",
        "best_title": "Melhor vídeo",
        "best_vpd": "VPD melhor",
        "run": "Última análise",
    }
    ch_widths = {"mon": 40, "score": 60, "title": 240, "age": 60, "subs": 100,
                 "views_total": 120, "vpv": 100, "upw": 90, "trend": 100,
                 "best_title": 260, "best_vpd": 90, "run": 130}
    ch_btns = ttk.Frame(tab_channels)
    ch_btns.pack(side="bottom", fill="x", pady=4)

    sheet_ch = Sheet(
        tab_channels,
        headers=[ch_headings[c] for c in ch_cols],
        show_row_index=False,
        show_top_left=False,
        height=480,
    )
    sheet_ch.enable_bindings((
        "single_select", "row_select", "column_width_resize",
        "arrowkeys", "rc_select", "copy", "right_click_popup_menu",
        "column_select",
    ))
    for i, c in enumerate(ch_cols):
        sheet_ch.column_width(column=i, width=ch_widths[c])
    sheet_ch.pack(side="left", fill="both", expand=True)
    # Guarda channel_id paralelo aos rows (tksheet não tem "tags" como Treeview)
    sheet_ch_ids: list[str] = []

    # ---------- Vídeos ----------
    v_cols = ("mon", "vpd", "views", "published", "dur", "channel",
              "title", "likes", "comments", "run")
    v_headings = {
        "mon": "Mon", "vpd": "VPD", "views": "Views", "published": "Publicado",
        "dur": "Duração (Min)", "channel": "Canal", "title": "Título",
        "likes": "Likes", "comments": "Coment.", "run": "Run",
    }
    v_widths = {"mon": 40, "vpd": 80, "views": 100, "published": 90, "dur": 90,
                "channel": 200, "title": 360, "likes": 80, "comments": 80, "run": 130}
    v_btns = ttk.Frame(tab_videos)
    v_btns.pack(side="bottom", fill="x", pady=4)

    sheet_v = Sheet(
        tab_videos,
        headers=[v_headings[c] for c in v_cols],
        show_row_index=False,
        show_top_left=False,
        height=480,
    )
    sheet_v.enable_bindings((
        "single_select", "row_select", "column_width_resize",
        "arrowkeys", "rc_select", "copy", "right_click_popup_menu",
        "column_select",
    ))
    for i, c in enumerate(v_cols):
        sheet_v.column_width(column=i, width=v_widths[c])
    sheet_v.pack(side="left", fill="both", expand=True)
    sheet_v_ids: list[str] = []

    # ---------- Runs ----------
    r_cols = ("created", "mode", "channels", "videos", "quota", "terms", "excel")
    r_headings = {
        "created": "Data", "mode": "Modo", "channels": "Canais",
        "videos": "Vídeos", "quota": "Cota", "terms": "Termos", "excel": "Excel",
    }
    r_widths = {"created": 150, "mode": 80, "channels": 70, "videos": 70,
                "quota": 60, "terms": 480, "excel": 240}
    runs_btns = ttk.Frame(tab_runs)
    runs_btns.pack(side="bottom", fill="x", pady=4)
    btn_run_export = ttk.Button(runs_btns, text="Exportar run para Excel")
    btn_run_export.pack(side="left", padx=4)
    btn_run_remove = ttk.Button(runs_btns, text="Remover run (confirma)")
    btn_run_remove.pack(side="left", padx=4)
    btn_run_import = ttk.Button(runs_btns, text="Importar planilhas antigas")
    btn_run_import.pack(side="left", padx=4)

    tv_r = ttk.Treeview(tab_runs, columns=r_cols, show="headings", height=22)
    for c in r_cols:
        tv_r.heading(c, text=r_headings[c])
        tv_r.column(c, width=r_widths[c], anchor="w")
    sb_r = ttk.Scrollbar(tab_runs, orient="vertical", command=tv_r.yview)
    tv_r.configure(yscrollcommand=sb_r.set)
    sb_r.pack(side="right", fill="y")
    tv_r.pack(side="left", fill="both", expand=True)

    # ---------- Monitorados ----------
    m_cols = ("kind", "title", "id", "tags", "notes", "added", "signal")
    m_headings = {"kind": "Tipo", "title": "Título", "id": "ID",
                  "tags": "Tags", "notes": "Notas", "added": "Adicionado", "signal": "Sinal"}
    m_widths = {"kind": 60, "title": 300, "id": 260, "tags": 160, "notes": 280,
                "added": 140, "signal": 100}
    mon_btns = ttk.Frame(tab_monitored)
    mon_btns.pack(side="bottom", fill="x", pady=4)
    btn_mon_add = ttk.Button(mon_btns, text="Adicionar monitorado")
    btn_mon_add.pack(side="left", padx=4)
    btn_mon_update = ttk.Button(mon_btns, text="Atualizar monitorados agora")
    btn_mon_update.pack(side="left", padx=4)
    btn_mon_remove = ttk.Button(mon_btns, text="Remover selecionado")
    btn_mon_remove.pack(side="left", padx=4)
    btn_mon_tags = ttk.Button(mon_btns, text="Editar tags")
    btn_mon_tags.pack(side="left", padx=4)
    btn_mon_notes = ttk.Button(mon_btns, text="Editar notas")
    btn_mon_notes.pack(side="left", padx=4)

    tv_m = ttk.Treeview(tab_monitored, columns=m_cols, show="headings", height=22)
    for c in m_cols:
        tv_m.heading(c, text=m_headings[c])
        tv_m.column(c, width=m_widths[c], anchor="w")
    sb_m = ttk.Scrollbar(tab_monitored, orient="vertical", command=tv_m.yview)
    tv_m.configure(yscrollcommand=sb_m.set)
    sb_m.pack(side="right", fill="y")
    tv_m.pack(side="left", fill="both", expand=True)

    # ---------- Analytics ----------
    an_top = ttk.Frame(tab_analytics); an_top.pack(fill="x", padx=8, pady=8)
    an_summary = tk.Text(an_top, height=6, wrap="word", state="disabled")
    an_summary.pack(fill="x")

    an_mid = ttk.Frame(tab_analytics); an_mid.pack(fill="both", expand=True, padx=8, pady=4)
    an_nb = ttk.Notebook(an_mid); an_nb.pack(fill="both", expand=True)
    an_top_ch = ttk.Frame(an_nb); an_nb.add(an_top_ch, text="Top canais")
    an_top_vid = ttk.Frame(an_nb); an_nb.add(an_top_vid, text="Vídeos acelerados")
    an_niches = ttk.Frame(an_nb); an_niches.add = None; an_nb.add(an_niches, text="Nichos/tags")

    tv_an_ch = ttk.Treeview(an_top_ch,
                            columns=("title", "avg_vpd", "trend", "subs", "upw", "delta_subs"),
                            show="headings", height=15)
    for c, t, w in [("title", "Canal", 260), ("avg_vpd", "VPD médio", 100),
                    ("trend", "Tendência", 100), ("subs", "Inscritos", 110),
                    ("upw", "Uploads/sem", 100), ("delta_subs", "Δ inscritos", 100)]:
        tv_an_ch.heading(c, text=t); tv_an_ch.column(c, width=w)
    tv_an_ch.pack(fill="both", expand=True)

    tv_an_vid = ttk.Treeview(an_top_vid,
                             columns=("title", "velocity", "views", "delta_views", "vpd"),
                             show="headings", height=15)
    for c, t, w in [("title", "Vídeo", 360), ("velocity", "Velocidade", 100),
                    ("views", "Views", 100), ("delta_views", "Δ views", 100),
                    ("vpd", "VPD atual", 100)]:
        tv_an_vid.heading(c, text=t); tv_an_vid.column(c, width=w)
    tv_an_vid.pack(fill="both", expand=True)

    tv_an_niche = ttk.Treeview(an_niches,
                               columns=("tag", "count", "avg_vpd", "median_vpd", "median_subs"),
                               show="headings", height=15)
    for c, t, w in [("tag", "Tag", 200), ("count", "Canais", 70),
                    ("avg_vpd", "VPD médio", 100), ("median_vpd", "VPD mediano", 110),
                    ("median_subs", "Inscritos mediano", 140)]:
        tv_an_niche.heading(c, text=t); tv_an_niche.column(c, width=w)
    tv_an_niche.pack(fill="both", expand=True)

    # ---------- Sort tri-state (asc → desc → off) nos headers ----------
    def _enable_sort(tv, refill_fn=None):
        """Clicar no header: asc -> desc -> sem ordenação (restaura refill)."""
        state = {"col": None, "dir": None}  # dir: 'asc' | 'desc' | None

        def _to_float_or_none(s):
            if s is None:
                return None
            txt = str(s).strip()
            if not txt or txt == "—":
                return None
            candidate = txt.replace(".", "").replace(",", ".")
            try:
                return float(candidate)
            except ValueError:
                return None

        def _sort_by(col):
            cur_col = state["col"]
            cur_dir = state["dir"]
            if col != cur_col:
                new_dir = "asc"
            elif cur_dir == "asc":
                new_dir = "desc"
            elif cur_dir == "desc":
                new_dir = None
            else:
                new_dir = "asc"

            state["col"] = col if new_dir else None
            state["dir"] = new_dir

            # Marcador visual ▲/▼/— no header
            for c in tv["columns"]:
                title = tv.heading(c)["text"]
                # remove sufixos antigos
                for suf in (" ▲", " ▼"):
                    if title.endswith(suf):
                        title = title[: -len(suf)]
                if c == col and new_dir == "asc":
                    title = title + " ▲"
                elif c == col and new_dir == "desc":
                    title = title + " ▼"
                tv.heading(c, text=title)

            if new_dir is None:
                # Restaura ordem original via refill
                if refill_fn is not None:
                    refill_fn()
                return

            raw = [(tv.set(k, col), k) for k in tv.get_children("")]
            # Decide se a coluna é numérica: se todas as células não-vazias parsearem como float.
            all_numeric = True
            for val, _ in raw:
                if val is None or str(val).strip() in ("", "—"):
                    continue
                if _to_float_or_none(val) is None:
                    all_numeric = False
                    break
            if all_numeric:
                def key_fn(pair):
                    f = _to_float_or_none(pair[0])
                    # None sempre ao fim (em asc e desc: usa +inf e -inf dependendo da direção)
                    if f is None:
                        return float("-inf") if new_dir == "desc" else float("inf")
                    return f
            else:
                def key_fn(pair):
                    v = pair[0]
                    if v is None or str(v).strip() in ("", "—"):
                        return ""
                    return str(v).lower()

            raw.sort(key=key_fn, reverse=(new_dir == "desc"))
            for idx, (_, k) in enumerate(raw):
                tv.move(k, "", idx)

        for col in tv["columns"]:
            tv.heading(col, command=lambda c=col: _sort_by(c))

    # ---------- Estado mutável ----------
    state = {
        "runs": [],
        "monitored": {"channels": [], "videos": []},
    }

    def _reload_state():
        state["runs"] = results_store.load_runs().get("runs", [])
        state["monitored"] = results_store.load_monitored()

    def _passes_filter(text_parts, score=None, vpd=None, views=None):
        q = (var_search.get() or "").strip().lower()
        if q and not any(q in (t or "").lower() for t in text_parts):
            return False
        try:
            if var_min_score.get().strip() and (score or 0) < float(var_min_score.get()):
                return False
        except ValueError:
            pass
        try:
            if var_min_vpd.get().strip() and (vpd or 0) < float(var_min_vpd.get()):
                return False
        except ValueError:
            pass
        try:
            if var_min_views.get().strip() and (views or 0) < float(var_min_views.get()):
                return False
        except ValueError:
            pass
        return True

    def _run_filter_matches(run):
        sel = var_mode.get()
        return sel in ("Todos", "") or (run.get("mode") == sel)

    # Índices numéricos nas colunas, configuração de gradiente por coluna.
    # (col_index, invert, log_scale) — invert=True: menor valor = mais verde.
    CH_HEAT = {
        1: (False, False),   # score: alto = verde
        3: (True, False),    # age: baixo = verde
        4: (False, True),    # subs: alto = verde (log)
        5: (False, True),    # views_total: alto = verde (log)
        6: (False, True),    # vpv: alto = verde (log)
        7: (False, False),   # upw: alto = verde
        8: (False, False),   # trend: alto = verde
        10: (False, True),   # best_vpd: alto = verde (log)
    }
    V_HEAT = {
        1: (False, True),                 # vpd: alto = verde (log)
        2: (False, True),                 # views: alto = verde (log)
        4: ("sweet", 60, 120, 30),        # dur: verde entre 60-120 min, decai ±30 min
        7: (False, True),                 # likes
        8: (False, True),                 # comments
    }

    def _sweet_ratios(values, lo_ideal, hi_ideal, taper):
        """Retorna ratios 0..1 onde [lo_ideal, hi_ideal] = 1.0; cai linearmente até
        lo_ideal-taper e hi_ideal+taper (que viram 0.0). Fora disso continua 0.0."""
        out = []
        for v in values:
            if not isinstance(v, (int, float)):
                out.append(None)
                continue
            if lo_ideal <= v <= hi_ideal:
                out.append(1.0)
            elif v < lo_ideal:
                r = (v - (lo_ideal - taper)) / taper
                out.append(max(0.0, min(1.0, r)))
            else:  # v > hi_ideal
                r = ((hi_ideal + taper) - v) / taper
                out.append(max(0.0, min(1.0, r)))
        return out

    def _apply_heat(sheet, data, heat_cols):
        """Para cada coluna em heat_cols, calcula gradiente e pinta células."""
        n = len(data)
        if n == 0:
            return
        for col_idx, cfg in heat_cols.items():
            # Coleta números da coluna
            col_vals = []
            for row in data:
                raw = row[col_idx] if col_idx < len(row) else None
                if raw in (None, "", "—"):
                    col_vals.append(None)
                    continue
                txt = str(raw).replace(".", "").replace(",", ".")
                try:
                    col_vals.append(float(txt))
                except ValueError:
                    col_vals.append(None)
            # Modo "sweet" (faixa ideal) ou modo ranking (default)
            if isinstance(cfg, tuple) and len(cfg) >= 4 and cfg[0] == "sweet":
                _, lo, hi, taper = cfg
                ratios = _sweet_ratios(col_vals, lo, hi, taper)
            else:
                invert, log_scale = cfg
                ratios = _rank_ratio(col_vals, invert=invert, log_scale=log_scale)
            for r_idx, ratio in enumerate(ratios):
                if ratio is None:
                    continue
                sheet.highlight_cells(row=r_idx, column=col_idx,
                                      bg=_gradient_hex(ratio), fg="#111111")

    def _refill_channels():
        from .utils import days_since
        mon_ch_ids = {c.get("channel_id") for c in state["monitored"].get("channels", [])}
        rows = []
        ids = []
        for run in state["runs"]:
            if not _run_filter_matches(run):
                continue
            run_ts = run.get("created_at") or ""
            for c in run.get("channels", []) or []:
                cid = c.get("channel_id")
                is_mon = cid in mon_ch_ids
                if var_only_mon.get() == "Apenas monitorados" and not is_mon:
                    continue
                if var_only_mon.get() == "Apenas não monitorados" and is_mon:
                    continue
                best = c.get("best_video") or {}
                best_vpd = None
                bpub = best.get("published_at")
                if bpub and best.get("views"):
                    best_vpd = (best["views"] or 0) / max(1, days_since(bpub))
                if not _passes_filter(
                    [c.get("channel_title"), best.get("title")],
                    score=c.get("score"), vpd=best_vpd, views=c.get("views_total"),
                ):
                    continue
                cons = c.get("consistency") or {}
                # Idade dinâmica: se tiver created_at, calcula agora (atualiza automaticamente dia a dia).
                created_at = c.get("created_at")
                if created_at:
                    try:
                        age_now = human_age_days(created_at)
                    except Exception:
                        age_now = c.get("age_days")
                else:
                    age_now = c.get("age_days")
                rows.append([
                    "✓" if is_mon else "",
                    _fmt_num(c.get("score")),
                    _safe(c.get("channel_title")),
                    _fmt_num(age_now),
                    _fmt_num(c.get("subscribers")),
                    _fmt_num(c.get("views_total")),
                    _fmt_num(c.get("views_per_video")),
                    _fmt_num(cons.get("uploads_per_week")),
                    _fmt_num(cons.get("vpd_trend")),
                    _safe(best.get("title"))[:80],
                    _fmt_num(best_vpd) if best_vpd else "—",
                    run_ts,
                ])
                ids.append(cid or "")
        sheet_ch.dehighlight_cells(all_=True)
        sheet_ch.set_sheet_data(rows, reset_col_positions=False, reset_row_positions=True, redraw=False)
        sheet_ch_ids.clear()
        sheet_ch_ids.extend(ids)
        _apply_heat(sheet_ch, rows, CH_HEAT)
        sheet_ch.redraw()

    def _refill_videos():
        mon_v_ids = {v.get("video_id") for v in state["monitored"].get("videos", [])}
        rows = []
        ids = []
        for run in state["runs"]:
            if not _run_filter_matches(run):
                continue
            run_ts = run.get("created_at") or ""
            for v in run.get("videos", []) or []:
                vid = v.get("video_id")
                is_mon = vid in mon_v_ids
                if var_only_mon.get() == "Apenas monitorados" and not is_mon:
                    continue
                if var_only_mon.get() == "Apenas não monitorados" and is_mon:
                    continue
                if not _passes_filter(
                    [v.get("title"), v.get("channel_title")],
                    vpd=v.get("vpd"), views=v.get("views"),
                ):
                    continue
                pub = v.get("published_at")
                try:
                    pub_fmt = human_date(pub) if pub else "—"
                except Exception:
                    pub_fmt = pub or "—"
                rows.append([
                    "✓" if is_mon else "",
                    _fmt_num(v.get("vpd")),
                    _fmt_num(v.get("views")),
                    pub_fmt,
                    _fmt_num(v.get("duration_min")),
                    _safe(v.get("channel_title")),
                    _safe(v.get("title"))[:120],
                    _fmt_num(v.get("likes")),
                    _fmt_num(v.get("comments")),
                    run_ts,
                ])
                ids.append(vid or "")
        sheet_v.dehighlight_cells(all_=True)
        sheet_v.set_sheet_data(rows, reset_col_positions=False, reset_row_positions=True, redraw=False)
        sheet_v_ids.clear()
        sheet_v_ids.extend(ids)
        _apply_heat(sheet_v, rows, V_HEAT)
        sheet_v.redraw()

    def _refill_runs():
        for row in tv_r.get_children():
            tv_r.delete(row)
        for run in state["runs"]:
            terms = ", ".join((run.get("terms_used") or [])[:6])
            vals = (
                run.get("created_at"),
                run.get("mode"),
                run.get("channels_count"),
                run.get("videos_count"),
                run.get("quota_used"),
                terms,
                run.get("excel_path") or "",
            )
            tv_r.insert("", "end", iid=run.get("run_id"), values=vals)

    def _refill_monitored():
        for row in tv_m.get_children():
            tv_m.delete(row)
        snap_ch = analytics.latest_snapshot_per_channel()
        for c in state["monitored"].get("channels", []) or []:
            signal = (snap_ch.get(c.get("channel_id")) or {}).get("signal", "")
            vals = (
                "canal",
                _safe(c.get("title")),
                c.get("channel_id"),
                ", ".join(c.get("tags") or []),
                (c.get("notes") or "")[:100],
                c.get("added_at"),
                signal,
            )
            tv_m.insert("", "end", iid=f"ch:{c.get('channel_id')}", values=vals)
        for v in state["monitored"].get("videos", []) or []:
            vals = (
                "vídeo",
                _safe(v.get("title")),
                v.get("video_id"),
                ", ".join(v.get("tags") or []),
                (v.get("notes") or "")[:100],
                v.get("added_at"),
                "",
            )
            tv_m.insert("", "end", iid=f"vid:{v.get('video_id')}", values=vals)

    def _refill_analytics():
        ov = analytics.overview()
        txt = (
            f"Runs: {ov['total_runs']}   |   Canais monitorados: {ov['total_monitored_channels']}   |   "
            f"Vídeos monitorados: {ov['total_monitored_videos']}   |   Snapshots: {ov['total_snapshots']}\n\n"
            f"Use as sub-abas abaixo para rankings. Tags/nichos agregam os canais monitorados."
        )
        an_summary.configure(state="normal")
        an_summary.delete("1.0", "end")
        an_summary.insert("1.0", txt)
        an_summary.configure(state="disabled")

        for row in tv_an_ch.get_children():
            tv_an_ch.delete(row)
        for c in ov["top_channels_by_avg_vpd"]:
            tv_an_ch.insert("", "end", values=(
                _safe(c.get("title")), _fmt_num(c.get("avg_vpd_recent")),
                _fmt_num(c.get("vpd_trend")), _fmt_num(c.get("subscribers")),
                _fmt_num(c.get("uploads_per_week")), _fmt_num(c.get("delta_subscribers")),
            ))

        for row in tv_an_vid.get_children():
            tv_an_vid.delete(row)
        for v in ov["top_videos_by_velocity"]:
            tv_an_vid.insert("", "end", values=(
                _safe(v.get("title"))[:90], _fmt_num(v.get("recent_velocity")),
                _fmt_num(v.get("views")), _fmt_num(v.get("delta_views")),
                _fmt_num(v.get("vpd_current")),
            ))

        for row in tv_an_niche.get_children():
            tv_an_niche.delete(row)
        for n in ov["niches"]:
            tv_an_niche.insert("", "end", values=(
                n.get("tag"), n.get("channels_count"),
                _fmt_num(n.get("avg_vpd")), _fmt_num(n.get("median_vpd")),
                _fmt_num(n.get("median_subs")),
            ))

    def reload_all():
        _reload_state()
        _refill_channels()
        _refill_videos()
        _refill_runs()
        _refill_monitored()
        _refill_analytics()

    # Habilita sort tri-state nos Treeviews restantes (Runs/Monitorados/Analytics)
    _enable_sort(tv_r, refill_fn=_refill_runs)
    _enable_sort(tv_m, refill_fn=_refill_monitored)
    _enable_sort(tv_an_ch, refill_fn=_refill_analytics)
    _enable_sort(tv_an_vid, refill_fn=_refill_analytics)
    _enable_sort(tv_an_niche, refill_fn=_refill_analytics)

    # ---------- Sort tri-state nos Sheets (Canais / Vídeos) ----------
    def _sheet_enable_sort(sheet, headers, refill_fn, heat_cols, ids_ref):
        """Sort tri-state clicando no header do tksheet: asc -> desc -> off."""
        state = {"col": None, "dir": None}
        original_headers = list(headers)

        def _to_float(s):
            if s in (None, "", "—"):
                return None
            txt = str(s).replace(".", "").replace(",", ".")
            try:
                return float(txt)
            except ValueError:
                return None

        def _on_header_click(event):
            try:
                col = sheet.identify_column(event)
            except Exception:
                return
            if col is None or col < 0:
                return

            cur_col, cur_dir = state["col"], state["dir"]
            if col != cur_col:
                new_dir = "asc"
            elif cur_dir == "asc":
                new_dir = "desc"
            elif cur_dir == "desc":
                new_dir = None
            else:
                new_dir = "asc"

            state["col"] = col if new_dir else None
            state["dir"] = new_dir

            # Atualiza marcador ▲/▼ no header sem duplicar
            new_headers = list(original_headers)
            if new_dir == "asc":
                new_headers[col] = f"{original_headers[col]} ▲"
            elif new_dir == "desc":
                new_headers[col] = f"{original_headers[col]} ▼"
            sheet.headers(new_headers)

            if new_dir is None:
                # Restaura ordem original via refill
                refill_fn()
                return

            # Captura dados + ids paralelos, reordena juntos
            data = sheet.get_sheet_data()
            # Monta lista de (key, row, id) preservando alinhamento
            entries = []
            use_numeric = True
            for i, row in enumerate(data):
                v = row[col] if col < len(row) else None
                num = _to_float(v)
                if num is None and v not in (None, "", "—"):
                    use_numeric = False
                entries.append((v, num, row, ids_ref[i] if i < len(ids_ref) else ""))

            if use_numeric:
                def key_fn(e):
                    _, num, _r, _i = e
                    if num is None:
                        return float("inf") if new_dir == "asc" else float("-inf")
                    return num
            else:
                def key_fn(e):
                    v, _n, _r, _i = e
                    return "" if v in (None, "—") else str(v).lower()

            entries.sort(key=key_fn, reverse=(new_dir == "desc"))
            new_rows = [e[2] for e in entries]
            new_ids = [e[3] for e in entries]

            sheet.dehighlight_cells(all_=True)
            sheet.set_sheet_data(new_rows, reset_col_positions=False,
                                 reset_row_positions=True, redraw=False)
            ids_ref.clear()
            ids_ref.extend(new_ids)
            # Reaplica gradientes com base na nova ordem
            _apply_heat(sheet, new_rows, heat_cols)
            sheet.redraw()

        try:
            sheet.CH.bind("<Button-1>", _on_header_click, add="+")
        except Exception:
            sheet.bind("<Button-1>", _on_header_click)

    _sheet_enable_sort(sheet_ch, [ch_headings[c] for c in ch_cols],
                       _refill_channels, CH_HEAT, sheet_ch_ids)
    _sheet_enable_sort(sheet_v, [v_headings[c] for c in v_cols],
                       _refill_videos, V_HEAT, sheet_v_ids)

    btn_reload.config(command=reload_all)

    # ---------- ações de contexto ----------
    def _sheet_selected_row(sheet):
        """Retorna o índice da linha selecionada no Sheet, ou None."""
        try:
            cs = sheet.get_currently_selected()
            if cs is None:
                return None
            # tksheet retorna uma namedtuple com .row (ou tuple (r, c))
            return getattr(cs, "row", None) if hasattr(cs, "row") else (cs[0] if cs else None)
        except Exception:
            return None

    def _selected_channel_id():
        r = _sheet_selected_row(sheet_ch)
        if r is None or r < 0 or r >= len(sheet_ch_ids):
            return None
        return sheet_ch_ids[r] or None

    def _selected_video_id():
        r = _sheet_selected_row(sheet_v)
        if r is None or r < 0 or r >= len(sheet_v_ids):
            return None
        return sheet_v_ids[r] or None

    def _find_channel_dict(cid):
        for run in state["runs"]:
            for c in run.get("channels", []) or []:
                if c.get("channel_id") == cid:
                    return c
        return None

    def _find_video_dict(vid):
        for run in state["runs"]:
            for v in run.get("videos", []) or []:
                if v.get("video_id") == vid:
                    return v
        return None

    def monitor_current_channel():
        cid = _selected_channel_id()
        if not cid:
            return
        c = _find_channel_dict(cid) or {}
        if results_store.add_monitored_channel(cid, c.get("channel_title") or "", source="resultado"):
            messagebox.showinfo("Monitor", f"Canal {cid} adicionado aos monitorados.")
        else:
            messagebox.showinfo("Monitor", "Canal já está nos monitorados.")
        reload_all()

    def unmonitor_current_channel():
        cid = _selected_channel_id()
        if not cid:
            return
        if results_store.remove_monitored_channel(cid):
            messagebox.showinfo("Monitor", f"Canal {cid} removido.")
        reload_all()

    def open_current_channel():
        cid = _selected_channel_id()
        if cid:
            _open_url(f"https://www.youtube.com/channel/{cid}")

    def copy_current_channel_url():
        cid = _selected_channel_id()
        if cid:
            _copy_to_clipboard(win, f"https://www.youtube.com/channel/{cid}")

    def monitor_current_video():
        vid = _selected_video_id()
        if not vid:
            return
        v = _find_video_dict(vid) or {}
        if results_store.add_monitored_video(vid, v.get("channel_id") or "",
                                             v.get("title") or "", source="resultado"):
            messagebox.showinfo("Monitor", f"Vídeo {vid} adicionado aos monitorados.")
        else:
            messagebox.showinfo("Monitor", "Vídeo já está nos monitorados.")
        reload_all()

    def unmonitor_current_video():
        vid = _selected_video_id()
        if vid and results_store.remove_monitored_video(vid):
            messagebox.showinfo("Monitor", f"Vídeo {vid} removido.")
        reload_all()

    def open_current_video():
        vid = _selected_video_id()
        if vid:
            _open_url(f"https://www.youtube.com/watch?v={vid}")

    def copy_current_video_url():
        vid = _selected_video_id()
        if vid:
            _copy_to_clipboard(win, f"https://www.youtube.com/watch?v={vid}")

    def purge_current_channel():
        cid = _selected_channel_id()
        if not cid:
            return
        c = _find_channel_dict(cid) or {}
        title = c.get("channel_title") or cid
        if not messagebox.askyesno(
            "Remover canal do histórico",
            f"Remover definitivamente '{title}' ({cid}) e TODOS os vídeos dele de:\n"
            "  • todos os runs do histórico\n"
            "  • lista de monitorados (se estiver)\n"
            "  • snapshots\n\n"
            "Essa ação não pode ser desfeita. Continuar?",
        ):
            return
        stats = results_store.purge_channel(cid)
        messagebox.showinfo(
            "Remover canal",
            f"Canal removido.\n\n"
            f"Runs afetados: {stats['runs_touched']}\n"
            f"Canais removidos: {stats['channels_removed']}\n"
            f"Vídeos removidos: {stats['videos_removed']}\n"
            f"Snapshots afetados: {stats['snapshots_touched']}\n"
            f"Removido dos monitorados: {'sim' if stats['monitor_channel_removed'] else 'não'}"
            f" (+{stats['monitor_videos_removed']} vídeos)",
        )
        reload_all()

    # Menus de contexto
    menu_ch = tk.Menu(win, tearoff=0)
    menu_ch.add_command(label="Monitorar canal", command=monitor_current_channel)
    menu_ch.add_command(label="Remover dos monitorados", command=unmonitor_current_channel)
    menu_ch.add_command(label="Abrir canal", command=open_current_channel)
    menu_ch.add_command(label="Copiar URL canal", command=copy_current_channel_url)
    menu_ch.add_separator()
    menu_ch.add_command(label="Remover canal do histórico", command=purge_current_channel)

    menu_vid = tk.Menu(win, tearoff=0)
    menu_vid.add_command(label="Monitorar vídeo", command=monitor_current_video)
    menu_vid.add_command(label="Remover dos monitorados", command=unmonitor_current_video)
    menu_vid.add_command(label="Abrir vídeo", command=open_current_video)
    menu_vid.add_command(label="Copiar URL vídeo", command=copy_current_video_url)

    def _popup_ch(event):
        # Seleção já foi atualizada pelo tksheet via rc_select
        menu_ch.tk_popup(event.x_root, event.y_root)

    def _popup_vid(event):
        menu_vid.tk_popup(event.x_root, event.y_root)

    # tksheet já permite rc_select; adicionamos o popup.
    # Vinculamos no widget interno do sheet (MT = main table).
    try:
        sheet_ch.MT.bind("<Button-3>", _popup_ch, add="+")
        sheet_v.MT.bind("<Button-3>", _popup_vid, add="+")
        sheet_ch.MT.bind("<Double-1>", lambda e: open_current_channel(), add="+")
        sheet_v.MT.bind("<Double-1>", lambda e: open_current_video(), add="+")
    except Exception:
        # Fallback para versões do tksheet sem .MT exposto
        sheet_ch.bind("<Button-3>", _popup_ch)
        sheet_v.bind("<Button-3>", _popup_vid)
        sheet_ch.bind("<Double-1>", lambda e: open_current_channel())
        sheet_v.bind("<Double-1>", lambda e: open_current_video())

    # Botões abaixo dos grids Canais/Vídeos
    ttk.Button(ch_btns, text="Monitorar canal", command=monitor_current_channel).pack(side="left", padx=4)
    ttk.Button(ch_btns, text="Remover monitor", command=unmonitor_current_channel).pack(side="left", padx=4)
    ttk.Button(ch_btns, text="Remover do histórico", command=purge_current_channel).pack(side="left", padx=4)
    ttk.Button(ch_btns, text="Abrir canal", command=open_current_channel).pack(side="left", padx=4)

    ttk.Button(v_btns, text="Monitorar vídeo", command=monitor_current_video).pack(side="left", padx=4)
    ttk.Button(v_btns, text="Remover monitor", command=unmonitor_current_video).pack(side="left", padx=4)
    ttk.Button(v_btns, text="Abrir vídeo", command=open_current_video).pack(side="left", padx=4)

    # ---------- Runs: exportar / remover ----------
    def _selected_run_id():
        sel = tv_r.selection()
        return sel[0] if sel else None

    def run_export_now():
        rid = _selected_run_id()
        if not rid:
            messagebox.showinfo("Runs", "Selecione um run.")
            return
        def target():
            try:
                export_run_to_excel(rid, status_cb=lambda m: None)
                messagebox.showinfo("Runs", f"Run {rid} exportado para Excel.")
            except Exception as ex:
                messagebox.showerror("Runs", f"Erro: {ex}")
        threading.Thread(target=target, daemon=True).start()

    def run_remove_now():
        rid = _selected_run_id()
        if not rid:
            return
        if not messagebox.askyesno("Remover run", f"Remover run {rid} permanentemente?"):
            return
        results_store.remove_run(rid)
        reload_all()

    def run_import_xlsx_now():
        if not messagebox.askyesno(
            "Importar planilhas antigas",
            "Isso vai ler todos os 'relatorio_canais_*.xlsx' em dados/ e "
            "adicionar como runs no histórico interno (runs já existentes são ignorados).\n\n"
            "Continuar?",
        ):
            return

        def target():
            try:
                from .import_xlsx import import_all_from
                stats = import_all_from(status_cb=lambda m: None)
                msg = (
                    f"Importação concluída.\n\n"
                    f"Arquivos encontrados: {stats['total']}\n"
                    f"Importados: {stats['imported']}\n"
                    f"Pulados (já importados): {stats['skipped']}\n"
                    f"Erros: {stats['errors']}"
                )
                if stats.get("errors_details"):
                    msg += "\n\nErros:\n" + "\n".join(stats["errors_details"][:5])
                messagebox.showinfo("Importar planilhas antigas", msg)
                reload_all()
            except Exception as ex:
                messagebox.showerror("Importar planilhas antigas", f"Erro: {ex}")

        threading.Thread(target=target, daemon=True).start()

    btn_run_export.config(command=run_export_now)
    btn_run_remove.config(command=run_remove_now)
    btn_run_import.config(command=run_import_xlsx_now)

    # ---------- Monitorados: ações ----------
    def _selected_monitored():
        sel = tv_m.selection()
        if not sel:
            return None, None
        iid = sel[0]
        if iid.startswith("ch:"):
            return "channel", iid[3:]
        if iid.startswith("vid:"):
            return "video", iid[4:]
        return None, None

    def monitored_remove():
        kind, the_id = _selected_monitored()
        if not kind:
            return
        if kind == "channel":
            results_store.remove_monitored_channel(the_id)
        else:
            results_store.remove_monitored_video(the_id)
        reload_all()

    def monitored_edit_tags():
        kind, the_id = _selected_monitored()
        if not kind:
            return
        current = ""
        obj = results_store.load_monitored()
        key = "channels" if kind == "channel" else "videos"
        id_key = "channel_id" if kind == "channel" else "video_id"
        for it in obj.get(key, []):
            if it.get(id_key) == the_id:
                current = ", ".join(it.get("tags") or [])
                break
        val = simpledialog.askstring("Tags", "Tags separadas por vírgula:", initialvalue=current)
        if val is None:
            return
        tags = [t.strip() for t in val.split(",") if t.strip()]
        results_store.set_monitored_tags(kind, the_id, tags)
        reload_all()

    def monitored_edit_notes():
        kind, the_id = _selected_monitored()
        if not kind:
            return
        current = ""
        obj = results_store.load_monitored()
        key = "channels" if kind == "channel" else "videos"
        id_key = "channel_id" if kind == "channel" else "video_id"
        for it in obj.get(key, []):
            if it.get(id_key) == the_id:
                current = it.get("notes") or ""
                break
        val = simpledialog.askstring("Notas", "Notas livres:", initialvalue=current)
        if val is None:
            return
        results_store.set_monitored_notes(kind, the_id, val)
        reload_all()

    def monitored_update_now():
        if not messagebox.askyesno("Atualizar", "Coletar snapshot atual de todos os monitorados agora?"):
            return

        def target():
            try:
                update_monitored(status_cb=lambda m: None)
            except QuotaExceeded as ex:
                messagebox.showerror("Cota", str(ex))
            except Exception as ex:
                messagebox.showerror("Erro", str(ex))
            reload_all()

        threading.Thread(target=target, daemon=True).start()

    def _parse_monitored_input(raw):
        """Retorna (kind, the_id_or_handle, error).
        kind: 'channel' | 'video' | 'handle' | None
        """
        s = (raw or "").strip()
        if not s:
            return None, None, "vazio"
        # URL de vídeo
        if "watch?v=" in s:
            vid = s.split("watch?v=", 1)[1].split("&", 1)[0]
            if vid:
                return "video", vid, None
        if "youtu.be/" in s:
            vid = s.split("youtu.be/", 1)[1].split("?", 1)[0].split("/", 1)[0]
            if vid:
                return "video", vid, None
        # URL de canal
        if "/channel/" in s:
            cid = s.split("/channel/", 1)[1].split("/", 1)[0].split("?", 1)[0]
            if cid.startswith("UC"):
                return "channel", cid, None
        # Handle @ → será resolvido via API
        if "/@" in s or s.startswith("@"):
            return "handle", s, None
        # ID solto
        if s.startswith("UC") and len(s) >= 20:
            return "channel", s, None
        if len(s) == 11 and all(c.isalnum() or c in "-_" for c in s):
            return "video", s, None
        return None, None, "formato não reconhecido"

    def monitored_add_dialog():
        dlg = tk.Toplevel(win)
        dlg.title("Adicionar monitorado")
        dlg.geometry("560x260")
        dlg.transient(win)
        try:
            dlg.grab_set()
        except Exception:
            pass

        ttk.Label(dlg, text="Cole URL ou ID (1 por linha):").pack(anchor="w", padx=10, pady=(10, 4))
        ttk.Label(dlg, text="• Canal: URL /channel/UC... ou ID UC...", foreground="#888").pack(anchor="w", padx=10)
        ttk.Label(dlg, text="• Vídeo: URL watch?v=... / youtu.be/... ou ID de 11 chars", foreground="#888").pack(anchor="w", padx=10)
        ttk.Label(dlg, text="• @handle: resolvido automaticamente via API (custa ~100 cota/handle)", foreground="#888").pack(anchor="w", padx=10, pady=(0, 4))

        txt = tk.Text(dlg, height=6, wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=4)

        def _go():
            lines = [ln for ln in txt.get("1.0", "end").splitlines() if ln.strip()]
            dlg.destroy()

            def work():
                added_ch = added_vid = 0
                errors = []
                handles_to_resolve = []  # [(orig_line, handle_str)]
                for ln in lines:
                    kind, value, err = _parse_monitored_input(ln)
                    if err:
                        errors.append(f"{ln.strip()[:40]} → {err}")
                        continue
                    if kind == "channel":
                        if results_store.add_monitored_channel(value, source="manual"):
                            added_ch += 1
                    elif kind == "video":
                        if results_store.add_monitored_video(value, source="manual"):
                            added_vid += 1
                    elif kind == "handle":
                        handles_to_resolve.append((ln.strip(), value))

                # Resolve handles depois (precisa de API)
                if handles_to_resolve:
                    from .youtube_api import resolve_handle_to_channel_id
                    for orig, h in handles_to_resolve:
                        try:
                            cid = resolve_handle_to_channel_id(h)
                        except Exception as ex:
                            errors.append(f"{orig[:40]} → erro na API: {ex}")
                            continue
                        if cid:
                            if results_store.add_monitored_channel(cid, source="manual"):
                                added_ch += 1
                        else:
                            errors.append(f"{orig[:40]} → handle não encontrado")

                msg = f"Adicionados: {added_ch} canal(is), {added_vid} vídeo(s)."
                if handles_to_resolve:
                    msg += f"\n(Handles resolvidos via API: {len(handles_to_resolve)})"
                if errors:
                    msg += "\n\nIgnorados/Erros:\n" + "\n".join(errors[:10])
                messagebox.showinfo("Adicionar monitorado", msg)
                reload_all()

            threading.Thread(target=work, daemon=True).start()

        btns = ttk.Frame(dlg); btns.pack(pady=8)
        ttk.Button(btns, text="Adicionar", command=_go).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancelar", command=dlg.destroy).pack(side="left", padx=4)

    btn_mon_add.config(command=monitored_add_dialog)
    btn_mon_remove.config(command=monitored_remove)
    btn_mon_tags.config(command=monitored_edit_tags)
    btn_mon_notes.config(command=monitored_edit_notes)
    btn_mon_update.config(command=monitored_update_now)

    # Carga inicial
    reload_all()

    # Workaround para o Tkinter não calcular larguras de coluna corretamente na primeira render:
    # força um re-layout depois que a janela tiver dimensões reais.
    def _force_layout():
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        if w > 1 and h > 1:
            win.geometry(f"{w + 1}x{h}")
            win.after(30, lambda: win.geometry(f"{w}x{h}"))

    win.after(50, _force_layout)

    return win
