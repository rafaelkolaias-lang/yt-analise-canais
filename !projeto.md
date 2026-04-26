# !projeto.md — youtube-analyzer

> Sistema web para descoberta, monitoramento e analytics de canais do YouTube, com foco em identificar **nichos dark em aceleração** e oportunidades de réplica. Sucessor em arquitetura web do app desktop Tkinter antigo (agora removido — toda a funcionalidade relevante foi portada para o stack web).

> **Status (2026-04-26):**
> - **Fases 0–8** (fundação → deploy EasyPanel) — ✅ concluídas em 2026-04-24
> - **Pós-MVP entregue 2026-04-25/26** (em produção):
>   - Analytics paginado (eliminou fan-out de 5N requests)
>   - Ações em massa em /monitoramento (canais e vídeos)
>   - Responsividade real Plano A + B (drawer mobile, cards stackados ≤768px)
>   - Bulk progress bar (snapshot itemizado, concorrência 4)
>   - Notificações do navegador no fim de sync
>   - Descoberta automática pós-sync (orçamento + termos derivados)
>   - Blacklist de canais removidos
>   - Revisão persistente por item (`reviewed_at`) em /runs > Descoberta
>   - Sugestões automáticas em /monitoramento > Sugestões (canais novos
>     com VPD alto + canais "mortos" pra pausar/remover)
>
> Sistema operacional 24/7 com YouTube API key configurada e descoberta
> automática rodando após cada sync.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | Next.js 15 (App Router), React 19, TypeScript 5.7, CSS vanilla, Recharts 2.15 (uso na Fase 6) |
| Backend | FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), PyMySQL, Pydantic v2, APScheduler 3.11 |
| Banco | MySQL 8 no EasyPanel (prod) / MariaDB 10.4 no XAMPP local (dev) |
| Migrações | Alembic (autogen) |
| Cripto | `cryptography.fernet` — chave mestra via `APP_SECRET_KEY` (derivação SHA-256) |
| HTTP externo | httpx (YouTube Data API v3) |

---

## Estrutura de pastas

```
yt-analise-canais-web/
├── api/                              # Backend FastAPI
│   ├── app/
│   │   ├── main.py                   # FastAPI + lifespan (scheduler) + CORS + routers
│   │   ├── seed.py                   # seed idempotente de 24 app_settings
│   │   ├── core/
│   │   │   ├── config.py             # Settings (pydantic-settings, lê .env)
│   │   │   ├── database.py           # engine, SessionLocal, Base, get_db()
│   │   │   ├── crypto.py             # Fernet encrypt/decrypt/mask para secrets no banco
│   │   │   └── scheduler.py          # APScheduler: start/shutdown/reschedule/next_run_time
│   │   ├── routers/
│   │   │   ├── health.py             # / | /health | /health/db
│   │   │   ├── settings.py           # /api/settings  (GET list, GET :key, PUT :key)
│   │   │   ├── discovery.py          # /api/discovery/{defaults,search,runs,runs/:id,runs/:id/.../review,blacklist}
│   │   │   ├── monitoring.py         # /api/monitoring/{channels,videos} + snapshot/patch/delete/best-videos + bulk-status/bulk-snapshot/bulk-delete
│   │   │   ├── sync.py               # /api/sync/{status,run,runs}
│   │   │   ├── suggestions.py        # /api/suggestions/{to-monitor,to-remove}
│   │   │   └── analytics.py          # /api/analytics/{overview,channels(paginado),channels/:id/{timeseries,summary},niches}
│   │   ├── services/
│   │   │   ├── settings_service.py   # público: sempre mascara secrets
│   │   │   ├── settings_reader.py    # interno: get_int/get_float/get_str/get_csv com cast
│   │   │   ├── youtube_client.py     # httpx + rotação de keys + quota tracking
│   │   │   ├── discovery_service.py  # search → hydrate → filter → persist; filtra blacklist
│   │   │   ├── discovery_seed_terms.py # ~95 termos seed (pt+en) pra auto-discovery
│   │   │   ├── auto_discovery_service.py # roda após sync; orçamento + termos derivados
│   │   │   ├── monitoring_service.py # add/snapshot/toggle/delete (+ blacklist no delete) + best videos + signal/analytics enrichment
│   │   │   ├── sync_service.py       # run_sync: itera ativos, tolera falha individual; engata auto_discovery no fim
│   │   │   ├── suggestions_service.py # recomendações: monitorar canais novos + pausar/remover canais mortos
│   │   │   └── analytics_service.py  # overview, timeseries, summary, niches (só lê banco)
│   │   ├── schemas/
│   │   │   ├── settings.py           # AppSettingRead / AppSettingUpdate
│   │   │   ├── discovery.py          # SearchRequest, DefaultFiltersRead, ResultChannel/Video, DiscoveryRunRead
│   │   │   ├── monitoring.py         # AddChannel/VideoRequest, ChannelRead, TrackedVideoRead, ChannelWithStats, BulkIdsRequest, BulkStatusRequest, BulkOperationResponse
│   │   │   ├── sync.py               # SyncRunRead, SyncStatusRead
│   │   │   ├── suggestions.py        # MonitorSuggestion, DeadChannelSuggestion
│   │   │   └── analytics.py          # AnalyticsOverview, TimeseriesPoint, ChannelAnalyticsSummary, NicheRow, ChannelBasic, ChannelAnalyticsBundle, PaginatedChannelAnalytics
│   │   └── models/
│   │       ├── __init__.py           # re-exporta todas as entidades
│   │       └── domain.py             # 12 entidades SQLAlchemy (ver "Modelo de dados")
│   ├── migrations/
│   │   ├── env.py                    # injeta DATABASE_URL do .env
│   │   └── versions/
│   │       ├── d69d8c5c7a0e_initial_schema.py        # schema inicial (11 tabelas)
│   │       ├── 59b9687df885_add_thumbnail_urls.py    # +thumbnail_url em channels e tracked_videos
│   │       ├── 56a880b51364_add_blacklist_and_review_state.py  # +channel_blacklist, reviewed_at em discovery_results_*
│   │       └── d6df02f56387_add_channel_published_at.py  # +channel_published_at em discovery_results_channels
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── Dockerfile                    # Python 3.11-slim + uvicorn (porta 8000)
│   ├── .dockerignore                 # exclui .venv, __pycache__, .env, git
│   ├── .env.example
│   ├── .env                          # ← gitignorado (senha real)
│   └── .venv/                        # ← gitignorado
│
├── web/                              # Frontend Next.js
│   ├── app/
│   │   ├── layout.tsx                # shell com sidebar
│   │   ├── page.tsx                  # Dashboard (healthchecks + contadores + painel sync)
│   │   ├── DashboardSyncPanel.tsx    # client: "Verificar agora" + próximo/último sync
│   │   ├── globals.css               # dark theme + componentes (botões, inputs, tabelas, tabs, forms)
│   │   ├── descoberta/
│   │   │   ├── page.tsx              # server: carrega defaults
│   │   │   └── DescobertaForm.tsx    # client: form + busca + tabelas + ações Monitorar
│   │   ├── monitoramento/
│   │   │   ├── page.tsx              # server: carrega channels + videos
│   │   │   └── MonitoramentoView.tsx # client: 4 abas (Canais, Vídeos, Melhores, Sugestões); BulkProgressBar inline; cards mobile (Plano B)
│   │   ├── runs/
│   │   │   ├── page.tsx              # server: carrega sync_runs + discovery_runs
│   │   │   └── RunsView.tsx          # client: 2 abas (Sync, Descoberta)
│   │   ├── configuracoes/
│   │   │   ├── page.tsx              # server: carrega settings
│   │   │   └── ConfiguracoesForm.tsx # client: agrupa por prefixo, salva inline
│   │   └── analytics/
│   │       ├── page.tsx              # server: carrega só niches (overview vai pelo client p/ respeitar filtro de status)
│   │       └── AnalyticsView.tsx     # client: filtro de status (Ativos/Pausados/Removidos/Todos) + 4 cards overview + cartões por canal + nichos
│   ├── components/
│   │   ├── Sidebar.tsx                # navegação 6 itens; vira drawer + hambúrguer em ≤768px
│   │   ├── SettingInput.tsx           # input/textarea com botão Salvar (dirty-aware) OU toggle switch quando valueType==='bool' (auto-save no clique)
│   │   ├── SecretInput.tsx            # input password com máscara + Alterar/Remover (suporta multiline)
│   │   ├── ChannelChart.tsx           # Recharts wrapper (LineChart/BarChart + tooltip pt-BR)
│   │   ├── ChannelAvatar.tsx          # avatar circular com fallback (inicial do título)
│   │   ├── VideoThumbnail.tsx         # thumb 16:9 com fallback "sem thumb"
│   │   ├── AddByLinkInput.tsx         # input pra colar link/ID e adicionar canal/vídeo
│   │   ├── ChannelsFilterBar.tsx      # filtros+ordenação da aba Canais (client-side); showSortDropdown em mobile
│   │   ├── VideosFilterBar.tsx        # filtros+ordenação da aba Vídeos (dropdown na grade ou em mobile)
│   │   ├── SortableHeader.tsx         # <th> clicável com cicle desc/asc/default
│   │   ├── Toaster.tsx                # Context + hook useToast (success/error/info)
│   │   ├── GlobalSyncIndicator.tsx    # badge no topo que polla /api/sync/status a cada 5s; dispara Notification ao detectar fim de sync
│   │   ├── Skeleton.tsx               # bloco animado (shimmer) para estados de loading
│   │   ├── ErrorCard.tsx              # cartão de erro padronizado com botão "Tentar de novo"
│   │   └── NotificationsSettings.tsx  # toggle de notificações do navegador (configurações)
│   ├── lib/
│   │   ├── api.ts                    # apiGet/Post/Patch/Delete + todos os tipos
│   │   ├── useIsMobile.ts            # hook matchMedia ≤768px (SSR-safe)
│   │   └── useBrowserNotifications.ts # hook Notification API + preferência local
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts                # output: "standalone" (pro Dockerfile)
│   ├── Dockerfile                    # multi-stage Node 20-alpine (deps/builder/runner)
│   ├── .dockerignore                 # exclui node_modules, .next, .env, git
│   ├── .env.example
│   ├── .env.local                    # ← gitignorado
│   └── node_modules/                 # ← gitignorado
│
├── docs/
├── scripts/                          # ferramentas one-shot (rodam manualmente)
│   ├── import_legacy.py              # importa canais + api keys do projeto desktop antigo
│   └── backfill_thumbnails.py        # popula thumbs em lote (1 unit por 50 canais/vídeos)
├── README.md                         # dev local + deploy EasyPanel + manutenção
├── !executar.md                      # tarefas pendentes (livre quando concluídas — git log é a verdade)
├── !projeto.md                       # este arquivo
├── start-dev.bat                     # 1-clique: abre 2 terminais com API e Web em dev
├── CLAUDE.md / AGENTS.md             # regras de IA
├── temporary_rules.md                # regras temporárias do projeto (gitignorado)
├── SECRETS.local.md                  # senhas e chaves locais (gitignorado)
└── .gitignore                        # cobre **/.env, .venv, node_modules, .next, dumps
```

