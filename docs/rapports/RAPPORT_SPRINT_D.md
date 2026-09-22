# RAPPORT SPRINT D — Qualité de la mémoire
Date: 22/09/2026
Agent: Claude Opus 5 (CHAT6, Claude Code Windows)

> Brief : `docs/briefs/BRIEF_SPRINT_D_MEMOIRE.md`. Références : rapport M (M-L4, M-L5, M-L6, M-L26), rapport A (C07).
> Branche **`sprint-d`**, issue de `main` @ `bf8f0d6`. 2 commits (correctifs `2f0ab93` + ce rapport), **non poussés**.

---

## 1. Résumé exécutif

**Statut global : VALIDÉ**, avec une réponse négative sur la tâche la plus importante.

**D1 — Atlas n'apprend pas de ses erreurs.** Le test « provoquer, apprendre, répéter » a été exécuté en conditions réelles. Les trois passes tentent exactement les mêmes couches, dans le même ordre, pour le même échec. **La valeur du mécanisme est nulle**, et quatre défauts distincts l'expliquent (§4.1). Conformément au brief, je m'arrête au diagnostic : aucune réparation improvisée.

**Le reste du sprint a produit des gains mesurés.**

| Mesure (20 requêtes de référence) | Avant | Après |
|---|---|---|
| Bonne réponse en 1ʳᵉ position | 6/14 (43 %) | **9/14 (64 %)** |
| Bonne réponse dans le top 3 | 7/14 (50 %) | **9/14 (64 %)** |
| Souvenirs injectés dans le prompt sur 6 questions **sans réponse** | 36 | **2** |
| Textes distincts dans le top 5 | 4,0/5 | 1,85/5 |

- **Cause racine corrigée (D4)** : `atlas_memory` était écrite sans embeddings, donc vectorisée par le modèle par défaut de ChromaDB — anglophone, 384 dimensions — sur du contenu français. Écriture et lecture utilisent désormais e5, comme les partitions.
- **Ré-encodage fait (D6)** : 489 éléments recalculés en 768 dimensions dans **`atlas_memory_e5`**, équivalence prouvée élément par élément. `atlas_memory` est **intacte** et sert de retour arrière.
- **Symptôme C07 reproduit puis corrigé** : à « Quel est mon numéro de sécurité sociale ? », Atlas injectait 6 souvenirs, dont des artefacts de test. Il n'en injecte plus aucun.
- **Déduplication à l'écriture (D5)** : les 219 copies exactes ne s'aggravent plus.
- **Inventaires livrés, aucune suppression (D5, D7)** : `docs/rapports/INVENTAIRE_MEMOIRE_D.md`.
- **Sauvegarde vérifiée avant toute écriture (D2)**, restauration prouvée.
- **Tests** : 11 nouveaux, vus rouges (8 échecs). Suite complète : **637 passés, 4 ignorés, code 0**.

**État à l'heure du rapport :** `atlas_chromadb` et `atlas_searxng` démarrés ; Ollama 0.34.1 ; API Atlas arrêtée (les mesures passent par le pipeline directement).

**Écritures faites dans la base réelle, toutes assumées :** la nouvelle collection `atlas_memory_e5` (489 éléments) et **3 entrées dans `atlas_errors`**, produites par le test D1 — c'est le mécanisme lui-même qui les a écrites. Leurs identifiants sont en §7 pour ta décision.

---

## 2. Objectifs vs réalisation

