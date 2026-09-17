# BRIEF SPRINT B1 — Sécurité des actions et durcissement du validateur

**Destinataire :** CHAT6 (Claude Opus, Claude Code Windows)
**Émetteur :** Superviseur technique Atlas
**Date d'émission :** 17 septembre 2026
**Durée estimée :** 1 journée
**Statut :** Première tranche de B-complet. Priorité sur la voix et la fiabilité.
**Références :** rapport A (L5, L24, annexe A.3 point 3, C02, C05)

---

## 1. Pourquoi cette tranche passe en premier

Deux défauts prouvés au sprint A permettent à Atlas d'**agir au mauvais endroit** :

**L5 — Atlas a tapé du texte dans une fenêtre.** Le planificateur a produit `window_hotkey {'keys': 'Fichier'}` ; `*args.get("keys")` a décomposé la chaîne, et les lettres **F-i-c-h-i-e-r** ont été frappées au clavier dans le Bloc-notes (titre observé : « *Fichier - Bloc-notes »). Sur une autre fenêtre au premier plan, c'est du texte arbitraire injecté n'importe où.

**L24 — le grounding a visé la mauvaise application.** Pour « ouvre le bloc-notes puis clique sur Fichier », il a cherché « bloc-notes » dans la fenêtre **Discord** au premier plan — une conversation privée — pendant 29 s. Un clic y était possible.

Ce ne sont pas des défauts de confort. Ce sont les deux seuls cas connus où Atlas peut causer un dommage réel, et ils sont actifs dès que tu l'utilises.

**Et tous deux ont traversé le validateur.** L'invariant 3 garantit qu'il est déterministe — il l'est. Il ne garantit pas qu'il valide assez, et il ne valide pas assez. L'audit A5 le chiffre : `core/validator.py::resolve` à **31 % de couverture**, 93 lignes jamais exécutées ; `core/planner.py` à 36 %.

Durcir cette barrière avant d'ajouter du vocal par-dessus est l'ordre sain.

---

## 2. Périmètre

**Autorisé — et c'est nouveau :** le code produit est modifiable, mais **uniquement pour L5 et L24** :

- `core/validator.py` — cœur du sprint
- `core/planner.py` — si la validation du plan l'exige
- `tools/grounding.py` — résolution de la cible de clic
- `tests/` — les tests de preuve

**Interdit — ce sont les tranches suivantes :**

- Chaîne vocale : L1 mot d'éveil, L2 cuBLAS, L3 TTS
- L4 heure inventée, L6 triple lancement, L9 OCR bloquant, C04 endpoint `/api/health` trompeur
- Toute refonte d'architecture

Si une correction de L5 ou L24 paraît exiger de toucher l'un de ces points, **s'arrêter et demander**.

**L'invariant 3 reste absolu : zéro appel LLM dans le chemin de validation.** Toute correction doit rester déterministe.

---

## 3. Méthode imposée : le test rouge d'abord

C'est la règle centrale de ce sprint, et elle vient directement de l'audit A5.

Le sprint v6.0.2 avait livré **17 tests verts** sur un mot d'éveil structurellement incapable de fonctionner. Les tests validaient des mocks, pas des comportements. On ne refait pas ça.

Pour chaque défaut :

1. **Écrire d'abord un test qui échoue**, et vérifier qu'il échoue **pour la bonne raison** — la sortie brute de l'échec figure dans le rapport.
2. Corriger.
3. Vérifier que le test passe.
4. Vérifier que les **377** tests passent toujours.

Un test qui n'a jamais été vu rouge ne prouve rien : il pourrait passer pour une raison sans rapport avec ce qu'il prétend vérifier.

Ces tests doivent exercer le **vrai chemin de code**, pas un remplaçant. Pour L5, cela signifie faire passer un plan par le vrai validateur. Pour L24, résoudre une vraie cible avec un contexte de fenêtres contrôlé.

---

## 4. Tâches

### SV1 — Reproduire les deux défauts en tests

Avant toute correction.

- **L5** : un plan contenant `window_hotkey {'keys': 'Fichier'}` doit aujourd'hui traverser le validateur. Le test le prouve.
- **L24** : une demande de clic visant une application nommée, alors qu'une autre est au premier plan, doit aujourd'hui partir sur celle du premier plan. Le test le prouve, sans cliquer réellement.

**Aucun de ces tests ne doit produire d'effet réel** : ni frappe clavier, ni clic, ni lancement d'application. Ce sont des tests de décision, pas d'exécution.

Consigner les deux échecs bruts dans le rapport.

### SV2 — L5 : valider les paramètres de touches

`window_hotkey` doit refuser tout ce qui n'est pas une combinaison de touches reconnue.

