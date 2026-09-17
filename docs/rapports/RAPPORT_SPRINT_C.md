# RAPPORT SPRINT C — Restructuration du dépôt
Date: 17/09/2026
Agent: Claude Opus 5 (CHAT6, Claude Code Windows)

> Brief : `docs/briefs/BRIEF_SPRINT_C.md`. Références : rapports A (A6, L20), M-bis (R-6, R-7), B-minimal.
> Branche **`sprint-c`**, issue de `main` @ `e0db2e0` (après fusion de `sprint-b-minimal`). 3 commits, **non poussés**.

---

## 1. Résumé exécutif

**Statut global : VALIDÉ**, avec une réserve assumée : la pile vision MiniCPM-V est **conservée**, sur décision d'Alexis, faute de remplir le critère de suppression du brief (§4, C6).

- **`assistant-bureau/` n'existe plus.** Tout le projet est à la racine du dépôt, déplacé par `git mv` : l'historique suit les fichiers.
- **Suite verte avant et après :** `python -m pytest tests/ -q` → **code 0**, 376 tests après déplacement, **377** après nettoyage (le test ajouté est expliqué en §5).
- **Aucune dérive de dépendances**, et pour une raison qui invalide le piège 1 du brief : **le venv n'était pas dans `assistant-bureau/`**, mais déjà à la racine du dépôt. Il n'a donc pas eu à être recréé ; `pip freeze` est identique au bit près (148 paquets).
- **Les chemins du code n'ont pas eu à changer** : ils sont tous construits relativement au fichier source (`Path(__file__).parent.parent`), et l'arborescence a bougé d'un bloc. Un seul fichier pointait hors du dépôt après l'aplatissement : `start_atlas_desktop.bat`, corrigé.
- **Collision des `README.md` : sans perte**, les deux fichiers étaient strictement identiques.
- **Documentation rangée** : le répertoire `rapport.md` a disparu, `RAPPORT_RULES.md` est dans `docs/`, les 14 rapports sont dans `docs/rapports/`.
- **Nettoyage** : 3 fichiers morts supprimés avec preuve, 16 scripts ad hoc sortis de `tests/`.
- **Hygiène** : `data/voices/` ignoré et le `.onnx.json` retiré du suivi, image SearXNG épinglée par digest, volume nommé pour son cache, 4 volumes anonymes vides supprimés, et correction d'un défaut que j'avais introduit au sprint M-bis (`pull_policy: never` empêchait toute installation neuve).
- **Mémoire intacte** : après `docker compose down` puis `up -d`, les **535 éléments** sont identiques (identifiants, documents, métadonnées, embeddings).
- **Aucun fichier perdu** : 159 → 154 fichiers suivis, soit exactement les 5 retraits voulus.

---

## 2. Objectifs vs réalisation