---

## Quando ler cada arquivo

| Precisa mexer em | Leia |
|---|---|
| **Backend** | |
| Config/env | [api/app/core/config.py](api/app/core/config.py), [api/.env.example](api/.env.example) |
| Conexão SQLAlchemy, sessão | [api/app/core/database.py](api/app/core/database.py) |
| Cifrar/decifrar secrets | [api/app/core/crypto.py](api/app/core/crypto.py) |
| Scheduler (APScheduler) | [api/app/core/scheduler.py](api/app/core/scheduler.py) |
| Bootstrap FastAPI, CORS, lifespan | [api/app/main.py](api/app/main.py) |
| Healthchecks | [api/app/routers/health.py](api/app/routers/health.py) |
| Schema do banco (models) | [api/app/models/domain.py](api/app/models/domain.py) |
| Migrações | [api/migrations/env.py](api/migrations/env.py), [api/alembic.ini](api/alembic.ini) |
| Settings default / seed | [api/app/seed.py](api/app/seed.py) |
| API /settings (público, mascara) | [api/app/services/settings_service.py](api/app/services/settings_service.py), [api/app/routers/settings.py](api/app/routers/settings.py) |
| Leitura interna de settings (cast) | [api/app/services/settings_reader.py](api/app/services/settings_reader.py) |
| Cliente YouTube + rotação | [api/app/services/youtube_client.py](api/app/services/youtube_client.py) |
| Regras de descoberta (manual) | [api/app/services/discovery_service.py](api/app/services/discovery_service.py), [api/app/routers/discovery.py](api/app/routers/discovery.py) |
| Descoberta automática (orçamento + termos derivados) | [api/app/services/auto_discovery_service.py](api/app/services/auto_discovery_service.py), [api/app/services/discovery_seed_terms.py](api/app/services/discovery_seed_terms.py) |
| Blacklist de canais (delete + filtro) | [api/app/services/monitoring_service.py](api/app/services/monitoring_service.py) (`delete_channel`), [api/app/services/discovery_service.py](api/app/services/discovery_service.py) (`get_blacklisted_channel_ids`) |
| Sugestões de monitoramento (recomendar/remover) | [api/app/services/suggestions_service.py](api/app/services/suggestions_service.py), [api/app/routers/suggestions.py](api/app/routers/suggestions.py) |
| Regras de monitoramento/snapshots | [api/app/services/monitoring_service.py](api/app/services/monitoring_service.py), [api/app/routers/monitoring.py](api/app/routers/monitoring.py) |
| Regras de sync (scheduler + manual) | [api/app/services/sync_service.py](api/app/services/sync_service.py), [api/app/routers/sync.py](api/app/routers/sync.py) |
| Regras de analytics (agregação snapshots) | [api/app/services/analytics_service.py](api/app/services/analytics_service.py), [api/app/routers/analytics.py](api/app/routers/analytics.py) |
| **Frontend** | |
| Cliente HTTP + tipos | [web/lib/api.ts](web/lib/api.ts) |
| Hook `useIsMobile` (matchMedia) | [web/lib/useIsMobile.ts](web/lib/useIsMobile.ts) |
| Hook `useBrowserNotifications` (Notification API + permission) | [web/lib/useBrowserNotifications.ts](web/lib/useBrowserNotifications.ts) |
| Layout/navegação (drawer mobile) | [web/app/layout.tsx](web/app/layout.tsx), [web/components/Sidebar.tsx](web/components/Sidebar.tsx) |
| Estilo global | [web/app/globals.css](web/app/globals.css) |
| Dashboard | [web/app/page.tsx](web/app/page.tsx), [web/app/DashboardSyncPanel.tsx](web/app/DashboardSyncPanel.tsx) |
| Tela de Descoberta | [web/app/descoberta/DescobertaForm.tsx](web/app/descoberta/DescobertaForm.tsx) |
| Tela de Monitoramento | [web/app/monitoramento/MonitoramentoView.tsx](web/app/monitoramento/MonitoramentoView.tsx) |
| Tela de Runs | [web/app/runs/RunsView.tsx](web/app/runs/RunsView.tsx) |
| Tela de Configurações | [web/app/configuracoes/ConfiguracoesForm.tsx](web/app/configuracoes/ConfiguracoesForm.tsx) |
| Tela de Analytics | [web/app/analytics/AnalyticsView.tsx](web/app/analytics/AnalyticsView.tsx), [web/components/ChannelChart.tsx](web/components/ChannelChart.tsx) |
| Input seguro (API keys) | [web/components/SecretInput.tsx](web/components/SecretInput.tsx) |
| Feedback global (toast, sync, loading, erro) | [web/components/Toaster.tsx](web/components/Toaster.tsx), [web/components/GlobalSyncIndicator.tsx](web/components/GlobalSyncIndicator.tsx), [web/components/Skeleton.tsx](web/components/Skeleton.tsx), [web/components/ErrorCard.tsx](web/components/ErrorCard.tsx) |
| Avatar / thumbnail (UI) | [web/components/ChannelAvatar.tsx](web/components/ChannelAvatar.tsx), [web/components/VideoThumbnail.tsx](web/components/VideoThumbnail.tsx) |
| Adicionar canal/vídeo via link | [web/components/AddByLinkInput.tsx](web/components/AddByLinkInput.tsx) (frontend), [api/app/services/monitoring_service.py](api/app/services/monitoring_service.py) (`resolve_youtube_input`), [api/app/routers/monitoring.py](api/app/routers/monitoring.py) (`POST /api/monitoring/resolve`) |
| Filtros e ordenação (Monitoramento) | [web/components/ChannelsFilterBar.tsx](web/components/ChannelsFilterBar.tsx), [web/components/VideosFilterBar.tsx](web/components/VideosFilterBar.tsx), [web/components/SortableHeader.tsx](web/components/SortableHeader.tsx) |
| Scripts one-shot | [scripts/import_legacy.py](scripts/import_legacy.py), [scripts/backfill_thumbnails.py](scripts/backfill_thumbnails.py) |