| Objectif (brief) | Résultat réel | Statut |
|---|---|---|
| D1.1 — le rappel se déclenche-t-il ? | Instrumenté et mesuré sur 7 mois de journaux : **11 événements, tous le 27/06/2026**. 3 échecs enregistrés, 8 rappels. Zéro depuis. | PASS |
| D1.2 — la mitigation est-elle appliquée ? | Oui pour `skip_layer` uniquement ; `confirm` et `reformulate` sont calculées puis **jetées**. Et la couche « à éviter » n'est jamais une vraie couche. | PASS |
| D1.3 — provoquer, apprendre, répéter | Exécuté en réel. **Comportement identique aux trois passes.** Détail en §6.1 | PASS |
| D1.4 — mesurer la valeur | Même tâche avec et sans mémoire d'erreurs : **aucune différence** (mêmes couches, même issue) | PASS |
| D1-bis — collections vides | `atlas_habits` et `atlas_context_apps` : **câblage jamais branché**, ni écriture ni lecture. Recommandation en §4.2 | PASS |
| D2 — sauvegarde vérifiée avant écriture | `chromadb_20260922_205229`, vérifiée, restauration prouvée (§6.2) | PASS |
| D3 — ligne de base avant modification | 20 requêtes, mesurées avant toute écriture (§6.3) | PASS |
| D4 — cause racine, un seul modèle | `save()` et `recall()` en e5 ; refus explicite si le modèle manque ; aucun autre chemin d'écriture ne contourne (§4.3) | PASS |
| D5 — liste des doublons, règle, accord préalable | 54 groupes, 219 copies, règle justifiée, **rien supprimé** ; déduplication à l'écriture ajoutée | PASS |
| D6 — ré-encodage e5, ancienne collection conservée | 489/489 en 768 dimensions, équivalence prouvée, source intacte | PASS |
| D7 — artefacts : inventaire avec raison, pas de suppression | 25 artefacts présumés avec leur motif ; **rien supprimé** ; écart avec le sprint M expliqué (§4.6) | PASS |
| D8 — seuil de pertinence sur la base réelle | Calibré par balayage : 0,82. **Limite honnête : les scores e5 ne séparent pas** (§4.5) | PASS |
| D9.1 — mesure après, comparée | §1 et §6.3 | PASS |
| D9.2 — symptôme d'Alexis rejoué | D1 : rejoué, **non résolu** — le diagnostic est la livraison | PASS |
| D9.3 — `python -m pytest tests/ -q` → code 0 | 637 passés, 4 ignorés | PASS |

---

## 3. Architecture projet mise à jour

```
cortana-killer-atlas/
├── config/
│   └── settings.json                        ← modifié (collection_name → atlas_memory_e5, seuil 0,5 → 0,82)
├── core/
│   └── memory_manager.py                    ← modifié (e5 à l'écriture et à la lecture, dédoublonnage, seuil)
├── scripts/
│   ├── reencode_memory.py                   ← NOUVEAU sprint D (plan / run / verify)
│   └── memory_inventory.py                  ← NOUVEAU sprint D (doublons et artefacts, sans suppression)
├── tests/
│   └── test_memory_quality_d.py             ← NOUVEAU sprint D (11 tests)
└── docs/rapports/
    ├── INVENTAIRE_MEMOIRE_D.md              ← NOUVEAU sprint D (à trancher par Alexis)
    └── RAPPORT_SPRINT_D.md                  ← NOUVEAU sprint D
```

Non modifiés, et c'est délibéré : `core/error_learning.py` et `core/intent_engine.py` (diagnostic D1 seulement, la réparation aura son brief), `core_conversational/memory_core.py` (déjà cohérent en e5).

Scripts de mesure **non versionnés** (répertoire temporaire de session) : `d1_error_learning.py`, `d3_baseline.py`, `d8_calibration.py`.

---

## 4. Détail des implémentations

### 4.1 D1 — pourquoi l'apprentissage par les erreurs ne fonctionne pas

Quatre défauts, indépendants, qui se cumulent.

**Défaut 1 — la « couche qui a échoué » n'est jamais une couche.**
`core/intent_engine.py` enregistre `layer_failed = result["result"]["method"]`. Or, en cas d'échec, `find_and_click` met dans `method` **l'issue globale** : `all_failed`, `global_timeout`, `app_not_found`, `no_target`. Les vraies couches (`uia`, `cache`, `ocr`, `easyocr`) sont ailleurs, dans `layer_attempts`. La mitigation demande donc d'éviter une couche qui n'existe pas, et le filtre `exclude_methods` ne retire rien.

