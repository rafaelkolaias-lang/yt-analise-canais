# -*- coding: utf-8 -*-
"""Detecção de idioma, mutação e aprendizado de termos de busca."""
import random


PT_STOPWORDS = {
    "de", "da", "do", "das", "dos", "a", "o", "e", "é", "em", "uma", "um", "no", "na", "para", "por", "com", "as", "os",
    "que", "ao", "à", "se", "sobre", "como", "sua", "seu", "são", "ou", "mais", "menos", "parte", "episódio", "completo",
}

PT_SW = {
    "de", "da", "do", "das", "dos", "uma", "um", "no", "na", "para", "por", "com", "as", "os",
    "que", "ao", "à", "se", "sobre", "como", "sua", "seu", "são", "ou", "mais", "menos",
    "história", "mistérios", "civilizações", "arqueologia", "vida", "universo", "tecnologia",
}
EN_SW = {
    "the", "of", "and", "to", "in", "for", "with", "on", "by", "about", "from", "history",
    "explained", "analysis", "documentary", "universe", "science", "technology",
}
ES_SW = {
    "de", "del", "la", "el", "las", "los", "para", "por", "con", "que", "más", "menos",
    "historia", "misterios", "civilizaciones", "arqueología", "vida", "universo", "tecnología",
}


def _guess_lang(term: str):
    t = term.strip().lower()
    if any(ch in t for ch in "ãõçáéíóúàâêô"):
        return "pt"
    if any(ch in t for ch in "áéíóúñ"):
        pass
    ws = set(w for w in t.replace("/", " ").split() if w)
    pt_score = len(ws & PT_SW)
    en_score = len(ws & EN_SW)
    es_score = len(ws & ES_SW)
    scores = {"pt": pt_score, "en": en_score, "es": es_score}
    lang = max(scores, key=scores.get)
    return lang if scores[lang] > 0 else None


def filter_terms_by_lang(terms, selected_langs):
    if not selected_langs:
        return terms
    out = []
    for t in terms:
        lg = _guess_lang(t)
        if lg is None:
            out.append(t)
        elif lg in selected_langs:
            out.append(t)
    return out


def mutate_terms(pool_base, pool_learned, k):
    suffixes = ["explicado", "completo", "2025", "pt-br", "análise", "documentário", "explained"]
    bag = set()
    for t in pool_base + pool_learned:
        bag.add(t)
        if " " in t:
            for s in suffixes:
                bag.add(f"{t} {s}")
    bag = list(bag)
    random.shuffle(bag)
    return bag[:k]


def extract_learned_terms_from_titles(titles, top_k=20):
    tokens = []
    for t in titles:
        words = [w.strip(".,:;!?()[]\"'").lower() for w in t.split()]
        words = [w for w in words if w and w not in PT_STOPWORDS and len(w) >= 3]
        tokens.append(words)
    bigrams = {}
    for ws in tokens:
        for i in range(len(ws) - 1):
            bg = f"{ws[i]} {ws[i + 1]}"
            if any(x in PT_STOPWORDS for x in bg.split()):
                continue
            bigrams[bg] = bigrams.get(bg, 0) + 1
    return [w for w, _ in sorted(bigrams.items(), key=lambda x: -x[1])[:top_k]]


def language_ok(vdict, allowed_langs, strict: bool = False):
    """
    Pós-filtro por idioma.
    - allowed_langs None/[]: aceita todos.
    - strict=False (padrão): vídeos sem metadados de idioma são aceitos.
    - strict=True: vídeos sem metadados de idioma são rejeitados.
    """
    if not allowed_langs:
        return True

    cand = (vdict.get("defaultAudioLanguage") or vdict.get("defaultLanguage") or "").lower().strip()
    if not cand:
        return not strict

    base = cand.split("-")[0]
    return (cand in allowed_langs) or (base in allowed_langs)
