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

## Health Endpoint

```http
GET /api/v1/health
```

The health endpoint confirms that the FastAPI service is reachable. It does
not run recommendation scoring and does not expose secrets, database URLs, or
environment values.

### Health Response

```json
{
  "status": "ok",
  "service": "GIFTYZI Recommendation Engine",
  "version": "0.1.0"
}
```

## Official Request

```json
{
  "status": "active",
  "budget_max": 80,
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
| `budget_max` | User budget maximum. When provided, products must satisfy `price <= budget_max`. | Optional |
| `hard_filters.recipient_gender` | Strict recipient gender filter. | Optional |
| `hard_filters.age_group` | Strict age group filter. | Optional |
| `soft_tags.event` | Scored event preference. | Optional |
| `soft_tags.relationship` | Scored relationship preference. | Optional |
| `soft_tags.theme` | Scored theme preference. | Optional |
| `soft_tags.gift_benefit` | Scored gift benefit preference. | Optional |
| `soft_tags.*[].intensity` | User signal strength. | Required per soft tag |
| `facet_weights` | Facet weights transported from Next.js `Facet.weight`. | Optional |
| `limit` | Page size requested by the client. Clamped to `RECOMMENDATION_MAX_LIMIT`. | Optional |
| `offset` | Zero-based result offset for stateless pagination. | Optional |

`budget_max`, `soft_tags.theme`, and `soft_tags.gift_benefit` are optional in
the request payload. Omitting them only means the user did not provide these
signals. It does not change their architectural role or scoring weight: when
they are present, they are applied exactly like any other budget constraint or
soft scoring facet.

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
  "total_candidates": 0,
  "returned_count": 0,
  "limit": 24,
  "offset": 0,
  "has_more": false,
  "next_offset": null,
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
    "limit": 24,
    "offset": 0,
    "total_candidates": 0,
    "returned_count": 0,
    "has_more": false,
    "next_offset": null,
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
| `total_candidates` | Number of candidates after HARD filters, scoring, and ranking, before pagination. |
| `returned_count` | Number of products returned in the current page. |
| `limit` | Effective limit after default fallback and max clamp. |
| `offset` | Effective offset applied to ranked results. |
| `has_more` | `true` when another stateless page is available. |
| `next_offset` | Offset to send for the next page, or `null` when the current page is final. |
| `query_interpretation` | Echoes the structured signals received by FastAPI. No NLP interpretation is performed in v1. |
| `hard_constraints` | Lists strict constraints actually applied by the engine. |
| `soft_preferences` | Lists scored preferences and transmitted facet weights. |
| `best_matches` | Current page of ranked recommended products. Each match keeps `_score`; v1 also includes minimal `_explanation`. |
| `related_ideas` | Empty in v1. Must never violate hard filters when implemented later. |
| `relaxations_applied` | Empty in v1. No relaxation is invented. |
| `suggested_reformulations` | Empty in v1. No reformulation is invented. |
| `fallback` | `null` when matches exist; explicit `no_matches` object when no product matches. |
| `meta` | Public response metadata including result count, limit, and contract version. |
| `debug_info` | Non-sensitive engine information only. No secrets, URLs, tokens, or environment variables. |

## Pagination

Pagination is stateless and is applied after scoring and ranking:

1. Fetch all candidates valid for DB-level HARD filters.
2. Apply request-level HARD filters.
3. Score every remaining candidate.
4. Sort/rank every scored candidate deterministically.
5. Return `ranked_results[offset : offset + limit]`.

The engine uses these environment variables:

```env
RECOMMENDATION_DEFAULT_LIMIT=24
RECOMMENDATION_MAX_LIMIT=100
```

`RECOMMENDATION_RESULT_LIMIT` is deprecated. If `RECOMMENDATION_DEFAULT_LIMIT`
is absent, a positive numeric legacy value is still accepted as a migration
fallback. Legacy unbounded values such as `all` fall back to the safe default.

Page 1 request:

```json
{
  "status": "active",
  "budget_max": 80,
  "limit": 24,
  "offset": 0
}
```

Next page request:

```json
{
  "status": "active",
  "budget_max": 80,
  "limit": 24,
  "offset": 24
}
```

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