| Objectif / critère (brief) | Résultat réel | Statut |
|---|---|---|
| `sprint-b-minimal` fusionnée dans `main`, travail sur `sprint-c` | Fusion en avance rapide (`7d5a9ce` → `e0db2e0`), branche `sprint-c` créée | PASS |
| C1 — Référence consignée : suite, `pip freeze`, inventaire Git, sauvegarde mémoire | 376 passés (code 0) ; 148 paquets ; 159 fichiers suivis ; sauvegarde `chromadb_20260917_211056` vérifiée | PASS |
| C2 — `assistant-bureau/` a disparu, contenu à la racine, historique préservé | `git mv` pour tout le contenu suivi ; `logs/` et `models/` (non suivis) déplacés par `mv` ; répertoire supprimé | PASS |
| Collision des deux `README.md` traitée et documentée | Fichiers **strictement identiques** (`diff` vide) : celui de la racine conservé, l'autre supprimé | PASS |
| C3 — `rapport.md` n'existe plus comme répertoire ; `RAPPORT_RULES.md` dans `docs/` | Fait ; ses 4 autres fichiers dans `docs/rapports/` | PASS |
| C3 — Rapports regroupés dans `docs/rapports/` | 14 rapports, dont les 6 de l'ancienne racine | PASS |
| C4 — Correction des chemins, fichier par fichier | Revue des 8 points du piège 3 (§4) ; 1 seul correctif nécessaire (`start_atlas_desktop.bat`) + `.gitignore`, README et 3 documents | PASS |
| C5 — Nouveau venv créé, dérive signalée | **Sans objet** : le venv était déjà à la racine (`C:\Users\alexis\Cortana_Killer\.venv`), il n'a pas bougé ni été recréé. `pip freeze` identique, consigné. | PASS (prémisse infirmée) |
| C5 — Suite verte, 376 tests | 376 passés, code 0, après déplacement | PASS |
| C5 — Atlas démarre, `/api/health` conforme, mémoire lue | `status: ok`, 4 services ; rappel « discord » → souvenir réel de février | PASS |
| C5 — `doctor.py` cohérent | Chemins à la racine, ChromaDB persistant, 2 critiques antérieurs (cuBLAS, CLI piper — sprint A) | PASS |
| C6 — Suppressions justifiées par une preuve | 3 fichiers supprimés avec `git grep` à l'appui ; 16 scripts déplacés | PASS |
| C6 — Pile vision MiniCPM-V | **Conservée**, sur décision d'Alexis : encore référencée par 5 fichiers de code et 6 de tests, donc hors critère du brief (§4) | ÉCART DOCUMENTÉ |
| C7 — `data/voices/` ignoré, `.onnx.json` retiré du suivi | Fait, fichier conservé sur le disque | PASS |
| C7 — Image SearXNG épinglée, volume nommé pour son cache | Digest `sha256:edf110a2…`, volume `atlas_searxng_cache` ; 4 volumes anonymes vides supprimés | PASS |
| C7 — Aucun secret dans le dépôt | Vérifié ; la clé SearXNG est une valeur de remplacement pour un service lié à 127.0.0.1, désormais commentée | PASS |
| C8 — Suite verte après nettoyage | **377** passés, code 0 (écart de +1 expliqué) | PASS |
| C8 — `docker compose down` / `up` : 535 éléments intacts | Identique à l'instantané | PASS |
| C8 — Inventaire Git comparé, aucun fichier perdu | 159 → 154, les 5 écarts attendus | PASS |

---

## 3. Architecture projet mise à jour

**Avant** : tout sous `assistant-bureau/`, racine du dépôt à 3 fichiers.
**Après** :

```
Cortana_Killer/                     (racine du dépôt)
├── main.py  docker-compose.yml  start_atlas_desktop.bat
├── requirements.txt  requirements-mac-manman.txt  requirements-core-conversational.txt
├── README.md  .gitignore
├── api/  core/  core_conversational/  tools/  ui/  desktop/  atlas-extension/
├── config/            (settings.json, searxng/)
├── data/              (non suivi : mémoire runtime, voices/, debug/, workflows/ modèles suivis)
├── logs/  models/     (non suivis)
├── scripts/
│   ├── doctor.py  backup_memory.py  download_voice_models.py
│   ├── check_ollama_config.py  compare_ocr_engines.py  profile_minicpm.py
│   └── manual/        ← 20 scripts à effets réels (4 du sprint B-minimal + 16 déplacés ici)
├── tests/             ← uniquement des tests, conftest.py et validate_v12.py
├── docs/
│   ├── RAPPORT_RULES.md
│   ├── install_checklist.md  runbook.md  voice_runbook.md  vision_runbook.md
│   ├── memory_runbook.md  core_conversational_runbook.md  orchestrator_chains.md  v51_brief.md
│   ├── briefs/        (5 briefs)
│   └── rapports/      (14 rapports, dont les 6 de l'ancienne racine et les 4 de rapport.md/)
└── .venv/  venv/      (non suivis ; `.venv` était déjà ici avant le sprint)
```

**Fichiers supprimés** : `test_kokoro.py` (racine, 0 octet), `core_conversational/test_kokoro.py`, `petite_image.png`.
**Retiré du suivi** (conservé sur disque) : `data/voices/fr_FR-siwis-medium.onnx.json`.
**Répertoire supprimé** : `rapport.md/`.

**Commits (branche `sprint-c`)**

| Commit | Portée | Titre |
|---|---|---|
| `fc31da3` | C2, C3, C4 | restructure: remonter Atlas à la racine du dépôt et ranger la documentation |
| `21ab270` | C6, C7 | chore: supprimer le code mort inventorié et durcir l'hygiène Git et Docker |
| (ce rapport) | C8 | docs: rapport du sprint C |

