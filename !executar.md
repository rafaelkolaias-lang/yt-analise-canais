# Plano de Execucao - youtube-analyzer

> **Sistema em producao** desde 2026-04-24 - todas as fases iniciais (0-8) +
> deploy real concluidos. Historico de entregas vive no `git log`.
>
> Use este arquivo so para **novas tarefas pendentes** (features, correcoes,
> duvidas tecnicas). Quando concluir uma, mover pra `git log` (nao acumular
> aqui).

---

## Tarefas Pendentes

## ✅ 5. Central de notificacoes interna com cota agregada do YouTube

Status: CONCLUIDO (opcao B — persistencia em app_settings, autorizada pelo usuario em 2026-04-26)

### Objetivo
Criar uma notificacao interna no site para exibir informacoes operacionais rapidas, comecando por consumo de quota da YouTube API somando todas as keys.

### Escopo
- Adicionar um icone fixo de notificacoes no canto inferior esquerdo.
- Ao clicar, abrir um painel leve estilo balao/lista com cards de informacao.
- Primeira informacao do painel:
  - quota total disponivel considerando todas as API keys cadastradas;
  - quota ja usada;
  - quota restante;
  - idealmente ultimo evento/acao que consumiu quota e quanto consumiu.
- Estruturar a UI/componente para permitir adicionar novas notificacoes no futuro sem refatoracao grande.
- Criar endpoint/servico backend para expor o resumo agregado de quota.
- Revisar o cliente do YouTube para persistir/recuperar um estado confiavel de uso agregado entre requests/processos, se necessario.

### Criterios de aceite
- O site mostra um icone de notificacoes no canto inferior esquerdo.
- O clique abre um painel funcional.
- O painel mostra a soma de consumo/restante considerando todas as keys.
- A estrutura aceita novas secoes/itens depois sem reescrever o componente.

### Possiveis armadilhas
- Hoje o contador de quota do cliente parece ser em memoria de processo; isso pode nao sobreviver a restart/deploy e pode divergir entre processos.
- Se a quota agregada nao for persistida em banco/app_settings, a notificacao pode mentir.

### Solucao aplicada (2026-04-26)
**Backend (sem migration nova; reutiliza `app_settings`)**
- `api/app/seed.py`: nova chave `youtube.quota_usage_today` (`value_type=json`,
  valor inicial `NULL`). Requer rodar `python -m app.seed` no proximo deploy
  da api (ja coberto pelo Lembrete 8).
- `api/app/services/youtube_client.py` reescrito para persistir uso agregado:
  - `build_from_db(db)` agora hidrata `used_per_key`, `last_event` e `date_utc`
    a partir de `app_settings.youtube.quota_usage_today` via
    `_load_persisted_usage()`. Aplica rollover diario UTC: se a `date_utc`
    salva for diferente de hoje, retorna vetor zerado (casa com o reset
    oficial da quota do YouTube).
  - `YouTubeClient` ganhou os campos `db: Optional[Session]`, `date_utc: str`
    e `last_event: Optional[dict]`. Tambem chama `_maybe_rollover()` antes
    de cada `_pick_key`, cobrindo o caso raro de worker longo cruzando a
    meia-noite UTC.
  - `_get(endpoint, params, event_label=None)`: apos HTTP 200 (ou apos um
    403 de quota que esgota a key), chama `_persist_state()`, que faz
    UPSERT do JSON em `app_settings`. Falha de persistencia eh engolida
    com print — a request principal nunca eh derrubada por telemetria.
  - Todos os metodos publicos (`search_videos`, `videos_by_ids`,
    `playlist_items`, `channels_by_ids`, `resolve_handle`) ganharam
    `event_label` opcional, com defaults descritivos do tipo
    `"search 'foo'"`, `"channels.list (12 ids)"`, etc., para popular
    `last_event.label` no painel.
  - `read_quota_summary(db)`: helper que devolve o resumo agregado para a UI
    sem disparar nenhuma chamada externa — soma `used_per_key`, calcula
    `total_quota = keys_count * daily_quota_per_key` e `remaining`.
- `api/app/schemas/notifications.py` (novo): `QuotaUsageEvent`, `QuotaSummary`.
- `api/app/routers/notifications.py` (novo): `GET /api/notifications/quota-summary`.
- `api/app/main.py`: registra `notifications.router`.

**Frontend**
- `web/lib/api.ts`: tipos `QuotaUsageEvent`, `QuotaSummary`.
- `web/components/NotificationsCenter.tsx` (novo): icone fixo no canto
  inferior esquerdo (`position: fixed; bottom; left;` via `.notif-root`),
  botao circular com badge colorido (warn em ≥70%, danger em ≥90%) e
  popover. Estrutura extensivel: o componente renderiza um array
  `cards: NotificationCard[] = [{ id, render }]` — adicionar uma nova
  notificacao no futuro = pushar mais um item. Hoje o array tem 1 card
  (`youtube-quota`). Painel recarrega o summary a cada 30s enquanto aberto
  e fecha com ESC ou clique fora.
- `web/app/layout.tsx`: monta `<NotificationsCenter />` dentro do
  `ToasterProvider`, fora do `app-shell`, para que o icone flutuante apareca
  em todas as telas.
- `web/app/globals.css`: bloco novo no fim com classes `.notif-root`,
  `.notif-toggle`, `.notif-badge*`, `.notif-popover*`, `.notif-card*` +
  media query mobile (≤768px) ajustando posicao/largura do popover.

**Verificacoes**
- `npx tsc --noEmit` no `web/`: sem erros.
- `python -m py_compile` nos 5 arquivos backend modificados/novos: OK.

