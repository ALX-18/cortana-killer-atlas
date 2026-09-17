# RAPPORT SPRINT B-MINIMAL — Verdir la suite et fermer les failles
Date: 17/09/2026
Agent: Claude Opus 5 (CHAT6, Claude Code Windows)

> Brief : `docs/briefs/BRIEF_SPRINT_B_MINIMAL.md`. Références : rapports A (L7, L13), M (P1.4, M-L4), M-bis (I-1, R-1 à R-3).
> Branche **`sprint-b-minimal`**, issue de `main` @ `7d5a9ce`. 5 commits, **non poussés**, à fusionner après lecture.

---

## 1. Résumé exécutif

**Statut global : VALIDÉ.**

**Critère qui débloque le sprint C :** `python -m pytest tests/ -q` renvoie **0** (376 passés, 0 échec, 0 ignoré), avec la production active. Sortie brute en section 5.

**Résultats principaux :**
- **Suite verte dans trois environnements :**
  - environnement complet (Docker) : **376 passés** ;
  - Docker en pause : **365 passés, 1 ignoré** ;
  - machine simulée sans ChromaDB : **363 passés, 13 ignorés** (code 0 dans les trois cas).
- **Isolation prouvée**, pendant le passage de référence mené avec la production en service :
  - les **121 fichiers** de `atlas_chromadb` sont identiques à l'octet avant et après ;
  - l'instantané API est identique (535 éléments) ;
  - les empreintes de `data/` et `logs/` sont identiques ;
  - aucun dossier temporaire ni processus ne reste.
- **Aucun test n'a échoué une fois isolé.**
- **Garde-fou** de `backup_memory.py` passé en **liste blanche**, couvert par 46 tests à `subprocess` simulé : l'incident I-1 (`compose down`) est refusé sans rien exécuter.
- **`ALLOW_RESET=FALSE`** : conteneur recréé, 535 éléments identiques, `reset` refusé (HTTP 403). **Découverte : la variable est ignorée par le serveur 1.4.1.** C'est la configuration de l'image qui refuse `reset` (prouvé sur conteneurs jetables, §4).
- **Aucun fichier de `core/`, `tools/`, `api/`, `main.py` ou `core_conversational/` modifié** (`git diff --name-only`).

**Réserve sur le préalable :** les copies externes demandées sont sur **d'autres disques du même PC** (A: et T:), pas hors machine. La sauvegarde `043101` n'y figurait pas au démarrage ; je l'y ai copiée à ta demande, puis vérifiée (§7, B-R1).

---

## 2. Objectifs vs réalisation

| Objectif / critère (brief) | Résultat réel | Statut |
|---|---|---|
| Sauvegarde externe `043101` confirmée par Alexis | Alexis confirme des copies sur les disques **A: et T: du même PC**. Contrôle : seule `030200` y figurait. Sur décision d'Alexis, j'ai copié `043101` sur A: et T: : 126 fichiers, 0 écart, archive `27df0647…` sur les deux. | PARTIEL (réserve « hors machine », §7) |
| Sauvegarde fraîche prise et vérifiée avant modification de `docker-compose.yml` | `chromadb_20260917_192138` (19:21:38), copie conforme ; `verify` code 0 | PASS |
| BM1 — Fichiers en attente commités, messages décrivant le changement réel | Rien en attente au démarrage : Alexis avait déjà tout commité dans `6a3453b`, dont le message « RAPPORT_SPRINT_M_BIS.md » ne décrit pas le contenu, et qui a **versionné `data/voices/fr_FR-siwis-medium.onnx.json`** (risque L20). Historique poussé, donc non réécrit. Les 5 commits du sprint ont des messages descriptifs. | PARTIEL (constat, §7) |
| BM2 — Scripts sortis de la collecte, sans suppression | 4 fichiers déplacés vers `scripts/manual/` et renommés sans préfixe `test_` (`git mv`) | PASS |
| BM3 — `TestVisionDisabled` passe isolé **et** en suite complète | `asyncio.run()` ; `1 passed` isolé ; vert dans les 3 passages complets | PASS |
| BM4 — Tests de service ignorés proprement quand le service est absent | `test_chroma_integration` (5) et `test_memory_v60` (8) ignorés sans ChromaDB de test ; `test_web_v20::test_01` ignoré sans SearXNG | PASS |
| BM5 — Tests isolés de la base et des données réelles ; échecs révélés signalés | `tests/conftest.py` : ChromaDB jetable + redirection de `data/` ; `tests/test_isolation.py` (5 tests) ; production et `data/` inchangés (preuves §5). **Aucun échec révélé.** | PASS |
| BM6 — Garde-fou en liste blanche, testé avec `subprocess.run` simulé | `check_docker_args()` ; `tests/test_backup_memory_guard.py` : 46 tests, `subprocess` remplacé dans le module | PASS |
| BM7 — `ALLOW_RESET=FALSE`, 535 éléments intacts après recréation, `reset` refusé | Fait ; 535 identiques à l'instantané ; `reset` → 403 ; données identiques après. Mécanisme réel documenté. | PASS |
| **`python -m pytest tests/ -q` → code 0**, sortie brute dans le rapport | Code 0, 376 passés (§5) | **PASS** |
| Aucune modification de `core/`, `tools/`, `api/`, `main.py`, `core_conversational/` | `git diff --name-only 7d5a9ce..HEAD` : aucun | PASS |