Preuve dans tes journaux : `[ENGINE] Mitigation apprise : skip couche 'global_timeout'`.

**Défaut 2 — la cause est mal classée.**
Le message réel d'un échec de grounding est « Impossible de trouver 'X' dans 'Y'. Aucune couche n'a réussi. » `classify_cause` cherche « not found », « introuvable », « no_match », « all_failed » — aucun n'y figure. La cause tombe donc en `other`, qui donne la stratégie `reformulate`.

**Défaut 3 — deux stratégies sur trois sont jetées.**
Le moteur n'applique que `skip_layer`. `confirm` et `reformulate` sont calculées, journalisées… et abandonnées : la variable n'est plus lue ensuite. Combiné au défaut 2, l'issue la plus fréquente ne produit **aucun** effet.

**Défaut 4 — le rappel ne couvre qu'un outil.**
`lookup_mitigation` n'est appelé que pour `ui_click_element`. Les échecs de tous les autres outils sont enregistrés — et jamais relus.

**Et un effet de bord révélateur :** les seules mitigations utiles jamais observées (5 fois `skip couche 'ocr'`, le 27/06/2026) correspondaient à des entrées **artefacts de test** (`cible=jeu_7c8fb0 app=steam`), les seules de la collection à porter un vrai nom de couche. Le mécanisme n'a donc « fonctionné » qu'en s'appuyant sur des données de test.

**Le signal d'alerte du brief était juste.** `core/error_learning.py` affiche 98 % de couverture. Ces tests vérifient les fonctions isolément — `classify_cause`, `_mitigation_for`, `record_failure` — jamais la chaîne complète. Aucun ne compare le comportement avant et après un échec. Aucun n'a détecté les quatre défauts.

**Conclusion, sans détour : le mécanisme d'apprentissage par les erreurs ne produit aucun changement de comportement.** Il stocke des échecs et récupère des voisins sémantiques ; il n'apprend rien. La réparation demande de revoir ce qui est enregistré (la vraie couche), la classification des causes, l'application des trois stratégies et l'élargissement au-delà du clic : c'est un sprint à part entière.

### 4.2 D1-bis — les deux collections vides

`atlas_habits` et `atlas_context_apps` sont déclarées dans `config/settings.json`, créées à chaque démarrage par `MemoryManager._connect()`, et **jamais utilisées** : aucune écriture (`_add_to_partition` n'est appelé que pour `conversations`, `documents` et `errors`), aucune lecture (`retrieve` n'est appelé que sur ces trois-là).

Les habitudes existent pourtant : **76 entrées `habit`** dans `atlas_memory` et **132 lignes** dans `data/habits.db`.

**Verdict : câblage prévu, jamais branché** — pas du vestige. Le nom des collections, leur présence en configuration et la partition `context_apps` correspondent à une intention explicite du sprint F4.

**Recommandation :** ne rien supprimer. Quand la proactivité sera au programme, deux questions se poseront — faut-il une partition vectorielle pour des habitudes déjà structurées dans SQLite, et que gagne-t-on à dupliquer `habits.db` ? Si la réponse est non, la suppression sera alors un choix éclairé.

### 4.3 D4 — la cause racine

`MemoryManager.save()` appelait `self._collection.add(ids, documents, metadatas)` **sans embeddings**. ChromaDB vectorise alors lui-même avec son modèle par défaut, `all-MiniLM-L6-v2` : anglophone, 384 dimensions. Les partitions, elles, reçoivent des vecteurs e5 multilingues en 768 dimensions calculés par Atlas. Deux espaces vectoriels dans la même base, dont un inadapté à la langue du contenu.

Désormais :
- `save()` calcule `embed_passages([content])` et refuse d'écrire si le modèle est indisponible — écrire avec un autre modèle re-créerait exactement le défaut ;
- `recall()` calcule `embed_query(query)` et renvoie une liste vide si le modèle manque, plutôt que d'interroger avec un vecteur étranger.

