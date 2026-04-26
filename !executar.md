# Plano de Execu√ß√£o ‚Äî youtube-analyzer

> **Sistema em produ√ß√£o** desde 2026-04-24 ‚Äî todas as fases iniciais (0‚Äì8) +
> deploy real conclu√≠dos. Hist√≥rico de entregas vive no `git log`.
>
> Use este arquivo s√≥ para **novas tarefas pendentes** (features, corre√ß√µes,
> d√≠vidas t√©cnicas). Quando concluir uma, mover pra `git log` (n√£o acumular
> aqui).

---

## Tarefas Pendentes


## ‚úÖ 1. Configura√ß√£o clic√°vel para ligar/desligar descoberta autom√°tica p√≥s-sync

Status: CONCLU√çDO

### Solu√ß√£o aplicada
- `[web/components/SettingInput.tsx](web/components/SettingInput.tsx)` agora
  detecta `valueType === "bool"` e renderiza um **toggle switch clic√°vel**
  (`role="switch"`, `aria-checked`, label "Ligado/Desligado") em vez do input
  texto. O toggle salva imediatamente ao clique (`"true"` / `"false"`) e
  reverte o estado visual se o `onSave` falhar.
- A setting j√° existia (`discovery.auto_enabled`, `value_type='bool'`,
  default `true`) e o backend j√° lia via `settings_reader.get_bool` ‚Äî
  nenhuma migration necess√°ria.
- `auto_discovery_service.run_auto_discovery` j√° respeita a flag
  ([api/app/services/auto_discovery_service.py:189](api/app/services/auto_discovery_service.py#L189)).

## ? 2. Mostrar thumbnail de vÌdeos e Ìcone de canais na Descoberta

Status: CONCLUÕDO

### SoluÁ„o aplicada
- **Backend / schema**: migration [`api/migrations/versions/1f7c9e4b2d11_add_discovery_thumbnails_and_video_unavailable.py`](api/migrations/versions/1f7c9e4b2d11_add_discovery_thumbnails_and_video_unavailable.py) adicionou `thumbnail_url` em `discovery_results_channels` e `discovery_results_videos`.
- **PersistÍncia da descoberta**: [`api/app/services/discovery_service.py`](api/app/services/discovery_service.py) agora grava thumbnail de canal via `pick_thumbnail(snippet)` e thumbnail de vÌdeo via `pick_thumbnail(snippet)` com fallback previsÌvel `i.ytimg.com/vi/.../hqdefault.jpg`.
- **Schemas / payloads**: [`api/app/schemas/discovery.py`](api/app/schemas/discovery.py) e [`web/lib/api.ts`](web/lib/api.ts) passaram a expor `thumbnail_url` em resultados de canais e vÌdeos.
- **Frontend**: [`web/app/descoberta/DescobertaForm.tsx`](web/app/descoberta/DescobertaForm.tsx) passou a reaproveitar [`web/components/VideoThumbnail.tsx`](web/components/VideoThumbnail.tsx) e [`web/components/ChannelAvatar.tsx`](web/components/ChannelAvatar.tsx) para renderizar os visuais na prÛpria tabela de resultados.
- **Fallback**: canal sem imagem continua com avatar por inicial; vÌdeo sem imagem cai no placeholder do componente ou no fallback previsÌvel do YouTube, sem quebrar a UI.

## ? 3. Tratar vÌdeos e canais removidos do YouTube com contexto e sem gerar partial recorrente

Status: CONCLUÕDO

### SoluÁ„o aplicada
- **PersistÍncia nova para vÌdeo indisponÌvel**: a mesma migration `1f7c9e4b2d11` adicionou `tracked_videos.unavailable_reason` e `tracked_videos.unavailable_since`.
- **Canais removidos**: [`api/app/services/monitoring_service.py`](api/app/services/monitoring_service.py) agora trata `channels.list` vazio como indisponibilidade permanente, marca o canal com `status="removed"`, `is_active=false`, preenche `notes` com contexto audit·vel (`canal`, `url`, `id`, motivo) e inclui o `youtube_channel_id` na blacklist para ele n„o voltar por descoberta/sugestıes.
- **VÌdeos removidos**: quando `videos.list` n„o retorna o vÌdeo monitorado, o serviÁo marca `TrackedVideo.status="removed"`, grava `unavailable_reason` e `unavailable_since`, e preserva contexto do canal dono / URL / ID na mensagem tratada.
- **Sync sem partial recorrente**: [`api/app/services/sync_service.py`](api/app/services/sync_service.py) passou a diferenciar indisponibilidade permanente de erro transitÛrio. Itens j· classificados como removidos entram sÛ como nota informativa no `SyncRun.notes`; n„o contaminam mais o status para `partial`.
- **Monitoramento / API**: [`api/app/routers/monitoring.py`](api/app/routers/monitoring.py), [`api/app/schemas/monitoring.py`](api/app/schemas/monitoring.py) e [`web/lib/api.ts`](web/lib/api.ts) passaram a expor `notes`, `unavailable_reason`, `unavailable_since`, `channel_title` e `channel_url`. A UI de [`web/app/monitoramento/MonitoramentoView.tsx`](web/app/monitoramento/MonitoramentoView.tsx) agora mostra esse contexto em canais/vÌdeos removidos.
- **ValidaÁ„o local**: `python -m py_compile` passou nos arquivos alterados, `npm run build` do frontend passou e `alembic upgrade head` foi aplicado no dev local atÈ a revision `1f7c9e4b2d11`.

## ‚úÖ 4. Filtro claro de status na aba Analytics com padr√£o em ativos

Status: CONCLU√çDO

### Solu√ß√£o aplicada
- **Backend** (filtro feito no banco, n√£o client-side):
  - `analytics_service.overview(db, status=...)` e
    `analytics_service.channels_paginated(..., status=...)` agora aceitam
    `status` (`active`/`paused`/`removed`/`all`). Filtragem central em
    `_filter_channel_ids_by_status` ‚Äî overview e listagem aplicam a mesma
    regra (consist√™ncia).
  - Routers `GET /api/analytics/overview` e `GET /api/analytics/channels`
    ganharam `status` query (`Query(..., pattern=...)`), default `active`.
- **Frontend**:
  - `web/app/analytics/page.tsx` parou de fazer SSR do overview (depende do
    filtro). Apenas `niches` continua server-side.
  - `web/app/analytics/AnalyticsView.tsx` ganhou `statusFilter` (default
    `active`), barra de tabs (`Ativos / Pausados / Removidos / Todos`) e o
    `useEffect` agora busca `overview` e `channels` em paralelo passando
    `status` na query. Trocar de filtro reseta para a p√°gina 1.
  - Empty state diferenciado: "Nenhum canal ativo" vs "Nenhum canal
    corresponde ao filtro selecionado".
- **Sem migration** ‚Äî `Channel.status` j√° existe (`active`/`paused`/`removed`).

<!--
Template de tarefa pendente:

## ‚è≥ N. T√≠tulo curto

Status: PENDENTE

### Objetivo
Por que isso precisa ser feito.

### Escopo
Lista de mudan√ßas concretas (arquivos, endpoints, telas).

### Crit√©rios de aceite
Como saber que terminou.

### Poss√≠veis armadilhas
O que olhar com aten√ß√£o.
-->