---

## Modelo de dados (MySQL — 12 tabelas + `alembic_version`)

| Tabela | Papel |
|---|---|
| `channels` | Canais conhecidos/monitorados (youtube_channel_id único, `status`=`active\|paused\|removed`, `is_active`, `source`, `thumbnail_url`) |
| `channel_snapshots` | Histórico de inscritos, views totais, `avg_vpd_recent`, deltas, `vpd_trend`, `uploads_per_week`, **`signal`** (`heating\|promising\|saturated\|stable`) + `signal_reason`. Índice `(channel_id, captured_at)` |
| `tracked_videos` | Vídeos acompanhados por canal (unique `(channel_id, youtube_video_id)`), `tracking_source` (`discovery`\|`best_from_channel`), `first_tracked_vpd`, `last_seen_*`, `thumbnail_url` |
| `video_snapshots` | Histórico de views/likes/comments/VPD/deltas por vídeo. Índice `(tracked_video_id, captured_at)` |
| `sync_runs` | Execuções de sincronização (`type`=`manual\|scheduled`, `status`=`running\|success\|partial\|failed`, contadores, notes com erros individuais) |
| `discovery_runs` | Buscas por termos (`filters_json`, contadores) |
| `discovery_results_channels` | Canais encontrados numa discovery_run (score, matched_term, `reviewed_at`, `channel_published_at`) |
| `discovery_results_videos` | Vídeos encontrados numa discovery_run (views, VPD, score, `reviewed_at`) |
| `tags` | Tags/nichos (name unique) — **usado na Fase 6** |
| `channel_tags` | N:N canal↔tag |
| `app_settings` | Config global chave/valor tipada; `is_secret=True` → `value` cifrado com Fernet |
| `channel_blacklist` | Canais que o usuário removeu (`youtube_channel_id` UNIQUE). Discovery filtra antes de hidratar — nunca reaceita |

> Total: **12 tabelas** (+ `alembic_version`). Migrations posteriores ao schema inicial:
> - `59b9687df885` — `thumbnail_url` em `channels` e `tracked_videos`
> - `56a880b51364` — tabela `channel_blacklist` + `reviewed_at` em ambos `discovery_results_*` (descoberta contínua, 2026-04-25)
> - `d6df02f56387` — `channel_published_at` em `discovery_results_channels` (sugestões de monitoramento, 2026-04-26)

**Convenções:**
- Contagens (inscritos, views) em `BIGINT` — canais grandes ultrapassam 2B.
- Métricas calculadas (VPD, deltas, trends) em `FLOAT`.
- Timestamps em UTC via `server_default=func.now()`.
- FKs com `ondelete="CASCADE"` + relationships com `cascade="all, delete-orphan"`.

### Configurações iniciais (seed em `app_settings`)

Carregadas via `python -m app.seed` (idempotente):

- **Sync**: `sync_interval_hours=12`
- **search.***: `window_days=14`, `min_views=5000`, `min_vpd=500`, `min_duration_seconds=60`, `languages=pt,en,es`, `pages_per_term=2`
- **channel.***: `min_age_days=30`, `max_age_days=3650`, `vpd_saturation=100000`
- **monitor.best_videos_sample_size**: `10` (últimos N uploads analisados pra detectar melhor VPD)
- **analytics.promising_max_subscribers**: `50000` (teto de inscritos para canal ser elegível a "promissor"/dark)
- **analytics.promising_vpd_ratio**: `0.3` (multiplicador de `vpd_saturation` — VPD mínimo pra canal pequeno ser "promissor")
- **youtube.api_keys**: secret (vazio, preenchido pela UI /configuracoes)
- **youtube.api_key_daily_quota**: `10000`
- **discovery.auto_enabled**: `true` (liga descoberta pós-sync)
- **discovery.auto_quota_pct**: `0.5` (fração da quota total disponível por ciclo)
- **discovery.auto_keywords**: ~95 termos seed pt+en (multiline, editável na UI)
- **discovery.auto_max_terms_per_run**: `30`
- **discovery.auto_derived_term_min_freq**: `3`
- **suggestions.monitor_min_vpd**: `10000` (VPD mínimo p/ recomendar canal)
- **suggestions.monitor_max_age_days**: `60` (idade máxima do canal p/ recomendar)
- **suggestions.dead_min_days_no_uploads**: `60` (sem uploads há ≥N dias)
- **suggestions.dead_max_vpd**: `2000` (VPD ≤ X — regras valem em conjunto)

---

## API REST

| Método | Path | Descrição |
|---|---|---|
| GET | `/` | Metadados do app |
| GET | `/health` | Status da API |
| GET | `/health/db` | Status da conexão com MySQL |
| GET | `/api/settings` | Lista todas as settings (secrets mascarados) |
| GET | `/api/settings/{key}` | Lê uma setting |
| PUT | `/api/settings/{key}` | Atualiza valor (cifra se `is_secret=True`; vazio limpa; reschedule dinâmico se for `sync_interval_hours`) |
| GET | `/api/discovery/defaults` | Defaults das `search.*` settings pra popular o form |
| POST | `/api/discovery/search` | Executa busca YouTube, persiste run + resultados |
| GET | `/api/discovery/runs?limit=` | Histórico de buscas — agora inclui `progress {channels_total/reviewed, videos_total/reviewed}` por run |
| GET | `/api/discovery/runs/{id}` | Run com resultados aninhados + `progress` + `reviewed_at` por item |
| PATCH | `/api/discovery/runs/{run_id}/channels/{result_id}/review` | Marca/desmarca canal como revisado (`{reviewed: bool}`) |
| PATCH | `/api/discovery/runs/{run_id}/videos/{result_id}/review` | Idem para vídeo |
| GET | `/api/discovery/blacklist` | Lista canais blacklistados (cada `delete_channel` adiciona) |
| DELETE | `/api/discovery/blacklist/{youtube_channel_id}` | Remove da blacklist (permite re-monitorar) |
| GET | `/api/suggestions/to-monitor` | Canais descobertos (não monitorados, fora da blacklist) que batem `suggestions.monitor_*` (VPD alto + idade baixa). Ordenado por VPD desc |
| GET | `/api/suggestions/to-remove` | Canais monitorados que batem regra de "morto" (`suggestions.dead_*`): sem uploads recentes E VPD baixo E sinal estagnado |
| GET | `/api/monitoring/channels` | Canais + último snapshot (subs, views, deltas, last_sync) |
| POST | `/api/monitoring/channels` | Adiciona canal por `youtube_channel_id` (idempotente) |
| PATCH | `/api/monitoring/channels/{id}` | Altera `status` (`active`/`paused`/`removed`) |
| DELETE | `/api/monitoring/channels/{id}` | Remove canal + cascata (snapshots, vídeos, tags) |
| POST | `/api/monitoring/channels/{id}/snapshot` | Snapshot imediato + detecta melhor upload recente (~3 units) |
| PATCH | `/api/monitoring/channels/bulk-status` | Status em lote (`{ids, status}`) — resposta `BulkOperationResponse` |
| POST | `/api/monitoring/channels/bulk-snapshot` | Snapshot em lote (`{ids}`) |
| POST | `/api/monitoring/channels/bulk-delete` | Remoção em lote (`{ids}`, POST e não DELETE pra ter body) |
| GET | `/api/monitoring/channels/{id}/best-videos` | Lista acumulativa de melhores vídeos detectados |
| GET | `/api/monitoring/videos` | Lista vídeos monitorados com `last_seen_*` |
| POST | `/api/monitoring/videos` | Adiciona vídeo por `youtube_video_id` (cria canal dono se preciso) |
| POST | `/api/monitoring/resolve` | Recebe link/ID, devolve `{kind: channel\|video, youtube_id}`. 0 units pra ID/URL com ID; 1 unit pra handle |
| PATCH | `/api/monitoring/videos/{id}` | Altera status |
| DELETE | `/api/monitoring/videos/{id}` | Remove vídeo + cascata (snapshots) |
| POST | `/api/monitoring/videos/{id}/snapshot` | Snapshot imediato do vídeo com deltas |
| PATCH | `/api/monitoring/videos/bulk-status` | Status em lote |
| POST | `/api/monitoring/videos/bulk-snapshot` | Snapshot em lote |
| POST | `/api/monitoring/videos/bulk-delete` | Remoção em lote |
| GET | `/api/sync/status` | `{interval_hours, next_run_at, last_run}` pro Dashboard |
| POST | `/api/sync/run` | Dispara sync manual síncrono (`type='manual'`) |
| GET | `/api/sync/runs?limit=` | Histórico de sync_runs (manual + scheduled) |
| GET | `/api/analytics/overview?status=active\|paused\|removed\|all` | Contadores por `signal` do último snapshot de cada canal + vídeos acelerando. `status` filtra por `Channel.status` (default `active`) |
| GET | `/api/analytics/channels?page=1&page_size=10&status=active` | **Bundle paginado**: canal + summary + 4 séries por página, em 1 request por página. Mesmo filtro `status` (default `active`) |
| GET | `/api/analytics/channels/{id}/timeseries?metric=` | Série temporal (`subscribers\|views_total\|avg_vpd_recent\|uploads_per_week`) |
| GET | `/api/analytics/channels/{id}/summary` | Totais + crescimento % 7d/30d + uploads/sem |
| GET | `/api/analytics/niches` | Agregação por tag: channels_count, avg_subscribers, avg_vpd |

