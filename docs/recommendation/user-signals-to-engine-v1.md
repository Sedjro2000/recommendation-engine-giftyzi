# User Signals To Engine v1

Phase 2.5 - Bloc 7 FastAPI.

This document maps the validated Next.js recommendation route fields to the
FastAPI recommendation engine v1 contract and runtime behavior.

## Supported Signals

| Signal Next.js | Champ FastAPI | Traitement FastAPI | Statut |
|---|---|---|---|
| `occasion` | `soft_tags.event` | Used in soft scoring through the `event` similarity table. The user tag intensity and `facet_weights.event` both affect the contribution. | SUPPORTÉ |
| `relationship` | `soft_tags.relationship` | Used in soft scoring through the `relationship` similarity table. The user tag intensity and `facet_weights.relationship` both affect the contribution. | SUPPORTÉ |
| `theme` | `soft_tags.theme` | Used in soft scoring through the `theme` similarity table. The user tag intensity and `facet_weights.theme` both affect the contribution. | SUPPORTÉ |
| `giftBenefit` | `soft_tags.gift_benefit` | Used in soft scoring through the `gift_benefit` similarity table. The user tag intensity and `facet_weights.gift_benefit` both affect the contribution. | SUPPORTÉ |
| `recipientGender` | `hard_filters.recipient_gender` | Applied as a strict blocking filter. Products without at least one matching `recipient_gender` are excluded. | SUPPORTÉ |
| `ageGroup` | `hard_filters.age_group` | Applied as a strict blocking filter. Products without at least one matching `age_group` are excluded. | SUPPORTÉ |
| `budgetMax` | `price` | Applied as a DB-level budget filter with `product.price <= request.price`. | SUPPORTÉ |
| SOFT explicit user intent | `soft_tags.*[].intensity` | Multiplies the soft match contribution. FastAPI accepts only the validated intensity policy values. | SUPPORTÉ |
| Facet weights from DB Next.js `Facet.weight` | `facet_weights` | Multiplies soft facet contributions for `event`, `relationship`, `theme`, and `gift_benefit`; absent weight falls back explicitly to neutral `1.0`. | SUPPORTÉ |

## Rejected Signals

| Signal Next.js | Champ FastAPI | Traitement FastAPI | Statut |
|---|---|---|---|
| `category` | `category` | Rejected by the strict root request schema. Also rejected if sent inside `soft_tags` or `facet_weights`. | REJETÉ |
| `recipient_personality` | `recipient_personality` | Rejected by the strict root request schema. Also rejected if sent inside `soft_tags` or `facet_weights`. | REJETÉ |
| `keywords` | `keywords` | Rejected by the strict root request schema. | REJETÉ |
| `type` | `type` | Rejected by the strict root request schema. | REJETÉ |
| Unknown field | Any unknown key | Rejected by Pydantic `extra="forbid"` on request and nested models. | REJETÉ |

## Existing FastAPI Contract Fields

| Signal Next.js | Champ FastAPI | Traitement FastAPI | Statut |
|---|---|---|---|
| INFORMATION_MANQUANTE | `product_id` | Accepted by the existing FastAPI contract and used for API logging only. It is not part of the Bloc 7 user signals emitted by Next.js. | NON_SUPPORTÉ_V1 |
| INFORMATION_MANQUANTE | `status` | Accepted by the existing FastAPI contract and used as a DB-level eligibility filter. | SUPPORTÉ |
| INFORMATION_MANQUANTE | `stock` | Accepted by the existing FastAPI contract, but candidate stock filtering is based on product stock in DB (`stock > 0`), not on `request.stock`. | NON_SUPPORTÉ_V1 |

## Runtime Guarantees

- Every accepted Bloc 7 user signal has a runtime effect: filter, ranking change, intensity multiplier, or facet-weight multiplier.
- No SOFT signal is accepted then ignored silently.
- `category`, `recipient_personality`, `keywords`, `type`, and unknown fields are rejected instead of ignored.
- Hard filters remain strict filters and are not used as soft scoring weights.
- Soft tags are used for scoring and are not converted into hard filters.
- Missing `facet_weights` for a used SOFT facet falls back explicitly to `1.0`, the neutral weight.
