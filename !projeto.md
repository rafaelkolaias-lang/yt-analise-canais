# !projeto.md — RK Youtube Analyzer

> Mapa operacional do projeto para a IA localizar rapidamente onde cada regra vive, sem precisar reler o repositório inteiro.
>
> Use este arquivo como **atalho de navegação**. Para tarefas pendentes, consulte `!executar.md`.

## Resumo do sistema

Sistema web para descoberta, monitoramento, sugestões e analytics de canais do YouTube.
Objetivo principal: encontrar canais promissores, acompanhar crescimento e identificar oportunidades de réplica.

Fluxo macro:
1. **Descoberta** busca vídeos/canais com filtros.
2. **Monitoramento** adiciona canais/vídeos ao tracking e coleta snapshots.
3. **Sync** atualiza periodicamente os canais monitorados.
4. **Analytics** agrega snapshots e mostra sinais de crescimento.
5. **Sugestões** aponta canais para monitorar ou remover/pausar.
6. **Notificações** mostra informação operacional agregada no próprio site.

## Status atual (2026-04-27)

Em produção/local já existem:
- Descoberta manual e automática.
- Monitoramento de canais e vídeos.
- Snapshot periódico via scheduler.
- Analytics paginado com filtro de status (`Ativos`, `Pausados`, `Removidos`, `Todos`).
- Sugestões de monitoramento (regra simples + Canal Viral) e remoção (canal morto).
- Thumbnails/avatares na descoberta e em runs.
- Tratamento persistente de vídeos/canais indisponíveis.
- Central de notificações no canto inferior esquerdo com card vermelho de chave queimada e cards locais (sem persistência) para API offline / API atualizada.
- Sidebar com a marca **RK Youtube Analyzer**.
- Filtro real de idade do canal na descoberta (`channel.min_age_days` / `channel.max_age_days`).
- `monitor.best_videos_sample_size` efetivamente lido do banco.
- `seed.py` com descrições curtas numeradas (`1.1`, `5.2`, `7.2.3`) e atualização de `description` em chaves já existentes; tooltip "?" com explicação detalhada na UI de Configurações.
- Coluna **Observações** em Runs > Sync sem truncamento (texto inteiro com quebra de linha).
- Gerenciamento INDIVIDUAL de chaves YouTube via `YouTubeKeysManager` (add/remove/reativar com bolinha verde/amarela/vermelha por chave).
- Defaults do seed calibrados pra produção (mín. VPD 1000, duração 120s, idade canal 7–365d, saturação 200k, etc.).
- **Endpoint batch `/api/monitoring/channels/best-videos?ids=…`** (1 query SQL com `IN (...)`, limite 200 ids/request) e UI da aba "Melhores vídeos" paginada (50 canais/página).
- **Endpoint `/api/version`** com `started_at` fixo no `lifespan`. Frontend faz polling 60s — 3 falhas = card local "API offline há Xs"; mudança de `started_at` (redeploy) = card local "API atualizada — recarregue".
- **Notificação `suggestions_changed`** criada no fim de `run_sync` (após auto-discovery) quando `to_monitor` ou `to_remove` cresce desde a última rodada. Card no popover tem link "Ver sugestões →" para `/monitoramento?tab=suggestions`. Estado persistido em `notifications.last_suggestions_count`.
- **Scheduler ancorado no último `SyncRun`**: regra "próximo sync automático = `ultimo_sync.started_at + sync_interval_hours`". O job `auto_sync` é re-ancorado depois de CADA `run_sync` (manual, scheduled, partial e failed) e quando `sync_interval_hours` muda. No startup, lê o último `SyncRun` para ancorar o `IntervalTrigger` com `start_date = ultimo + intervalo` (UTC). Sem nenhum sync no banco, mantém o trigger em `now + intervalo`. Eliminada a contradição "ultimo sync agora · próximo em 15h" no dashboard.
- **Observabilidade operacional / falhas silenciosas tratadas**:
  - Helper `notifications_service.safe_system_alert(source_key, title, message, ...)` cria/atualiza notificação `type=system_alert` por área de falha (idempotente via `source_key`).
  - Source keys ativas: `ops:auto_discovery_failed`, `ops:suggestions_check_failed`, `ops:scheduler_reanchor_failed`, `ops:quota_persist_failed`, `ops:burned_key_persist_failed`.
  - `auto_discovery_service.run_auto_discovery` agora PROPAGA exceção pro caller (em vez de engolir) — o `sync_service` traduz em alerta. Skips esperados (feature off, sem orçamento, sem termos) seguem retornando `None` silenciosamente.
  - `youtube_client._decrypt_keys_from_db` levanta `APIKeyDecryptError` quando há valor salvo mas o decrypt falha (antes virava "sem chave"). Router `/api/sync/run` mapeia para HTTP 400 com mensagem específica.
  - `prints` em `youtube_client._persist_state` e `_mark_key_burned` viraram `log.warning(..., exc_info=True)` + `safe_system_alert`.
  - `safe_upsert` agora loga com `exc_info=True` (canal alternativo quando a tabela `notifications` está quebrada).
  - **Healthchecks**:
    - `GET /health/db` retorna **HTTP 503** quando o banco está inacessível (antes era 200 com JSON `{"status":"error"}`).
    - `GET /health/notifications` valida leitura da tabela `notifications`.
    - `GET /health/ops` agrega: banco, tabelas essenciais (`app_settings`, `notifications`, `sync_runs`), scheduler vivo + job registrado + `last_error()` nulo, decrypt das chaves YouTube quando há valor salvo. Retorna 503 se qualquer check falhar.
  - **Scheduler**: novo `last_error()` e `is_running()`. `reanchor()` retorna `bool` (sucesso). `start()` agora captura exceção e grava `_last_error`. `/api/sync/status` expõe `scheduler_ok` e `scheduler_error`; `DashboardSyncPanel` mostra "Agendador indisponível" em vermelho quando `scheduler_ok=false`.
  - **Frontend `NotificationsCenter`** ganhou 2 cards locais novos: `api_degraded` (versão OK + `/health/ops` em erro, com detalhe do subsistema afetado) e `notifications_unreachable` (3 falhas seguidas em `loadList`/`loadCounter`). Badge vermelho cobre os dois também.

