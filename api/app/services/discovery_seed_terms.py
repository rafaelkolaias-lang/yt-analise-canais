"""
Seed inicial de termos para descoberta automática.

~100 termos cobrindo nichos genéricos em pt-BR e en, ponto de partida pro
usuário editar via UI. A lista vive em código (não no banco) só pra ficar
versionada — o valor real ativo fica em `app_settings.discovery.auto_keywords`,
preenchido por seed.py se a key não existir.

Critérios de seleção: nichos com volume comprovado, baixo crowding em alguns
recortes, evergreen (não dependem de notícia do dia). Mistura formatos
(tutorial, story, ranking) pra discovery não viesar pra um padrão só.
"""
from __future__ import annotations


SEED_TERMS_PT: list[str] = [
    # Finanças / renda
    "renda extra online",
    "investir pouco dinheiro",
    "como sair das dívidas",
    "vida financeira",
    "passivo mensal dividendos",
    # IA / tech
    "inteligência artificial 2026",
    "chatgpt para iniciantes",
    "automação no n8n",
    "criar app sem código",
    "ferramentas de ia",
    # Saúde mental / autoajuda
    "ansiedade tratamento natural",
    "rotina matinal produtiva",
    "produtividade trabalho remoto",
    "como dormir melhor",
    "gestão emocional",
    # Histórias / mistério
    "histórias de terror reais",
    "mistérios sem solução",
    "casos verídicos crime",
    "documentário verdadeiro",
    "lendas urbanas brasileiras",
    # Mundo cripto / web3
    "bitcoin halving 2028",
    "stablecoin para iniciantes",
    "carteira fria criptomoedas",
    # Estudos / carreira
    "como aprender inglês sozinho",
    "carreira em tecnologia 2026",
    "concursos públicos federais",
    "estudar para enem",
    # Culinária prática
    "receitas low carb",
    "marmita fitness barata",
    "café da manhã rápido",
    # Lifestyle / minimalismo
    "vida minimalista",
    "morar sozinho com pouco",
    "organização da casa",
    # Games / nicho
    "speedrun pokemon",
    "lore dark souls",
    "build wow classic",
    # Ciência popular
    "documentário espaço",
    "buracos negros explicação",
    "evolução humana fatos",
    # Espiritualidade / místico
    "tarot intuitivo",
    "manifestação dinheiro",
    "lei da atração realidade",
    # Crianças / família
    "atividades educativas crianças",
    "homeschooling brasil",
    # Carros / motos
    "review carros 0km",
    "moto custo benefício",
]

SEED_TERMS_EN: list[str] = [
    # Money / personal finance
    "make money online 2026",
    "passive income ideas",
    "personal finance for beginners",
    "stock market explained",
    "real estate investing tips",
    # AI / tech
    "ai tools for productivity",
    "chatgpt advanced prompts",
    "build saas with ai",
    "no code app builder",
    "claude vs chatgpt",
    # Health / fitness
    "home workout no equipment",
    "intermittent fasting guide",
    "sleep optimization",
    "anxiety relief techniques",
    "morning routine productivity",
    # Stories / mystery
    "true scary stories",
    "unsolved mysteries documentary",
    "horror stories animated",
    "creepypasta narration",
    # Learning / career
    "learn coding from scratch",
    "remote jobs that pay well",
    "freelance writing tutorial",
    "language learning hacks",
    # Crypto / web3
    "bitcoin price prediction",
    "ethereum staking guide",
    "defi explained simple",
    # Gaming
    "minecraft survival tips",
    "valorant aim training",
    "elden ring boss guide",
    # Lifestyle / minimalism
    "minimalist lifestyle daily",
    "tiny house tour",
    "digital nomad guide",
    # Science / education
    "space documentary",
    "quantum physics explained",
    "human evolution facts",
    # Self help / mindset
    "stoicism daily practice",
    "discipline beats motivation",
    "deep work focus",
    # Food
    "easy meal prep",
    "low carb recipes",
    "sourdough bread tutorial",
    # Cars / vehicles
    "best cars 2026",
    "ev range comparison",
    # Hobbies
    "watercolor for beginners",
    "guitar fingerstyle lesson",
    "diy woodworking projects",
]


def all_seed_terms() -> list[str]:
    """Lista combinada (pt + en), deduplicada e estável (mantém ordem)."""
    seen: set[str] = set()
    out: list[str] = []
    for term in SEED_TERMS_PT + SEED_TERMS_EN:
        norm = term.strip().lower()
        if norm and norm not in seen:
            seen.add(norm)
            out.append(term.strip())
    return out
