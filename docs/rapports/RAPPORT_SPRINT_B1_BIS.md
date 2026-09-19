# RAPPORT SPRINT B1-BIS — Généraliser le patron de sécurité aux actions restantes
Date: 19/09/2026
Agent: Claude Opus 5 (CHAT6, Claude Code Windows)

> Brief : `docs/briefs/BRIEF_SPRINT_B1_BIS.md`. Références : rapport B1, annexe A (SV4).
> Branche **`sprint-b1-bis`**, issue de `sprint-b1` @ `0552532`. 2 commits (correctifs `32e28a6` + ce rapport), **non poussés**.

---

## 1. Résumé exécutif

**Statut global : VALIDÉ.**

- **L5 est maintenant corrigé en entier.** B1 contrôlait *ce qui* est frappé ; B1-bis contrôle aussi *où*. `window_type` et `window_hotkey` exigent une fenêtre cible. Cette cible est la fenêtre nommée ; à défaut, la fenêtre de travail récente ; sinon la demande est refusée. Le premier plan n'est **jamais** utilisé par défaut.
- **Côté outil, le premier plan est vérifié après le focus et avant la moindre frappe.** Sans cette vérification, un focus « réussi » que Windows n'a pas réellement accordé laissait le texte partir dans la fenêtre active.
- **Rejeu réel (critère décisif du brief).** Une fenêtre témoin étrangère à la demande est au premier plan, et trois demandes de frappe sont envoyées : refus explicite sans cible, texte livré dans la bonne fenêtre, héritage de cible dans un plan. **Contenu final du témoin : `''`** (aucun caractère parasite).
- Contrôles ajoutés sur les autres actions : titres vides refusés sur les 5 actions de fenêtre, position d'ancrage en liste blanche, bornes de clic multi-écrans, URL limitées à `http`/`https`.
- **Tests :** **146 nouveaux**, vus rouges avant correction (**121 échecs**). Suite complète : **543 passés, 4 ignorés, code 0** (397 + 146).
- **Couverture de `core/validator.py` : 55 % → 70 %.** Pour `resolve` seule : 38 % → 66 %.
- **Annexe A recalculée** sur les 18 actions : **11 protégées, 4 partiellement, 3 pas du tout.** Avant ce sprint : 4 / 6 / 8, et non 4 / 6 / 7 comme l'écrivait le rapport B1 (erreur de décompte corrigée en annexe).
- BS5 : deux analyses livrées en annexe B, **sans code**.
- Invariant 3 respecté (aucun appel LLM ajouté). Un seul fichier touché hors de la liste du brief, `core/planner.py` (10 lignes), **sur autorisation explicite** demandée en cours de sprint.
- **État à l'heure du rapport :**
  - conteneurs `atlas_chromadb` et `atlas_searxng` démarrés ;
  - Ollama 0.34.1 joignable ;
  - API Atlas (port 8550) arrêtée : le rejeu appelle directement le pipeline.

---

## 2. Objectifs vs réalisation

| Objectif (brief) | Résultat réel | Statut |
|---|---|---|
| Méthode : tests rouges d'abord, sorties brutes, aucun effet réel | 146 tests écrits avant correction. **121 rouges**, et chaque échec montre le défaut lui-même, pas une erreur d'import. Les 27 tests verts d'emblée sont des contreparties d'acceptation (voir §5). pyautogui est piégé ; focus, fenêtre active et écrans sont simulés. | PASS |
| BS1 — `window_type` / `window_hotkey` : cible obligatoire, refus sinon | Validateur : cible nommée, sinon fenêtre de travail récente **réussie** de moins de 2 min, sinon refus. Outil : cible exigée, puis premier plan vérifié après le focus. | PASS |
| BS1 — cible héritée de l'étape précédente du plan | Planificateur : une étape `type`/`hotkey` reçoit `step.target`, à défaut l'application courante du plan. Modification hors périmètre, autorisée explicitement. | PASS |
| BS1 — contrainte sur `text` : définie, justifiée, appliquée | Définie en §4.3 : chaîne de 1 à 2 000 caractères, aucun caractère de contrôle sauf `\n` et `\t`. Appliquée dans le validateur et dans l'outil. | PASS |
| BS2 — titre vide refusé (close, focus, minimize, maximize, snap) | Refus dans le validateur, plus de repli sur le premier plan. Refus dans les 5 outils, avant tout appel à `getWindowsWithTitle`. | PASS |
| BS2 — `position` de `window_snap` en liste blanche | `VALID_SNAP_POSITIONS`, contrôlée dans le validateur et dans l'outil | PASS |
| BS3 — bornes des coordonnées de `window_click`, multi-écrans | Point exigé sur un écran réel (`EnumDisplayMonitors`) ; coordonnées négatives acceptées si un écran s'y trouve. Point exigé dans la fenêtre cible si elle est nommée. | PASS |
| BS4 — schémas d'URL en liste blanche | `http` et `https` seulement. `file:`, `javascript:` (y compris masqué par des espaces ou caractères de contrôle), `data:`, `vbscript:`, `ms-settings:`, `ftp:` et les URL sans hôte sont refusés, dans le validateur et dans `browser_bridge`. | PASS |
| BS5 — deux analyses, **aucun code** | Annexe B : `launch_app(path)` et contenu des actions planifiées. Aucun code écrit sur ces deux points. | PASS |
| BS6.1 — tests BS1 à BS4 verts après avoir été vus rouges | 146/146 (4 cas ignorés volontairement, voir §5) | PASS |
| BS6.2 — `python -m pytest tests/ -q` → code 0, écarts expliqués | 543 passés, 4 ignorés, code 0. Un test B1 adapté, expliqué en §5. | PASS |
| BS6.3 — rejeu réel : frappe avec une autre application au premier plan | 3 cas, témoin vide de bout en bout (§6) | PASS |
| BS6.4 — couverture du validateur avant/après | 55 % → 70 % (§5) | PASS |
| BS6.5 — rapport conforme, annexe A recalculée | Ce document ; annexe A | PASS |

---

## 3. Architecture projet mise à jour

```
cortana-killer-atlas/
├── core/
│   ├── validator.py                     ← modifié (frappe, fenêtres, snap, clic, URL)
│   └── planner.py                       ← modifié (10 lignes : cible des étapes de frappe) — hors périmètre, autorisé
├── tools/
│   ├── window_controller.py             ← modifié (contrôles purs + garde-fous dans les outils)
│   └── browser_bridge.py                ← modifié (liste blanche de schémas d'URL)
├── tests/
│   ├── test_action_safety_b1_bis.py     ← NOUVEAU B1-bis (146 tests + 4 ignorés)
│   └── test_action_safety_b1.py         ← modifié (1 test : cible ajoutée, voir §5)
└── docs/rapports/
    └── RAPPORT_SPRINT_B1_BIS.md         ← NOUVEAU B1-bis
```