Pontos importantes recentes:
- Os services antigos `analytics_service.py` e `suggestions_service.py` foram removidos.
- O backend ativo usa `analytics_service_v2.py` e `suggestions_service_v2.py`.
- A central de notificações é expansível por cards independentes. Hoje renderiza: cards persistidos da tabela `notifications` + cards transientes (chave queimada, API offline, API atualizada). Cota saiu da central — vive em `QuotaSidebarWidget` na sidebar.
- Termo exibido "Canal Viral" mapeia para chaves técnicas `breakout_*` (preservadas por compatibilidade — não renomear sem migration de dados).
- Pool SQLAlchemy ajustado para `pool_size=10 + max_overflow=20` (teto 30 conexões) em `api/app/core/database.py`. O default 5+10 esgotava quando a UI disparava muitas requests em paralelo (ex: aba "Best" carregando N canais simultaneamente). Não reduzir sem antes mover essa carga para endpoints batch.

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | Next.js 15, React 19, TypeScript, CSS vanilla, Recharts |
| Backend | FastAPI, SQLAlchemy 2, Pydantic v2, APScheduler |
| Banco | MySQL 8 em produção / MariaDB XAMPP em dev |
| Migrações | Alembic |
| HTTP externo | YouTube Data API v3 via `httpx` |
| Segredos | Fernet (`APP_SECRET_KEY`) |

## Estrutura principal