---

## Fluxos críticos

1. **Healthcheck end-to-end** (Dashboard): SSR fetch paralelo em `/`, `/health`, `/health/db`, `/api/sync/status`, `/api/monitoring/channels`, `/api/monitoring/videos`. Se algum falhar, card vira `danger`.

2. **Criptografia de API keys** (Fase 2): usuário digita no `SecretInput` → PUT `/api/settings/{key}` → `settings_service.update_setting()` chama `encrypt()` (Fernet) → persiste `value` cifrado em `app_settings.value`. Ao ler: `_to_read()` NUNCA decifra para o DTO — retorna máscara (`********xxxx`). Decifragem só acontece em consumidores backend (ex.: `youtube_client.build_from_db()` lê `youtube.api_keys` e decifra para uso interno).

3. **Migrações**: sempre `.venv/Scripts/python.exe -m alembic upgrade head` a partir de `api/`. **Nunca** aplicar migração em produção sem autorização explícita (regra de ouro).

4. **Agrupamento de settings por prefixo** (Fase 2 UI): settings com prefixo `sync_`, `search.`, `channel.`, `monitor.`, `youtube.` caem automaticamente em seções correspondentes em [ConfiguracoesForm.tsx](web/app/configuracoes/ConfiguracoesForm.tsx). Prefixo desconhecido → "Outros". Novos grupos: editar o array `SECTIONS`.

5. **Discovery (Fase 3 MVP)**: UI chama `POST /api/discovery/search` → `discovery_service` monta `DiscoveryRun(status=running)` → `youtube_client` roda `search.list` por termo × idioma → hidrata vídeos/canais → filtra por views/VPD/duração → persiste resultados e marca run `success`. Em caso de exceção, marca `failed` com `notes`. Custos de quota: `search=100`, `videos/channels=1` (ver `QUOTA_COST`).

6. **Rotação de keys**: `youtube_client.YouTubeClient` é criado por request via `build_from_db()`; contadores de quota são em memória do processo (não persistem entre restarts). Se virar problema, mover `used[]` pra `app_settings` ou Redis. Em 403 com "quota"/"daily limit", key é marcada esgotada (`used[idx] = daily_quota`) e a próxima é tentada.

7. **Monitorar idempotente**: POST com canal já cadastrado retorna row existente. POST de vídeo novo resolve canal dono automaticamente (cria se preciso).

8. **Snapshot de canal** (Fase 4): `POST /api/monitoring/channels/:id/snapshot` → `snapshot_channel()` → `channels.list` (stats atuais) → deriva uploads playlist (`UC→UU`, economiza 1 chamada) → `playlistItems` + `videos.list` → calcula melhor upload por VPD → cria `TrackedVideo(tracking_source='best_from_channel')` **acumulativo** (não duplica, não remove) → grava `ChannelSnapshot` com deltas vs anterior. Custo ~3 units/canal.

9. **Snapshot de vídeo** (Fase 4): puxa stats, grava `VideoSnapshot` com deltas, atualiza `TrackedVideo.last_seen_*` para leitura rápida sem JOIN. `first_tracked_vpd` populado só no primeiro snapshot.

10. **Best videos acumulativo**: lista por canal sempre cresce (nunca remove). Mesmo vídeo detectado novamente não duplica. UI mostra em aba própria com carregamento lazy.

11. **Sync automático** (Fase 5): APScheduler `BackgroundScheduler` roda no mesmo processo do uvicorn via `lifespan` em [api/app/main.py](api/app/main.py). Intervalo lido de `sync_interval_hours` no startup. `misfire_grace_time=15min`, `coalesce=True`, `max_instances=1`. Cada tick abre **Session própria** (`run_sync_in_new_session`) porque `Depends(get_db)` não vale em jobs background.

12. **Reschedule dinâmico**: `settings_service.update_setting` detecta mudança em `sync_interval_hours` e chama `scheduler.reschedule(new_hours)` em runtime. Sem restart. Import tardio do módulo `scheduler` evita ciclo.

13. **Tolerância a falha no sync**: `run_sync` itera com `try/except` individual — falhas agregadas em `notes`, status final `success` (zero erros) ou `partial` (com erros). Só vira `failed` se erro no setup (ex.: API key ausente).

14. **Custo de quota estimado**: ~3 units/canal + ~1 unit/vídeo. 50 canais + 100 vídeos = 250 units/tick. Default 12h = ~500/dia. Margem confortável para 10k/dia por key.

15. **Enriquecimento analytics no snapshot** (Fase 6): `snapshot_channel` agora calcula `signal` (`saturated` → `heating` → `promising` → `stable`, nessa ordem de precedência), `signal_reason`, `vpd_trend`/`delta_avg_vpd` (diferença vs snapshot anterior) e `uploads_per_week` (contagem de `TrackedVideo.first_tracked_at` nos últimos 30 dias, sem custo extra de quota). Thresholds em `analytics.promising_max_subscribers` (50k default) e `analytics.promising_vpd_ratio` (0.3 default, multiplicador de `channel.vpd_saturation`). Alteráveis em runtime via `/configuracoes`.

16. **Overview analytics**: `analytics_service.overview()` agrupa pelo `signal` do **último** `ChannelSnapshot` de cada canal (subquery `MAX(captured_at)` por `channel_id`). `videos_accelerating` compara os 2 últimos `VideoSnapshot` por vídeo e conta onde `vpd[0] > vpd[1]`. Canais com snapshots anteriores à Fase 6 aparecem como `channels_unknown` até receberem novo snapshot.

17. **Gráficos no frontend (paginado + filtro de status, 2026-04-25/26)**: página `/analytics` é um server component que pré-carrega só `niches` (overview foi pro client porque agora depende do filtro de status). `AnalyticsView` (client) tem barra de tabs `Ativos / Pausados / Removidos / Todos` (default `active`) e dispara em paralelo `GET /api/analytics/overview?status=...` + `GET /api/analytics/channels?page=...&page_size=...&status=...` a cada mudança de filtro/página. O endpoint de canais devolve um `PaginatedChannelAnalytics` com bundle agregado (canal + summary + 4 séries) — substituiu o modelo anterior de `5N requests` que derrubava o site. Filtragem central em `_filter_channel_ids_by_status()` ([api/app/services/analytics_service.py](api/app/services/analytics_service.py)) — overview e listagem aplicam a mesma regra (consistência). Trocar de filtro reseta para a página 1. Endpoints unitários (`/summary`, `/timeseries`) **mantidos** para reuso futuro/depuração. Skeleton dimensionado pela `page_size`, não pelo total de canais.

