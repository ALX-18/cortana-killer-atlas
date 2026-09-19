# RAPPORT SPRINT B1 — Sécurité des actions et durcissement du validateur
Date: 17/09/2026
Agent: Claude Opus 5 (CHAT6, Claude Code Windows)

> Brief : `docs/briefs/BRIEF_SPRINT_B1_SECURITE.md`. Références : rapport A (L5, L24, annexe A.3, C02, C05).
> Branche **`sprint-b1`**, issue de `main` @ `fd8220d`. 2 commits (correctifs + ce rapport), **non poussés**.

---

## 1. Résumé exécutif

**Statut global : VALIDÉ.**

Les deux défauts qui permettaient à Atlas d'agir au mauvais endroit sont corrigés, chacun prouvé par un test **vu rouge d'abord**, puis par un rejeu réel.

- **L5 — frappe de texte arbitraire.** `window_hotkey {'keys': 'Fichier'}` traversait le validateur ; l'exécuteur décomposait la chaîne en sept frappes envoyées à la fenêtre active. Sortie rouge consignée : `le validateur laisse passer une frappe de texte arbitraire : window_hotkey params={'keys': 'Fichier'}`. Désormais : liste blanche de touches, rejet propre et journalisé.
- **L24 — clic sur la mauvaise application.** Sans application nommée, le validateur prenait le titre de la fenêtre au premier plan. Sortie rouge consignée : `assert 'Discord' not in '★ conversation privée - Discord'`. Désormais : application nommée, ou application de l'étape précédente, sinon **échec explicite**.
- **Cause réelle de L24 identifiée** : `Planner._validate_plan` résout **toutes** les étapes avant la première exécution ; l'étape « clique » ne voyait donc jamais l'application ouverte à l'étape précédente. Le planificateur transmet désormais cette application.
- **Rejeu réel de C05** (Explorateur de fichiers au premier plan) : le clic a hérité de « bloc-notes » et a atteint le menu **Fichier du Bloc-notes** (clic OCR à (300, 318), confiance 77 %). **Aucune frappe parasite, aucun clic hors cible.**
- **Suite : 397 tests, code 0** (377 + 20 nouveaux).
- **Couverture** de `core/validator.py` : **41 % → 55 %** (`resolve` : 31 % au sprint A → 38 %) ; `core/planner.py` : 36 % → 59 %.
- **Invariant 3 respecté** : aucun appel LLM introduit dans le chemin de validation.
- **Aucune modification hors** `core/validator.py`, `core/planner.py`, `tools/grounding.py`, `tests/`.

**Ce que ce sprint n'a pas corrigé, et qu'il faut savoir :** l'inventaire SV4 montre que le problème est **plus large que ces deux cas**. Sept actions à effet de bord acceptent encore des paramètres non validés, dont deux de la même famille exactement : `window_type` et `window_hotkey` sans `target` frappent dans la fenêtre au premier plan, et `window_close("")` fermerait une fenêtre arbitraire. Détail et priorités en annexe.

---

## 2. Objectifs vs réalisation

| Objectif / critère (brief) | Résultat réel | Statut |
|---|---|---|
| SV1 — Les deux défauts reproduits en tests échouant d'abord, sorties brutes consignées | 20 tests écrits avant toute correction, **20 rouges**, sorties brutes en section 5. Aucun effet réel (pyautogui piégé). | PASS |
| SV2 — L5 : paramètres de touches en liste blanche, rejet propre et journalisé | `VALID_HOTKEY_KEYS` + `normalize_hotkey_keys()` ; refus → message utilisateur + `logger.warning` ; rien n'est exécuté | PASS |
| SV2 — Question : rejeter l'action seule ou la chaîne ? | Traitée en section 4 : **toute la chaîne**, avec justification | PASS |
| SV3 — L24 : cible = application nommée ou lancée à l'étape précédente, échec explicite sinon | Validateur (plus de repli premier plan), planificateur (transmission entre étapes), grounding (`no_target`, `app_not_found`) | PASS |
| SV3 — Vérifier le passage de contexte entre étapes | **Absent** : toutes les étapes sont résolues avant exécution. C'était la cause réelle ; corrigé dans le planificateur | PASS |
| SV4 — Tableau de revue des paramètres d'action à effet de bord | Annexe A : 18 actions passées en revue, 7 trous identifiés et priorisés | PASS |
| SV5 — Couverture du validateur avant/après, chemins inatteignables signalés | 41 % → 55 % ; `_is_browser` et `_BROWSER_PROCESSES` : **code mort dans le validateur**, signalés | PASS |
| SV6.1 — Les deux tests SV1 passent | 20/20 | PASS |
| SV6.2 — `python -m pytest tests/ -q` code 0, écarts expliqués | **397 passés**, code 0 ; écart 377 → 397 expliqué (section 5) | PASS |
| SV6.3 — Couverture avant/après | Section 5 | PASS |
| SV6.4 — Rejeu réel de C05 | Deux rejeux (plan LLM réel, puis chemin du clic déterministe) + cas « clic sans application » : aucun effet indésirable | PASS |
| Aucun appel LLM dans le chemin de validation | Vérifié (section 4) | PASS |