```text
yt-analise-canais-web/
├── api/
│   ├── app/
│   │   ├── main.py
│   │   ├── seed.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── crypto.py
│   │   │   ├── database.py
│   │   │   └── scheduler.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── domain.py
│   │   ├── routers/
│   │   │   ├── analytics.py
│   │   │   ├── discovery.py
│   │   │   ├── health.py
│   │   │   ├── monitoring.py
│   │   │   ├── notifications.py
│   │   │   ├── settings.py
│   │   │   ├── suggestions.py
│   │   │   ├── sync.py
│   │   │   └── youtube_keys.py
│   │   ├── schemas/
│   │   │   ├── analytics.py
│   │   │   ├── discovery.py
│   │   │   ├── monitoring.py
│   │   │   ├── notifications.py
│   │   │   ├── settings.py
│   │   │   ├── suggestions.py
│   │   │   ├── sync.py
│   │   │   └── youtube_keys.py
│   │   └── services/
│   │       ├── analytics_service_v2.py
│   │       ├── auto_discovery_service.py
│   │       ├── discovery_seed_terms.py
│   │       ├── discovery_service.py
│   │       ├── monitoring_service.py
│   │       ├── notifications_service.py
│   │       ├── settings_help.py
│   │       ├── settings_reader.py
│   │       ├── settings_service.py
│   │       ├── suggestions_service_v2.py
│   │       ├── sync_service.py
│   │       ├── youtube_client.py
│   │       └── youtube_keys_service.py
│   ├── migrations/
│   │   ├── env.py
│   │   └── versions/
│   ├── alembic.ini
│   ├── Dockerfile
│   └── requirements.txt
├── web/
│   ├── app/
│   │   ├── analytics/
│   │   ├── configuracoes/
│   │   ├── descoberta/
│   │   ├── monitoramento/
│   │   ├── runs/
│   │   ├── DashboardSyncPanel.tsx
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   │   ├── AddByLinkInput.tsx
│   │   ├── ChannelAvatar.tsx
│   │   ├── ChannelChart.tsx
│   │   ├── ChannelsFilterBar.tsx
│   │   ├── ErrorCard.tsx
│   │   ├── GlobalSyncIndicator.tsx
│   │   ├── HelpTooltip.tsx
│   │   ├── NotificationsCenter.tsx
│   │   ├── NotificationsSettings.tsx
│   │   ├── QuotaSidebarWidget.tsx
│   │   ├── SecretInput.tsx
│   │   ├── SettingInput.tsx
│   │   ├── Sidebar.tsx
│   │   ├── Skeleton.tsx
│   │   ├── SortableHeader.tsx
│   │   ├── Toaster.tsx
│   │   ├── VideoThumbnail.tsx
│   │   ├── VideosFilterBar.tsx
│   │   └── YouTubeKeysManager.tsx
│   ├── lib/
│   │   ├── api.ts
│   │   ├── useBrowserNotifications.ts
│   │   └── useIsMobile.ts
│   ├── Dockerfile
│   ├── next.config.ts
│   └── package.json
├── scripts/
│   ├── backfill_thumbnails.py
│   └── import_legacy.py
├── docs/
├── !executar.md
├── !projeto.md
├── README.md
├── temporary_rules.md
└── start-dev.bat
```

## Onde mexer em cada assunto

### Backend base

| Assunto | Arquivos |
|---|---|
| Bootstrap FastAPI, CORS, lifespan | `api/app/main.py` |
| Endpoint heartbeat `/api/version` (`{version, started_at}`) | `api/app/main.py` (`APP_VERSION`, `APP_STARTED_AT`, `app_version()`) |
| Healthchecks (`/health`, `/health/db`, `/health/notifications`, `/health/ops`) | `api/app/routers/health.py` |
| Configuração via `.env` | `api/app/core/config.py`, `api/.env.example` |
| Banco / sessão SQLAlchemy | `api/app/core/database.py` |
| Criptografia de secrets | `api/app/core/crypto.py` |
| Scheduler / reagendamento + saúde (`is_running`, `last_error`) | `api/app/core/scheduler.py` |
| Models / schema real do banco | `api/app/models/domain.py` |
| Migrações | `api/migrations/env.py`, `api/migrations/versions/*` |
| Seed / defaults de `app_settings` | `api/app/seed.py` |
| Leitura interna tipada de settings | `api/app/services/settings_reader.py` |
| API pública de configurações | `api/app/services/settings_service.py`, `api/app/routers/settings.py` |
| Textos longos (tooltip "?") das settings | `api/app/services/settings_help.py` |
| Tooltip "?" da UI de configurações | `web/components/HelpTooltip.tsx`, `web/app/configuracoes/ConfiguracoesForm.tsx` |

