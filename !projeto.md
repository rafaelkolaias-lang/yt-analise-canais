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

## Status atual (2026-04-26)

Em produção/local já existem:
- Descoberta manual e automática.
- Monitoramento de canais e vídeos.
- Snapshot periódico via scheduler.
- Analytics paginado com filtro de status (`Ativos`, `Pausados`, `Removidos`, `Todos`).
- Sugestões de monitoramento e remoção.
- Thumbnails/avatares na descoberta e em runs.
- Tratamento persistente de vídeos/canais indisponíveis.
- Notificações internas no canto inferior esquerdo com resumo de quota.
- Sidebar com a marca **RK Youtube Analyzer**.
- Filtro real de idade do canal na descoberta (`channel.min_age_days` / `channel.max_age_days`).
- `monitor.best_videos_sample_size` efetivamente lido do banco.
- `seed.py` com descrições didáticas e atualização de `description` em chaves já existentes.

Pontos importantes recentes:
- Os services antigos `analytics_service.py` e `suggestions_service.py` foram removidos.
- O backend ativo usa `analytics_service_v2.py` e `suggestions_service_v2.py`.
- A central de notificações já nasceu expansível: hoje mostra quota, mas a estrutura aceita novos cards.

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
│   │   │   └── sync.py
│   │   ├── schemas/
│   │   │   ├── analytics.py
│   │   │   ├── discovery.py
│   │   │   ├── monitoring.py
│   │   │   ├── notifications.py
│   │   │   ├── settings.py
│   │   │   ├── suggestions.py
│   │   │   └── sync.py
│   │   └── services/
│   │       ├── analytics_service_v2.py
│   │       ├── auto_discovery_service.py
│   │       ├── discovery_seed_terms.py
│   │       ├── discovery_service.py
│   │       ├── monitoring_service.py
│   │       ├── settings_reader.py
│   │       ├── settings_service.py
│   │       ├── suggestions_service_v2.py
│   │       ├── sync_service.py
│   │       └── youtube_client.py
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
│   │   ├── NotificationsCenter.tsx
│   │   ├── NotificationsSettings.tsx
│   │   ├── SecretInput.tsx
│   │   ├── SettingInput.tsx
│   │   ├── Sidebar.tsx
│   │   ├── Skeleton.tsx
│   │   ├── SortableHeader.tsx
│   │   ├── Toaster.tsx
│   │   ├── VideoThumbnail.tsx
│   │   └── VideosFilterBar.tsx
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
| Configuração via `.env` | `api/app/core/config.py`, `api/.env.example` |
| Banco / sessão SQLAlchemy | `api/app/core/database.py` |
| Criptografia de secrets | `api/app/core/crypto.py` |
| Scheduler / reagendamento do sync | `api/app/core/scheduler.py` |
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
| Resumo de quota para a central de notificações | `api/app/routers/notifications.py`, `api/app/schemas/notifications.py`, `api/app/services/youtube_client.py` |
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
- A central de notificações faz polling de `/api/youtube/keys/health` em background (60s) pro badge do sino refletir queimadas mesmo com painel fechado.
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
| Sync de todos os canais | `api/app/services/sync_service.py`, `api/app/routers/sync.py`, `api/app/schemas/sync.py` |
| UI de monitoramento | `web/app/monitoramento/MonitoramentoView.tsx`, `web/lib/api.ts` |
| Runs / revisão persistente da descoberta | `web/app/runs/RunsView.tsx` |

Observações atuais do monitoramento:
- `monitor.best_videos_sample_size` é lido do banco quando `snapshot_channel()` não recebe override.
- `uploads_per_week` hoje usa uploads reais do canal, não mais `TrackedVideo.first_tracked_at` como proxy.
- Vídeos indisponíveis gravam `unavailable_reason` e `unavailable_since`.
- Canais removidos vão para `status='removed'` e entram na blacklist.

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
| Componente global / popover | `web/components/NotificationsCenter.tsx` |
| Mount global | `web/app/layout.tsx` |
| Preferência de navegador | `web/components/NotificationsSettings.tsx`, `web/lib/useBrowserNotifications.ts` |
| Endpoint operacional atual | `api/app/routers/notifications.py`, `api/app/schemas/notifications.py` |

Observações:
- O sino no canto inferior esquerdo já existe.
- Hoje ele mostra **quota agregada de todas as keys**.
- A estrutura é extensível por cards independentes no array `cards` de `NotificationsCenter.tsx`.

### Layout / shell / identidade visual

| Assunto | Arquivos |
|---|---|
| Sidebar / nome do sistema | `web/components/Sidebar.tsx` |
| Shell e providers globais | `web/app/layout.tsx` |
| CSS global / responsividade | `web/app/globals.css` |

Observação:
- A sidebar já usa o nome **RK Youtube Analyzer**.

## App settings: estado atual

O `seed.py` hoje trabalha com **34 chaves** em `app_settings`.

Categorias principais:
- `sync_*`
- `search.*`
- `channel.*`
- `monitor.*`
- `analytics.*`
- `youtube.*`
- `discovery.auto_*`
- `suggestions.*`

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
- configurações: `api/app/seed.py`, `api/app/services/settings_service.py`, `web/app/configuracoes/ConfiguracoesForm.tsx`
- notificações: `web/components/NotificationsCenter.tsx`, `api/app/routers/notifications.py`, `api/app/schemas/notifications.py`

## Regra de manutenção deste arquivo

Objetivo deste mapa:
- mostrar **onde** está cada coisa;
- registrar decisões estruturais relevantes;
- evitar releitura desnecessária do projeto.

Não usar este arquivo para backlog detalhado.
Backlog e pendências ficam em `!executar.md`.
