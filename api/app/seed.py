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
        "description": "1.1 — De quantas em quantas horas o sync automático roda.",
    },
    # -------------------------------------------------------------
    # Thresholds de busca/discovery
    # -------------------------------------------------------------
    {
        "key": "search.window_days",
        "value": "14",
        "value_type": "int",
        "description": "2.1 — Janela em dias da busca: só vídeos publicados nesse período.",
    },
    {
        "key": "search.min_views",
        "value": "5000",
        "value_type": "int",
        "description": "2.2 — Views mínimas para o vídeo entrar nos resultados.",
    },
    {
        "key": "search.min_vpd",
        "value": "1000",
        "value_type": "int",
        "description": "2.3 — VPD mínimo (views por dia desde a publicação).",
    },
    {
        "key": "search.min_duration_seconds",
        "value": "120",
        "value_type": "int",
        "description": "2.4 — Duração mínima do vídeo em segundos (60+ exclui Shorts).",
    },
    {
        "key": "search.languages",
        "value": "pt,en,es",
        "value_type": "str",
        "description": "2.5 — Idiomas em que a busca pede preferência (CSV de códigos ISO).",
    },
    {
        "key": "search.pages_per_term",
        "value": "2",
        "value_type": "int",
        "description": "2.6 — Páginas pedidas por termo de busca (cada página = 50 vídeos, 100 units).",
    },
    # -------------------------------------------------------------
    # Filtro de idade do CANAL (aplicado na descoberta)
    # -------------------------------------------------------------
    {
        "key": "channel.min_age_days",
        "value": "7",
        "value_type": "int",
        "description": "3.1 — Idade mínima do canal (dias desde a criação) para entrar na descoberta.",
    },
    {
        "key": "channel.max_age_days",
        "value": "365",
        "value_type": "int",
        "description": "3.2 — Idade máxima do canal (dias desde a criação) para entrar na descoberta.",
    },
    {
        "key": "channel.vpd_saturation",
        "value": "200000",
        "value_type": "int",
        "description": "3.3 — Linha de saturação de VPD: acima disso, o canal já é considerado consolidado.",
    },
    # -------------------------------------------------------------
    # Monitoramento
    # -------------------------------------------------------------
    {
        "key": "monitor.best_videos_sample_size",
        "value": "10",
        "value_type": "int",
        "description": "4.1 — Quantos uploads recentes baixar de cada canal monitorado por sync.",
    },
    # -------------------------------------------------------------
    # Analytics — thresholds de classificação de sinal
    # -------------------------------------------------------------
    {
        "key": "analytics.promising_max_subscribers",
        "value": "50000",
        "value_type": "int",
        "description": "5.1 — Teto de inscritos para o canal ser marcado como 'promissor'.",
    },
    {
        "key": "analytics.promising_vpd_ratio",
        "value": "0.2",
        "value_type": "float",
        "description": "5.2 — Piso de VPD para 'promissor', como fração da saturação (3.3).",
    },
    {
        "key": "analytics.recent_uploads_sample_size",
        "value": "5",
        "value_type": "int",
        "description": "5.3 — Quantos uploads recentes entram na mediana de views.",
    },
    {
        "key": "analytics.breakout_max_subscribers",
        "value": "10000",
        "value_type": "int",
        "description": "5.4 — Teto de inscritos para o canal ser marcado como 'Canal Viral'.",
    },
    {
        "key": "analytics.breakout_min_median_views",
        "value": "50000",
        "value_type": "int",
        "description": "5.5 — Piso da mediana de views recentes para 'Canal Viral'.",
    },
    {
        "key": "analytics.breakout_views_to_subs_ratio",
        "value": "2",
        "value_type": "float",
        "description": "5.6 — Multiplicador views ÷ inscritos para 'Canal Viral'.",
    },
    # -------------------------------------------------------------
    # API do YouTube
    # -------------------------------------------------------------
    {
        "key": "youtube.api_keys",
        "value": None,
        "value_type": "secret",
        "is_secret": True,
        "description": "8.1 — Chaves da YouTube Data API v3 (uma por linha). Cifradas no banco.",
    },
    {
        "key": "youtube.api_key_daily_quota",
        "value": "10000",
        "value_type": "int",
        "description": "8.2 — Quota diária por chave (default oficial do Google: 10.000 units).",
    },
    {
        "key": "youtube.quota_usage_today",
        "value": None,
        "value_type": "json",
        "description": "8.3 — Estado interno do consumo de quota do dia (não mexa).",
    },
    {
        "key": "youtube.api_keys_burned",
        "value": None,
        "value_type": "json",
        "description": "8.4 — Estado interno: chaves YouTube marcadas como queimadas (não mexa).",
    },
    # -------------------------------------------------------------
    # Descoberta automática (rodada após cada sync)
    # -------------------------------------------------------------
    {
        "key": "discovery.auto_enabled",
        "value": "true",
        "value_type": "bool",
        "description": "6.1 — Liga/desliga a descoberta automática que roda após cada sync.",
    },
    {
        "key": "discovery.auto_quota_pct",
        "value": "0.5",
        "value_type": "float",
        "description": "6.2 — Fração da quota total diária reservada para a descoberta automática (0 a 1).",
    },
    {
        "key": "discovery.auto_keywords",
        "value": "\n".join(all_seed_terms()),
        "value_type": "str",
        "description": "6.3 — Termos seed da descoberta automática (um por linha).",
    },
    {
        "key": "discovery.auto_max_terms_per_run",
        "value": "30",
        "value_type": "int",
        "description": "6.4 — Limite máximo de termos (seed + derivados) por execução.",
    },
    {
        "key": "discovery.auto_derived_term_min_freq",
        "value": "3",
        "value_type": "int",
        "description": "6.5 — Frequência mínima para uma palavra virar 'termo derivado'.",
    },
    # -------------------------------------------------------------
    # Sugestões — recomendações exibidas em Monitoramento > Sugestões.
    # São APENAS recomendações — nunca executam ação no canal.
    # -------------------------------------------------------------
    {
        "key": "suggestions.monitor_min_vpd",
        "value": "10000",
        "value_type": "int",
        "description": "7.1.1 — VPD mínimo para sugerir um canal (regra simples).",
    },
    {
        "key": "suggestions.monitor_max_age_days",
        "value": "90",
        "value_type": "int",
        "description": "7.1.2 — Idade máxima do canal (dias) na regra simples.",
    },
    {
        "key": "suggestions.monitor_breakout_max_subscribers",
        "value": "20000",
        "value_type": "int",
        "description": "7.2.1 — Teto de inscritos para 'Canal Viral'.",
    },
    {
        "key": "suggestions.monitor_breakout_max_age_days",
        "value": "90",
        "value_type": "int",
        "description": "7.2.2 — Idade máxima do canal (dias) para 'Canal Viral'.",
    },
    {
        "key": "suggestions.monitor_breakout_max_video_count",
        "value": "10",
        "value_type": "int",
        "description": "7.2.3 — Número máximo de vídeos publicados para 'Canal Viral'.",
    },
    {
        "key": "suggestions.monitor_breakout_min_views",
        "value": "50000",
        "value_type": "int",
        "description": "7.2.4 — Views mínimas do melhor vídeo descoberto para 'Canal Viral'.",
    },
    {
        "key": "suggestions.monitor_breakout_min_vpd",
        "value": "2000",
        "value_type": "int",
        "description": "7.2.5 — VPD mínimo do melhor vídeo descoberto para 'Canal Viral'.",
    },
    {
        "key": "suggestions.dead_min_days_no_uploads",
        "value": "60",
        "value_type": "int",
        "description": "7.3.1 — Dias sem uploads para considerar o canal 'morto'.",
    },
    {
        "key": "suggestions.dead_max_vpd",
        "value": "2000",
        "value_type": "int",
        "description": "7.3.2 — VPD máximo para considerar o canal 'morto'.",
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