---

## 3. Architecture projet mise à jour

```
assistant-bureau/
├── docker-compose.yml                          ← MODIFIÉ (ALLOW_RESET=FALSE + commentaire)
├── scripts/
│   ├── backup_memory.py                        ← MODIFIÉ (liste blanche docker)
│   └── manual/                                 ← NOUVEAU dossier
│       ├── api_clean_check.py                  ← DÉPLACÉ de tests/test_api_clean.py
│       ├── stream_fix_check.py                 ← DÉPLACÉ de tests/test_stream_fix.py
│       ├── cleanup_check.py                    ← DÉPLACÉ de tests/test_cleanup.py
│       └── habit_persistence_check.py          ← DÉPLACÉ de tests/test_habit_persistence.py
├── tests/
│   ├── conftest.py                             ← NOUVEAU (isolation ChromaDB + data/)
│   ├── test_isolation.py                       ← NOUVEAU (5 tests)
│   ├── test_backup_memory_guard.py             ← NOUVEAU (46 tests)
│   ├── test_compose_config.py                  ← NOUVEAU (5 tests, statiques)
│   ├── test_automation_v30.py                  ← MODIFIÉ
│   ├── test_chroma_integration.py              ← MODIFIÉ
│   ├── test_final_v50.py                       ← MODIFIÉ
│   ├── test_memory_v60.py                      ← MODIFIÉ
│   ├── test_metrics_grounding_v52.py           ← MODIFIÉ
│   ├── test_stabilisation_v31.py               ← MODIFIÉ
│   ├── test_v53_migration.py                   ← MODIFIÉ
│   ├── test_web_v20.py                         ← MODIFIÉ
│   └── validate_v12.py                         ← MODIFIÉ (script custom isolé)
└── docs/rapports/RAPPORT_SPRINT_B_MINIMAL.md   ← NOUVEAU
```

`git diff --stat 7d5a9ce..HEAD` : 19 fichiers, +625 / −47.

**Commits (branche `sprint-b-minimal`)**

| Commit | Tâche | Titre |
|---|---|---|
| `9c8e7e0` | BM2 | tests: sortir de tests/ quatre scripts qui agissaient à l'import |
| `01c733c` | BM3 | tests: TestVisionDisabled ne dépend plus de la boucle asyncio laissée par d'autres tests |
| `52c41dc` | BM4, BM5 | tests: isoler la suite de la mémoire ChromaDB et des données réelles |
| `30dc6e4` | BM6 | backup_memory: garde-fou docker en liste blanche, testé avec subprocess simulé |
| `c0087c8` | BM7 | docker-compose: ALLOW_RESET=FALSE pour atlas_chromadb, et test statique des protections |

Le présent rapport fera l'objet d'un sixième commit.

