# !projeto.md — yt-analise-canais

## Proposta
Ferramenta de **descoberta e análise de canais do YouTube** via **YouTube Data API v3**, com GUI Tkinter. Objetivo: achar **canais pequenos/médios com vídeos em crescimento rápido** (foco em VPD — views/dia) para inspirar ideias de nicho na criação de novos canais.

Principais capacidades:
- Busca vídeos por palavras-chave (pt/es/en) em janela de publicação configurável
- Analisa canais (idade, consistência de uploads, views, engajamento, uploads/semana, tendência VPD)
- Calcula **score composto 0–100** e armazena tudo em histórico interno (JSON)
- Janela visual "Ver canais / vídeos" com abas de **Canais**, **Vídeos**, **Runs**, **Monitorados**, **Analytics**
- **Monitoramento contínuo**: marca canais/vídeos, tira snapshots periódicos, detecta aceleração
- **Monitor diário automático** via Agendador do Windows (roda 1×/dia no login, só avisa se houver novidade)
- **Importação** de planilhas antigas (`.xlsx` do formato anterior)
- Export **Excel** sob demanda (Scored com 30 colunas + autofilter, ou RAW)
- **Build `.exe`** via `build.bat` (PyInstaller onefile) — o `.exe` reconhece a pasta `dados/` ao lado dele

## Estrutura

```
main.py                   # entrypoint (aceita --daily-check pra modo silencioso)
build.bat                 # empacota o app em dist → move o .exe para a raiz → limpa build/dist/spec
yt-analise-canais.exe     # (gerado) binário PyInstaller; reconhece dados/ ao lado de si via sys.frozen
app/
  __init__.py
  config.py               # DEFAULT_CONFIG, CFG, paths (sensível a sys.frozen), API_KEYS, QUOTA_USED (lista por key), helpers de quota
  utils.py                # log, QuotaExceeded, iso8601, datas tz-safe, safe_ratio, fmt_int, chunked
  tooltip.py              # Tooltip + help_badge usados pela GUI (balões "?" de ajuda)
  persistence.py          # canais_listados.csv, termos.json (load/save + seeds genéricas), execucoes.csv
  results_store.py        # runs/monitorados/snapshots JSON atômicos (central interna); purge_channel
  youtube_api.py          # yt_get (rotação/cota por key), search/hydrate/channels/playlistItems, trending, related, resolve_handle_to_channel_id
  terms.py                # _guess_lang, filter_terms_by_lang, mutate_terms, extract_learned_terms, language_ok
  scoring.py              # WEIGHT_*, channel_consistency_metrics (uploads/sem + vpd_trend), score_title, compute_score (VPD log-norm)
  excel_export.py         # write_excel (Scored — 30 colunas com autofilter), write_excel_raw
  engine.py               # run_engine (Scored) + _run_raw + run_monitor + update_monitored + export_run_to_excel + helpers
  analytics.py            # rankings, latest snapshots, niche_summary, overview
  import_xlsx.py          # importa planilhas .xlsx antigas do formato write_excel como runs salvos
  daily_monitor.py        # should_run_today, run_if_due, show_notification (popup Tk com 'Abrir programa' / 'OK')
  scheduler.py            # enable/disable via schtasks com fallback para pasta Startup do Windows
  results_window.py       # janela 'Ver canais/vídeos' (abas Canais/Vídeos/Runs/Monitorados/Analytics); tksheet com gradiente
  gui.py                  # make_gui, main, open_folder, diálogo Monitor IDs, checkboxes de modo e daily
dados/                    # estado persistente (nunca commitar com API keys)
versoes-exportadas/       # histórico/backup de builds; pedir confirmação antes de ler/alterar
__pycache__/              # cache Python gerado; não é fonte do projeto
```

> **Estado mutável global** (`CFG`, `API_KEYS`, `_current_key_idx`, `QUOTA_USED`, `CUSTOM_SEARCH_TERMS`) vive em [app/config.py](app/config.py). Sempre acessar via `from app import config; config.X` — **nunca** com `from app.config import API_KEYS` (isso faz cópia local e quebra a rotação de cota).

> **Paths sensíveis a runtime**: `DATA_DIR` detecta `sys.frozen` (PyInstaller). Rodando via `python main.py` usa `PROJECT_ROOT = .../yt-analise-canais/`. Rodando via `.exe` empacotado usa `PROJECT_ROOT = pasta_do_exe`. Garante que o `dados/` fique **ao lado do executável** e não numa pasta temporária.

