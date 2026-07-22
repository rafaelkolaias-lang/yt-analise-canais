# Plano de Execucao - youtube-analyzer

> Use este arquivo so para tarefas pendentes.
> Quando uma tarefa for concluida, remover daqui.

---

## ✅ 5. Sugestões: página própria + candidatos em observação automática

Status: CONCLUÍDO (Claude 1, 22/07/2026 — aguardando deploy api+web e `python -m app.seed`)

Solicitacao:
- "Sugestões" vira item proprio na sidebar (abaixo de Monitoramento).
- As top sugestoes devem ser observadas automaticamente pelo sistema (snapshots de VPD) para ganhar/perder pontuacao com o tempo, ate o usuario decidir Monitorar ou Dispensar (botao novo).

Solução aplicada (opcao A escolhida pelo usuario — reuso do sync):
- Canal sugerido vira row em `channels` com `status="candidate"` (sem migration): o sync de 12h ja snapshotta; escondido de Monitoramento (`list_channels`) e Analytics (`_channel_query`).
- `suggestion_candidates_service.py`: auto-add das top sugestoes pos-sync ate o teto (`suggestions.max_candidates`=10, liga/desliga em `suggestions.auto_candidates_enabled` — seeds novos), com snapshot imediato de baseline; `list_candidates` (evolucao VPD primeiro vs ultimo snapshot, ordenado por crescimento), `promote` (→active), `dismiss` (delete+blacklist `suggestion_dismissed`), `dismiss_suggestion` (blacklist direto pra sugestao nao-candidata).
- Endpoints: GET `/api/suggestions/candidates`, POST `/candidates/{id}/promote`, POST `/candidates/{id}/dismiss`, POST `/api/suggestions/dismiss`.
- Web: pagina `/sugestoes` (`SugestoesView.tsx`: secao "Em observação automática" com VPD inicial/atual/evolucao% + Monitorar/Dispensar; listas "para monitorar" com Dispensar novo e "mortos"); item "Sugestões" na sidebar; aba antiga removida do Monitoramento (`?tab=suggestions` redireciona); link da central aponta pra `/sugestoes`.
- Validado: compileall + import OK, `npm run build` OK.
- Deploy: api + web + `python -m app.seed` (2 settings novas). Sem migration.

## ✅ 3. Sistema de login nativo (site + API + app Windows)

Status: CONCLUÍDO (Claude 1, 22/07/2026 — aguardando deploy: migration + seed)

Solicitacao:
- Proteger o site e a API com login proprio (opcao B escolhida pelo usuario; sem modelo cronometro-web).
- O programa do Windows tambem loga, mas salva o login no PC para nao pedir toda hora.

Solução aplicada:
- Migration `c9d1e3f5a7b2`: tabelas `users` e `auth_sessions` (token opaco com SHA-256 no banco; sessao web=30d, desktop=365d).
- `api/app/core/security.py` (PBKDF2 stdlib) + `api/app/services/auth_service.py` + `api/app/routers/auth.py` (`/api/auth/login|logout|me|change-password`).
- Protecao global por Bearer em `main.py` (`core/auth.require_auth`); abertas só `/`, `/api/version`, `/health*`, `/api/auth/login`.
- `python -m app.seed` cria `admin`/`admin` se nao houver usuarios (TROCAR a senha em Configuracoes).
- Web: `/login` (fora do shell via `AppShell`), token em localStorage+cookie (`lib/authToken.ts`), Bearer automatico + redirect em 401 (`lib/api.ts`), SSR via `lib/serverApi.ts`, guard de paginas em `web/middleware.ts`, logout na sidebar, card de troca de senha em Configuracoes.
- Validado: `compileall` OK, `npm run build` OK.

## ✅ 4. Alerta de pico de views por canal (multiplicador) + programa Windows

Status: CONCLUÍDO (Claude 1, 22/07/2026 — aguardando deploy: migration + seed)

Solicitacao:
- Por canal: ligar/desligar alerta e definir multiplicador (ex.: 1.5x, 2x, 3x) manualmente.
- Regra: ganho de views das ultimas 24h >= multiplicador x media diaria dos 7 dias anteriores do proprio canal.
- Notificacao na central do site + notificacao de navegador; programa do Windows (popup custom) para quando nao estiver no site — popup clicavel abre o Analytics direto no canal.

