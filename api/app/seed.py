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