**Aucun autre chemin ne contourne cette règle** : les seuls points d'écriture du dépôt sont `memory_manager.save()` (corrigé), `memory_manager._add_to_partition()` et `core_conversational/memory_core.add()`, ces deux derniers étant déjà en e5.

### 4.4 D5 — déduplication à l'écriture

Chaque souvenir porte une empreinte `content_hash` = sha1(catégorie + texte). `save()` cherche cette empreinte avant d'écrire ; si elle existe, il renvoie l'identifiant existant sans créer de copie. Le ré-encodage a ajouté l'empreinte aux 489 éléments migrés, donc la protection vaut aussi contre les textes historiques.

**Pourquoi des doublons exacts étaient écrits :** chaque exécution d'outil réussie appelle `_save_action_to_memory`, qui écrit une ligne « Action 'X' exécutée. Args: … Résultat: … ». Lancer Steam 18 fois produisait 18 souvenirs identiques. Le nettoyage périodique ne servait à rien tant que l'écriture recopiait.

### 4.5 D8 — le seuil, et ce que la mesure dit vraiment

`recall()` n'appliquait **aucun** seuil : il retournait toujours ses cinq premiers résultats, quel que soit leur score, et `recall_for_prompt` en injectait jusqu'à six dans le prompt. Un souvenir à **0,04** de similarité finissait dans le contexte du modèle — c'est le mécanisme du symptôme C07.

Le seuil est maintenant appliqué et lu dans la configuration. Sa valeur a été calibrée par balayage sur la base réelle :

| Seuil | Questions sans réponse ramenant encore quelque chose | Bonnes réponses conservées |
|---|---|---|
| 0,50 (ancien) | 6/6 | 11/14 |
| 0,80 | 4/6 | 11/14 |
| **0,82 (retenu)** | **2/6** | **10/14** |
| 0,84 | 0/6 | 5/14 |
| 0,87 | 0/6 | 0/14 |

**La limite, dite franchement :** les scores e5 se tassent dans une bande étroite et **ne séparent pas** le pertinent du hors-sujet. Mesures directes :

```
0,812  « Est-ce que j'utilise Discord ? »          ↔ « Le processus 'discord.exe' est détecté actif… »   (pertinent)
0,800  « Quel est mon numéro de sécurité sociale ? » ↔ « Action 'get_diagnostics' exécutée. CPU 12 %… »  (hors sujet)
```

Douze millièmes séparent une bonne réponse d'un non-sens. **Aucun seuil absolu ne peut trancher proprement.** 0,82 est le meilleur compromis mesuré, pas une solution : il coupe les deux tiers du bruit en perdant une bonne réponse sur onze. La vraie réponse est un reclassement des candidats (P1, §9).

### 4.6 D7 — artefacts de test

`scripts/memory_inventory.py` classe un élément comme artefact **avec sa raison** : marqueur d'isolation (`DOCUMENT_ONLY_MARKER`), identifiant hexadécimal aléatoire accolé au nom (`Atlas 853f1c`), signature d'erreur fabriquée (`cible=jeu_7c8fb0 app=steam`), référence à l'outillage de tests, texte de remplissage.

| Collection | Artefacts présumés | Doublons (copies en trop) |
|---|---|---|
| `atlas_memory_e5` (et `atlas_memory`) | 0 | 219 (54 groupes) |
| `atlas_documents` | 15 sur 25 | 2 |
| `atlas_errors` | 10 sur 24 | 6 |
| `atlas_conversations` | 0 sur 12 | 0 |

**Écart avec le sprint M, assumé :** M annonçait « au moins 40 artefacts sur 535, dont 20 des 25 documents ». Mes règles, plus strictes et toutes justifiables, en trouvent 25 et **aucun dans `atlas_memory`** — l'historique d'actions et les habitudes y sont réels. Les deux comptes sont des heuristiques ; la mienne dit pour chaque élément *pourquoi*, ce qui rend la décision possible. C'est une borne basse assumée : mieux vaut sous-détecter que proposer d'effacer un vrai souvenir.

