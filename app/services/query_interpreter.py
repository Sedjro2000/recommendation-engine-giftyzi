import logging
from typing import TypedDict

logger = logging.getLogger(__name__)


class QueryContext(TypedDict):
    event: str | None
    relationship: str | None
    theme: str | None
    recipient_gender: str | None


EVENT_KEYWORDS: dict[str, list[str]] = {
    "anniversaire": ["anniversaire", "birthday", "anniv"],
    "noel": ["noël", "noel", "christmas", "xmas"],
    "saint_valentin": ["saint-valentin", "saint valentin", "valentin", "valentine"],
    "fete_des_meres": ["fête des mères", "fete des meres", "mother's day", "mothers day"],
    "fete_des_peres": ["fête des pères", "fete des peres", "father's day", "fathers day"],
    "mariage": ["mariage", "wedding", "mariée", "mariee"],
    "naissance": ["naissance", "naître", "naitre", "nouveau-né", "nouveau né", "newborn"],
    "bapteme": ["baptême", "bapteme", "baptism"],
    "juste_faire_plaisir": ["faire plaisir", "cadeau surprise", "sans raison", "juste parce que"],
}

RELATIONSHIP_KEYWORDS: dict[str, list[str]] = {
    "partenaire": ["partenaire", "copain", "copine", "petit ami", "petite amie", "chéri", "cheri", "chérie", "cherie"],
    "ami": ["mon ami", "mon amie", "meilleur ami", "meilleure amie", "pote", "friend"],
    "collegue": ["collègue", "collegue", "coworker"],
    "mere": ["mère", "mere", "maman", "mom", "mother"],
    "pere": ["père", "pere", "papa", "dad", "father"],
    "enfant": ["enfant", "mon fils", "ma fille", "gamin", "kid", "child"],
    "un_proche": ["un proche", "quelqu'un de proche", "proche"],
}

THEME_KEYWORDS: dict[str, list[str]] = {
    "romantique": ["romantique", "romantic", "amour", "love"],
    "luxe": ["luxe", "luxueux", "premium", "haut de gamme"],
    "amusant": ["amusant", "fun", "drôle", "rigolo", "marrant"],
    "technologie": ["technologie", "tech", "high-tech", "high tech", "gadget", "électronique", "electronique"],
    "bien_etre": ["bien-être", "bien etre", "wellness", "détente", "detente", "spa", "relaxation", "zen"],
    "voyage": ["voyage", "travel", "aventure", "trip", "escapade"],
    "fait_main": ["fait main", "artisanal", "handmade", "personnalisé", "personalise"],
    "minimaliste": ["minimaliste", "épuré", "epure"],
    "traditionnel": ["traditionnel", "classique", "traditional"],
    "decoratif": ["décoratif", "decoratif", "décoration", "decoration"],
}

GENDER_KEYWORDS: dict[str, list[str]] = {
    "female": ["femme", "féminin", "feminine", "elle", "dame", "girl"],
    "male": ["homme", "masculin", "masculine", "lui", "monsieur", "garçon", "garcon", "boy"],
}


def _detect_first(query_lower: str, keyword_map: dict[str, list[str]]) -> str | None:
    """Return the slug of the first keyword map entry that matches the query."""
    for slug, keywords in keyword_map.items():
        if any(kw in query_lower for kw in keywords):
            return slug
    return None


def interpret_query(query: str) -> QueryContext:
    """
    Parse a natural language query and return a structured QueryContext.

    Detects up to one value per facet using keyword matching (first match wins).
    Slugs are normalized to match similarity table keys (underscore format).

    Returns:
        QueryContext with keys: event, relationship, theme, recipient_gender.
        Each value is a slug string or None if not detected.
    """
    query_lower = query.lower()

    context = QueryContext(
        event=_detect_first(query_lower, EVENT_KEYWORDS),
        relationship=_detect_first(query_lower, RELATIONSHIP_KEYWORDS),
        theme=_detect_first(query_lower, THEME_KEYWORDS),
        recipient_gender=_detect_first(query_lower, GENDER_KEYWORDS),
    )

    logger.debug(f"[QueryInterpreter] context={context}")
    return context
