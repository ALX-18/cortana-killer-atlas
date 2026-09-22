# BRIEF SPRINT D — Qualité de la mémoire

**Destinataire :** CHAT6 (Claude Opus, Claude Code Windows)
**Émetteur :** Superviseur technique Atlas
**Date d'émission :** 22 septembre 2026
**Durée estimée :** 1 journée
**Statut :** Premier des quatre chantiers de la reprise. Précède la voix.
**Références :** rapport M (M-L4, M-L5, M-L6, M-L26, annexe A), rapport A (C07)

---

## 1. Pourquoi ce sprint passe avant la voix

Les réponses vocales viendront du même moteur que les réponses texte, et ce moteur puise dans la mémoire. Le sprint A l'a observé : une réponse conversationnelle contaminée par « un souvenir ancien et hors sujet ».

Faire la voix d'abord reviendrait à juger une fonctionnalité neuve sur des réponses dégradées par autre chose.

**Trois défauts documentés, tous dans `atlas_memory` :**

- **Deux modèles d'embedding coexistent.** `atlas_memory` (479 éléments) est vectorisée en 384 dimensions par `all-MiniLM-L6-v2`, **un modèle anglophone**, appliqué à du contenu français. Ce n'est pas un choix : `core/memory_manager.py` appelle `add` sans fournir d'embeddings, donc le client Chroma utilise son modèle par défaut. Les partitions (conversations, documents, erreurs) utilisent `intfloat/multilingual-e5-base` en 768 dimensions, calculé par Atlas.
- **213 des 479 éléments sont des doublons exacts de texte.** Les premiers résultats de chaque recherche sont donc occupés par des copies.
- **Au moins 40 éléments sur 535 sont des artefacts de test**, dont 20 des 25 documents. Classement heuristique, borne basse.

**Et surtout — la vraie demande d'Alexis.** Il ne constate pas de symptôme de rappel précis. Ce qu'il veut savoir, c'est si **Atlas apprend réellement de ses erreurs**. C'est le mécanisme le plus distinctif du projet, celui qui est mis en avant partout, et il n'a jamais été prouvé bout en bout. C'est l'objet de D1, et c'est la tâche la plus importante du sprint.

---

## 2. Règles

**Ce sprint touche la mémoire. Les règles des sprints M s'appliquent intégralement.**

- **Sauvegarde vérifiée avant toute écriture.** `backup` puis `verify`, comme d'habitude.
- **Aucune suppression sans validation explicite d'Alexis.** Ni doublon, ni artefact de test, ni rien. CHAT6 propose des listes, Alexis décide.
- En cas de doute sur une commande touchant Docker ou la base : ne pas l'exécuter, demander.
- Le test rouge d'abord, méthode inchangée.

**Périmètre autorisé :** `core/memory_manager.py`, `core_conversational/memory_core.py` si nécessaire, `scripts/` pour l'outillage de migration, `config/settings.json` pour les seuils, `tests/`.

**Interdit :** la chaîne vocale, le grounding, les modes. Chacun a sa tranche.

---

## 3. Tâches

### D1 — Prouver que l'apprentissage par les erreurs fonctionne

**Tâche la plus importante du sprint.** C'est la demande d'Alexis, formulée ainsi : « être sûr qu'il apprend vraiment de ses erreurs ».

C'est le mécanisme le plus distinctif d'Atlas. Il est revendiqué partout — roadmap, argumentaire, portfolio — et **il n'a jamais été prouvé de bout en bout**.

**Signal d'alerte à prendre au sérieux :** `core/error_learning.py` affiche **98 % de couverture**, l'une des plus élevées du projet. Le sprint A a établi ce que valent les couvertures élevées : v6.0.2 avait livré 17 tests verts sur un mot d'éveil structurellement incapable de se déclencher. Une couverture prouve que des lignes s'exécutent, pas qu'un comportement se produit.

**État connu :** `atlas_errors` contient 19 éléments, dont au moins 5 sont des artefacts de test — donc une quinzaine d'erreurs réelles accumulées depuis juin 2026.

À établir, dans cet ordre :

**1. Le rappel se déclenche-t-il ?** Instrumenter le chemin : à quelle fréquence la recherche dans `atlas_errors` est-elle appelée, avec quels scores de similarité, sur quelles actions, et combien de fois elle ne remonte rien.

**2. La mitigation est-elle réellement appliquée ?** Prendre une erreur réelle de la collection, reconstituer la situation qui l'a produite, et tracer de bout en bout : rappel → mitigation → action. Montrer où le comportement diverge de celui qu'on aurait sans la mémoire d'erreurs.

**3. Le test décisif — provoquer, apprendre, répéter.**

Provoquer délibérément un échec reproductible. Vérifier qu'il est indexé dans `atlas_errors`. Refaire **exactement la même action** et observer si le comportement change.

Si rien ne change, le mécanisme ne fonctionne pas — quelle que soit la couverture, quel que soit le nombre d'éléments stockés. C'est le seul test qui prouve quoi que ce soit.

**4. Mesurer la valeur.** Même tâche, avec et sans la mémoire d'erreurs disponible. L'écart entre les deux est la valeur réelle du mécanisme. S'il est nul, il faut le savoir.

**Consigne d'honnêteté :** si le mécanisme ne fonctionne pas, le dire clairement et s'arrêter là. Un diagnostic net vaut infiniment mieux qu'un correctif improvisé en fin de sprint. La réparation fera l'objet de son propre brief, avec le temps qu'il faut.

