"""
Auto-discovery service — etapa de descoberta automática que roda DEPOIS do
sync normal. Não substitui o sync nem é disparada pelo usuário; é
orquestrada por `sync_service.run_sync` ao final de cada execução.

Princípios:
  - Tem orçamento próprio: no máximo `discovery.auto_quota_pct` (default 50%)
    da cota diária total (todas as keys somadas).
  - Mistura termos seed (configuráveis em `discovery.auto_keywords`) com
    termos DERIVADOS automaticamente de palavras frequentes nos títulos dos
    canais já descobertos (reduz pontos cegos sem depender de o usuário
    lembrar de novos termos).
  - Reusa o `discovery_service.run_discovery` existente — não duplica a
    lógica de busca/filtro/persistência.
  - Tolera ausência de API key e falhas individuais sem propagar exceção
    ao `sync_service`.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import Channel, DiscoveryResultChannel, DiscoveryRun
from app.services import discovery_service, settings_reader, youtube_client


# Custo aproximado por termo num run (search.list em 1 página × ~3 idiomas
# = 100×3 units; depois 1 unit p/ videos.list e 1 p/ channels.list, ignorável).
# Dimensionado para ser conservador: prefere subestimar quantos termos cabem
# do que estourar o orçamento.
ESTIMATED_COST_PER_TERM = 300

# Palavras descartadas ao derivar termos (stopwords pt + en, lowercase).
_STOPWORDS = {
    # pt
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na",
    "por", "para", "com", "sem", "que", "se", "um", "uma", "uns", "umas", "ao",
    "à", "às", "aos", "como", "mais", "menos", "muito", "pouco", "tudo", "nada",
    "ser", "ter", "estar", "fazer", "vai", "ir", "vou", "você", "voce", "vc",
    # en
    "the", "and", "or", "of", "to", "in", "on", "at", "for", "with", "from",
    "by", "as", "is", "are", "was", "were", "be", "been", "being", "this",
    "that", "these", "those", "it", "its", "we", "you", "they", "i", "my",
    "your", "their", "our", "his", "her", "an", "a", "but", "if", "so", "not",
    "no", "yes", "do", "does", "did", "can", "could", "will", "would", "should",
    # comuns no YouTube
    "video", "vídeo", "channel", "canal", "shorts", "live", "vlog", "podcast",
    "official", "oficial", "ep", "episode", "ep1", "feat", "ft",
}

# Quebra em tokens alfanuméricos (suporta acentos via \w em re.UNICODE — default Py3).
_WORD_RE = re.compile(r"[a-záàâãéêíóôõúüç0-9]{4,}", re.IGNORECASE)


def _read_seed_terms(db: Session) -> list[str]:
    """Lê `discovery.auto_keywords` (texto multilinha) e devolve lista limpa."""
    raw = settings_reader.get_str(db, "discovery.auto_keywords", "") or ""
    out: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        term = line.strip()
        if not term:
            continue
        norm = term.lower()
        if norm in seen:
            continue
        seen.add(norm)
        out.append(term)
    return out


def derive_terms_from_recent_channels(
    db: Session, max_terms: int = 30, min_freq: int = 3
) -> list[str]:
    """
    Extrai palavras frequentes dos títulos dos canais já no monitoramento +
    dos resultados de discovery anteriores. Stopwords filtradas. Retorna
    lista ordenada por frequência (descendente), limitada a `max_terms`.
    Palavras com frequência < `min_freq` descartadas pra evitar ruído.
    """
    titles: list[str] = []

    monitored = db.query(Channel.title).all()
    titles.extend(t[0] for t in monitored if t[0])

    discovered = (
        db.query(DiscoveryResultChannel.title)
        .order_by(desc(DiscoveryResultChannel.captured_at))
        .limit(500)
        .all()
    )
    titles.extend(t[0] for t in discovered if t[0])

    counter: Counter[str] = Counter()
    for title in titles:
        for match in _WORD_RE.findall(title):
            word = match.lower()
            if word in _STOPWORDS:
                continue
            counter[word] += 1

    return [w for w, freq in counter.most_common(max_terms) if freq >= min_freq]


def pick_terms_for_run(db: Session) -> list[str]:
    """
    Monta a lista final de termos para uma execução automática.

    Estratégia: pega 70% dos termos de seed (rotacionando por hora pra não
    repetir os mesmos sempre) + 30% derivados. Total bound em
    `discovery.auto_max_terms_per_run`.
    """
    max_terms = settings_reader.get_int(db, "discovery.auto_max_terms_per_run", 30)
    min_freq = settings_reader.get_int(db, "discovery.auto_derived_term_min_freq", 3)

    seed = _read_seed_terms(db)
    derived = derive_terms_from_recent_channels(db, max_terms=max_terms, min_freq=min_freq)

    if not seed and not derived:
        return []

    seed_quota = max(1, int(max_terms * 0.7))
    derived_quota = max(0, max_terms - seed_quota)

    # Rotação determinística do seed: usa hora atual como offset, assim cada
    # ciclo automático pega uma janela diferente sem precisar persistir
    # estado de "qual foi o último usado".
    if seed:
        offset = (datetime.utcnow().hour * 7) % len(seed)
        rotated = seed[offset:] + seed[:offset]
        seed_picked = rotated[:seed_quota]
    else:
        seed_picked = []

    # Deduplica derived contra seed (case-insensitive) para evitar re-busca
    # do mesmo termo na mesma run.
    seed_lower = {t.lower() for t in seed_picked}
    derived_picked: list[str] = []
    for term in derived:
        if term.lower() in seed_lower:
            continue
        derived_picked.append(term)
        if len(derived_picked) >= derived_quota:
            break

    return seed_picked + derived_picked


def _calculate_budget(db: Session) -> int:
    """
    Orçamento total em units para esta execução automática.

    `daily_quota_per_key × num_keys × auto_quota_pct`.

    Usa o número de keys vivas (decifradas) — se zero, retorna 0 e o caller
    deve abortar sem chamar a API.
    """
    pct = settings_reader.get_float(db, "discovery.auto_quota_pct", 0.5)
    pct = max(0.0, min(1.0, pct))
    if pct <= 0:
        return 0

    try:
        client = youtube_client.build_from_db(db)
    except youtube_client.NoAPIKeyConfigured:
        return 0

    num_keys = len(client.keys)
    if num_keys == 0:
        return 0

    return int(client.daily_quota * num_keys * pct)


def run_auto_discovery(db: Session) -> Optional[DiscoveryRun]:
    """
    Executa um ciclo de descoberta automática. Retorna o `DiscoveryRun`
    criado, ou None se a execução foi pulada (sem termos / sem orçamento /
    feature desligada).

    NUNCA propaga exceção — o caller (sync_service) já registrou seu próprio
    sucesso e não pode ser invalidado por uma falha aqui.
    """
    if not settings_reader.get_bool(db, "discovery.auto_enabled", True):
        return None

    budget = _calculate_budget(db)
    if budget <= 0:
        return None

    terms = pick_terms_for_run(db)
    if not terms:
        return None

    # Corta termos para caber no orçamento conservador.
    max_terms_by_budget = max(1, budget // ESTIMATED_COST_PER_TERM)
    if len(terms) > max_terms_by_budget:
        terms = terms[:max_terms_by_budget]

    defaults = discovery_service.load_default_filters(db)
    filters = discovery_service.DiscoveryFilters(
        terms=terms,
        window_days=defaults["window_days"],
        min_views=defaults["min_views"],
        min_vpd=defaults["min_vpd"],
        min_duration_seconds=defaults["min_duration_seconds"],
        languages=defaults["languages"],
        # Auto-discovery pega apenas 1 página por termo pra estender o
        # alcance (mais termos) em vez de aprofundar (mais páginas).
        pages_per_term=1,
        # Mesmos limites de idade do canal aplicados na descoberta manual,
        # vindos das mesmas settings (channel.min/max_age_days).
        min_channel_age_days=defaults["min_channel_age_days"],
        max_channel_age_days=defaults["max_channel_age_days"],
    )

    try:
        return discovery_service.run_discovery(db, filters)
    except Exception:
        # Já foi marcado como `failed` no banco pelo run_discovery; não
        # propaga.
        return None