Diff du commit `32e28a6` : 6 fichiers, dont `core/validator.py` (+147), `tools/window_controller.py` (+188), `tools/browser_bridge.py` (+58), `core/planner.py` (+10).

Scripts de rejeu et de diagnostic, **non versionnés** (répertoire temporaire de session) : `b1bis_witness.py`, `b1bis_replay_type.py`, `b1bis_diag_focus.py`, `b1bis_cov.py`, `b1bis_junit.py`.

---

## 4. Détail des implémentations

### 4.1 Où placer les contrôles : constat préalable

Avant de coder, j'ai recensé tous les chemins qui appellent les outils. Le validateur ne voit **pas** tout :

| Chemin | Passe par le validateur ? | Actif ? |
|---|---|---|
| Requête utilisateur → classifieur → validateur → moteur | Oui | Oui |
| Plan LLM → `Planner._validate_plan` → validateur | Oui | Oui |
| Planificateur horaire, déclencheurs, workflows → `main._execute_action` → `execute_tool` | **Non** | **Oui** |
| `execute_confirmed` (après confirmation) | Non ; paramètres déjà passés par `execute_tool` | Oui |
| `redo_last_action` → `TOOL_HANDLERS` | Non ; rejoue une action déjà exécutée | Oui |
| `Orchestrator`, `process_ai_response` (appel d'outils par le LLM) | Non | Non (branchés nulle part) |

**Conséquence :** les contrôles sont écrits comme **fonctions pures dans les modules d'outils**, et appliqués deux fois :
- par le validateur, pour un refus propre avant exécution, avec message à l'utilisateur ;
- par l'outil lui-même, en défense en profondeur pour les chemins sans validateur.

Il y a une seule définition par règle, pas de duplication. Aucun workflow, tâche planifiée ou déclencheur existant n'utilise `window_*` ni le navigateur (vérifié dans `data/workflows/*.yaml`, `data/schedules.json` et `data/triggers.json`) : ce durcissement ne casse aucun usage enregistré.

### 4.2 `tools/window_controller.py`

**Contrôles purs** (sans effet ; chacun retourne un message d'erreur, vide si le paramètre est acceptable) :
- `check_type_text(text) -> (texte, erreur)` : contrainte sur `text` (§4.3).
- `check_window_title(title) -> (titre, erreur)` : chaîne non vide après `strip()`.
- `check_click_params(x, y, button, clicks) -> erreur` : `x` et `y` entiers (booléens exclus) et présents, point dans l'un des écrans, `button` ∈ {left, right, middle}, `clicks` entre 1 et 3.
- `_monitor_rects()` : rectangles réels des écrans via `win32api.EnumDisplayMonitors` ; repli sur `pyautogui.size()` sans pywin32.
- `VALID_SNAP_POSITIONS` : les 6 positions que `window_snap` savait déjà gérer.

**Garde-fous dans les outils :**
- `_focus_and_verify(target)` (**nouveau, pièce centrale**) :
  - met la cible au premier plan ;
  - relit la fenêtre **réellement active** (`gw.getActiveWindow()`) ;
  - refuse si son titre ne correspond à aucun alias de la cible.
  - Raison : `focus_window` peut rendre `success` sans que Windows ait cédé le premier plan (protection contre le vol de focus d'un processus en arrière-plan). Le texte partait alors dans la fenêtre active. Ce cas est couvert par `test_bs1_outil_focus_rate_ne_tape_pas_au_premier_plan`, dont la sortie rouge était *« texte tapé dans '★ conversation privée - Discord' au lieu du bloc-notes »*.
- `window_type` : cible obligatoire, texte contrôlé, `_focus_and_verify`, puis frappe.
- `window_hotkey` : cible obligatoire, puis `_focus_and_verify`.
- `window_click` : `check_click_params`. Si une cible est nommée, `_focus_and_verify`, puis point exigé dans le rectangle de la fenêtre active.
- `WindowController.focus_window` refuse les titres vides. Ce n'est pas anodin : pywinauto cherchait alors `title_re=".*.*"` (n'importe quelle fenêtre).
- `window_close`, `window_minimize`, `window_maximize`, `window_snap` : titre vide refusé **avant** `getWindowsWithTitle` ; position d'ancrage contrôlée avant toute action.

### 4.3 Contrainte sur `text` (BS1), définie avant application

| Règle | Justification |
|---|---|
| Doit être une **chaîne** | `pyautogui.typewrite` interprète une **liste** comme des noms de touches : `["win", "r"]` ouvre la boîte Exécuter. Un LLM qui renvoie une liste obtient donc des frappes de touches, pas du texte. |
| **Non vide** | Une frappe vide n'a pas de sens. Un `None` qui devient `""` masquerait une erreur du planificateur. |
| **2 000 caractères au plus** | Tapé caractère par caractère (0,02 s d'intervalle), un texte long prend des dizaines de secondes, pendant lesquelles le premier plan peut changer (risque B1B-R3). La limite borne cette fenêtre de temps. |
| **Aucun caractère de contrôle** (Unicode `Cc`) **sauf `\n` et `\t`** | Échappement (`\x1b`), retour arrière (`\x08`), NUL, DEL… n'ont rien à faire dans un texte dicté. `\n` et `\t` ont un sens (lignes, colonnes). `\r\n` et `\r` sont normalisés en `\n`. |
| Accents et Unicode imprimable acceptés | Ce ne sont pas des risques. `typewrite` ne sait pas taper certains caractères non ASCII, mais c'est une limite fonctionnelle, pas de sécurité (B1B-R9). |

### 4.4 `tools/browser_bridge.py`

- `ALLOWED_URL_SCHEMES = {"http", "https"}`. J'ai cherché d'autres schémas dans le code : `ms-settings:` et `steam://` existent, mais uniquement dans `launch_app`, jamais pour le navigateur. Aucun autre schéma n'a donc un usage avéré en navigation.
- `check_url(url, allow_empty=False) -> (url, erreur)`. Les espaces de tête et de fin sont retirés. Tout espace ou caractère de contrôle (`Cc`, `Cf`) **restant** est refusé : les navigateurs les ignorent dans le schéma (`java\tscript:`, `\x01javascript:`), donc les nettoyer reviendrait à contrôler autre chose que ce que le navigateur verra. Puis `urlsplit` vérifie le schéma (insensible à la casse) et exige un nom d'hôte.
- `browser_navigate` et `browser_new_tab` appliquent `check_url` avant tout envoi à l'extension. Seul un nouvel onglet peut être vide.

### 4.5 `core/validator.py`

- Import des contrôles ci-dessus. Aucun appel LLM : que des comparaisons et des listes constantes (invariant 3).
- `_resolve_working_window(world_state)` (nouveau) : la fenêtre nommée par la dernière action **réussie** (`result.status == "success"`) de moins de 2 minutes. Actions retenues : `ui_click_element`, `launch_app`, `window_focus`, `window_maximize`, `window_type`, `window_hotkey`. Atlas Desktop est exclu. Une action échouée ou périmée ne transmet rien (testé).
- `type` / `hotkey` :
  - le texte ou les touches sont contrôlés d'abord, pour que le message L5 de B1 reste inchangé ;
  - la cible vient de `params["target"]`, sinon de `_resolve_working_window`, sinon la demande est refusée ;
  - `intent.target` n'est **pas** utilisé : pour une frappe issue du classifieur, c'est le texte lui-même (rejeu : `target="'bonjour atlas' dans cible-b1bis"`).
- `close` : titre obligatoire. La confirmation seule ne protégeait pas, puisqu'elle portait sur « fermer une fenêtre » sans dire laquelle.
- `minimize` / `maximize` / `focus` : l'anaphore « remets-la » passe toujours par la dernière action. Le **repli sur le premier plan est supprimé** (même règle que L24), et `__last_window__` ne peut plus partir comme titre.
- `snap` (nouvelle branche) : titre obligatoire, position en liste blanche, paramètres reconstruits explicitement.
- `select` → `window_click` (nouvelle branche) : `check_click_params`. Les paramètres sont reconstruits (`x`, `y`, `button`, `clicks`, `target` éventuel).
- `navigate` / `open_tab` : `check_url` **avant** le choix de la voie (extension, `browser_open` ou `launch_app`), donc les trois voies sont couvertes.

### 4.6 `core/planner.py` (hors périmètre, autorisé)

Dans `_validate_plan`, une étape `type` ou `hotkey` sans `params["target"]` reçoit `step.target`, à défaut l'application courante du plan. `current_app` suit aussi la cible des étapes de frappe.

**Défaut trouvé à cette occasion :** l'exemple même du prompt du planificateur place la fenêtre dans `step.target` (`{"action": "type", "target": "bloc-notes", "params": {"text": "hello"}}`), mais le validateur ne transmettait que `params`. **La cible des frappes planifiées était donc perdue avant ce sprint**, et le texte partait au premier plan. Sortie rouge : *« cible attendue bloc-notes, obtenue None : la frappe irait au premier plan »*.

---

## 5. Résultats des tests

### État rouge, avant toute correction

```
python -m pytest tests/test_action_safety_b1_bis.py -q -p no:cacheprovider -rfps --tb=no
121 failed, 27 passed, 2 skipped in 1.20s
```

Sorties brutes (une par test ; les variantes paramétrées sont du même type) :

```
test_bs1_frappe_sans_cible_est_refusee - AssertionError: frappe sans cible, partirait dans la fenêtre au premier plan : window_type {'text': 'bonjour'}
test_bs1_hotkey_sans_cible_est_refuse - AssertionError: raccourci sans cible, partirait dans la fenêtre au premier plan : window_hotkey {'keys': ['ctrl', 's']}
test_bs1_frappe_herite_du_contexte_de_travail_recent[last_action0] - AssertionError: assert None == 'bloc-notes'
test_bs1_contexte_perime_ou_en_echec_nest_pas_herite - AssertionError: assert False is True
test_bs1_plan_la_frappe_vise_lapplication_ouverte[step1] - AssertionError: cible attendue bloc-notes, obtenue None : la frappe irait au premier plan
test_bs1_texte_invalide_refuse[\x1b[2J] - AssertionError: texte '\x1b[2J' accepté : {'text': '\x1b[2J', 'target': 'bloc-notes'}
test_bs1_texte_invalide_refuse[None] - AssertionError: texte None accepté : {'text': None, 'target': 'bloc-notes'}
test_bs1_outil_window_type_sans_cible_ne_tape_rien - AssertionError: texte tapé dans '★ conversation privée - Discord'
test_bs1_outil_window_hotkey_sans_cible_nenvoie_rien - AssertionError: raccourci envoyé à '★ conversation privée - Discord'
test_bs1_outil_focus_rate_ne_tape_pas_au_premier_plan - AssertionError: texte tapé dans '★ conversation privée - Discord' au lieu du bloc-notes
test_bs1_outil_texte_de_controle_refuse - AssertionError: séquence de contrôle tapée
test_bs2_action_de_fenetre_sans_titre_refusee[close] - AssertionError: close sans titre accepté : window_close {}
test_bs2_action_de_fenetre_sans_titre_refusee[minimize] - AssertionError: minimize dirigé vers le premier plan
test_bs2_anaphore_sans_fenetre_precedente_refusee - AssertionError: assert '__last_window__' != '__last_window__'
test_bs2_snap_parametres_invalides_refuses[params0] - AssertionError: window_snap accepté : {'title': 'bloc-notes', 'position': 'center'}
test_bs2_snap_valide_accepte - AssertionError: assert {'position': 'top-left'} == {'position': ... 'bloc-notes'}
test_bs2_outil_titre_vide_ne_touche_aucune_fenetre[-window_close] - AssertionError: window_close('') a agi sur '★ conversation privée - Discord' : ['close']
test_bs2_outil_titre_vide_ne_touche_aucune_fenetre[-window_snap] - AssertionError: window_snap('') a agi sur '★ conversation privée - Discord' : ['moveTo', 'resizeTo']
test_bs3_clic_coordonnees_invalides_refuse[params0] - AssertionError: window_click accepté : {'x': 5000, 'y': 500}
test_bs3_clic_coordonnees_invalides_refuse[params5] - AssertionError: window_click accepté : {}
test_bs3_outil_clic_hors_ecran_nest_pas_execute - AssertionError: clic hors écran exécuté
test_bs3_outil_clic_hors_de_la_fenetre_cible_nest_pas_execute - AssertionError: clic sur l'écran mais hors de la fenêtre cible exécuté
test_bs4_url_hors_liste_blanche_refusee[extension_connectee-navigate-file:///C:/Windows/win.ini] - AssertionError: navigate 'file:///C:/Windows/win.ini' accepté : browser_navigate {'url': 'file:///C:/Windows/win.ini'}
test_bs4_url_hors_liste_blanche_refusee[extension_connectee-navigate-\x01javascript:alert(1)] - AssertionError: navigate '\x01javascript:alert(1)' accepté : browser_navigate {'url': '\x01javascript:alert(1)'}
test_bs4_url_hors_liste_blanche_refusee[extension_absente-navigate-first_result] - AssertionError: navigate 'first_result' accepté : browser_open {'url': 'first_result'}
test_bs4_url_hors_liste_blanche_refusee[extension_absente-open_tab-javascript:alert(1)] - AssertionError: open_tab 'javascript:alert(1)' accepté : launch_app {'name': 'opera gx', 'args': ['javascript:alert(1)']}
test_bs4_outil_bridge_nenvoie_pas_une_url_dangereuse[browser_navigate-file:///C:/Windows/win.ini] - AssertionError: URL 'file:///C:/Windows/win.ini' transmise à l'extension
```

**Les 27 tests verts dès le départ sont des contreparties d'acceptation**, attendues vertes avant comme après. Elles prouvent que les corrections ne refusent pas trop :
- frappe avec cible explicite ;
- textes valides, dont `\n`, `\t`, les accents et exactement 2 000 caractères ;
- anaphore résolue ;
- actions de fenêtre avec titre ;
- clics sur l'écran principal **et sur un écran secondaire à gauche** (`x=-500`, `x=-1920`) ;
- URL https ;
- nouvel onglet vide ;
- frappe dans une cible correctement mise au premier plan.

**Un test ajusté entre le rouge et le vert, à signaler.** Dans `test_bs4_url_hors_liste_blanche_refusee`, j'avais classé `open_tab` avec `url=None` comme invalide. Or « ouvre un nouvel onglet » produit précisément une intention **sans clé `url`**, et un onglet vide est légitime. Le cas est désormais ignoré (`skip`), comme `url=""` : d'où **4 ignorés** (2 URL × 2 états de l'extension). Pour `navigate`, `None` et `""` restent refusés.

### Après correction

```
python -m pytest tests/test_action_safety_b1_bis.py -q -p no:cacheprovider --tb=short
146 passed, 4 skipped in 0.42s
```

### Suite complète : commande exacte du brief

```
python -m pytest tests/ -q
543 passed, 4 skipped in 71.57s (0:01:11)
exit=0
```

**Écart 397 → 543, expliqué :** +146 tests de `tests/test_action_safety_b1_bis.py`. Aucun test supprimé.

**Un test existant modifié :** `test_action_safety_b1.py::test_l5_hotkeys_valides_acceptees`. Il résolvait un raccourci valide **sans cible** et attendait une acceptation ; il encodait donc exactement la moitié de L5 que ce sprint ferme. Ce test porte sur les touches, pas sur la cible : il fournit désormais `"target": "bloc-notes"`, et son assertion sur les touches est inchangée. Sortie avant ajustement : `rejected=True, rejection_reason='fenêtre cible indéterminée pour la saisie'`.

**Non-régression, suite par suite** (même exécution, export JUnit) :

| Suite | Résultat |
|---|---|
| `test_action_safety_b1.py` | 20 passés |
| `test_action_safety_b1_bis.py` | 146 passés, 4 ignorés |
| `test_app_resolver_v51.py` | 5 passés |
| `test_automation_v30.py` | 15 passés |
| `test_backup_memory_guard.py` | 46 passés |
| `test_chroma_integration.py` | 5 passés |
| `test_compose_config.py` | 6 passés |
| `test_core_conversational.py` | 15 passés |
| `test_file_indexer_v51.py` | 2 passés |
| `test_file_organizer_v51.py` | 3 passés |
| `test_final_v50.py` | 10 passés |
| `test_identity_v60.py` | 8 passés |
| `test_interaction_v22.py` | 10 passés |
| `test_isolation.py` | 5 passés |
| `test_memory_v60.py` | 33 passés |
| `test_metrics_grounding_v52.py` | 7 passés |
| `test_orchestrator_v60.py` | 14 passés |
| `test_real_e2e_kimi_v51.py` | 2 passés |
| `test_redo_heuristics_v52.py` | 22 passés |
| `test_sprint_kimi_understanding_v51.py` | 14 passés |
| `test_stabilisation_v31.py` | 5 passés |
| `test_v53_migration.py` | 17 passés |
| `test_v601_patches.py` | 25 passés |
| `test_vision_parsers.py` | 45 passés |
| `test_vision_v60.py` | 24 passés |
| `test_voice_v40.py` | 12 passés |
| `test_voice_v602.py` | 17 passés |
| `test_web_v20.py` | 10 passés |
| **Total, 28 fichiers** | **543 passés, 4 ignorés, 0 échec** |

La suite complète est passée trois fois, toutes vertes : avec couverture (83 s), sans couverture (70 s), puis la commande exacte ci-dessus. Le test instable signalé au sprint B1 (`test_web_v20::test_07`, B1-R5) a passé les trois fois.

### Couverture (BS6.4)

Mesures sur la suite complète, avant (code de `0552532`) et après (`32e28a6`) :
```
python -m pytest tests/ -q -p no:cacheprovider --cov=core.validator --cov=core.planner --cov=tools.window_controller --cov=tools.browser_bridge --cov-report=json:<fichier>
```

| Module | Avant | Après |
|---|---|---|
| `core/validator.py` | **55 %** (143/260) | **70 %** (228/325) |
| — dont `resolve` | 38 % (mesure B1) | **66 %** (120/181) |
| `core/planner.py` | 59 % (55/94) | 62 % (63/102) |
| `tools/window_controller.py` | 35 % (107/307) | 49 % (194/395) |
| `tools/browser_bridge.py` | 23 % (38/162) | 38 % (75/196) |

Couverture des fonctions ajoutées ou modifiées :
- 100 % : `check_type_text`, `check_window_title`, `check_click_params`, `window_type`, `_reject`.
- Entre 82 % et 95 % : `window_click` (92 %), `normalize_hotkey_keys` (95 %), `check_url` (86 %), `_resolve_working_window` (82 %).
- Restent :
  - `_focus_and_verify` (71 %) : branche d'exception de `getActiveWindow` ;
  - `window_hotkey` (50 %) : le chemin nominal après focus n'est pas testé côté outil, alors que `window_type`, qui partage `_focus_and_verify`, l'est ;
  - `_monitor_rects` (11 %) : simulée dans tous les tests. Elle a été vérifiée **une fois sur le vrai poste, en lecture seule** :
    ```
    écrans réels : [(0, 0, 1920, 1080), (1920, 0, 3840, 1080)] | pyautogui.size() : (1920, 1080)
    (10, 10) -> accepté
    (1919, 1079) -> accepté
    (6920, 10) -> point (6920, 10) hors de tout écran
    (-5000, 10) -> point (-5000, 10) hors de tout écran
    ```
    Le poste a un second écran **à droite**. `pyautogui.size()` ne voit que le principal, ce qui justifie `EnumDisplayMonitors`.

Code mort, toujours signalé et non retiré (le brief le range en « à ne pas traiter ici ») : `_is_browser` (25 %), `_BROWSER_NAMES` et `_BROWSER_PROCESSES` dans le validateur.

---

## 6. Comportement observé en scénarios réels

**Dispositif.** Pour prouver « aucun texte dans la fenêtre au premier plan », il faut pouvoir **lire** ce que cette fenêtre a reçu. J'ai donc utilisé deux fenêtres témoins : deux processus Tk séparés, dont chacun recopie en continu le contenu de sa zone de texte dans un fichier.
- `cible-b1bis` : la fenêtre que l'utilisateur nomme.
- `temoin-b1bis` : placée **au premier plan** avant chaque cas, étrangère à la demande.

La chaîne est entièrement réelle : `collect_context` → classifieur → validateur (→ planificateur pour le cas C) → `ExecutionEngine` → `window_controller` → pyautogui. La seule neutralisation est l'enregistrement en mémoire longue (`_save_action_to_memory`), pour ne rien écrire dans la mémoire ChromaDB de l'utilisateur. Aucun Bloc-notes réel n'a été touché, ce qui évite la restauration de session de Windows 11 constatée au sprint B1.

| ID | Commande | Résultat attendu | Résultat observé | Statut |
|---|---|---|---|---|
| R1 | `écris 'bonjour atlas'` (aucune application nommée ni contexte récent ; témoin au premier plan) | Refus explicite, rien de tapé | `tool='__conversation__' rejected=True` ; message : *« Action refusée : fenêtre cible indéterminée pour la saisie. Précise l'application, par exemple « écris bonjour dans le bloc-notes ». »* ; cible `''`, témoin `''` | PASS |
| R2 | `écris 'bonjour atlas' dans cible-b1bis` (témoin au premier plan) | Texte dans la cible, **ou** échec explicite ; rien dans le témoin | `window_type {'text': 'bonjour atlas', 'target': 'cible-b1bis'}` → *« Texte tapé (13 caractères) »* ; premier plan passé à `cible-b1bis` ; **cible `'bonjour atlas'`, témoin `''`** | PASS |
| R3 | Plan `[focus cible-b1bis, type " + plan" sans cible]` (témoin au premier plan) | La frappe hérite de la fenêtre de l'étape 1 | étape 2 → `window_type {'text': ' + plan', 'target': 'cible-b1bis'}` ; **cible `'bonjour atlas + plan'`, témoin `''`** | PASS |

Verdict final du script : `VERDICT témoin au premier plan : OK (contenu final '')`.

**Déroulé honnête : trois passages ont été nécessaires, pour des raisons propres au dispositif témoin.**

1. **Premier passage.** Le témoin est bien resté vide, mais **la cible aussi**, alors qu'Atlas annonçait « Texte tapé (13 caractères) ». J'ai isolé le problème avec un diagnostic sur la seule fenêtre cible, en trois essais : focus d'Atlas, `activate()` de pygetwindow, puis clic dans la zone de texte. Après focus, Windows donnait bien le premier plan **et le focus clavier** à la fenêtre (`classe_focus='TkChild'`), mais Tk ignorait les frappes tant qu'aucun widget n'avait son focus *interne*. Il fallait un clic : `avant='' après=''` puis, après clic, `après='C'`. Les frappes arrivaient donc dans le bon processus et n'allaient nulle part ailleurs. Le témoin a été corrigé (focus interne rendu à la zone de texte à chaque activation). Le diagnostic refait donne `après='A'` dès le focus d'Atlas.
2. **Deuxième passage.** Tout était conforme. Une lecture intermédiaire affichait toutefois `cible=''` juste après R3, alors que le contenu final était complet. Le témoin réécrivait son fichier en le tronquant d'abord, et une lecture tombait parfois dans cet intervalle. **La même course aurait pu, en théorie, masquer du texte dans le témoin.** L'écriture a été rendue atomique (fichier temporaire puis `os.replace`).
3. **Troisième passage** (tableau ci-dessus). Les lectures sont cohérentes à chaque étape.

Le cas « focus accordé en apparence mais refusé par Windows » ne s'est pas produit sur ce poste : pywinauto a obtenu le premier plan à chaque fois. Il reste couvert par un test unitaire, et son absence en réel est consignée comme limite (B1B-R2).

---

## 7. Limites et risques identifiés

| ID | Description | Sévérité | Mitigation proposée |
|---|---|---|---|
| B1B-R1 | **Les titres sont comparés par sous-chaîne.** Une cible générique (`"a"`, `"e"`) correspond à presque toute fenêtre : `focus_window` en prend une au hasard, et la vérification du premier plan, qui utilise la même règle, la valide. | Moyen | Longueur minimale de titre, ou comparaison sur le processus ou le titre exact après focus (P1) |
| B1B-R2 | Le refus de focus par Windows n'a **pas pu être provoqué en réel** : pywinauto a réussi à chaque essai. Le garde-fou est prouvé par test unitaire seulement. | Faible | Rejeu dédié quand le cas se présentera (Atlas lancé depuis un processus sans focus) |
| B1B-R3 | Le premier plan est vérifié **une fois, avant** la frappe. Une frappe caractère par caractère de 2 000 caractères dure plus de 40 s ; si l'utilisateur change de fenêtre pendant ce temps, la suite du texte part ailleurs. | Moyen | Frappe par tronçons avec revérification, ou presse-papiers au-delà de quelques dizaines de caractères (P2) |
| B1B-R4 | Les **touches** de `window_hotkey` (L5, B1) ne sont validées que dans le validateur. Le planificateur horaire, les déclencheurs et les workflows peuvent encore envoyer `keys=["F","i",…]`. La cible, elle, est désormais exigée côté outil. | Faible (aucune tâche enregistrée n'utilise `window_hotkey`) | Déplacer `normalize_hotkey_keys` à côté des autres contrôles purs (P2) ; couvert de toute façon par l'analyse B (annexe B) |
| B1B-R5 | `browser_open` (Playwright, `tools/browser_controller.py`, **hors périmètre**) n'a pas de contrôle d'URL côté outil. Il est couvert par le validateur et par la confirmation forcée d'`execute_tool`, mais pas s'il est appelé par une tâche planifiée. Dans ce contexte, la confirmation reste sans réponse et l'action ne part pas. | Faible | Appliquer `check_url` dans `browser_open` (P2) |
| B1B-R6 | **Changement de comportement visible :** « réduis la fenêtre » ou « mets-la au premier plan » sans fenêtre nommée ni action précédente **sont désormais refusés**, au lieu de viser le premier plan. C'est voulu (même règle que L24), mais c'est une perte de commodité. | Faible | Si le besoin est réel : une formulation explicite (« la fenêtre active ») qui désignerait sciemment le premier plan, **hors Atlas Desktop** (P3, décision superviseur) |
| B1B-R7 | L'exemple du **prompt du planificateur** navigue vers `"first_result"`, qui n'est pas une URL. Ce type de plan est désormais refusé **en entier**, y compris l'étape de recherche (règle B1 : un plan avec une étape refusée est abandonné). « Cherche X et ouvre le premier résultat » échouera tant que le prompt n'est pas corrigé. | Moyen (fonctionnel) | Corriger l'exemple du prompt, ou faire résoudre `first_result` par le moteur (P1, fichier du planificateur) |
| B1B-R8 | `window_click` **sans cible** clique à un point d'écran valide dans la fenêtre qui s'y trouve, quelle qu'elle soit. C'est la nature d'un clic par coordonnées. | Faible | Accepté. À exiger une cible si l'usage le permet (P3) |
| B1B-R9 | `typewrite` ne sait pas taper certains caractères non ASCII : ils sont ignorés **sans erreur**, et Atlas annonce « Texte tapé (N caractères) ». Constaté dans le code, pas dans ce rejeu (texte ASCII). | Faible | Presse-papiers pour tout texte non ASCII (P2) |
| B1B-R10 | Un `\n` dans le texte envoie Entrée. Dans une messagerie, il **envoie le message**. Ce n'est pas un défaut de sécurité, puisque la cible est vérifiée, mais c'est un effet à connaître. | Faible | Documenter ; éventuellement une confirmation pour une cible de messagerie (P3) |
| B1B-R11 | Deux scripts manuels (`scripts/manual/diagnostic_v22.py`, `real_integration_v23_check.py`) appellent `window_type(target=None)` ou `window_hotkey` sans cible. Ils seront **refusés**. Non modifiés (hors périmètre) ; ils ne font pas partie de la suite. | Faible | Les mettre à jour s'ils resservent (P3) |
| B1B-R12 | `read_url` (lecture d'une page côté serveur) accepte toute URL `http` : `http://localhost:8001` (ChromaDB) ou `:11434` (Ollama) sont joignables par une URL issue d'un contenu externe. Requêtes GET seulement, et `reset` désactivé côté ChromaDB. Hors du périmètre BS4, qui listait les outils du navigateur. | Moyen | Interdire les hôtes locaux et privés dans `read_url` (P2) |
| B1B-R13 | **Constat hors code.** Le commit `0552532` (poussé sur `origin/sprint-b1`) a ajouté `assistant-bureau/data/` : `atlas_actions.jsonl`, `file_index.json`, `file_reorg_history.jsonl` et `habits.db`. Vérifié : ce sont des **traces de tests d'une machine macOS** (chemins `/private/var/folders/.../pytest-of-alx/`, workflow `mode_gaming`, table `process_habits` vide), **sans donnée sensible**. Le dossier `assistant-bureau/` n'existe plus depuis le sprint C, et `.gitignore` ne couvre que `data/` à la racine. | Faible | Retirer ces fichiers du suivi et ignorer `**/data/*.db` et les journaux (P2, hors périmètre de ce sprint, non traité) |
| B1B-R14 | Le rapport B1 comptait **7** actions « non protégées » ; le tableau en contenait **8**. Le brief B1-bis a repris ce 7. | Faible | Corrigé en annexe A |
| B1-R2 (reporté) | Un refus est toujours rendu comme une réponse `__conversation__` : le moteur ne distingue pas « refusé » de « conversation ». | Faible | Inchangé (moteur hors périmètre) |

---

## 8. Checklist de validation

Critères repris **exactement** du brief :

- [x] Tests rouges d'abord, sorties brutes consignées, aucun effet réel. Preuve en §5 (121 rouges, sorties brutes ; pyautogui piégé dans tous les tests).
- [x] `window_type` et `window_hotkey` : cible obligatoire, refus explicite sinon. Preuve en §5 (tests BS1) et en §6, R1.
- [x] Contrainte sur `text` définie, justifiée, appliquée. Voir §4.3, et les tests `test_bs1_texte_*` en §5.
- [x] Actions de fenêtre : titre vide refusé ; `position` de `window_snap` en liste blanche. Preuve en §5 (tests BS2, validateur et 5 outils × 2 titres vides).
- [x] `window_click` : bornes vérifiées, multi-écrans géré. Preuve en §5 (tests BS3, dont l'écran secondaire gauche ; vérification réelle de `_monitor_rects`).
- [x] Schémas d'URL en liste blanche. Preuve en §5 (tests BS4, validateur sous les deux états de l'extension, et `browser_bridge`).
- [x] BS5 : deux analyses livrées, **aucun code écrit** sur ces deux points. Voir annexe B ; `app_launcher.py`, `scheduler.py`, `trigger_engine.py` et `workflow_engine.py` sont intacts.
- [x] `python -m pytest tests/ -q` → code 0. Preuve en §5 (543 passés, 4 ignorés, `exit=0`).
- [x] **Rejeu réel de la frappe avec une autre application au premier plan : aucun texte parasite.** Preuve en §6 (témoin `''` après R1, R2 et R3).
- [x] Annexe A recalculée : combien d'actions protégées, partiellement, pas du tout. Voir annexe A (11 / 4 / 3).
- [x] Aucun appel LLM dans le chemin de validation. Voir §4.5 : listes constantes et comparaisons ; aucun import d'`ollama_client` dans les fichiers modifiés.
- [x] Aucune modification hors du périmètre. **Avec une exception autorisée :** `core/planner.py` (10 lignes). La question a été posée pendant le sprint et la réponse était « modification minimale autorisée ». Le reste est dans le périmètre : `core/validator.py`, `tools/window_controller.py`, `tools/browser_bridge.py`, `tests/`.

---

## 9. Recommandations pour le sprint suivant

Le brief annonce la chaîne vocale comme tranche suivante. Les points ci-dessous ne la bloquent pas ; ils sont classés pour décision.

### P1
1. **Corriger l'exemple `first_result` du prompt du planificateur** (B1B-R7). Il est aujourd'hui garanti d'échouer. C'est une correction de texte dans `core/planner.py`.
2. **Durcir la correspondance des titres** (B1B-R1) : longueur minimale, ou vérification post-focus sur le processus attendu. C'est le maillon le plus faible du garde-fou de frappe.
3. **Décider des deux analyses BS5** (annexe B). Recommandation : interdire `launch_app(path)` (coût quasi nul, aucun usage), et engager la validation des actions planifiées avant d'en ajouter de nouvelles.

### P2
4. Frappe par tronçons avec revérification du premier plan, ou presse-papiers au-delà d'un seuil (B1B-R3, B1B-R9).
5. Déplacer `normalize_hotkey_keys` parmi les contrôles purs, et l'appliquer aussi dans `window_hotkey` (B1B-R4).
6. `check_url` dans `browser_open` (B1B-R5), et interdiction des hôtes locaux et privés dans `read_url` (B1B-R12).
7. Nettoyer `assistant-bureau/data/` du dépôt et élargir `.gitignore` (B1B-R13).

### P3
8. Supprimer `_is_browser`, `_BROWSER_NAMES` et `_BROWSER_PROCESSES` (code mort, signalé depuis B1).
9. Mettre à jour les deux scripts manuels (B1B-R11). Documenter l'effet de `\n` dans les messageries (B1B-R10).
10. Distinguer un refus d'une conversation dans le moteur (B1-R2).

---

# Annexe A — Revue des paramètres d'action à effet de bord, recalculée après B1-bis

« Détecté ? » = un paramètre absurde produit par le LLM est-il refusé ? « Couche » = où : **V** validateur (requêtes et plans), **O** outil (tous les chemins, y compris planificateur horaire, déclencheurs et workflows).

| Action | Après B1 | Après B1-bis | Couche | Reste |
|---|---|---|---|---|
| `window_hotkey` | Partiel (touches) | **Oui** : touches en liste blanche + cible obligatoire, premier plan vérifié | V (touches), V+O (cible) | Touches non contrôlées côté O (B1B-R4) |
| `window_type` | Non | **Oui** : cible obligatoire, texte contraint, premier plan vérifié | V+O | Titres génériques (B1B-R1), durée de frappe (B1B-R3) |
| `ui_click_element` | Oui | Oui | V+O | — |
| `window_click` | Non | **Oui** : x/y entiers sur un écran réel, bouton et clics bornés, point dans la fenêtre cible | V+O | Sans cible : clic positionnel (B1B-R8) |
| `window_close` | Partiel (confirmation) | **Oui** : titre obligatoire + confirmation | V+O | Titres génériques (B1B-R1) |
| `window_focus` / `window_minimize` / `window_maximize` | Non | **Oui** : titre obligatoire, plus de repli sur le premier plan | V+O | Titres génériques (B1B-R1) |
| `window_snap` | Non | **Oui** : titre obligatoire, position en liste blanche | V+O | — |
| `launch_app` | Non (chemin) | Non (chemin) | — | Analyse B.1 |
| `kill_process` | Oui | Oui | moteur | — |
| `set_priority` | Non | Non | — | Hors brief |
| `run_powershell` | Oui | Oui | O | — |
| `system_config` | Partiel | Partiel | moteur | Hors brief |
| `browser_navigate` / `browser_open` / `browser_new_tab` | Non | **Oui** : http/https seulement | V (les trois) + O (`navigate`, `new_tab`) | `browser_open` sans contrôle côté O (B1B-R5) |
| `browser_ext_click` / `browser_ext_type` | Non | Non | — | Hors brief (P3 depuis B1) |
| `schedule_add` | Partiel | Partiel | — | Analyse B.2 |
| `trigger_add` | Partiel | Partiel | — | Analyse B.2 |
| `workflow_run` / `workflow_create` | Partiel | Partiel | — | Analyse B.2 |
| `redo_last_action` | Oui | Oui, et renforcé : le rejeu passe par les outils, qui appliquent maintenant leurs propres contrôles | O | — |

**Décompte :**

| | Protégées | Partiellement | Pas du tout |
|---|---|---|---|
| Après B1 (recompté) | 4 | 6 | **8** |
| **Après B1-bis** | **11** | **4** | **3** |

**Correction du rapport B1.** Il annonçait 4 / 6 / 7 pour 18 actions : la somme ne tombait pas juste. Le tableau B1 comptait bien huit lignes « Non » : `window_type`, `window_click`, `focus/minimize/maximize`, `window_snap`, `launch_app`, `set_priority`, les actions de navigation et `browser_ext_*`.

**Lecture d'ensemble.** Il reste trois actions non protégées. Deux étaient hors du brief (`set_priority`, `browser_ext_*`), et la troisième (`launch_app` avec `path`) fait l'objet de l'analyse B.1. Les quatre protections partielles relèvent toutes du même problème de fond : **ce qui est enregistré pour plus tard n'est pas validé** (analyse B.2), plus `system_config`, hors brief.

---

# Annexe B — BS5 : analyses sans implémentation

## B.1 `launch_app` avec un paramètre `path`

**Usage réel aujourd'hui : aucun.**
- Aucun appel interne ne passe `path` : ni `intent_engine`, ni l'orchestrateur, ni le classifieur, qui ne produit que `name`.
- Aucun des 5 workflows, 2 tâches planifiées et 1 déclencheur enregistrés ne l'utilise.
- Le paramètre n'arrive que par du contenu produit par le LLM, par trois voies :
  - une étape de plan `open` **sans cible**, pour laquelle le validateur transmet `intent.params` tels quels ;
  - une tâche ou un workflow créé avec des étapes LLM (analyse B.2) ;
  - l'ancien appel d'outils par le LLM, qui n'est plus branché.

**Ce qu'il permet.**
- Un chemin qui ne se termine pas par `.exe` est ouvert par `os.startfile(path)`. Les `.bat`, `.cmd`, `.vbs`, `.js`, `.hta`, `.lnk` et `.url` **s'exécutent**.
- Un `.exe` est lancé par `subprocess.Popen`.
- Un fichier téléchargé dans `Téléchargements` peut donc être exécuté sur la foi d'une sortie LLM.

**Options :**

| Option | Pour | Contre / pièges |
|---|---|---|
| 1. **Interdire `path`**, `name` seul, résolu dans l'index des applications | Coût quasi nul puisque inutilisé. Surface supprimée, pas réduite. Aucune règle subtile. | Une application portable absente de l'index devient inaccessible. Réponse : un fichier d'alias tenu **par l'utilisateur** (nom → chemin), jamais par le LLM. Piège : un `name` qui *contient* un chemin (`C:\…`, `..\`) doit être traité comme un `path`. |
| 2. Liste blanche d'emplacements (Program Files, System32…) + extensions (`.exe`, `.lnk`) | Garde les chemins explicites | Plusieurs pièges : `%LOCALAPPDATA%\Programs` est inscriptible par l'utilisateur, donc n'est pas une frontière de confiance. Il faut aussi gérer la normalisation (`..`, jonctions, noms courts 8.3, UNC `\\serveur\partage`, casse) et le délai entre contrôle et lancement. Une règle facile à contourner. |
| 3. Confirmation obligatoire dès qu'un `path` est fourni | Simple, garde la souplesse | L'utilisateur confirme un chemin qu'il ne peut pas évaluer, et la lassitude de confirmation s'installe. Dans une tâche planifiée, personne ne confirme : l'action est bloquée **silencieusement**. |

**Recommandation : option 1**, dans le validateur et dans l'outil. Si un besoin réel apparaît, un fichier d'alias géré par l'utilisateur. L'option 3 n'apporte rien sur un paramètre que personne n'utilise.

## B.2 Contenu des actions planifiées (`schedule_add`, `trigger_add`, `workflow_create`)

**État actuel.**
- Les `actions` ou `steps` sont **enregistrées telles quelles** (`data/schedules.json`, `data/triggers.json`, `data/workflows/*.yaml`) après **une** confirmation à la création.
- Elles sont ensuite exécutées par `main._execute_action` → `execute_tool`, **sans passer par le validateur**.
- Par le classifieur, le contenu vient de gabarits déterministes (`launch_app` d'applications connues, `notify`). Par le **planificateur**, c'est le contenu du LLM qui est conservé (`params.setdefault("actions", [])` garde ce qui existe).

**Ce qui protège déjà à l'exécution :**
- **les contrôles côté outil ajoutés par ce sprint** : fenêtres, clic, frappe, URL du pont ;
- la liste blanche PowerShell ;
- les confirmations forcées d'`execute_tool` (`kill_process`, arrêt et redémarrage, `browser_open`). En exécution planifiée, personne ne les confirme : l'action reste en attente et **ne s'exécute pas, sans que personne n'en soit averti**.

**Approche proposée :** valider récursivement au moment de l'enregistrement, **et de nouveau au chargement et à l'exécution.**
1. **Liste blanche d'actions planifiables.** Par exemple `launch_app` (par nom), `notify`, `get_diagnostics`, `maintenance_cleanup_temp`, `maintenance_gc`, `system_config:set_power_plan` et `workflow_run`. En sont **exclues** :
   - les actions interactives (`window_type`, `window_hotkey`, `window_click`, `ui_click_element`), car le premier plan à l'heure du déclenchement est inconnu ;
   - les actions qui exigent une confirmation, qui ne peut pas avoir lieu ;
   - les actions d'automatisation elles-mêmes (une tâche qui crée une tâche).
2. **Paramètres de chaque action** contrôlés par les **mêmes** fonctions pures que le validateur (`check_url`, `check_window_title`…), via une table outil → contrôle. Aujourd'hui le validateur associe des *intentions*, pas des *appels d'outil* : c'est la pièce à écrire.
3. **Récursion :** `workflow_run` dans un workflow impose la détection de cycles et une profondeur maximale.
4. **Revalidation au chargement et à l'exécution**, pas seulement à la création.

**Coût estimé :** ½ à 1 journée. Il comprend la table des contrôles par outil (une vingtaine d'outils) et les tests rouges. Il faut aussi décider du sort des 8 éléments enregistrés (5 workflows, 2 tâches planifiées, 1 déclencheur). **Deux workflows seraient refusés par les règles ci-dessus :**
- `mode_gaming`, qui contient `kill_process`, action à confirmation forcée ;
- `nettoyage_systeme`, qui contient `maintenance_empty_bin` (voir le piège 5).

Les six autres (`launch_app` par nom, `notify`, `get_diagnostics`, `set_power_plan`, maintenance non destructive) passeraient.

**Pièges :**
1. **Deux validateurs qui divergent.** Le validateur d'intentions et le validateur d'appels d'outils doivent partager les contrôles purs, pas les recopier. Ce sprint a commencé cette factorisation (`check_*`).
2. **Valider à la création ne suffit pas.** Les fichiers de `data/` se modifient à la main, et une ancienne version d'Atlas a pu enregistrer ce qu'une règle actuelle refuse. Il faut donc revalider au chargement.
3. **Que faire d'un élément devenu invalide ?** Le **désactiver et prévenir**, pas le supprimer : c'est la donnée de l'utilisateur.
4. **Confirmations silencieuses.** Une action qui exige une confirmation doit être refusée *à l'enregistrement*, pas découverte bloquée à 3 h du matin.
5. **Effets destructifs récurrents.** Le workflow `nettoyage_systeme` vide la corbeille, ce qui est une **suppression définitive**, à chaque exécution. Une action destructive planifiée mérite une décision explicite : exclusion, ou confirmation par tâche au moment de l'enregistrement.
6. **Amplification par les déclencheurs.** Un déclencheur se relance à chaque dépassement de seuil, cooldown mis à part. Une action anodine répétée toutes les 60 s ne l'est plus.
7. **Le vrai piège de fond.** Le brief le formule : ces défauts *s'installent*. La validation doit être pensée comme un invariant du stockage, pas comme une étape du parcours de création.

**Décision laissée au superviseur**, comme le demande le brief.

---

*Rapport Sprint B1-bis — CHAT6 (Claude Opus 5, Claude Code Windows), 19/09/2026.*