- Liste blanche de noms de touches valides — la même logique que le garde-fou Docker du sprint B-minimal : on autorise explicitement, on refuse le reste.
- Un plan invalide doit être **rejeté proprement**, avec un message exploitable, pas exécuté au mieux.
- Le rejet doit être **journalisé** et remonter dans la réponse à l'utilisateur.

Question à traiter dans le rapport : quand le planificateur produit un paramètre invalide, faut-il rejeter l'action seule, ou toute la chaîne ? Proposer, argumenter, appliquer le choix le plus sûr par défaut.

### SV3 — L24 : la cible de clic n'est jamais la fenêtre au premier plan par défaut

Règle à établir : la cible d'un `ui_click_element` est **l'application nommée dans la demande**, ou **celle lancée à l'étape précédente de la chaîne**. Jamais la fenêtre au premier plan faute de mieux.

- Si l'application attendue est introuvable, **échouer explicitement** plutôt que de se rabattre sur ce qui est visible.
- Un échec clair vaut infiniment mieux qu'un clic au mauvais endroit : c'est la règle de ce sprint.
- Vérifier le passage de contexte entre étapes d'une chaîne : l'orchestrateur transmet-il l'application de l'étape précédente ? Si non, c'est la vraie cause, et il faut le dire.

### SV4 — Revue systématique des paramètres d'action à effet de bord

Les deux défauts sont deux instances d'un même problème : **le validateur fait confiance aux paramètres produits par le LLM.**

Passer en revue, action par action, toutes celles qui agissent sur le système — frappe clavier, clic, fermeture de fenêtre, lancement d'application, commande système — et vérifier pour chacune :

- Quels paramètres elle accepte
- Ce qui se passe si le LLM en produit un absurde
- Si le validateur le détecte

Livrable : un **tableau** action par action, avec les trous identifiés. **Corriger seulement L5 et L24 dans ce sprint** ; les autres trous sont inventoriés et priorisés pour un sprint ultérieur.

Cette tâche est de l'inventaire, pas de la correction. C'est elle qui dira si le problème est large ou circonscrit.

### SV5 — Couverture du validateur

`resolve` est à 31 %, avec 93 lignes jamais exécutées. Ce sprint ne vise pas une couverture cible, mais les chemins traversés par L5 et L24 doivent l'être, et la couverture après correction doit être mesurée et comparée.

Signaler tout chemin de `resolve` qui reste inatteignable : du code mort dans un validateur de sécurité est un problème en soi.

### SV6 — Vérification et rapport

1. Les deux tests SV1 passent.
2. `python -m pytest tests/ -q` → **code 0**, 377 tests plus les nouveaux, tout écart expliqué.
3. Couverture de `core/validator.py` avant et après.
4. **Rejeu réel du scénario C05** : « ouvre le bloc-notes puis clique sur Fichier », avec Discord ou une autre application au premier plan. Attendu : soit le clic atteint le Bloc-notes, soit l'action échoue explicitement. **Dans aucun cas du texte ne doit être tapé, ni un clic partir sur la mauvaise fenêtre.**
5. Rapport conforme à `docs/RAPPORT_RULES.md`, 9 sections, dans `docs/rapports/RAPPORT_SPRINT_B1.md`.

Le rejeu du point 4 est le critère qui compte. Les tests prouvent la logique ; seul le rejeu prouve le produit.

---

## 5. Critères de validation

- [ ] Les deux défauts reproduits en tests **échouant d'abord**, sorties brutes consignées
- [ ] L5 corrigé : paramètres de touches en liste blanche, rejet propre et journalisé
- [ ] L24 corrigé : cible = application nommée ou lancée à l'étape précédente, échec explicite sinon
- [ ] Tableau de revue des paramètres d'action à effet de bord livré
- [ ] Couverture de `core/validator.py` mesurée avant et après
- [ ] `python -m pytest tests/ -q` → code 0, aucun écart inexpliqué
- [ ] **Scénario C05 rejoué réellement** : aucune frappe parasite, aucun clic sur la mauvaise fenêtre
- [ ] Aucun appel LLM introduit dans le chemin de validation (invariant 3)
- [ ] Aucune modification hors `core/validator.py`, `core/planner.py`, `tools/grounding.py`, `tests/`

## 6. Rappels de méthode

- **Le test rouge d'abord, toujours.** Un test jamais vu échouer ne prouve rien.
- **Échouer proprement vaut mieux qu'agir au hasard.** C'est le principe directeur des deux corrections.
- Ne pas déborder sur la voix, l'OCR ou l'heure. Elles ont leurs tranches.
- En cas de doute sur une commande touchant Docker ou la mémoire : ne pas l'exécuter, demander.
- Un garde-fou se teste avec des commandes simulées. Règle permanente depuis I-1.
