# RAPPORT SPRINT B1-TER — La validation comme invariant du stockage
Date: 19/09/2026
Agent: Claude Opus 5 (CHAT6, Claude Code Windows)

> Brief : `docs/briefs/BRIEF_SPRINT_B1_TER.md`. Références : rapport B1-bis, §4.1 et annexe B.
> Branche **`sprint-b1-ter`**, issue de `main` @ `75047c3`. 2 commits (correctifs `9a87d9a` + ce rapport), **non poussés**.

---

## 1. Résumé exécutif

**Statut global : VALIDÉ.**

**Le chemin des automatisations ne contournait plus seulement le validateur : il ignorait la validation tout court.** Désormais, toute action enregistrée est contrôlée trois fois, à la création, au chargement et à l'exécution, par une table outil → contrôle unique. Seules six actions y sont autorisées, et tout le reste est refusé avec son motif.

**Anomalie A confirmée, et plus large que prévu.** L'exécution à blanc des 8 éléments enregistrés (§6.1) le montre : dans `mode_gaming`, ce ne sont pas une mais **deux étapes sur quatre** qui n'ont jamais tourné.
- `kill_process` n'a jamais fermé Teams.
- `system_config`, le plan « Haute performance », **n'a jamais été appliqué** : `system_config` exige toujours une confirmation.
- La notification finale « Mode Gaming activé ✅ » annonçait donc un résultat faux.

**Anomalie B confirmée** : `nettoyage_systeme` vidait réellement la corbeille à chaque exécution.

**Le silence est levé.** Tout blocage laisse trois traces :
- un avertissement dans le log applicatif ;
- une ligne `ERR_AUTOMATION_BLOCKED` dans le journal servi par `/api/logs/recent` ;
- une notification Windows, au plus une par élément toutes les 30 minutes.