18. **Feedback global** (Fase 7): qualquer ação (sync manual, snapshot, salvar config, adicionar canal/vídeo, busca) que antes mostrava erro/sucesso inline agora dispara um toast via `useToast()` do `<ToasterProvider>` montado em [web/app/layout.tsx](web/app/layout.tsx). Handlers de erro chamam `toast.error(msg)` e re-lançam quando o caller precisa reagir (ex.: `ConfiguracoesForm.save` re-lança pra o `SecretInput` saber que não deve fechar o editor). `AnalyticsView` usa `<ErrorCard>` com botão "Tentar de novo" porque o erro de carga inicial precisa de permanência, não um toast efêmero.

19. **Indicador global de sync** (Fase 7): [web/components/GlobalSyncIndicator.tsx](web/components/GlobalSyncIndicator.tsx) é client, montado uma vez no `<main>` pelo layout. Faz polling em `/api/sync/status` a cada 5s (`setInterval`) e renderiza um badge apenas quando `last_run.status === "running"`. Serve pro caso de sync longo (>30s, muitos canais) enquanto o usuário navega pra outra página. Custo: 12 req/min quando a aba está aberta — aceitável porque é um endpoint leve e local. Em prod pode virar SSE ou WebSocket se incomodar.

20. **Loading com skeletons**: [web/components/Skeleton.tsx](web/components/Skeleton.tsx) exporta `<Skeleton>` (bloco isolado) e `<SkeletonCard>` (um cartão inteiro). AnalyticsView renderiza um esqueleto de cartão de canal enquanto busca dados — mesma estrutura visual da versão final, só que com blocos cinza em shimmer. CSS respeita `prefers-reduced-motion` e desliga todas as animações quando o usuário pediu redução.

21. **Dockerfiles** (Fase 8): [api/Dockerfile](api/Dockerfile) é single-stage simples (Python 3.11-slim + uvicorn + requirements), porta 8000. [web/Dockerfile](web/Dockerfile) é multi-stage (deps → builder → runner) com Node 20-alpine. O runner só copia o `.next/standalone/` + `.next/static/` + `public/`, o que exige `output: "standalone"` em [next.config.ts](web/next.config.ts). Usuário não-root `nextjs:1001` no runner. Imagem final fica pequena (~150 MB est.) e starta com `node server.js`. Build arg `NEXT_PUBLIC_API_URL` é repassado a env var antes do `npm run build` — EasyPanel precisa passar isso como build arg, senão o frontend sai com `http://localhost:8000` embutido.

22. **Higiene de deploy**: `.env` e `.env.local` não podem vazar pro container — cobertos por [api/.dockerignore](api/.dockerignore) e [web/.dockerignore](web/.dockerignore) (além do `.gitignore`). Checklist: `git check-ignore -v api/.env web/.env.local` retorna linhas do gitignore → ambos bloqueados. `APP_SECRET_KEY` de prod vai só nas env vars do EasyPanel, **não** no repositório.