---

## 3. Architecture projet mise à jour

```
core/
├── validator.py        ← MODIFIÉ (liste blanche de touches, refus d'action, cible de clic)
└── planner.py          ← MODIFIÉ (transmission de l'application entre étapes, abandon du plan)
tools/
└── grounding.py        ← MODIFIÉ (no_target, app_not_found)
tests/
├── test_action_safety_b1.py            ← NOUVEAU (20 tests)
├── test_sprint_kimi_understanding_v51.py ← MODIFIÉ (test qui encodait le défaut L24)
└── test_vision_parsers.py              ← MODIFIÉ (mocks manquants pour les tests de délais)
docs/rapports/RAPPORT_SPRINT_B1.md      ← NOUVEAU
```

`git diff --stat main..sprint-b1` : 6 fichiers, +184 / −13 (hors rapport).

**Commits** : `2a09f38` (correctifs et tests), puis ce rapport.

**Environnement** : `pytest-cov` installé dans `.venv` pour SV5 (outil de test, sans effet sur le produit ; il figurera dans un futur `pip freeze`).

---

## 4. Détail des implémentations

### `core/validator.py`

**Mécanisme de refus (nouveau).** `ResolvedAction` porte `rejected: bool` et `rejection_reason: str`. La méthode `_reject()` journalise en `warning` et renvoie une action **non exécutable** : `tool="__conversation__"` avec un message destiné à l'utilisateur. Le moteur traite déjà ce cas sans effet de bord (`status: "conversation"`), ce qui permet un refus propre **sans toucher à `core/intent_engine.py`**, hors périmètre.

**L5 — liste blanche de touches.**
- `VALID_HOTKEY_KEYS` = modificateurs (`ctrl`, `alt`, `shift`, `win`…) ∪ touches nommées (`enter`, `tab`, `esc`, `home`, flèches, multimédia…) ∪ `f1`–`f24` ∪ caractères imprimables simples.
- `normalize_hotkey_keys(raw)` accepte une liste (`["ctrl","s"]`) ou une chaîne de combinaison (`"ctrl+s"`, `"ctrl s"`), normalise en minuscules, **refuse** tout jeton hors liste, les types non textuels et au-delà de 5 touches. Retourne `(touches, erreur)` : déterministe, sans dépendance externe.
- Dans `resolve`, la branche `interaction/hotkey` valide avant de choisir l'outil ; en cas d'erreur, `_reject` avec un message actionnable (« Pour saisir du texte, utilise une demande de frappe explicite. »).
- « Fichier » est refusé parce que `fichier` n'est pas une touche ; `ctrl+s` passe et ressort normalisé en `['ctrl', 's']` — l'exécuteur reçoit donc toujours une liste, ce qui neutralise aussi le dépaquetage `*args` à l'origine du défaut.

**L24 — cible de clic.** L'ordre de résolution devient :
1. `app_title` explicite (extrait de la demande par le classifieur, ex. « dans le bloc-notes ») ;
2. application du contexte de travail récent (`last_action` de type `ui_click_element`, < 2 min, hors Atlas Desktop) ;
3. **sinon : refus explicite.** Le repli sur `foreground_window` est supprimé ; le titre du premier plan est seulement journalisé pour le diagnostic.

### `core/planner.py`

