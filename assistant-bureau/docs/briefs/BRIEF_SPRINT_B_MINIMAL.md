# BRIEF SPRINT B-MINIMAL — Verdir la suite et fermer les failles

**Destinataire :** CHAT6 (Claude Opus, Claude Code Windows)
**Émetteur :** Superviseur technique Atlas
**Date d'émission :** 17 septembre 2026
**Durée estimée :** ½ à 1 journée
**Statut :** Dernier sprint avant la restructuration (C).
**Références :** rapports A (L7, L13), M (P1.4, M-L4), M-bis (I-1, R-1, R-2, R-3)

---

## 1. Objectif

Un seul, et il est mesurable :

> **`python -m pytest tests/ -q` doit renvoyer le code 0.**

La commande **brute**, sans option, sans `--continue-on-collection-errors`. Aujourd'hui elle renvoie 2 et n'exécute aucun test.

C'est le prérequis du sprint C : on ne restructure pas sur une suite rouge, sinon on ne sait plus distinguer les pannes préexistantes de celles causées par le déplacement.

S'y ajoutent les correctifs de sécurité issus de l'incident I-1, qui ne peuvent pas attendre.

---

## 2. Périmètre — strict

**Autorisé :**

- `tests/` — c'est le cœur du sprint
- `scripts/backup_memory.py` — correctif du garde-fou
- `docker-compose.yml` — `ALLOW_RESET`
- `conftest.py`, `pytest.ini` / `pyproject.toml` — configuration de la collecte

**Interdit :**

- Toute modification de `core/`, `tools/`, `api/`, `main.py`, `core_conversational/`

### Règle anti-dérive, importante

Le Sprint A a trouvé de vrais défauts produit : mot d'éveil inopérant, TTS muet, STT sans cuBLAS, heure inventée, `window_hotkey` qui tape du texte, grounding qui vise la mauvaise fenêtre. **Aucun ne se corrige ici.** Ils sont le périmètre de B-complet.

Si un test échoue parce que le **produit** est cassé et non le test, il ne faut ni corriger le produit, ni masquer l'échec : le marquer `xfail` avec une référence explicite au numéro de risque (`# xfail — voir rapport A, L1`), et le signaler dans le rapport.

En l'état, cela ne devrait pas se produire : au passage 4 du sprint A, seuls des défauts de test séparaient la suite du vert.

---

## 3. Préalables

1. **Confirmer auprès d'Alexis que la sauvegarde `chromadb_20260917_043101` a été copiée hors machine.** L'ancien conteneur n'existe plus : les sauvegardes sont le seul filet.
2. Avant toute modification de `docker-compose.yml` (BM7), prendre une sauvegarde fraîche : `backup` puis `verify`.

---

## 4. Tâches

### BM1 — Versionner ce qui est en attente

Le rapport M-bis signale que `scripts/backup_memory.py` n'est pas encore versionné, et que `docker-compose.yml`, `scripts/doctor.py` et `docs/install_checklist.md` ont été modifiés.

Faire le point sur ce qui n'est pas commité, et le commiter avec des messages **descriptifs**.

Remarque de méthode : les commits du sprint A s'intitulaient « Implement code changes to enhance functionality and improve performance » alors qu'aucun code n'avait été modifié. Sur un projet bâti sur la traçabilité, un message de commit doit décrire ce qui a réellement changé.

### BM2 — Sortir les scripts de la collecte

`tests/test_api_clean.py` et `tests/test_stream_fix.py` ne sont pas des tests : ce sont des scripts qui envoient de vraies requêtes à `localhost:8550` **au moment de l'import**. Si Atlas tourne, ils lui expédient de vraies commandes (« ouvre steam », « Cherche Python sur internet »).

Même problème pour `tests/test_cleanup.py` (appelle `process_ai_response` avec `launch_app steam`) et `tests/test_habit_persistence.py` (écrit dans le vrai `data/habits.db`).

Les déplacer hors de `tests/` — par exemple dans `scripts/manual/` — ou les exclure de la collecte (`collect_ignore` dans `conftest.py`). **Préférer le déplacement** : un script rangé parmi les tests finira toujours par être ramassé par quelqu'un.

Ne pas les supprimer : ils ont une valeur en usage manuel.

### BM3 — Corriger le test dépendant de l'ordre

`tests/test_v53_migration.py::TestVisionDisabled::test_vision_disabled_returns_skipped` passe seul, échoue dans la suite complète. Cause : `asyncio.get_event_loop()` alors que pytest-asyncio 1.3 a déjà posé puis retiré une boucle.

Correctif : `asyncio.run()`, ou la fixture appropriée. Vérifier qu'il passe **dans les deux cas** — isolé et en suite complète.

### BM4 — Rendre les tests de service conditionnels