Observações atuais das settings/UI de configurações:
- `description` em `app_settings` é o texto CURTO, prefixado com numeração (ex: `5.2 — ...`). É o que aparece ao lado do campo. Definido em `seed.py`.
- `help` é o texto LONGO didático, exibido no tooltip do "?". Mora em código (`settings_help.py`), não no banco — evita migration por mudança puramente textual. Endpoint `/api/settings` mistura os dois antes de devolver.
- Numeração da UI (1., 2., 3., …) é calculada na ordem de exibição em `ConfiguracoesForm.tsx`. Os textos referenciam outros itens pelo número (ex: "ver 4.2"). Manter `seed.py`/`settings_help.py` coerentes com a ordem das `SECTIONS` no frontend.

### YouTube API / quota / chaves

| Assunto | Arquivos |
|---|---|
| Cliente YouTube, rotação de keys, persistência de quota | `api/app/services/youtube_client.py` |
| Gerenciamento individual de chaves (add/remove/unburn) | `api/app/services/youtube_keys_service.py`, `api/app/routers/youtube_keys.py`, `api/app/schemas/youtube_keys.py` |
| Resumo de quota para o `QuotaSidebarWidget` (`GET /api/notifications/quota-summary`) | `api/app/routers/notifications.py`, `api/app/schemas/notifications.py`, `api/app/services/youtube_client.py` |
| UI de chaves (verde/amarelo/vermelho + add/remove/reativar) | `web/components/YouTubeKeysManager.tsx` (renderizado dentro da seção 8 em `web/app/configuracoes/ConfiguracoesForm.tsx`) |

Observações atuais da quota e chaves:
- Identidade da chave = `fingerprint` (SHA-256[:16]). Estável e não vaza segredo.
- Persistência em `app_settings.youtube.quota_usage_today` usa `used_by_fingerprint: {fp: int}` (formato legado `used_per_key: [int]` ainda é lido por compat).
- `_persist_state()` faz merge aditivo sob `SELECT ... FOR UPDATE` — concorrência entre processos não perde consumo.
- Lista de chaves QUEIMADAS (HTTP 400 keyInvalid) vive em `app_settings.youtube.api_keys_burned` (JSON não cifrado, indexado por fp). `youtube_client._get` marca queimada e segue rotacionando em vez de explodir.
- Endpoints REST por fingerprint:
  - `GET /api/youtube/keys` → lista com status `ok|quota_exhausted|burned`.
  - `POST /api/youtube/keys` → adiciona (idempotente).
  - `DELETE /api/youtube/keys/{fp}` → remove (limpa também a marca de queimada).
  - `POST /api/youtube/keys/{fp}/unburn` → reativa sem teste; queima de novo se ainda estiver inválida.
  - `GET /api/youtube/keys/health` → resumo `{total, ok, quota_exhausted, burned, last_burned_at}`. Usado pela central de notificações pra mostrar card vermelho quando há queimada.
- A central de notificações faz polling de `/api/youtube/keys/health` em background (60s); o badge do sino fica vermelho e o popover mostra card vermelho quando há chave queimada, mesmo com painel fechado.
- `youtube.api_keys`, `youtube.api_keys_burned` e `youtube.quota_usage_today` ficam ESCONDIDAS do form genérico de Configurações via `INTERNAL_KEYS` em `ConfiguracoesForm.tsx` — chaves aparecem só via `YouTubeKeysManager`.

### Descoberta

