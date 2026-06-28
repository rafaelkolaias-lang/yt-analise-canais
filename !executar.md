# Plano de Execucao - youtube-analyzer

> Use este arquivo so para tarefas pendentes.
> Quando uma tarefa for concluida, remover daqui.

---

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