- `_validate_plan` suit l'application de travail au fil des étapes : une étape `open` / `launch` / `focus` / `maximize` / `minimize` avec une cible devient l'application courante, et une étape `click` sans `app_title` en hérite (journalisé).
- **Réponse à la question du brief (rejeter l'action seule ou toute la chaîne ?) : toute la chaîne.** Argument : le planificateur est un LLM ; un paramètre absurde n'est pas un accident isolé mais le signe que la sortie n'est pas fiable. Exécuter les autres étapes reviendrait à agir à moitié sur la foi d'un plan déjà démenti — par exemple lancer une application puis abandonner, en laissant l'utilisateur dans un état intermédiaire non demandé. En pratique, `_validate_plan` renvoie un plan réduit à la seule étape refusée, dont l'exécution se borne à afficher le message : **aucune action n'est exécutée**, et l'utilisateur sait pourquoi.

### `tools/grounding.py`

- `find_and_click` refuse une cible vide (`method: "no_target"`). Motif mesuré : `gw.getWindowsWithTitle("")` renvoie **toutes** les fenêtres, et `_choose_best_window` retenait alors la fenêtre active — c'est le mécanisme par lequel un clic pouvait partir n'importe où. Le test rouge le montrait : avec une cible vide, la fonction tournait 20 s avant de rendre `global_timeout`.
- Si la fenêtre nommée est introuvable, échec explicite (`method: "app_not_found"`) **sans essayer aucune couche**, au lieu de laisser les couches travailler sur une autre fenêtre.
- `_find_candidate_windows("")` renvoie `[]` (défense en profondeur).

### Invariant 3 — zéro LLM dans la validation
`core/validator.py` importe `intent_classifier` (types), `browser_bridge` et `world_state` ; aucune dépendance Ollama, aucun appel réseau. Les ajouts de ce sprint sont des listes constantes et des comparaisons de chaînes. `_validate_plan` reste purement local (le LLM intervient dans `plan()`, en amont, pour **produire** le plan, pas pour le valider).

---

## 5. Résultats des tests

Environnement : `.venv` (Python 3.12.3, pytest 9.0.2), racine du dépôt, Atlas arrêté, Docker actif.

### SV1 — état rouge, avant toute correction
```
python -m pytest tests/test_action_safety_b1.py -q
20 failed, 325 warnings in 42.54s
```

Extraits bruts, défaut par défaut :

**L5 — action unique**
```
E       AssertionError: le validateur laisse passer une frappe de texte arbitraire : window_hotkey params={'keys': 'Fichier'}
E       assert not ('window_hotkey' == 'window_hotkey'
E           window_hotkey and 'Fichier' == 'Fichier'
```
**L5 — paramètres invalides (7 cas)**
```
E       AssertionError: 'Fichier' exécutable tel quel : params={'keys': 'Fichier'}
E       assert 'window_hotkey' != 'window_hotkey'
E       AssertionError: '' exécutable tel quel : params={'keys': ''}
```
**L24 — action unique, Discord au premier plan**
```
E       AssertionError: clic dirigé vers le premier plan
E       assert 'Discord' not in '★ conversat...ée - Discord'
E         'Discord' is contained here:
E           ★ conversation privée - Discord
```
**L24 — plan C05 (« ouvre le bloc-notes puis clique sur Fichier »)**
```
E       AssertionError: assert 'Discord' not in '★ conversat...ée - Discord'
```
**L24 — grounding, cible vide**
```
E       AssertionError: assert 'global_timeout' == 'no_target'
E         - no_target
E         + global_timeout
```
(la fonction avait donc parcouru les couches pendant 20 s sur des fenêtres quelconques)

### SV6.1 — après correction
```
python -m pytest tests/test_action_safety_b1.py -q
20 passed in 0.15s
```

### SV6.2 — suite complète
```
python -m pytest tests/ -q
397 passed in 72.12s (0:01:12)
exit=0
```

**Écart 377 → 397, expliqué :** +20 tests de `tests/test_action_safety_b1.py`. Aucun test supprimé.

**Deux fichiers de tests existants modifiés, et pourquoi :**

| Test | Avant | Après | Raison |
|---|---|---|---|
| `test_sprint_kimi_understanding_v51::test_click_on_element_uses_foreground_title_when_app_missing` | Vérifiait que le clic se rabattait sur le titre du premier plan (« Amis - Discord ») | Renommé `..._refuses_foreground_title_when_app_missing` : vérifie le refus | **Ce test encodait le défaut L24.** Le corriger sans changer ce test aurait été impossible ; le conserver revenait à protéger le défaut |
| `test_vision_parsers::TestGroundingTimeoutEnforced` (3 tests) | Appelaient `find_and_click` sans simuler la recherche de fenêtre ni la couche EasyOCR | Ajout des deux mocks | `find_and_click` exige désormais une fenêtre existante. En prime, ces tests passent de ~13 s à 3,3 s : ils chargeaient réellement EasyOCR |

**Instabilité constatée, sans rapport avec ce sprint :** au premier passage complet, `test_web_v20::test_07_searxng_403_fallback_ddg_triggered` a échoué (`fallback_link` au lieu de `duckduckgo`). Exécuté seul, il passe **avec et sans** les modifications de ce sprint ; il a repassé dans les deux passages complets suivants. Cause probable : limitation de débit du repli DuckDuckGo quand les dix tests web s'enchaînent. Consigné en section 7 (B1-R5).

### SV5 / SV6.3 — couverture
```
python -m pytest tests/ -q --cov=core.validator --cov=core.planner --cov=tools.grounding
```
| Module | Avant | Après |
|---|---|---|
| `core/validator.py` | **41 %** (92/227) | **55 %** (143/260) |
| `core/planner.py` | 36 % (29/80) | 59 % (55/94) |
| `tools/grounding.py` | 25 % | 25 % (inchangé : le sprint n'ajoute que des refus précoces) |

`resolve` : 31 % au sprint A → **38 %**. Les mesures « avant » proviennent d'un passage complet sur l'arbre remisé (`git stash`), donc du code réel d'avant correction.

**Chemins de `resolve` encore non couverts (84 lignes), par bloc :** catégorie `automation` (32 lignes : `schedule`, `trigger`, `workflow*`), catégorie `web` (navigate / open_tab / read / search, ~20 lignes), `window_mgmt` close et focus par anaphore (~15 lignes), verbe inconnu, `window_type`, `process/kill`.

**Code mort trouvé dans le validateur (signalé, non supprimé — hors périmètre de correction) :**
- `Validator._is_browser()` : défini, **jamais appelé** (aucune référence dans le dépôt) ;
- `_BROWSER_PROCESSES` : constante **jamais lue** ;
- `_BROWSER_NAMES` : lue uniquement par `_is_browser`, donc morte par transitivité.

Du code mort dans un validateur de sécurité entretient l'illusion d'une protection : à supprimer dans la tranche suivante.

### SV6.4 — rejeu réel du scénario C05

**Rejeu 1 — chaîne complète avec le vrai planificateur LLM** (Explorateur de fichiers au premier plan, aucun Bloc-notes ouvert) :
```
premier plan : 'docs : Explorateur de fichiers'
intent: category=window_mgmt verb=open target='bloc-notes' complex=True
plan LLM (2 étapes) : 'Ouvrir bloc-notes et cliquer sur Fichier'
  étape 1: action='open'   -> tool='launch_app'    params={'name': 'bloc-notes'}        rejected=False
  étape 2: action='hotkey' -> tool='window_hotkey' params={'keys': ['alt', 'f']}        rejected=False
résultats (94.7s) : launch_app success ; window_hotkey success "Raccourci 'alt+f' envoyé."
```
Le LLM a produit cette fois un **raccourci valide** (`alt+f`), accepté et normalisé en liste par la nouvelle validation. Le chemin du clic n'a donc pas été exercé par ce tirage : d'où le rejeu 2.

**Rejeu 2 — chemin du clic, plan C05 exact passé par le vrai `_validate_plan` puis le vrai moteur** :
```
premier plan : 'docs : Explorateur de fichiers'
  étape 1: 'open'  -> tool='launch_app'       params={'name': 'bloc-notes'}
  étape 2: 'click' -> tool='ui_click_element' params={'element_name': 'Fichier', 'app_title': 'bloc-notes'}
  exécution en 31.0s
  launch_app        status='success'
  ui_click_element  status='success'  "Clic OCR sur 'Fichier' à (300, 318), confiance=77%."
```
**La cible est « bloc-notes », pas l'Explorateur au premier plan, et le clic a atteint le menu Fichier du Bloc-notes.**

**Rejeu 3 — « clique sur Fichier » sans application nommée, processus neuf** (Bloc-notes au premier plan, pour mettre la règle à l'épreuve) :
```
[VALIDATOR] Action refusée (interaction/click) : application cible indéterminée pour le clic
tool = '__conversation__' | rejected = True
message = "Action refusée : application cible indéterminée pour le clic. Précise l'application,
           par exemple « clique sur Fichier dans le bloc-notes »."
exécution -> status='conversation'
```
Aucune action exécutée, alors même qu'une fenêtre était disponible au premier plan.

**Contrôle des effets de bord.** Une fenêtre `*Fichier – Bloc-notes` est apparue pendant le rejeu 1. **Elle ne vient pas de ce rejeu** : c'est l'onglet non enregistré créé par l'incident du sprint A (C02), que le Bloc-notes de Windows 11 restaure à son lancement. Preuves : aucun Bloc-notes ne tournait avant le rejeu ; la seule action clavier du rejeu était `alt+f`, qui ouvre un menu et ne saisit rien ; le titre correspond exactement à celui observé au sprint A. Cet onglet a depuis disparu (arrêt forcé du Bloc-notes). Toutes les fenêtres ouvertes par les rejeux ont été fermées.

---

## 6. Comportement observé en scénarios réels

| ID | Scénario | Attendu | Observé | Statut |
|---|---|---|---|---|
| B1-S01 | `window_hotkey {'keys': 'Fichier'}` (avant correction) | — | Résolu en action exécutable : 7 frappes potentielles | Défaut reproduit |
| B1-S02 | Idem après correction | Refus | `rejected=True`, message « raccourci clavier invalide (touche inconnue : 'Fichier') » | PASS |
| B1-S03 | `ctrl+s`, `["alt","f4"]`, `CTRL+SHIFT+n`, `win`, `f5` | Acceptés | Acceptés, normalisés en listes minuscules | PASS |
| B1-S04 | Plan contenant un raccourci invalide | Chaîne abandonnée | Plan réduit à l'étape refusée ; `launch_app` non exécuté | PASS |
| B1-S05 | Clic sans application, Discord au premier plan (avant) | — | `app_title` = titre Discord | Défaut reproduit |
| B1-S06 | Idem après correction | Refus explicite | Refusé, premier plan seulement journalisé | PASS |
| B1-S07 | Plan C05, validation | Héritage de l'application | `app_title='bloc-notes'` | PASS |
| B1-S08 | **Rejeu réel C05** | Clic sur le Bloc-notes ou échec clair | Clic OCR sur « Fichier » dans le Bloc-notes, (300, 318) | PASS |
| B1-S09 | **Rejeu réel, clic sans application** | Refus, aucune action | Refus, message utilisateur | PASS |
| B1-S10 | Plan LLM réel (tirage du jour) | Pas de frappe parasite | `alt+f` valide, accepté et normalisé | PASS |
| B1-S11 | Grounding, cible vide | Échec immédiat | `no_target` (avant : 20 s puis `global_timeout`) | PASS |
| B1-S12 | Grounding, application absente | Échec explicite | `app_not_found`, aucune couche tentée | PASS |

---

## 7. Limites et risques identifiés

| # | Description | Sévérité | Mitigation proposée |
|---|---|---|---|
| B1-R1 | **Sept actions à effet de bord acceptent encore des paramètres non validés** (annexe A). Deux sont de la même famille que L5 : `window_type` et `window_hotkey` sans `target` frappent dans la fenêtre au premier plan. Une est destructive : `window_close("")` sélectionnerait toutes les fenêtres et fermerait la première — atténué par la confirmation obligatoire sur le verbe `close`. | **Élevé** | Tranche suivante : appliquer à ces actions la même logique (cible obligatoire, paramètres en liste blanche). Priorisation en annexe A. |
| B1-R2 | Le refus passe par `tool="__conversation__"`, faute de canal d'erreur propre : `core/intent_engine.py` est hors périmètre. L'utilisateur reçoit bien le message, mais le refus n'est pas distinguable d'une réponse conversationnelle dans les métriques (`atlas_actions.jsonl`). | Moyen | Quand `intent_engine` sera dans le périmètre : statut `rejected` dédié et journalisation dans les métriques. |
| B1-R3 | `resolve` reste à 38 % : les branches `automation` (32 lignes) et `web` ne sont pas couvertes, alors qu'elles créent des tâches planifiées et ouvrent des URL. | Moyen | Étendre les tests de décision à ces catégories dans la tranche suivante. |
| B1-R4 | **Code mort dans le validateur** : `_is_browser`, `_BROWSER_NAMES`, `_BROWSER_PROCESSES`. | Faible | Suppression dans la tranche suivante (hors périmètre ici). |
| B1-R5 | `test_web_v20::test_07` est instable en suite complète (repli DuckDuckGo limité en débit). Passe seul, sur `main` comme sur cette branche. | Faible | Rendre le test tolérant aux trois sources de repli, ou le marquer `network`. |
| B1-R6 | Le rejeu 1 n'a pas exercé le chemin du clic : le plan LLM varie d'un tirage à l'autre. Le chemin a été rejoué de façon déterministe (rejeu 2), mais sur un plan fourni par moi, pas produit par le modèle. | Faible | Rejouer la phrase plusieurs fois lors de la prochaine session réelle. |
| B1-R7 | `launch_app` reste non idempotent : trois lancements du Bloc-notes observés à chaque rejeu (défaut L6, hors périmètre). Il brouille la lecture des rejeux. | Moyen | Tranche L6, déjà inventoriée au sprint A. |
| B1-R8 | La liste blanche de touches est définie à la main. Une touche légitime absente (claviers non français, touches multimédia rares) serait refusée à tort — refus visible et corrigible, jamais dangereux. | Faible | Compléter à l'usage ; la comparer à `pyautogui.KEYBOARD_KEYS` reste possible. |
| B1-R9 | L'héritage d'application entre étapes ne couvre que les étapes `click`. Un `type` ou un `hotkey` d'une chaîne n'hérite de rien (et n'a pas de `target`), donc frappe au premier plan. | **Élevé** (lié à B1-R1) | Étendre l'héritage à `type` et `hotkey` **en même temps** que l'obligation de cible, pour ne pas rediriger des frappes par surprise. |
| B1-R10 | La branche `sprint-b1` n'est ni poussée ni fusionnée. | Faible | Relecture et fusion par Alexis. |

---

## 8. Checklist de validation

- [x] **Les deux défauts reproduits en tests échouant d'abord, sorties brutes consignées** : section 5 (SV1), 20 rouges.
- [x] **L5 corrigé : paramètres de touches en liste blanche, rejet propre et journalisé** : section 4, B1-S02.
- [x] **L24 corrigé : cible = application nommée ou lancée à l'étape précédente, échec explicite sinon** : section 4, B1-S06 à B1-S09.
- [x] **Tableau de revue des paramètres d'action à effet de bord livré** : annexe A.
- [x] **Couverture de `core/validator.py` mesurée avant et après** : 41 % → 55 % (section 5).
- [x] **`python -m pytest tests/ -q` → code 0, aucun écart inexpliqué** : 397 passés ; +20 tests, deux fichiers modifiés justifiés.
- [x] **Scénario C05 rejoué réellement : aucune frappe parasite, aucun clic sur la mauvaise fenêtre** : section 5 (SV6.4), avec l'origine de la fenêtre `*Fichier` établie.
- [x] **Aucun appel LLM introduit dans le chemin de validation** : section 4.
- [x] **Aucune modification hors `core/validator.py`, `core/planner.py`, `tools/grounding.py`, `tests/`** : `git diff --name-only`.

---

## 9. Recommandations pour le sprint suivant

### P1 — même famille de défauts, déjà identifiés
- **P1.1** Cible obligatoire pour `window_type` et `window_hotkey` (B1-R1, B1-R9) : une frappe sans fenêtre nommée doit être refusée, comme le clic. C'est le prolongement direct de ce sprint, et le risque résiduel le plus élevé.
- **P1.2** `window_close` / `window_focus` / `window_minimize` / `window_maximize` / `window_snap` : refuser un titre vide (aujourd'hui « toutes les fenêtres », première servie).
- **P1.3** `window_click` : valider que les coordonnées sont dans les limites de l'écran (`_point_in_bounds` existe déjà dans le grounding).

### P2
- P2.1 Canal d'erreur propre pour les refus, quand `intent_engine` entrera dans le périmètre (B1-R2).
- P2.2 Couverture des branches `automation` et `web` de `resolve` (B1-R3).
- P2.3 Suppression du code mort du validateur (B1-R4).
- P2.4 `launch_app` idempotent (L6) : il fausse tous les rejeux (B1-R7).

### P3
- P3.1 Stabiliser `test_web_v20::test_07` (B1-R5).
- P3.2 Reste de B-complet : voix (L1, L2, L3), heure inventée (L4), couches OCR bloquantes (L9), `/api/health` trompeur (C04).

---

# Annexe A — Revue des paramètres d'action à effet de bord (SV4)

Revue des 18 actions capables de modifier l'état de la machine. « Détecté ? » = le validateur rejette-t-il un paramètre absurde produit par le LLM.

| Action | Paramètres acceptés | Si le LLM produit une valeur absurde | Détecté ? | Suite |
|---|---|---|---|---|
| `window_hotkey` | `keys`, `target` | **keys** : corrigé ce sprint (liste blanche). **target absent → frappe dans la fenêtre au premier plan** | Partiel | **P1.1** |
| `window_type` | `text`, `target`, `use_clipboard` | `target` absent → texte tapé dans la fenêtre au premier plan ; `text` non contraint (peut contenir des séquences de contrôle) | **Non** | **P1.1** |
| `ui_click_element` | `element_name`, `app_title` | Corrigé ce sprint : cible obligatoire, fenêtre vérifiée, refus sinon | **Oui** | — |
| `window_click` | `x`, `y`, `button`, `clicks`, `target` | Coordonnées hors écran ou arbitraires → clic n'importe où ; aucun contrôle de bornes | **Non** | **P1.3** |
| `window_close` | `title` | `title=""` → `getWindowsWithTitle("")` renvoie toutes les fenêtres, la première est fermée. Atténué : confirmation obligatoire sur `close` | Partiel (confirmation) | **P1.2** |
| `window_focus` / `window_minimize` / `window_maximize` | `title` | Même mécanisme, sans confirmation ; effet limité (focus, réduction) | **Non** | P1.2 |
| `window_snap` | `title`, `position` | `position` libre (chaîne non validée) ; titre vide → fenêtre arbitraire | **Non** | P1.2 |
| `launch_app` | `name`, `path`, `wait` | `path` arbitraire → exécution d'un binaire quelconque ; `name` inconnu → résolution floue puis échec | **Non** (chemin) | P2 |
| `kill_process` | `pid`, `name` | Confirmation **forcée par le moteur** pour `kill_process`, plus classification intouchable/demande/libre | **Oui** | — |
| `set_priority` | `pid`, `priority` | `priority` non validée ; `KeyError` si absente | **Non** | P2 |
| `run_powershell` | `command` | Liste blanche **et** liste noire dans `system_config` (`Remove-Item`, `Invoke-Expression`, `reg delete`…), journalisé dans `audit_log.jsonl` | **Oui** | — |
| `system_config` | `action`, `**kwargs` | Confirmation forcée pour `shutdown`, `restart`, `hibernate`, `sleep` ; autres actions non validées | Partiel | P2 |
| `browser_navigate` / `browser_open` / `browser_new_tab` | `url` | URL non validée (`file://`, `javascript:` non filtrés) | **Non** | P2 |
| `browser_ext_click` / `browser_ext_type` | sélecteur, texte | Non validés ; dépend de l'extension | **Non** | P3 |
| `schedule_add` | `name`, `trigger_type`, `trigger_config`, `actions` | Confirmation obligatoire (validateur) ; **contenu des actions planifiées non validé** — une action absurde est enregistrée puis rejouée à chaque déclenchement | Partiel | P2 |
| `trigger_add` | condition, actions | Idem : confirmation, contenu non validé | Partiel | P2 |
| `workflow_run` / `workflow_create` | `name`, `steps` | Confirmation obligatoire ; étapes YAML non validées à la création | Partiel | P2 |
| `redo_last_action` | — | Rejoue la dernière action du `WorldState` ; hérite des contrôles de l'action d'origine | **Oui** | — |

**Lecture d'ensemble.** Le problème est **large, mais structuré** : sur 18 actions, 4 sont correctement protégées (PowerShell par liste blanche, `kill_process` et les arrêts système par confirmation forcée, le clic depuis ce sprint), 6 le sont partiellement par une confirmation qui ne valide pas le contenu, et 7 ne valident rien. Toutes les lacunes relèvent du même principe : **le validateur fait confiance aux paramètres produits par le LLM**. La parade est la même partout — cible obligatoire, valeurs en liste blanche, bornes vérifiées — et ce sprint en fournit le patron avec `normalize_hotkey_keys` et `_reject`.

---

*Rapport Sprint B1 — CHAT6 (Claude Opus 5, Claude Code Windows), 17/09/2026.*
