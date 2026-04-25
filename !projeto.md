# !projeto.md — youtube-analyzer

> Sistema web para descoberta, monitoramento e analytics de canais do YouTube, com foco em identificar **nichos dark em aceleração** e oportunidades de réplica. Sucessor em arquitetura web do app desktop Tkinter antigo (agora removido — toda a funcionalidade relevante foi portada para o stack web).

> **Status (2026-04-24):**
> - **Fase 0** (fundação web) — ✅
> - **Fase 1** (modelagem do banco) — ✅
> - **Fase 2** (configurações centrais + API keys cifradas) — ✅
> - **Fase 3** (descoberta com YouTube Data API v3) — ✅
> - **Fase 4** (monitoramento persistente + snapshots + melhores vídeos) — ✅
> - **Fase 5** (sync automático APScheduler + manual + histórico) — ✅
> - **Fase 6** (analytics: sinais, mini-gráficos por canal, nichos) — ✅
> - **Fase 7** (UX polish: toaster, skeletons, indicador global de sync) — ✅
> - **Fase 8** (Dockerfiles + docs prontos para deploy EasyPanel) — ✅
> - **Deploy inicial em produção** (EasyPanel projeto `banco`) — ✅ 2026-04-24
>
> Sistema operacional 24/7. Próxima ação manual: configurar a YouTube API key
> em `/configuracoes` pra começar a popular dados (sync já está agendado pro
> próximo tick de 12h, mas precisa de key pra fazer requests reais).

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
│   │   ├── seed.py                   # seed idempotente de 13 app_settings
│   │   ├── core/
│   │   │   ├── config.py             # Settings (pydantic-settings, lê .env)
│   │   │   ├── database.py           # engine, SessionLocal, Base, get_db()
│   │   │   ├── crypto.py             # Fernet encrypt/decrypt/mask para secrets no banco
│   │   │   └── scheduler.py          # APScheduler: start/shutdown/reschedule/next_run_time
│   │   ├── routers/
│   │   │   ├── health.py             # / | /health | /health/db
│   │   │   ├── settings.py           # /api/settings  (GET list, GET :key, PUT :key)
│   │   │   ├── discovery.py          # /api/discovery/{defaults,search,runs,runs/:id}
│   │   │   ├── monitoring.py         # /api/monitoring/{channels,videos} + snapshot/patch/delete/best-videos
│   │   │   ├── sync.py               # /api/sync/{status,run,runs}
│   │   │   └── analytics.py          # /api/analytics/{overview,channels/:id/{timeseries,summary},niches}
│   │   ├── services/
│   │   │   ├── settings_service.py   # público: sempre mascara secrets
│   │   │   ├── settings_reader.py    # interno: get_int/get_float/get_str/get_csv com cast
│   │   │   ├── youtube_client.py     # httpx + rotação de keys + quota tracking
│   │   │   ├── discovery_service.py  # search → hydrate → filter → persist
│   │   │   ├── monitoring_service.py # add/snapshot/toggle/delete + best videos + signal/analytics enrichment
│   │   │   ├── sync_service.py       # run_sync: itera ativos, tolera falha individual
│   │   │   └── analytics_service.py  # overview, timeseries, summary, niches (só lê banco)
│   │   ├── schemas/
│   │   │   ├── settings.py           # AppSettingRead / AppSettingUpdate
│   │   │   ├── discovery.py          # SearchRequest, DefaultFiltersRead, ResultChannel/Video, DiscoveryRunRead
│   │   │   ├── monitoring.py         # AddChannel/VideoRequest, ChannelRead, TrackedVideoRead, ChannelWithStats
│   │   │   ├── sync.py               # SyncRunRead, SyncStatusRead
│   │   │   └── analytics.py          # AnalyticsOverview, TimeseriesPoint, ChannelAnalyticsSummary, NicheRow
│   │   └── models/
│   │       ├── __init__.py           # re-exporta todas as entidades
│   │       └── domain.py             # 11 entidades SQLAlchemy (ver "Modelo de dados")
│   ├── migrations/
│   │   ├── env.py                    # injeta DATABASE_URL do .env
│   │   └── versions/
│   │       └── d69d8c5c7a0e_initial_schema.py
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
│   │   │   └── MonitoramentoView.tsx # client: 3 abas (Canais, Vídeos, Melhores)
│   │   ├── runs/
│   │   │   ├── page.tsx              # server: carrega sync_runs + discovery_runs
│   │   │   └── RunsView.tsx          # client: 2 abas (Sync, Descoberta)
│   │   ├── configuracoes/
│   │   │   ├── page.tsx              # server: carrega settings
│   │   │   └── ConfiguracoesForm.tsx # client: agrupa por prefixo, salva inline
│   │   └── analytics/
│   │       ├── page.tsx              # server: carrega overview + channels + niches
│   │       └── AnalyticsView.tsx     # client: 4 cards + cartões por canal (mini-charts) + nichos
│   ├── components/
│   │   ├── Sidebar.tsx                # navegação fixa (6 itens)
│   │   ├── SettingInput.tsx           # input plain com botão Salvar (dirty-aware)
│   │   ├── SecretInput.tsx            # input password com máscara + Alterar/Remover (suporta multiline)
│   │   ├── ChannelChart.tsx           # Recharts wrapper (LineChart/BarChart + tooltip pt-BR)
│   │   ├── ChannelAvatar.tsx          # avatar circular com fallback (inicial do título)
│   │   ├── VideoThumbnail.tsx         # thumb 16:9 com fallback "sem thumb"
│   │   ├── AddByLinkInput.tsx         # input pra colar link/ID e adicionar canal/vídeo
│   │   ├── ChannelsFilterBar.tsx      # filtros+ordenação da aba Canais (client-side)
│   │   ├── VideosFilterBar.tsx        # filtros+ordenação da aba Vídeos (dropdown só na grade)
│   │   ├── SortableHeader.tsx         # <th> clicável com cicle desc/asc/default
│   │   ├── Toaster.tsx                # Context + hook useToast (success/error/info)
│   │   ├── GlobalSyncIndicator.tsx    # badge no topo que polla /api/sync/status a cada 5s
│   │   ├── Skeleton.tsx               # bloco animado (shimmer) para estados de loading
│   │   └── ErrorCard.tsx              # cartão de erro padronizado com botão "Tentar de novo"
│   ├── lib/api.ts                    # apiGet/Post/Patch/Delete + todos os tipos
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
| Regras de descoberta | [api/app/services/discovery_service.py](api/app/services/discovery_service.py), [api/app/routers/discovery.py](api/app/routers/discovery.py) |
| Regras de monitoramento/snapshots | [api/app/services/monitoring_service.py](api/app/services/monitoring_service.py), [api/app/routers/monitoring.py](api/app/routers/monitoring.py) |
| Regras de sync (scheduler + manual) | [api/app/services/sync_service.py](api/app/services/sync_service.py), [api/app/routers/sync.py](api/app/routers/sync.py) |
| Regras de analytics (agregação snapshots) | [api/app/services/analytics_service.py](api/app/services/analytics_service.py), [api/app/routers/analytics.py](api/app/routers/analytics.py) |
| **Frontend** | |
| Cliente HTTP + tipos | [web/lib/api.ts](web/lib/api.ts) |
| Layout/navegação | [web/app/layout.tsx](web/app/layout.tsx), [web/components/Sidebar.tsx](web/components/Sidebar.tsx) |
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

