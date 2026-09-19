# BRIEF SPRINT B1-BIS — Généraliser le patron de sécurité aux actions restantes

**Destinataire :** CHAT6 (Claude Opus, Claude Code Windows)
**Émetteur :** Superviseur technique Atlas
**Date d'émission :** 18 septembre 2026
**Durée estimée :** ½ journée
**Statut :** Clôt la famille sécurité. Dernier sprint avant la chaîne vocale.
**Références :** rapport B1, annexe A (SV4)

---

## 1. Pourquoi ce sprint existe

Le sprint B1 a corrigé deux défauts prouvés. Son annexe A montre que **le problème est plus large** : sur 18 actions capables de modifier la machine, 4 sont correctement protégées, 6 partiellement, et **7 ne valident rien**.

Et surtout, **L5 n'est corrigé qu'à moitié.** On a validé *ce qui est tapé* ; on n'a pas validé *où*. `window_type` et `window_hotkey` sans paramètre `target` frappent toujours dans la fenêtre au premier plan — exactement le dommage qu'on vient d'empêcher, par une autre porte.

Ta propre conclusion en annexe A est la bonne : « la parade est la même partout — cible obligatoire, valeurs en liste blanche, bornes vérifiées — et ce sprint en fournit le patron ». Il reste à l'appliquer.

**Ce sprint n'invente rien.** Il généralise `normalize_hotkey_keys` et `_reject` aux cas restants.

---

## 2. Périmètre

**Autorisé :** `core/validator.py`, `tools/window_controller.py` si nécessaire, `tools/browser_bridge.py` pour les URL, `tests/`.

**Interdit :** chaîne vocale (L1, L2, L3), L4 heure, L6 triple lancement, L9 OCR bloquant, C04 endpoint trompeur. Et toute refonte du planificateur.

**Invariant 3 absolu** : aucun appel LLM dans le chemin de validation. Les corrections sont des listes constantes et des comparaisons.

**Méthode imposée, inchangée : le test rouge d'abord.** Pour chaque défaut, un test qui échoue, dont la sortie brute figure dans le rapport, avant toute correction. Aucun test ne doit produire d'effet réel.

---

## 3. Tâches

### BS1 — Cible obligatoire pour la frappe (la moitié manquante de L5)

`window_type` et `window_hotkey` sans `target` frappent dans la fenêtre au premier plan.

Appliquer la règle déjà retenue pour `ui_click_element` au sprint B1 :

1. Cible explicite issue de la demande ;
2. sinon, application du contexte de travail récent ou de l'étape précédente du plan ;
3. **sinon, refus explicite.** Pas de repli sur le premier plan.

Vérifier aussi le paramètre `text` de `window_type` : il n'est aujourd'hui contraint par rien et peut contenir des séquences de contrôle. Proposer une contrainte raisonnable — la définir dans le rapport avant de l'appliquer.

### BS2 — Titre non vide pour les actions de fenêtre

`window_close`, `window_focus`, `window_minimize`, `window_maximize`, `window_snap` : un titre vide fait remonter **toutes** les fenêtres à `getWindowsWithTitle("")`, et c'est la première qui est retenue.

- Titre vide ou absent → refus explicite.
- `window_snap` : valider `position` contre une liste blanche de positions connues.

`window_close` bénéficie déjà d'une confirmation obligatoire, mais une confirmation qui porte sur une cible indéterminée ne protège de rien : l'utilisateur confirme « fermer une fenêtre » sans savoir laquelle.

### BS3 — Bornes des coordonnées de clic

`window_click` accepte des coordonnées arbitraires, sans contrôle.

Vérifier que le point demandé tombe dans les limites de l'écran — et, si la cible est une fenêtre nommée, dans les limites de cette fenêtre. Hors limites → refus explicite.

Traiter le cas multi-écrans : les coordonnées négatives sont légitimes sur un écran secondaire placé à gauche. Ne pas les rejeter par principe.

### BS4 — Schémas d'URL en liste blanche

`browser_navigate`, `browser_open`, `browser_new_tab` acceptent n'importe quelle URL. `file://` et `javascript:` ne sont pas filtrés.