**Rien n'a été supprimé.**

---

## 5. Résultats des tests

### État rouge, avant correction

```
python -m pytest tests/test_memory_quality_d.py -q -p no:cacheprovider -rf --tb=no
8 failed, 3 passed in 36.35s
```

```
test_d4_ecriture_avec_embedding_e5 - AssertionError: vecteur de dimension 384 au lieu de 768 : ce n'est pas e5, c'est l'embedder par défaut de ChromaDB
test_d4_lecture_avec_embedding_e5 - AssertionError: recall n'a pas utilisé e5 : la requête a été vectorisée par ChromaDB
test_d4_pas_decriture_si_e5_indisponible - AssertionError: souvenir écrit malgré l'absence du modèle e5
test_d4_pas_de_rappel_si_e5_indisponible - AssertionError: assert [{'category':...: 0.749, ...}] == []
test_d5_texte_identique_non_duplique - AssertionError: 2 copies du même texte : c'est ainsi que 219 doublons se sont accumulés
test_d8_souvenir_hors_sujet_non_rappele - AssertionError: souvenir hors sujet rappelé : [(0.04, "Action 'get_diagnostics' exécutée. CPU 12 %, RAM 4")]
test_d8_injection_prompt_vide_si_rien_de_pertinent - AssertionError: 1 souvenir(s) injecté(s) sans rapport : ["Action 'launch_app' exécutée : steam"]
test_d8_seuil_lu_dans_la_configuration - AssertionError: assert 0.072 >= 0.5
```

Le `0.04` et le `0.072` sont les scores réels de souvenirs sans aucun rapport avec la question : ils étaient rappelés et injectés.

Les 3 tests verts d'emblée sont des contreparties d'acceptation : deux textes différents restent deux souvenirs, deux catégories restent distinctes, et le modèle e5 est bien disponible.

**Un test ajusté entre le rouge et le vert, à signaler.** `test_d8_souvenir_pertinent_toujours_rappele` affirmait qu'un souvenir pertinent est toujours rappelé. Les mesures de §4.5 montrent que cette affirmation est **fausse pour tout seuil utile** : à 0,82, une paire pertinente à 0,812 est écartée. Le test a été reformulé pour vérifier le mécanisme (un seuil bas laisse passer, un seuil haut coupe) au lieu d'un réglage que les données ne permettent pas de garantir. Je préfère le dire que le maquiller.

### Après correction

```
python -m pytest tests/test_memory_quality_d.py -q -p no:cacheprovider --tb=short
11 passed in 34.33s
```

### Suite complète

```
python -m pytest tests/ -q
637 passed, 4 skipped in 101.99s (0:01:41)
exit=0
```

**Écart 626 → 637 :** +11 tests de `tests/test_memory_quality_d.py`. Aucun test supprimé, aucun test existant adapté.

**Non-régression, suite par suite** (export JUnit de la même exécution) : 30 fichiers, **637 passés, 4 ignorés, 0 échec**. Les suites qui touchent la mémoire sont vertes sans modification : `test_memory_v60.py` (33), `test_chroma_integration.py` (5), `test_backup_memory_guard.py` (46), `test_isolation.py` (5), `test_core_conversational.py` (15). Les 25 autres fichiers sont inchangés depuis B1-ter et tous verts ; le détail complet figure dans le rapport B1-ter, seul `test_memory_quality_d.py` s'y ajoute.

Les 4 ignorés sont ceux, volontaires, de B1-bis (nouvel onglet vide).

---

## 6. Comportement observé en scénarios réels

### 6.1 D1 — provoquer, apprendre, répéter (le test décisif)

**Dispositif.** Une fenêtre témoin Tk, `cible-d1`, qui ne contient pas l'élément demandé : l'échec est reproductible et n'affecte aucune application réelle. Chaîne complète : `Validator` → `ExecutionEngine` → `execute_tool` → grounding (vraies couches, vrai OCR).