**Hors dépôt**
- `C:\Users\alexis\Atlas_backups\memoire\chromadb_20260917_192138\` : **nouvelle** sauvegarde vérifiée.
- `A:\Atlas_backups\memoire\chromadb_20260917_043101\` et `T:\Atlas_backups\memoire\chromadb_20260917_043101\` : **nouvelles** copies.
- Docker : `atlas_chromadb` **recréé** à 19:22:24 (même volume, même image) ; conteneurs jetables `atlas_memcheck_reset_TRUE`, `_FALSE` et `_cfg` créés puis supprimés, ainsi que ceux des vérifications (`atlas_memcheck_2026…`).

---

## 4. Détail des implémentations

### BM2 — `scripts/manual/`
- Déplacement par `git mv`, sans suppression.
- Renommage sans préfixe `test_` : placés hors de `tests/` mais toujours nommés `test_*.py`, les scripts seraient ramassés par un `pytest` lancé sans argument.
- Docstrings complétées : effets réels (« envoie de VRAIES commandes à une instance Atlas », « ÉCRIT DANS LE VRAI data/habits.db », « EXÉCUTE DE VRAIS OUTILS, dont launch_app steam ») et usage.
- Chemins ajustés au nouvel emplacement : `os.chdir(.., ..)` pour `habit_persistence_check.py`, `sys.path` absolu pour `cleanup_check.py`.
- Les 4 fichiers compilent (`py_compile`). Ils n'ont **pas** été exécutés : leurs effets sont réels.
- Les autres scripts ad hoc de `tests/` (`debug_*.py`, `api_*_check.py`, etc., inventaire du sprint A) ne sont pas collectés par pytest et n'ont pas été déplacés (hors périmètre de BM2, candidats au sprint C).

### BM3 — `tests/test_v53_migration.py`
`asyncio.get_event_loop().run_until_complete(...)` est remplacé par `asyncio.run(...)`.

### BM4 / BM5 — `tests/conftest.py`
- **`pytest_configure`** s'exécute avant la collecte, ce qui est nécessaire : `test_memory_v60` sonde ChromaDB à l'import.
  1. **ChromaDB jetable** : `python -c "…chromadb.cli.cli.app()" run --path <tmp> --port <libre>`, dans l'interpréteur courant. Le lanceur `chroma.exe` crée en effet un processus enfant qui survit à `terminate()` et verrouille les fichiers ; c'est ce qu'a révélé un premier essai, avec 3 dossiers orphelins supprimés ensuite. Attente du heartbeat, 40 s au plus. `ATLAS_TEST_NO_CHROMA=1` saute cette étape.
  2. **Redirection ChromaDB** : `chromadb.HttpClient` est remplacé par une fonction qui **ignore l'hôte et le port demandés** et vise le serveur jetable, ou à défaut un port libre non écouté (connexion refusée, jamais la production). `core.memory_manager.CHROMA_HOST/PORT` sont alignés et son singleton est réinitialisé. Le client d'origine reste accessible via `chromadb.HttpClient.original`, pour les tests.
  3. **Redirection de `data/`** : projet temporaire `atlas_tests_root_*` (copie des 4 workflows modèles versionnés, sans le workflow personnel, et de `config/settings.json`). Réaffectation de `atlas_logger.LOG_FILE`, `context_monitor._DB_PATH`, `file_indexer.DATA_DIR/INDEX_FILE`, `file_organizer.DATA_DIR/HISTORY_FILE`, `scheduler.*`, `trigger_engine.*`, `workflow_engine.*`, `app_launcher.FILE_INDEX_PATH`, `grounding._DEBUG_IMAGE_DIR` et `system_config._AUDIT_LOG_PATH`.
  4. **`api/routes.py`** construit `…/data/atlas_actions.jsonl` et `…/config/settings.json` à partir de son propre `__file__`, dans chaque fonction. Sans modifier `api/`, le module `pathlib` **vu par `routes`** est remplacé par une copie dont `Path(routes.__file__)` renvoie `<racine temporaire>/api/routes.py`. Les autres chemins passent inchangés. **Il s'agit d'un contournement de test ; le défaut produit (chemins de données dispersés) relève de B-complet.**
- **`pytest_report_header`** affiche l'URL du ChromaDB de test et la racine temporaire.
- **`pytest_unconfigure`** arrête le serveur (`terminate`, puis `kill` après 10 s) et supprime les dossiers, avec jusqu'à 10 tentatives espacées de 0,5 s (latence de libération des fichiers sous Windows).

### BM4 / BM5 — tests adaptés
- `test_chroma_integration.py` : cible `ATLAS_TEST_CHROMA_URL` ; `pytestmark = skipif(...)` si le serveur est absent.
- `test_memory_v60.py` : la sonde utilise `chromadb.HttpClient()` (redirigé) ; message de skip mis à jour.
- `test_web_v20.py` : `_searxng_up()` + `skipif` sur `test_01`.
- `test_automation_v30.py`, `test_metrics_grounding_v52.py`, `test_stabilisation_v31.py`, `test_final_v50.py::test_07` : chemins lus **dans les modules**, donc redirigés, au lieu de `data/` réel. **Ces tests supprimaient puis restauraient les vrais fichiers** (`atlas_actions.jsonl`, `schedules.json`, `triggers.json`) : une interruption en cours de test les aurait perdus. Chaque fichier vérifie à l'import que l'isolation est active.
- `test_final_v50.py::test_01` : `main.LOCK_FILE` passe dans `tmp_path`, au lieu du vrai `data/atlas.lock`.
- `validate_v12.py` (script custom) : applique `tests.conftest._isolate_data()` avant exécution, puis supprime le dossier.

### BM5 — `tests/test_isolation.py`
Cinq tests :
- la redirection de `chromadb.HttpClient` (hôte `127.0.0.1`, jamais le port 8001, appels positionnels comme nommés) ;
- le port de `memory_manager` ;
- les 10 chemins de modules, sous la racine temporaire et hors du `data/` réel ;
- la redirection ciblée de `routes` ;
- la présence des 4 modèles de workflows.

### BM6 — `scripts/backup_memory.py`
- `check_docker_args(args)`, appelée **avant** `subprocess.run`, lève `GuardRefusal` pour tout ce qui n'est pas explicitement autorisé :
  - `inspect`, `ps`, `volume inspect` ;
  - `exec` limité à `sh -c <HASH_SCRIPT|CONFIG_SCRIPT>`, deux constantes désormais utilisées par le script lui-même ;
  - `cp` uniquement `conteneur:/chemin` vers l'hôte (un chemin Windows `C:\…` n'est pas pris pour un conteneur) ;
  - `run` et `create` avec `--pull never`, un nom `atlas_memcheck_*` ou `--rm`, et le volume de production monté uniquement en `:ro` ;
  - `rm` uniquement si **toutes** les cibles commencent par `atlas_memcheck_`.
- Tout le reste est refusé, dont `compose`, `start`, `stop`, `kill`, `volume rm/prune/create`, `pull`, `system prune`, `image rm` et `commit`.
- Docstring mise à jour.

### BM6 — `tests/test_backup_memory_guard.py`
- Fixture autouse : `backup_memory.subprocess` est remplacé par un espace de noms dont `run` enregistre les appels. Le module global `subprocess` **n'est pas** modifié, et la substitution est vérifiée avant chaque test.
- 35 commandes refusées, dont `compose down`, `compose down -v`, `rm -f atlas_chromadb`, un `exec … rm -rf /data` et un `exec` chaînant le script autorisé avec `; rm -rf /data`. Pour chacune, on vérifie qu'**aucun appel** n'atteint `subprocess`.
- 11 commandes autorisées, transmises telles quelles.
- Un parcours `cmd_backup` complet (docker et HTTP simulés) qui n'emploie que `ps`, `inspect`, `exec` et `cp`.

### BM7 — `docker-compose.yml`
- `ALLOW_RESET=TRUE` → `FALSE`, avec un commentaire décrivant le mécanisme réel.
- **Expériences préalables sur conteneurs jetables** (image identique, base vide, collection « canari ») :

| Conteneur | `reset` | Canari après |
|---|---|---|
| `ALLOW_RESET=TRUE` | **HTTP 403** « Reset is disabled by config » | présent |
| `ALLOW_RESET=FALSE` | HTTP 403 | présent |
| `/config.yaml` contenant `allow_reset: true` (contrôle positif) | **HTTP 200** | **disparu** |

- **Conclusion mesurée :** le serveur 1.4.1 ignore la variable. Seul `allow_reset` dans `/config.yaml` compte, et le fichier de l'image (`persist_path: "/data"`, SHA-256 `dbedd3fa…`) ne l'active pas. La production n'a donc jamais été réinitialisable par cette voie, y compris avec `TRUE`.
- **Application en production :**
  1. Sauvegarde et vérification (`192138`).
  2. Instantané.
  3. `docker compose --dry-run up -d` : seul `atlas_chromadb` est recréé.
  4. `docker compose up -d`.
  5. Comparaison : identique.
  6. Vérification que le `/config.yaml` de la production est identique à celui des jetables.
  7. `POST /api/v2/reset` → **403**.
  8. Nouvelle comparaison : identique.
- Aucun appel à `reset` dans `core/`, `core_conversational/`, `tools/`, `api/`, `main.py`, `tests/` ou `scripts/` (grep).

### `tests/test_compose_config.py`
Test statique (lecture YAML) qui verrouille :
- le projet `atlas` ;
- le digest de l'image et `pull_policy: never` ;
- le volume externe monté sur `/data` ;
- `ALLOW_RESET=FALSE` et l'absence de montage sur `/config.yaml` ;
- le profil du service `ollama`.

**Hors périmètre littéral :** ce fichier est dans `tests/` (autorisé), mais il n'était pas demandé. Justification : sans lui, les protections de M-bis et de BM7 pourraient régresser en silence.

---

## 5. Résultats des tests

Environnement : `.venv` historique (Python 3.12.3, pytest 9.0.2, pytest-asyncio 1.3.0), depuis `assistant-bureau/`, `PYTHONIOENCODING=utf-8`, Atlas arrêté.

### Commande de référence — environnement complet (Docker : `atlas_chromadb` et `atlas_searxng` actifs), 19:24:01 → 19:25:35

```
python -m pytest tests/ -q
```
Sortie brute intégrale :
```
C:\Users\alexis\Cortana_Killer\.venv\Lib\site-packages\pywinauto\__init__.py:80: UserWarning: Revert to STA COM threading mode
  warnings.warn("Revert to STA COM threading mode", UserWarning)
