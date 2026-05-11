# Rapport FastAPI — intégration gift_type

## 1. Verdict global
VALIDÉ AVEC RÉSERVES

## 2. Résumé
`gift_type` a été intégré comme facette SOFT de recommandation côté FastAPI. Le contrat accepte désormais `soft_tags.gift_type` au format existant du moteur, la validation des slugs est stricte, le scoring actif applique un bonus SOFT fort, et la lecture projection Mongo expose aussi `gift_type` sans en faire un `hard_filter`.

Le poids final métier utilisé est `20.0` pour `gift_type`. Si `facet_weights.gift_type` est fourni, il doit rester à `20.0`. Si le produit ne porte pas `gift_type`, le pipeline ne plante pas et le score de cette facette reste simplement à `0`.

## 3. Fichiers modifiés
- `app/schemas/recommendation.py`
- `app/config/facets.py`
- `app/config/similarity_loader.py`
- `app/config/similarity/gift_type.json`
- `app/services/best_matches_service.py`
- `app/services/query_understanding_service.py`
- `app/services/ranking_service.py`
- `app/services/similarity_service.py`
- `app/repositories/product_repository.py`
- `tests/integration/test_recommendation_contract.py`
- `tests/integration/test_similarity_tables.py`
- `tests/e2e/test_recommendation_endpoint.py`

## 4. Contrat FastAPI
Le format exact attendu est :

```json
{
  "soft_tags": {
    "gift_type": [
      { "slug": "coffret", "intensity": 1.0 }
    ]
  }
}
```

Le moteur n’introduit pas de nouveau format. `soft_tags.<facet>` reste une liste d’objets `{ "slug": ..., "intensity": ... }`.

## 5. Facet registry
Confirmation :
- `gift_type` existe dans le registry des facettes.
- Slugs autorisés : `coffret`, `kit`, `gift_card`, `subscription`, `experience`
- Weight final : `20.0`
- Type : SOFT

Références :
- `app/config/facets.py`
- `app/schemas/recommendation.py`

## 6. Scoring
`gift_type` est scoré dans le scoring actif du pipeline via `best_matches_service`, pas via un hard filter.

Comportement :
- match exact `gift_type` -> bonus SOFT fort selon le poids `20.0`
- produit sans `gift_type` -> pas de crash, contribution `0`
- produit avec un autre `gift_type` -> pas d’exclusion, pas de bonus exact
- aucun produit matching `gift_type` -> le moteur peut quand même renvoyer des résultats via les autres signaux

Preuve fonctionnelle :
- test e2e de boost de score sur produit `coffret`
- test e2e confirmant que `gift_type` reste SOFT quand aucun produit ne matche

## 7. Similarity
Une table de similarité a été ajoutée pour `gift_type`.

Logique V1 :
- identité stricte -> `1.0`
- toutes les autres combinaisons -> `0.0`

Fichier :
- `app/config/similarity/gift_type.json`

## 8. Query understanding
`gift_type` est conservé depuis `soft_tags` et reflété dans `query_understanding.detected_signals`.

L’extraction NLP n’a pas été ajoutée dans cette étape.

`query_interpreter.py` n’est pas branché dans le pipeline actif. Le pipeline actif appelle `query_understanding_service(request)` depuis `app/orchestrator/recommendation_pipeline.py`.

## 9. Tests ajoutés/modifiés
- Contrat accepte `gift_type`
- Contrat rejette un slug `gift_type` inconnu
- Contrat rejette un `facet_weights.gift_type` différent de `20.0`
- Registry et poids `gift_type` vérifiés
- Table de similarité `gift_type` vérifiée
- Endpoint complet avec `gift_type`
- Scoring : un produit `coffret` score mieux
- `gift_type` reste SOFT si aucun produit ne matche
- produit sans `gift_type` ne casse pas le pipeline

## 10. Résultat des commandes
- `docker compose run --rm api python -m pytest tests/integration/test_recommendation_contract.py -q`
  - résultat : `10 passed`
- `docker compose run --rm api python -m pytest tests/e2e/test_recommendation_endpoint.py -q`
  - résultat : `5 passed`
- `docker compose run --rm api python -m pytest -q`
  - résultat : échec hors scope pendant la collecte de `tests/test_giftyzi.py`
  - erreur : `ImportError: cannot import name 'FacetWeights' from 'app.api.schemas'`
  - analyse : il s’agit d’une suite legacy non alignée avec l’API/schéma FastAPI actifs de ce chantier

## 11. Risques restants
- Extraction NLP `gift_type` non branchée
- Les produits non encore taggés `gift_type` ne bénéficieront pas du boost
- La documentation publique FastAPI peut encore être enrichie pour exposer `gift_type`
- L’intégration Next.js côté payload `facet_weights.gift_type = 20` reste à confirmer bout en bout
- La suite legacy `tests/test_giftyzi.py` reste cassée hors scope

## 12. Verdict opérationnel
On peut passer à l’intégration Next.js pour le flux actif FastAPI.

Le seul blocant résiduel n’est pas sur le pipeline actif `recommend`, mais sur une suite de tests legacy (`tests/test_giftyzi.py`) déjà désalignée avec les schémas exposés par `app.api.schemas`.
