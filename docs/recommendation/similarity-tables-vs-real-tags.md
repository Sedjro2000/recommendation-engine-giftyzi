# Similarity Tables vs Real Tags

## Contexte

Audit FastAPI Phase 2.5 Bloc 6.

Source de verite taxonomique : export Next.js `docs/recommendation/real-taxonomy-v1.json`.

Les tables de similarite FastAPI auditees sont limitees aux facettes SOFT moteur v1 :

- `event`
- `relationship`
- `theme`
- `gift_benefit`

Les facettes `age_group`, `recipient_gender`, `category` et `recipient_personality` ne doivent pas apparaitre dans les tables de similarite.

## Asymetries Detectees

### `event`

- `noel -> bapteme` : `0.3`, inverse absent
- `saint-valentin -> fete-des-meres` : `0.3`, inverse absent
- `saint-valentin -> fete-des-peres` : `0.2`, inverse absent
- `saint-valentin -> bapteme` : `0.1`, inverse absent
- `saint-valentin -> naissance` : `0.2`, inverse absent
- `mariage -> juste-faire-plaisir` : `0.4`, inverse absent

### `relationship`

- Aucune asymetrie detectee.

### `theme`

- `romantic -> personalized` : `0.7`, inverse absent
- `romantic -> beauty` : `0.6`, inverse absent
- `romantic -> fashion` : `0.6`, inverse absent
- `luxury -> fashion` : `0.7`, inverse absent
- `luxury -> beauty` : `0.7`, inverse absent
- `funny -> experience` : `0.7`, inverse absent
- `tech -> modern` : `0.8`, inverse absent
- `tech -> practical` : `0.7`, inverse absent
- `wellness -> beauty` : `0.7`, inverse absent
- `wellness -> eco-friendly` : `0.6`, inverse absent
- `travel -> experience` : `0.8`, inverse absent
- `handmade -> personalized` : `0.8`, inverse absent
- `minimalist -> modern` : `0.7`, inverse absent
- `traditional -> decorative` : `0.6`, inverse absent
- `decorative -> art` : `0.7`, inverse absent

### `gift_benefit`

- `experiential -> emotional` : `0.7`, inverse absent
- `experiential -> memorable` : `0.8`, inverse absent
- `decorative-benefit -> memorable` : `0.6`, inverse absent

## Asymetries Corrigees

Toutes les asymetries detectees ont ete corrigees par ajout de la relation inverse avec le meme score.

### `event`

- Ajout de `bapteme -> noel` : `0.3`
- Ajout de `fete-des-meres -> saint-valentin` : `0.3`
- Ajout de `fete-des-peres -> saint-valentin` : `0.2`
- Ajout de `bapteme -> saint-valentin` : `0.1`
- Ajout de `naissance -> saint-valentin` : `0.2`
- Ajout de `juste-faire-plaisir -> mariage` : `0.4`

### `theme`

- Ajout de `personalized -> romantic` : `0.7`
- Ajout de `beauty -> romantic` : `0.6`
- Ajout de `fashion -> romantic` : `0.6`
- Ajout de `fashion -> luxury` : `0.7`
- Ajout de `beauty -> luxury` : `0.7`
- Ajout de `experience -> funny` : `0.7`
- Ajout de `modern -> tech` : `0.8`
- Ajout de `practical -> tech` : `0.7`
- Ajout de `beauty -> wellness` : `0.7`
- Ajout de `eco-friendly -> wellness` : `0.6`
- Ajout de `experience -> travel` : `0.8`
- Ajout de `personalized -> handmade` : `0.8`
- Ajout de `modern -> minimalist` : `0.7`
- Ajout de `decorative -> traditional` : `0.6`
- Ajout de `art -> decorative` : `0.7`

### `gift_benefit`

- Ajout de `emotional -> experiential` : `0.7`
- Ajout de `memorable -> experiential` : `0.8`
- Ajout de `memorable -> decorative-benefit` : `0.6`

## Asymetries Assumees

Aucune asymetrie assumee.