`test_chroma_integration` (5 tests) et `test_web_v20::test_01_searxng_heartbeat_under_3s` échouent quand le service n'est pas démarré. Ils doivent être **ignorés proprement** dans ce cas, comme le fait déjà `test_memory_v60`.

Objectif : la suite reste interprétable sur une machine sans Docker. Un test ignoré dit « non vérifié » ; un test rouge dit « cassé ». Ce n'est pas la même information.

### BM5 — Isoler les tests de la mémoire réelle

**La tâche la plus importante du sprint après le vert.**

Aujourd'hui, chaque exécution de la suite écrit dans la base que l'on vient de passer deux sprints à protéger. Le sprint M l'a chiffré : **au moins 40 des 535 éléments sont des artefacts de test, dont 20 des 25 documents**. `test_chroma_integration` crée et supprime une collection dans la vraie base.

Même problème pour les fichiers de données : le sprint A a ajouté 101 lignes à `data/atlas_actions.jsonl`, des entrées à `audit_log.jsonl`, et a écrit dans `habits.db`.

À traiter :

- Les tests ChromaDB doivent viser une **base de test séparée** — autre collection, autre port, ou instance jetable — jamais la base de production.
- Les tests qui écrivent dans `data/` doivent utiliser `tmp_path` ou un répertoire de données redirigé par variable d'environnement.

**Signaler tout test qui échoue une fois isolé.** Un test qui ne passait que grâce à l'état réel de la machine est un test qui ne prouvait rien — c'est une découverte, pas une régression.

### BM6 — Garde-fou en liste blanche, et testé correctement

L'incident I-1 vient d'une liste noire : `compose down` n'y figurait pas, donc elle est passée.

Une liste noire laisse toujours passer ce qu'on n'a pas imaginé. Inverser : **refuser tout ce qui n'est pas explicitement autorisé.** Liste blanche des sous-commandes `docker` nécessaires au script (`inspect`, `exec`, `cp`, `ps`, `run`, `create`, `volume inspect`, et `rm` uniquement sur le préfixe `atlas_memcheck_`). Tout le reste est refusé, `compose` comprise.

**Et les tests de ce garde-fou se font avec `subprocess.run` simulé.** Jamais avec de vraies commandes. C'est la leçon directe de l'incident, et elle doit être inscrite dans le code par des tests, pas seulement dans un rapport.

### BM7 — `ALLOW_RESET=FALSE`

Décision du superviseur. Un appel API `reset` efface aujourd'hui toute la base. Après deux sprints consacrés à protéger ces données, laisser une commande unique capable de tout détruire est incohérent.

1. Vérifier qu'aucun test ni aucun code d'Atlas n'appelle `reset`.
2. Passer la variable à `FALSE` dans `docker-compose.yml`.
3. Recréer le conteneur et vérifier que **les 535 éléments sont toujours là** — le volume est externe, ils doivent survivre.
4. Vérifier qu'un appel `reset` est désormais refusé.

Si un test en dépend, le signaler **sans** revenir à `TRUE` : la bonne réponse est d'adapter le test.

### BM8 — Rapport

Conforme à `rapport.md/RAPPORT_RULES.md`, 9 sections. Dans `docs/rapports/RAPPORT_SPRINT_B_MINIMAL.md`.

Doit contenir la **sortie brute** de la commande de référence :

```
python -m pytest tests/ -q
```

avec son code de retour. C'est le seul critère qui débloque le sprint C.

---

## 5. Critères de validation

- [ ] Sauvegarde externe `043101` confirmée par Alexis
- [ ] Sauvegarde fraîche prise et vérifiée avant modification de `docker-compose.yml`
- [ ] Fichiers en attente commités, avec des messages décrivant le changement réel
- [ ] Scripts sortis de la collecte, sans suppression
- [ ] `TestVisionDisabled` passe isolé **et** en suite complète
- [ ] Tests de service ignorés proprement quand le service est absent
- [ ] Tests isolés de la base et des données réelles ; échecs révélés par l'isolation signalés
- [ ] Garde-fou en liste blanche, testé avec `subprocess.run` simulé
- [ ] `ALLOW_RESET=FALSE`, 535 éléments intacts après recréation, `reset` refusé
- [ ] **`python -m pytest tests/ -q` → code 0**, sortie brute dans le rapport
- [ ] Aucune modification de `core/`, `tools/`, `api/`, `main.py`, `core_conversational/`

## 6. Rappels de méthode

- **Un garde-fou se teste avec des commandes simulées.** Règle issue de I-1, désormais permanente.
- En cas de doute sur une commande touchant Docker ou la base : ne pas l'exécuter, demander.
- Ne pas corriger les défauts produit. Ils ont leur sprint.
- Honnêteté intellectuelle non négociable : un test rendu vert en masquant un vrai problème est pire qu'un test rouge.