Solução aplicada:
- Migration `f4a6b8c0d2e4`: colunas `spike_alert_enabled` / `spike_alert_multiplier` (default 2.0) / `spike_last_alert_at` em `channels`.
- `api/app/services/spike_alert_service.py`: regra 24h vs media 7d (tolerancia 12–48h no ponto de 24h, span minimo 3d, piso 100 views/dia, cooldown 24h). Chamado por canal dentro do `run_sync` (tolerante a falha).
- Notification `type=view_spike` com `metadata.link=/analytics?q=<canal>`; endpoint `PATCH /api/monitoring/channels/{id}/spike-alert`.
- Web: `SpikeAlertControl` (sino + multiplicador) na tabela e nos cards mobile do Monitoramento; card "Ver no Analytics →" na central; notificacao de navegador para picos novos (polling de fundo no `NotificationsCenter`); `/analytics?q=` pre-preenche a busca.
- Programa Windows: `windows-notifier/notifier.py` (stdlib puro: popup tkinter custom canto inferior direito, clique abre o Analytics no canal, login salvo em `%APPDATA%\RK-YT-Notifier\config.json`, polling 60s, ancora `last_seen_id`). `iniciar-notificador.bat` + `README.md` com autostart opcional.
- Validado: `compileall` OK (api + notifier), `npm run build` OK.

## ✅ 1. Criar Analytics de videos monitorados organizado por canal

Status: CONCLUÍDO

Solução aplicada:
- Backend: função `videos_by_channel` em `analytics_service_v2.py` — busca canais paginados, depois vídeos e snapshots em lote (sem N+1), monta séries temporais de VPD e views por vídeo.
- Backend: schemas `VideoAnalyticsItem`, `ChannelBasicWithStatus`, `ChannelVideoBundle`, `PaginatedVideosByChannel` em `schemas/analytics.py`.
- Backend: endpoint `GET /api/analytics/videos-by-channel?page&page_size&channel_status` em `routers/analytics.py` (máximo 20 canais/página).
- Frontend: tipos correspondentes adicionados em `web/lib/api.ts`.
- Frontend: novo componente `web/components/VideosByChannelView.tsx` — lista canais colapsáveis com vídeos ordenados por VPD desc; cada vídeo tem botão "gráficos" que expande mini-charts de VPD e Views usando `ChannelChart`; filtro de status e granularidade de bucket; paginação.
- Frontend: `AnalyticsView.tsx` ganhou aba "Canais" / "Vídeos por canal" no topo. Aba de canais preservada sem alteração. Aba de vídeos renderiza `<VideosByChannelView />`.
- Build backend (`python -m compileall`) e frontend (`npm run build`) passaram sem erros.

Solicitacao:
- Os videos monitorados parecem perder contexto/informacoes anteriores a cada rerun/sync.
- Criar uma area de Analytics para videos monitorados, organizada por canal.
- A ideia e mostrar os videos de cada canal com historico em grafico, porque um video pode estar melhor em uma rodada e outro video pode passar a performar melhor depois.

Objetivo:
- Permitir analisar a evolucao dos videos monitorados ao longo do tempo sem depender apenas do "melhor video atual".
- Mostrar, por canal, quais videos foram monitorados, como evoluiram e quando trocaram de posicao/desempenho.
- Evitar a impressao de que o sistema perdeu informacao quando, na verdade, ele pode estar recalculando o ranking com base no snapshot mais recente.

Arquivos provaveis:
- Backend:
  - `api/app/models/domain.py` (`TrackedVideo`, `VideoSnapshot`, `Channel`)
  - `api/app/services/analytics_service_v2.py`
  - `api/app/routers/analytics.py`
  - `api/app/schemas/analytics.py`
- Frontend:
  - `web/app/analytics/AnalyticsView.tsx` ou nova aba/componente dentro de Analytics
  - `web/components/ChannelChart.tsx` ou novo componente de grafico para videos
  - `web/lib/api.ts`

Leitura minima antes de implementar:
- `api/app/models/domain.py`
- `api/app/services/analytics_service_v2.py`
- `api/app/routers/analytics.py`
- `api/app/schemas/analytics.py`
- `web/app/analytics/AnalyticsView.tsx`
- `web/lib/api.ts`

Comportamento desejado:
1. Nova visao/aba no Analytics:
   - Nome sugerido: "Videos por canal" ou "Videos monitorados".
   - Manter a tela atual de Analytics de canais.
   - Adicionar uma aba/controle para alternar entre "Canais" e "Videos por canal".

2. Listagem organizada por canal:
   - Cada canal deve aparecer como um grupo expansivel ou card.
   - Dentro do canal, listar os videos monitorados daquele canal.
   - Mostrar titulo, status, URL, ultima view conhecida, VPD atual, data do primeiro tracking e ultima coleta.

3. Graficos por video:
   - Para cada video, exibir series temporais baseadas em `VideoSnapshot`.
   - Metricas sugeridas:
     - views ao longo do tempo;
     - VPD ao longo do tempo;
     - delta de views entre snapshots;
     - opcional: ranking do video dentro do canal por VPD/views.

4. Comparacao entre videos do mesmo canal:
   - Em cada canal, permitir ver quais videos estao performando melhor agora.
   - Ordenacao padrao por melhor desempenho recente:
     - VPD atual desc;
     - depois views atuais desc;
     - depois ultimo snapshot mais recente.
   - Mostrar se um video "passou" outro em desempenho, quando possivel.