## Central interna (runs + monitorados + snapshots)

O app é uma **central de descoberta de nichos**, não só gerador de Excel.

- **Runs salvos em `dados/resultados_buscas.json`** — cada execução (Scored/RAW/Monitor) salva todos os canais/vídeos + metadados. `run_engine`/`_run_raw`/`run_monitor` retornam `dict` com `{run_id, mode, channels_count, videos_count, excel_path}`.
- **Excel passou a ser opcional** — default `AUTO_EXPORT_EXCEL=False`. Exportação manual via janela "Ver canais/vídeos" → aba Runs → "Exportar run para Excel".
- **Canais/vídeos monitorados** em `dados/monitorados.json` com tags, notas, status. Adicionados pela janela de resultados (clique direito, botões ou diálogo "Adicionar monitorado" que aceita `@handle` e resolve via API).
- **Snapshots temporais** em `dados/snapshots_monitoramento.json`. `update_monitored()` (botão "Atualizar monitorados agora") coleta estado atual, calcula deltas vs snapshot anterior (Δ inscritos, Δ views, Δ VPD, velocidade de vídeos) e atribui `signal` ao canal: **Aquecendo / Estável / Saturado / Promissor**.
- **Gravação atômica**: `results_store._atomic_write_json` escreve em `.tmp` e substitui — evita corromper se o app fechar no meio.
- **Purge definitivo**: `results_store.purge_channel(channel_id)` remove canal e todos os vídeos dele de **runs, monitorados e snapshots**. Exposto na aba Canais (botão "Remover do histórico" + menu de clique direito).

## Três modos de operação

### 1) Modo Scored (default)
- Busca termos filtrados por idioma; ordenação configurável (`SEARCH_ORDER`: `relevance` default / `date` / `viewCount` / `rating`)
- Hidrata vídeos e aplica filtro composto: **`views ≥ BASE_MIN_VIEWS` OR `vpd ≥ BASE_MIN_VPD`** + duração + idioma
- Filtra canais por idade dentro de `[BASE_MIN_CHANNEL_AGE_DAYS, BASE_MAX_CHANNEL_AGE_DAYS]` (default 30–365)
- Amostra N uploads recentes por canal (`UPLOADS_SAMPLE`, default 6)
- Calcula consistência: mediana/média/desvio de views, % long, % acima de min_views, **uploads/semana**, **tendência VPD** (VPD do último upload ÷ mediana dos anteriores; >1 = acelerando)
- Score 0–100 ponderado: VPD 35% (log-normalizado com teto `VPD_SATURATION`), VPS 20%, engajamento 25%, consistência 10%, título 5%, novidade 5%
- Fallbacks configuráveis (A: relax, B: repetidos/mais antigos com teto, C: muito antigos sem teto, fail-safe)
- Persistência: sempre grava run em `resultados_buscas.json`; Excel só se `AUTO_EXPORT_EXCEL=True`

### 2) Modo RAW (`RAW_EXPORT_MODE=True`)
- Dump de vídeos crus ordenados por `views_per_day | views | date_desc | random`
- Mesmo filtro composto views-OR-vpd do Scored
- Limite configurável (`RAW_LIMIT`, default 250)
- Pode incluir Trending (`RAW_INCLUDE_TRENDING`) e Relacionados (`RAW_INCLUDE_RELATED`)
- `STRICT_WINDOW_IN_RAW` aplica janela de publicação rígida
- Persistência idem: run em JSON; Excel opcional

### 3) Modo Monitor (botão "Monitorar IDs")
- Usuário cola uma lista de `channel_id`, URLs `youtube.com/channel/UC...` **ou `@handle` / URL com `/@handle`** (resolvido automaticamente via API `search`, ~100 cota por handle)
- Pula totalmente busca/trending/related — só `channels` + `playlistItems` + `videos` dos canais informados
- Aplica filtro views-OR-vpd em cada vídeo amostrado
- Gera run salvo no `resultados_buscas.json` com `mode="monitor"`
- Uso típico: reavaliar periodicamente uma shortlist de canais suspeitos de estarem crescendo

## Monitoramento diário automático (opcional)

Checkbox **"Monitorar todo dia (no login do Windows)"** liga/desliga uma tarefa que, a cada login do Windows, roda `python main.py --daily-check` (ou `yt-analise-canais.exe --daily-check`).

