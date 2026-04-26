"""
Seed inicial idempotente de app_settings.

Uso:
  cd api && .venv/Scripts/python.exe -m app.seed

Comportamento:
  - Se a chave NÃO existe: insere com value+value_type+description default.
  - Se a chave JÁ existe: NÃO toca o `value` (preserva ajustes do usuário),
    mas atualiza `description` para refletir o texto mais recente do código.
    Isso permite reescrever descrições didáticas sem precisar mexer no banco.

Seguro rodar múltiplas vezes.
"""
from __future__ import annotations

from app.core.database import SessionLocal
from app.models import AppSetting
from app.services.discovery_seed_terms import all_seed_terms

DEFAULT_SETTINGS: list[dict] = [
    # -------------------------------------------------------------
    # Sincronização
    # -------------------------------------------------------------
    {
        "key": "sync_interval_hours",
        "value": "12",
        "value_type": "int",
        "description": (
            "De quantas em quantas HORAS o sistema sai pra sincronizar todos os canais "
            "monitorados (puxar inscritos, views, novos uploads). Ex.: 12 = 2x por dia. "
            "Mudar essa setting reagenda o scheduler na hora, sem reiniciar."
        ),
    },
    # -------------------------------------------------------------
    # Thresholds de busca/discovery
    # -------------------------------------------------------------
    {
        "key": "search.window_days",
        "value": "14",
        "value_type": "int",
        "description": (
            "Quando você faz uma busca no YouTube, o sistema só pede vídeos publicados "
            "nos últimos N dias. Ex.: 14 = 'me traz vídeos das duas últimas semanas'. "
            "Vídeos mais antigos não são retornados pela API. Aplica-se à busca manual "
            "E à descoberta automática."
        ),
    },
    {
        "key": "search.min_views",
        "value": "5000",
        "value_type": "int",
        "description": (
            "Vídeos com MENOS views que isso são descartados antes de virar resultado. "
            "Útil pra cortar vídeo zerado e focar em conteúdo que já provou alguma "
            "tração."
        ),
    },
    {
        "key": "search.min_vpd",
        "value": "500",
        "value_type": "int",
        "description": (
            "VPD = views por dia desde a publicação. Vídeos com VPD abaixo desse valor "
            "são descartados. Ex.: vídeo de 7 dias com 5.000 views tem VPD ≈ 714 — "
            "passa em 500. Mede velocidade, não tamanho."
        ),
    },
    {
        "key": "search.min_duration_seconds",
        "value": "60",
        "value_type": "int",
        "description": (
            "Duração mínima do vídeo em segundos. Use 60+ para excluir Shorts (que têm "
            "≤60s). 0 = aceita qualquer duração, inclusive Shorts."
        ),
    },
    {
        "key": "search.languages",
        "value": "pt,en,es",
        "value_type": "str",
        "description": (
            "Idiomas em que a busca pede preferência (passa para o YouTube como "
            "'relevanceLanguage'). CSV de códigos ISO. Ex.: 'pt,en,es' = busca cada "
            "termo 3 vezes, uma por idioma. Mais idiomas = mais quota gasta."
        ),
    },
    {
        "key": "search.pages_per_term",
        "value": "2",
        "value_type": "int",
        "description": (
            "Cada página da YouTube API devolve até 50 vídeos. 2 páginas = até 100 "
            "vídeos por termo (por idioma). Cada página custa 100 units de quota — "
            "subir esse número multiplica o gasto rapidamente."
        ),
    },
    # -------------------------------------------------------------
    # Filtro de idade do CANAL (aplicado na descoberta)
    # -------------------------------------------------------------
    {
        "key": "channel.min_age_days",
        "value": "30",
        "value_type": "int",
        "description": (
            "Na descoberta, canais com idade MENOR que isso (em dias desde a criação no "
            "YouTube) são descartados, junto com seus vídeos. Ex.: 30 = ignora canais "
            "criados há menos de 1 mês. Use 0 pra desligar esse corte. Vale para "
            "descoberta manual E automática."
        ),
    },
    {
        "key": "channel.max_age_days",
        "value": "3650",
        "value_type": "int",
        "description": (
            "Mesma regra do mínimo, só que pelo lado MÁXIMO. Canais MAIS VELHOS que isso "
            "são descartados. Ex.: 3650 = 10 anos (default). Use um valor enorme (ex.: "
            "99999) se você não quer limite superior."
        ),
    },
    {
        "key": "channel.vpd_saturation",
        "value": "100000",
        "value_type": "int",
        "description": (
            "Linha de corte para o sinal 'saturado' no Analytics. Canal cujo VPD médio "
            "recente passa desse valor é considerado consolidado/grande demais para "
            "ainda ser 'oportunidade'. Ex.: 100.000 VPD = canal já está em escala."
        ),
    },
    # -------------------------------------------------------------
    # Monitoramento
    # -------------------------------------------------------------
    {
        "key": "monitor.best_videos_sample_size",
        "value": "10",
        "value_type": "int",
        "description": (
            "Quantos uploads MAIS RECENTES o sistema baixa de cada canal a cada sync, "
            "para (a) detectar 'melhor vídeo recente' e (b) calcular uploads/semana. "
            "Mais alto = visão mais ampla, custa 1 unit a mais por canal acima de 50."
        ),
    },
    # -------------------------------------------------------------
    # Analytics — thresholds de classificação de sinal
    # -------------------------------------------------------------
    {
        "key": "analytics.promising_max_subscribers",
        "value": "50000",
        "value_type": "int",
        "description": (
            "Para o sinal 'promissor' (canal pequeno com VPD alto), inscritos têm que "
            "estar ABAIXO desse valor. Acima disso o canal já é considerado 'grande' "
            "demais pra ser uma oportunidade dark."
        ),
    },
    {
        "key": "analytics.promising_vpd_ratio",
        "value": "0.3",
        "value_type": "float",
        "description": (
            "Para virar 'promissor', o VPD recente do canal precisa ser ≥ "
            "channel.vpd_saturation × este valor. Ex.: saturação 100k × ratio 0.3 = "
            "canal precisa ter VPD ≥ 30.000 para entrar no radar."
        ),
    },
    {
        "key": "analytics.recent_uploads_sample_size",
        "value": "5",
        "value_type": "int",
        "description": (
            "Quantos vídeos recentes o Analytics usa para calcular a MEDIANA de views "
            "(que entra na regra de breakout precoce). 5 = pega os 5 vídeos mais "
            "recentes do canal e tira a mediana."
        ),
    },
    {
        "key": "analytics.breakout_max_subscribers",
        "value": "10000",
        "value_type": "int",
        "description": (
            "Para sinalizar 'breakout precoce' no Analytics, o canal precisa ter MENOS "
            "inscritos que isso. A ideia é flagrar canal pequeno com vídeo "
            "desproporcionalmente grande (sinal de descolamento)."
        ),
    },
    {
        "key": "analytics.breakout_min_median_views",
        "value": "50000",
        "value_type": "int",
        "description": (
            "Para 'breakout precoce', a mediana de views dos últimos uploads precisa "
            "ser ≥ esse valor. Mediana alta + canal pequeno = vídeo desproporcional."
        ),
    },
    {
        "key": "analytics.breakout_views_to_subs_ratio",
        "value": "5",
        "value_type": "float",
        "description": (
            "Para 'breakout precoce', a mediana de views recentes precisa ser pelo "
            "menos N vezes maior que os inscritos. Ex.: 5 = mediana de views ≥ 5x "
            "inscritos. Mede o quanto o conteúdo está performando ALÉM da audiência."
        ),
    },
    # -------------------------------------------------------------
    # API do YouTube
    # -------------------------------------------------------------
    {
        "key": "youtube.api_keys",
        "value": None,
        "value_type": "secret",
        "is_secret": True,
        "description": (
            "Chaves da YouTube Data API v3 (uma por linha). O sistema rotaciona entre "
            "elas — quando uma estoura quota, pula automaticamente para a próxima. "
            "Cifradas no banco com Fernet (chave mestra em APP_SECRET_KEY)."
        ),
    },
    {
        "key": "youtube.api_key_daily_quota",
        "value": "10000",
        "value_type": "int",
        "description": (
            "Quota diária POR KEY (default oficial do Google = 10.000 units/dia). "
            "O sistema usa esse valor para decidir quando rotacionar e para calcular o "
            "consumo agregado mostrado no painel de notificações."
        ),
    },
    {
        "key": "youtube.quota_usage_today",
        "value": None,
        "value_type": "json",
        "description": (
            "Estado interno: quanto cada key gastou HOJE (UTC) e qual foi o último "
            "evento. Usado pela central de notificações. Reseta automaticamente todo "
            "dia em UTC — não precisa mexer."
        ),
    },
    # -------------------------------------------------------------
    # Descoberta automática (rodada após cada sync)
    # -------------------------------------------------------------
    {
        "key": "discovery.auto_enabled",
        "value": "true",
        "value_type": "bool",
        "description": (
            "Liga/desliga a descoberta automática que roda DEPOIS de cada sync. Quando "
            "ligada, o sistema busca novos canais usando uma mistura de termos seed "
            "(você cadastra) + termos derivados (extraídos dos canais já descobertos)."
        ),
    },
    {
        "key": "discovery.auto_quota_pct",
        "value": "0.5",
        "value_type": "float",
        "description": (
            "Fração da quota TOTAL diária (todas as keys somadas) que a descoberta "
            "automática pode gastar por ciclo. Ex.: 0.5 com 1 key (10k units) = "
            "descoberta tem orçamento de 5.000 units, deixando o resto para snapshots "
            "e busca manual. Entre 0 e 1."
        ),
    },
    {
        "key": "discovery.auto_keywords",
        "value": "\n".join(all_seed_terms()),
        "value_type": "str",
        "description": (
            "Lista de termos SEED da descoberta automática (um por linha). O sistema "
            "rotaciona entre eles a cada execução e mistura com termos derivados "
            "automaticamente dos canais já descobertos."
        ),
    },
    {
        "key": "discovery.auto_max_terms_per_run",
        "value": "30",
        "value_type": "int",
        "description": (
            "Limite máximo de termos por execução automática (seed + derivados). 30 com "
            "1 página por termo × 3 idiomas = ~9.000 units. Subir esse número aumenta "
            "cobertura, mas pode estourar o orçamento de auto_quota_pct."
        ),
    },
    {
        "key": "discovery.auto_derived_term_min_freq",
        "value": "3",
        "value_type": "int",
        "description": (
            "Para uma palavra virar 'termo derivado', ela precisa aparecer pelo menos "
            "N vezes nos títulos dos canais já descobertos. Filtro anti-ruído: 1 ou 2 "
            "ocorrências geralmente é palavra solta sem padrão."
        ),
    },
    # -------------------------------------------------------------
    # Sugestões — recomendações exibidas em Monitoramento > Sugestões.
    # São APENAS recomendações — nunca executam ação no canal.
    # -------------------------------------------------------------
    {
        "key": "suggestions.monitor_min_vpd",
        "value": "10000",
        "value_type": "int",
        "description": (
            "Regra simples para sugerir um canal: VPD recente precisa ser ≥ esse "
            "valor. Combina com max_age_days no E lógico — as duas têm que passar."
        ),
    },
    {
        "key": "suggestions.monitor_max_age_days",
        "value": "60",
        "value_type": "int",
        "description": (
            "Regra simples para sugerir um canal: idade do canal (em dias desde a "
            "criação no YouTube) precisa ser ≤ esse valor. Combina com min_vpd no E "
            "lógico."
        ),
    },
    {
        "key": "suggestions.monitor_breakout_max_subscribers",
        "value": "10000",
        "value_type": "int",
        "description": (
            "Regra de breakout precoce: canal precisa ter MENOS inscritos que isso. "
            "Todas as 5 regras 'breakout_*' valem em conjunto (E lógico)."
        ),
    },
    {
        "key": "suggestions.monitor_breakout_max_age_days",
        "value": "30",
        "value_type": "int",
        "description": (
            "Regra de breakout precoce: idade do canal ≤ esse valor (em dias). "
            "Combina com as outras 'breakout_*' no E lógico."
        ),
    },
    {
        "key": "suggestions.monitor_breakout_max_video_count",
        "value": "3",
        "value_type": "int",
        "description": (
            "Regra de breakout precoce: canal precisa ter MENOS que esse número TOTAL "
            "de vídeos. A ideia é pegar canal com pouquíssimo conteúdo já estourando."
        ),
    },
    {
        "key": "suggestions.monitor_breakout_min_views",
        "value": "50000",
        "value_type": "int",
        "description": (
            "Regra de breakout precoce: o melhor vídeo descoberto do canal precisa "
            "ter PELO MENOS esse número de views."
        ),
    },
    {
        "key": "suggestions.monitor_breakout_min_vpd",
        "value": "2000",
        "value_type": "int",
        "description": (
            "Regra de breakout precoce: VPD do melhor vídeo descoberto precisa ser ≥ "
            "esse valor."
        ),
    },
    {
        "key": "suggestions.dead_min_days_no_uploads",
        "value": "60",
        "value_type": "int",
        "description": (
            "Regra de canal 'morto': canal monitorado precisa estar há ≥ esse número "
            "de dias SEM novos uploads. Combina com dead_max_vpd no E lógico."
        ),
    },
    {
        "key": "suggestions.dead_max_vpd",
        "value": "2000",
        "value_type": "int",
        "description": (
            "Regra de canal 'morto': VPD recente do canal precisa ser ≤ esse valor. "
            "Combina com dead_min_days_no_uploads no E lógico — só vira sugestão de "
            "remoção se o canal está parado E com performance baixa."
        ),
    },
]


def run() -> None:
    db = SessionLocal()
    try:
        inserted = 0
        updated_descriptions = 0
        unchanged = 0
        for item in DEFAULT_SETTINGS:
            key = item["key"]
            new_description = item.get("description")
            existing = db.query(AppSetting).filter_by(key=key).one_or_none()
            if existing:
                # Não mexe em value/value_type (preserva configuração do usuário),
                # mas atualiza a description para refletir o texto mais recente do
                # código — assim reescrever descrição didática só requer rerodar
                # o seed.
                if new_description and existing.description != new_description:
                    existing.description = new_description
                    updated_descriptions += 1
                else:
                    unchanged += 1
                continue
            db.add(
                AppSetting(
                    key=key,
                    value=item.get("value"),
                    value_type=item.get("value_type", "str"),
                    is_secret=item.get("is_secret", False),
                    description=new_description,
                )
            )
            inserted += 1
        db.commit()
        print(
            f"Seed concluído: {inserted} inseridas, "
            f"{updated_descriptions} descrições atualizadas, "
            f"{unchanged} inalteradas."
        )
    finally:
        db.close()


if __name__ == "__main__":
    run()