5. Historico sem perder dados:
   - Confirmar se os snapshots antigos de `VideoSnapshot` ja estao sendo preservados.
   - Se estiverem preservados, a tarefa e principalmente expor esses dados no Analytics.
   - Se nao estiverem preservados corretamente, corrigir a causa antes da UI.

Backend sugerido:
1. Criar endpoint:
   - `GET /api/analytics/videos-by-channel`
   - Query params sugeridos:
     - `status=active|paused|removed|all`
     - `channel_status=active|paused|removed|all`
     - `page`
     - `page_size`
     - opcional `channel_id`
2. Resposta sugerida:
   - lista paginada de canais;
   - cada canal com `videos`;
   - cada video com resumo e series temporais.
3. Evitar N+1 excessivo:
   - Buscar canais paginados;
   - buscar videos desses canais em lote;
   - buscar snapshots desses videos em lote;
   - montar em memoria por `tracked_video_id`.

Frontend sugerido:
1. Adicionar aba "Videos por canal" em Analytics.
2. Renderizar grupos por canal.
3. Cada video pode ter um mini grafico ou grafico expandido.
4. Usar loading/skeleton e paginacao para nao travar a tela se houver muitos videos.

Validacao:
- Rodar `python -m compileall api/app`.
- Rodar `npm run build` em `web`.
- Testar com canal que tenha varios videos monitorados e varios snapshots.
- Conferir que snapshots antigos continuam aparecendo depois de novos syncs.
- Conferir que a ordenacao muda quando outro video fica melhor.

## X 2. Estudar arquivamento de trechos de videos removidos do YouTube

Status: PENDENTE - AGUARDAR CONFIRMACAO DO USUARIO ANTES DE IMPLEMENTAR

Solicitacao:
- O usuario quer uma opcao para salvar trechos de videos em algum lugar.
- Objetivo: se um video/canal for removido do YouTube, ainda conseguir estudar o trecho para entender por que aquele canal foi removido e aprender a fazer conteudos corretamente.
- O video nao precisa ser em alta qualidade; 480p e suficiente.
- O usuario considera usar Google Drive ou MEGA por causa do armazenamento.

Regra obrigatoria:
- Antes de implementar qualquer parte deste recurso, Claude deve perguntar ao usuario se ele quer realmente fazer essa alteracao agora.
- Tambem deve perguntar qual destino de armazenamento prefere: Google Drive, MEGA, storage proprio/VPS, S3/compatível, ou somente salvar metadados por enquanto.

Arquivo de referencia criado:
- `lembrete.md`

Ideias tecnicas para avaliar:
1. Salvar somente metadados primeiro:
   - titulo, canal, URL, thumbnail, descricao, transcricao quando disponivel, stats e motivo da selecao.
   - Baixo armazenamento.
   - Nao preserva o video, mas ja ajuda muito na analise.

2. Salvar frames/thumbnails periodicos:
   - Capturar thumbnail e alguns frames representativos.
   - Armazenamento baixo.
   - Ajuda a estudar embalagem visual, mas nao preserva narrativa completa.

3. Salvar trechos curtos em 480p:
   - Baixar apenas trechos relevantes, por exemplo primeiros 30-90 segundos ou trechos definidos manualmente.
   - Armazenamento medio.
   - Melhor custo/beneficio para estudo.

4. Salvar video inteiro em 480p somente para candidatos fortes:
   - Aplicar apenas para videos/canais com sinal alto: Canal Viral, Aquecendo, Promissor ou VPD acima de limite.
   - Armazenamento alto, mas controlado por regra.

5. Armazenamento Google Drive:
   - Bom para organizacao manual e acesso facil.
   - Precisa OAuth/service account e controle de quota.
   - Criar estrutura por canal/video/data.

6. Armazenamento MEGA:
   - Pode oferecer bastante espaco.
   - Integracao via ferramentas externas pode ser mais fragil.
   - Avaliar confiabilidade da lib/CLI antes de automatizar.

7. Armazenamento local/VPS + backup:
   - Mais controle tecnico.
   - Exige disco, limpeza e politica de retencao.
   - Pode ficar caro conforme volume.

Recomendacao inicial:
- Comecar com metadados + thumbnails + opcao manual de arquivar trecho curto em 480p.
- Nao baixar automaticamente tudo.
- Criar politica de retencao:
  - limite por canal;
  - limite diario;
  - limite de armazenamento total;
  - apagar/compactar arquivos antigos somente com confirmacao do usuario.

Cuidados legais e operacionais:
- Confirmar se o uso e apenas estudo privado.
- Evitar redistribuicao de conteudo baixado.
- Nao salvar credenciais do Google Drive/MEGA em texto puro.
- Se for criar tabelas novas ou migrations, pedir permissao explicita antes.
- Se for usar pasta de backup ou armazenamento externo, perguntar antes de ler/adicionar/alterar.