Fluxo ([app/daily_monitor.py](app/daily_monitor.py)):
1. `should_run_today()` checa `dados/daily_state.json` (`last_run: YYYY-MM-DD`). Se já rodou hoje, sai silenciosamente.
2. Roda `update_monitored()` para coletar snapshot fresco.
3. Analisa novidades relevantes: canais com sinal `Aquecendo`/`Promissor`, `vpd_trend ≥ 1.20`, `delta_subscribers ≥ 100`, vídeos com `recent_velocity ≥ 500` views/dia.
4. **Só abre popup Tk se houver novidades.** Popup tem "Abrir programa" (abre GUI normal) e "OK" (fecha silenciosamente).
5. Marca o dia como rodado; próximos logins no mesmo dia não executam nada.

Agendamento ([app/scheduler.py](app/scheduler.py)):
- Primeira tentativa: `schtasks /create /sc onlogon /tn yt-analise-canais-daily`
- Se falhar (acesso negado, sem admin): fallback automático criando `.bat` em `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\yt-analise-canais-daily.bat`
- Desligar remove ambas as fontes
- Detecta `python.exe` vs `.exe` empacotado — usa `pythonw.exe` pra não abrir console preto

## Fluxo do engine Scored ([app/engine.py](app/engine.py): `run_engine`)
1. Reset de cota por key (`config.reset_quota()`)
2. Carrega termos: `config.CUSTOM_SEARCH_TERMS` (manuais da GUI, **usados literalmente sem `mutate_terms`**) OU `termos.json["base"] + learned` (passa por `mutate_terms`)
3. Filtra por idiomas ativos via `filter_terms_by_lang`
4. Trending (categorias embaralhadas; respeita `max_per_cat` por categoria) via `discover_trending`
5. Para cada termo → `search_videos` com `order=SEARCH_ORDER`; quota checada por key via `_find_key_with_budget` antes de cada chamada
6. `hydrate_videos` → API `videos` (statistics, contentDetails, snippet)
7. Aplica `_video_passes` (views OR vpd + duração) + `language_ok`
8. Related opcional (limitado; `relatedToVideoId` deprecado desde 2023 — pode voltar vazio)
9. `get_channels_info` → API `channels`
10. Aprovação por `_channel_age_ok` (respeita `min_age` e `max_age`)
11. Fallbacks A/B/C se não atingiu `MIN_CHANNELS_PER_SHEET`; fail-safe como última carta
12. **Dedup final por (channel_id, video_id)** antes do agrupamento
13. `get_playlist_recent_video_ids` + `channel_consistency_metrics` (uploads/sem, vpd_trend)
14. `compute_score` gera score final
15. `_finalize_scored_run`: serializa tudo em `resultados_buscas.json`; se `AUTO_EXPORT_EXCEL=True`, também chama `write_excel`
16. `extract_learned_terms_from_titles` — **só títulos em PT** (evita poluição multilíngue); atualiza `termos.json`
17. `log_run` grava execução em `execucoes.csv`

## Onde está cada coisa

