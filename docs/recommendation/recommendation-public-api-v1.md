# Recommendation Public API v1

Phase 2.5 - Bloc 8 FastAPI.

This document describes the public recommendation contract exposed by FastAPI.
It separates the user recommendation request from product candidate data.

## User Recommendation Request vs Product Projection

The public request represents the user's constraints and preferences.

Product candidate fields such as `product_id` and `stock` are not user request
fields. They belong to products loaded by the engine from the repository or DB.

FastAPI still applies `stock > 0` internally to candidate products, but the
caller must not send `stock` as part of the recommendation request.

## Endpoint

```http
POST /api/v1/recommend
```

## Official Request

```json
{
  "status": "active",
  "price": 80,
  "hard_filters": {
    "recipient_gender": ["female"],
    "age_group": ["adulte"]
  },
  "soft_tags": {
    "event": [{ "slug": "anniversaire", "intensity": 1.0 }],
    "relationship": [{ "slug": "partenaire", "intensity": 1.0 }],
    "theme": [{ "slug": "romantic", "intensity": 1.0 }],
    "gift_benefit": [{ "slug": "emotional", "intensity": 1.0 }]
  },
  "facet_weights": {
    "event": 1.3,
    "relationship": 1.1,
    "theme": 0.9,
    "gift_benefit": 1.0
  }
}
```

## Request Semantics

| Field | Meaning | Status |
|---|---|---|
| `status` | Product eligibility status filter, usually `active`. | Required |
| `price` | User budget maximum, mapped from `budgetMax`. Products must satisfy `price <= budget_max`. | Required |
| `hard_filters.recipient_gender` | Strict recipient gender filter. | Optional |
| `hard_filters.age_group` | Strict age group filter. | Optional |
| `soft_tags.event` | Scored event preference. | Optional |
| `soft_tags.relationship` | Scored relationship preference. | Optional |
| `soft_tags.theme` | Scored theme preference. | Optional |
| `soft_tags.gift_benefit` | Scored gift benefit preference. | Optional |
| `soft_tags.*[].intensity` | User signal strength. | Required per soft tag |
| `facet_weights` | Facet weights transported from Next.js `Facet.weight`. | Optional |

## Forbidden Request Fields

The request schema uses `extra="forbid"`. These fields are rejected if sent:

- `product_id`
- `stock`
- `category`
- `recipient_personality`
- `keywords`
- `type`
- Any unknown field

## Official Response

```json
{
  "query_interpretation": {
    "normalized_query": null,
    "detected_signals": {
      "event": ["anniversaire"],
      "relationship": ["partenaire"],
      "theme": ["romantic"],
      "gift_benefit": ["emotional"],
      "recipient_gender": ["female"],
      "age_group": ["adulte"],
      "budget_max": 80
    },
    "confidence": {}
  },
  "hard_constraints": {
    "status": "active",
    "budget_max": 80,
    "availability": "in_stock",
    "recipient_gender": ["female"],
    "age_group": ["adulte"]
  },
  "soft_preferences": {
    "event": ["anniversaire"],
    "relationship": ["partenaire"],
    "theme": ["romantic"],
    "gift_benefit": ["emotional"],
    "facet_weights": {
      "event": 1.3,
      "relationship": 1.1,
      "theme": 0.9,
      "gift_benefit": 1.0
    }
  },
  "best_matches": [],
  "related_ideas": [],
  "relaxations_applied": [],
  "suggested_reformulations": [],
  "fallback": null,
  "meta": {
    "result_count": 0,
    "limit": 10,
    "contract_version": "recommendation_public_v1"
  },
  "debug_info": {
    "scoring_formula": "similarity * product_intensity * user_intensity * facet_weight",
    "stock_filter": "stock > 0",
    "exact_match_score": 1.0
  }
}
```

## Response Block Semantics

| Block | Semantics |
|---|---|
| `query_interpretation` | Echoes the structured signals received by FastAPI. No NLP interpretation is performed in v1. |
| `hard_constraints` | Lists strict constraints actually applied by the engine. |
| `soft_preferences` | Lists scored preferences and transmitted facet weights. |
| `best_matches` | Ranked recommended products. Each match keeps `_score`; v1 also includes minimal `_explanation`. |
| `related_ideas` | Empty in v1. Must never violate hard filters when implemented later. |
| `relaxations_applied` | Empty in v1. No relaxation is invented. |
| `suggested_reformulations` | Empty in v1. No reformulation is invented. |
| `fallback` | `null` when matches exist; explicit `no_matches` object when no product matches. |
| `meta` | Public response metadata including result count, limit, and contract version. |
| `debug_info` | Non-sensitive engine information only. No secrets, URLs, tokens, or environment variables. |

## Fallback

When no product matches the applied constraints, FastAPI returns:

```json
{
  "reason": "no_matches",
  "message": "Aucun produit ne correspond aux contraintes actuelles."
}
```

## Match Explanation v1

Each product in `best_matches` keeps `_score` and receives a minimal
`_explanation`:

```json
{
  "matched_hard_filters": {},
  "matched_soft_tags": {},
  "score_breakdown": {
    "total_score": 4.19,
    "detail_level": "minimal_v1",
    "formula": "similarity * product_intensity * user_intensity * facet_weight"
  }
}
```

The v1 breakdown does not expose detailed per-facet numeric contributions.

## v1 Limits

- No NLP.
- `related_ideas` is empty.
- `relaxations_applied` is empty.
- `suggested_reformulations` is empty.
- No ML, embeddings, or vector search.
- No automatic aliasing or normalization of invalid slugs.