## Modelo de dados (MySQL — 11 tabelas + `alembic_version`)

| Tabela | Papel |
|---|---|
| `channels` | Canais conhecidos/monitorados (youtube_channel_id único, `status`=`active\|paused\|removed`, `is_active`, `source`, `thumbnail_url`) |
| `channel_snapshots` | Histórico de inscritos, views totais, `avg_vpd_recent`, deltas, `vpd_trend`, `uploads_per_week`, **`signal`** (`heating\|promising\|saturated\|stable`) + `signal_reason`. Índice `(channel_id, captured_at)` |
| `tracked_videos` | Vídeos acompanhados por canal (unique `(channel_id, youtube_video_id)`), `tracking_source` (`discovery`\|`best_from_channel`), `first_tracked_vpd`, `last_seen_*`, `thumbnail_url` |
| `video_snapshots` | Histórico de views/likes/comments/VPD/deltas por vídeo. Índice `(tracked_video_id, captured_at)` |
| `sync_runs` | Execuções de sincronização (`type`=`manual\|scheduled`, `status`=`running\|success\|partial\|failed`, contadores, notes com erros individuais) |
| `discovery_runs` | Buscas por termos (`filters_json`, contadores) |
| `discovery_results_channels` | Canais encontrados numa discovery_run (score, matched_term) |
| `discovery_results_videos` | Vídeos encontrados numa discovery_run (views, VPD, score) |
| `tags` | Tags/nichos (name unique) — **usado na Fase 6** |
| `channel_tags` | N:N canal↔tag |
| `app_settings` | Config global chave/valor tipada; `is_secret=True` → `value` cifrado com Fernet |

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
| GET | `/api/discovery/runs?limit=` | Histórico de buscas (resumo) |
| GET | `/api/discovery/runs/{id}` | Run com resultados aninhados |
| GET | `/api/monitoring/channels` | Canais + último snapshot (subs, views, deltas, last_sync) |
| POST | `/api/monitoring/channels` | Adiciona canal por `youtube_channel_id` (idempotente) |
| PATCH | `/api/monitoring/channels/{id}` | Altera `status` (`active`/`paused`/`removed`) |
| DELETE | `/api/monitoring/channels/{id}` | Remove canal + cascata (snapshots, vídeos, tags) |
| POST | `/api/monitoring/channels/{id}/snapshot` | Snapshot imediato + detecta melhor upload recente (~3 units) |
| GET | `/api/monitoring/channels/{id}/best-videos` | Lista acumulativa de melhores vídeos detectados |
| GET | `/api/monitoring/videos` | Lista vídeos monitorados com `last_seen_*` |
| POST | `/api/monitoring/videos` | Adiciona vídeo por `youtube_video_id` (cria canal dono se preciso) |
| POST | `/api/monitoring/resolve` | Recebe link/ID, devolve `{kind: channel\|video, youtube_id}`. 0 units pra ID/URL com ID; 1 unit pra handle |
| PATCH | `/api/monitoring/videos/{id}` | Altera status |
| DELETE | `/api/monitoring/videos/{id}` | Remove vídeo + cascata (snapshots) |
| POST | `/api/monitoring/videos/{id}/snapshot` | Snapshot imediato do vídeo com deltas |
| GET | `/api/sync/status` | `{interval_hours, next_run_at, last_run}` pro Dashboard |
| POST | `/api/sync/run` | Dispara sync manual síncrono (`type='manual'`) |
| GET | `/api/sync/runs?limit=` | Histórico de sync_runs (manual + scheduled) |
| GET | `/api/analytics/overview` | Contadores por `signal` do último snapshot de cada canal + vídeos acelerando |
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