**Rejeu réel, deux volets.**
- *Enregistrement :* cinq automatisations interdites sont refusées avec un message clair, sans rien écrire.
- *Édition à la main (critère décisif) :* un workflow créé par Atlas puis modifié à la main (ajout d'un `kill_process`) est **détecté au chargement, désactivé, signalé**, et son exécution est refusée avant la première étape. Le fichier n'est pas réécrit.

**Autres correctifs.**
- `launch_app` n'accepte plus de chemin, ni par `path`, ni par un nom en forme de chemin, ni par le repli sur l'index de fichiers. Ce dernier point est une découverte : un `.bat` de Téléchargements était lançable par son seul nom.
- **Perte de données évitée** : avant ce sprint, une seule entrée illisible dans `schedules.json` ou `triggers.json` vidait toute la liste chargée, et le prochain enregistrement **écrasait le fichier**.

**Tests.** **83 nouveaux**, vus rouges (73 échecs). Suite complète : **626 passés, 4 ignorés, code 0** (543 + 83). Trois tests existants encodaient l'anomalie A et ont été adaptés (§5).

**Annexe A, dernier calcul :** 17 protégées (dont 2 par inaccessibilité), 1 partiellement (`system_config`, hors des briefs), 0 sans protection.

**Tes éléments enregistrés : aucun modifié ni supprimé.** Empreintes MD5 identiques avant et après le sprint. Deux workflows sont désormais **désactivés en mémoire** (`mode_gaming`, `nettoyage_systeme`) en attendant ta décision (annexe B).

**Invariant 3 respecté**, périmètre respecté (§8).

**État à l'heure du rapport :**
- conteneurs `atlas_chromadb` et `atlas_searxng` démarrés ;
- Ollama 0.34.1 ;
- API Atlas arrêtée : le rejeu utilise les vrais moteurs, sans le serveur.

---

## 2. Objectifs vs réalisation

| Objectif (brief) | Résultat réel | Statut |
|---|---|---|
| Méthode : rouge d'abord, sorties brutes, aucun effet réel | 83 tests, **73 rouges** avant correction, sorties brutes en §5. Données dans un répertoire temporaire, rappels simulés, aucune notification réelle en test. | PASS |
| Deux anomalies actives à traiter en priorité | A : mesurée (§6.1), puis rendue visible (BT1) et impossible (BT2). B : `maintenance_empty_bin` exclu des automatisations. | PASS |
| BT1 — toute automatisation bloquée est journalisée **et** signalée | `report_automation_block` : log, journal d'actions (`/api/logs/recent`), notification Windows limitée. Couvre les refus au chargement et à l'exécution, et les confirmations impossibles. | PASS |
| BT2 — liste blanche des actions planifiables, justifiée, appliquée | 6 actions autorisées, 47 refusées par famille de motifs (§4.2). Un test vérifie la classification des 53 outils. | PASS |
| BT3 — table outil → contrôle, une seule définition par règle | `AUTOMATION_ACTION_CHECKS` dans `core/validator.py`. Elle réutilise `check_app_name`, et les moteurs, le validateur et `main` appellent la même fonction. | PASS |
| BT4 — cycles et profondeur maximale de `workflow_run` | Limite de 3 niveaux, justifiée en §4.2. Contrôle statique à la création et au chargement, garde à l'exécution par variable de contexte. | PASS |
| BT5 — validation à la création, au chargement, à l'exécution | Les trois moments, dans les trois moteurs et dans `main.execute_automation_action` | PASS |
| BT5 — élément invalide au chargement : désactivé et signalé, jamais supprimé | Désactivation **en mémoire** ; entrée réécrite telle que lue ; entrée illisible conservée ; fichier illisible jamais écrasé | PASS |
| BT6 — actions encore non protégées, dont `launch_app(path)` (option 1) | `path` refusé dans le validateur, l'outil et les automatisations ; nom en forme de chemin refusé ; repli sur l'index restreint. `set_priority` et `browser_ext_click/type` : inaccessibles par une intention (test) et exclus des automatisations. | PASS |
| BT7 — 8 éléments analysés, options pour les refusés, **aucun modifié** | Annexe B. Empreintes identiques avant et après. Un élément inerte signalé (« Job sans nom »). | PASS |
| BT8.1 — tests BT1 à BT6 verts après rouge | 83/83 | PASS |
| BT8.2 — `python -m pytest tests/ -q` → code 0, écarts expliqués | 626 passés, 4 ignorés, code 0 ; 3 tests adaptés, expliqués | PASS |
| BT8.3 — rejeu : refus à l'enregistrement, fichier édité à la main détecté au chargement | §6.2 et §6.3 | PASS |
| BT8.4 — annexe A recalculée | Annexe A | PASS |
| BT8.5 — rapport conforme | Ce document | PASS |

---

## 3. Architecture projet mise à jour

```
cortana-killer-atlas/
├── main.py                                  ← modifié (execute_automation_action, notification, ordre de chargement)
├── core/
│   ├── validator.py                         ← modifié (liste blanche, table outil → contrôle, cycles, signalement ; launch_app par nom)
│   ├── scheduler.py                         ← modifié (3 moments de validation, chargement entrée par entrée)
│   ├── trigger_engine.py                    ← modifié (idem)
│   └── workflow_engine.py                   ← modifié (idem + garde de récursion + pas d'écrasement)
├── tools/
│   └── app_launcher.py                      ← modifié (BT6 : nom seulement, index restreint)
├── tests/
│   ├── test_automation_safety_b1_ter.py     ← NOUVEAU B1-ter (83 tests)
│   ├── test_automation_v30.py               ← modifié (2 tests encodant l'anomalie A)
│   └── test_final_v50.py                    ← modifié (1 test encodant l'anomalie A)
└── docs/rapports/
    └── RAPPORT_SPRINT_B1_TER.md             ← NOUVEAU B1-ter
```

Diff du commit `9a87d9a` : 9 fichiers.

Scripts de rejeu, **non versionnés** (répertoire temporaire de session) : `b1ter_dryrun.py`, `b1ter_replay.py`. Aucun fichier de `data/` n'est versionné par ce sprint, et aucun n'a été modifié (§6).

---

## 4. Détail des implémentations

### 4.1 Le principe

Il y a une seule fonction de contrôle, `check_automation_actions(actions, resolve_workflow, stack)`, appelée à trois moments et par tous les chemins :

| Moment | Où | Effet d'un refus |
|---|---|---|
| **Création** | `Validator.resolve` (demande utilisateur ou plan LLM), `AtlasScheduler.add_job`, `TriggerEngine.add_trigger`, `WorkflowEngine.create_workflow` | Rien n'est enregistré ; message qui dit pourquoi |
| **Chargement** | `AtlasScheduler.start`, `TriggerEngine._load_triggers`, `WorkflowEngine.load_workflows` | Élément **désactivé en mémoire** (`invalid_reason`), signalé ; fichier non réécrit |
| **Exécution** | `_on_job_trigger` / `run_job_now`, `_fire_trigger`, `run_workflow`, puis `main.execute_automation_action` pour chaque action | Aucune étape exécutée ; signalé |

**Pourquoi le chargement ne réécrit jamais :** `invalid_reason` est un champ en mémoire, exclu de la sauvegarde (`to_storage_dict`). Quand un autre enregistrement réécrit le fichier, une tâche désactivée est réécrite **exactement comme elle a été lue**, et ses champs inconnus sont conservés.

### 4.2 `core/validator.py`

**Liste blanche (BT2).** Six actions sont autorisées :

| Action | Pourquoi elle a sa place dans une automatisation | Contrôle des paramètres (BT3) |
|---|---|---|
| `launch_app` | Usage principal réel (5 workflows sur 5, la tâche du lundi) | Seules les clés `name` et `wait` sont admises ; `path` interdit ; `check_app_name` (§4.6) ; `wait` booléen |
| `notify` | Pas d'effet de bord ; c'est le retour naturel d'une automatisation | Message de 1 à 500 caractères, titre et durée bornés |
| `get_diagnostics` | Lecture seule, utilisée par `demarrage_matin` | Aucun paramètre |
| `maintenance_cleanup_temp` | Fichiers temporaires de plus de N jours : effet borné, sans PowerShell arbitraire | `max_age_days` entier de 1 à 365 |
| `maintenance_gc` | Libération de mémoire de processus, sans effet visible | Aucun paramètre |
| `workflow_run` | Composition de routines | `workflow_id` non vide, puis contrôle récursif (BT4) |

Toute clé inattendue est refusée, pour qu'un paramètre ne puisse pas passer inaperçu. Les 47 autres outils sont refusés avec un **motif par famille** (`_AUTOMATION_EXCLUSIONS`) :

| Famille | Outils | Motif affiché |
|---|---|---|
| Interactive | `window_*` (type, hotkey, click, close, focus, minimize, maximize, snap), `ui_click_element`, `web_search_to_notepad`, `browser_*` qui agissent | « action interactive : la fenêtre au premier plan au moment du déclenchement est inconnue » |
| Confirmation forcée | `kill_process`, `run_powershell`, `system_config`, `browser_open` | « confirmation obligatoire, impossible sans utilisateur présent » |
| Automatisation | `schedule_add/remove/run_now`, `trigger_add/toggle`, `workflow_create` | « une automatisation ne crée, ne modifie ni ne relance d'autre automatisation » |
| Destructive | `maintenance_empty_bin` | « suppression définitive, rejouée à chaque exécution » |
| Imprévisible | `redo_last_action` | « rejoue une action qui dépend du moment où elle a eu lieu » |
| Non contrôlée | `set_priority` | « paramètres non contrôlés » |
| Sans destinataire | listes, lectures, `web_search`, `read_url`, `screen_read`… | « sans effet utile : le résultat n'est remis à personne » |
| Inconnue | tout autre nom | « outil inconnu » |

La dernière famille (« sans destinataire ») n'est pas dangereuse, mais une automatisation qui lit un résultat que personne ne reçoit n'a pas d'usage. Les refuser garde la liste minimale ; en autoriser une plus tard est une ligne dans la table.

**Récursion (BT4).** `_check_workflow_chain` descend dans chaque `workflow_run` avec la pile des workflows traversés. Un workflow déjà dans la pile forme un cycle ; au-delà de `MAX_WORKFLOW_DEPTH = 3`, la chaîne est trop profonde.

Pourquoi 3 :
- aucun workflow existant n'en imbrique un autre ;
- 2 niveaux couvrent le seul cas plausible (« routine du matin » qui lance « mode travail ») ;
- au-delà de trois niveaux, la chaîne n'est plus lisible pour l'utilisateur qui l'a acceptée, et une erreur s'y amplifie.

Une tâche → w2 → w3 → w4 passe ; w1 → w2 → w3 → w4 est refusé (testé).

**Signalement (BT1).** `report_automation_block(source, élément, motif)` :
1. `logger.warning` ;
2. une ligne JSONL au format du journal d'actions, avec `error_code: ERR_AUTOMATION_BLOCKED`, `result: blocked` et `pipeline_stage: automation:<source>`, dans le fichier que sert `/api/logs/recent` ;
3. une notification par `set_automation_notifier`, injectée par `main.py`, **au plus une par élément toutes les 30 minutes** (un déclencheur est réévalué toutes les 10 s).

En test, aucun notificateur n'est installé : pas de notification réelle.

**BT6 dans `resolve`.** Pour `open` → `launch_app` : `path` refusé, nom contrôlé par `check_app_name`.

**Création par le chemin intention.** Les verbes `schedule`, `trigger` et `workflow_create` contrôlent `actions` ou `steps` **avant** la confirmation. L'utilisateur n'a donc pas à confirmer une automatisation qui sera refusée.

### 4.3 `core/scheduler.py` et `core/trigger_engine.py`

- Nouveau champ `invalid_reason` (calculé, jamais écrit) et nouvelle méthode `to_storage_dict()`.
- `_load_*` travaille **entrée par entrée** :
  - une entrée illisible (champ manquant, identifiant absent ou en double) est signalée et gardée telle quelle (`_unparsed_entries`) ;
  - un fichier illisible (JSON invalide, pas une liste) pose `_storage_error` : **aucune écriture** jusqu'au prochain chargement, et `add_*` lève `ValueError`.
- `_save_*` réécrit les éléments désactivés depuis leur entrée d'origine, puis les entrées illisibles.
- `add_job` / `add_trigger` lèvent `ValueError` avec le motif, comme `add_trigger` le faisait déjà pour la limite de 20 déclencheurs.
- Exécution :
  - `_on_job_trigger` et `run_job_now` refusent un élément désactivé ou redevenu invalide ;
  - `_check_triggers` saute les déclencheurs désactivés, déjà signalés au chargement, sans les réévaluer ni les resignaler toutes les 10 s ;
  - `_fire_trigger` recontrôle avant d'agir.
- `ContextTrigger.from_dict` travaille sur une copie : il altérait l'entrée lue (`pop("condition")`), ce qui empêchait de la réécrire telle quelle.
- La validation des workflows lancés passe par `get_workflow_engine().steps_for_validation`, qui renvoie `None` pour un workflow introuvable ou désactivé.

### 4.4 `core/workflow_engine.py`

- `load_workflows` fonctionne en deux passes : lecture de tous les fichiers (un fichier illisible est signalé et laissé intact), puis validation de chacun avec résolution des sous-workflows.
- `list_workflows` expose `disabled_reason` : l'utilisateur peut voir pourquoi un workflow ne tourne plus.
- `run_workflow` suit trois étapes :
  1. garde d'exécution par `contextvars` (`_RUNNING`) : un `workflow_run` imbriqué repasse par `execute_tool` puis revient ici, dans la même tâche asyncio, donc un cycle ou une profondeur excessive est détecté même si le contenu a changé après le chargement ;
  2. revalidation complète ;
  3. seulement ensuite, `_run_steps`, qui reprend la boucle d'origine inchangée.
- `create_workflow` :
  - contrôle les étapes, **y compris un workflow qui se lancerait lui-même**, le nouveau workflow étant résolu dans sa propre pile ;
  - n'écrase plus un fichier `.yaml` existant. Avant, un fichier illisible, donc non chargé, était écrasé par une création du même nom.
- `steps_for_validation` charge les workflows à la demande s'ils ne l'ont pas encore été.

### 4.5 `main.py`

- `execute_automation_action(action)` : fonction de module, testable sans démarrer l'application. Elle remplace le `_execute_action` interne.
  - Elle recontrôle l'action, puis appelle `execute_tool`.
  - Si `execute_tool` répond `confirmation_required`, **la confirmation orpheline est retirée** (`resolve_pending`), et l'action devient un blocage signalé, au lieu de rester en attente pour toujours. C'est la correction directe de l'anomalie A pour tout cas que la liste blanche n'aurait pas prévu.
- Le `lifespan` installe le notificateur, qui programme `tools.notifier.notify` dans la boucle asyncio.
- **Les workflows sont chargés avant le planificateur et les déclencheurs** : une tâche qui lance un workflow est contrôlée contre la liste des workflows. Sans cela, elle aurait été jugée « workflow introuvable ».

### 4.6 `tools/app_launcher.py` (BT6)

- `check_app_name(name)` : chaîne de 1 à 80 caractères, sans `\`, `/`, `:` ni `..`, sans caractère de contrôle.
- `launch_app` refuse tout `path` non vide et tout nom invalide, **avant** la résolution. Le paramètre reste dans la signature parce que `TOOL_HANDLERS` (`core/intent_engine.py`, hors périmètre) le transmet.

**Évaluation de la suppression pure de `path`, demandée par le brief.** Fonctionnellement, c'est fait : plus aucun chemin n'est accepté nulle part. Retirer aussi le paramètre de la signature obligerait à modifier `core/intent_engine.py`, et la seule fonction qui l'utilise encore, `launch_chained`, n'est appelée nulle part (code mort, signalé).

**Découverte : le nom menait aussi à un chemin arbitraire.** Quand un nom n'est pas trouvé, `launch_app` se rabat sur l'index passif des fichiers, dont les racines sont **Bureau, Documents et Téléchargements**. Ce repli acceptait `.exe`, `.bat` et `.cmd` par correspondance partielle ou approximative : « lance setup » pouvait exécuter un `setup_tool.bat` téléchargé. Le repli n'admet plus que les raccourcis (`.lnk`, `.url`), jamais dans Téléchargements. La contrepartie est testée : un `.lnk` du Bureau reste lançable par son nom.

---

## 5. Résultats des tests

### État rouge, avant toute correction

```
python -m pytest tests/test_automation_safety_b1_ter.py -q -p no:cacheprovider -rfps --tb=no
73 failed, 10 passed in 3.22s
```

Sorties brutes (une par test ; les variantes paramétrées sont du même type) :

```
test_bt2_tache_planifiee_interdite_refusee_a_la_creation[window_type-...] - Failed: DID NOT RAISE <class 'ValueError'>
test_bt2_tache_planifiee_interdite_refusee_a_la_creation[launch_app-{'path': 'C:\\Users\\alexis\\Downloads\\...] - Failed: DID NOT RAISE <class 'ValueError'>
test_bt2_declencheur_interdit_refuse_a_la_creation[window_type-...] - Failed: DID NOT RAISE <class 'ValueError'>
test_bt2_workflow_interdit_refuse_a_la_creation[window_type-...] - AssertionError: workflow avec window_type créé : {'success': True, 'message': "Workflow 'Essai' créé.", 'workflow_id': 'essai', 'file': 'essai.yaml'}
test_bt3_action_malformee_refusee['launch_app'] - Failed: DID NOT RAISE <class 'ValueError'>
test_bt2_liste_blanche_exacte_sur_tous_les_outils - AssertionError: acceptés en trop : ['browser_bridge_status', 'browser_click', 'browser_close', 'browser_current_url', 'browser_ext_click', ... (tous)
test_bt2_demande_utilisateur_de_planifier_une_action_interdite_refusee - AssertionError: schedule_add avec kill_process accepté : {'name': 'fermer teams', 'actions': [{'action': 'kill_process', 'params': {'name': 'teams.exe'}}], ...}
test_bt4_workflow_run_vers_un_workflow_existant_accepte_inconnu_refuse - Failed: DID NOT RAISE <class 'ValueError'>
test_bt4_workflow_qui_sappelle_lui_meme_refuse_a_la_creation - AssertionError: workflow auto-récursif créé : {'success': True, ... 'workflow_id': 'boucle', 'file': 'boucle.yaml'}
test_bt4_cycle_entre_fichiers_detecte_au_chargement_et_jamais_execute - AssertionError: 30 étape(s) exécutée(s) malgré le cycle
test_bt4_profondeur_maximale - AssertionError: w1 (4 niveaux) accepté
test_bt4_garde_a_lexecution_meme_si_le_cycle_apparait_apres_le_chargement - AssertionError: 30 relance(s) exécutée(s)
test_bt5_tache_editee_a_la_main_detectee_au_chargement - AssertionError: tâche invalide enregistrée dans APScheduler
test_bt5_entree_malformee_ne_fait_pas_perdre_les_autres - AssertionError: tâche valide perdue au chargement
test_bt5_fichier_illisible_jamais_ecrase - Failed: DID NOT RAISE <class 'ValueError'>
test_bt5_declencheur_edite_a_la_main_jamais_declenche - AssertionError: déclencheur invalide exécuté : [{'action': 'window_type', 'params': {'text': 'x', 'target': 'bloc-notes'}}]
test_bt5_workflow_edite_a_la_main_desactive_et_signale - AssertionError: étapes exécutées : [{'action': 'kill_process', 'params': {'name': 'teams.exe'}}, {'action': 'launch_app', 'params': {'name': 'steam'}}]
test_bt5_creation_necrase_pas_un_fichier_existant_non_charge - AssertionError: fichier existant écrasé
test_bt5_tache_modifiee_en_memoire_refusee_a_lexecution - AssertionError: actions exécutées : [{'action': 'notify', ...}, {'action': 'kill_process', 'params': {'name': 'teams.exe'}}]
test_bt1_point_dexecution_commun_bloque_et_signale - AssertionError: main n'expose aucun contrôle à l'exécution : _execute_action appelle execute_tool directement
test_bt1_confirmation_impossible_devient_un_blocage_signale - AssertionError: main._execute_action ne détecte pas les confirmations impossibles
test_bt1_notifications_limitees_pour_un_meme_element - AssertionError: chaque blocage doit être journalisé
test_bt6_outil_launch_app_refuse_un_chemin[kwargs0] - AssertionError: lancé : ['C:\\Users\\alexis\\Downloads\\setup.bat']
test_bt6_outil_launch_app_refuse_un_chemin[kwargs1] - AssertionError: lancé : [['C:\\Windows\\System32\\cmd.exe']]
test_bt6_outil_launch_app_refuse_un_chemin[kwargs2] - AssertionError: lancé : [['where', 'C:\\Users\\alexis\\Downloads\\setup.bat']]
test_bt6_nom_ne_resout_pas_vers_un_script_telecharge - AssertionError: fichier de l'index exécuté : ['...\\Downloads\\setup_tool.bat', [...'\\Downloads\\outil.exe']]
test_bt6_validateur_refuse_path_dans_une_demande - AssertionError: path transmis : {'path': 'C:\\Users\\alexis\\Downloads\\setup.bat'}
test_bt7_classement_des_workflows_modeles - AssertionError: assert 'kill_process' in ((None or ''))
```

Le « 30 » des tests de cycle est la borne de sécurité de ces tests. **Sans elle, le cycle `wf_a → wf_b → wf_a` s'exécutait sans fin** : le défaut était une récursion infinie.

**Les 10 tests verts dès le départ :**
- 7 contreparties d'acceptation (actions autorisées) ;
- le raccourci `.lnk` du Bureau ;
- l'inaccessibilité de `set_priority` et `browser_ext_*` par une intention (constat structurel) ;
- `test_bt5_tache_invalide_conservee_telle_quelle_apres_un_ajout`, qui passait parce que rien n'était validé. Il garantit que la quarantaine n'altère pas l'entrée.

**Deux rectifications de mes propres tests, à signaler :**
1. `test_bt4_profondeur_maximale` échouait d'abord sur `ImportError: cannot import name 'MAX_WORKFLOW_DEPTH'`, un rouge qui ne montrait pas le défaut (leçon B1). Réordonné, il échoue sur *« w1 (4 niveaux) accepté »* ; la constante est vérifiée en dernier.
2. `test_bt5_entree_malformee_ne_fait_pas_perdre_les_autres` exigeait l'égalité stricte de l'entrée valide après réécriture. Or le planificateur y met à jour `next_run`, comme il l'a toujours fait. Le test cherche une **suppression** : il compare désormais l'identifiant et les champs définis par l'utilisateur.

Les deux tests qui visent `main.execute_automation_action` remplacent `execute_tool` et `collect_context` à leur source (`core.intent_engine`, `core.context_monitor`), parce que `main` les importe à l'appel.

### Après correction

```
python -m pytest tests/test_automation_safety_b1_ter.py -q -p no:cacheprovider --tb=short
83 passed in 1.64s
```

### Tests existants qui encodaient l'anomalie A (3, adaptés)

| Test | Ce qu'il affirmait | Réalité | Adaptation |
|---|---|---|---|
| `test_automation_v30::test_11_workflow_run_mode_gaming` | Avec un rappel simulé qui répond « succès », `kill_process` et `system_config` de `mode_gaming` « s'exécutent » | En réel, ces deux étapes demandent une confirmation que personne ne donne : **elles ne se sont jamais exécutées** (§6.1). Le test protégeait le défaut. | Renommé `test_11_workflow_run_execute_les_etapes_dans_lordre`. L'ordre est vérifié sur `demarrage_matin` (liste exacte des appels). `mode_gaming` doit être refusé sans aucun appel. |
| `test_automation_v30::test_13_trigger_intouchable_skip` | Enregistrait un déclencheur `kill_process` pour vérifier la protection « intouchable » | `kill_process` n'est plus admis dans un déclencheur | Vérifie d'abord le **refus** d'un déclencheur `kill_process`, puis la protection « intouchable » sur une action autorisée qui désigne le même processus |
| `test_final_v50::test_10_workflow_mode_gaming_criteria_success` | Critères de réussite de `mode_gaming`, dont « power_plan_applique », avec étapes simulées réussies | Le plan d'alimentation n'a jamais été appliqué en réel | Renommé `test_10_workflow_criteria_success`. Critères vérifiés sur `demarrage_matin` ; `mode_gaming` doit être refusé. |

### Suite complète

```
python -m pytest tests/ -q
626 passed, 4 skipped in 88.03s (0:01:28)
exit=0
```

La même suite a aussi été passée avec l'export JUnit et la couverture (`--junitxml … --cov …`) : 626 passés, 4 ignorés en 92,81 s, code 0. C'est cette exécution qui fournit le détail par fichier ci-dessous.

**Écart 543 → 626, expliqué :** +83 tests de `test_automation_safety_b1_ter.py`. Aucun test supprimé ; trois adaptés (ci-dessus). Les 4 ignorés sont ceux, volontaires, de B1-bis (onglet vide légitime).

**Non-régression, suite par suite** (export JUnit de la même exécution) :

| Suite | Résultat |
|---|---|
| `test_action_safety_b1.py` | 20 passés |
| `test_action_safety_b1_bis.py` | 146 passés, 4 ignorés |
| `test_app_resolver_v51.py` | 5 passés |
| `test_automation_safety_b1_ter.py` | 83 passés |
| `test_automation_v30.py` | 15 passés (2 adaptés) |
| `test_backup_memory_guard.py` | 46 passés |
| `test_chroma_integration.py` | 5 passés |
| `test_compose_config.py` | 6 passés |
| `test_core_conversational.py` | 15 passés |
| `test_file_indexer_v51.py` | 2 passés |
| `test_file_organizer_v51.py` | 3 passés |
| `test_final_v50.py` | 10 passés (1 adapté) |
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
| **Total, 29 fichiers** | **626 passés, 4 ignorés, 0 échec** |

### Couverture (après ; non exigée par le brief)

Suite complète avec `--cov` sur les modules modifiés :

| Module | Couverture |
|---|---|
| `core/scheduler.py` | 87 % (186/215) |
| `core/workflow_engine.py` | 84 % (203/243) |
| `core/validator.py` | 76 % (349/460) ; 70 % à la fin de B1-bis |
| `core/trigger_engine.py` | 74 % (195/263) |
| `tools/app_launcher.py` | 58 % (153/263) |

Je n'ai pas relevé de mesure « avant » pour les moteurs d'automatisation : le brief ne demandait pas de couverture pour ce sprint. Ces chiffres ne sont donc pas comparés.

---

## 6. Comportement observé en scénarios réels

### 6.1 Constat avant correction : exécution à blanc des 8 éléments enregistrés (BT7, anomalie A)

Chaque action des vrais fichiers de `data/` est passée par le **vrai** `execute_tool` : routage et confirmations forcées réels. Les 53 outils étaient remplacés par des enregistreurs, donc **aucune action réelle**. Mémoire longue et journal neutralisés, fichiers lus sans être écrits (empreintes vérifiées).

```
  [mode_gaming] 4 étape(s)
    Fermer apps inutiles        kill_process             -> BLOQUÉ (confirmation jamais donnée)  Fermer 'teams.exe' est une action irréversible.
    Haute performance           system_config            -> BLOQUÉ (confirmation jamais donnée)  Modification système : set_power_plan
    Lancer Steam                launch_app               -> EXÉCUTÉ
    Notification                notify                   -> EXÉCUTÉ  (géré par le moteur de workflow)
  [nettoyage_systeme] 4 étape(s)
    Vider la corbeille          maintenance_empty_bin    -> EXÉCUTÉ
  ...
  [d2c2f123] 'Job sans nom' enabled=True interval — 0 action(s)
    (aucune action : se déclenche sans rien faire)
```

Les autres éléments (`demarrage_matin`, `mode_travail`, `workflow_discord_spotify`, la tâche Steam du lundi, le déclencheur GPU) ont toutes leurs étapes exécutées. Détail en annexe B.

### 6.2 Rejeu, volet 1 : enregistrer une automatisation interdite

Sur les vrais moteurs et les vrais fichiers, **par le chemin réel** : la demande utilisateur passe par le validateur, puis `execute_tool` appelle `schedule_add`, `trigger_add` ou `workflow_create`, ce qui se produit après confirmation.

**Avant le rejeu :**
- tes 7 fichiers sont sauvegardés et leurs empreintes relevées ;
- la mémoire longue est neutralisée.

| ID | Tentative | Résultat attendu | Résultat observé | Statut |
|---|---|---|---|---|
| R1 | Demande « ferme Teams tous les soirs à 18h » (plan : `schedule` + `kill_process`) | Refus avant confirmation | `rejected=True` : *« Action refusée : automatisation refusée (action 1 — action 'kill_process' non autorisée dans une automatisation (confirmation obligatoire, impossible sans utilisateur présent)). »* | PASS |
| R2 | `schedule_add` avec `window_type` | Refus, rien écrit | `status='error'` : *« Tâche 'frappe auto' refusée : action 1 — action 'window_type' non autorisée dans une automatisation (action interactive : la fenêtre au premier plan au moment du déclenchement est inconnue) »* | PASS |
| R3 | `trigger_add` avec `run_powershell` | Refus, rien écrit | *« Déclencheur 'si CPU > 90, PowerShell' refusé : … 'run_powershell' … (confirmation obligatoire, impossible sans utilisateur présent) »* | PASS |
| R4 | `workflow_create` avec `maintenance_empty_bin` | Refus, aucun fichier | *« Workflow 'vider la corbeille' refusé : … (suppression définitive, rejouée à chaque exécution). »* | PASS |
| R5 | `workflow_create` avec `launch_app(path=…\setup.bat)` | Refus, aucun fichier | *« Workflow 'lancer un script' refusé : action 1 — 'launch_app' : paramètre 'path' interdit : seul un nom d'application est accepté. »* | PASS |
| R6 | `workflow_create` valide (une notification) | Créé | `data/workflows/rejeu_b1ter.yaml` créé par Atlas | PASS |

Après R1 à R6 : `md5sum -c` sur tes 7 fichiers donne **7 × OK**.

### 6.3 Rejeu, volet 2 (critère décisif) : fichier modifié à la main, détecté au chargement

1. Le fichier créé en R6, `data/workflows/rejeu_b1ter.yaml`, a été **modifié à la main** dans un éditeur de texte : une étape ajoutée en tête.
   ```yaml
   - name: Fermer Teams (ajout manuel)
     action: kill_process
     params:
       name: teams.exe
   ```
2. Un nouveau chargement a été fait **dans l'ordre du démarrage d'Atlas** (workflows, puis tâches, puis déclencheurs), avec le rappel `main.execute_automation_action` et **la vraie notification Windows** (même code que `main._automation_toast`). La boucle des déclencheurs n'était pas démarrée, pour qu'aucun déclenchement ne réécrive `triggers.json`.

| ID | Étape | Résultat attendu | Résultat observé | Statut |
|---|---|---|---|---|
| R7 | Chargement | Workflow édité détecté, désactivé, signalé | `workflow rejeu_b1ter DÉSACTIVÉ : action 1 — action 'kill_process' non autorisée dans une automatisation (…)` ; notification Windows réelle : `🔔 Notification : Atlas — automatisation bloquée — workflow « rejeu b1ter » : …` | PASS |
| R8 | Même chargement, tes éléments | Les deux workflows refusés sont signalés ; les autres restent actifs | `mode_gaming` et `nettoyage_systeme` **désactivés et notifiés** ; `demarrage_matin`, `mode_travail`, `workflow_discord_spotify`, les 2 tâches et le déclencheur : actifs | PASS |
| R9 | Lancement du workflow édité | Refus avant la première étape | `status='error'` : *« Workflow 'rejeu b1ter' désactivé : action 1 — action 'kill_process' … »* ; aucune étape exécutée | PASS |
| R10 | Journal servi par `/api/logs/recent` | Blocages visibles | 4 lignes `ERR_AUTOMATION_BLOCKED` : Mode Gaming, Nettoyage Système et rejeu b1ter au chargement, puis rejeu b1ter à l'exécution. Pour cette dernière, **pas de seconde notification** (limitation à une par 30 min). | PASS |
| R11 | Fichiers | Rien réécrit | Empreintes identiques pour le fichier édité **et** pour tes 7 fichiers | PASS |

`data/workflows/rejeu_b1ter.yaml`, créé par le rejeu et non par toi, a ensuite été supprimé. `data/workflows` contient de nouveau exactement tes 5 fichiers.

Il reste dans le vrai `data/atlas_actions.jsonl` les lignes de signalement ajoutées par le rejeu : 2 au premier chargement, 4 au second. Ce sont de vrais signalements, et je les ai laissées.

---

## 7. Limites et risques identifiés

| ID | Description | Sévérité | Mitigation proposée |
|---|---|---|---|
| B1T-R1 | **Les workflows lancés à la demande sont aussi refusés.** « Active le mode gaming », dit par l'utilisateur présent, est désormais refusé, parce qu'un workflow est un élément enregistré et que la règle ne distingue pas lancement automatique et lancement demandé. Conséquence directe du brief, qui prévoit le refus de ces deux workflows. **`mode_gaming` et `nettoyage_systeme` ne fonctionnent plus tant qu'Alexis n'a pas tranché** (annexe B). | Moyen (fonctionnel) | Décision : options en annexe B. Une piste de fond : un mode « lancé par l'utilisateur » où les confirmations sont vraiment présentées une à une (moteur hors périmètre) |
| B1T-R2 | **Le `lifespan` modifié n'a pas été exécuté par un vrai démarrage d'Atlas.** Les tests importent `main` sans le lancer, et le rejeu reproduit le branchement au lieu de passer par le serveur. Je n'ai pas démarré l'API pour ne pas toucher à la mémoire ni aux fichiers de l'utilisateur hors rejeu. Relecture du diff faite (§4.5). | Moyen | Au prochain lancement d'Atlas : deux notifications attendues (Mode Gaming, Nettoyage Système), et `/api/logs/recent` doit les montrer. Si rien n'apparaît, c'est ce branchement. |
| B1T-R3 | Un refus à la création par `schedule_add` ou `trigger_add` est une `ValueError`, qu'`execute_tool` (hors périmètre) journalise **avec une trace de pile**, comme un plantage. Le message utilisateur est clair ; le log est trompeur. | Faible | Faire retourner `{"success": False}` par `_run_schedule_add` / `_run_trigger_add` (`core/intent_engine.py`, P2) |
| B1T-R4 | Les conditions `confirm_before_run` présentes dans les 5 workflows ne sont **appliquées par aucun code**. Le YAML promet une confirmation qui n'a jamais lieu : autre écart silencieux, du même ordre que l'anomalie A. | Moyen | Appliquer la condition, ou la retirer du format (P1, décision) |
| B1T-R5 | Seules les **actions** sont validées. Un `trigger_config` de tâche invalide fait échouer l'enregistrement dans APScheduler avec un simple `logger.error` (comportement antérieur, non signalé à l'utilisateur). Une condition de déclencheur inconnue (métrique, opérateur) est ignorée silencieusement. | Faible | Étendre `report_automation_block` à ces deux cas (P2) |
| B1T-R6 | Une tâche **sans aucune action** est acceptée (« Job sans nom » : toutes les 24 h, rien). Aucun danger, mais c'est un élément inerte que l'utilisateur ne voit pas. | Faible | Refuser une liste d'actions vide à la création (P2 ; deux tests v30 en créent volontairement) |
| B1T-R7 | La limitation des notifications est en mémoire : **à chaque démarrage d'Atlas**, chaque élément désactivé produit une notification (deux aujourd'hui), tant qu'Alexis n'a pas décidé. C'est voulu, puisqu'un élément désactivé doit rester visible, mais c'est répétitif. | Faible | Accepté ; disparaît avec la décision de l'annexe B |
| B1T-R8 | Pas d'endpoint d'état dédié (« quelles automatisations sont désactivées ? ») : `api/routes.py` est hors périmètre. On le voit par `/api/logs/recent`, par `list_workflows` (`disabled_reason`) et dans la liste des tâches (`invalid_reason`). | Faible | `GET /api/automation/status` (P2) |
| B1T-R9 | `set_priority` et `browser_ext_click/type` sont protégés **par inaccessibilité** : aucune intention ne les produit (test), et les automatisations les refusent. Leurs paramètres restent non contrôlés si un chemin futur les atteint. | Faible | Contrôler leurs paramètres le jour où un chemin les expose (P3) |
| B1T-R10 | `launch_chained` (`tools/app_launcher.py`) est du **code mort** qui passe `path`. Il est désormais refusé par `launch_app`. | Faible | Supprimer (P3) |
| B1T-R11 | Le fichier réel `data/file_index.json` contient deux entrées de tests (chemins `pytest-of-alexis`) datées du 16/09/2026 19:16, **antérieures à l'isolation des tests** (B-minimal). L'index n'a pas été reconstruit depuis. Sans conséquence ; à noter pour ne pas y chercher de fuite actuelle. | Faible | Se corrige à la prochaine indexation |
| B1T-R12 | Le seuil `MAX_WORKFLOW_DEPTH = 3` et la liste blanche sont des choix, justifiés en §4.2 mais pas validés par un usage réel. | Faible | À réviser si un usage légitime est refusé : c'est une ligne dans la table |

---

## 8. Checklist de validation

Critères repris **exactement** du brief :

- [x] Tests rouges d'abord, sorties brutes, aucun effet réel. Preuve en §5 (73 rouges ; données temporaires, rappels simulés, aucun notificateur en test).
- [x] Toute automatisation bloquée est journalisée **et signalée** à l'utilisateur. Preuve en §5 (tests BT1) et §6.3, R7 et R10 : notification réelle et journal `/api/logs/recent`.
- [x] Liste blanche des actions planifiables établie, justifiée, appliquée. Voir §4.2 et `test_bt2_liste_blanche_exacte_sur_tous_les_outils`.
- [x] Table outil → contrôle écrite, une seule définition par règle. Voir §4.2, `AUTOMATION_ACTION_CHECKS`, appelée par le validateur, les trois moteurs et `main`.
- [x] Cycles et profondeur maximale traités pour `workflow_run`. Preuve en §5 (tests BT4, dont cycle entre fichiers et cycle apparu après chargement).
- [x] Validation effective **à la création, au chargement et à l'exécution**. Voir §4.1 et les tests BT5 pour chacun des trois moments.
- [x] Élément invalide au chargement : désactivé et signalé, jamais supprimé. Preuve en §5 (`test_bt5_*`) et §6.3, R7 et R11.
- [x] `launch_app(path)` traité selon l'option 1. Voir §4.6 : refusé dans le validateur, l'outil et les automatisations, plus la fermeture du repli sur l'index.
- [x] Les 8 éléments enregistrés analysés ; **aucun modifié ni supprimé**. Voir annexe B ; empreintes identiques en §6.2 et §6.3.
- [x] `python -m pytest tests/ -q` → code 0. Preuve en §5 (626 passés, 4 ignorés, `exit=0`).
- [x] **Rejeu : action interdite refusée à l'enregistrement, et fichier édité à la main détecté au chargement.** Voir §6.2 (R1 à R5) et §6.3 (R7 à R11).
- [x] Annexe A recalculée. Voir annexe A.
- [x] Aucun appel LLM dans un chemin de validation. Les fonctions ajoutées ne sont que tables constantes et comparaisons ; aucun import d'`ollama_client` dans les fichiers modifiés.

Périmètre : les 6 fichiers de code modifiés sont tous dans la liste autorisée (`core/validator.py`, `main.py`, `core/workflow_engine.py`, `core/scheduler.py`, `core/trigger_engine.py`, `tools/app_launcher.py`), plus `tests/`.

Deux modifications de `main.py` dépassent le seul corps de `_execute_action` ; les deux font partie du branchement de ce chemin :
- l'installation du notificateur ;
- l'ordre de chargement des moteurs.

---

## 9. Recommandations pour le sprint suivant

La famille sécurité est close ; ces points ne bloquent pas la chaîne vocale.

### P1
1. **Décider du sort de `mode_gaming` et `nettoyage_systeme`** (annexe B). Tant que ce n'est pas fait, ils sont désactivés et notifiés à chaque démarrage.
2. **`confirm_before_run` : l'appliquer ou le retirer** (B1T-R4). C'est le même genre d'écart que l'anomalie A : une promesse que le code ne tient pas.
3. **Démarrer Atlas une fois et vérifier les deux notifications** (B1T-R2).

### P2
4. Refus à la création sans trace de pile (B1T-R3, `core/intent_engine.py`).
5. Signaler aussi les `trigger_config` et conditions de déclencheur invalides (B1T-R5), et refuser les tâches sans action (B1T-R6).
6. `GET /api/automation/status` (B1T-R8).
7. Reports de B1-bis toujours ouverts :
   - titres génériques ;
   - frappe longue ;
   - `normalize_hotkey_keys` côté outil ;
   - `check_url` dans `browser_open` ;
   - hôtes locaux dans `read_url` ;
   - nettoyage de `assistant-bureau/data/`.

### P3
8. Supprimer `launch_chained` et le code mort du validateur (`_is_browser`, `_BROWSER_*`).
9. Contrôles de paramètres pour `set_priority` et `browser_ext_*` si un chemin les expose un jour.

---

# Annexe A — Revue des paramètres d'action à effet de bord, dernier calcul

« Détecté ? » = un paramètre absurde produit par le LLM est-il refusé, sur **tous** les chemins vivants (requête, plan, automatisations) ?

| Action | Après B1-bis | Après B1-ter | Par quoi |
|---|---|---|---|
| `window_hotkey` | Oui | Oui | Validateur + outil ; exclu des automatisations |
| `window_type` | Oui | Oui | Idem |
| `ui_click_element` | Oui | Oui | Idem |
| `window_click` | Oui | Oui | Idem |
| `window_close` | Oui | Oui | Idem |
| `window_focus` / `minimize` / `maximize` | Oui | Oui | Idem |
| `window_snap` | Oui | Oui | Idem |
| `launch_app` | **Non** (chemin) | **Oui** | `path` et noms en forme de chemin refusés (validateur, outil, automatisations) ; repli sur l'index restreint aux raccourcis hors Téléchargements |
| `kill_process` | Oui | Oui | Confirmation forcée ; exclu des automatisations |
| `set_priority` | **Non** | **Oui (inaccessible)** | Aucune intention ne le produit (test) ; exclu des automatisations. Paramètres toujours non contrôlés (B1T-R9) |
| `run_powershell` | Oui | Oui | Liste blanche + confirmation ; exclu des automatisations |
| `system_config` | Partiel | Partiel | Confirmation toujours demandée ; paramètres non contrôlés ; exclu des automatisations. Hors des briefs B1 à B1-ter. |
| `browser_navigate` / `browser_open` / `browser_new_tab` | Oui | Oui | http(s) seulement ; exclus des automatisations |
| `browser_ext_click` / `browser_ext_type` | **Non** | **Oui (inaccessible)** | Aucune intention ne les produit (test) ; exclus des automatisations (B1T-R9) |
| `schedule_add` | Partiel | **Oui** | Liste blanche + table de contrôle, à la création, au chargement et à l'exécution |
| `trigger_add` | Partiel | **Oui** | Idem |
| `workflow_run` / `workflow_create` | Partiel | **Oui** | Idem + cycles et profondeur |
| `redo_last_action` | Oui | Oui | Rejoue par les outils, qui appliquent leurs contrôles ; exclu des automatisations |

**Décompte :**

| | Protégées | Partiellement | Pas du tout |
|---|---|---|---|
| Rapport B1 (recompté en B1-bis) | 4 | 6 | 8 |
| Après B1-bis | 11 | 4 | 3 |
| **Après B1-ter** | **17** (dont 2 par inaccessibilité) | **1** (`system_config`) | **0** |

Honnêtement, **15 actions sont protégées par un contrôle de leurs paramètres**. Deux autres le sont parce qu'aucun chemin vivant ne peut les atteindre ; si un jour un chemin les expose, elles redeviennent non protégées. La seule protection partielle, `system_config`, n'a été traitée par aucun des trois briefs. Elle demande toujours une confirmation, mais ne contrôle pas ses paramètres.

---

# Annexe B — BT7 : les huit éléments enregistrés, constat sans action

Aucun de ces éléments n'a été modifié ni supprimé : empreintes MD5 identiques avant et après le sprint. « Aujourd'hui » désigne le comportement réel **avant** ce sprint (§6.1).

| # | Élément | Ce qu'il fait | Aujourd'hui (avant B1-ter) | Nouvelles règles |
|---|---|---|---|---|
| 1 | Workflow `demarrage_matin` | Lance Opera GX, Discord, VS Code ; diagnostic ; notification | Tout s'exécute | **Passe** |
| 2 | Workflow `mode_gaming` | Ferme `teams.exe` ; plan « Haute performance » ; lance Steam ; notification « Mode Gaming activé ✅ » | **Étapes 1 et 2 ne se sont jamais exécutées** (confirmation demandée, jamais donnée, anomalie A). Seuls Steam et la notification ont tourné. La notification annonçait un mode gaming qui n'était pas appliqué. | **Refusé** : `kill_process` et `system_config` exigent une confirmation |
| 3 | Workflow `mode_travail` | Lance Opera GX, VS Code, Discord ; notification | Tout s'exécute | **Passe** |
| 4 | Workflow `nettoyage_systeme` | Vide la corbeille ; supprime les fichiers temporaires de plus de 7 jours ; libère la RAM ; notification | Tout s'exécute, **y compris la suppression définitive de la corbeille** (anomalie B) | **Refusé** : `maintenance_empty_bin` |
| 5 | Workflow `workflow_discord_spotify` (créé par conversation, non versionné) | Lance Discord et Spotify | Tout s'exécute | **Passe** |
| 6 | Tâche « lundis a 9h lance steam » | Lance Steam le lundi à 9 h | S'exécute | **Passe** |
| 7 | Tâche « Job sans nom » | **Rien** : aucune action, toutes les 24 h | Se déclenche sans effet depuis le 10/04/2026 (résidu d'une demande de planification sans action reconnue) | **Passe** (rien à valider), mais inerte (B1T-R6) |
| 8 | Déclencheur « GPU over 90 » | Notification « GPU high » si GPU > 90 % pendant 2 s | Fonctionne (déclenché 9 fois, dernier le 27/06/2026) | **Passe** |

**Éléments qui ne fonctionnaient déjà pas à cause de l'anomalie A :** seulement `mode_gaming`, mais pour **deux étapes**, et non une comme le supposait le brief. Aucun autre élément ne contient d'action à confirmation. Le « Job sans nom » ne fonctionne pas non plus, mais pour une autre raison : il est vide.

### Options pour `mode_gaming` (décision d'Alexis)

| Option | Effet | Pour | Contre |
|---|---|---|---|
| a. Exception explicite pour le plan d'alimentation | Autoriser `system_config` avec la seule valeur `action: set_power_plan` et une liste fermée de plans | Le plan d'alimentation est réversible et sans perte ; c'est le cœur du « mode gaming » | Ouvre une porte dans `system_config`, à borner strictement. `kill_process` reste refusé. |
| b. Réécriture | Retirer « Fermer apps inutiles » (ou le remplacer par une notification « pense à fermer Teams »), et garder le reste avec l'option a ou sans le plan d'alimentation | Le workflow dit enfin la vérité sur ce qu'il fait | Perd la fermeture automatique de Teams, qui n'a de toute façon jamais eu lieu |
| c. Workflow « à la demande » avec confirmations réelles | Présenter chaque confirmation à l'utilisateur quand il lance lui-même le workflow | Garde toutes les étapes, en sécurité | Demande une évolution du moteur et de l'interface (hors périmètre) ; reste interdit en automatique |
| d. Suppression | — | Simple | Perd Steam et la notification, qui fonctionnaient |

Recommandation : **b**, avec **a** si le plan d'alimentation compte pour toi.

### Options pour `nettoyage_systeme` (décision d'Alexis)

| Option | Effet | Pour | Contre |
|---|---|---|---|
| a. Exception « à la demande seulement » | Admettre `maintenance_empty_bin` dans un workflow lancé par l'utilisateur, jamais dans une tâche ni un déclencheur | Garde l'usage réel : aucune tâche ne lance ce workflow aujourd'hui, il ne tourne qu'à la demande | Demande de distinguer lancement demandé et automatique (même prérequis que l'option c ci-dessus) |
| b. Réécriture | Retirer « Vider la corbeille », garder temporaires, RAM et notification | Immédiat ; plus aucune suppression définitive récurrente | La corbeille se vide à la main |
| c. Suppression | — | Simple | Perd le nettoyage des temporaires, qui est utile et borné |

Recommandation : **b** tout de suite, **a** si la distinction « à la demande » est construite plus tard.

### Pour « Job sans nom »

Il est inoffensif. On peut le supprimer, ou le laisser. Je ne le touche pas.

---

*Rapport Sprint B1-ter — CHAT6 (Claude Opus 5, Claude Code Windows), 19/09/2026.*
