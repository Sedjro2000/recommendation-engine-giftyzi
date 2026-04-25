# Similarity Sensitive Relations v1

## Contexte

Audit FastAPI Phase 2.5 Bloc 6.

Ce document liste les similarites fortes des tables FastAPI, definies par un score `>= 0.8` hors match exact.

Source taxonomique de reference : export Next.js `docs/recommendation/real-taxonomy-v1.json`.

## Relations Sensibles

| Facette | Source | Cible | Score | Raison / justification |
| --- | --- | --- | ---: | --- |
| `event` | `anniversaire` | `juste-faire-plaisir` | `0.8` | A VALIDER PRODUIT |
| `event` | `bapteme` | `naissance` | `0.8` | Evenements familiaux lies a l'arrivee ou la celebration d'un enfant. |
| `event` | `juste-faire-plaisir` | `anniversaire` | `0.8` | A VALIDER PRODUIT |
| `event` | `juste-faire-plaisir` | `noel` | `0.8` | A VALIDER PRODUIT |
| `event` | `naissance` | `bapteme` | `0.8` | Evenements familiaux lies a l'arrivee ou la celebration d'un enfant. |
| `event` | `noel` | `juste-faire-plaisir` | `0.8` | A VALIDER PRODUIT |
| `relationship` | `ami` | `un-proche` | `0.8` | `un-proche` est une relation generale pouvant inclure un ami. |
| `relationship` | `un-proche` | `ami` | `0.8` | `un-proche` est une relation generale pouvant inclure un ami. |
| `theme` | `experience` | `travel` | `0.8` | Le voyage est une forme d'experience cadeau. |
| `theme` | `handmade` | `personalized` | `0.8` | Un cadeau fait main peut souvent etre personnalise. |
| `theme` | `modern` | `tech` | `0.8` | A VALIDER PRODUIT |
| `theme` | `personalized` | `handmade` | `0.8` | Un cadeau personnalise peut souvent etre fait main. |
| `theme` | `tech` | `modern` | `0.8` | A VALIDER PRODUIT |
| `theme` | `travel` | `experience` | `0.8` | Le voyage est une forme d'experience cadeau. |
| `gift_benefit` | `emotional` | `memorable` | `0.9` | Un benefice emotionnel peut rendre le cadeau memorable. |
| `gift_benefit` | `experiential` | `memorable` | `0.8` | Une experience cadeau peut etre memorable. |
| `gift_benefit` | `long-lasting` | `useful` | `0.8` | A VALIDER PRODUIT |
| `gift_benefit` | `memorable` | `emotional` | `0.9` | Un cadeau memorable peut avoir une forte dimension emotionnelle. |
| `gift_benefit` | `memorable` | `experiential` | `0.8` | Une experience cadeau peut etre memorable. |
| `gift_benefit` | `useful` | `long-lasting` | `0.8` | A VALIDER PRODUIT |

## Points Produit A Valider

- `event`: relations fortes impliquant `juste-faire-plaisir`.
- `theme`: proximite forte entre `modern` et `tech`.
- `gift_benefit`: proximite forte entre `useful` et `long-lasting`.