23. **Lições do deploy real (2026-04-24)** — bugs/galhos achados em produção que a Fase 8 não cobriu e foram patched:

   - **Scheduler crashava no startup com banco vazio**: o `lifespan` do FastAPI chama `scheduler.start()` que tentava ler `sync_interval_hours` do banco antes de existir tabela. Container morria antes do shell ficar acessível pra rodar alembic. Fix em [api/app/core/scheduler.py](api/app/core/scheduler.py): `_current_interval_hours()` agora envolve a leitura num `try/except` e usa `Settings.sync_interval_hours` (env var) como fallback. Loga warning pedindo alembic+seed.
   - **Alembic quebrou com `ValueError: invalid interpolation syntax`**: senhas URL-encoded com `%XX` (ex.: `%24` pra `$`) faziam o ConfigParser interno do Alembic tentar interpolar. SQLAlchemy direto não sofre disso. Fix em [api/migrations/env.py](api/migrations/env.py): `.replace("%", "%%")` antes de `set_main_option`.
   - **Dockerfile do web tinha `COPY /app/public` mas o projeto não tem `public/`**: build quebrou no stage runner. Fix em [web/Dockerfile](web/Dockerfile): linha removida (comentário de como reativar caso precise um dia).
   - **Domínio do EasyPanel pedia "Protocolo do destino"**: marcando HTTPS, o proxy mandava TLS handshake pro uvicorn/next que servem **HTTP cru** dentro do container → "Invalid HTTP request received" + 500. Solução: **destino interno é HTTP**, externo é HTTPS (certificado Let's Encrypt cuidado pelo EasyPanel). Vale tanto pra `-api` (porta 8000) quanto pra `-web` (porta 3000).
   - **Build args do Next.js (NEXT_PUBLIC_*)**: o EasyPanel **passa env vars do Ambiente como build-arg automaticamente** — não precisa de campo "Build Args" separado. Confirmado vendo o comando `docker buildx build --build-arg 'NEXT_PUBLIC_API_URL=...'` nos logs do build.

24. **Fluxo recomendado pra primeira vez no EasyPanel** (resumo do que demos certo): (1) criar serviço `App` com Source apontando pro `/api` ou `/web`, (2) Construção em `Dockerfile` (não Nixpacks), (3) Ambiente com env vars, (4) Implantar, (5) **só depois do container estar verde**, adicionar Domínio na aba dedicada com **destino HTTP**, externo HTTPS, porta correta. Pra `-api`, depois rodar `alembic upgrade head` + `python -m app.seed` no shell do container (botão `>_` → Bash). Pra `-web`, basta o domínio ficar de pé.

25. **Thumbnails** (canal e vídeo): `monitoring_service._pick_thumbnail()` extrai a maior URL disponível (`high → medium → default`) do `snippet.thumbnails` que já vem em todas as chamadas `channels.list` e `videos.list`. Custo extra: **zero** — é dado que já trafega. Persistido em `channels.thumbnail_url` e `tracked_videos.thumbnail_url` (VARCHAR(512)). Atualizado em todos os pontos onde criamos ou refresh-amos esses registros (`_get_or_create_channel_from_youtube`, `snapshot_channel`, `add_video`, `_accumulate_best_video`, `snapshot_video`). Frontend usa `<ChannelAvatar>` (circular, fallback inicial do título) em Monitoramento + Analytics; `<VideoThumbnail>` (16:9, fallback "sem thumb") em Vídeos lista (200×113) + Vídeos grade (320×180) + Melhores Vídeos.

26. **Layout lista/grade** (Monitoramento → Vídeos): toggle no canto superior direito da aba alterna entre tabela tradicional (`list`) e grade de cards (`grid`, ~280px por coluna). Persistido em `localStorage` chave `monitoramento.videoLayout`. No modo grade os campos visíveis são reduzidos pra caber no card: thumb grande, título (2 linhas truncadas), pill de status, views, VPD atual + inicial entre parênteses, botões Atualizar e Pausar/Retomar. **Sem** botão Remover na grade — quem quer apagar usa a lista.

27. **API keys multilinha**: `SecretInput` ganhou prop `multiline?: boolean` (textarea 5 linhas, monospace). Em `ConfiguracoesForm`, ativada **só** pra `youtube.api_keys` — outros secrets continuam input de uma linha. Backend `youtube_client.build_from_db()` aceita `,` ou `\n` como separador (compat com config CSV antigo). Pra novos secrets multilinha, basta adicionar a key no condicional do `ConfiguracoesForm`.

28. **Configurações com layout invertido**: descrição agora vem em destaque (texto normal, fonte 13px) e a chave técnica (`youtube.api_keys`, etc.) aparece embaixo em fonte monospace cinza, como referência. Lógica em [ConfiguracoesForm.tsx](web/app/configuracoes/ConfiguracoesForm.tsx).

29. **Bug-padrão a evitar — schemas Pydantic construídos manualmente**: em [api/app/routers/monitoring.py](api/app/routers/monitoring.py), a função `_channel_with_stats` constrói `ChannelWithStats` campo a campo com keyword args (porque precisa misturar dados do `Channel` ORM + último `ChannelSnapshot`). Quando adicionamos `thumbnail_url`, esquecemos esse lugar e o GET `/api/monitoring/channels` retornou `null` mesmo com banco populado (POST `/api/monitoring/channels` que usa `from_attributes=True` direto funcionava). **Regra**: ao adicionar campo num schema, fazer `git grep "NomeDoSchema("` pra achar todos os construtores manuais.

30. **Scripts one-shot em `scripts/`**:
    - `import_legacy.py`: importa do projeto desktop antigo (`E:\Automacao-YT\yt-analise-canais\dados\`). Idempotente. `--base-url` aponta pro alvo, `--skip-keys` pula configuração das API keys (use em prod onde já configurou via UI), `--skip-listados` pula os 232 canais "vistos", `--dry-run` mostra plano sem escrever. Usa `urllib` puro (sem deps). Rodado uma vez em local + uma vez em prod (2026-04-25), gerou ~216 canais em prod (11 active + 205 paused; 7 falham por canais deletados no YouTube).
    - `backfill_thumbnails.py`: popula `thumbnail_url` em lote (50 IDs por chamada `channels.list`/`videos.list`). Custo: 1 unit por lote vs 3 units por canal se fosse via snapshot. Idempotente — só toca em registros com `thumbnail_url IS NULL`. Útil quando se importa canais antes do code do `_pick_thumbnail` estar rodando, ou quando se adiciona o campo a um banco que já tem dados.

31. **Adicionar canal/vídeo via link** (UX do usuário): aba Canais do Monitoramento tem [web/components/AddByLinkInput.tsx](web/components/AddByLinkInput.tsx) no topo — um input só que aceita link ou ID. Backend resolve em [api/app/services/monitoring_service.py](api/app/services/monitoring_service.py) (`resolve_youtube_input`) com regex pra IDs puros e URLs (`watch?v=`, `youtu.be/`, `shorts/`, `embed/`, `/channel/UC…`, `/@handle`, `/c/`, `/user/`). Endpoint `POST /api/monitoring/resolve` retorna `{kind, youtube_id}`; o frontend encadeia `add_channel` ou `add_video`. Custos de quota: 0 units pra ID/URL com ID embutido; 1 unit pra handles (resolve via `channels.list?forHandle=`). Vídeos resolvem o canal dono automaticamente (já era assim no `add_video`).

32. **Filtros + ordenação client-side** em Monitoramento → abas Canais e Vídeos. Componentes [web/components/ChannelsFilterBar.tsx](web/components/ChannelsFilterBar.tsx) e [web/components/VideosFilterBar.tsx](web/components/VideosFilterBar.tsx) exportam (a) o componente da barra, (b) o tipo dos filtros, (c) o default e (d) a função `apply...Filters(list, filters)` que filtra+ordena. `MonitoramentoView` mantém 2 states de filtros e usa `useMemo` pra derivar listas. **Não persiste** em localStorage (decisão deliberada: F5 reseta — evita "sumiço fantasma" de canal por filtro esquecido). Empty state diferenciado: lista vazia ("nenhum canal monitorado") vs filtro vazio ("nenhum corresponde aos filtros aplicados") com botão Limpar visível só quando há filtro ativo. Decisão de escala: client-side suporta tranquilamente até alguns milhares de itens; se um dia escalar pra 10k+, migrar pra query params na API.

33. **Ordenação por header clicável** ([web/components/SortableHeader.tsx](web/components/SortableHeader.tsx)): nas tabelas em modo lista, clicar num `<th>` ordenável cicla 3 estados (null → desc → asc → default). Setinha (↕ inativo / ↓ desc / ↑ asc) em `var(--accent)` quando ativa. Algumas colunas têm só `descKey` (Δ Inscritos, VPD inicial, Último sync) — nesses casos o ciclo vira 2 estados (null → desc → default). No **modo grade da aba Vídeos** e em **mobile (≤768px)** não há header pra clicar, então `VideosFilterBar` e `ChannelsFilterBar` aceitam `showSortDropdown` como prop e renderizam um `<select>` inline (`MonitoramentoView` passa `videoLayout === "grid" || isMobile` e `isMobile` respectivamente). Header desktop e dropdown mobile/grade compartilham o mesmo estado `*Filters.sort` — alternar contexto preserva a ordenação.

34. **Ações em massa em Monitoramento** (2026-04-25): canais e vídeos têm 6 endpoints bulk em [api/app/routers/monitoring.py](api/app/routers/monitoring.py): `bulk-status` (PATCH), `bulk-snapshot` (POST) e `bulk-delete` (POST, não DELETE — body `{ids}` no DELETE quebra clientes simples). Helper `_run_bulk(ids, op)` itera item a item capturando exceções por id e devolve `BulkOperationResponse {total, success_count, error_count, processed_ids, errors:[{id,message}]}` — falha individual **não** trava o lote. Reusa `monitoring_service.set_channel_status / snapshot_channel / delete_channel` (e equivalentes de vídeo). Importante: as rotas bulk são registradas **antes** das `/{id}` no router para FastAPI não tentar casar `bulk-status` contra o path param `int`. Frontend ([web/app/monitoramento/MonitoramentoView.tsx](web/app/monitoramento/MonitoramentoView.tsx)) tem estado `selectedChannelIds: Set<number>` e `selectedVideoIds: Set<number>`, checkbox por linha + header com `indeterminate`, barra `.bulk-actions-bar` com Atualizar/Pausar-Retomar/Remover/Limpar (botão único quando seleção é homogênea, dois botões quando mistura `active`+`paused`). Após resposta: `processed_ids` saem da seleção (falhados ficam pra retry), `useEffect` limpa IDs stale após `refreshChannels/refreshVideos`. Toast resume sucesso total/parcial (com amostra de 3 erros + contador).

36. **Descoberta automática pós-sync** (2026-04-25): após cada `run_sync` terminar (success/partial), [api/app/services/sync_service.py](api/app/services/sync_service.py) chama em `try/except` próprio (com import tardio pra evitar ciclo) o [api/app/services/auto_discovery_service.py](api/app/services/auto_discovery_service.py). O `run_auto_discovery` (a) checa flag `discovery.auto_enabled`, (b) calcula orçamento `daily_quota_per_key × num_keys × discovery.auto_quota_pct` (default 50%), (c) monta lista de termos via `pick_terms_for_run` = **70% seed (rotação determinística por hora atual, sem persistir estado) + 30% derivados** de palavras frequentes em títulos de `Channel` + últimos 500 `DiscoveryResultChannel` (filtra stopwords pt+en, palavras com 4+ chars, `min_freq=3`), (d) corta lista por orçamento usando `ESTIMATED_COST_PER_TERM=300` (conservador: 1 página × 3 idiomas × 100 units), (e) reusa `discovery_service.run_discovery` com `pages_per_term=1` (prefere alcance a profundidade). **Nunca propaga exceção** — falha aqui não pode invalidar o sync. Termos seed iniciais (~95, pt+en) em [api/app/services/discovery_seed_terms.py](api/app/services/discovery_seed_terms.py); valor ativo fica em `discovery.auto_keywords` (multiline, editável em /configuracoes).

37. **Blacklist de canais removidos** (2026-04-25): `monitoring_service.delete_channel` insere o `youtube_channel_id` em `channel_blacklist` (idempotente, `reason='user_removed'`) **antes** de fazer o cascade delete. `discovery_service.run_discovery` chama `get_blacklisted_channel_ids(db)` entre os passos 3 (filtro de vídeos) e 4 (hidratação de canais) — descarta vídeos cujo `channelId` está na blacklist, evitando o custo de `channels.list`. Endpoints `GET /api/discovery/blacklist` e `DELETE /api/discovery/blacklist/{yt_id}` permitem inspecionar e remover (re-monitorar exige tirar da blacklist primeiro). Estado de revisão por item: `discovery_results_channels.reviewed_at` e `discovery_results_videos.reviewed_at` (TIMESTAMP NULL) marcam o que o usuário já triou — preservado entre sessões. UI em /runs > Descoberta: linha clicável expande detalhes inline (`GET /api/discovery/runs/:id`), checkbox "OK" por item, contador `X/Y revisados (Z%)` na linha resumida. Adicionar item ao monitoramento marca implicitamente como revisado.

38. **Bulk progress bar — snapshot itemizado** (2026-04-25): apenas o snapshot em massa virou itemizado no frontend (canais e vídeos). Status e delete continuam usando os endpoints `bulk-*` originais (são instantâneos). Helper `runItemizedSnapshot` em [web/app/monitoramento/MonitoramentoView.tsx](web/app/monitoramento/MonitoramentoView.tsx) dispara N `apiPost` unitários via pool com `BULK_CONCURRENCY=4` (não estoura conexão nem quota), atualiza state `BulkProgress {label, total, done, success, failed}` por item, remove o id da seleção em tempo real via `onSuccess(id)`, mostra `<BulkProgressBar>` acima das abas com barra que muda de cor (`running/ok/partial/fail`) e contador `done/total (pct%)`. No fim, toast resume e a barra fica 2s na tela. Os endpoints bulk antigos (`/channels/bulk-snapshot`, `/videos/bulk-snapshot`) **continuam existindo** mas não são mais usados pela UI — mantidos pra cliente CLI/script externo se precisar.

39. **Notificações do navegador** (2026-04-25, escopo inicial): `Notification` API nativa, **funciona só com aba aberta**. Não usa Service Worker / Web Push (entrega em background completa exigiria backend de push com VAPID + persistência de subscription). Hook [web/lib/useBrowserNotifications.ts](web/lib/useBrowserNotifications.ts) expõe estados (`unsupported|default|granted|denied`) + preferência `enabled` em `localStorage` (per-device — não faz sentido sincronizar). [web/components/NotificationsSettings.tsx](web/components/NotificationsSettings.tsx) fica no topo da `/configuracoes` com toggle inteligente que adapta texto por estado. Eventos disparadores: por enquanto, **só término de sync** — [web/components/GlobalSyncIndicator.tsx](web/components/GlobalSyncIndicator.tsx) detecta transição `running → terminado` (ou run novo já terminado, comparando `prevStatus`+`prevId`) e dispara `Notification` com título por status (`Sync concluído ✓` / `... com falhas parciais` / `Sync falhou`) e body `channels_processed · videos_processed`. `tag: sync-{id}` evita duplicatas se o browser re-mostrar.

40. **Sugestões automáticas de monitoramento** (2026-04-26): tela `/monitoramento` ganhou aba **Sugestões** com duas seções, sem ação automática (sempre exige clique do usuário):
    - **"Recomendados para monitorar"**: `GET /api/suggestions/to-monitor` → `suggestions_service.list_monitor_suggestions(db)` busca em `discovery_results_channels` (último registro por `youtube_channel_id` via `MAX(captured_at)`) os canais que (a) **não** estão na tabela `channels`, (b) **não** estão na blacklist, (c) `avg_vpd_recent ≥ suggestions.monitor_min_vpd` (default 10000), (d) `channel_published_at` existe e `>= now - suggestions.monitor_max_age_days` (default 60). Ordena por VPD desc.
    - **"Possivelmente mortos"**: `GET /api/suggestions/to-remove` → `list_dead_suggestions(db)` percorre canais `status='active'` e aplica regra composta (TODAS valem): (a) último `TrackedVideo.first_tracked_at` há ≥ `suggestions.dead_min_days_no_uploads` dias OU sem uploads tracked nenhum, (b) `last_snapshot.avg_vpd_recent ≤ suggestions.dead_max_vpd` (default 2000), (c) `last_snapshot.signal in (NULL, 'stable', 'unknown')`. Ordena por "mais morto primeiro" (VPD asc, dias-sem-upload desc).
    - **`channel_published_at` em `discovery_results_channels`** (migration `d6df02f56387`): coluna nova preenchida pelo `discovery_service.run_discovery` a partir do `snippet.publishedAt` que já vem grátis em `channels.list` (zero quota extra). Registros antigos (pré-migration) ficam NULL e **não aparecem** nas sugestões de monitorar até serem re-descobertos pelo auto-discovery.
    - **UI** ([web/app/monitoramento/MonitoramentoView.tsx](web/app/monitoramento/MonitoramentoView.tsx)): aba lazy-load (carrega só ao abrir), botão "Recarregar" no banner. Cards `SuggestionsToMonitor` e `SuggestionsToRemove` (componentes locais). Ações reusam endpoints existentes (`POST /api/monitoring/channels`, `PATCH /channels/:id`, `DELETE /channels/:id`) — ao executar, item sai da lista local na hora pra dar feedback imediato.
    - **Configs separadas** em `/configuracoes` → "Sugestões" (prefixo `suggestions.*`, distinto de `analytics.*`/`monitor.*`/`discovery.*` justamente pra evitar mistura).

41. **Responsividade real** (2026-04-25, Plano A + Plano B): a aplicação não é mais desktop-only.
    - **Plano A (shell + breakpoints)**: [web/components/Sidebar.tsx](web/components/Sidebar.tsx) virou drawer mobile com botão hambúrguer fixed, ESC fecha, troca de rota fecha, click no overlay fecha, `body { overflow: hidden }` enquanto aberto. [web/app/globals.css](web/app/globals.css) tem 3 breakpoints reais: ≤1024 (sidebar 200px, padding reduzido, analytics-overview 2 col), ≤768 (sidebar fixed transformX, hambúrguer aparece, `.main` ganha padding-top 64px, tabs roláveis horizontalmente, filter-bar quebra em linhas, row-actions com tap target ≥36px, tabelas com `overflow-x: auto` + paddings reduzidos, toaster ancorado no rodapé largura quase total, card-grid 1 col, video-grid `minmax(220px,1fr)`), ≤480 (tipografia menor, botões 36px+, bulk-actions empilhada com botões 38px+). Bulk-actions já empilha em ≤600.
    - **Plano B (cards stackados em `/monitoramento`)**: hook [web/lib/useIsMobile.ts](web/lib/useIsMobile.ts) usa `matchMedia` (default ≤768), SSR-safe. `MonitoramentoView` renderiza **dois blocos** por aba — `desktop-only` (tabela existente) e `mobile-only` (lista de `.mobile-card`). Cards têm header (checkbox + avatar + título + status), grid 2x2 de meta, ações row, e uma toolbar acima com "Selecionar todos / Desmarcar todos" + contador. `ChannelsFilterBar` ganhou `showSortDropdown` espelhando o que `VideosFilterBar` já tinha — em mobile ambos mostram select de ordenação inline. Aba Vídeos > grid já era responsiva, não foi tocada. Estado e handlers de seleção/bulk **reaproveitados** sem duplicação. Outras telas (`/dashboard`, `/descoberta`, `/runs`, `/configuracoes`) já usam grids responsivos (`card-grid`, `form-grid`, `settings-row`) e `.table-wrap` com `overflow-x` — sem intervenção pontual necessária. **Validação visual em 360/390/768/1024 é responsabilidade do usuário** (a IA não testa visual).

42. **Descoberta visual + indisponibilidade persistente** (2026-04-26): a migration [`api/migrations/versions/1f7c9e4b2d11_add_discovery_thumbnails_and_video_unavailable.py`](api/migrations/versions/1f7c9e4b2d11_add_discovery_thumbnails_and_video_unavailable.py) adicionou `thumbnail_url` em `discovery_results_channels` e `discovery_results_videos`, além de `tracked_videos.unavailable_reason` e `tracked_videos.unavailable_since`. O [`api/app/services/discovery_service.py`](api/app/services/discovery_service.py) agora persiste thumb de canal via `pick_thumbnail(snippet)` e thumb de vídeo com fallback previsível `i.ytimg.com/vi/.../hqdefault.jpg`; [`web/app/descoberta/DescobertaForm.tsx`](web/app/descoberta/DescobertaForm.tsx) reaproveita [`web/components/ChannelAvatar.tsx`](web/components/ChannelAvatar.tsx) e [`web/components/VideoThumbnail.tsx`](web/components/VideoThumbnail.tsx) para renderizar isso na tabela. Para itens removidos/privados, [`api/app/services/monitoring_service.py`](api/app/services/monitoring_service.py) marca canal como `status='removed'` com `notes` auditável e põe o `youtube_channel_id` na blacklist; vídeos passam a gravar `unavailable_reason`/`unavailable_since`. [`api/app/services/sync_service.py`](api/app/services/sync_service.py) trata esses casos como nota informativa, sem manter `partial` recorrente.

---

## Deploy (EasyPanel, em produção desde 2026-04-24)

Projeto no EasyPanel: `banco`. Três serviços rodando:

| Serviço | URL pública | Porta interna | Source |
|---|---|---|---|
| `youtube-analyzer-api` | https://banco-youtube-analyzer-api.cpgdmb.easypanel.host | 8000 | repo Git, `/api`, [api/Dockerfile](api/Dockerfile) |
| `youtube-analyzer-web` | https://banco-youtube-analyzer-web.cpgdmb.easypanel.host | 3000 | repo Git, `/web`, [web/Dockerfile](web/Dockerfile) |
| `youtube-analyzer-banco` | (interno) | 3306 | MySQL 8 provisionado pelo EasyPanel |

Host interno do banco (acessível só dentro da rede do EasyPanel):
`banco_youtube-analyzer-banco:3306`. É o que aparece no `DATABASE_URL` da API.

Repo Git: https://github.com/rafaelkolaias-lang/yt-analise-canais (público,
para deploy via Git padrão do EasyPanel funcionar sem chave SSH/Deploy Key).

Deploy disparado:
1. Manualmente (botão "Implantar" em cada serviço).
2. Via webhook (URLs gravadas em `temporary_rules.md`, gitignorado).

Passo-a-passo de manutenção operacional (URL muda, senha rotaciona, secret
trocada, etc.) em [README.md → Manutenção](README.md#manutenção--o-que-fazer-se).

---

## Rodar localmente (dev)

### Pré-requisitos
- Python 3.11+, Node.js 18.17+ (testado em 24.13)
- MySQL do XAMPP ligado (ou equivalente)

### Primeira vez
```bash
# API
cd api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # ajustar DATABASE_URL e APP_SECRET_KEY
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m app.seed

# Web
cd web
npm install
cp .env.example .env.local
```

### Subir (2 terminais) OU duplo-clique em `start-dev.bat`
```bash
# Terminal 1 (API na 8000)
cd api && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Terminal 2 (Web na 3000)
cd web && npm run dev
```

URLs: Dashboard <http://localhost:3000>, Swagger <http://localhost:8000/docs>.

---

## Armadilhas conhecidas

- **MySQL do XAMPP local teve InnoDB corrompido** em 2026-04-23 (log sequence number is in the future). Backup em `c:\xampp\mysql\data_backup_2026-04-23\` (119 MB). Bancos antigos (`dados`, `snake_arena`) descartados com autorização.
- **`APP_SECRET_KEY` perdida = secrets do banco irrecuperáveis** (Fernet não tem backdoor). Gerar uma para dev e outra diferente para prod; manter prod só no env do container.
- **Host interno do EasyPanel** (`banco_youtube-analyzer-banco`) **não resolve fora da rede** do EasyPanel. Para dev local apontar para XAMPP ou IP público do serviço.
- **Linter da IDE pode marcar imports de `app.*`, `sqlalchemy`, `fastapi` como "not found"** — falso-positivo (lê Python global, não o venv em `api/.venv`). Runtime via `.venv/Scripts/python.exe` resolve tudo. Ignorar.
- **Port conflict em dev**: se `uvicorn` crashar mal, porta 8000 pode ficar órfã. `taskkill //F //IM python.exe` libera. Mesmo vale pra `node.exe` na 3000.
- **`datetime.utcnow()`** é naive. Frontend converte pra local via `toLocaleString('pt-BR')`. Scheduler do APScheduler retorna tz-aware (UTC), normalizado em `scheduler.next_run_time()`.
- **`uvicorn --reload`** em dev não dispara scheduler duplicado — o reloader só recarrega o processo filho. Em prod, não usar `--reload`.
- **Snapshots antigos não têm `signal` preenchido** — o enriquecimento só roda em `snapshot_channel` a partir da Fase 6. Overview conta esses canais em `channels_unknown` até cair um sync novo. Sem backfill retroativo intencionalmente (custo de quota zero pra esperar o próximo tick).
- **Dashboard faz 7 fetches paralelos agora** (healthchecks + sync status + canais + vídeos + analytics overview). Se algum endpoint ficar lento vira gargalo visível na primeira renderização.
- **Polling do GlobalSyncIndicator** acontece em toda página (está no layout). Em dev com a aba aberta, dá pra ver a cada 5s uma request em `/api/sync/status` nos logs do uvicorn — esperado.
- **`useToast` fora de `<ToasterProvider>` lança erro** em runtime ("precisa estar dentro de ToasterProvider"). Como o provider envolve a app-shell inteira no layout, todos os componentes client têm acesso. Se criar nova página, não precisa nada extra.
- **`NEXT_PUBLIC_API_URL` é lida em build time**, não runtime. Mudar a URL da API depois do deploy exige rebuild da imagem do `youtube-analyzer-web` — não basta trocar env var e restartar. No EasyPanel, passar como build arg além de env var pra garantir.
- **`output: "standalone"` inclui `node_modules` só do que foi efetivamente importado**, numa cópia parcial em `.next/standalone/node_modules`. Se mudar o `next.config.ts` pra tirar o standalone, o `web/Dockerfile` atual **quebra** porque não vai existir `server.js`. Reverter os dois juntos ou não mudar.
- **Docker Desktop não instalado na máquina dev** (2026-04-24) — o primeiro build real dos Dockerfiles foi no EasyPanel. Resultaram em 3 fixes (scheduler tolerante a banco vazio, escape de `%` no env.py do Alembic, remoção do `COPY /app/public`).
- **Domínios EasyPanel — destino HTTP, externo HTTPS**. Marcar HTTPS no destino faz o proxy Traefik mandar TLS pro uvicorn/Next que servem só HTTP cru no container → "Invalid HTTP request received" e 500. Vale pra `-api` (8000) e `-web` (3000).
- **Webhook de deploy do EasyPanel é uma credencial**. Cada serviço tem seu próprio. Estão guardados em `temporary_rules.md` (gitignorado). Não ecoar em respostas pro usuário depois de salvos.
- **Auto-discovery em base nova/sem canais**: a derivação de termos depende de já haver `Channel` ou `DiscoveryResultChannel` no banco. Em base zerada, os primeiros runs usam só termos seed — esperado, vai melhorar conforme aparecem canais.
- **Notificações do navegador só com aba aberta**: a Notification API atual NÃO entrega em background. Pra entrega real (PWA / Web Push), precisa Service Worker + backend de push com VAPID keys + persistência de subscriptions — é tarefa separada não implementada.
- **Bulk endpoints antigos seguem expostos**: `/api/monitoring/{channels,videos}/bulk-snapshot` ainda existem mas a UI principal não usa mais (substituído pelo `runItemizedSnapshot`). Mantido por compat com qualquer script CLI; remover só se confirmar que ninguém depende.
- **Toda migration nova exige `alembic upgrade head` + `python -m app.seed` no shell do `-api` em prod após o deploy**: o container não roda automaticamente. Padrão: abrir EasyPanel → `youtube-analyzer-api` → `>_` (Console) → colar os 2 comandos. Migrations atuais aplicáveis em prod: `d69d8c5c7a0e`, `59b9687df885`, `56a880b51364`, `d6df02f56387`. A última (`d6df02f56387`) é necessária pra "Sugestões → Recomendados para monitorar" funcionar — se faltar, a lista fica vazia (filtro exige `channel_published_at IS NOT NULL`).
- **Sugestões "para monitorar" dependem de canais re-descobertos pós-2026-04-26**: registros antigos de `discovery_results_channels` ficaram com `channel_published_at=NULL` e não aparecem na lista até o auto-discovery re-encontrá-los. Em base nova, primeiros runs já gravam corretamente.

---

## Regras de ouro

- **Banco**: nenhuma alteração (CREATE/ALTER/DROP/INSERT/UPDATE/DELETE, migrações) sem autorização explícita. Dev local é aberto; prod EasyPanel requer confirmação.
- **Git commit/push/deploy**: proibido sem pedido explícito via chat. Autorização anterior não vale pra próxima execução.
- **Credenciais**: nunca commitar `.env` real. `.gitignore` cobre `**/.env` com exceção para `.env.example`. Conferir com `git check-ignore -v api/.env`.
- **Coordenação multi-IA**: ao editar `!projeto.md` ou `!executar.md`, adicionar `AGUARDE ALTERANDO` na primeira linha; remover ao terminar.

