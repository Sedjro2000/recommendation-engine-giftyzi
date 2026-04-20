# 🎁 GIFTYZI — Recommendation Engine

## 🧠 Description

GIFTYZI est un moteur de recommandation de cadeaux intelligent basé sur :

- compréhension de l’intention utilisateur
- contraintes métier strictes (HARD)
- scoring contextuel (SOFT)
- recommandations explicables

---

## 🎯 Principe fondamental

- **HARD = sécurité (filtre)**
- **SOFT = intelligence (scoring)**
- **Score = pertinence contextuelle**

---

## 🧩 Architecture (Pipeline)

```
Input utilisateur
→ Normalisation
→ Interprétation
→ HARD vs SOFT
→ Candidate retrieval
→ Filtering (HARD)
→ Scoring (SOFT)
→ Ranking
→ Résultat
```

---

## ⚖️ HARD vs SOFT

### 🔴 HARD (strict)
- budget_max
- stock > 0
- status = active

👉 jamais violé

### 🟡 SOFT (scoring)
- occasion
- theme
- relationship
- gift_benefit

---

## 🧠 Scoring (MVP)

Actuellement :

```
score = occasion_score
```

👉 basé uniquement sur l’occasion (Phase 1)

---

## 🚀 API

### Endpoint

```
POST /api/v1/recommend
```

### Input

```json
{
  "query": "cadeau anniversaire",
  "budget_max": 10000
}
```

### Output

```json
{
  "best_matches": [
    {
      "name": "Produit",
      "price": 5000,
      "_score": 0.9
    }
  ]
}
```

---

## 🛠️ Stack technique

- **FastAPI** → API
- **MongoDB Atlas** → Base de données
- **Docker** → Conteneurisation

---

## 🐳 Lancer le projet

### Build & run

```bash
docker-compose up --build
```

---

## 📊 Phase actuelle

### ✅ PHASE 1 — MVP moteur

- endpoint `/recommend`
- filtres HARD (budget + stock + status)
- scoring simple (occasion)
- top 10 produits

---

## ⚠️ Limitation actuelle

- Pas de champ `occasion_score` dans la base
- Score = 0 pour tous les produits

👉 prochain travail : enrichissement des données

---

## 📈 Roadmap

### 🥈 Phase 2
- table de similarité
- multi-valeurs
- explications

### 🥉 Phase 3
- reranking
- fallback
- relaxation

### 🧠 Phase 4
- embeddings
- personnalisation

---

## 👨‍💻 Auteur

**Sedjro**

---

## 📌 Note

> Un bon produit n’est pas forcément le meilleur.  
> Le meilleur produit est celui qui correspond le mieux à l’intention utilisateur.