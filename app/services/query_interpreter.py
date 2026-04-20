import logging

logger = logging.getLogger(__name__)

OCCASION_KEYWORDS: dict[str, list[str]] = {
    "anniversaire": ["anniversaire", "birthday", "anniv"],
    "noel": ["noël", "noel", "christmas", "xmas"],
    "mariage": ["mariage", "wedding", "mariée", "mariee"],
    "saint-valentin": ["saint-valentin", "valentin", "valentine"],
    "fete-des-meres": ["fête des mères", "fete des meres", "mother's day", "mothers day"],
    "fete-des-peres": ["fête des pères", "fete des peres", "father's day", "fathers day"],
}


def interpret_query(query: str) -> list[str]:
    """
    Detect occasion keywords in a natural language query.
    Returns a list of matched occasion identifiers.
    """
    query_lower = query.lower()
    detected: list[str] = []

    for occasion, keywords in OCCASION_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            detected.append(occasion)
            logger.debug(f"[QueryInterpreter] Detected occasion: '{occasion}'")

    if not detected:
        logger.debug("[QueryInterpreter] No specific occasion detected in query.")

    return detected