| Assunto | Arquivos |
|---|---|
| Regras da descoberta manual | `api/app/services/discovery_service.py`, `api/app/routers/discovery.py`, `api/app/schemas/discovery.py` |
| Defaults da busca | `api/app/services/discovery_service.py`, `api/app/seed.py` |
| Descoberta automática | `api/app/services/auto_discovery_service.py` |
| Termos seed da auto-discovery | `api/app/services/discovery_seed_terms.py` |
| UI da descoberta | `web/app/descoberta/DescobertaForm.tsx`, `web/lib/api.ts` |
| Thumb/avatar na descoberta | `web/components/ChannelAvatar.tsx`, `web/components/VideoThumbnail.tsx` |

Observações atuais da descoberta:
- `channel.min_age_days` e `channel.max_age_days` filtram canal por idade real na descoberta manual e automática.
- `thumbnail_url` já é persistido em `discovery_results_channels` e `discovery_results_videos`.
- A blacklist é respeitada para não redescobrir canal removido.

### Monitoramento / snapshots

| Assunto | Arquivos |
|---|---|
| Regras de canal/vídeo monitorado | `api/app/services/monitoring_service.py`, `api/app/routers/monitoring.py`, `api/app/schemas/monitoring.py` |
| Best videos por canal (singular) | `monitoring_service.list_best_videos_for_channel`, `GET /api/monitoring/channels/{id}/best-videos` |
| Best videos em LOTE | `monitoring_service.list_best_videos_for_channels`, `GET /api/monitoring/channels/best-videos?ids=1,2,3` (limite `BEST_VIDEOS_BATCH_MAX_IDS=200`) |
| Sync de todos os canais | `api/app/services/sync_service.py`, `api/app/routers/sync.py`, `api/app/schemas/sync.py` |
| Detecção de "sugestões mudaram" pós-sync | `sync_service._check_suggestions_changed` (chamado depois da auto-discovery) |
| UI de monitoramento | `web/app/monitoramento/MonitoramentoView.tsx`, `web/lib/api.ts` |
| Runs / revisão persistente da descoberta | `web/app/runs/RunsView.tsx` |

Observações atuais do monitoramento:
- `monitor.best_videos_sample_size` é lido do banco quando `snapshot_channel()` não recebe override.
- `uploads_per_week` hoje usa uploads reais do canal, não mais `TrackedVideo.first_tracked_at` como proxy.
- Vídeos indisponíveis gravam `unavailable_reason` e `unavailable_since`.
- Canais removidos vão para `status='removed'` e entram na blacklist.
- Aba "Melhores vídeos" do `MonitoramentoView` é PAGINADA (50 canais/página) e cada troca de página faz UMA request batch ao endpoint plural. O endpoint singular só é usado quando atualizamos um canal específico após snapshot manual.
- `MonitoramentoView` aceita deep-link `?tab=channels|videos|best|suggestions`. A central de notificações usa `?tab=suggestions` para o link "Ver sugestões →" do card `suggestions_changed`.
- O scheduler é re-ancorado pelo `sync_service` ao final de cada `run_sync` (sucesso, partial, failed). A próxima execução automática SEMPRE cai em `started_at + sync_interval_hours` em vez do horário em que o processo subiu — vale tanto para sync manual quanto agendado.

### Sugestões

| Assunto | Arquivos |
|---|---|
| Lógica ativa de sugestões | `api/app/services/suggestions_service_v2.py`, `api/app/routers/suggestions.py`, `api/app/schemas/suggestions.py` |
| UI da aba Sugestões | `web/app/monitoramento/MonitoramentoView.tsx` |
| Settings `suggestions.*` | `api/app/seed.py`, `web/app/configuracoes/ConfiguracoesForm.tsx` |

Regras atuais de sugestões:
- `to-monitor`: canais descobertos, ainda não monitorados, com critérios de VPD/idade/blacklist.
- `to-remove`: canais ativos com sinais de canal morto.
- Há suporte para Canal Viral nas sugestões via settings `suggestions.monitor_breakout_*` (chaves de settings mantêm o nome `breakout_*` por compatibilidade; o termo exibido na UI é "Canal Viral").