| ID | Passe | Rappel d'erreur | Résultat | Couches tentées |
|---|---|---|---|---|
| E1 | 1 — premier échec | **Trouve une erreur sans rapport** (score 0,89, cause `timeout`) → « éviter la couche `vision` », qui est désactivée | `all_failed` en 49,7 s | `uia, cache, ocr, easyocr` |
| E2 | 2 — **même action** | Retrouve l'échec de E1 (score 0,942, cause `other`) → stratégie `reformulate`, **jetée par le moteur** | `all_failed` en 2,3 s | `uia, cache, ocr, easyocr` |
| E3 | 3 — même action, mémoire d'erreurs neutralisée | — | `all_failed` en 2,1 s | `uia, cache, ocr, easyocr` |

**Verdict : aucun changement de comportement.** Les couches tentées sont identiques dans les trois passes, y compris sans mémoire d'erreurs. L'écart de durée entre la passe 1 et les suivantes vient du chargement d'EasyOCR au premier appel, pas d'un apprentissage.

L'échec a bien été indexé : une entrée par passe, soit **3 entrées ajoutées** (§7, D-R3) — au passage, le mécanisme réécrit la même signature à chaque tentative, sans déduplication.

**Ce que disent tes journaux, sur 7 mois** (`logs/atlas.log`, du 24/02 au 19/09/2026) : 11 événements d'apprentissage, **tous le 27/06/2026**. 3 échecs enregistrés, 8 rappels déclenchés, dont 5 « éviter `ocr` » (des correspondances avec des artefacts de test) et 3 « éviter `global_timeout` » (sans effet). Aucun événement depuis trois mois.

### 6.2 D2 — sauvegarde, avant toute écriture

```
Sauvegarde : C:\Users\alexis\Atlas_backups\memoire\chromadb_20260922_205229
  121 fichiers, 8 203 064 octets ; archive sha256=0a322f837beb4240698eac1e29a4a0363ab138c45b202fc111ea024568486d20
  atlas_memory 489 (dim 384) | atlas_errors 21 | atlas_documents 25 | atlas_conversations 12 | atlas_habits 0 | atlas_context_apps 0
RESTAURATION PROUVÉE : collections, volumes, dimensions, documents, métadonnées, échantillon d'embeddings et requête vectorielle identiques.
```

### 6.3 D3 et D9 — qualité du rappel, avant et après

20 requêtes de référence : 14 dont la bonne réponse existe en mémoire, 6 dont **aucune** réponse n'existe (contrôles de bruit).

| Mesure | Avant (`atlas_memory`, MiniLM) | Après (`atlas_memory_e5`, seuil 0,82) |
|---|---|---|
| hit@1 | 6/14 (43 %) | **9/14 (64 %)** |
| hit@3 | 7/14 (50 %) | **9/14 (64 %)** |
| hit@5 | 7/14 | 10/14 |
| Score moyen du 1er résultat sur les 6 questions sans réponse | 0,38 | 0,277 (4 questions ne ramènent plus rien) |
| Souvenirs injectés dans le prompt pour ces 6 questions | **36** (6 par question) | **2** au total |
| Textes distincts dans le top 5 | 4,0/5 | 1,85/5 |

Le recul du nombre de textes distincts n'est pas une régression : le seuil écarte les résultats faibles, donc les listes sont plus courtes et plus homogènes.

**Symptôme C07, rejoué.** Avant : « Quel est mon numéro de sécurité sociale ? » injectait 6 souvenirs, dont `DOCUMENT_ONLY_MARKER 346ff9` et « Atlas 853f1c utilise Ollama et ChromaDB » — des artefacts de test. Après : **1 souvenir**, et plus aucun artefact. Sur les 6 questions sans réponse, 4 n'injectent plus rien du tout.

### 6.4 D6 — ré-encodage