**Deploy (importante — entra no escopo do Lembrete 8)**
- `python -m app.seed` no container da api eh **obrigatorio** apos o deploy,
  para popular a nova chave `youtube.quota_usage_today`. Sem isso, o endpoint
  ainda funciona (vai mostrar 0 used) e a primeira request bem-sucedida do
  YouTube vai criar a linha automaticamente (logica do `_persist_state`),
  mas o seed eh a forma idiomatica.

## ✅ 6. Renomear marca na sidebar para RK Youtube Analyzer

Status: CONCLUIDO

### Objetivo
Atualizar o nome exibido na barra lateral do sistema.

### Escopo
- Trocar o rotulo atual `youtube-analyzer` por `RK Youtube Analyzer`.
- Validar em desktop e mobile, se houver header/sidebar responsiva.

### Criterios de aceite
- O novo nome aparece corretamente na navegacao lateral.

### Possiveis armadilhas
- Conferir se o texto tambem existe em layout compartilhado, metadata ou header secundario.

### Solucao aplicada (2026-04-26)
- `web/components/Sidebar.tsx`: `<h1>youtube-analyzer</h1>` -> `<h1>RK Youtube Analyzer</h1>`
  (mesmo elemento usado em desktop e no drawer mobile, entao cobre os dois layouts).
- `web/app/layout.tsx`: `metadata.title` ajustado para "RK Youtube Analyzer"
  (afeta o `<title>` da aba do navegador para casar com a marca).
- Mantido sem alteracao: `package.json` / `package-lock.json` / `web/.env.example`
  ainda usam o nome tecnico `youtube-analyzer-web` — sao identificadores de
  pacote npm e do projeto, nao "marca exibida na sidebar". Renomear o package
  forcaria mexer em build/deploy sem ganho.

## ✅ 7. Filtro temporal nos graficos do Analytics por agregacao de pontos

Status: CONCLUIDO

### Objetivo
Permitir mudar a granularidade dos graficos do Analytics para facilitar leitura do historico.

### Escopo
- Adicionar opcoes de filtro nos graficos:
  - `Todos`
  - `1 dia`
  - `7 dias`
  - `30 dias`
- Regra esperada:
  - `Todos`: mostra todos os pontos/snapshots existentes;
  - `1 dia`: cada ponto representa 1 dia;
  - `7 dias`: cada ponto representa 7 dias;
  - `30 dias`: cada ponto representa 30 dias.
- Implementar agregacao por janela no backend ou no frontend com criterio consistente por periodo.
- Aplicar o filtro aos graficos de:
  - views totais
  - inscritos
  - VPD recente
  - uploads/semana

### Criterios de aceite
- O usuario consegue alternar a granularidade sem recarregar a pagina inteira.
- Os graficos mudam a quantidade de pontos de acordo com o filtro.
- `Todos` continua exibindo todos os snapshots.

### Possiveis armadilhas
- Definir bem a agregacao por janela: ultimo valor do periodo vs media do periodo.
- Para metricas cumulativas (`views_total`, `subscribers`), normalmente faz mais sentido usar o ultimo ponto do bucket.
- Para metricas derivadas (`avg_vpd_recent`, `uploads_per_week`), pode fazer mais sentido media por bucket.

### Solucao aplicada (2026-04-26)
- Agregacao feita 100% no frontend, em cima das series ja entregues pelo
  bundle paginado (`/api/analytics/channels`). Sem mudanca de contrato da API.
- `web/components/ChannelChart.tsx`:
  - Novos props `bucket: 'all'|'1d'|'7d'|'30d'` e `aggregation: 'last'|'avg'`.
  - Funcao `bucketize(points, bucketDays, aggregation)` agrupa os snapshots em
    janelas de N dias contadas para tras a partir do snapshot mais recente do
    array (nao do "agora" do cliente, pra nao gerar bucket vazio na borda).
  - `aggregation='last'`: usa o ultimo ponto do bucket (cumulativas).
  - `aggregation='avg'`: usa a media do bucket (derivadas).
  - Quando `bucket !== 'all'`, o eixo X passa a mostrar so dia/mes (sem hora),
    pra reduzir poluicao visual.
- `web/app/analytics/AnalyticsView.tsx`:
  - Estado novo `chartBucket` + cartao de filtro "Granularidade dos graficos"
    (mesmo padrao visual do filtro de status).
  - Trocar bucket nao refaz fetch — so re-renderiza os 4 graficos.
  - `views_totais` / `inscritos` -> `aggregation='last'`.
  - `vpd_recente` / `uploads/semana` -> `aggregation='avg'`.
- `npx tsc --noEmit` passa sem erros.

## ⏳ 8. Lembrete de deploy desta rodada de melhorias de Analytics/Sugestoes

Status: PENDENTE

### Objetivo
Nao esquecer os passos manuais necessarios quando for subir as melhorias novas de Analytics/Sugestoes.

### Escopo
- No deploy futuro da `api`, lembrar de rodar no console:
```bash
cd /app
python -m app.seed
```
- Motivo:
  - essa rodada adiciona novas keys de configuracao em `app_settings`;
  - nao ha migration nova, mas o `seed` precisa popular as chaves ausentes.
- No deploy do `web`, lembrar de publicar junto as mudancas da UI de Analytics e Sugestoes.

### Criterios de aceite
- Antes do deploy, esse lembrete ainda esta visivel aqui no `!executar.md`.

### Possiveis armadilhas
- Esquecer o `python -m app.seed` e depois estranhar thresholds/defaults faltando no comportamento novo.

<!--
Template de tarefa pendente:

## ⏳ N. Titulo curto

Status: PENDENTE

### Objetivo
Por que isso precisa ser feito.

### Escopo
Lista de mudancas concretas (arquivos, endpoints, telas).

### Criterios de aceite
Como saber que terminou.

### Possiveis armadilhas
O que olhar com atencao.
-->