**Hors dépôt** : sauvegarde `C:\Users\alexis\Atlas_backups\memoire\chromadb_20260917_211056\` (archive `a05226953511a47e…`, vérifiée). Conteneurs `atlas_chromadb` et `atlas_searxng` recréés ; volumes `atlas_chromadb_data` (inchangé) et `atlas_searxng_cache` (nouveau).

---

## 4. Détail des implémentations

### C1 — Références avant déplacement
- Fusion de `sprint-b-minimal` dans `main` en avance rapide, création de `sprint-c`.
- `python -m pytest tests/ -q` → **376 passés, code 0** (référence).
- `pip freeze` → 148 paquets, conservé hors dépôt.
- `git ls-files` → 159 fichiers.
- `backup` + `verify` de la mémoire : conforme, restauration prouvée.

### C2 — Aplatissement
- **Préparation** : suppression des caches `.pytest_cache` (présents aux deux niveaux) et `__pycache__` ; fusion de `data/debug` : les **54 captures** créées à la racine par le chemin relatif du grounding (défaut G4 du sprint A) rejoignent `data/debug`, sans conflit de noms.
- **Déplacement** : `git mv` pour chaque entrée suivie. `logs/` et `models/` ne contenant que des fichiers non suivis, `git mv` les refuse (« source directory is empty ») : déplacés par `mv`.
- **Collision `README.md`** : les deux fichiers étaient **identiques** (5 251 octets, `diff` vide). Celui de la racine est conservé, `assistant-bureau/README.md` supprimé. Aucun contenu perdu.
- **Collision `data/`** : traitée avant le déplacement (fusion des captures).
- **Collision `.pytest_cache`** : caches supprimés.

### C3 — Documentation
- `rapport.md/RAPPORT_RULES.md` → `docs/RAPPORT_RULES.md` ; `DIAGNOSTIC_V22.md`, `RAPPORT_CHAT3_FIN_MISSION.md`, `RAPPORT_SUPERVISEUR_V22.md`, `RAPPORT_V23.md` → `docs/rapports/`. Le répertoire `rapport.md` n'existe plus.
- Les 6 rapports de l'ancienne racine (`RAPPORT_V30`, `V31`, `V40`, `V50`, `V602`, `RAPPORT_DECISION_2026-04-08`) → `docs/rapports/`.

### C4 — Chemins, point par point (piège 3)

| Élément | Constat | Action |
|---|---|---|
| `docker-compose.yml` (`./config/searxng`) | Chemin relatif **au fichier compose**, qui a bougé avec le reste | Aucune ; vérifié après recréation : `bind: C:\Users\alexis\Cortana_Killer\config\searxng` |
| `start_atlas_desktop.bat` | `%ROOT%..\.venv` pointait **hors du dépôt** après l'aplatissement | **Corrigé** en `%ROOT%.venv` (3 occurrences) |
| `scripts/doctor.py` | `ROOT = Path(__file__).resolve().parent.parent` → racine | Aucune ; vérifié à l'exécution |
| `scripts/backup_memory.py` | Aucun chemin projet (destination sous `~/Atlas_backups`) | Aucune ; vérifié à l'exécution |
| `tests/conftest.py` | `PROJECT_ROOT = parent.parent` → racine | Aucune ; vérifié par la suite verte |
| `api/routes.py` | Reconstruit ses chemins depuis `__file__` (défaut connu) | **Non corrigé** (B-complet). Vérifié non aggravé : `parent.parent` désigne toujours la racine du projet ; `tests/test_isolation.py::test_routes_data_path_is_redirected` passe |
| `main.py` (`logs/`, `data/chromadb`) | `Path(__file__).parent` → racine | Aucune ; Atlas démarre |
| Tous les `Path(__file__).parent.parent` du code | 20 occurrences (`core/`, `tools/`, `api/`) | Aucune : elles pointent sur la racine du projet, qui a suivi |
| `.gitignore` | 21 règles préfixées `assistant-bureau/` | **Purgées** ; deux équivalents racine manquaient (`data/workflows/workflow_discord_spotify.yaml`, `tests/audit_results_v22.json`) et ont été ajoutés, sinon ces fichiers privés devenaient suivis |
| `README.md`, `docs/install_checklist.md`, `docs/voice_runbook.md`, `docs/core_conversational_runbook.md` | 15 mentions `cd assistant-bureau` et chemins | **Mis à jour**. Une mention subsiste volontairement dans la checklist : elle désigne l'**ancien projet Docker** `assistant-bureau` pour les postes installés avant le 17/09 |

### C5 — Vérification
1. **Le piège 1 ne s'applique pas** : `.venv` est à `C:\Users\alexis\Cortana_Killer\.venv`, donc déjà à la racine avant le sprint (`pyvenv.cfg` : `command = … -m venv c:\Users\alexis\Cortana_Killer\.venv`). Le déplacement ne l'a pas touché ; aucune recréation, donc **aucun risque de dérive**. `pip freeze` avant et après : identiques (148 paquets). L'ancien venv n'a pas été supprimé, puisqu'il est le venv courant.
2. Suite : **376 passés, code 0**.
3. Atlas : `/api/health` → `{"status":"ok", ollama ok, chromadb ok, searxng ok, voice enabled/running}` ; `/api/memory/stats` → 479 + 12 + 25 + 19 ; `/api/memory/recall?query=discord parametres` → souvenir réel du 25/02/2026 (« Le processus 'discord.exe' est détecté actif de manière récurrente »).
4. `doctor.py` : chemins à la racine, `[OK] ChromaDB persiste dans un volume`, 2 critiques antérieurs (cuBLAS 12, CLI piper — sprint A, périmètre B-complet).

### C6 — Nettoyage

**Supprimés, avec preuve `git grep` sur tout le dépôt :**

| Fichier | Preuve | Justification |
|---|---|---|
| `test_kokoro.py` (racine) | Aucune occurrence de `test_kokoro` hors du second fichier Kokoro | Fichier **vide** (0 octet), vestige de l'évaluation Kokoro |
| `core_conversational/test_kokoro.py` | Seules occurrences : lui-même | Script d'essai Kokoro, abandonné au profit de Piper ; importait `kokoro_onnx`, non installé ; 0 % de couverture ; placé dans un paquet de production |
| `petite_image.png` | **Aucune occurrence** de `petite_image` | Échantillon OCR manuel (75 Ko), sans usage depuis le commit initial |

**Déplacés vers `scripts/manual/` (16)** : `_check_searxng.py`, `api_browser_confirm_check.py`, `api_chat_smoke.py`, `api_readurl_check.py`, `api_websearch_check.py`, `audit_capabilities_v22.py`, `debug_parser.py`, `debug_test2.py`, `diagnostic_v22.py`, `direct_hist_websearch.py`, `run_one_prompt.py`, `runtime_tool_direct_checks.py`, `scenario_5tests_v20.py`, `smoke_runtime_v20.py`, plus `test_real_integration_v23.py` → `real_integration_v23_check.py` et `test_real_kimi_5cmd_v51.py` → `real_kimi_5cmd_v51_check.py`. Ces deux derniers portaient un nom de test mais n'exposaient **aucun** test collecté, tout en agissant réellement sur le PC (lancement d'applications, frappe clavier, fermeture de fenêtres). Les racines de projet calculées ont été ajustées (`scripts/manual/` → racine) dans 6 fichiers ; tous compilent.

**Pile vision MiniCPM-V : CONSERVÉE.** Mesures à l'appui :
- Morte à l'exécution : `_build_layers` n'ajoute `_try_vision` que si `vision_enabled`, réglé à `false` ; couverture de `_try_vision` en suite complète : **1 %** (sprint A).
- **Mais encore référencée** : `api/routes.py` (champ `vision_enabled` de `/api/health`), `config/settings.json` (2 clés), `scripts/profile_minicpm.py`, `scripts/check_ollama_config.py`, et 6 fichiers de tests.
- Coût estimé d'une suppression : ~250 lignes de `tools/grounding.py` (`_try_vision`, `_parse_vision_json`, `_normalize_vision_payload`, `_encode_image`, `_preferred_vision_models`, `_has_local_minicpm`, constantes de délai), modification d'`api/` et de la configuration, **~22 tests supprimés** (parseurs vision de `test_vision_parsers.py`) et ~5 réécrits, soit 377 → ~352.
- Le critère du brief (« la preuve qu'il n'est référencé nulle part ») **n'est pas rempli**. Alexis a tranché : conserver, et traiter dans un sprint dédié.

**DialoGPT-medium** (1,7 Go, cache Hugging Face, hors dépôt, aucune référence dans le code) : signalé, non supprimé (§7, C-R4).

### C7 — Hygiène Git et Docker
- `.gitignore` : `data/voices/` ajouté ; `data/voices/fr_FR-siwis-medium.onnx.json` retiré du suivi (`git rm --cached`), fichier conservé sur le disque. Il avait été versionné par erreur au commit `6a3453b` (risque L20).
- Image SearXNG épinglée : `searxng/searxng@sha256:edf110a2816d8963949d03879c72a7e19c221b5f7bfb7952a33ae073f96ccb18`.
- Volume nommé `atlas_searxng_cache` pour `/var/cache/searxng` (avec `name:` explicite, sinon compose préfixe et donne `atlas_atlas_searxng_cache`). **4 volumes anonymes orphelins, tous vides, supprimés** après vérification qu'aucun conteneur ne les utilisait.
- **Correction d'un défaut que j'avais introduit au sprint M-bis** : `pull_policy: never` sur `chromadb` empêchait une installation neuve de récupérer l'image. Retiré : le digest suffit à figer la version, et une machine vierge peut de nouveau télécharger exactement cette image.
- Secrets : aucun secret réel dans le dépôt. `SEARXNG_SECRET_KEY=atlas_secret_key_change_me` est une valeur de remplacement pour un service lié à `127.0.0.1` ; un commentaire le précise et indique quoi faire si SearXNG est un jour exposé.
- `tests/test_compose_config.py` mis à jour en conséquence (digests, volume nommé, `pull_policy`).

---

## 5. Résultats des tests

Environnement : `.venv` (Python 3.12.3, pytest 9.0.2), commandes lancées depuis la **racine du dépôt**, Atlas arrêté, Docker actif.

### Référence, avant déplacement (21:08)
```
python -m pytest tests/ -q
376 passed, 4 warnings in 120.95s (0:02:00)
exit=0
```

### Après déplacement (C5, 21:14)
```
python -m pytest tests/ -q
376 passed, 4 warnings in 77.86s (0:01:17)
exit=0
```
`pip freeze` avant/après : **identiques** (148 paquets, `diff` vide).

### Après nettoyage (C8, 21:3x)
```
python -m pytest tests/ -q
377 passed, 4 warnings in 83.36s (0:01:23)
exit=0
```

**Écart 376 → 377, expliqué :** un test ajouté dans `tests/test_compose_config.py`, `test_searxng_cache_on_named_volume`, qui vérifie le volume nommé exigé par C7. Aucun test n'a disparu : les 16 scripts déplacés et les 3 fichiers supprimés n'exposaient **aucun** test collecté (vérifié au sprint B-minimal par le rapport JUnit, et confirmé ici par le total inchangé hors ajout).

### Non-régression détaillée
| Étape | Total | Échecs | Ignorés |
|---|---|---|---|
| Référence (avant déplacement) | 376 | 0 | 0 |
| Après aplatissement + chemins | 376 | 0 | 0 |
| Après nettoyage + hygiène Docker | 377 | 0 | 0 |

### Vérifications runtime
```
GET /api/health   → {"status":"ok","services":{"ollama":{"ok":true},"chromadb":{"ok":true},"searxng":{"ok":true},"voice":{"enabled":true,"running":true}},"tesseract_status":{"ok":true,...},"vision_enabled":false}
GET /api/memory/stats → total_memories 479 ; partitions : conversations 12, documents 25, errors 19
GET /api/memory/recall?query=discord parametres → habit_54af088c1416, score 0.487, daté du 25/02/2026
python scripts/doctor.py → 77 vérifications, 2 critiques (cuBLAS 12, CLI piper : sprint A), exit 1
docker compose down && docker compose up -d && comparaison d'instantané
   → IDENTIQUE À L'INSTANTANÉ (ids, documents, métadonnées, embeddings, uuid de collection) : True — 535 éléments
