# -*- coding: utf-8 -*-
"""GUI Tkinter (+ ttkbootstrap se disponível) com logging thread-safe."""
import os
import sys
import queue
import threading
import subprocess
import webbrowser
from pathlib import Path

from . import config
from . import scheduler
from .utils import QuotaExceeded
from .engine import run_engine, run_monitor
from .tooltip import help_badge
from .results_window import open_results_window


def open_folder(p: Path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(p))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)])
        else:
            subprocess.run(["xdg-open", str(p)])
    except Exception:
        webbrowser.open(f"file://{p.resolve()}")


def make_gui():
    try:
        import tkinter as tk
        from tkinter import ttk
        import ttkbootstrap as tb
        ThemedTk = tb.Window
        use_tb = True
    except Exception:
        import tkinter as tk
        from tkinter import ttk
        ThemedTk = tk.Tk
        use_tb = False

    root = ThemedTk()
    root.title(config.APP_NAME)
    if use_tb:
        root.geometry("1100x860")
        try:
            root.style = tb.Style(theme="darkly")
        except Exception:
            pass
    else:
        root.geometry("1100x860")

    CFG = config.CFG

    var_min_channels = tk.IntVar(value=CFG["MIN_CHANNELS_PER_SHEET"])
    var_uploads_sample = tk.IntVar(value=CFG["UPLOADS_SAMPLE"])
    var_age_max = tk.IntVar(value=CFG["BASE_MAX_CHANNEL_AGE_DAYS"])
    var_age_min = tk.IntVar(value=CFG.get("BASE_MIN_CHANNEL_AGE_DAYS", 30))
    var_min_views = tk.IntVar(value=CFG["BASE_MIN_VIEWS"])
    var_min_vpd = tk.IntVar(value=CFG.get("BASE_MIN_VPD", 300))
    var_vpd_sat = tk.IntVar(value=CFG.get("VPD_SATURATION", 50000))
    var_window_days = tk.IntVar(value=CFG["BASE_PUBLISHED_AFTER_DAYS"])
    var_search_order = tk.StringVar(value=CFG.get("SEARCH_ORDER", "relevance"))

    var_allow_repeated = tk.BooleanVar(value=CFG.get("ALLOW_REPEATED_AS_LAST_RESORT", False))
    var_allow_older = tk.BooleanVar(value=CFG.get("ALLOW_OLDER_AS_LAST_RESORT", True))
    var_older_max = tk.IntVar(value=CFG.get("OLDER_MAX_CHANNEL_AGE_DAYS", 365))
    var_force_too_old = tk.BooleanVar(value=CFG.get("FORCE_TOO_OLD_BEFORE_FAILSAFE", True))

    var_lang_pt = tk.BooleanVar(value=("pt" in CFG["SELECTED_LANGS"]))
    var_lang_es = tk.BooleanVar(value=("es" in CFG["SELECTED_LANGS"]))
    var_lang_en = tk.BooleanVar(value=("en" in CFG["SELECTED_LANGS"]))

    var_pages_per_term = tk.IntVar(value=CFG["SEARCH_PAGES_PER_TERM"])
    var_terms_per_run = tk.IntVar(value=CFG["SEARCH_TERMS_PER_RUN"])
    var_quota_per_key = tk.IntVar(value=CFG.get("QUOTA_BUDGET_PER_KEY", 8000))

    var_raw_mode = tk.BooleanVar(value=CFG.get("RAW_EXPORT_MODE", False))
    var_raw_limit = tk.IntVar(value=CFG.get("RAW_LIMIT", 250))
    var_raw_sort = tk.StringVar(value=CFG.get("RAW_SORT_BY", "views_per_day"))
    var_raw_trending = tk.BooleanVar(value=CFG.get("RAW_INCLUDE_TRENDING", True))
    var_raw_related = tk.BooleanVar(value=CFG.get("RAW_INCLUDE_RELATED", False))
    var_raw_strict_window = tk.BooleanVar(value=CFG.get("STRICT_WINDOW_IN_RAW", True))
    var_auto_excel = tk.BooleanVar(value=CFG.get("AUTO_EXPORT_EXCEL", False))
    var_daily = tk.BooleanVar(value=scheduler.is_enabled())

    keys_text = "\n".join(CFG.get("API_KEYS", []))

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)

    lf_lang = ttk.LabelFrame(frm, text="Idiomas & RAW")
    lf_lang.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=(0, 12))
    ttk.Checkbutton(lf_lang, text="Português (pt)", variable=var_lang_pt).grid(row=0, column=0, sticky="w", padx=8, pady=6)
    ttk.Checkbutton(lf_lang, text="Espanhol (es)", variable=var_lang_es).grid(row=1, column=0, sticky="w", padx=8, pady=6)
    ttk.Checkbutton(lf_lang, text="Inglês (en)", variable=var_lang_en).grid(row=2, column=0, sticky="w", padx=8, pady=6)

    ttk.Separator(lf_lang, orient="horizontal").grid(row=3, column=0, sticky="ew", padx=8, pady=(6, 6))

    ttk.Checkbutton(lf_lang, text="Modo Dump (vídeos crus)", variable=var_raw_mode).grid(row=4, column=0, sticky="w", padx=8, pady=6)
    help_badge(
        lf_lang,
        "Modo Dump (RAW): exporta vídeos crus, sem calcular score, sem filtrar canais "
        "novos/antigos e sem checar 'já visto'. Útil para varredura ampla. "
        "Quando desligado, roda o modo Scored padrão (com ranking 0–100).",
    ).grid(row=4, column=2, sticky="w", padx=4)

    ttk.Label(lf_lang, text="Limite de vídeos (RAW)").grid(row=5, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_lang, textvariable=var_raw_limit, width=10).grid(row=5, column=1, sticky="w", padx=6)
    help_badge(
        lf_lang,
        "Quantidade máxima de vídeos que serão escritos na planilha RAW. "
        "Os vídeos são ordenados conforme 'Ordenar por (RAW)' antes de aplicar este corte.",
    ).grid(row=5, column=2, sticky="w", padx=4)

    ttk.Label(lf_lang, text="Ordenar por (RAW)").grid(row=6, column=0, sticky="w", padx=8, pady=6)
    cmb = ttk.Combobox(lf_lang, textvariable=var_raw_sort,
                       values=["views_per_day", "views", "date_desc", "random"],
                       width=14, state="readonly")
    cmb.grid(row=6, column=1, sticky="w", padx=6)
    help_badge(
        lf_lang,
        "Como ordenar os vídeos na planilha RAW:\n"
        "• views_per_day — views ÷ dias desde publicação (ritmo de crescimento)\n"
        "• views — total de visualizações (favorece virais antigos)\n"
        "• date_desc — mais recentes primeiro\n"
        "• random — embaralha (útil para descoberta diversificada)",
    ).grid(row=6, column=2, sticky="w", padx=4)

    ttk.Checkbutton(lf_lang, text="Incluir Trending (RAW)", variable=var_raw_trending).grid(row=7, column=0, sticky="w", padx=8, pady=6)
    help_badge(
        lf_lang,
        "Adiciona vídeos da seção 'Em alta' (mostPopular) das categorias configuradas "
        "(default: Educação 27, Ciência & Tech 28, Notícias 25). "
        "Custo de quota baixo (videos=1) — geralmente vale a pena ligar.",
    ).grid(row=7, column=2, sticky="w", padx=4)

    ttk.Checkbutton(lf_lang, text="Incluir Relacionados (RAW)", variable=var_raw_related).grid(row=8, column=0, sticky="w", padx=8, pady=6)
    help_badge(
        lf_lang,
        "Para alguns vídeos coletados, busca também os 'relacionados' do YouTube. "
        "ATENÇÃO: a API relatedToVideoId foi descontinuada em 2023 — pode retornar "
        "vazio silenciosamente. Cada chamada custa 100 unidades de quota.",
    ).grid(row=8, column=2, sticky="w", padx=4)

    ttk.Checkbutton(lf_lang, text="Aplicar janela rigidamente (RAW)", variable=var_raw_strict_window).grid(row=9, column=0, sticky="w", padx=8, pady=6)
    help_badge(
        lf_lang,
        "Se ligado, descarta no RAW qualquer vídeo publicado fora da 'Janela publicados (dias)'. "
        "Se desligado, a API ainda filtra por publishedAfter, mas vídeos retornados via "
        "Trending/Relacionados podem fugir da janela.",
    ).grid(row=9, column=2, sticky="w", padx=4)

    ttk.Separator(lf_lang, orient="horizontal").grid(row=10, column=0, sticky="ew", padx=8, pady=(6, 6))
    ttk.Checkbutton(lf_lang, text="Gerar Excel automático", variable=var_auto_excel).grid(row=11, column=0, sticky="w", padx=8, pady=6)
    help_badge(
        lf_lang,
        "Se ligado, cada execução gera automaticamente um arquivo .xlsx em dados/. "
        "Se desligado (padrão), os resultados ficam apenas no histórico interno e "
        "podem ser exportados sob demanda pela janela 'Ver canais/vídeos'.",
    ).grid(row=11, column=2, sticky="w", padx=4)

    def _toggle_daily():
        from tkinter import messagebox
        if var_daily.get():
            ok, msg = scheduler.enable()
            if ok:
                messagebox.showinfo("Monitor diário", msg)
            else:
                var_daily.set(False)
                messagebox.showerror("Monitor diário", msg)
        else:
            ok, msg = scheduler.disable()
            if ok:
                messagebox.showinfo("Monitor diário", msg)
            else:
                var_daily.set(True)
                messagebox.showerror("Monitor diário", msg)

    ttk.Checkbutton(lf_lang, text="Monitorar todo dia (no login do Windows)",
                    variable=var_daily, command=_toggle_daily).grid(row=12, column=0, sticky="w", padx=8, pady=6)
    help_badge(
        lf_lang,
        "Registra uma tarefa no Agendador do Windows que, ao fazer login, roda a análise "
        "dos canais/vídeos monitorados. Usa trava para rodar no MÁXIMO 1× por dia. "
        "Se encontrar novidades (canal aquecendo, inscritos subindo, vídeo acelerando), "
        "mostra um aviso com botão 'Abrir programa'. Sem novidades, fica silencioso.",
    ).grid(row=12, column=2, sticky="w", padx=4)

    lf_params = ttk.LabelFrame(frm, text="Parâmetros (vídeos/canais)")
    lf_params.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=(0, 12))
    ttk.Label(lf_params, text="Janela publicados (dias)").grid(row=0, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_params, textvariable=var_window_days, width=10).grid(row=0, column=1, padx=8, pady=6, sticky="w")

    ttk.Label(lf_params, text="Views mín. por vídeo").grid(row=1, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_params, textvariable=var_min_views, width=10).grid(row=1, column=1, padx=8, pady=6, sticky="w")
    help_badge(
        lf_params,
        "Views mínimas para um vídeo ser considerado. Funciona em OR com 'VPD mínimo': "
        "se o vídeo bater QUALQUER um dos dois critérios, passa. "
        "Para achar canais pequenos em crescimento, baixe este número (ex.: 5000).",
    ).grid(row=1, column=2, padx=4, sticky="w")

    ttk.Label(lf_params, text="VPD mín. (views/dia)").grid(row=2, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_params, textvariable=var_min_vpd, width=10).grid(row=2, column=1, padx=8, pady=6, sticky="w")
    help_badge(
        lf_params,
        "Views por dia mínimo (views ÷ dias desde publicação). É o critério-chave para achar "
        "canais pequenos com vídeos emergindo. Ex.: 300 VPD = um vídeo com 3000 views em 10 dias "
        "passa, mesmo com total de views baixo.",
    ).grid(row=2, column=2, padx=4, sticky="w")

    ttk.Label(lf_params, text="Duração mín. (min)").grid(row=3, column=0, sticky="w", padx=8, pady=6)
    ent_dur = ttk.Entry(lf_params, width=10)
    ent_dur.insert(0, str(CFG["BASE_MIN_DURATION_MIN"]))
    ent_dur.grid(row=3, column=1, padx=8, pady=6, sticky="w")
    help_badge(
        lf_params,
        "Duração mínima do vídeo. Use 1 para aceitar Shorts; 8 para vídeos médios+; "
        "20 para documentários/podcasts longos. No nicho YouTube 2025, 8-15min costuma ser o sweet spot.",
    ).grid(row=3, column=2, padx=4, sticky="w")

    ttk.Label(lf_params, text="Idade mín. do canal (dias)").grid(row=4, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_params, textvariable=var_age_min, width=10).grid(row=4, column=1, padx=8, pady=6, sticky="w")
    help_badge(
        lf_params,
        "Canais MAIS NOVOS que esta idade são descartados. Evita farms recém-criadas e "
        "dá tempo do YouTube indexar. Padrão: 30 dias.",
    ).grid(row=4, column=2, padx=4, sticky="w")

    ttk.Label(lf_params, text="Idade máx. do canal (dias)").grid(row=5, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_params, textvariable=var_age_max, width=10).grid(row=5, column=1, padx=8, pady=6, sticky="w")
    help_badge(
        lf_params,
        "Canais MAIS VELHOS que esta idade são descartados (no modo Scored). "
        "Para buscar canais consolidados em crescimento, use 365+. Para canais bem novos, use 90.",
    ).grid(row=5, column=2, padx=4, sticky="w")

    ttk.Label(lf_params, text="Uploads amostrados [Scored]").grid(row=6, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_params, textvariable=var_uploads_sample, width=10).grid(row=6, column=1, padx=8, pady=6, sticky="w")

    ttk.Label(lf_params, text="Mín. canais por planilha [Scored]").grid(row=7, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_params, textvariable=var_min_channels, width=10).grid(row=7, column=1, padx=8, pady=6, sticky="w")

    ttk.Separator(lf_params, orient="horizontal").grid(row=8, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 6))

    ttk.Label(lf_params, text="Ordenação da busca").grid(row=9, column=0, sticky="w", padx=8, pady=6)
    ttk.Combobox(lf_params, textvariable=var_search_order,
                 values=["relevance", "date", "viewCount", "rating"],
                 width=14, state="readonly").grid(row=9, column=1, sticky="w", padx=8, pady=6)
    help_badge(
        lf_params,
        "Como o YouTube ordena os resultados da busca por termo:\n"
        "• relevance — mistura relevância + popularidade (padrão, bom para descoberta)\n"
        "• date — mais recentes primeiro (ideal para achar virais fresquinhos)\n"
        "• viewCount — os mais assistidos no termo (favorece canais grandes)\n"
        "• rating — melhor rating (pouco útil hoje)",
    ).grid(row=9, column=2, padx=4, sticky="w")

    ttk.Label(lf_params, text="VPD saturation (score)").grid(row=10, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_params, textvariable=var_vpd_sat, width=10).grid(row=10, column=1, padx=8, pady=6, sticky="w")
    help_badge(
        lf_params,
        "Teto usado para normalizar VPD no Score (log-escala). VPD acima deste valor é "
        "considerado 'máximo'. Padrão 50000. Suba para 100000 se você busca nichos com vídeos virais.",
    ).grid(row=10, column=2, padx=4, sticky="w")

    ttk.Label(lf_params, text="Páginas por termo (search)").grid(row=11, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_params, textvariable=var_pages_per_term, width=10).grid(row=11, column=1, padx=8, pady=6, sticky="w")
    help_badge(
        lf_params,
        "Quantas páginas de resultados (50 vídeos cada) buscar por termo. "
        "Cada página custa 100 unidades de quota. 1 página costuma ser suficiente — "
        "aumentar só se a quota permitir e você quiser mais profundidade por termo.",
    ).grid(row=11, column=2, padx=4, sticky="w")

    ttk.Label(lf_params, text="Termos por execução (0 = automático)").grid(row=12, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_params, textvariable=var_terms_per_run, width=10).grid(row=12, column=1, padx=8, pady=6, sticky="w")
    help_badge(
        lf_params,
        "Quantos termos diferentes serão usados em cada rodada.\n"
        "• 0 = programa decide (usa tudo que couber no orçamento de cota).\n"
        "• > 0 = teto fixo (se não couber na cota, cai automaticamente para o que cabe).\n\n"
        "Custo: 100 × termos × idiomas × páginas. Com 6 API keys × 8000 cota/key = 48000 total.",
    ).grid(row=12, column=2, padx=4, sticky="w")

    ttk.Label(lf_params, text="Cota por API key").grid(row=13, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_params, textvariable=var_quota_per_key, width=10).grid(row=13, column=1, padx=8, pady=6, sticky="w")
    help_badge(
        lf_params,
        "Orçamento de cota POR API key. O total efetivo = este valor × número de keys. "
        "YouTube dá 10.000/dia grátis por projeto. Default 8000 deixa folga de segurança. "
        "Quando uma key esgota, o app troca automaticamente para a próxima.",
    ).grid(row=13, column=2, padx=4, sticky="w")

    lf_keys = ttk.LabelFrame(frm, text="API Keys (uma por linha)")
    lf_keys.grid(row=0, column=2, sticky="nsew", padx=(0, 0), pady=(0, 8))
    txt_keys = tk.Text(lf_keys, width=40, height=6, wrap="none")
    txt_keys.insert("1.0", keys_text)
    txt_keys.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
    lf_keys.grid_columnconfigure(0, weight=1)
    lf_keys.grid_rowconfigure(0, weight=1)

    lf_log = ttk.LabelFrame(frm, text="Log")
    lf_log.grid(row=1, column=2, rowspan=3, sticky="nsew", pady=(0, 12))
    txt_log = tk.Text(lf_log, width=40, height=18, wrap="word")
    txt_log.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
    lf_log.grid_rowconfigure(0, weight=1)
    lf_log.grid_columnconfigure(0, weight=1)

    lf_fallback = ttk.LabelFrame(frm, text="Fallbacks [Somente modo Scored]")
    lf_fallback.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
    ttk.Checkbutton(lf_fallback, text="Permitir repetidos (último recurso)", variable=var_allow_repeated).grid(row=0, column=0, sticky="w", padx=8, pady=6)
    ttk.Checkbutton(lf_fallback, text="Permitir mais antigos (com teto)", variable=var_allow_older).grid(row=0, column=1, sticky="w", padx=8, pady=6)
    ttk.Label(lf_fallback, text="Idade máx. (teto, dias)").grid(row=0, column=2, sticky="w", padx=8, pady=6)
    ttk.Entry(lf_fallback, textvariable=var_older_max, width=10).grid(row=0, column=3, sticky="w", padx=8, pady=6)
    ttk.Checkbutton(lf_fallback, text="Completar com 'muito antigos' antes do fail-safe", variable=var_force_too_old).grid(row=1, column=0, columnspan=4, sticky="w", padx=8, pady=6)

    btns = ttk.Frame(frm)
    btns.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 6))
    for i in range(5):
        btns.grid_columnconfigure(i, weight=1)

    btn_run = ttk.Button(btns, text="Executar agora")
    btn_run.grid(row=0, column=0, padx=4, pady=4, sticky="ew")
    btn_monitor = ttk.Button(btns, text="Monitorar IDs")
    btn_monitor.grid(row=0, column=1, padx=4, pady=4, sticky="ew")
    btn_results = ttk.Button(btns, text="Ver canais / vídeos",
                             command=lambda: open_results_window(root))
    btn_results.grid(row=0, column=2, padx=4, pady=4, sticky="ew")
    btn_open = ttk.Button(btns, text="Abrir pasta de dados", command=lambda: open_folder(config.DATA_DIR))
    btn_open.grid(row=0, column=3, padx=4, pady=4, sticky="ew")
    btn_save = ttk.Button(btns, text="Salvar configurações")
    btn_save.grid(row=0, column=4, padx=4, pady=4, sticky="ew")

    lf_manual = ttk.LabelFrame(frm, text="Termos de busca manuais (1 por linha; vazio = lista padrão)")
    lf_manual.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
    txt_manual_terms = tk.Text(lf_manual, height=5, wrap="word")
    txt_manual_terms.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
    lf_manual.grid_rowconfigure(0, weight=1)
    lf_manual.grid_columnconfigure(0, weight=1)

    frm.grid_rowconfigure(0, weight=1)
    frm.grid_rowconfigure(3, weight=1)
    frm.grid_columnconfigure(0, weight=1)
    frm.grid_columnconfigure(1, weight=1)
    frm.grid_columnconfigure(2, weight=1)

    log_queue = queue.Queue()
    runner_thread = {"th": None}
    running_flag = {"running": False}

    # Estilo para links clicáveis no log
    txt_log.tag_configure("link", foreground="#4ea1ff", underline=True)

    def _open_url_from_log(url: str):
        try:
            webbrowser.open(url)
        except Exception:
            pass

    import re as _re
    _url_re = _re.compile(r"https?://[^\s<>\"'()]+")

    _link_seq = {"n": 0}

    def _append_log_main(msg: str):
        # Insere texto preservando links clicáveis
        text = msg + "\n"
        pos = 0
        for m in _url_re.finditer(text):
            start, end = m.span()
            if start > pos:
                txt_log.insert("end", text[pos:start])
            url = m.group(0)
            tag_name = f"url_{_link_seq['n']}"
            _link_seq['n'] += 1
            txt_log.insert("end", url, ("link", tag_name))
            txt_log.tag_bind(tag_name, "<Button-1>",
                             lambda _e, u=url: _open_url_from_log(u))
            txt_log.tag_bind(tag_name, "<Enter>",
                             lambda _e: txt_log.config(cursor="hand2"))
            txt_log.tag_bind(tag_name, "<Leave>",
                             lambda _e: txt_log.config(cursor=""))
            pos = end
        if pos < len(text):
            txt_log.insert("end", text[pos:])
        txt_log.see("end")

    def _drain_log():
        try:
            while True:
                msg = log_queue.get_nowait()
                _append_log_main(msg)
        except queue.Empty:
            pass
        root.after(120, _drain_log)

    def log_from_worker(message: str):
        log_queue.put(message)

    _drain_log()

    def save_cfg():
        langs = []
        if var_lang_pt.get(): langs.append("pt")
        if var_lang_es.get(): langs.append("es")
        if var_lang_en.get(): langs.append("en")

        keys = [ln.strip() for ln in txt_keys.get("1.0", "end").splitlines() if len(ln.strip()) >= 20]

        try:
            base_min_dur = int(ent_dur.get().strip() or "20")
        except Exception:
            base_min_dur = 20

        CFG["SELECTED_LANGS"] = langs
        CFG["MIN_CHANNELS_PER_SHEET"] = int(var_min_channels.get() or 5)
        CFG["UPLOADS_SAMPLE"] = int(var_uploads_sample.get() or 6)
        CFG["BASE_MAX_CHANNEL_AGE_DAYS"] = int(var_age_max.get() or 365)
        CFG["BASE_MIN_CHANNEL_AGE_DAYS"] = max(0, int(var_age_min.get() or 30))
        CFG["BASE_MIN_VIEWS"] = int(var_min_views.get() or 5000)
        CFG["BASE_MIN_VPD"] = max(0, int(var_min_vpd.get() or 300))
        CFG["VPD_SATURATION"] = max(1000, int(var_vpd_sat.get() or 50000))
        CFG["SEARCH_ORDER"] = str(var_search_order.get() or "relevance")
        CFG["BASE_PUBLISHED_AFTER_DAYS"] = int(var_window_days.get() or 90)
        CFG["BASE_MIN_DURATION_MIN"] = base_min_dur

        CFG["ALLOW_REPEATED_AS_LAST_RESORT"] = bool(var_allow_repeated.get())
        CFG["ALLOW_OLDER_AS_LAST_RESORT"] = bool(var_allow_older.get())
        CFG["OLDER_MAX_CHANNEL_AGE_DAYS"] = int(var_older_max.get() or 365)
        CFG["FORCE_TOO_OLD_BEFORE_FAILSAFE"] = bool(var_force_too_old.get())

        CFG["SEARCH_PAGES_PER_TERM"] = int(var_pages_per_term.get() or 1)
        try:
            _terms_raw = int(var_terms_per_run.get())
        except Exception:
            _terms_raw = 0
        CFG["SEARCH_TERMS_PER_RUN"] = max(0, _terms_raw)
        CFG["QUOTA_BUDGET_PER_KEY"] = max(100, int(var_quota_per_key.get() or 8000))

        CFG["RAW_EXPORT_MODE"] = bool(var_raw_mode.get())
        CFG["RAW_LIMIT"] = int(var_raw_limit.get() or 250)
        CFG["RAW_SORT_BY"] = str(var_raw_sort.get() or "views_per_day")
        CFG["RAW_INCLUDE_TRENDING"] = bool(var_raw_trending.get())
        CFG["RAW_INCLUDE_RELATED"] = bool(var_raw_related.get())
        CFG["STRICT_WINDOW_IN_RAW"] = bool(var_raw_strict_window.get())
        CFG["AUTO_EXPORT_EXCEL"] = bool(var_auto_excel.get())

        CFG["API_KEYS"] = keys
        config.save_config(CFG)

        config.API_KEYS = CFG["API_KEYS"][:]
        config._current_key_idx = 0
        config.resize_quota_for_keys()

        _append_log_main("✔️ Configurações salvas.")

    def _poll_runner():
        th = runner_thread["th"]
        if th is not None and th.is_alive():
            root.after(200, _poll_runner)
        else:
            running_flag["running"] = False
            btn_run.config(state="normal")
            try:
                btn_monitor.config(state="normal")
            except Exception:
                pass
            _append_log_main("🏁 Execução finalizada.")

    def run_now():
        if running_flag["running"]:
            _append_log_main("⚠️ Já existe uma execução em andamento. Aguarde terminar.")
            return

        raw_terms = txt_manual_terms.get("1.0", "end").strip()
        if raw_terms:
            terms = [t.strip() for t in raw_terms.replace(";", "\n").splitlines() if t.strip()]
            config.CUSTOM_SEARCH_TERMS = terms
        else:
            config.CUSTOM_SEARCH_TERMS = []

        save_cfg()
        txt_log.delete("1.0", "end")
        _append_log_main("🚀 Iniciando execução...")

        running_flag["running"] = True
        btn_run.config(state="disabled")

        def target():
            try:
                out = run_engine(status_cb=log_from_worker)
                if isinstance(out, dict):
                    if out.get("excel_path"):
                        log_from_worker(f"📁 Excel gerado: {out['excel_path']}")
                    log_from_worker(f"ℹ️ Use 'Ver canais / vídeos' para explorar o run {out.get('run_id')}.")
                elif out:
                    log_from_worker(f"📁 Arquivo gerado: {out}")
            except QuotaExceeded as e:
                log_from_worker(f"[COTA] {e}")
            except Exception as e:
                log_from_worker(f"❌ Erro: {e}")

        th = threading.Thread(target=target, daemon=True)
        runner_thread["th"] = th
        th.start()
        _poll_runner()

    def run_monitor_ids():
        if running_flag["running"]:
            _append_log_main("⚠️ Já existe uma execução em andamento. Aguarde terminar.")
            return

        dlg = tk.Toplevel(root)
        dlg.title("Monitorar canais")
        dlg.geometry("560x320")
        dlg.transient(root)
        try:
            dlg.grab_set()
        except Exception:
            pass
        ttk.Label(dlg, text="Cole channel_ids ou URLs de canais (1 por linha):").pack(anchor="w", padx=10, pady=(10, 4))
        txt = tk.Text(dlg, height=12, wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=4)

        def _parse_channel_inputs(raw):
            """Retorna (ids_prontos: list, handles_a_resolver: list)."""
            ids = []
            handles = []
            for ln in raw.splitlines():
                s = ln.strip()
                if not s:
                    continue
                # ID UC... solto
                if s.startswith("UC") and "/" not in s and len(s) >= 20:
                    ids.append(s); continue
                # URL /channel/UC...
                if "/channel/" in s:
                    tail = s.split("/channel/", 1)[1].split("/", 1)[0].split("?", 1)[0]
                    if tail.startswith("UC"):
                        ids.append(tail); continue
                # Handle @... ou URL /@...
                if s.startswith("@") or "/@" in s:
                    handles.append(s); continue
                # Outro formato qualquer — tenta como ID puro mesmo
                ids.append(s)
            return ids, handles

        def _go():
            raw = txt.get("1.0", "end")
            ids, handles = _parse_channel_inputs(raw)
            dlg.destroy()
            if not ids and not handles:
                _append_log_main("⚠️ Nenhum ID válido colado.")
                return
            save_cfg()
            txt_log.delete("1.0", "end")
            n_total = len(ids) + len(handles)
            _append_log_main(f"📡 Iniciando monitor de {n_total} canal(is)...")
            if handles:
                _append_log_main(
                    f"🔎 {len(handles)} handle(s) @ serão resolvidos via API (~100 cota cada)."
                )
            running_flag["running"] = True
            btn_run.config(state="disabled")
            btn_monitor.config(state="disabled")

            def target():
                try:
                    # Resolve handles em UC... primeiro
                    final_ids = list(ids)
                    if handles:
                        from .youtube_api import resolve_handle_to_channel_id
                        for h in handles:
                            try:
                                cid = resolve_handle_to_channel_id(h)
                            except Exception as ex:
                                log_from_worker(f"❌ Falha resolvendo '{h}': {ex}")
                                continue
                            if cid:
                                log_from_worker(
                                    f"✅ Resolvido '{h}' → {cid}\n"
                                    f"    Confira: https://www.youtube.com/channel/{cid}"
                                )
                                final_ids.append(cid)
                            else:
                                log_from_worker(f"⚠️ Não encontrei canal para '{h}'.")
                    if not final_ids:
                        log_from_worker("❌ Nenhum canal resolvido; abortando.")
                        return
                    out = run_monitor(final_ids, status_cb=log_from_worker)
                    if isinstance(out, dict):
                        if out.get("excel_path"):
                            log_from_worker(f"📁 Excel gerado: {out['excel_path']}")
                        log_from_worker(f"ℹ️ Run salvo: {out.get('run_id')}. Veja em 'Ver canais / vídeos'.")
                    elif out:
                        log_from_worker(f"📁 Arquivo gerado: {out}")
                except QuotaExceeded as e:
                    log_from_worker(f"[COTA] {e}")
                except Exception as e:
                    log_from_worker(f"❌ Erro: {e}")

            th = threading.Thread(target=target, daemon=True)
            runner_thread["th"] = th
            th.start()
            _poll_runner()

        ttk.Button(dlg, text="Analisar", command=_go).pack(pady=10)

    btn_save.config(command=save_cfg)
    btn_run.config(command=run_now)
    btn_monitor.config(command=run_monitor_ids)

    foot = ttk.Label(frm, text="Dica: defina YOUTUBE_API_KEYS no ambiente (separadas por vírgula) para rodízio automático de cotas.")
    foot.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

    root.mainloop()


def main():
    make_gui()


if __name__ == "__main__":
    main()