| O que procurar | Arquivo |
|---|---|
| Defaults, paths (com sys.frozen), `PROJECT_ROOT`, `AUTO_EXPORT_EXCEL`, quota por key (`QUOTA_USED` lista, `quota_left_on_key`, `quota_total_budget`, `reset_quota`, `resize_quota_for_keys`) | [app/config.py](app/config.py) |
| Parser de duração, datas tz-safe (naive assumido UTC), `QuotaExceeded`, `chunked` | [app/utils.py](app/utils.py) |
| Tooltips da GUI (`Tooltip`, `help_badge`) | [app/tooltip.py](app/tooltip.py) |
| `canais_listados.csv`, `termos.json` (seeds genéricas), `execucoes.csv` | [app/persistence.py](app/persistence.py) |
| Runs/monitorados/snapshots JSON atômicos (`append_run`, `get_run`, `remove_run`, `add_monitored_*`, `purge_channel`, `snapshots_for_*`) | [app/results_store.py](app/results_store.py) |
| `yt_get` (quota por key), `search_videos` (com `order`), `hydrate_videos`, `get_channels_info`, `get_playlist_recent_video_ids`, `discover_trending`, `discover_related`, `resolve_handle_to_channel_id` | [app/youtube_api.py](app/youtube_api.py) |
| `_guess_lang`, `filter_terms_by_lang`, `mutate_terms`, `extract_learned_terms_from_titles`, `language_ok` | [app/terms.py](app/terms.py) |
| `WEIGHT_*`, `channel_consistency_metrics` (uploads/sem + vpd_trend), `score_title`, `compute_score` (VPD log-norm) | [app/scoring.py](app/scoring.py) |
| `write_excel` (Scored, 30 colunas, autofilter) e `write_excel_raw` | [app/excel_export.py](app/excel_export.py) |
| `run_engine`, `_run_raw`, `run_monitor`, `update_monitored`, `export_run_to_excel`, `_finalize_scored_run`, `_finalize_raw_run`, helpers `_video_passes`/`_channel_age_ok`/`_user_terms_cap` | [app/engine.py](app/engine.py) |
| Rankings, latest snapshots, niche_summary, overview | [app/analytics.py](app/analytics.py) |
| Import de `.xlsx` antigos → runs (`parse_xlsx`, `import_all_from`) | [app/import_xlsx.py](app/import_xlsx.py) |
| Daily check: `should_run_today`, `run_if_due`, `show_notification` | [app/daily_monitor.py](app/daily_monitor.py) |
| Agendador Windows: `enable`, `disable`, `is_enabled` (schtasks + Startup fallback) | [app/scheduler.py](app/scheduler.py) |
| Janela "Ver canais/vídeos" (tksheet com gradiente, sort tri-state, filtros, menus de contexto, diálogos) | [app/results_window.py](app/results_window.py) |
| GUI Tkinter principal, `make_gui`, `open_folder`, diálogo Monitor IDs, checkboxes Excel/Daily | [app/gui.py](app/gui.py) |

## Configuração (`dados/config.json`)

### Principais
- `API_KEYS`: lista — **rotação automática com cota por key** — armazenada em **plaintext**
- `QUOTA_BUDGET_PER_KEY`: default **8000** por key; total efetivo = `budget_per_key × len(API_KEYS)`
- `QUOTA_BUDGET`: legado — mantido para compat de chaves/docs mas não é mais o cap real
- `REGION_CODE`: `None` = global
- `SELECTED_LANGS`: default `["pt","es","en"]`
- `SEARCH_ORDER`: default `"relevance"` (relevance/date/viewCount/rating)
- `BASE_PUBLISHED_AFTER_DAYS`: janela de publicação (90)
- `BASE_MAX_CHANNEL_AGE_DAYS`: idade máx canal (**365**)
- `BASE_MIN_CHANNEL_AGE_DAYS`: idade mín canal (**30**)
- `BASE_MIN_DURATION_MIN`: duração mín (**8 min**)
- `BASE_MIN_VIEWS`: views mín por vídeo (**5000**)
- `BASE_MIN_VPD`: VPD mín alternativo (**300** — filtro é views OR vpd)
- `VPD_SATURATION`: teto de normalização log do VPD no score (default 50000)
- `SEARCH_TERMS_PER_RUN`: **0 = automático** (programa decide quantos termos cabem na cota); >0 = teto fixo
- `TRENDING_CATEGORIES`: `[27, 28, 25]` (Educação, Ciência&Tech, Notícias)
- `UPLOADS_SAMPLE`, `MIN_CHANNELS_PER_SHEET`, `RELATED_EXPLORE_LIMIT`, `SEARCH_PAGES_PER_TERM`, `REQUEST_PAUSE`

### Fallbacks Scored
- `ALLOW_REPEATED_AS_LAST_RESORT`: permitir canais já vistos (default `false`)
- `ALLOW_OLDER_AS_LAST_RESORT` + `OLDER_MAX_CHANNEL_AGE_DAYS` (default `true` + 365)
- `LAST_RESORT_MIN_VIEWS`: default 5000
- `FORCE_TOO_OLD_BEFORE_FAILSAFE` (default `true`)

### Excel
- `AUTO_EXPORT_EXCEL`: default **`false`**. Quando `true`, cada execução também gera `.xlsx`. Quando `false`, resultados ficam só em `resultados_buscas.json` e o usuário exporta sob demanda pela janela de resultados. Controlado pelo checkbox "Gerar Excel automático" na GUI.

### Fonte alternativa de keys
Env `YOUTUBE_API_KEYS` ou `YOUTUBE_API_KEY` sobrescreve o config ao carregar.