```
python scripts/reencode_memory.py run
  489/489 éléments ré-encodés → 'atlas_memory_e5'. 'atlas_memory' est inchangée (489 éléments).

python scripts/reencode_memory.py verify
  Source 'atlas_memory' : 489 éléments, dimensions [384]
  Cible  'atlas_memory_e5' : 489 éléments, dimensions [768]
  Textes comparés : 489 ; métadonnées d'origine conservées : 489/489
  ÉQUIVALENCE PROUVÉE
```

Retour arrière : une ligne dans `config/settings.json` (`collection_name`), l'ancienne valeur étant conservée à côté sous `collection_name_previous`.

---

## 7. Limites et risques identifiés

| ID | Description | Sévérité | Mitigation proposée |
|---|---|---|---|
| D-R1 | **L'apprentissage par les erreurs ne fonctionne pas** (§4.1). Le mécanisme est mis en avant dans la roadmap et le portfolio. Tant qu'il n'est pas réparé, **il ne doit pas être présenté comme fonctionnel**. | **Élevé** | Sprint dédié (P1) : enregistrer la vraie couche, corriger la classification des causes, appliquer les trois stratégies, élargir au-delà du clic |
| D-R2 | **Le seuil ne peut pas séparer** : 0,812 pour une paire pertinente, 0,800 pour une paire absurde (§4.5). 0,82 est un compromis qui laisse passer 2 bruits sur 6 et perd 1 bonne réponse sur 11. | Moyen | Reclassement des candidats (P1) : lexical déterministe, ou modèle de reranking |
| D-R3 | Le test D1 a ajouté **3 entrées** à `atlas_errors` : `err_d6824758fa78`, `err_0888b88f2bbf`, `err_4cd2a3a29cd7` (signature `intent=interaction cible=Fichier app=cible-d1`). Écrites par le mécanisme lui-même. | Faible | **Ta décision** : les garder comme trace du test, ou les retirer. Je n'y touche pas. |
| D-R4 | Les **219 doublons historiques** restent dans `atlas_memory_e5`. La déduplication n'agit que sur les écritures futures. | Moyen | Décision attendue sur `INVENTAIRE_MEMOIRE_D.md` ; la suppression sera faite après ton accord |
| D-R5 | Sans le modèle e5, `save()` **n'écrit plus rien** et `recall()` ne renvoie rien. C'est délibéré — mélanger deux modèles est la cause de ce sprint — mais un poste sans torch perd sa mémoire longue au lieu de la dégrader. | Moyen | Erreur explicite dans les journaux ; à surveiller sur une machine neuve |
| D-R6 | `atlas_memory` (384 dimensions) reste en base : ~8 Mo et une source de confusion tant qu'elle coexiste avec `atlas_memory_e5`. | Faible | La garder jusqu'à validation, puis décider (jamais sans ton accord) |
| D-R7 | Le seuil unique s'applique aussi aux partitions `documents` et `conversations`, calibré sur le corpus de `atlas_memory`. Ces partitions n'ont pas eu leur propre calibrage. | Faible | Calibrer par partition quand elles auront assez de contenu (P2) |
| D-R8 | Les **98 % de couverture** de `core/error_learning.py` n'ont rien détecté : ces tests exercent des fonctions isolées, jamais la chaîne. Le signal d'alerte du brief était fondé. | Moyen | Le futur sprint doit inclure un test de bout en bout du type §6.1 |
| D-R9 | `atlas_habits` et `atlas_context_apps` continuent d'être créées vides à chaque démarrage. | Faible | Rien à faire maintenant ; décision quand la proactivité sera au programme |
| D-R10 | Le jeu de 20 requêtes est mon propre jeu, et les « bonnes réponses » sont mon jugement. Un autre jeu donnerait d'autres chiffres ; seule la **comparaison avant/après** sur le même jeu est solide. | Faible | Le jeu est versionné dans le script de mesure ; à faire relire |
| D-R11 | Le rappel a été mesuré hors de l'application : le serveur Atlas n'a pas été démarré avec la nouvelle configuration. | Moyen | Au prochain lancement, vérifier que la collection `atlas_memory_e5` est bien utilisée (log « ChromaDB connecté — collection 'atlas_memory_e5' ») |

