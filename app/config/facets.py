"""
Snapshot FastAPI de la taxonomie réelle Next.js.

Source de vérité amont :
- Next.js DB Prisma Facet/Tag
- Export machine-readable : docs/recommendation/real-taxonomy-v1.json
- Date d'export documentée côté Next.js : 2026-04-24

Les tables de similarité FastAPI ne doivent utiliser que les facettes SOFT
moteur v1 listées dans SIMILARITY_FACETS.
"""

HARD_FACET_SLUGS: dict[str, frozenset[str]] = {
    "age_group": frozenset(
        {
            "adolescent",
            "adulte",
            "bebe",
            "enfant",
            "senior",
        }
    ),
    "recipient_gender": frozenset(
        {
            "female",
            "male",
            "unisex",
        }
    ),
}

SOFT_FACET_SLUGS: dict[str, frozenset[str]] = {
    "event": frozenset(
        {
            "anniversaire",
            "bapteme",
            "fete-des-meres",
            "fete-des-peres",
            "juste-faire-plaisir",
            "mariage",
            "naissance",
            "noel",
            "saint-valentin",
        }
    ),
    "relationship": frozenset(
        {
            "ami",
            "collegue",
            "enfant-relation",
            "mere",
            "partenaire",
            "pere",
            "un-proche",
        }
    ),
    "theme": frozenset(
        {
            "art",
            "beauty",
            "decorative",
            "drink",
            "eco-friendly",
            "experience",
            "fashion",
            "food",
            "funny",
            "handmade",
            "luxury",
            "minimalist",
            "modern",
            "personalized",
            "practical",
            "romantic",
            "tech",
            "traditional",
            "travel",
            "wellness",
        }
    ),
    "gift_benefit": frozenset(
        {
            "collectible",
            "decorative-benefit",
            "educational",
            "emotional",
            "entertaining",
            "experiential",
            "long-lasting",
            "memorable",
            "surprising",
            "useful",
        }
    ),
}

OUT_OF_SCOPE_FACET_SLUGS: dict[str, frozenset[str]] = {
    "category": frozenset(
        {
            "accessories",
            "bijoux",
            "books",
            "clothing",
            "electronics",
            "flowers",
            "food-category",
            "gadgets",
            "home-decor",
            "parfum",
            "toys",
        }
    ),
    "recipient_personality": frozenset(
        {
            "adventurous",
            "creative",
            "funny-personality",
            "luxury-lover",
            "nature-lover",
            "serious",
            "sporty",
            "tech-lover",
        }
    ),
}

ENGINE_V1_FACETS: frozenset[str] = frozenset(
    {
        *HARD_FACET_SLUGS,
        *SOFT_FACET_SLUGS,
    }
)

SIMILARITY_FACETS: tuple[str, ...] = (
    "event",
    "relationship",
    "theme",
    "gift_benefit",
)