### Segurança
`dados/config.json` contém chaves reais em texto puro. Não commitar, anexar em issue ou enviar esse arquivo sem sanitizar.

## Quota por API key

[app/youtube_api.py](app/youtube_api.py) `yt_get`:
- `config.QUOTA_USED` é **lista paralela** a `API_KEYS`. Cada key tem seu próprio contador.
- Antes de chamar, `_find_key_with_budget(est)` procura qual key ainda tem cota local suficiente para o custo.
- Se encontra uma key com cota, usa. Se não, levanta `QuotaExceeded`.
- Se API retornar 403 quota_exceeded: marca aquela key como esgotada (`QUOTA_USED[idx] = budget`) e tenta a próxima.
- Mudança de `API_KEYS` pela GUI chama `config.resize_quota_for_keys()` automaticamente.

Vantagem sobre o modelo antigo: com 6 keys × 8000 = **48.000 unidades efetivas por dia** em vez de só 1000 globais. Permite rodadas com muitos mais termos.

## Persistência (`dados/`)

| Arquivo | Conteúdo |
|---|---|
| `config.json` | Configuração da GUI (plaintext, incluindo API keys) |
| `termos.json` | `{base: [...], learned: [...], last_updated}` |
| `canais_listados.csv` | Memória de canais já vistos (evita repetir em runs futuras) |
| `execucoes.csv` | Log de cada execução (data, new_channels, quota_used, terms_used) |
| `resultados_buscas.json` | **Central interna**: histórico completo de runs (canais + vídeos + params) |
| `monitorados.json` | Canais/vídeos marcados pelo usuário (tags, notas, status) |
| `snapshots_monitoramento.json` | Snapshots temporais dos monitorados com deltas e sinal |
| `daily_state.json` | Estado do monitor diário (`last_run`, `last_run_at`) |
| `relatorio_canais_*.xlsx` | Saída Scored/Monitor (só com `AUTO_EXPORT_EXCEL=True` ou export manual) |
| `videos_raw_*.xlsx` | Saída RAW (só com `AUTO_EXPORT_EXCEL=True` ou export manual) |

> ⚠️ Se existir um `dados/config.json` de versão anterior, os novos campos (`BASE_MIN_VPD`, `BASE_MIN_CHANNEL_AGE_DAYS`, `VPD_SATURATION`, `SEARCH_ORDER`, `QUOTA_BUDGET_PER_KEY`, `AUTO_EXPORT_EXCEL`) são mesclados em memória a partir de `DEFAULT_CONFIG`, mas só vão para o arquivo quando o usuário clica em "Salvar configurações". Pra reset total, apagar o arquivo.

## Score composto (pesos)
```python
WEIGHT_VPD   = 0.35   # views/dia — log-normalizado: log1p(vpd) / log1p(VPD_SATURATION)
WEIGHT_VPS   = 0.20   # views/inscrito
WEIGHT_ENG   = 0.25   # 0.7*like_rate + 0.3*comment_rate
WEIGHT_CONS  = 0.10   # consistência (mediana views / min_views)
WEIGHT_TITLE = 0.05   # score_title (tamanho + caps ratio)
WEIGHT_NOVO  = 0.05   # novelty por idade do canal (≤30d=1.0, ≤60d=0.6, ≤90d=0.3)
```

## Métricas extras no Excel Scored

A planilha tem 30 colunas com `autofilter`. Além do score e métricas tradicionais, inclui:
- **Uploads/sem** — frequência de postagem nos uploads amostrados
- **Tendência VPD** — VPD do vídeo mais recente ÷ mediana dos anteriores (>1.0 = acelerando, <1.0 = desacelerando)

## Dependências

Runtime (requeridas):
- `requests` — cliente HTTP
- `python-dateutil` — `isoparse` para datas YouTube
- `xlsxwriter` — export Excel
- `openpyxl` — leitura de `.xlsx` antigos (via `Importar planilhas antigas`)
- `tksheet` — tabelas com cores por célula na janela de resultados
- `tkinter` (stdlib)

Opcional:
- `ttkbootstrap` — tema dark da GUI principal (se não estiver, cai pra `tk.Tk()` normal)

Não há `requirements.txt` nem `pyproject.toml`. Install manual: `pip install requests python-dateutil xlsxwriter openpyxl tksheet ttkbootstrap`.

## Build (`build.bat`)

Script na raiz que empacota o app em `.exe` via PyInstaller e deixa limpinho:

1. Apaga `build/`, `dist/` e `.spec` anteriores
2. Verifica/instala PyInstaller
3. Empacota com `--onefile --windowed --name yt-analise-canais --collect-submodules app` + hidden imports (`ttkbootstrap`, `xlsxwriter`, `dateutil.parser`)
4. **Move** `dist\yt-analise-canais.exe` → raiz (`yt-analise-canais.exe`)
5. Apaga `build/`, `dist/` e o `.spec`

O `.exe` resultante usa `dados/` **ao lado dele** (ancorado em `sys.executable.parent` quando `sys.frozen` é True). Aceita `--daily-check` pra modo silencioso (idêntico ao `python main.py --daily-check`).

## GUI principal (Tkinter + ttkbootstrap)

Geometria inicial **1100×860**. Layout em grid 3 colunas × 5 linhas.

**Col 0 — Idiomas & RAW:** checkboxes pt/es/en; Modo Dump; Limite RAW; Ordenar por RAW; Incluir Trending/Relacionados; Aplicar janela rigidamente; **Gerar Excel automático**; **Monitorar todo dia (no login do Windows)**. Cada opção tem tooltip `?`.

**Col 1 — Parâmetros:**
- Janela publicados (dias)
- Views mín. por vídeo
- VPD mín. (views/dia)
- Duração mín. (min)
- Idade mín. do canal (dias)
- Idade máx. do canal (dias)
- Uploads amostrados
- Mín. canais por planilha
- Ordenação da busca (dropdown)
- VPD saturation (score)
- Páginas por termo
- Termos por execução (0 = automático)
- **Cota por API key**

**Col 2 — API Keys** (uma por linha).

**Row 1 — Fallbacks** (só Scored).

**Row 2 — Botões:** Executar agora / Monitorar IDs / Ver canais / vídeos / Abrir pasta de dados / Salvar configurações.

**Row 3 — Termos de busca manuais** (textarea larga, abaixo dos botões).

**Log** na coluna 2 (empilhado abaixo do API Keys, `rowspan=3`) com drain thread-safe via `queue.Queue` + `root.after(120, _drain_log)`. Qualquer `http://` / `https://` no texto é renderizado como **link clicável** (cor azul, cursor de mão) via tags do `Text` — clique abre no navegador padrão.

**Diálogo "Monitorar IDs"**: textarea aceita channel_ids, URLs `/channel/UC...`, e `@handle` / URLs `/@handle` (resolvido via API, ~100 cota por handle). **Após a análise, os canais são adicionados automaticamente à lista de monitorados** (`results_store.add_monitored_channel(..., source="monitor_ids")`).

## Janela "Ver canais / vídeos" ([app/results_window.py](app/results_window.py))

Abre pelo botão principal. Geometria 1420×780.

**Filtros globais no topo**: busca, modo (Todos/scored/raw/monitor), Monitorados (Todos/apenas/não), Score mín., VPD mín., Views mín., botão "Recarregar / aplicar filtros".

**Abas:**

### Canais (tksheet com gradientes)
Colunas: Mon, Score, Canal, Idade (calculada **dinamicamente** a partir de `created_at` — sobe sozinha dia a dia), Inscritos, Views canal, Views/vídeo, Uploads/sem, Tendência VPD, Melhor vídeo, VPD melhor, Última análise.

Cores por célula (`tksheet`):
- Score, Uploads/sem, Tendência VPD, VPD melhor: alto = verde
- Idade: **baixo = verde** (mais novo melhor)
- Inscritos, Views canal, Views/vídeo: alto = verde, escala log

Sort tri-state clicando no header: asc ▲ → desc ▼ → off (restaura).

Botões / clique direito: Monitorar canal, Remover monitor, Abrir canal, Copiar URL, **Remover do histórico** (`purge_channel` — apaga canal + vídeos de runs, monitorados, snapshots).

### Vídeos (tksheet com gradientes)
Colunas: Mon, VPD, Views, Publicado, Duração (Min), Canal, Título, Likes, Coment., Run.

Cores:
- VPD, Views, Likes, Coment.: alto = verde, log
- **Duração (Min)**: modo "sweet spot" — **60–120 min = verde cheio**, degradê ±30 min, vermelho fora

Sort tri-state idem.

### Runs (Treeview)
Colunas: Data, Modo, Canais, Vídeos, Cota, Termos, Excel.