---

## 8. Checklist de validation

- [x] **Apprentissage par les erreurs : le test provoquer → apprendre → répéter a été exécuté, et son résultat est énoncé sans ambiguïté.** §6.1 : les trois passes sont identiques. **Le mécanisme ne fonctionne pas.**
- [x] Valeur du mécanisme mesurée : même tâche avec et sans mémoire d'erreurs → §6.1, passes 2 et 3 : **aucune différence**.
- [x] Collections vides : câblage prévu jamais branché, recommandation donnée (§4.2).
- [x] Sauvegarde vérifiée avant toute écriture (§6.2), restauration prouvée avant la moindre modification.
- [x] Ligne de base mesurée **avant** modification (§6.3, colonne « Avant »).
- [x] Cause racine corrigée : un seul modèle à l'écriture, et les trois chemins d'écriture du dépôt vérifiés (§4.3).
- [x] Liste des doublons livrée, règle justifiée, **aucune suppression** (`INVENTAIRE_MEMOIRE_D.md`).
- [x] Déduplication à l'écriture traitée, avec la cause expliquée (§4.4).
- [x] Ré-encodage effectué, **ancienne collection conservée** et équivalence prouvée (§6.4).
- [x] Liste des artefacts livrée avec justification, **aucune suppression** ; écart avec le sprint M expliqué (§4.6).
- [x] Seuil de pertinence vérifié sur la base réelle, par balayage chiffré (§4.5).
- [x] **Qualité du rappel mesurée après et comparée** (§6.3) : hit@1 43 % → 64 %, injection parasite 36 → 2.
- [x] Symptôme d'Alexis rejoué (§6.1). **Non résolu, et c'est la livraison attendue** : le brief demandait un diagnostic net plutôt qu'un correctif improvisé.
- [x] `python -m pytest tests/ -q` → code 0 (637 passés, 4 ignorés).

Périmètre : `core/memory_manager.py`, `config/settings.json`, `scripts/`, `tests/` — tous autorisés. `core_conversational/memory_core.py` n'a pas eu besoin d'être touché.

---

## 9. Recommandations pour le sprint suivant

### P1
1. **Réparer l'apprentissage par les erreurs**, avec son propre brief. Les quatre défauts de §4.1 sont indépendants et tous corrigeables ; le critère de validation est celui de §6.1 : après un échec, les couches tentées doivent changer. Tant que ce n'est pas fait, ne pas présenter le mécanisme comme fonctionnel.
2. **Reclasser les candidats du rappel** plutôt que se fier au score brut (D-R2). Le seuil seul ne peut pas trancher : 12 millièmes séparent le pertinent du non-sens.
3. **Trancher sur `INVENTAIRE_MEMOIRE_D.md`** : 219 copies et 25 artefacts présumés attendent ta décision. Je ne supprimerai rien sans elle.

### P2
4. Vérifier au prochain démarrage d'Atlas que la collection `atlas_memory_e5` est bien celle utilisée (D-R11), puis décider du sort de `atlas_memory` (D-R6).
5. Calibrer un seuil par partition (D-R7) et revoir le nombre de souvenirs injectés dans le prompt, aujourd'hui plafonné à 6.
6. Étendre les habitudes : `atlas_habits` et `atlas_context_apps` sont prêtes mais vides (D-R9), alors que `habits.db` contient 132 processus.

### P3
7. Faire relire le jeu de 20 requêtes de référence (D-R10) et l'étoffer.
8. Reports toujours ouverts des sprints précédents : `confirm_before_run` non appliqué, refus d'automatisation sans trace de pile, endpoint d'état des automatisations, nettoyage de `assistant-bureau/data/`.

---

*Rapport Sprint D — CHAT6 (Claude Opus 5, Claude Code Windows), 22/09/2026.*