### Analytics

| Assunto | Arquivos |
|---|---|
| Lógica ativa de analytics | `api/app/services/analytics_service_v2.py`, `api/app/routers/analytics.py`, `api/app/schemas/analytics.py` |
| UI do Analytics | `web/app/analytics/AnalyticsView.tsx`, `web/components/ChannelChart.tsx`, `web/lib/api.ts` |

O Analytics ativo já contempla:
- filtro por status de canal (`active`, `paused`, `removed`, `all`);
- overview paginado + lista paginada de canais;
- séries temporais por canal;
- `median_recent_views`;
- crescimento em 7d, 30d e 90d;
- consistência de crescimento;
- Canal Viral (campos `breakout_candidate`, `breakout_reason` mantidos por compat; UI exibe "Canal Viral");
- `niches()` coerente com canais que realmente têm snapshot.

### Notificações internas

| Assunto | Arquivos |
|---|---|
| Tabela e model de notificações persistentes | `api/app/models/domain.py` (`Notification`), migration `a1c5e9d8b3f0_add_notifications_table.py` |
| Service (CRUD + cap FIFO + `safe_upsert` + `safe_system_alert`) | `api/app/services/notifications_service.py` |
| Endpoints persistidos + `quota-summary` (feed do widget da sidebar) | `api/app/routers/notifications.py`, `api/app/schemas/notifications.py` |
| Componente global / popover | `web/components/NotificationsCenter.tsx` |
| Widget de cota fixo na sidebar | `web/components/QuotaSidebarWidget.tsx` (renderizado em `web/components/Sidebar.tsx`) |
| Mount global | `web/app/layout.tsx` |
| Preferência de navegador | `web/components/NotificationsSettings.tsx`, `web/lib/useBrowserNotifications.ts` |
| Endpoint saúde das chaves | `api/app/routers/youtube_keys.py` (`GET /api/youtube/keys/health`) |
| Heartbeat de versão (offline/redeploy) | `api/app/main.py` (`/api/version`); polling no `NotificationsCenter.tsx` |
| Detecção "sugestões mudaram" | `api/app/services/sync_service.py::_check_suggestions_changed` |

Observações (estado atual após Fases 1–5):
- **Sistema persistente** em tabela `notifications`. Cada row = um EVENTO histórico (não estado).
- Model `Notification` em `api/app/models/domain.py` tem índices `ix_notifications_dismissed_created` (lista visível ordenada) e `ix_notifications_source_key` (lookup do upsert). Campo `metadata_json` é JSON livre lido pelo frontend (ex: link de destino, ids).
- Tipos: `task_progress`, `task_done`, `task_error`, `system_alert`, `suggestions_changed`.
- `source_key` permite atualizar a MESMA notificação durante a execução em vez de empilhar (ex: sync manual atualiza progresso na mesma row).
- Cap FIFO de **20 não-dispensadas** — ao criar a 21ª, a mais antiga é auto-dispensada (não deletada — auditoria preservada).
- Endpoints: `GET /api/notifications` (lista + unread_count), `GET /api/notifications/unread-count`, `POST /{id}/read`, `POST /read-all`, `POST /{id}/dismiss`, `POST /dismiss-all`. `GET /api/notifications/quota-summary` mantido (consumido pelo widget da sidebar).
- Sync manual sempre cria card de progresso. Sync agendado: silencioso quando `success`, cria card só em `partial`/`failed`.
- Polling no popover: counter a cada 30s (badge sempre atualizado), lista a cada 10s quando popover aberto, health a cada 60s em background, **`/api/version` a cada 60s em background**.
- Badge prioriza: **vermelho** (chave queimada > 0 OU API offline) > **azul** (notificações não-lidas > 0 OU redeploy detectado). Cota não influencia o badge.
- **Cota da YouTube API**: vive em `QuotaSidebarWidget` (sidebar esquerda, sempre visível). Polling a cada 60s + botão ⟳ de refresh manual.
- **Cards transientes** no popover (estado, não evento; não persistem): chave queimada, **API offline** (3 falhas seguidas em `/api/version`), **API atualizada** (`started_at` mudou desde a primeira leitura na sessão — botão "Recarregar agora").
- Cards locais existem só em `useState`. `started_at` da primeira leitura é guardado em `sessionStorage` (chave `app.api.startedAt`).
- `suggestions_changed`: criado por `sync_service._check_suggestions_changed` no fim de `run_sync` (após auto-discovery), comparando contagens atuais com `app_settings.notifications.last_suggestions_count`. Se `to_monitor` ou `to_remove` cresce, cria notificação `type=suggestions_changed` com link "Ver sugestões →" para `/monitoramento?tab=suggestions`.
- Cap 20 e cleanup: não há cleanup automático de rows dismissed; auditoria fica até intervenção manual.