Liste blanche : `http`, `https`, et tout autre schéma dont l'usage est avéré dans Atlas. Tout le reste refusé.

Ce point compte doublement : Atlas lit du contenu externe non fiable (recherche web, OCR d'écran). Une URL produite à partir de ce contenu ne doit jamais pouvoir ouvrir un fichier local ni exécuter du script.

### BS5 — Proposer, ne pas implémenter : les deux cas qui demandent réflexion

Ces deux-là ne relèvent pas du patron mécanique. **Analyser et proposer, sans coder.**

**`launch_app` avec un paramètre `path`** — exécution d'un binaire arbitraire. Quelles options : liste blanche d'emplacements, confirmation obligatoire dès qu'un `path` est fourni, interdiction pure du paramètre au profit de `name` seul ? Quel est l'usage réel de `path` aujourd'hui dans le code et dans les workflows existants ?

**Contenu des actions planifiées** (`schedule_add`, `trigger_add`, `workflow_create`) — c'est le cas le plus préoccupant de l'annexe A, parce qu'il **persiste et se rejoue** : une action absurde enregistrée une fois est exécutée à chaque déclenchement, longtemps après que l'utilisateur a oublié l'avoir acceptée. Les autres défauts sont ponctuels, celui-ci s'installe.

La validation du contenu suppose de valider récursivement un plan au moment de l'enregistrement. Décrire l'approche, son coût et ses pièges. La décision reviendra au superviseur.

### BS6 — Vérification et rapport

1. Tous les tests de BS1 à BS4 passent, après avoir été vus rouges.
2. `python -m pytest tests/ -q` → **code 0**, 397 tests plus les nouveaux, écarts expliqués.
3. **Rejeu réel** : demander à Atlas de saisir du texte alors qu'une **autre application est au premier plan**. Attendu : soit le texte va dans la bonne fenêtre, soit l'action échoue explicitement. **En aucun cas du texte ne doit apparaître dans la fenêtre au premier plan.**
4. Couverture de `core/validator.py` avant et après.
5. Rapport conforme à `docs/RAPPORT_RULES.md`, 9 sections, dans `docs/rapports/RAPPORT_SPRINT_B1_BIS.md`, avec l'**annexe A mise à jour** : le même tableau des 18 actions, recalculé après ce sprint.

Le point 3 est le critère qui compte. Il est à `window_type` ce que le rejeu de C05 était à `ui_click_element`.

---

## 4. Critères de validation

- [ ] Tests rouges d'abord, sorties brutes consignées, aucun effet réel
- [ ] `window_type` et `window_hotkey` : cible obligatoire, refus explicite sinon
- [ ] Contrainte sur `text` définie, justifiée, appliquée
- [ ] Actions de fenêtre : titre vide refusé ; `position` de `window_snap` en liste blanche
- [ ] `window_click` : bornes vérifiées, multi-écrans géré
- [ ] Schémas d'URL en liste blanche
- [ ] BS5 : deux analyses livrées, **aucun code écrit** sur ces deux points
- [ ] `python -m pytest tests/ -q` → code 0
- [ ] **Rejeu réel de la frappe avec une autre application au premier plan** : aucun texte parasite
- [ ] Annexe A recalculée : combien d'actions protégées, partiellement, pas du tout
- [ ] Aucun appel LLM dans le chemin de validation
- [ ] Aucune modification hors du périmètre

## 5. Notes pour plus tard, à ne pas traiter ici

- **Le planificateur résout toutes les étapes avant la première exécution** (découverte B1). Aucune étape ne peut donc dépendre du résultat réel d'une étape antérieure, seulement de ce qui était prévu. Contourné pour le clic ; la question de fond reste ouverte pour les chaînes multi-app.
- `_is_browser` et `_BROWSER_PROCESSES` sont du **code mort dans le validateur** (signalé au sprint B1). À nettoyer à l'occasion.

## 6. Rappels de méthode

- Le test rouge d'abord, toujours.
- **Échouer proprement vaut mieux qu'agir au hasard.** Principe directeur, inchangé.
- Ne pas déborder sur la voix : c'est la tranche suivante, et elle attend.
- En cas de doute sur une commande touchant Docker ou la mémoire : ne pas l'exécuter, demander.
