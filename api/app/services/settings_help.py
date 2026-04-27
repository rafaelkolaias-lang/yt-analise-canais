"""
Textos detalhados (didáticos) das settings para o tooltip "?" na UI.

A `description` em `app_settings` (definida em `seed.py`) é a versão CURTA
exibida ao lado do campo. Aqui ficam as versões LONGAS, didáticas, que
aparecem no hover do "?". Cada texto começa com o número da seção/regra
para virar referência cruzada (ex.: "ver 4.2", "combina com 7.2.3").

Numeração:
  1.x   Sincronização
  2.x   Busca / Discovery
  3.x   Scoring de canal
  4.x   Monitoramento
  5.x   Analytics
  6.x   Descoberta automática
  7.x   Sugestões
        7.1.x Regra simples
        7.2.x Canal Viral
        7.3.x Canal morto
  8.x   API do YouTube

Mantido em código (não no banco) para evitar migration por mudança puramente
textual. O endpoint mistura o `help` aqui com o `description` do banco antes
de devolver ao frontend.
"""
from __future__ import annotations


HELP_TEXTS: dict[str, str] = {
    # =================================================================
    # 1. Sincronização
    # =================================================================
    "sync_interval_hours": (
        "1.1 — Cadência do sync automático.\n\n"
        "Define de quantas em quantas horas o sistema acorda para visitar "
        "todos os canais que você já está monitorando, atualizando inscritos, "
        "views totais, e procurando uploads novos.\n\n"
        "Exemplo: 12 = sincroniza duas vezes por dia (meia-noite e meio-dia, "
        "com pequena variação).\n\n"
        "Trade-off: mais frequente = dado mais fresco, mas gasta mais quota da "
        "YouTube API (ver 8.2). Para ~50 canais, 12h é confortável.\n\n"
        "Mudou e salvou? O scheduler é reagendado na hora — não precisa "
        "reiniciar nada."
    ),

    # =================================================================
    # 2. Busca / Discovery
    # =================================================================
    "search.window_days": (
        "2.1 — Janela temporal da busca.\n\n"
        "Quando você roda uma busca (manual ou automática), o sistema só pede "
        "à YouTube vídeos publicados nos últimos N dias.\n\n"
        "Exemplo: 14 = 'me traga vídeos das duas últimas semanas'. Vídeos mais "
        "antigos nem entram no resultado.\n\n"
        "Quanto MENOR esse número, mais 'fresco' o resultado, mas você perde "
        "vídeos antigos que ainda estão performando bem. 14 a 30 é o ponto "
        "comum para descoberta de tendências.\n\n"
        "Vale para a busca manual E para a descoberta automática (ver 6.1)."
    ),
    "search.min_views": (
        "2.2 — Corte mínimo de views absolutas.\n\n"
        "Vídeos com menos views que isso são descartados antes mesmo de "
        "virarem resultado. Útil pra cortar vídeo zerado e focar em conteúdo "
        "que já provou ter público.\n\n"
        "Diferença pro 2.3 (mín. VPD): aqui é volume bruto, lá é velocidade. "
        "Vídeo de um ano com 5.000 views passa em 2.2 mas é lento (VPD baixo); "
        "vídeo novo com 5.000 views passa nos dois.\n\n"
        "5.000 a 10.000 é um corte razoável para descoberta inicial."
    ),
    "search.min_vpd": (
        "2.3 — Corte mínimo de VPD (views por dia).\n\n"
        "VPD = views totais ÷ dias desde a publicação. Mede VELOCIDADE, não "
        "tamanho.\n\n"
        "Exemplo: vídeo de 7 dias com 5.000 views tem VPD ≈ 714. Passa em "
        "VPD ≥ 500. Já um vídeo de 3 anos com as mesmas 5.000 views tem VPD "
        "ínfimo e é descartado, porque está parado.\n\n"
        "Combina com 2.2 no E lógico: o vídeo precisa ter MUITAS views E "
        "estar acumulando rápido."
    ),
    "search.min_duration_seconds": (
        "2.4 — Duração mínima do vídeo (em segundos).\n\n"
        "Use ≥ 60 para excluir Shorts (que têm até 60s). 0 desliga o filtro e "
        "aceita qualquer duração, inclusive Shorts.\n\n"
        "Shorts inflam VPD artificialmente (são consumidos em rajadas), então "
        "se a sua tese é vídeo longo, manter ≥ 60 é o normal."
    ),
    "search.languages": (
        "2.5 — Idiomas de preferência da busca.\n\n"
        "Lista CSV de códigos ISO (ex.: pt,en,es). Para cada termo buscado, o "
        "sistema repete a busca uma vez por idioma, passando o código como "
        "'relevanceLanguage' para a YouTube.\n\n"
        "Mais idiomas = mais cobertura, mas multiplica o custo de quota: cada "
        "idioma extra é mais uma chamada de busca (100 units cada — ver 2.6).\n\n"
        "Para um nicho local, deixe só 'pt'. Para nichos globais (música, "
        "tech), 'pt,en,es' é o padrão."
    ),
    "search.pages_per_term": (
        "2.6 — Páginas pedidas por termo.\n\n"
        "Cada página da YouTube API devolve até 50 vídeos. 2 páginas = até "
        "100 vídeos por termo (por idioma de 2.5).\n\n"
        "ATENÇÃO ao custo: cada página custa 100 units de quota. 2 páginas × "
        "3 idiomas × 30 termos da descoberta automática (ver 6.4) = 18.000 "
        "units, quase 2 chaves cheias por ciclo.\n\n"
        "1 página é o conservador. 2 só se você tem várias chaves."
    ),

    # =================================================================
    # 3. Scoring de canal
    # =================================================================
    "channel.min_age_days": (
        "3.1 — Idade mínima do canal (em dias).\n\n"
        "Na descoberta, canais com menos dias desde a criação no YouTube são "
        "descartados, junto com seus vídeos.\n\n"
        "Exemplo: 30 = ignora canais criados há menos de um mês. Use 0 para "
        "desligar esse corte e aceitar canais bem novos.\n\n"
        "Por que isso existe: canais muito novos têm pouco histórico — fica "
        "difícil saber se o sucesso é tendência ou só acaso. Se sua tese é "
        "achar canais pequenos e novíssimos, baixe esse número.\n\n"
        "Vale para descoberta manual E automática. Combina com 3.2 num "
        "intervalo (mínimo, máximo)."
    ),
    "channel.max_age_days": (
        "3.2 — Idade máxima do canal (em dias).\n\n"
        "Mesma regra de 3.1, pelo lado de cima. Canais MAIS VELHOS que isso "
        "são descartados.\n\n"
        "Exemplo: 3650 = 10 anos (default, praticamente sem limite). Use "
        "valor enorme (99999) se você não quer limite superior.\n\n"
        "Útil quando você quer só canais relativamente novos (ex.: 3.1 = 30 e "
        "3.2 = 730 = canais entre 1 mês e 2 anos)."
    ),
    "channel.vpd_saturation": (
        "3.3 — Linha de saturação de VPD.\n\n"
        "Usada pelo Analytics para distinguir 'oportunidade' de 'já saturado'. "
        "Canal cujo VPD médio recente passa desse valor é considerado "
        "consolidado/grande demais para ainda ser oportunidade.\n\n"
        "Exemplo: 100.000 VPD = canal já está em escala industrial.\n\n"
        "Esse número também é base para 5.2 (promissor): canal vira promissor "
        "se chega numa fração dessa saturação. Trate 3.3 como 'topo' e 5.2 "
        "como 'a partir de quanto começa a virar interessante'."
    ),

    # =================================================================
    # 4. Monitoramento
    # =================================================================
    "monitor.best_videos_sample_size": (
        "4.1 — Quantos uploads recentes baixar por canal a cada sync.\n\n"
        "A cada sincronização (ver 1.1), o sistema baixa os N uploads mais "
        "recentes de cada canal monitorado, para:\n"
        "  • detectar 'melhor vídeo recente' do canal;\n"
        "  • calcular uploads/semana.\n\n"
        "Mais alto = visão mais ampla, mas custa 1 unit a mais por canal "
        "acima de 50 uploads (a YouTube API pagina em 50).\n\n"
        "10 a 20 cobre bem a maioria dos casos sem inflar custo."
    ),

    # =================================================================
    # 5. Analytics
    # =================================================================
    "analytics.promising_max_subscribers": (
        "5.1 — Teto de inscritos para o sinal 'promissor'.\n\n"
        "Para o Analytics marcar um canal como 'promissor' (canal pequeno com "
        "VPD alto), os inscritos têm que estar abaixo desse valor.\n\n"
        "Acima disso o canal já é considerado 'grande' demais pra ser "
        "oportunidade. 50.000 é um corte comum para a tese de canais "
        "pequenos com vídeo desproporcional.\n\n"
        "Combina com 5.2 no E lógico — os dois precisam passar."
    ),
    "analytics.promising_vpd_ratio": (
        "5.2 — Piso de VPD para o sinal 'promissor', como fração de 3.3.\n\n"
        "Define a partir de quanto VPD um canal entra no radar como "
        "'promissor'. É uma fração da linha de saturação (ver 3.3).\n\n"
        "Exemplo: se a saturação for 100.000 e a fração for 0,3 (= 30%), o "
        "canal precisa ter VPD ≥ 30.000 para virar promissor.\n\n"
        "Por que fração e não número absoluto: assim, se você ajustar 3.3 "
        "para um nicho diferente, o piso de promissor sobe/desce junto sem "
        "precisar mexer aqui."
    ),
    "analytics.recent_uploads_sample_size": (
        "5.3 — Tamanho da amostra usada na mediana de views recentes.\n\n"
        "Quantos vídeos recentes do canal o Analytics olha para calcular a "
        "MEDIANA de views. Essa mediana entra na regra de Canal Viral "
        "(ver 5.4 e 5.5).\n\n"
        "Mediana é menos sensível a um vídeo viralzão isolado do que média — "
        "5 a 10 uploads dão um sinal estável."
    ),
    "analytics.breakout_max_subscribers": (
        "5.4 — Teto de inscritos para 'Canal Viral' no Analytics.\n\n"
        "Para o Analytics marcar um canal já monitorado como 'Canal Viral', "
        "ele precisa ter MENOS inscritos que isso.\n\n"
        "A ideia é flagrar canal pequeno cujo conteúdo está performando bem "
        "ALÉM da audiência atual — sinal de descolamento.\n\n"
        "Combina com 5.5 e 5.6 no E lógico: as três regras valem juntas."
    ),
    "analytics.breakout_min_median_views": (
        "5.5 — Piso da mediana de views para 'Canal Viral'.\n\n"
        "A mediana de views dos últimos uploads (calculada com 5.3) precisa "
        "ser ≥ esse valor.\n\n"
        "Mediana alta + canal pequeno (5.4) = vídeo desproporcional, exatamente "
        "o sinal que o 'Canal Viral' tenta capturar.\n\n"
        "Combina com 5.4 e 5.6 no E lógico."
    ),
    "analytics.breakout_views_to_subs_ratio": (
        "5.6 — Multiplicador views ÷ inscritos para 'Canal Viral'.\n\n"
        "A mediana de views recentes (5.5) precisa ser pelo menos N vezes "
        "maior que o número de inscritos.\n\n"
        "Exemplo: 5 = mediana de views ≥ 5x inscritos. Mede o quanto o "
        "conteúdo está performando ALÉM da audiência atual.\n\n"
        "Esse é o coração do sinal: 5.4 e 5.5 garantem 'canal pequeno com "
        "vídeo grande', e 5.6 garante que a desproporção é grande de "
        "verdade."
    ),

    # =================================================================
    # 6. Descoberta automática
    # =================================================================
    "discovery.auto_enabled": (
        "6.1 — Liga/desliga a descoberta automática.\n\n"
        "Quando ligada, depois de cada sync (ver 1.1) o sistema roda uma "
        "rodada de descoberta usando uma mistura de termos seed (que você "
        "cadastra em 6.4) e termos derivados (extraídos automaticamente dos "
        "canais já descobertos).\n\n"
        "Desligue se quiser controlar a descoberta 100% manualmente — útil "
        "enquanto você ainda está calibrando os termos seed."
    ),
    "discovery.auto_quota_pct": (
        "6.2 — Fração da quota total que a descoberta pode gastar por ciclo.\n\n"
        "Entre 0 e 1. É a porcentagem da quota TOTAL diária (todas as chaves "
        "somadas — ver 8.2) que a descoberta automática tem como orçamento "
        "por ciclo.\n\n"
        "Exemplo: 0,5 com 1 chave (10.000 units) = descoberta tem 5.000 "
        "units, deixando os outros 5.000 para snapshots e busca manual.\n\n"
        "Sobe esse valor se você está com várias chaves e quer mais "
        "cobertura. Reduz se a descoberta está engolindo quota antes de "
        "sobrar pro sync."
    ),
    "discovery.auto_keywords": (
        "6.3 — Termos SEED da descoberta automática (um por linha).\n\n"
        "Lista que o sistema rotaciona a cada execução. Mistura com termos "
        "DERIVADOS (palavras frequentes nos títulos dos canais já "
        "descobertos — ver 6.5) para ampliar cobertura.\n\n"
        "Dica: comece com 10–20 termos que descrevem o nicho que você quer "
        "minerar. O sistema usa cada um como uma busca independente, então "
        "termos genéricos demais (ex.: 'video') gastam quota sem retorno."
    ),
    "discovery.auto_max_terms_per_run": (
        "6.4 — Limite máximo de termos por execução.\n\n"
        "Soma de termos seed (6.3) + termos derivados (6.5) por ciclo da "
        "descoberta automática.\n\n"
        "Cálculo de custo: 30 termos × 1 página × 3 idiomas (ver 2.5) ≈ "
        "9.000 units. Ou seja, ~1 chave inteira (8.2) por ciclo.\n\n"
        "Subir aumenta cobertura, mas pode estourar o orçamento de 6.2 e o "
        "ciclo é cortado no meio. Se você está com várias chaves, pode subir."
    ),
    "discovery.auto_derived_term_min_freq": (
        "6.5 — Frequência mínima para uma palavra virar 'termo derivado'.\n\n"
        "O sistema extrai palavras dos títulos dos canais já descobertos e, "
        "se uma palavra aparece N vezes ou mais, ela vira candidata a termo "
        "derivado e entra no pool com os termos seed (6.3).\n\n"
        "É um filtro anti-ruído: 1 ou 2 ocorrências geralmente é palavra "
        "solta sem padrão. 3 a 5 já indica recorrência real.\n\n"
        "Subir = só termos muito frequentes (perde diversidade). Baixar = "
        "mais variedade, mas mais ruído."
    ),

    # =================================================================
    # 7. Sugestões — exibidas em Monitoramento → Sugestões
    # =================================================================

    # 7.1 Regra simples
    "suggestions.monitor_min_vpd": (
        "7.1.1 — VPD mínimo da regra simples.\n\n"
        "Canal descoberto vira sugestão pra você monitorar se o VPD recente "
        "for ≥ esse valor.\n\n"
        "Combina com 7.1.2 (idade máxima) no E lógico: as duas têm que passar.\n\n"
        "Diferença pra 7.2: aqui é uma regra direta (canal jovem com VPD "
        "alto). Em 7.2.x existe um conjunto mais restrito para 'Canal "
        "Viral' (canal MUITO novo, MUITO poucos vídeos, mas com vídeo "
        "estourando)."
    ),
    "suggestions.monitor_max_age_days": (
        "7.1.2 — Idade máxima do canal na regra simples (dias).\n\n"
        "Idade do canal (em dias desde a criação no YouTube) precisa ser ≤ "
        "esse valor para virar sugestão pela regra simples.\n\n"
        "Combina com 7.1.1 (VPD mínimo) no E lógico."
    ),

    # 7.2 Canal Viral
    "suggestions.monitor_breakout_max_subscribers": (
        "7.2.1 — Teto de inscritos para 'Canal Viral'.\n\n"
        "Canal precisa ter MENOS inscritos que isso.\n\n"
        "Todas as 5 regras de Canal Viral (7.2.1 a 7.2.5) valem em "
        "conjunto (E lógico) — o canal só vira sugestão se passar nas cinco."
    ),
    "suggestions.monitor_breakout_max_age_days": (
        "7.2.2 — Idade máxima do canal para 'Canal Viral' (dias).\n\n"
        "Idade do canal (em dias desde a criação no YouTube) precisa ser ≤ "
        "esse valor.\n\n"
        "Combina com as outras regras de Canal Viral (7.2.1, 7.2.3, "
        "7.2.4, 7.2.5) no E lógico."
    ),
    "suggestions.monitor_breakout_max_video_count": (
        "7.2.3 — Número máximo de vídeos publicados.\n\n"
        "Canal precisa ter MENOS que esse número TOTAL de vídeos no canal "
        "inteiro.\n\n"
        "A ideia é capturar canal com pouquíssimo conteúdo já estourando — "
        "sinal forte de tese boa, antes do canal escalar.\n\n"
        "Combina com as outras regras de Canal Viral (7.2.1, 7.2.2, "
        "7.2.4, 7.2.5) no E lógico."
    ),
    "suggestions.monitor_breakout_min_views": (
        "7.2.4 — Views mínimas do melhor vídeo descoberto.\n\n"
        "O melhor vídeo descoberto do canal precisa ter pelo menos esse "
        "número de views.\n\n"
        "Combina com as outras regras de Canal Viral (7.2.1 a 7.2.3 e "
        "7.2.5) no E lógico."
    ),
    "suggestions.monitor_breakout_min_vpd": (
        "7.2.5 — VPD mínimo do melhor vídeo descoberto.\n\n"
        "VPD do melhor vídeo descoberto precisa ser ≥ esse valor.\n\n"
        "Combina com as outras regras de Canal Viral (7.2.1 a 7.2.4) no "
        "E lógico."
    ),

    # 7.3 Canal morto
    "suggestions.dead_min_days_no_uploads": (
        "7.3.1 — Dias mínimos sem novos uploads para considerar 'morto'.\n\n"
        "Canal monitorado precisa estar há ≥ esse número de dias SEM uploads "
        "novos para virar sugestão de pausa/remoção.\n\n"
        "Combina com 7.3.2 (VPD máximo) no E lógico — só vira sugestão de "
        "remoção se o canal está parado E com performance baixa."
    ),
    "suggestions.dead_max_vpd": (
        "7.3.2 — VPD máximo para considerar 'morto'.\n\n"
        "VPD recente do canal precisa ser ≤ esse valor.\n\n"
        "Combina com 7.3.1 (dias sem upload) no E lógico. A intenção é "
        "evitar marcar como morto canal que está parado mas ainda tem "
        "vídeos antigos performando bem."
    ),

    # =================================================================
    # 8. API do YouTube
    # =================================================================
    "youtube.api_keys": (
        "8.1 — Chaves da YouTube Data API v3.\n\n"
        "Uma por linha. O sistema rotaciona entre elas — quando uma estoura a "
        "quota diária (ver 8.2), pula automaticamente para a próxima.\n\n"
        "Cifradas no banco com Fernet (chave mestra em APP_SECRET_KEY do "
        "ambiente). Não aparecem em texto plano em nenhum endpoint.\n\n"
        "Para criar chaves: console.cloud.google.com → APIs e serviços → "
        "Credenciais → Criar chave de API. Habilite a 'YouTube Data API v3' "
        "no projeto."
    ),
    "youtube.api_key_daily_quota": (
        "8.2 — Quota diária POR CHAVE.\n\n"
        "Default oficial do Google: 10.000 units por chave por dia. O sistema "
        "usa esse valor para decidir quando rotacionar (ver 8.1) e para "
        "calcular o consumo agregado mostrado na central de notificações.\n\n"
        "Se você pediu aumento de quota e o Google liberou, ajuste aqui para "
        "o novo limite. Se ficar errado, o sistema vai parar de rotacionar "
        "antes da hora ou tentar usar uma chave já estourada."
    ),
    "youtube.quota_usage_today": (
        "8.3 — Estado interno de consumo de quota (não mexa).\n\n"
        "Guarda quanto cada chave gastou HOJE (em UTC) e qual foi o último "
        "evento de consumo. É lido pela central de notificações para mostrar "
        "o gráfico de consumo.\n\n"
        "Reseta automaticamente todo dia em UTC. Não precisa mexer — está "
        "exposto aqui só pra debug."
    ),
}


def get_help(key: str) -> str | None:
    """Devolve o texto longo (didático) para uma chave de setting, ou None."""
    return HELP_TEXTS.get(key)