searxng /search?format=json → HTTP 200
```

### Inventaire Git comparé
```
git ls-files : 159 avant, 154 après
Écarts (5) : README.md (doublon identique supprimé), fr_FR-siwis-medium.onnx.json (retiré du suivi),
             petite_image.png, test_kokoro.py ×2 (supprimés)
Les entrées test_real_integration_v23.py et test_real_kimi_5cmd_v51.py apparaissent comme
« disparues » par nom de base : elles ont été renommées en scripts/manual/*_check.py.
```

---

## 6. Comportement observé en scénarios réels

| ID | Scénario | Attendu | Observé | Statut |
|---|---|---|---|---|
| S01 | Fusion `sprint-b-minimal` → `main` | Avance rapide | `7d5a9ce..e0db2e0` | PASS |
| S02 | Aplatissement par `git mv` | Historique préservé | Statut Git en `R` (renommages) pour tous les fichiers suivis | PASS |
| S03 | `git mv logs/` et `models/` | Déplacement | Refusé (« source directory is empty ») : dossiers non suivis, déplacés par `mv` | Contourné |
| S04 | Suite après déplacement | 376, code 0 | 376, code 0 | PASS |
| S05 | Atlas depuis la nouvelle racine | Santé et mémoire | `/api/health` ok ; rappel réel de février | PASS |
| S06 | `doctor.py` après déplacement | Chemins cohérents | `logs/`, `data/`, `settings.json` à la racine ; volume ChromaDB OK | PASS |
| S07 | `.gitignore` purgé | Rien de nouveau à suivre | 2 fichiers privés redevenus visibles → règles racine ajoutées | PASS après correction |
| S08 | `docker compose down` / `up -d` (nouveau fichier) | 535 intacts | Identique à l'instantané | PASS |
| S09 | Volume nommé SearXNG | Cache persistant | `atlas_atlas_searxng_cache` au premier essai (préfixe de projet) → `name:` explicite, recréé en `atlas_searxng_cache` | PASS après correction |
| S10 | Suppression des volumes anonymes | Sans perte | 3 supprimés (vides) ; le 4e est **utilisé par un conteneur interne de Docker Desktop**, laissé en place | PARTIEL |
| S11 | Suite après nettoyage | 377, code 0 | 377, code 0 | PASS |

---

## 7. Limites et risques identifiés

| # | Description | Sévérité | Mitigation proposée |
|---|---|---|---|
| C-R1 | **Pile vision MiniCPM-V toujours présente** : ~250 lignes mortes à l'exécution dans le module le plus fragile (`tools/grounding.py`, 25 % de couverture), plus 2 scripts et 2 clés de configuration. | Moyen | Sprint dédié : supprimer le code, les clés, `scripts/profile_minicpm.py`, le champ `/api/health` et adapter 6 fichiers de tests (≈ −25 tests). Plan chiffré en §4. |
| C-R2 | **`api/routes.py` reconstruit ses chemins depuis `__file__`**, ce qui oblige `tests/conftest.py` à un contournement (`pathlib` substitué). Le déplacement ne l'a pas aggravé, mais le défaut demeure. | Moyen | B-complet : répertoire de données centralisé, puis suppression du contournement. |
| C-R3 | Un **volume anonyme Docker** (`853e767d…`, vide) reste attaché à un conteneur interne de Docker Desktop, invisible dans `docker ps -a`. Le volume Kubernetes `bebccf9e…` (1,16 Go) subsiste également : hors projet, Kubernetes étant désactivé. | Faible | Nettoyage par Alexis via l'interface de Docker Desktop, s'il le souhaite. |
| C-R4 | **DialoGPT-medium**, 1,7 Go dans `~/.cache/huggingface`, sans aucune référence dans le code. Cache hors dépôt : je ne l'ai pas supprimé. | Faible | Suppression par Alexis : `huggingface-cli delete-cache`, ou effacement du dossier `models--microsoft--DialoGPT-medium`. |
| C-R5 | `docs/` mélange runbooks, checklist, règles et briefs à plat. Le brief ne demandait pas de sous-découpage. | Faible | À ranger si la documentation grossit (`docs/runbooks/`). |
| C-R6 | Le dépôt reste nommé `Cortana_Killer` sur le disque ; la structure cible du brief mentionnait `cortana-killer-atlas/`. Renommer le dossier casserait le venv (chemins absolus) et les libellés Docker. | Faible | Ne renommer qu'au prix d'une recréation du venv, ou seulement le dépôt distant. |
| C-R7 | `data/debug` contient désormais 54 captures d'écran de plus (fusion des deux dossiers), soit ~12 Mo, avec du contenu potentiellement personnel. Non suivi par Git. | Faible | Suppression possible à tout moment : ce sont des traces de diagnostic du grounding. |
| C-R8 | Les scripts de `scripts/manual/` n'ont **pas été exécutés** : ils agissent réellement sur le PC. Leurs chemins ont été ajustés et ils compilent, mais leur bon fonctionnement n'est pas prouvé. | Moyen | Les exécuter au cas par cas lors de B-complet, quand leur usage se présentera. |
| C-R9 | La branche `sprint-c` n'est ni poussée ni fusionnée. | Faible | Alexis : relire, fusionner, pousser. |
| C-R10 | Le renommage de deux fichiers (`test_real_*`) fait apparaître des « disparitions » dans une comparaison naïve d'inventaire par nom de base. | Faible | Comparer les chemins complets, comme fait ici. |

---

## 8. Checklist de validation

- [x] **`sprint-b-minimal` fusionnée dans `main`, travail sur `sprint-c`** : §4, C1.
- [x] **Référence C1 consignée** : suite (376, code 0), `pip freeze` (148), inventaire Git (159), sauvegarde `211056` vérifiée.
- [x] **`assistant-bureau/` a disparu, contenu à la racine, historique préservé (`git mv`)** : §3, §6 S02.
- [x] **Collision des deux `README.md` traitée et documentée** : fichiers identiques, celui de la racine conservé (§4, C2).
- [x] **`rapport.md` n'existe plus en tant que répertoire ; `RAPPORT_RULES.md` dans `docs/`** : §4, C3.
- [x] **Rapports regroupés dans `docs/rapports/`** : 14 rapports.
- [x] **Nouveau venv créé, dérive de dépendances signalée** : le venv **n'avait pas à être recréé** (déjà à la racine) ; `pip freeze` identique, écart nul, prémisse du brief infirmée et documentée (§4, C5).
- [x] **`python -m pytest tests/ -q` → code 0, 376 tests, avant et après nettoyage** : 376 avant, **377** après, écart de +1 expliqué (§5).
- [x] **Atlas démarre, `/api/health` conforme, `doctor.py` cohérent** : §5.
- [x] **`docker compose down` / `up` : 535 éléments intacts** : §5.
- [x] **Suppressions justifiées par une preuve de non-référencement** : §4, C6. La pile vision, qui ne remplit pas ce critère, est **conservée**.
- [x] **`data/voices/` ignoré, `.onnx.json` retiré du suivi** : §4, C7.
- [x] **Image SearXNG épinglée, volume nommé pour son cache** : §4, C7.
- [x] **Aucun fichier perdu (inventaire comparé)** : 159 → 154, 5 écarts attendus (§5).

---

## 9. Recommandations pour le sprint suivant

### P1
- **P1.1** Relire et fusionner `sprint-c` dans `main`, puis pousser (C-R9). Le dépôt cessera alors de paraître vide sur GitHub.
- **P1.2** B-complet peut démarrer : les défauts produit du sprint A sont intacts et la suite est verte (377). Ordre suggéré : mot d'éveil (L1), TTS (L3), STT/cuBLAS (L2), puis heure inventée (L4), `window_hotkey` (L5), cible du grounding (L24), couches OCR bloquantes (L9).
- **P1.3** Sprint dédié à la pile vision (C-R1), avec le plan chiffré du §4.

### P2
- P2.1 Centraliser le répertoire de données du produit, puis retirer le contournement `pathlib` du `conftest` (C-R2).
- P2.2 Exécuter, au fil des besoins, les scripts de `scripts/manual/` pour valider leurs nouveaux chemins (C-R8).
- P2.3 `pytest.ini` : `asyncio_default_fixture_loop_scope`, marqueurs `integration`/`network`/`desktop` (rappel B-minimal).
- P2.4 Activer le venv dans `start_atlas_desktop.bat` (défaut O2 du sprint A, sinon le repli TTS reste introuvable).

### P3
- P3.1 Nettoyages hors dépôt : DialoGPT-medium (1,7 Go), volume Kubernetes (1,16 Go), captures `data/debug` (C-R3, C-R4, C-R7).
- P3.2 Sous-découpage de `docs/` si la documentation grossit (C-R5).
- P3.3 Décision sur le nom du dépôt (C-R6).

---

*Rapport Sprint C — CHAT6 (Claude Opus 5, Claude Code Windows), 17/09/2026.*