Botões: **Exportar run para Excel** (chama `export_run_to_excel`; reconstrói `blocks` a partir do JSON e chama `write_excel`), **Remover run** (confirma), **Importar planilhas antigas** (lê todos `relatorio_canais_*.xlsx` em `dados/`, cria runs via `import_xlsx.import_all_from`, idempotente).

### Monitorados (Treeview)
Colunas: Tipo (canal/vídeo), Título, ID, Tags, Notas, Adicionado, Sinal (Aquecendo/Estável/Saturado/Promissor).

Botões: **Adicionar monitorado** (diálogo aceita URL/ID/@handle — resolve em background), **Atualizar monitorados agora** (`update_monitored`), Remover, Editar tags, Editar notas.

### Analytics (Treeview)
Sub-abas: Top canais (por VPD médio), Vídeos acelerados (por `recent_velocity`), Nichos/tags (`niche_summary`). Topo com overview resumo.

## Thread-safety
- Worker roda em `threading.Thread(daemon=True)` em [app/gui.py](app/gui.py)
- Logs passam por `log_queue.put()` do worker e são drenados na main thread via `root.after(120, _drain_log)`
- `_poll_runner` observa término da thread e reabilita botões (Executar + Monitorar)

## Versionamento

Repositório **privado** no GitHub: `https://github.com/rafaelkolaias-lang/yt-analise-canais` (branch `main`, tag inicial `v0.1.0`).

`.gitignore` na raiz protege: `dados/` (contém API keys), `versoes-exportadas/`, `*.exe`, `__pycache__/`, `build/`, `dist/`, `*.spec`, `.env`, `.vscode/`, `.idea/`. Também ignora arquivos internos de agentes (`\!executar.md`, `CLAUDE.md`, `AGENTS.md`, `RULES.md`, `temporary_rules.md`, `agents/`) — mas `!projeto.md` vai para o repo.

## Armadilhas / atenção
- **Quota-intensivo**: cada `search` custa 100 unidades. O app distribui entre múltiplas keys (`QUOTA_BUDGET_PER_KEY × N`), mas ainda assim runs com muitos termos × muitos idiomas gastam rápido. `planned_terms_for_budget` reserva 20% da cota para endpoints baratos.
- `discover_related` usa `relatedToVideoId`, **deprecado pelo YouTube em 2023** — retorna `[]` silenciosamente na maioria dos casos.
- `STRICT_LANGUAGE` + `SELECTED_LANGS` filtram por `defaultLanguage`/`defaultAudioLanguage` do snippet — muitos vídeos vêm sem esses campos (por isso o default é não-estrito).
- `extract_learned_terms_from_titles` aprende **bigramas em PT** com stopwords PT. A versão atual filtra os títulos por `_guess_lang == "pt"` antes de extrair, evitando poluição quando o run traz canais EN/ES.
- Seeds em [app/persistence.py](app/persistence.py) `_SEED_TERMS` são **genéricas** (tutorial/review/how to/curso/dica em pt/en/es). Se você tem nicho específico, use a textarea de termos manuais (aplicada literalmente, sem mutação).
- `output_xlsx_path` inclui segundos no nome — improvável sobrescrever, mas pode acumular arquivos; com `AUTO_EXPORT_EXCEL=False` isso não acontece.
- Trocar `SEARCH_ORDER` muda radicalmente o perfil dos resultados: `date` favorece descoberta recente, `viewCount` favorece canais grandes, `relevance` mistura.
- Estado global em `config` precisa sempre ser acessado via `from app import config; config.X`. Importar com `from app.config import API_KEYS` faz cópia local e perde mutações feitas pela GUI (ex: salvar keys novas).
- **Datas sem timezone**: XLSX antigos armazenavam publicações como string `"2025-10-30"`. `app/utils.py` agora trata datas naive como UTC (`_as_aware_utc`), evitando `TypeError` em subtração mixed tz.
- **Import legado**: `.xlsx` antigos nem sempre têm todas as colunas que o modelo atual gera (likes/comments dos vídeos, uploads/sem, tendência VPD). Campos ausentes viram `None` → reexportação mostra como 0. Pra recuperar métricas, rode "Monitorar IDs" nos channel_ids importados.
- **Handle `@...`**: o YouTube não permite consulta direta. Quando aparece, o app faz `search?q=@handle&type=channel` gastando 100 cota por handle. Após resolvido, só usa o `UC...`.