17. **Gráficos no frontend**: página `/analytics` é um server component que pré-carrega `/overview`, canais e nichos em paralelo, e delega pra `AnalyticsView` (client). Cada cartão de canal dispara 5 fetches paralelos (`summary` + 4 `timeseries`) via `Promise.all`, então N canais = 5N requests. Gráficos via `ChannelChart` (Recharts `LineChart`/`BarChart` com tooltip pt-BR). Canal sem dados mostra "coletando dados…" em vez de gráfico vazio.

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

33. **Ordenação por header clicável** ([web/components/SortableHeader.tsx](web/components/SortableHeader.tsx)): nas tabelas em modo lista, clicar num `<th>` ordenável cicla 3 estados (null → desc → asc → default). Setinha (↕ inativo / ↓ desc / ↑ asc) em `var(--accent)` quando ativa. Algumas colunas têm só `descKey` (Δ Inscritos, VPD inicial, Último sync) — nesses casos o ciclo vira 2 estados (null → desc → default). No **modo grade da aba Vídeos** não há header pra clicar, então `VideosFilterBar` aceita `showSortDropdown` como prop e renderiza um `<select>` inline só nesse caso (`MonitoramentoView` passa `videoLayout === "grid"`). A seleção de coluna no header e o dropdown da grade compartilham o mesmo estado `videoFilters.sort` — alternar layout preserva a ordenação.

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

---

## Regras de ouro

- **Banco**: nenhuma alteração (CREATE/ALTER/DROP/INSERT/UPDATE/DELETE, migrações) sem autorização explícita. Dev local é aberto; prod EasyPanel requer confirmação.
- **Git commit/push/deploy**: proibido sem pedido explícito via chat. Autorização anterior não vale pra próxima execução.
- **Credenciais**: nunca commitar `.env` real. `.gitignore` cobre `**/.env` com exceção para `.env.example`. Conferir com `git check-ignore -v api/.env`.
- **Coordenação multi-IA**: ao editar `!projeto.md` ou `!executar.md`, adicionar `AGUARDE ALTERANDO` na primeira linha; remover ao terminar.