### Layout / shell / identidade visual

| Assunto | Arquivos |
|---|---|
| Sidebar / nome do sistema | `web/components/Sidebar.tsx` |
| Shell e providers globais | `web/app/layout.tsx` |
| CSS global / responsividade | `web/app/globals.css` |

Observações:
- A sidebar já usa o nome **RK Youtube Analyzer** e renderiza `QuotaSidebarWidget` no rodapé.
- Convenções de classe CSS em `globals.css`: prefixo `.notif-*` para a central de notificações (`notif-root`, `notif-toggle`, `notif-badge`, `notif-popover`, `notif-card`, `notif-card-title`, `notif-popover-header/body`, variantes `notif-badge-info|warn|danger`, `notif-perm-*`); prefixo `.quota-widget-*` para o widget de cota na sidebar (`quota-widget`, `-header`, `-refresh`, `-bar`, `-bar-fill`, `-numbers`, `-pct`, `-foot`, `-empty`, `-loading`, `-error`). Reutilizar essas classes em mudanças novas em vez de inventar.

## App settings: estado atual

O `seed.py` hoje trabalha com **36 chaves** em `app_settings`.

Categorias principais:
- `sync_*`
- `search.*`
- `channel.*`
- `monitor.*`
- `analytics.*`
- `youtube.*` (inclui as 4 chaves internas: `api_keys`, `api_key_daily_quota`, `quota_usage_today`, `api_keys_burned`)
- `discovery.auto_*`
- `suggestions.*`
- `notifications.*` (interna)

Chaves INTERNAS (escondidas da UI genérica via `INTERNAL_KEYS` em `ConfiguracoesForm.tsx`):
- `youtube.api_keys` — gerenciada por `YouTubeKeysManager`.
- `youtube.api_keys_burned` — estado interno de queimadas, manipulado por `youtube_client` e `YouTubeKeysManager`.
- `youtube.quota_usage_today` — estado interno de consumo, escrito pelo `youtube_client`.
- `notifications.last_suggestions_count` — JSON `{to_monitor, to_remove}` escrito por `sync_service._check_suggestions_changed`. Comparação com a rodada anterior decide se cria notificação `suggestions_changed`.

Comportamento importante do seed:
- se a chave não existe: insere;
- se a chave já existe: preserva `value` e `value_type`, mas atualiza `description`.

Sempre que subir mudança de settings/descrições na API, lembrar:

```bash
cd /app
python -m app.seed
```

## Migrações importantes

Migrations atuais no projeto:
- `d69d8c5c7a0e_initial_schema.py`
- `59b9687df885_add_thumbnail_urls.py`
- `56a880b51364_add_blacklist_and_review_state.py`
- `d6df02f56387_add_channel_published_at.py`
- `1f7c9e4b2d11_add_discovery_thumbnails_and_video_unavailable.py`
- `a1c5e9d8b3f0_add_notifications_table.py`

Lembrete operacional de produção:

```bash
cd /app
alembic upgrade head
python -m app.seed
```

## Frontend: leitura rápida por tela

