"""
Seed inicial idempotente de app_settings.

Uso:
  cd api && .venv/Scripts/python.exe -m app.seed

Só insere chaves que ainda não existem — seguro de rodar múltiplas vezes.
Não sobrescreve valores já configurados pelo usuário.
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
        "description": "Intervalo em horas entre sincronizações automáticas.",
    },
    # -------------------------------------------------------------
    # Thresholds de busca/discovery (base fiel ao app desktop)
    # -------------------------------------------------------------
    {
        "key": "search.window_days",
        "value": "14",
        "value_type": "int",
        "description": "Janela de publicação em dias para considerar um vídeo recente.",
    },
    {
        "key": "search.min_views",
        "value": "5000",
        "value_type": "int",
        "description": "Views mínimas para incluir vídeo no resultado.",
    },
    {
        "key": "search.min_vpd",
        "value": "500",
        "value_type": "int",
        "description": "VPD mínimo (views per day) para incluir vídeo.",
    },
    {
        "key": "search.min_duration_seconds",
        "value": "60",
        "value_type": "int",
        "description": "Duração mínima em segundos (exclui shorts quando > 60).",
    },
    {
        "key": "search.languages",
        "value": "pt,en,es",
        "value_type": "str",
        "description": "Idiomas ativos (CSV de códigos ISO).",
    },
    {
        "key": "search.pages_per_term",
        "value": "2",
        "value_type": "int",
        "description": "Páginas de resultados por termo de busca.",
    },
    # -------------------------------------------------------------
    # Thresholds de canal
    # -------------------------------------------------------------
    {
        "key": "channel.min_age_days",
        "value": "30",
        "value_type": "int",
        "description": "Idade mínima do canal em dias.",
    },
    {
        "key": "channel.max_age_days",
        "value": "3650",
        "value_type": "int",
        "description": "Idade máxima do canal em dias (10 anos).",
    },
    {
        "key": "channel.vpd_saturation",
        "value": "100000",
        "value_type": "int",
        "description": "VPD médio acima do qual o canal é considerado saturado.",
    },
    # -------------------------------------------------------------
    # Monitoramento
    # -------------------------------------------------------------
    {
        "key": "monitor.best_videos_sample_size",
        "value": "10",
        "value_type": "int",
        "description": "Últimos N uploads analisados para detectar melhor vídeo recente por canal.",
    },
    # -------------------------------------------------------------
    # Analytics — thresholds de classificação de sinal
    # -------------------------------------------------------------
    {
        "key": "analytics.promising_max_subscribers",
        "value": "50000",
        "value_type": "int",
        "description": "Inscritos máximos para um canal ser elegível a 'promissor' (dark).",
    },
    {
        "key": "analytics.promising_vpd_ratio",
        "value": "0.3",
        "value_type": "float",
        "description": "Multiplicador de vpd_saturation para considerar VPD alto em canal pequeno.",
    },
    {
        "key": "analytics.recent_uploads_sample_size",
        "value": "5",
        "value_type": "int",
        "description": "Quantidade de uploads recentes usados no Analytics para medir mediana de views.",
    },
    {
        "key": "analytics.breakout_max_subscribers",
        "value": "10000",
        "value_type": "int",
        "description": "Máximo de inscritos para marcar um canal como breakout precoce no Analytics.",
    },
    {
        "key": "analytics.breakout_min_median_views",
        "value": "50000",
        "value_type": "int",
        "description": "Mediana mínima de views recentes para um canal pequeno virar breakout no Analytics.",
    },
    {
        "key": "analytics.breakout_views_to_subs_ratio",
        "value": "5",
        "value_type": "float",
        "description": "Razão mínima entre mediana de views recentes e inscritos para breakout precoce.",
    },
    # -------------------------------------------------------------
    # API keys YouTube (cifradas quando definidas pelo usuário)
    # Aqui apenas cria o registro vazio — a tela de Configurações
    # (Fase 2) vai preencher com valor cifrado.
    # -------------------------------------------------------------
    {
        "key": "youtube.api_keys",
        "value": None,
        "value_type": "secret",
        "is_secret": True,
        "description": "Chaves da YouTube Data API v3 (uma por linha). Cifradas com Fernet (APP_SECRET_KEY).",
    },
    {
        "key": "youtube.api_key_daily_quota",
        "value": "10000",
        "value_type": "int",
        "description": "Cota diária por API key do YouTube.",
    },
    # Estado persistido de consumo de quota — usado pela central de
    # notificações para mostrar o uso agregado das keys. Atualizado pelo
    # `youtube_client._get` a cada request bem-sucedida e zerado quando
    # `date_utc` < hoje (rollover diário em UTC, pra casar com o reset do
    # YouTube). Formato:
    #   {"date_utc": "YYYY-MM-DD",
    #    "used_per_key": [123, 0, ...],
    #    "last_event": {"at": ISO, "label": "...", "cost": N, "key_index": K} | null}
    {
        "key": "youtube.quota_usage_today",
        "value": None,
        "value_type": "json",
        "description": "Estado persistido de consumo da cota diária do YouTube por API key (rollover diário UTC).",
    },
    # -------------------------------------------------------------
    # Discovery automática (rodada após cada sync)
    # -------------------------------------------------------------
    {
        "key": "discovery.auto_enabled",
        "value": "true",
        "value_type": "bool",
        "description": "Liga/desliga a descoberta automática pós-sync.",
    },
    {
        "key": "discovery.auto_quota_pct",
        "value": "0.5",
        "value_type": "float",
        "description": "Fração máxima da cota diária total (todas as keys) que a descoberta automática pode consumir num ciclo.",
    },
    {
        "key": "discovery.auto_keywords",
        "value": "\n".join(all_seed_terms()),
        "value_type": "str",
        "description": "Termos seed da descoberta automática (uma linha por termo). Editável pelo usuário; o sistema também gera termos derivados a partir dos canais já descobertos.",
    },
    {
        "key": "discovery.auto_max_terms_per_run",
        "value": "30",
        "value_type": "int",
        "description": "Quantos termos no máximo cada execução automática deve buscar (mistura seed + derivados).",
    },
    {
        "key": "discovery.auto_derived_term_min_freq",
        "value": "3",
        "value_type": "int",
        "description": "Frequência mínima de uma palavra em títulos de canais já descobertos para virar termo derivado de busca.",
    },
    # -------------------------------------------------------------
    # Sugestões automáticas (recomendações exibidas em Monitoramento > Sugestões)
    # São APENAS recomendações — nunca executam ação no canal.
    # -------------------------------------------------------------
    {
        "key": "suggestions.monitor_min_vpd",
        "value": "10000",
        "value_type": "int",
        "description": "VPD recente mínimo para um canal descoberto ser SUGERIDO para monitoramento.",
    },
    {
        "key": "suggestions.monitor_max_age_days",
        "value": "60",
        "value_type": "int",
        "description": "Idade máxima do canal (em dias desde a criação) para ser SUGERIDO para monitoramento.",
    },
    {
        "key": "suggestions.monitor_breakout_max_subscribers",
        "value": "10000",
        "value_type": "int",
        "description": "Máximo de inscritos para sinalizar canal recém-criado com vídeo desproporcional nas sugestões.",
    },
    {
        "key": "suggestions.monitor_breakout_max_age_days",
        "value": "30",
        "value_type": "int",
        "description": "Idade máxima do canal para a regra de breakout precoce nas sugestões.",
    },
    {
        "key": "suggestions.monitor_breakout_max_video_count",
        "value": "3",
        "value_type": "int",
        "description": "Máximo de vídeos totais no canal para considerar breakout precoce nas sugestões.",
    },
    {
        "key": "suggestions.monitor_breakout_min_views",
        "value": "50000",
        "value_type": "int",
        "description": "Views mínimas do melhor vídeo descoberto para marcar breakout precoce nas sugestões.",
    },
    {
        "key": "suggestions.monitor_breakout_min_vpd",
        "value": "2000",
        "value_type": "int",
        "description": "VPD mínimo do melhor vídeo descoberto para breakout precoce nas sugestões.",
    },
    {
        "key": "suggestions.dead_min_days_no_uploads",
        "value": "60",
        "value_type": "int",
        "description": "Dias sem novos uploads (TrackedVideo recente) para um canal ser candidato a 'morto'.",
    },
    {
        "key": "suggestions.dead_max_vpd",
        "value": "2000",
        "value_type": "int",
        "description": "VPD recente máximo para um canal ser candidato a 'morto'. As 3 regras de morto valem em conjunto (E lógico).",
    },
]


def run() -> None:
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        for item in DEFAULT_SETTINGS:
            key = item["key"]
            existing = db.query(AppSetting).filter_by(key=key).one_or_none()
            if existing:
                skipped += 1
                continue
            db.add(
                AppSetting(
                    key=key,
                    value=item.get("value"),
                    value_type=item.get("value_type", "str"),
                    is_secret=item.get("is_secret", False),
                    description=item.get("description"),
                )
            )
            inserted += 1
        db.commit()
        print(f"Seed concluído: {inserted} inseridas, {skipped} já existiam.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