C:\Users\alexis\Cortana_Killer\.venv\Lib\site-packages\pytest_asyncio\plugin.py:247: PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.
The event loop scope for asynchronous fixtures will default to the fixture caching scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to function scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session"

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
........................................................................ [ 19%]
........................................................................ [ 38%]
........................................................................ [ 57%]
........................................................................ [ 76%]
........................................................................ [ 95%]
................                                                         [100%]
============================== warnings summary ===============================
tests/test_vision_parsers.py::TestGroundingTimeoutEnforced::test_layer_timeout_aborts_slow_layer
  C:\Users\alexis\Cortana_Killer\.venv\Lib\site-packages\easyocr\detection.py:81: DeprecationWarning: torch.ao.quantization is deprecated and will be removed in 2.10. 
  For migrations of users: 
  1. Eager mode quantization (torch.ao.quantization.quantize, torch.ao.quantization.quantize_dynamic), please migrate to use torchao eager mode quantize_ API instead 
  2. FX graph mode quantization (torch.ao.quantization.quantize_fx.prepare_fx,torch.ao.quantization.quantize_fx.convert_fx, please migrate to use torchao pt2e quantization API instead (prepare_pt2e, convert_pt2e) 
  3. pt2e quantization has been migrated to torchao (https://github.com/pytorch/ao/tree/main/torchao/quantization/pt2e) 
  see https://github.com/pytorch/ao/issues/2259 for more details
    torch.quantization.quantize_dynamic(net, dtype=torch.qint8, inplace=True)

tests/test_vision_parsers.py::TestGroundingTimeoutEnforced::test_layer_timeout_aborts_slow_layer
tests/test_vision_parsers.py::TestGroundingTimeoutEnforced::test_layer_timeout_aborts_slow_layer
  C:\Users\alexis\Cortana_Killer\.venv\Lib\site-packages\torch\ao\quantization\quantize.py:570: DeprecationWarning: torch.ao.quantization is deprecated and will be removed in 2.10. 
  For migrations of users: 
  1. Eager mode quantization (torch.ao.quantization.quantize, torch.ao.quantization.quantize_dynamic), please migrate to use torchao eager mode quantize_ API instead 
  2. FX graph mode quantization (torch.ao.quantization.quantize_fx.prepare_fx,torch.ao.quantization.quantize_fx.convert_fx, please migrate to use torchao pt2e quantization API instead (prepare_pt2e, convert_pt2e) 
  3. pt2e quantization has been migrated to torchao (https://github.com/pytorch/ao/tree/main/torchao/quantization/pt2e) 
  see https://github.com/pytorch/ao/issues/2259 for more details
    convert(model, mapping, inplace=True)

tests/test_vision_parsers.py::TestGroundingTimeoutEnforced::test_layer_timeout_aborts_slow_layer
  C:\Users\alexis\Cortana_Killer\.venv\Lib\site-packages\easyocr\recognition.py:177: DeprecationWarning: torch.ao.quantization is deprecated and will be removed in 2.10. 
  For migrations of users: 
  1. Eager mode quantization (torch.ao.quantization.quantize, torch.ao.quantization.quantize_dynamic), please migrate to use torchao eager mode quantize_ API instead 
  2. FX graph mode quantization (torch.ao.quantization.quantize_fx.prepare_fx,torch.ao.quantization.quantize_fx.convert_fx, please migrate to use torchao pt2e quantization API instead (prepare_pt2e, convert_pt2e) 
  3. pt2e quantization has been migrated to torchao (https://github.com/pytorch/ao/tree/main/torchao/quantization/pt2e) 
  see https://github.com/pytorch/ao/issues/2259 for more details
    torch.quantization.quantize_dynamic(model, dtype=torch.qint8, inplace=True)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
376 passed, 4 warnings in 82.83s (0:01:22)
```
**Code de retour : 0.**

**Preuves d'isolation, relevées autour de ce passage :**
```
instantané API production avant  : 535 éléments (documents 7bfaad20…, errors e067ff39…, memory b277039f…, conversations 623c1c6f…)
instantané API production après  : IDENTIQUE À L'INSTANTANÉ (ids, documents, métadonnées, embeddings, uuid de collection) : True
fichiers de atlas_chromadb (sha256, 121) avant/après : fichiers production identiques : True 121 []
find data logs -type f -exec sha256sum (18 fichiers) avant/après : data/ et logs/ INCHANGÉS
%TEMP%\atlas_tests_* après : aucun reliquat
```

### Autres passages de la commande de référence

| Contexte | Commande | Résultat | Code |
|---|---|---|---|
| Docker en pause manuelle (production injoignable), avant ajout des tests d'isolation et de compose | `python -m pytest tests/ -q` | `365 passed, 1 skipped` (SearXNG) ; `data/` et `logs/` inchangés | 0 |
| Machine simulée sans ChromaDB, production **joignable** | `ATLAS_TEST_NO_CHROMA=1 python -m pytest tests/ -q -rs` | `363 passed, 13 skipped` : 5 `test_chroma_integration` + 8 `test_memory_v60` (« ChromaDB de test non disponible »). Production identique à l'instantané après. | 0 |

Ce dernier passage montre qu'en l'absence du serveur de test, la production (pourtant en service sur 8001) n'est **pas** utilisée en repli.

### Tests ciblés
```
python -m pytest "tests/test_v53_migration.py::TestVisionDisabled::test_vision_disabled_returns_skipped" -q  → 1 passed
python -m pytest tests/test_backup_memory_guard.py -q                                                          → 46 passed
python -m pytest tests/test_isolation.py -q                                                                    → 5 passed
python -m pytest tests/test_compose_config.py -q                                                               → 5 passed
python -m pytest tests/test_chroma_integration.py tests/test_web_v20.py::test_01_searxng_heartbeat_under_3s -rs
   → en-tête « atlas: ChromaDB de test = http://127.0.0.1:62659 » ; 5 passed, 1 skipped (Docker en pause)
```

### Suites custom (scripts), `data/` et `logs/` inchangés après
```
python tests/test_architecture_v23.py → exit=0 — RÉSULTAT : 23/23 (100%)
python tests/test_interaction_v22.py  → exit=0 — Résultat : 10/10 tests passés
python tests/validate_v12.py          → exit=0 — (données de test : …\atlas_tests_root_lxycnm6w) … === ALL TESTS PASSED ===
```

### Non-régression par rapport au sprint A (passage 4)
- Sprint A : 319 passés, 1 échec, 2 erreurs de collecte, sur 322 éléments.
- Aujourd'hui : **376 passés**.
- Différence :
  - les 2 « erreurs » étaient des scripts, désormais déplacés ;
  - l'échec `TestVisionDisabled` est corrigé ;
  - **+56 tests nouveaux** (46 garde-fou, 5 isolation, 5 compose) ;
  - les 320 tests d'origine passent tous.
- **Échecs révélés par l'isolation : aucun.** Un point à noter : `TestMetricsGroundingEmpty::test_no_log_returns_zero_counts` ne passait jusqu'ici que parce que sa fixture **supprimait le vrai journal**. Il passe maintenant sur un journal temporaire vide.

---

## 6. Comportement observé en scénarios réels

| ID | Scénario | Attendu | Observé | Statut |
|---|---|---|---|---|
| S01 | Contrôle des copies externes (A:, T:) | `043101` présente | Seule `030200` présente, avec archive conforme | Écart signalé |
| S02 | Copie de `043101` vers A: et T: | 126 fichiers conformes | 126/126, archive `27df0647…` sur les deux | PASS |
| S03 | Suite complète, production active | Code 0, production intacte | 376 passés ; 121/121 fichiers et API identiques | PASS |
| S04 | Suite, Docker en pause | Tests de service ignorés, code 0 | 365 passés, 1 ignoré | PASS |
| S05 | Suite sans ChromaDB de test, production joignable | Aucun repli sur la production | 13 ignorés, production identique | PASS |
| S06 | `reset` sur jetables TRUE / FALSE / config | Comprendre le mécanisme | 403 / 403 / 200 (base vidée) | PASS |
| S07 | Recréation de `atlas_chromadb` avec `ALLOW_RESET=FALSE` | 535 intacts | Identique à l'instantané | PASS |
| S08 | `POST /api/v2/reset` en production | Refusé | HTTP 403 ; données identiques après | PASS |
| S09 | Scripts custom | Verts, sans écriture réelle | 23/23, 10/10, ALL PASS ; `data/` inchangé | PASS |
| S10 | Premier nettoyage du ChromaDB de test | Aucun reliquat | 3 dossiers orphelins (processus enfant de `chroma.exe`) → corrigé, puis vérifié sans reliquat | PASS après correction |

Atlas n'a pas été lancé : ce sprint ne touche pas au produit.

---

## 7. Limites et risques identifiés

| # | Description | Sévérité | Mitigation proposée |
|---|---|---|---|
| B-R1 | Les copies « externes » sont sur **d'autres disques du même PC** (A:, T:). Elles protègent d'une panne du disque C:, pas d'un vol, d'un sinistre, d'un rançongiciel ni d'une panne d'alimentation détruisant plusieurs disques. | Élevé | Une copie réellement hors machine (disque débranché ou stockage distant chiffré). Action d'Alexis. |
| B-R2 | La sauvegarde du jour (`192138`) n'est copiée ni sur A: ni sur T:. Son archive est toutefois identique à celle de `043101` (`27df0647…`), qui l'est. | Faible | Aucune tant que la base n'évolue pas ; recopier après usage d'Atlas. |
| B-R3 | `6a3453b` (commit d'Alexis) a versionné `data/voices/fr_FR-siwis-medium.onnx.json` (risque L20), avec un message non descriptif. Fichier public (configuration de voix Piper), sans donnée sensible. | Faible | Sprint C : `git rm --cached` + `data/voices/` dans `.gitignore`. Historique poussé : pas de réécriture. |
| B-R4 | **`ALLOW_RESET` est une configuration morte** pour le serveur 1.4.1. La protection réelle tient au `/config.yaml` de l'image, qui pourrait changer avec une autre image. Le digest épinglé et `test_compose_config` limitent ce risque. | Moyen | Sprint C/B : monter un `/config.yaml` explicite contenant `allow_reset: false`, versionné. Le test statique interdit aujourd'hui tout montage de `/config.yaml` sans revue. |
| B-R5 | Le contournement `pathlib` sur `api/routes.py` dépend de la forme actuelle du code (`pathlib.Path(__file__)`). Une réécriture de `routes` le rendrait inopérant ; `test_isolation::test_routes_data_path_is_redirected` le détecterait alors. | Moyen | B-complet : centraliser le répertoire de données (constante unique ou variable d'environnement) et supprimer le contournement. |
| B-R6 | L'isolation couvre la mémoire ChromaDB et `data/`, **pas** les autres effets réels de certains tests : réseau (ddgs, example.com, SearXNG en lecture), navigateur Playwright, lecture de l'écran par EasyOCR, fenêtre active (`test_interaction_v22` test 3), appels Ollama éventuels. | Moyen | Inventaire A.4 du rapport A ; marquage `integration` et option de désactivation au sprint C ou B. |
| B-R7 | `main.py`, importé par des tests, construit un `FileHandler` vers le vrai `logs/atlas.log` : ouverture en ajout, **aucune écriture constatée** (empreintes inchangées). | Faible | B-complet : configuration du journal hors import. |
| B-R8 | Le ChromaDB de test est la version native 1.5.1 (client installé), et non l'image 1.4.1 de production. La compatibilité des deux a été démontrée au sprint M. | Faible | Accepté ; un test contre l'image exacte demanderait Docker. |
| B-R9 | `validate_v12.py` importe désormais `tests.conftest` : il doit être lancé depuis `assistant-bureau/` (comme avant). | Faible | Documenté dans le code. |
| B-R10 | Avertissements restants : `asyncio_default_fixture_loop_scope` non défini (pytest-asyncio), dépréciations torch via EasyOCR. Non bloquants. | Faible | Sprint C : `pytest.ini` avec `asyncio_default_fixture_loop_scope = function`. |
| B-R11 | La branche `sprint-b-minimal` n'est pas poussée ni fusionnée. | Faible | Alexis : relire, fusionner, pousser. |

---

## 8. Checklist de validation

- [ ] **Sauvegarde externe `043101` confirmée par Alexis** : les copies sont sur A: et T:, disques du **même** PC ; `043101` n'y était pas et a été ajoutée par moi à la demande d'Alexis, puis vérifiée (§2). Non coché, faute de copie hors machine (B-R1).
- [x] **Sauvegarde fraîche prise et vérifiée avant modification de `docker-compose.yml`** : `192138`, `verify` code 0 (§5, BM7).
- [x] **Fichiers en attente commités, avec des messages décrivant le changement réel** : rien n'était en attente (déjà dans `6a3453b`) ; les 5 commits du sprint sont descriptifs (§3). Constat sur `6a3453b` en B-R3.
- [x] **Scripts sortis de la collecte, sans suppression** : `scripts/manual/` (§4).
- [x] **`TestVisionDisabled` passe isolé et en suite complète** : §5.
- [x] **Tests de service ignorés proprement quand le service est absent** : passages « Docker en pause » et « sans ChromaDB » (§5).
- [x] **Tests isolés de la base et des données réelles ; échecs révélés par l'isolation signalés** : preuves §5 ; aucun échec révélé.
- [x] **Garde-fou en liste blanche, testé avec `subprocess.run` simulé** : 46 tests (§4, §5).
- [x] **`ALLOW_RESET=FALSE`, 535 éléments intacts après recréation, `reset` refusé** : §4, §6 (S07, S08).
- [x] **`python -m pytest tests/ -q` → code 0, sortie brute dans le rapport** : §5.
- [x] **Aucune modification de `core/`, `tools/`, `api/`, `main.py`, `core_conversational/`** : `git diff --name-only 7d5a9ce..HEAD`.

---

## 9. Recommandations pour le sprint suivant

**Le critère de déblocage du sprint C est rempli : la suite est verte, avec la commande brute.**

### P1
- P1.1 Copie **hors machine** d'une sauvegarde vérifiée (B-R1).
- P1.2 Relire et fusionner `sprint-b-minimal` dans `main`, puis pousser (B-R11).
- P1.3 Pendant le sprint C, relancer `python -m pytest tests/ -q` après chaque déplacement : c'est la référence verte (376).

### P2 (sprint C)
- P2.1 `data/voices/` dans `.gitignore` et retrait de l'index du `.onnx.json` (B-R3).
- P2.2 `pytest.ini` : `asyncio_default_fixture_loop_scope`, marqueurs `integration`/`network`/`desktop` pour les tests à effets réels (B-R6, B-R10).
- P2.3 Ranger les autres scripts ad hoc de `tests/` (inventaire A, B.2).
- P2.4 `/config.yaml` explicite (`allow_reset: false`) monté et versionné (B-R4).

### P3 (B-complet)
- P3.1 Centraliser le répertoire de données du produit, puis retirer le contournement `pathlib` du `conftest` (B-R5).
- P3.2 Défauts produit du sprint A (voix, heure, `window_hotkey`, grounding…), inchangés dans ce sprint, conformément au brief.

---

*Rapport Sprint B-minimal — CHAT6 (Claude Opus 5, Claude Code Windows), 17/09/2026.*