| Tela | Arquivos principais |
|---|---|
| Dashboard | `web/app/page.tsx`, `web/app/DashboardSyncPanel.tsx` |
| Descoberta | `web/app/descoberta/page.tsx`, `web/app/descoberta/DescobertaForm.tsx` |
| Monitoramento | `web/app/monitoramento/page.tsx`, `web/app/monitoramento/MonitoramentoView.tsx` |
| Runs | `web/app/runs/page.tsx`, `web/app/runs/RunsView.tsx` |
| Configurações | `web/app/configuracoes/page.tsx`, `web/app/configuracoes/ConfiguracoesForm.tsx` |
| Analytics | `web/app/analytics/page.tsx`, `web/app/analytics/AnalyticsView.tsx` |

## Scripts utilitários

| Script | Função |
|---|---|
| `scripts/import_legacy.py` | importa dados do projeto desktop antigo |
| `scripts/backfill_thumbnails.py` | backfill de thumbs em lote |

## Deploy / produção

Serviços EasyPanel:
- `youtube-analyzer-api`
- `youtube-analyzer-web`
- `youtube-analyzer-banco`

O projeto usa webhook manual de deploy salvo em `temporary_rules.md`.
Não expor webhook em resposta pública.

Checklist padrão depois de subir a API:
1. abrir o console do serviço `youtube-analyzer-api`;
2. rodar `alembic upgrade head` se houve migration nova;
3. rodar `python -m app.seed` quando houve mudança de settings/descrições.

## Armadilhas importantes

- `APP_SECRET_KEY` perdida torna secrets antigos irrecuperáveis.
- `NEXT_PUBLIC_API_URL` é lida em build time no frontend.
- O host interno do banco do EasyPanel não resolve fora da rede do EasyPanel.
- A central de notificações do site não usa push real; hoje é UI interna com polling do backend.
- `GlobalSyncIndicator` faz polling periódico de `/api/sync/status`.
- O frontend principal usa `api.ts` como contrato central; mudanças de schema pedem ajuste ali.
- Se mexer em Analytics ou Sugestões, use os arquivos `_v2`, não tente recriar os antigos.

## Arquivos que normalmente devem ser lidos antes de alterar algo

Leitura mínima recomendada por área:
- descoberta: `api/app/services/discovery_service.py`, `api/app/routers/discovery.py`, `web/app/descoberta/DescobertaForm.tsx`, `web/lib/api.ts`
- monitoramento: `api/app/services/monitoring_service.py`, `api/app/routers/monitoring.py`, `web/app/monitoramento/MonitoramentoView.tsx`, `web/lib/api.ts`
- sync: `api/app/services/sync_service.py`, `api/app/core/scheduler.py`, `api/app/routers/sync.py`
- analytics: `api/app/services/analytics_service_v2.py`, `api/app/routers/analytics.py`, `web/app/analytics/AnalyticsView.tsx`, `web/lib/api.ts`
- sugestões: `api/app/services/suggestions_service_v2.py`, `api/app/routers/suggestions.py`, `web/app/monitoramento/MonitoramentoView.tsx`
- configurações: `api/app/seed.py`, `api/app/services/settings_service.py`, `api/app/services/settings_help.py`, `web/app/configuracoes/ConfiguracoesForm.tsx`, `web/components/HelpTooltip.tsx`
- chaves YouTube (gerenciamento individual): `api/app/services/youtube_keys_service.py`, `api/app/routers/youtube_keys.py`, `api/app/services/youtube_client.py`, `web/components/YouTubeKeysManager.tsx`
- notificações: `web/components/NotificationsCenter.tsx`, `api/app/routers/notifications.py`, `api/app/schemas/notifications.py`, `api/app/routers/youtube_keys.py` (endpoint /health)

## Regra de manutenção deste arquivo

Objetivo deste mapa:
- mostrar **onde** está cada coisa;
- registrar decisões estruturais relevantes;
- evitar releitura desnecessária do projeto.

Não usar este arquivo para backlog detalhado.
Backlog e pendências ficam em `!executar.md`.