### D1-bis — Deux collections vides, à expliquer

`atlas_habits` et `atlas_context_apps` contiennent **zéro élément**, alors que les habitudes existent bel et bien — elles sont stockées dans `atlas_memory` (75 entrées de type `habit`) et dans `habits.db`.

Ces deux collections sont-elles du vestige à supprimer, ou du câblage prévu qui n'a jamais été branché ? La réponse compte : la proactivité future repose sur les habitudes.

Constat et recommandation. **Aucune suppression.**

### D2 — Sauvegarde

`backup` + `verify` avant toute modification. Consigner emplacement et empreintes.

### D3 — Ligne de base de la qualité du rappel

**Avant de toucher à quoi que ce soit**, construire un jeu de requêtes de référence — une vingtaine — avec, pour chacune, ce qu'un humain considérerait comme le bon résultat. Mesurer ce que la mémoire actuelle renvoie.

Sans cette mesure, aucune amélioration ne sera démontrable. C'est la même discipline que la suite de tests : on ne peut pas affirmer avoir amélioré ce qu'on n'a pas mesuré avant.

### D4 — La cause racine

`core/memory_manager.py` ligne ~180 : `add` est appelé sans embeddings. Corriger pour qu'Atlas fournisse ses propres vecteurs avec **e5-base**, le modèle déjà utilisé par les partitions et déjà présent en cache.

Vérifier qu'aucun autre chemin d'écriture ne contourne cette règle. Un seul point d'entrée pour l'écriture en mémoire, un seul modèle.

### D5 — Déduplication

213 doublons exacts identifiés au sprint M.

1. Produire la **liste complète**, avec pour chaque groupe le texte, le nombre de copies et leurs métadonnées.
2. Définir la règle de conservation — la plus ancienne, la plus récente, celle qui porte le plus de métadonnées — et la justifier.
3. **Soumettre à Alexis. Ne rien supprimer avant son accord.**

Traiter aussi la question de fond : **pourquoi des doublons exacts sont-ils écrits ?** Une déduplication à l'écriture vaut mieux qu'un nettoyage périodique.

### D6 — Ré-encodage en e5-base

Recalculer les vecteurs d'`atlas_memory` en 768 dimensions avec e5-base, de façon que toutes les collections partagent le même espace.

- Vérifier la cohérence après migration : dimensions, nombre d'éléments, contenus inchangés.
- Conserver l'ancienne collection jusqu'à validation de la nouvelle. **Pas de point de non-retour** — même principe qu'au sprint M-bis.

### D7 — Artefacts de test : inventaire, pas suppression

Le classement du sprint M était heuristique. Produire la liste avec, pour chaque élément, **la raison** de le considérer comme un artefact.

**Soumettre à Alexis. Ne rien supprimer.** Un faux positif ici efface un vrai souvenir.

Note : les tests n'écrivent plus dans la base réelle depuis B-minimal. La pollution est historique, elle ne s'aggrave pas.

### D8 — Seuil de pertinence et chemin de rappel

Vérifier `retrieval_min_score` sur la base réelle (risque M-L26). Un seuil trop bas fait remonter des souvenirs hors sujet — exactement le symptôme de C07.

Examiner aussi le nombre de résultats remontés et la façon dont ils sont injectés dans le prompt.

### D9 — Mesure après, et rapport

1. Rejouer le jeu de requêtes de D3. **Comparer.** L'amélioration doit être chiffrée, pas affirmée.
2. Rejouer le symptôme d'Alexis (D1) : est-il résolu ?
3. `python -m pytest tests/ -q` → code 0.
4. Rapport conforme à `docs/RAPPORT_RULES.md`, 9 sections, dans `docs/rapports/RAPPORT_SPRINT_D.md`.

---

## 4. Critères de validation

- [ ] **Apprentissage par les erreurs : le test provoquer → apprendre → répéter a été exécuté, et son résultat est énoncé sans ambiguïté**
- [ ] Valeur du mécanisme mesurée : même tâche avec et sans mémoire d'erreurs
- [ ] Collections vides `atlas_habits` et `atlas_context_apps` : vestige ou câblage non branché, recommandation donnée
- [ ] Sauvegarde vérifiée avant toute écriture
- [ ] Ligne de base du rappel mesurée **avant** modification
- [ ] Cause racine corrigée : un seul modèle d'embedding à l'écriture
- [ ] Liste des doublons livrée, règle justifiée, **aucune suppression sans accord**
- [ ] Déduplication à l'écriture traitée
- [ ] Ré-encodage effectué, ancienne collection conservée jusqu'à validation
- [ ] Liste des artefacts livrée avec justification, **aucune suppression**
- [ ] Seuil de pertinence vérifié sur la base réelle
- [ ] **Qualité du rappel mesurée après, comparée à la ligne de base**
- [ ] Symptôme d'Alexis rejoué
- [ ] `python -m pytest tests/ -q` → code 0

## 5. Rappels de méthode

- **Rien ne s'efface sans l'accord d'Alexis.** La mémoire est le seul actif irremplaçable du projet.
- **Mesurer avant, mesurer après.** Une amélioration non chiffrée n'est pas une amélioration.
- Le test rouge d'abord.
- Ne pas déborder sur la voix : elle vient juste après.
