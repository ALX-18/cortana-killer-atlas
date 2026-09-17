# RAPPORT SPRINT A — État des lieux
Date: 16/09/2026
Agent: Claude Opus 5 (CHAT6, Claude Code Windows)

> Brief : `docs/briefs/BRIEF_SPRINT_A.md`. Règles : `rapport.md/RAPPORT_RULES.md`.
> Poste : Toulouse, Intel i5-10400F, 23,9 Go RAM, NVIDIA RTX 5060 8 151 Mio (pilote 616.92), Windows 11 Pro 10.0.26200.
> Dépôt : `main` @ `875d07b`. **Aucun fichier existant n'a été modifié** (voir section 3).
>
> **Mise à jour 19h30 (même jour)** : Alexis a activé la virtualisation dans le BIOS (redémarrage à 18:59). Les parties dépendantes de Docker ont été rejouées : **passage 4** (section 5), Atlas en environnement complet (section 6, C05 à C07), mesures RAM/VRAM avec Docker (annexe C.2). Au redémarrage, Ollama s'est **mis à jour tout seul en 0.34.1** ; les mesures du passage 4 ne sont donc pas strictement comparables à celles de l'après-midi (0.34.0).

---

## 1. Résumé exécutif

**Statut global : PARTIELLEMENT VALIDÉ.** Les tâches A1 à A7 et A10 sont livrées avec des mesures. A8 est incomplet : R01 exécuté, R02 à R07 non exécutés avec une voix humaine. A9 est incomplet : les rapports de veille sont introuvables depuis ce poste.

**Réponse à la question qui débloque la suite : la suite de tests est ROUGE.**
- `python -m pytest tests/ -q` (commande brute) : **0 test exécuté**, la collecte est interrompue par 2 erreurs.
- Environnement complet (passage 4 : Docker ChromaDB + SearXNG, Ollama natif), avec `--continue-on-collection-errors` : **319 passés / 1 échoué / 2 erreurs de collecte** sur 322 éléments. Code de retour de la commande brute : 2.
- Suites custom (passé deux fois) : `test_architecture_v23` **23/23**, `test_interaction_v22` **10/10**, `validate_v12` **ALL PASS**.
- **Dans l'environnement complet, plus aucun échec ne vient de l'environnement.** Les trois éléments rouges sont des défauts de la suite elle-même :
  - `test_api_clean.py` et `test_stream_fix.py` : des scripts collectés comme des tests ;
  - `test_v53_migration::TestVisionDisabled::test_vision_disabled_returns_skipped` : dépend de l'ordre d'exécution (passe seul, échoue systématiquement dans la suite complète).

**Le vert des tests unitaires masque un produit rouge.** La chaîne vocale est cassée à **trois endroits indépendants**, chacun prouvé sur ce poste (section 6, annexe A) :
1. Le mot d'éveil ne peut **jamais** se déclencher : `_wake_callback` transmet du float32 normalisé alors qu'openWakeWord attend du PCM int16. Avec « Hey Atlas » injecté, score 0,0008 et 0 déclenchement ; contrôle int16, score 0,9951 et 1 déclenchement.
2. Le STT sur GPU plante (`cublas64_12.dll is not found`) : `stt_device=cuda` et aucun CUDA Toolkit sur le poste.
3. Le TTS ne produit **aucun son** avec le venv historique : l'API de piper-tts 1.4.1 est incompatible avec le code, et le repli CLI est cassé.

S'y ajoutent : une heure **inventée** par le LLM (à 17:06, « Il est 14h32 ») et une commande planifiée qui a **tapé** le mot « Fichier » au clavier au lieu de cliquer.

**État runtime (après activation de la virtualisation) :** Atlas démarre en 17 s ; `/api/health` → **`"status":"ok"`** (Ollama, ChromaDB Docker, SearXNG Docker, voix). Pic VRAM de la chaîne complète : **6,5 à 6,7 Go / 8,15 Go**. Pic RAM système : **23,4 / 23,9 Go (98 %)** avec Docker, dont la VM WSL occupe à elle seule 8,3 Go ; 18,7 Go sans Docker. GPU au maximum à **75 °C** après 5 min de charge.

**Deux constats critiques apparus avec Docker :**
- **ChromaDB n'écrit pas dans le volume monté.** L'image persiste dans `/data`, alors que `docker-compose.yml` monte `data/chromadb` sur `/chroma/chroma`, qui reste vide. Toute la mémoire long terme d'Atlas (6 collections, depuis février) ne vit que dans la couche du conteneur : un `docker compose down` ou une mise à jour de l'image la **détruirait**. Une sauvegarde a été faite (`docker cp`), rien n'a été modifié.
- **Le grounding a visé la mauvaise application.** Pour « ouvre le bloc-notes puis clique sur Fichier », il a cherché « bloc-notes » dans la fenêtre Discord au premier plan (une conversation privée) pendant 29 s, au-delà du plafond de 20 s. Aucun clic n'a eu lieu.

---

## 2. Objectifs vs réalisation

| Objectif attendu (brief) | Résultat réel | Statut |
|---|---|---|
| A1 — Confirmer l'état du dépôt côté Windows | `main` = `origin/main` @ `875d07b`, arbre propre, pas d'autre branche, 5 livrables v6.0.2 présents. **Deux divergences** : (1) `2a2389e` n'est **pas un doublon** de `e01949a` : il supprime `core_conversational/test_kokoro_rori.wav` (141 Ko), que `e01949a` avait ajouté, et le blob reste dans l'historique ; (2) le poste **n'est pas vierge** : `.venv` créé le 11/03/2026, modèles Ollama vieux de 3 à 6 mois, `data/` rempli depuis avril. C'est très probablement l'ancien disque avec la nouvelle carte graphique. | PASS (avec divergences signalées) |
| A2 — Installation depuis zéro + `docs/install_checklist.md` | Installation neuve de `requirements.txt` dans un venv vierge (`Cortana_Killer\venv\`) : **OK en 9 min 32 s**, `pip check` propre. Premier essai en **échec** (`LongPathsEnabled=0`, chemin trop long pour torch). Checklist livrée, 14 étapes, avec les pièges rencontrés. Limite : Python, Ollama, Tesseract et Docker étaient **déjà installés** ; leurs installeurs n'ont pas été rejoués. | PARTIEL |
| A2 — Atlas installé et démarrant | `python main.py` démarre : lock, Tesseract 5.5.0, ChromaDB connecté, scheduler, triggers, systray, VoiceEngine, bridge 9999. Après activation de la virtualisation, voie Docker documentée validée : `/api/health` → `"status":"ok"`, tous services verts. | PASS |
| A3 — `scripts/doctor.py` | Livré : 76 vérifications, correction proposée pour chaque échec, détection GPU/VRAM, recommandation de modèle, code de retour 1 si un composant critique manque, mode `--json`. Validé sur 2 venvs × 2 PATH, résultats cohérents avec les mesures. | PASS |
| A4 — Suite complète 270 pytest + 33 custom + validate_v12 | Exécutée **4 fois** (env. trouvé / + Chroma natif / venv neuf / **environnement complet Docker**) + 3 scripts custom (deux fois). La suite compte aujourd'hui **320 tests pytest** collectés, et non 270. Échecs listés nominativement (section 5). **Rouge.** | PASS (tâche) / suite ROUGE |
| A4 — Cas connu `test_voice_v40::test_10_gpu_absent_warning_no_crash` | **PASS sur Windows**, confirmé dans les 3 passages. Bémol : le test simule `torch.cuda` et ne voit pas qu'en réalité torch est une build CPU, d'où un avertissement « aucun GPU » **faux** à chaque démarrage. | PASS |
| A5 — Audit qualité des tests | Livré (annexe A) : couverture par module et par fonction (52 % au total, **grounding 25 %**), tests tautologiques, zones critiques non couvertes, tests fragiles, liste hiérarchisée. Aucun test écrit. | PASS |
| A6 — Inventaire code et architecture | Livré (annexe B) : 6 points du superviseur confirmés ou corrigés, 40 éléments localisés avec criticité, preuve de code mort pour MiniCPM-V, écarts doc/code, dépendances. | PASS |
| A7 — RAM / VRAM / températures | Mesures chiffrées pour les 4 premiers points, sans puis avec Docker (annexe C.1, C.2 ; pic RAM à **98 %** avec Docker). Températures **GPU** mesurées. Température **CPU non mesurée** (WMI refusé sans droits admin ; la zone ACPI lisible est figée à 27,9 °C). Pic VRAM 6,5–6,7 Go : arbitrages proposés, **non appliqués**. | PARTIEL |
| A8 — R01 à R07 avec micro réel | R01 **PASS** (réel). R02 à R07 **non exécutés avec une voix humaine**. Le micro réel a été ouvert (40 min d'écoute par Atlas, 20 min de mesure de faux positifs), et R02, R03, R04 et R05 ont été évalués par injection audio ou pipeline texte : **tous FAIL prédits et prouvés** (section 6). | PARTIEL |
| A8 — Taux de faux positifs `hey_atlas` | Code actuel : 0 sur 40 min, **par construction** (le détecteur ne peut rien détecter). Détecteur correctement alimenté en int16 : **0 déclenchement sur 20 min** de micro réel (score max 0,0172). L'activité réelle de la pièce pendant ces 20 min n'est pas connue. | PARTIEL |
| A9 — Revue des rapports de veille | **Rapports introuvables** : disque, Gmail, Notion (seule mention : « une veille automatisée tourne chaque samedi »), tâches planifiées locales, routines cloud Claude Code (liste vide). Substitut fourni : relevé des versions obsolètes (annexe D), rien appliqué. | FAIL (substitut fourni) |
| A10 — Rapport RAPPORT_RULES, 9 sections, réponse vert/rouge | Ce document. Réponse : **rouge**. | PASS |

---

## 3. Architecture projet mise à jour

Fichiers créés (versionnables) :

```
assistant-bureau/
├── scripts/
│   └── doctor.py                    ← NOUVEAU Sprint A
└── docs/
    ├── install_checklist.md         ← NOUVEAU Sprint A
    └── rapports/
        └── RAPPORT_SPRINT_A.md      ← NOUVEAU Sprint A
```

Fichiers et répertoires runtime créés, **non versionnés** (couverts par `.gitignore`, sauf mention) :

```
assistant-bureau/
├── models/wakewords/hey_atlas.onnx            ← R01 (205 430 o, sha256 ea196d0e…)
└── data/voices/
    ├── fr_FR-siwis-medium.onnx                ← R01 (63 201 294 o, sha256 641d1ab0…)
    └── fr_FR-siwis-medium.onnx.json           ← R01 (4 875 o) — ⚠ NON couvert par .gitignore (apparaît dans git status)
Cortana_Killer/venv/                           ← venv d'installation neuve A2 (ignoré par .gitignore:14 « venv/ »), à supprimer ou conserver selon décision
```

Fichiers **existants** modifiés : **aucun fichier de code, de configuration ou de test.**
Fichiers de **données runtime** modifiés comme effet de bord des tests et mesures (non versionnés) :
- `data/atlas_actions.jsonl` : +101 lignes (466 → 567), écrites par les tests (orchestration, workflow `mode_gaming` mocké, web_search) et par la mesure A7 ;
- `data/audit_log.jsonl` : +1 ligne (`validate_v12`, « Get-Process TEST ») ;
- `data/habits.db` : écrite puis nettoyée par `test_habit_persistence` et `validate_v12` ;
- `data/schedules.json` et `data/triggers.json` : **identiques** avant et après (vérifié par `diff` avec la sauvegarde de début de sprint).

Environnement modifié : conteneur Docker `assistant_ollama` **arrêté** (`docker stop`, réversible par `docker start assistant_ollama`) ; `atlas_searxng` et `assistant_chromadb` laissés actifs. Le venv neuf a reçu `pytest`, `pytest-asyncio` et `pytest-cov`. Le `.venv` historique n'a **reçu aucune installation**. Les modèles de support OpenWakeWord ont été téléchargés dans le venv neuf. Le fichier `.coverage` généré a été supprimé.

---

## 4. Détail des implémentations (par fichier)

### `scripts/doctor.py` (nouveau)
**Rôle :** diagnostic d'installation en lecture seule. Il ne modifie ni la configuration, ni les données, ni l'environnement. Crédit en en-tête : approche inspirée de `sosoj92/jarvis-assistant-vocal` (MIT), réécrite pour Atlas sans code repris.

**Fonctions :**
- `check_python()` : Python 3.12 exigé (critique) ; venv actif (avertissement).
- `check_project_layout()` : `settings.json` lisible, sections attendues, **dossier `logs/` présent** (critique : `main.py` plante à l'import sans lui).
- `check_packages()` : 36 paquets, installation **et** import réel (détecte les DLL manquantes). Sévérité ajustée selon `voice.enabled`. Signale `easyocr` et `pytest`, absents de `requirements.txt`.
- `check_tesseract()` : binaire dans le PATH (ou présent mais hors PATH), version, langues `fra` et `eng`, et **`pytesseract.get_tesseract_version()`** (ce que Python voit réellement, parade à l'épisode v5.2).
- `check_easyocr_models()` : cache `~/.EasyOCR/model`.
- `check_ollama()` : binaire, serveur, présence du **modèle configuré** ; avertit du conflit de port avec le service `ollama` de `docker-compose.yml`.
- `check_memory_and_web()` : heartbeat ChromaDB (host/port de la config) ; SearXNG `/healthz`, sévérité selon la disponibilité du repli `ddgs`.
- `check_playwright()` : présence de l'exécutable Chromium attendu par la version installée.
- `check_virtualization()` : `VirtualizationFirmwareEnabled`, CLI et moteur Docker.
- `detect_gpu()` : `nvidia-smi` (nom, VRAM totale/utilisée/libre, pilote, température), torch CUDA ou CPU, CTranslate2, **chargement réel de `cublas64_12.dll`** (critique si `stt_device=cuda` et voix active), providers onnxruntime.
- `recommend()` : paliers de VRAM → LLM, taille whisper et périphérique STT (8 Go → `qwen2.5:7b` + whisper `base` sur cuda). Estimation du pic comparée à la VRAM disponible, qui réintègre les modèles déjà chargés (`/api/ps`). Les arbitrages sont listés, jamais appliqués.
- `check_voice()` : modèle de mot d'éveil, voix Piper (`.onnx` + `.json`), modèles de support OpenWakeWord **dans le venv courant**, **CLI `piper` exécutable** (repli TTS), cache du modèle whisper, micro et sortie par défaut.
- `render()` / `main()` : rendu par section avec `[OK]`, `[ECHEC]`, `[ATTENTION]` et une ligne « Correction » ; `--json` pour un futur installeur ; code de retour 1 si un critique échoue.

**Intégration :** script autonome, lancé depuis `assistant-bureau/`. Réutilise uniquement `config/settings.json`. N'importe aucun module d'Atlas, ce qui lui permet de fonctionner même si les dépendances d'Atlas sont cassées.

**Validation effectuée :**

| Venv | PATH venv | Code | Critiques signalés | Conforme à la réalité mesurée ? |
|---|---|---|---|---|
| `.venv` (historique) | non | 1 | cuBLAS 12, CLI piper | Oui : STT cuda plante, aucun son |
| `.venv` | oui | 1 | cuBLAS 12, CLI piper | Oui : le CLI piper 1.4.1 plante (`pathvalidate`) |
| `venv` (neuf) | non | 1 | cuBLAS 12, CLI piper | Oui : pas de son sans activation |
| `venv` | oui | 1 | cuBLAS 12 | Oui : son produit (6,2 s), STT cuda plante |
| `venv`, avant `download_voice_models` | non | 1 | modèles de support OWW | Oui : stockés dans le venv |

### `docs/install_checklist.md` (nouveau)
Procédure cochable en 14 étapes : matériel et système, Git, Python 3.12, venv, dépendances, Tesseract, EasyOCR, Ollama, ChromaDB (Docker ou natif), recherche web, `settings.json`, modèles voix, dossiers runtime, premier lancement, tests. Chaque étape a une commande de vérification. Les **10 pièges constatés** sur ce poste sont marqués « ⚠ Vu sur le terrain » : chemins longs, virtualisation, plusieurs Python, venv non activé, paquets non déclarés, Playwright, cuBLAS, piper, dossier `logs/`, scripts de test à effets de bord. Deux commandes sont signalées comme non testées telles quelles.

### Hors périmètre / scope caché
Rien d'ajouté au produit. Outils **jetables** utilisés pour les mesures, conservés hors dépôt dans le répertoire temporaire de session : échantillonneur A7, script de chaîne A7, sonde de faux positifs, bancs d'injection audio. Ils n'importent le code d'Atlas qu'en lecture ; deux bancs remplacent des fonctions **en mémoire** (`sd.InputStream`, `_on_wake_word`, `_wake_detected`, `sd.play`) pour les besoins de la preuve. Aucun fichier du dépôt n'a été touché.

---

## 5. Résultats des tests

Environnement : Windows 11, `C:\Users\alexis\Cortana_Killer\.venv` (Python 3.12.3, pytest 9.0.2, pytest-asyncio 1.3.0) sauf mention, depuis `assistant-bureau/`, avec `PYTHONIOENCODING=utf-8`. Ollama 0.34.0 actif dans tous les passages.

### Passage 0 — commande brute
```
python -m pytest tests/ -q
```
```
ERROR tests/test_api_clean.py - requests.exceptions.ConnectionError: HTTPConn...
ERROR tests/test_stream_fix.py - requests.exceptions.ConnectionError: HTTPCon...
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
2 errors in 23.37s
```
**0 test exécuté.** `tests/test_api_clean.py` et `tests/test_stream_fix.py` ne sont pas des tests : ce sont des scripts qui envoient des requêtes à `localhost:8550` **au moment de l'import**. Si Atlas tourne, ils lui envoient de vraies commandes (« ouvre steam », « Cherche Python sur internet »). La collecte importe aussi `test_cleanup.py` (appelle `process_ai_response` avec un `launch_app steam` ; Steam **ne s'est pas lancé**, constaté) et `test_habit_persistence.py` (écrit dans le vrai `data/habits.db`, puis nettoie).

### Passage 1 — environnement tel que trouvé (Docker arrêté, pas de ChromaDB, pas de SearXNG)
```
python -m pytest tests/ -q -rfEs --continue-on-collection-errors --durations=20 --junitxml=run1.xml -p no:cacheprovider
```
```
FAILED tests/test_chroma_integration.py::TestChromaIntegration::test_02_heartbeat_http
FAILED tests/test_v53_migration.py::TestVisionDisabled::test_vision_disabled_returns_skipped
FAILED tests/test_web_v20.py::test_01_searxng_heartbeat_under_3s[asyncio] - h...
ERROR tests/test_api_clean.py - requests.exceptions.ConnectionError: HTTPConn...
ERROR tests/test_stream_fix.py - requests.exceptions.ConnectionError: HTTPCon...
ERROR tests/test_chroma_integration.py::TestChromaIntegration::test_01_heartbeat
ERROR tests/test_chroma_integration.py::TestChromaIntegration::test_03_create_collection
ERROR tests/test_chroma_integration.py::TestChromaIntegration::test_04_insert_and_query
ERROR tests/test_chroma_integration.py::TestChromaIntegration::test_05_cleanup_collection
SKIPPED [8] tests\test_memory_v60.py:186..255: ChromaDB (Docker) non disponible
3 failed, 305 passed, 8 skipped, 4 warnings, 6 errors in 116.04s (0:01:56)
```

### Passage 2 — ChromaDB natif (`chroma run --port 8001`), SearXNG toujours absent
Même commande (`--junitxml=run2.xml`).
```
FAILED tests/test_v53_migration.py::TestVisionDisabled::test_vision_disabled_returns_skipped
FAILED tests/test_web_v20.py::test_01_searxng_heartbeat_under_3s[asyncio] - h...
ERROR tests/test_api_clean.py - requests.exceptions.ConnectionError: HTTPConn...
ERROR tests/test_stream_fix.py - requests.exceptions.ConnectionError: HTTPCon...
2 failed, 318 passed, 4 warnings, 2 errors in 97.41s (0:01:37)
```

### Passage 3 — venv **neuf** (`Cortana_Killer\venv`, `requirements.txt` + pytest, pytest-asyncio, pytest-cov), ChromaDB natif
```
..\venv\Scripts\python.exe -m pytest tests/ -q -rfEs --continue-on-collection-errors -p no:cacheprovider --cov=core --cov=tools --cov=api --cov=core_conversational --cov-report=term --junitxml=run3.xml
```
```
FAILED tests/test_v53_migration.py::TestVisionDisabled::test_vision_disabled_returns_skipped
FAILED tests/test_web_v20.py::test_01_searxng_heartbeat_under_3s[asyncio] - h...
FAILED tests/test_web_v20.py::test_06_browser_open_and_get_current_url[asyncio]
ERROR tests/test_api_clean.py - requests.exceptions.ConnectionError: HTTPConn...
ERROR tests/test_stream_fix.py - requests.exceptions.ConnectionError: HTTPCon...
3 failed, 317 passed, 1 warning, 2 errors in 142.07s (0:02:22)
TOTAL                                    6538   3124    52%
```

### Passage 4 — environnement complet (après activation de la virtualisation, 19:15)
Docker Desktop 29.8.0 : `assistant_chromadb` (API v2, 1.0.0) et `atlas_searxng` actifs ; conteneur `assistant_ollama` **arrêté** (conflit, voir L22) ; Ollama natif **0.34.1** ; `.venv` historique ; Atlas arrêté.
```
python -m pytest tests/ -q -p no:cacheprovider
```
```
ERROR tests/test_api_clean.py - requests.exceptions.ConnectionError: HTTPConn...
ERROR tests/test_stream_fix.py - requests.exceptions.ConnectionError: HTTPCon...
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
2 errors in 17.73s
exit=2
```
```
python -m pytest tests/ -q -rfEs --continue-on-collection-errors --durations=20 --junitxml=run4.xml -p no:cacheprovider
```
```
FAILED tests/test_v53_migration.py::TestVisionDisabled::test_vision_disabled_returns_skipped
ERROR tests/test_api_clean.py - requests.exceptions.ConnectionError: HTTPConn...
ERROR tests/test_stream_fix.py - requests.exceptions.ConnectionError: HTTPCon...
1 failed, 319 passed, 4 warnings, 2 errors in 101.71s (0:01:41)
exit=1
```
`test_web_v20::test_01_searxng_heartbeat_under_3s` **passe** (SearXNG actif) et `test_chroma_integration` passe **5/5** contre le vrai ChromaDB Docker. Les 6 collections Atlas sont intactes après la suite (vérifié ; sauvegarde `docker cp` faite avant).

### Échecs et erreurs, nominativement

| Test | Passages | Cause exacte | Nature |
|---|---|---|---|
| `test_api_clean.py` (collecte) | 0 à 4 | Script, pas un test : `requests.post("http://localhost:8550/api/chat")` à l'import → `ConnectionError` (WinError 10061) | **Défaut de la suite** |
| `test_stream_fix.py` (collecte) | 0 à 4 | Idem, sur `/api/chat/stream` | **Défaut de la suite** |
| `test_v53_migration.py::TestVisionDisabled::test_vision_disabled_returns_skipped` | 1 à 4 | `asyncio.get_event_loop()` → `RuntimeError: There is no current event loop in thread 'MainThread'` (pytest-asyncio 1.3 a déjà positionné puis retiré une boucle). **Passe seul** (`1 passed`) et dans son fichier (`17 passed`). | **Test dépendant de l'ordre** : vrai défaut |
| `test_web_v20.py::test_01_searxng_heartbeat_under_3s` | 1, 2, 3 (**PASS au 4**) | `httpx.ConnectError: All connection attempts failed` sur `localhost:8888` : SearXNG non démarré, Docker bloqué (virtualisation BIOS désactivée, `HCS_E_HYPERV_NOT_INSTALLED`) | Environnement, résolu par l'activation de la virtualisation |
| `test_chroma_integration.py` test_01 (erreur), test_02 (échec), test_03, test_04, test_05 (erreurs) | 1 | `ValueError: Could not connect to a Chroma server` / `httpx.ConnectError` sur `localhost:8001` | Environnement ; **5/5 PASS** en passages 2 et 3 |
| `test_memory_v60.py` (8 tests) | 1 (ignorés) | « ChromaDB (Docker) non disponible » | Environnement ; **33/33 PASS** en passages 2 et 3 |
| `test_web_v20.py::test_06_browser_open_and_get_current_url` | 3 | `BrowserType.launch: Executable doesn't exist at ...\ms-playwright\chromium-1243\chrome-win64\chrome.exe` : playwright 1.63 (venv neuf) attend Chromium 1243, seul le 1208 est installé | Étape d'installation manquante (checklist §4) |

### Non-régression par suite (résultats JUnit)

| Fichier | Passage 1 (env. trouvé) | Passage 2 (+Chroma natif) | Passage 3 (venv neuf) | Passage 4 (env. complet) |
|---|---|---|---|---|
| `test_app_resolver_v51` | 5/5 | 5/5 | 5/5 | 5/5 |
| `test_automation_v30` | 15/15 | 15/15 | 15/15 | 15/15 |
| `test_chroma_integration` | 0/5 (1 échec, 4 erreurs) | 5/5 | 5/5 | 5/5 |
| `test_core_conversational` | 15/15 | 15/15 | 15/15 | 15/15 |
| `test_file_indexer_v51` | 2/2 | 2/2 | 2/2 | 2/2 |
| `test_file_organizer_v51` | 3/3 | 3/3 | 3/3 | 3/3 |
| `test_final_v50` | 10/10 | 10/10 | 10/10 | 10/10 |
| `test_identity_v60` | 8/8 | 8/8 | 8/8 | 8/8 |
| `test_interaction_v22` | 10/10 | 10/10 | 10/10 | 10/10 |
| `test_memory_v60` | 25/33 (8 ignorés) | 33/33 | 33/33 | 33/33 |
| `test_metrics_grounding_v52` | 7/7 | 7/7 | 7/7 | 7/7 |
| `test_orchestrator_v60` | 14/14 | 14/14 | 14/14 | 14/14 |
| `test_real_e2e_kimi_v51` | 2/2 | 2/2 | 2/2 | 2/2 |
| `test_redo_heuristics_v52` | 22/22 | 22/22 | 22/22 | 22/22 |
| `test_sprint_kimi_understanding_v51` | 14/14 | 14/14 | 14/14 | 14/14 |
| `test_stabilisation_v31` | 5/5 | 5/5 | 5/5 | 5/5 |
| `test_v53_migration` | 16/17 (1 échec) | 16/17 (1 échec) | 16/17 (1 échec) | 16/17 (1 échec) |
| `test_v601_patches` | 25/25 | 25/25 | 25/25 | 25/25 |
| `test_vision_parsers` | 45/45 | 45/45 | 45/45 | 45/45 |
| `test_vision_v60` | 24/24 | 24/24 | 24/24 | 24/24 |
| `test_voice_v40` | 12/12 (**test_10 PASS**) | 12/12 | 12/12 | 12/12 |
| `test_voice_v602` | 17/17 | 17/17 | 17/17 | 17/17 |
| `test_web_v20` | 9/10 (1 échec) | 9/10 (1 échec) | 8/10 (2 échecs) | 10/10 |
| erreurs de collecte (2 scripts) | 2 | 2 | 2 | 2 |
| **Total** | **305 P / 3 F / 8 S / 6 E** | **318 P / 2 F / 2 E** | **317 P / 3 F / 2 E** | **319 P / 1 F / 2 E** |

Les modules `test_cleanup.py`, `test_habit_persistence.py`, `test_architecture_v23.py`, `test_real_integration_v23.py` et `test_real_kimi_5cmd_v51.py` sont importés par pytest, mais ne contiennent **aucun** test collecté.

### Suites custom (scripts), `.venv`, Atlas arrêté — identiques à 16h et au passage 4 (19h15)
```
python tests/test_architecture_v23.py   → exit=0 — « RÉSULTAT : 23/23 (100%) »
python tests/test_interaction_v22.py    → exit=0 — « Résultat : 10/10 tests passés »
python tests/validate_v12.py            → exit=0 — « === ALL TESTS PASSED === » (Lifespan version=4.0.0)
```
Note : les « 33 custom » valent 23 + 10. Les 10 de `test_interaction_v22.py` sont **aussi** comptés par pytest, ce qui fait un double comptage dans l'objectif « 270 + 33 ». `test_interaction_v22` test 3 dépend de la fenêtre active (il a lu « Settings - Docker Desktop »).

### Vérifications isolées complémentaires
```
python -m pytest "tests/test_v53_migration.py::TestVisionDisabled::test_vision_disabled_returns_skipped" -q -p no:cacheprovider → 1 passed
python -m pytest tests/test_v53_migration.py -q -p no:cacheprovider → 17 passed
```

### Verdict
**Suite ROUGE**, pour deux raisons : (a) la commande standard n'exécute aucun test (code 2) ; (b) dans l'environnement complet, il reste un échec dû à un vrai défaut de test (dépendance à l'ordre). **Aucun échec restant n'est dû à l'environnement.** Aucune régression ne peut être attribuée à ce sprint : aucun fichier existant n'a été modifié.

---

## 6. Comportement observé en scénarios utilisateur réels

### Scénarios du brief

| ID | Commande utilisateur | Résultat attendu | Résultat observé | Statut |
|---|---|---|---|---|
| R01 | `python scripts/download_voice_models.py` (×2) | 3 téléchargements OK, idempotence | 1er lancement 16:06:01 → 16:06:10, exit 0 : OWW OK, `hey_atlas.onnx` 205 430 o, `fr_FR-siwis-medium.onnx` 63 201 294 o + `.json` 4 875 o. 2e lancement : trois `[SKIP] ... deja present`, exit 0. Venv neuf : OWW téléchargé, les deux autres en SKIP. | **PASS** |
| R02 | Dire « Atlas » | Systray idle → listening | **Non exécuté avec une voix humaine.** Atlas a écouté le vrai micro (« Microphone (GAMING HEADSETS) », niveau ambiant moyen 403–455) de 16:25 à 17:05 : **aucune** détection. Preuve de cause : le vrai `VoiceEngine` alimenté par un WAV « Hey Atlas » (voix SAPI Zira en-US, 16 kHz) déclenche **0 fois** ; score du modèle en float32/32768 (code Atlas) = **0,0008**, en int16 = **0,9951**. Contrôle, même banc avec entrée int16 : **1 déclenchement**. Le mot d'éveil ne peut pas fonctionner, quel que soit le micro. Le modèle est entraîné sur « **Hey** Atlas », pas sur « Atlas ». | **FAIL (prouvé, voix humaine non testée)** |
| R03 | « Quelle heure il est » | Transcription correcte + réponse vocale | Non exécuté vocalement (bloqué par R02). Éléments réels : (a) STT `cuda` → `RuntimeError: Library cublas64_12.dll is not found or cannot be loaded` ; (b) pipeline texte de la voix (`_run_text_pipeline`) à **17:06:35** → « **Il est 14h32.** » (heure fausse, inventée par le LLM ; 14,6 s à froid, 1,8 s à chaud) ; (c) TTS `.venv` → « TTS unavailable », aucun son. | **FAIL (prédit, 3 causes prouvées)** |
| R04 | « Ferme cette fenêtre » | Intention exécutée + confirmation vocale | Non exécuté (risque de fermer une fenêtre réelle). Résolution à blanc, avec et sans contexte réel : `window_mgmt/close`, cible **« cette »** → `window_close {'title': 'cette'}`, `confirmation_required=True`. Le pronom n'est pas résolu et la voix n'a aucun moyen de confirmer. | **FAIL (prédit)** |
| R05 | « Comment tu vas » | Réponse conversationnelle vocale | Pipeline texte : « Je vais bien, merci ! Et toi, comment vas-tu ? » (2,0 s). Réponse correcte, mais **muette** (TTS) et inaccessible (R02). | **FAIL (partie texte OK)** |
| R06 | 5 commandes d'affilée | Aucun crash, retour idle | Non exécuté (R02 impossible). Atlas est resté 40 min en écoute sans crash. | **NON EXÉCUTÉ** |
| R07 | Latence mot d'éveil → premier son | Valeur mesurée | Non mesurable (R02 et TTS). Composantes mesurées : STT GPU (avec contournement) 10,8 s à froid / 0,16 s à chaud ; STT CPU ~5,3 s pour 3 s ; pipeline planifié 33,7 s ; LLM à chaud < 1 s ; TTS avec son (venv neuf activé) 6,2 s par phrase. | **NON MESURÉ** |

### Faux positifs `hey_atlas`
| Condition | Durée | Déclenchements (seuil 0,5) | Score max |
|---|---|---|---|
| Atlas réel (code actuel) | 40 min (16:25–17:05) | 0, **par construction** (entrée float) | n/a |
| Sonde int16, même micro | 20 min (16:44:50–17:04:50), 15 000 trames | **0** | 0,0172 (p99,9 = 0,0028) |

Ambiance : niveau moyen 403, p95 2 049, max 5 663 ; **17,7 % des trames au-dessus de 500**, le seuil de parole de `_record_audio_sync`. L'activité réelle de la pièce (conversation, musique) n'est pas connue : ce n'est pas une mesure « usage normal » garantie.

### Scénarios réels supplémentaires (chaîne A7, code Atlas via `VoiceEngine`, entrée audio synthétique)

| ID | Commande | Attendu | Observé | Statut |
|---|---|---|---|---|
| C01 | Audio « ouvre le bloc-notes puis clique sur Fichier » (Piper siwis → 16 kHz) → STT | Transcription fidèle | « Ouvrez le **Black Note** puis clique sur Fichier. » (whisper base) | FAIL |
| C02 | Pipeline planifié sur cette transcription | Bloc-notes ouvert une fois, clic sur « Fichier » via le grounding | `launch_app` exécuté, **vérification échouée**, 2 nouvelles tentatives : **3 Bloc-notes lancés** (16:33:21 / 23 / 25). Puis `window_hotkey {'keys': 'Fichier'}` : **les lettres F-i-c-h-i-e-r ont été tapées** dans le Bloc-notes (titre « *Fichier - Bloc-notes »). Grounding jamais appelé. Réponse : « 'bloc notes' lancé avec succès. ; Raccourci 'F+i+c+h+i+e+r' envoyé. » | FAIL |
| C03 | Premier appel LLM après démarrage | Réponse rapide | 80,5 s (dont 40 s de watchdog de détection GPU Ollama et 40 s de chargement) ; au second essai à froid, 14,6 s | Observation |
| C04 | `/api/health` Atlas en marche | État fidèle | `"voice": {"enabled": true, "running": true}` alors que la voix ne peut pas se déclencher | FAIL (observabilité) |

| C05 | Même chaîne, **environnement complet** (Docker, Ollama 0.34.1), 19:21 | Idem C02 | STT **correct** (« Ouvre le bloc note puis clique sur fichier. », 15,8 s à froid / 0,19 s à chaud). `launch_app` : **à nouveau 3 lancements** (19:21:53 / 55 / 57), vérification échouée. Puis `ui_click_element` : **« Recherche 'bloc-notes' dans '… - Discord' (type=electron) »**, la cible étant la fenêtre Discord au premier plan (conversation privée). Grounding de 19:22:15,7 à 19:22:44,7, soit **29 s pour un plafond de 20 s** (couches bloquantes, L9) ; abandon, **aucun clic**. Réponse : « 'bloc notes' lancé avec succès. ; Recherche visuelle trop lente — timeout 20s. » Pipeline : 67,2 s. | FAIL |
| C06 | `/api/health`, environnement complet | Tous services OK | `{"status":"ok", ollama ok, chromadb ok, searxng ok, voice running}` (toujours trompeur pour la voix) | PASS (réserve C04) |
| C07 | `POST /api/chat` « Comment tu vas ? », premier appel après démarrage | Réponse conversationnelle | 46 s à froid. « Je vais bien, merci ! Comment allez-vous ? Est-ce que vous avez besoin d'aide pour ajuster vos paramètres Discord ou pour autre chose ? » La mémoire long terme réelle est bien branchée, mais un souvenir ancien et hors sujet contamine la réponse. | PARTIEL |

Les Bloc-notes ouverts par C02 et C05 (3 + 3) ont été fermés ; leur seul contenu était le texte tapé par le test (C02) ou vide (C05).

---

## 7. Limites et risques identifiés

| # | Description | Sévérité | Mitigation proposée |
|---|---|---|---|
| L1 | **Mot d'éveil inopérant** : `core/voice_engine.py` `_wake_callback` convertit en float32/32768 ; openWakeWord attend de l'int16 (preuve section 6). | Élevé | Sprint B : passer l'int16 brut à `predict` ; test d'intégration avec un WAV réel. |
| L2 | **STT GPU inopérant** : `cublas64_12.dll` absent (pas de CUDA Toolkit ; CTranslate2 ne l'embarque pas). | Élevé | Sprint B : arbitrage cuBLAS (Toolkit / `nvidia-cublas-cu12`) ou `stt_device=cpu`. Détecté par `doctor.py`. |
| L3 | **TTS muet** : piper-tts ≥ 1.3 renvoie un générateur (API incompatible), l'exception est avalée, et le repli CLI exige `pathvalidate` (absent en 1.4.1) **et** un venv activé (absent de `start_atlas_desktop.bat`). | Élevé | Sprint B : adapter `_speak_sync` à l'API `AudioChunk`, épingler piper-tts, journaliser l'échec. |
| L4 | **Heure inventée** par le LLM (« Il est 14h32 » à 17:06). | Élevé | Sprint B : réponse déterministe pour l'heure et la date (outil) ou contexte horaire injecté. |
| L5 | **`window_hotkey` décompose une chaîne en caractères** (`*args.get("keys")`) : le planificateur peut faire taper du texte dans la fenêtre au premier plan. | Élevé | Sprint B : valider `keys` (liste de touches connues) dans le validateur. |
| L6 | **Relance non idempotente de `launch_app`** : 3 lancements, succès annoncé malgré l'échec de vérification. | Moyen | Sprint B : vérification tolérante au titre de fenêtre, pas de relance si le processus existe. |
| L7 | **Suite rouge** : 2 scripts à effets de bord collectés + 1 test dépendant de l'ordre. | Élevé (bloque C) | Sprint B minimal : exclure ou déplacer les scripts (`collect_ignore`), corriger le test (`asyncio.run`). |
| L8 | ~~Docker inutilisable (virtualisation désactivée dans le BIOS)~~ **Résolu à 18:59** par Alexis. Passage 4 et mesures rejoués. | — | Checklist : `VirtualizationFirmwareEnabled` vaut `False` dès que l'hyperviseur tourne ; `doctor.py` vérifie aussi `HypervisorPresent`. |
| L9 | **Couches OCR bloquantes** : `_try_ocr` et `_try_easyocr` sont synchrones, les délais de `wait_for` ne s'appliquent pas (8 s réels pour un délai de 3 s, enregistré « failure » au lieu de « timeout » ; **29 s réels pour un plafond global de 20 s** en C05), et toute la boucle (API, voix) est gelée. | Élevé | Sprint B : `asyncio.to_thread` ; le test actuel (`asyncio.sleep`) ne le détecte pas. |
| L10 | **Démarrage à froid LLM jusqu'à 80 s** (watchdog GPU Ollama 0.34.0 + chargement sans mmap), proche de `stream_timeout_seconds=90`. | Moyen | Préchargement au démarrage d'Atlas ; suivre Ollama 0.34.1 (annexe D). |
| L11 | **torch en build CPU** : EasyOCR 22 s sur CPU, faux avertissement « aucun GPU ». Passer en CUDA ajouterait ~1 Go de VRAM au pic. | Moyen | Arbitrage superviseur (annexe C). |
| L12 | **`requirements.txt` non figé** : dérive constatée entre venvs (piper 1.4.1 → 1.8.0, torch 2.12.1 → 2.14.0, onnxruntime 1.24.3 → 1.30.0). `easyocr`, `pypdf` et `pytest` ne sont pas déclarés. | Moyen | Sprint B/C : fichier de verrouillage. |
| L13 | **Tests à effets de bord sur les données réelles** (`atlas_actions.jsonl` +101 lignes, `audit_log`, `habits.db`) : ils faussent `/api/metrics`. | Moyen | Sprint B : `tmp_path` / variable d'environnement pour `data/`. |
| L14 | R02 à R07 **non exécutés avec une voix humaine** ; taux de faux positifs mesuré sans maîtrise de l'ambiance. | Élevé (critère non rempli) | À refaire après correction de L1 à L3 (protocole section 9). |
| L15 | **Température CPU non mesurée** (WMI refusé sans admin, zone ACPI figée). | Faible | Relevé avec HWiNFO ou LibreHardwareMonitor, lancés par Alexis. |
| L16 | Échantillonnage A7 effectif d'environ **3,5 s** (et non 1 s) : des pics brefs peuvent avoir été manqués. Chaîne mesurée dans un processus de mesure séparé, pas dans le processus Atlas. | Faible | Refaire avec `nvidia-smi dmon` si l'arbitrage VRAM se joue à < 300 Mio. |
| L17 | Arrêt d'Atlas forcé (TaskStop) : **arrêt propre non vérifié**. | Faible | Vérifier Ctrl+C / « Quitter » du systray en sprint B. |
| L18 | Rapports de veille **introuvables** : A9 non réalisé sur sa source. | Moyen | Superviseur : indiquer l'emplacement des rapports du samedi. |
| L19 | Installeurs de Python, Ollama, Tesseract et Docker **non rejoués** (déjà présents) : la checklist est vérifiée sur un poste préinstallé, pas sur un Windows vierge. | Moyen | Validation sur une VM ou un second poste (nécessite la virtualisation). |
| L20 | `data/voices/*.onnx.json` non couvert par `.gitignore` : risque de commit accidentel. | Faible | Sprint C : ajouter `data/voices/` au `.gitignore`. |
| L21 | **Mémoire long terme non persistée sur l'hôte** : l'image `chromadb/chroma` écrit dans `/data` (`persist_path: "/data"`), le volume est monté sur `/chroma/chroma` (vide), et `data/chromadb` est vide côté Windows. `docker compose down`, une mise à jour d'image ou une suppression du conteneur = **perte de toute la mémoire**. | **Élevé** | Immédiat : ne pas supprimer ni recréer `assistant_chromadb`. Sauvegarde sprint A : `docker cp assistant_chromadb:/data` (7,6 Mo, hors dépôt). Sprint B : monter le volume sur `/data` (ou `persist_path`) après copie. Détecté par `doctor.py`. |
| L22 | **Deux Ollama sur le port 11434** : `docker-compose.yml` démarre `assistant_ollama` (0.17.0, redémarrage automatique) sur `[::]:11434`, l'Ollama natif écoute sur `127.0.0.1:11434`. `localhost:11434` répondait **0.17.0** (le conteneur, qui n'a que `mistral`). Atlas utilise `127.0.0.1`, donc le natif, mais tout client qui résout `localhost` en IPv6 part vers le conteneur. | Moyen | Conteneur arrêté pour ce sprint (`docker stop assistant_ollama`, réversible). Sprint B/C : retirer le service de `docker-compose.yml` ou le placer derrière un profil. |
| L23 | **Saturation RAM avec Docker** : VM WSL 8,3 Go ; RAM système **23,4 / 23,9 Go** au pic de la chaîne (18,7 Go sans Docker). Au-delà, le système paginera. | **Élevé** | Arbitrage superviseur : limiter la VM WSL (`.wslconfig` → `memory=`), ChromaDB natif, ou alléger les modèles CPU (annexe C.2). Non appliqué. |
| L24 | **Grounding sur la mauvaise application** (C05) : le planificateur et le validateur ont laissé cibler la fenêtre au premier plan (Discord) pour un libellé d'une autre application. Un clic dans une conversation privée était possible. | **Élevé** | Sprint B : la cible d'un `ui_click_element` doit être l'application nommée ou celle lancée à l'étape précédente, jamais la fenêtre au premier plan par défaut. |
| L25 | **Mise à jour automatique d'Ollama** (0.34.0 → 0.34.1 au redémarrage) : environnement non figé entre deux mesures. | Faible | Désactiver la mise à jour automatique pendant les campagnes de mesure. |
| L26 | Rappel mémoire hors sujet dans les réponses conversationnelles (C07). | Faible | Sprint B : seuil de pertinence (`retrieval_min_score`) à vérifier sur la base réelle. |

---

## 8. Checklist de validation

- [x] **État du dépôt confirmé côté Windows** : section 2, A1 (avec 2 divergences : `2a2389e` n'est pas un doublon ; le poste n'est pas vierge).
- [x] **Atlas installé et démarrant, checklist suivie et livrée** : installation neuve OK (section 2, A2), démarrage réel en environnement complet (`/api/health` → `ok`, section 6 C06) ; `docs/install_checklist.md` livré. Réserve : installeurs système non rejoués (L19).
- [x] **`doctor.py` livré, détecte la VRAM, recommande un modèle** : section 4 (RTX 5060, 8 151 Mio → `qwen2.5:7b` + whisper `base`).
- [x] **Suite complète exécutée, résultats bruts, échecs nominatifs** : section 5 (4 passages dont un en environnement complet, + 3 scripts ×2, causes nominatives).
- [x] **Audit de qualité des tests livré** : annexe A.
- [x] **Inventaire dette et code mort livré, incluant les points relevés en A6** : annexe B.
- [x] **Relevé RAM/VRAM/températures chiffré** : annexe C. Réserve : température CPU non mesurée (L15).
- [ ] **R01-R07 exécutés avec micro réel** : seul R01 est exécuté ; R02 à R07 n'ont pas été dits par une voix humaine. Micro réel ouvert (60 min cumulées) et causes d'échec prouvées par injection (section 6).
- [ ] **Inventaire veille livré** : les rapports sources sont introuvables (L18) ; un relevé de versions obsolètes est fourni en substitut (annexe D).
- [x] **Aucune modification d'un fichier existant** : section 3. Seuls des fichiers de données runtime ont été modifiés par les tests.

---

## 9. Recommandations pour le sprint suivant

### Ordre des sprints — réponse à la question du brief
La suite est **rouge**, donc la règle du brief s'applique : corriger le bloquant **avant** de déplacer. Le bloquant qui rend un déplacement invérifiable est cependant **petit et localisé dans `tests/`**. Proposition soumise au superviseur :

1. **B-minimal** (verdir la suite, ~½ journée) : exclure ou renommer `test_api_clean.py`, `test_stream_fix.py`, `test_cleanup.py` et `test_habit_persistence.py` de la collecte ; corriger `TestVisionDisabled` (`asyncio.run`) ; rendre `test_01_searxng_heartbeat` et `test_chroma_integration` conditionnels (skip si le service est absent, comme `test_memory_v60`), pour que la suite reste interprétable sans Docker. Critère : `python -m pytest tests/ -q` vert, commande brute, sans option. Au passage 4, seuls ces points séparent la suite du vert. **Avant tout**, corriger la persistance ChromaDB (L21), car la restructuration du sprint C touchera probablement `docker-compose.yml` et `data/`.
2. **C** (restructuration) sur cette base verte.
3. **B-complet** (corrections produit ci-dessous).

### P1 — bloquants / fiabilité
- P1.1 Mot d'éveil : entrée int16 (L1) + test d'intégration avec WAV réel (annexe A, T1).
- P1.2 TTS : API piper `AudioChunk`, version épinglée, échec journalisé, repli indépendant du PATH (L3). Le repli SAPI déjà retenu en Notion (« trois emprunts ») est à considérer.
- P1.3 STT : arbitrage cuBLAS ou CPU (L2). Précharger le modèle whisper à l'installation.
- P1.4 Heure et date déterministes (L4).
- P1.5 Validation de `window_hotkey` et des paramètres produits par le planificateur (L5).
- P1.6 Couches OCR hors boucle d'événements, délais réellement appliqués (L9).
- P1.7 **Persistance ChromaDB** (L21) : sauvegarder `/data`, monter le volume sur le bon chemin, vérifier après `docker compose down/up`. *(La virtualisation BIOS est faite, L8 résolu.)*
- P1.9 Cible du grounding = application demandée, jamais la fenêtre au premier plan par défaut (L24).
- P1.10 RAM : arbitrage sur la VM WSL (L23).
- P1.8 Après P1.1 à P1.3 : **refaire R02 à R07 avec Alexis au micro**, en disant « **Hey Atlas** » ; mesurer 30 min de faux positifs en usage réel.

### P2 — robustesse technique
- P2.1 Relance `launch_app` idempotente, pas de « succès » après une vérification échouée (L6).
- P2.2 Résolution des pronoms (« cette fenêtre » → fenêtre au premier plan) et chemin de confirmation vocale (R04).
- P2.3 Isoler `data/` dans les tests (L13).
- P2.4 Verrouiller les dépendances ; déclarer `easyocr`, `pypdf`, `pytest`, `pytest-asyncio` ; retirer `aiosqlite` et `pydantic-settings` s'ils restent inutilisés (L12).
- P2.5 `main.py` : créer `logs/` avant `FileHandler` ; chemins `data/debug` absolus.
- P2.6 `/api/health` : `voice.running` doit refléter la capacité réelle (modèles, cuBLAS, TTS) (C04).
- P2.7 Préchargement du LLM au démarrage et utilisation effective de `ollama.context_window` (L10, annexe B).
- P2.8 `start_atlas_desktop.bat` : activer le venv.
- P2.9 `docker-compose.yml` : retirer ou isoler le service `ollama` (L22) ; secret SearXNG hors dépôt (S1).

### P3 — performance / qualité
- P3.1 Arbitrages VRAM (annexe C), à trancher avant tout passage de torch en CUDA.
- P3.2 Suppression du double appel Tesseract dans `_try_ocr` et de l'appel `/api/tags` à chaque clic quand la vision est désactivée.
- P3.3 Tests à écrire selon la liste hiérarchisée de l'annexe A.
- P3.4 Code mort et nettoyage de dépôt (annexe B), à traiter en sprint C.
- P3.5 Relevé de la température CPU avec un outil dédié (L15).

### Protocole de reprise R02 à R07 (à exécuter par Alexis)
1. Venv activé, `python scripts\doctor.py` → code 0.
2. `python main.py` depuis `assistant-bureau\`, observer le systray.
3. R02 : dire « Hey Atlas » 10 fois à 1 m ; noter le nombre de passages en « listening ».
4. R03 à R05 : une commande après chaque éveil ; noter la transcription (logs) et la réponse entendue.
5. R06 : 5 cycles d'affilée ; vérifier le retour en « idle ».
6. R07 : chronométrer de la fin de « Atlas » au premier son (enregistrement téléphone ou horodatages des logs).
7. Laisser Atlas tourner 30 min en activité normale ; compter les éveils non sollicités.

---

# Annexes

## Annexe A — Audit de la qualité des tests

### A.1 Couverture réelle (passage 3, `pytest-cov`, 6 538 instructions)

| Module | Instr. | Couverture | | Module | Instr. | Couverture |
|---|---|---|---|---|---|---|
| **tools/grounding.py** | 957 | **25 %** | | core/validator.py | 227 | 41 % |
| core/intent_engine.py | 698 | 50 % | | core/planner.py | 80 | **36 %** |
| api/routes.py | 481 | 54 % | | tools/systray.py | 88 | 39 % |
| **core/voice_engine.py** | 334 | **42 %** | | tools/system_config.py | 113 | 31 % |
| tools/window_controller.py | 307 | 35 % | | tools/browser_bridge.py | 162 | 23 % |
| core/intent_classifier.py | 277 | 68 % | | tools/process_manager.py | 82 | 23 % |
| core/memory_manager.py | 260 | 66 % | | tools/screen_reader.py | 62 | 16 % |
| tools/app_launcher.py | 236 | 55 % | | core/orchestrator.py | 153 | 85 % |
| core/trigger_engine.py | 213 | 73 % | | core/error_learning.py | 66 | 98 % |
| core/workflow_engine.py | 188 | 82 % | | core_conversational/test_kokoro.py | 9 | 0 % |
| **TOTAL** | 6 538 | **52 %** | | | | |

**Chemins jamais empruntés, par fonction :**
- `tools/grounding.py` : `_try_ocr` **1 %**, `_try_uia` 2 %, `_try_cache` 3 %, `_try_easyocr` 8 %, `_try_electron_heuristics` 19 %, `_try_steam_nav_heuristic` 3 %, `verify_post_click` 2 %, `_check_proximity_disambiguation` 2 %, `_verify_target_near_point` 2 %, `_choose_best_window` 3 %, `_capture_window_screenshot` 3 %, `_find_candidate_windows` 8 %, `_detect_app_type` 11 %, `_try_vision` 1 % (normal : code mort).
- `core/voice_engine.py` : `_speak_sync` **2 %**, `_run_text_pipeline` 2 %, `_record_audio_sync` 4 %, `_listen_loop` 6 %, `_wake_callback` **10 %**, `_init_wake_word` 33 %.
- `core/validator.py` : `resolve` **31 %** (93 lignes jamais exécutées), `_is_app_running` 7 %.
- `core/planner.py` : `plan` 8 %, `_parse_plan` 6 %, `_validate_plan` 12 %, `replan` 9 %.
- `core/intent_engine.py` : `execute_confirmed` 5 %, `_verify` 6 %, `route_interaction` 9 %, `_run_redo` 10 %, `execute` 46 %.

Les invariants 2 (le LLM planifie) et 3 (validateur déterministe) reposent sur `planner` et `validator.resolve`, justement parmi les moins couverts.

### A.2 Tests tautologiques (valident un mock plutôt qu'un comportement)

| Test | Pourquoi il ne prouve rien | Défaut réel qui passe à travers |
|---|---|---|
| `test_voice_v40::test_05_speak_executes_without_error` | Remplace `_speak_sync`, puis vérifie que le remplaçant a été appelé | TTS muet (L3) |
| `test_voice_v40::test_04_transcribe_returns_string` | `faster_whisper` remplacé par un faux qui renvoie « bonjour atlas » | cuBLAS absent (L2), modèle non préchargé |
| `test_voice_v40::test_06_full_pipeline_mock` | Les 4 étapes (record, transcribe, pipeline, speak) sont mockées ; seul l'enchaînement des états du systray est testé | Toute la chaîne réelle |
| `test_voice_v40::test_02/03/12` | `_init_wake_word` et `_listen_loop` remplacés | Mot d'éveil inopérant (L1) |
| `test_voice_v602::test_06/07` | `predict` mocké avec des scores fixes ; `_wake_callback` (conversion float) jamais exécuté | L1 |
| `test_voice_v602::test_05` | `Model` mocké ; vérifie seulement les arguments du constructeur | L1 |
| `test_voice_v602::test_12/13` | Vérifie que les URL et destinations sont les constantes du module (constante == constante) | — |
| `test_voice_v602::test_15` | Vérifie qu'on appelle `download_models` avec la sentinelle, pas que les modèles arrivent. Comportement réel confirmé à la lecture d'openwakeword 0.6.0 | — |
| `test_voice_v602::test_08` | Instantané de `settings.json` : casse à chaque réglage légitime, ne teste aucun code | — |
| `test_voice_v40::test_10` | `torch` remplacé : ne voit pas que la build réelle est CPU (faux avertissement permanent) | L11 |
| `test_vision_parsers::TestGroundingTimeoutEnforced::test_layer_timeout_aborts_slow_layer` | La couche lente est un `asyncio.sleep` coopératif ; les vraies couches OCR sont **synchrones**. Démontré : couche bloquante de 8 s avec délai de 3 s → 9,0 s, statut « failure » | L9 |
| `test_vision_parsers::test_timeout_constants_present`, `test_vision_v60::test_easyocr_timeout_defined` | Constante == valeur littérale | L9 |
| `test_vision_v60::TestGroundingStackF2`, `test_sprint_kimi_understanding_v51` (ordre des couches) | Vérifient la **liste** des couches, jamais leur exécution | G1 à G3 (annexe B) |
| `test_automation_v30::test_11_workflow_run_mode_gaming` | Callback mocké : vérifie la liste des actions, pas leur effet ni la protection | — |
| `test_final_v50::test_04_idempotent_launch_skip` | `_is_process_running` forcé à True | L6 (relance ×3 observée) |

### A.3 Zones critiques non couvertes
1. **Grounding** (couche la plus fragile) : aucun test n'exécute `_try_ocr`, `_try_uia`, `_try_cache` ou `_try_easyocr` sur une image, même statique. Aucun test du seuil `min_score=1.1`, de la désambiguïsation, de `verify_post_click`, de la sélection de fenêtre, des coordonnées multi-écrans.
2. **Chaîne voix réelle** : aucun test avec un fichier audio réel (WAV → OWW → whisper → Piper).
3. **Planificateur → validateur** : aucun test ne vérifie qu'un plan LLM absurde (`window_hotkey keys="Fichier"`) soit rejeté.
4. **Confirmation** : `execute_confirmed` à 5 %, aucun chemin vocal.
5. **Réponses factuelles** (heure, date) : non testées, alors qu'elles sont fausses.
6. **Sécurité PowerShell** : 4 cas seulement (`validate_v12`), `system_config` à 31 %.
7. **Démarrage de `main.py`** (lifespan complet) : jamais exécuté en test ; un clone neuf sans `logs/` plante.

### A.4 Tests fragiles

| Test / fichier | Dépendance | Constat |
|---|---|---|
| `test_v53_migration::TestVisionDisabled::test_vision_disabled_returns_skipped` | **Ordre d'exécution** (`get_event_loop`) | Échoue dans la suite, passe seul |
| `test_vision_parsers::test_layer_timeout_aborts_slow_layer` | `get_event_loop` + **écran réel** : `_try_easyocr` non mocké, EasyOCR lu sur l'écran courant (5,9 s) et **peut cliquer** si « fichier » est visible dans une fenêtre « notepad » | Risque d'effet de bord |
| `test_vision_v60` (`_try_easyocr("Notepad", ...)`) | Écran réel, fenêtres ouvertes | Idem |
| `test_interaction_v22::test_03` | Fenêtre active réelle | A lu « Settings - Docker Desktop » |
| `test_web_v20` (10 tests) | Internet (ddgs, example.com), SearXNG, **navigateur Playwright réel** (11,9 s) | Échec selon l'environnement |
| `test_chroma_integration` | Serveur ChromaDB ; crée et supprime une collection **dans la vraie base Atlas** (Docker) | 0/5 sans serveur ; risque pour la mémoire réelle, aggravé par L21 |
| `test_core_conversational::test_embeddings_available` | Modèle HF (26,5 s) | Réseau au premier lancement |
| `test_automation_v30` | Vrais `data/schedules.json` et `triggers.json` (sauvegarde/restauration par fixture) | Un crash en cours de test laisse l'état modifié |
| `test_metrics_grounding_v52`, `test_stabilisation_v31`, `test_final_v50`, orchestrateur | Écrivent dans le vrai `data/atlas_actions.jsonl` | +101 lignes pendant ce sprint |
| `validate_v12`, `test_habit_persistence` | Vrais `audit_log.jsonl` et `habits.db` | Pollution (« Get-Process TEST » ×34) |
| `validate_v12::test_lifespan` | `version in {"3.0.0","3.1.0","4.0.0"}` | Bloque toute montée de version |
| `test_memory_v60` | `time`/`datetime` (6 occurrences) | À surveiller (non reproduit) |
| `test_api_clean`, `test_stream_fix` | API vivante, **actions réelles** | Voir section 5 |

### A.5 Liste hiérarchisée des tests à écrire ou renforcer (ne pas écrire dans ce sprint)

| Prio | Test | Justification |
|---|---|---|
| T1 | Intégration mot d'éveil : WAV « Hey Atlas » (fixture) injecté dans le vrai `_wake_callback` → `_on_wake_word` appelé ; WAV neutre → non appelé | Aurait détecté L1 (banc déjà prouvé en section 6) |
| T2 | TTS réel : `_speak_sync` avec la voix réelle et `sd.play` intercepté **en validant le dtype** → tableau int16 non vide | Aurait détecté L3 (piège : un faux `sd.play` permissif masque le bug, constaté pendant ce sprint) |
| T3 | STT réel (CPU) sur WAV fixture, assertion sur les mots-clés | L2 et qualité de transcription (« Black Note ») |
| T4 | Grounding OCR sur captures statiques (Steam, Discord, Bloc-notes) avec `pyautogui.click` mocké : coordonnées attendues ± tolérance | Couche la plus fragile, 1 % de couverture |
| T5 | Délais de grounding avec une couche **bloquante** (`time.sleep`) → statut `timeout` et durée ≤ délai + marge | L9 (le test actuel est coopératif) |
| T6 | Validateur : rejet des `keys` non-touches, des cibles pronominales non résolues, des outils inconnus issus du planificateur | L5, invariant 3 |
| T7 | Heure et date : réponse contenant l'heure système (± 1 min) | L4 |
| T8 | `launch_app` : vérification échouée alors que le processus existe → aucune relance ni second lancement | L6 |
| T9 | Démarrage `main.py` dans un répertoire temporaire sans `logs/` | Plantage d'un clone neuf |
| T10 | `_record_audio_sync` avec ambiance à ~17 % de trames > 500 → l'enregistrement s'arrête avant `max_recording_seconds` | Seuil fixe contre bruit réel mesuré |
| T11 | `/api/health` reflète l'indisponibilité voix (modèle absent, cuBLAS absent) | C04 |
| T12 | Tous les tests écrivant dans `data/` → `tmp_path` | L13 |
| T13 | Remplacer les tests tautologiques de l'A.2 ou les compléter par un test réel | Faux sentiment de sécurité |

---

## Annexe B — Inventaire dette, code mort et architecture

### B.1 Points relevés par le superviseur

| Point | Constat CHAT6 | Criticité |
|---|---|---|
| Tout sous `assistant-bureau/` ; racine = `README.md`, `.gitignore`, `requirements-core-conversational.txt` | **Confirmé** (`git ls-files` : 143 fichiers, 140 sous `assistant-bureau/`). Le `README.md` racine est une copie (5 251 o) de `assistant-bureau/README.md`. Il existe aussi, non suivis, un `.venv/` et un `data/debug/` (12 Mo de captures Steam) **à la racine**, créés par un lancement depuis la racine (voir G4). | Moyenne (C) |
| `rapport.md` est un répertoire | **Confirmé** : 5 fichiers. | Faible (C) |
| Six rapports à la racine d'`assistant-bureau/` | **Confirmé**, plus 2 fichiers de profiling locaux non suivis (`rapport_ollama_config.txt`, `rapport_profile_minicpm.txt`). | Faible (C) |
| `test_kokoro.py` vide | **Confirmé**, 0 octet, ajouté par `e01949a`, **référencé nulle part** (grep : seul le brief). **Mais** il existe aussi `core_conversational/test_kokoro.py` (482 o, suivi) : script Kokoro exécuté à l'import (`kokoro_onnx`, `soundfile` non installés), dans un **paquet de production**, compté dans la couverture (0 %). Son WAV de sortie a été ajouté puis retiré par `2a2389e`. | Faible / Moyenne (le second) |
| `petite_image.png` (75 Ko) | Recadrage d'interface de jeu (« TOTAL D'XP / Utilisez les paramètres standard »), probablement un échantillon OCR manuel. **Aucune référence** dans le code, les tests ou les scripts. Présent depuis le commit initial. **Mort.** | Faible |
| `.venv`, `__pycache__`, `.pytest_cache`, `logs/`, `data/` exclus | **Confirmé** : aucun fichier suivi sous ces chemins, `git ls-files -ci --exclude-standard` vide. Seuls `data/workflows/*.yaml` sont suivis (intentionnel). **Trou** : `data/voices/*.onnx.json` n'est pas ignoré (L20). `.coverage` n'est pas ignoré. | Faible |
| Commit « doublon » | **Infirmé** : `2a2389e` supprime `core_conversational/test_kokoro_rori.wav`. Le blob de 141 Ko reste dans l'historique. | Info |

### B.2 Code mort (avec preuve)

| Élément | Localisation | Preuve | Criticité |
|---|---|---|---|
| Pile vision MiniCPM-V | `tools/grounding.py` `_try_vision` (l.1132–1349), `_parse_vision_json`, `_encode_image`, `_normalize_vision_payload`, `_steam_nav_crop` (partiel) | `_build_layers` n'ajoute `_try_vision` que si `_is_vision_enabled()` ; `config/settings.json` → `grounding.vision_enabled=false`. Aucun autre appelant hors `tests/` et `scripts/profile_minicpm.py` (manuel). Couverture de `_try_vision` en suite complète : 1 %. | Moyenne (~250 lignes) |
| Garde redondante | `_try_vision` l.1139 (retour « skipped ») | Inatteignable en production puisque la couche n'est pas ajoutée ; seul le test l'atteint | Faible |
| Appels résiduels à la vision | `_build_layers` → `_has_local_minicpm()` (requête `/api/tags`, cache 10 s) **à chaque clic** ; `find_and_click` → `_preferred_vision_models()`, `_list_ollama_models()` à chaque échec | Exécutés alors que la vision est désactivée | Faible |
| Repli par défaut vision **activée** | `_is_vision_enabled()` renvoie `True` si `settings.json` est illisible | Contredit la décision de la Réunion #4/#5 | Faible |
| Modèles Ollama inutilisés | `minicpm-v:latest` 5,5 Go, `qwen2.5:14b` 9,0 Go, `mistral:latest` 4,4 Go | Config = `qwen2.5:7b` ; ~19 Go de disque | Faible |
| `scripts/profile_minicpm.py`, `docs/vision_runbook.md` | — | Outillage de la pile désactivée | Faible |
| `ollama.context_window: 8192` | `config/settings.json` | Lu **nulle part** (grep). Contexte effectif d'Atlas = 4 096 (ligne de commande `llama-server -c 4096` à 16:33:15) | Moyenne |
| `ollama._previous_model`, `_migration_reason` (« RTX 3050 ») | `config/settings.json` | Informatif, obsolète | Faible |
| `core_conversational/test_kokoro.py`, `test_kokoro.py` | voir B.1 | — | Faible |
| Scripts ad hoc dans `tests/` | `debug_parser.py`, `debug_test2.py`, `run_one_prompt.py`, `_check_searxng.py`, `api_*_check.py` (4), `audit_capabilities_v22.py` (exécute de vraies commandes à l'import : Bloc-notes, calculatrice, frappe), `diagnostic_v22.py`, `scenario_5tests_v20.py`, `smoke_runtime_v20.py`, `direct_hist_websearch.py`, `runtime_tool_direct_checks.py`, `test_real_integration_v23.py` (actions réelles), `test_real_kimi_5cmd_v51.py` | Non collectés ou 0 test ; certains agissent sur le PC | Moyenne (C) |
| `tools/diagnostics.py` `get_temperatures()` | l.98 | `psutil.sensors_temperatures()` n'existe pas sous Windows : branche toujours en échec | Faible |

### B.3 Défauts de code relevés (inventaire, **non corrigés**)

| ID | Localisation | Nature | Criticité |
|---|---|---|---|
| V1 | `core/voice_engine.py` `_wake_callback` | float32/32768 transmis à OWW (int16 attendu) → mot d'éveil inopérant | **Élevée** |
| V2 | `core/voice_engine.py` `_speak_sync` | `PiperVoice.synthesize(text)` renvoie un générateur (piper ≥ 1.3) ; `sd.play` → `TypeError` avalé par `except: pass` | **Élevée** |
| V3 | idem, repli | `subprocess.run(["piper", ...])` : dépend du PATH, erreurs silencieuses, WAV vide → « TTS unavailable: » sans message | **Élevée** |
| V4 | `_transcribe` | `device="cuda"` sans vérifier cuBLAS ; modèle téléchargé à la première utilisation | **Élevée** |
| V5 | `_speak_sync` | `PiperVoice.load` à **chaque** phrase (~3 s) | Moyenne |
| V6 | `_on_wake_word` | Le flux du mot d'éveil continue de remplir la file pendant l'enregistrement : risque de redéclenchement sur l'arriéré | Moyenne |
| V7 | `_record_audio_sync` | Seuil de parole fixe 500 ; 17,7 % des trames ambiantes le dépassent | Moyenne |
| V8 | `_wake_callback` | `if status: return` : trames perdues sans trace | Faible |
| V9 | voix | Aucun journal d'événement d'éveil ni de changement d'état (invariant 5 Observabilité) | Moyenne |
| V10 | voix | Aucune voie de confirmation pour `confirmation_required` (R04) | Moyenne |
| M1 | `main.py` l.31 | `FileHandler(logs/atlas.log)` sans créer `logs/` → plantage d'un clone neuf | Moyenne |
| M2 | `main.py` `_warn_if_voice_gpu_missing` | Teste torch alors que le STT utilise CTranslate2 → faux positif permanent (torch CPU) | Faible |
| M3 | `main.py` | `version="4.0.0"` alors que le projet est en v6.0.2 ; `validate_v12` fige cette valeur | Faible |
| G1 | `tools/grounding.py` `_try_ocr`, `_try_easyocr` | `async` sans `await` : bloquent la boucle, `wait_for` inopérant (prouvé) | **Élevée** |
| G2 | `_try_ocr` l.884 | `image_to_data` appelé une fois de trop (résultat écrasé l.915) | Faible |
| G3 | `_build_layers` | Appel réseau `/api/tags` à chaque clic (vision désactivée) | Faible |
| G4 | `_DEBUG_IMAGE_DIR = "data/debug"` | Relatif au **répertoire courant** → `Cortana_Killer/data/debug` (12 Mo) créé à la racine | Faible |
| G5 | `_try_ocr` Steam | 3 PNG écrits à chaque tentative, sans rotation | Faible |
| E1 | `core/intent_engine.py` l.110 | `*args.get("keys", [])` décompose une chaîne en caractères (C02) | **Élevée** |
| E2 | moteur, `launch_app` | Relance ×2 après vérification échouée → 3 instances ; succès annoncé | Moyenne |
| E3 | classificateur / validateur | « cette fenêtre » → titre « cette » | Moyenne |
| E4 | validateur | `app_title="le bloc-notes"` (article conservé) | Faible |
| E5 | réponses conversationnelles | Heure inventée (R03) | **Élevée** |
| E6 | `core/planner.py` docstring | « Utilise Qwen2.5 14B » alors que la config est en 7B | Faible |
| D1 | `docker-compose.yml` service `chromadb` | Volume monté sur `/chroma/chroma` alors que l'image persiste dans `/data` : mémoire dans la couche du conteneur (L21) | **Élevée** |
| D2 | `docker-compose.yml` service `ollama` | Second Ollama (0.17.0) sur `[::]:11434`, `restart: unless-stopped`, démarré à chaque lancement de Docker Desktop (L22) | Moyenne |
| D3 | `docker-compose.yml` | Images `:latest` non épinglées (`chromadb/chroma`, `searxng/searxng`, `ollama/ollama`) : un `pull` change silencieusement de version | Moyenne |
| S1 | `docker-compose.yml`, `config/searxng/settings.yml` | Secret SearXNG en dur `atlas_secret_key_change_me` (service local) | Faible |
| S2 | `docker-compose.yml` | Service `ollama` sur 11434 en conflit avec l'Ollama natif | Moyenne |
| O1 | `/api/health` | `voice.running=true` sans capacité réelle | Moyenne |
| O2 | `start_atlas_desktop.bat` | venv non activé (casse le repli TTS) ; répertoire courant non fixé (G4) | Moyenne |

### B.4 Incohérences documentation / code

| Document | Affirmation | Réalité |
|---|---|---|
| `README.md` (racine + `assistant-bureau`) | `ollama pull mistral` | Modèle configuré : `qwen2.5:7b` |
| `README.md` | `docker-compose up -d` | Démarre aussi un Ollama conteneurisé (conflit) ; exige la virtualisation |
| `README.md` | `pip install -r requirements.txt` suffit | Manquent `easyocr`, `pypdf`, Playwright Chromium, dossier `logs/`, modèles voix, cuBLAS |
| `README.md` Architecture | `docker-compose.yml # Ollama + ChromaDB` | + SearXNG ; `core/` et `tools/` listés partiellement (voix, grounding, planner, orchestrator absents) |
| `README.md` | « `docker-compose up -d` » démarre la mémoire | Mémoire non persistée sur l'hôte (L21) |
| `README.md` | « Tesseract absent → couche vision MiniCPM-V » | Vision désactivée : repli EasyOCR puis échec |
| `docs/voice_runbook.md` §0 et §2 | Pipeline prêt une fois les modèles téléchargés | 3 défauts bloquants (V1 à V4) |
| `docs/voice_runbook.md` §5 | « Sur RTX 3050 » | RTX 5060 ; l'avertissement « aucun GPU » est faux |
| `docs/voice_runbook.md` §1 | « Dire Atlas » (brief R02) | Modèle entraîné sur « Hey Atlas » |
| `RAPPORT_V602.md` §5 | `test_10` attendu PASS sous Windows | **Confirmé PASS** |
| `RAPPORT_V602.md` §1 | Pipeline « déjà fonctionnel (v4.0) » | Jamais fonctionnel sur ce poste (V1 à V4) |
| `tools/grounding.py` docstring | « 4 couches », « MiniCPM-V ~300 ms » | 6 à 7 couches possibles ; délai MiniCPM 45 s ; vision désactivée |
| `config/settings.json` | `context_window: 8192` | Ignoré (4 096 effectif) |
| Notion « Invariants » §5 Observabilité | « Toute capacité nouvelle est journalisée » | Événements voix non journalisés (V9), échecs TTS silencieux (V2) |

### B.5 Écarts par rapport aux invariants (Notion « 1. Invariants »)

| Invariant | Constat |
|---|---|
| 1. 100 % local | Respecté à l'exécution. Téléchargements à la première utilisation (whisper, embeddings, EasyOCR) : réseau requis une fois. Télémétrie ChromaDB **activée** par défaut côté client (« Anonymized telemetry enabled » dans le journal d'Atlas), à désactiver. |
| 2. Controlled loop | Respecté structurellement (le LLM produit un plan, le moteur exécute). Mais les **paramètres** du plan passent sans contrôle sémantique (E1). |
| 3. Validateur déterministe | Aucun appel LLM dans `core/validator.py` (vérifié). Validation de plan limitée (`_validate_plan` → `resolve`), `keys` non validé. |
| 4. Rien d'irréversible sans confirmation | Pas d'action destructive observée. Des frappes clavier non maîtrisées peuvent atteindre la fenêtre au premier plan (E1) : non irréversible, mais non contrôlé. |
| 5. Observabilité | Écarts V9, V2, O1 ; les tests polluent les métriques (L13). |
| 6. Personnel | Respecté. |

### B.6 Dépendances

| Catégorie | Éléments |
|---|---|
| Déclarées, jamais importées | `aiosqlite`, `pydantic-settings`. `comtypes` n'est jamais importé directement (dépendance de `pycaw`, à garder). `lxml` est utilisé comme parseur BeautifulSoup (chaîne `"lxml"`, à garder). |
| Utilisées, non déclarées | `easyocr` (grounding), `pypdf` (memory_ingest, optionnel), `requests` (grounding, scripts ; transitive), `torch` (main.py ; transitive), `Pillow` (transitive), `ctranslate2` (transitive), `pathvalidate` (CLI piper 1.4.x), `pytest` / `pytest-asyncio` (tests), `kokoro_onnx` / `soundfile` (script parasite) |
| Système non déclarées | cuBLAS 12 (STT GPU), Chromium Playwright, Tesseract (documenté), Docker + virtualisation |
| Doublons | `requirements-core-conversational.txt` (racine) : `httpx>=0.27`, `chromadb>=0.5`, `sentence-transformers>=3.0` contre des versions figées dans `assistant-bureau/requirements.txt` |
| Non figées | 21 lignes `>=` sur 33 (12 seulement en `==`) → dérive constatée (L12) |

---

## Annexe C — Relevé RAM, VRAM et températures

### C.1 — Environnement de l'après-midi (sans Docker, ChromaDB natif)

**Méthode.** Échantillonneur (`nvidia-smi` + `psutil`) de 16:24:17 à 17:05:19. Pas effectif ~3,5 s. Chaque phase est étiquetée pendant la mesure. « RSS python » = somme des processus Python hors échantillonneur (Atlas + processus de mesure). ChromaDB tourne en natif (`chroma.exe`, non compté). Bureau Windows actif pendant toute la mesure : Wallpaper Engine, Opera GX, Discord, VS Code, Overwolf, Docker Desktop (en erreur), Claude.

| Phase | n | VRAM min–max (Mio) | RAM système max (Mio) | RSS python max (Mio) | RSS ollama max (Mio) | GPU °C max | Util. GPU moy. | Puiss. max (W) | Ventilo GPU max | CPU moy. |
|---|---|---|---|---|---|---|---|---|---|---|
| Repos, sans Atlas | 14 | 1 571–1 591 | 15 974 | 134 | 108 | 51 | 7 % | 23 | 0 % | 41 % |
| **1. Atlas démarré, inactif** | 19 | **1 530–1 630** | **16 353** | **567** | 108 | 54 | 11 % | 24 | 0 % | 25 % |
| Chargement LLM | 24 | 1 535–6 451 | 16 443 | 578 | 129 | 56 | 5 % | 33 | 0 % | 32 % |
| **2. LLM chargé seul** (qwen2.5:7b, ctx 8192) | 32 | **6 427–6 453** | 16 272 | 649 | 124 | 69 | 12 % | 128 | 41 % | 25 % |
| Chaîne : STT (whisper base cuda int8) | 8 | 6 331–**6 525** | 16 223 | 1 030 | 122 | 49 | 18 % | 21 | 33 % | 32 % |
| Chaîne : pipeline (planif. LLM ctx 4096 + actions) | 9 | 1 690–**6 569** | 16 669 | 2 258 | 121 | 64 | 25 % | 141 | 0 % | 38 % |
| Chaîne : EasyOCR (CPU) + capture | 6 | 6 439–6 453 | **18 614** | 4 170 | 121 | 52 | 12 % | 20 | 0 % | 53 % |
| Chaîne : TTS | 1 | 6 435 | **18 689** | 4 184 | 121 | 52 | 19 % | 19 | 0 % | 28 % |
| Tests whisper cuda + LLM chargé | 63 | 5 882–**6 696** | 16 194 | 1 605 | 122 | 53 | 14 % | 40 | 33 % | 32 % |
| **5. Charge soutenue 5 min** (LLM 600 tokens en boucle + whisper CPU 6 threads) | 48 | 1 336–6 242 | 16 584 | 1 076 | 131 | **75** | **83 %** | **144** | **65 %** | **86 %** |
| Refroidissement (0 à 25 min) | 21 | 1 372–6 240 | 16 154 | 525 | 115 | 64 → 59 | 15 % | 69 | 65 % | 24 % |

**Réponses aux 5 points du brief**
1. **Au repos, Atlas démarré et inactif** : VRAM **1,53–1,63 Go**, identique au bureau seul. Atlas n'occupe pas de VRAM tant que le LLM n'est pas chargé : torch en build CPU et modèle Whisper pas encore chargé. RAM système 16,35 Go (+~0,4 Go vs sans Atlas). Processus Atlas **~565 Mio** RSS.
2. **LLM chargé seul** : VRAM **6,43–6,45 Go** avec `num_ctx=8192`, soit **+4,86 Go**. Répartition Ollama : modèle 4 168 + KV 448 + calcul 140 = 4 756 Mio. Avec le contexte réellement utilisé par Atlas (4 096), le cache KV est plus petit ; non isolé par mesure.
3. **Pic sur chaîne complète** : **6,53–6,57 Go** (STT GPU + planification + actions). Pic absolu observé **6,70 Go** (LLM + un processus whisper GPU supplémentaire). Marge : **~1,45–1,6 Go** sur 8,15 Go. Moins de 7 Go, mais pas loin : arbitrages ci-dessous.
4. **RAM système en pic** : **18,69 Go / 23,9 Go** (78 %) sans Docker ; **23,45 Go / 23,9 Go (98 %) avec Docker**, qui est la configuration documentée (C.2). Côté Python, **4,18 Go** au total : Atlas ~0,57 Go + processus de mesure ~3,6 Go (EasyOCR torch CPU + embeddings e5-base + whisper + Piper). Dans Atlas réel, ces modèles vivraient dans le processus Atlas, soit **~4 Go de RSS** pour Atlas une fois tous les modèles chargés (extrapolation, non mesuré dans Atlas).
5. **Températures** : GPU **75 °C max** après 5 min à 83 % d'utilisation (144 W, ventilateur 65 %) ; 64 °C une minute après ; 59 °C 25 min après (ventilateur toujours à 65 %) ; 50–54 °C au repos, ventilateur à 0 % (mode semi-passif). **CPU : non mesurée.** `MSAcpi_ThermalZoneTemperature` renvoie « Accès refusé » sans droits admin, et la zone ACPI `\_TZ.TZ00` lisible reste figée à 27,9 °C : ce n'est pas le die CPU. Charge CPU moyenne pendant le stress : 86 %.

**Latences mesurées (pour R07 et L10)**

| Étape | Mesure |
|---|---|
| Démarrage Atlas (lancement → API prête) | ~19 s (imports ~6 s ; lifespan 12,7 s, dont **5,4 s d'import de torch** pour le seul avertissement GPU (M2), ~4 s systray + voix, ~2 s bridge) |
| LLM à froid (1er appel) | **80,5 s** (watchdog GPU 40 s + chargement 40,5 s) ; 2e essai à froid plus tard : 14,6 s |
| Rechargement LLM quand le contexte change (4 096 ↔ 8 192) | ~4 s |
| LLM à chaud | 62–75 tokens/s ; < 1 s pour une réponse courte |
| STT GPU (contournement cuBLAS), toute première exécution | 34 s (compilation des noyaux) |
| STT GPU, 1er appel par processus / à chaud | 2,3–14 s / 1,5–1,65 s (3 s de bruit) ; 0,16 s (3,4 s de parole) |
| STT CPU (int8) | ~5,3 s pour 3 s |
| Pipeline planifié (C02) | 33,7 s |
| Chargement EasyOCR + lecture plein écran (CPU) | 22,2 s |
| TTS `.venv` (aucun son) / venv neuf activé (son) | 4,0 s / 6,2 s |

### C.2 — Environnement complet avec Docker (après activation de la virtualisation, 19:18–19:24)

Même échantillonneur. Docker Desktop actif (`assistant_chromadb`, `atlas_searxng` ; `assistant_ollama` arrêté). Ollama natif 0.34.1.

| Phase | n | VRAM min–max (Mio) | RAM système max (Mio) | RSS python max (Mio) | GPU °C max | CPU moy. |
|---|---|---|---|---|---|---|
| Docker actif, sans Atlas | 6 | 1 501–1 643 | **20 458** | 0 | 61 | 43 % |
| Atlas démarré, inactif | 10 | 1 478–1 521 | 20 718 | 433 | 61 | 45 % |
| 1er `/api/chat` à froid (LLM ctx 4 096) | 12 | 1 417–6 070 | 21 639 | 1 288 | 63 | 54 % |
| Chaîne : STT | 3 | 6 058–6 069 | 20 843 | 1 762 | 53 | 56 % |
| Chaîne : pipeline (planif. + grounding) | 12 | 6 298–6 455 | 23 279 | 4 142 | 62 | 68 % |
| Chaîne : EasyOCR | 4 | 6 433–**6 496** | **23 445** | 5 275 | 45 | 88 % |
| Chaîne : TTS | 1 | 6 489 | 23 415 | 5 339 | 44 | 60 % |

- Empreinte de Docker : `vmmemWSL` **8 344 Mio** de working set, alors que les conteneurs n'utilisent que 134 Mio (SearXNG) et 44 Mio (ChromaDB), selon `docker stats`. Surcoût RAM au repos : **+4,5 Go** par rapport à l'après-midi (15,97 → 20,46 Go).
- **Pic RAM système : 23 445 Mio sur 23 910, soit 98 %** (L23). Le processus Atlas atteint ~1,3 Go après le premier chat (embeddings chargés).
- VRAM : inchangée à ±0,2 Go (pic 6,50 Go ; Docker n'utilise pas le GPU puisque le conteneur Ollama est arrêté).
- LLM : le modèle chargé par Atlas utilise un contexte de **4 096** (`ollama ps`), soit 4,7 Go affichés.

**Arbitrage RAM proposé — NON appliqué :** limiter la VM WSL dans `%USERPROFILE%\.wslconfig` (`[wsl2]` → `memory=4GB`, à valider avec ChromaDB et SearXNG), ou ChromaDB natif + SearXNG seul sous Docker, ou décharger EasyOCR et les embeddings entre usages.

**Arbitrages VRAM proposés — NON appliqués, décision du superviseur**

| Option | Effet estimé | Contrepartie |
|---|---|---|
| A. `voice.stt_device=cpu` | −0,1 à −0,3 Go au pic ; supprime aussi la dépendance cuBLAS | STT ~5,3 s au lieu de ~1,6 s |
| B. Garder whisper `base` (ne pas passer à `small`) | Évite +~0,4 Go | Qualité de transcription (« Black Note ») |
| C. Utiliser réellement `context_window` (`num_ctx` explicite) | Fixe le cache KV (224 Mio à 4 096, 448 à 8 192) ; supprime les rechargements de 4 s si d'autres clients utilisent un autre contexte | Aucune |
| D. **Ne pas** réduire `keep_alive` | — | Un rechargement coûte 15 à 80 s sur ce poste ; le réduire dégraderait fortement l'usage. Envisager plutôt un préchargement au démarrage. |
| E. Décharger le LLM entre commandes | −4,8 Go hors commande | Même coût que D, à proscrire sur ce poste |
| F. **Ne pas** passer torch en CUDA sans arbitrage | EasyOCR sur GPU = +~1 Go estimé → pic ~7,5 Go | EasyOCR à 22 s sur CPU |
| G. Réduire la VRAM du bureau (Wallpaper Engine, navigateurs) | ~1,5 Go occupés hors Atlas | Choix de l'utilisateur |

---

## Annexe D — Inventaire veille

**Constat : les rapports hebdomadaires de veille sont introuvables depuis ce poste.**
Emplacements cherchés : disque utilisateur (motifs *veille*, *watch*), Gmail (« veille », « stack watch » depuis le 01/07/2026 : aucun rapport), Notion (« veille », « Atlas stack » : seule la page « 9. Positionnement & diffusion » dit « Une veille automatisée tourne chaque samedi », sans lien vers les sorties), tâches planifiées locales (aucune), routines cloud Claude Code (liste vide). Connecteurs indisponibles : GitHub, Slack et Linear (échec de connexion ou autorisation requise). **Action superviseur : indiquer où sont publiés les rapports du samedi.**

**Substitut factuel — versions obsolètes dans le `.venv` historique** (`pip list --outdated`, 16/09/2026, **rien appliqué**) :

| Composant | Installé | Dernière | Concerne Atlas | Criticité |
|---|---|---|---|---|
| piper-tts | 1.4.1 | 1.8.0 | TTS : la 1.4.1 casse le CLI (`pathvalidate`) ; l'API ≥ 1.3 est incompatible avec `_speak_sync` | **Élevée** (lié à L3) |
| ctranslate2 | 4.7.1 | 4.8.2 | STT ; ne résout pas cuBLAS à lui seul | Moyenne |
| Ollama (natif) | 0.34.0 → **0.34.1 installée automatiquement** au redémarrage de 18:59 | 0.34.1 | Watchdog de détection GPU expiré au démarrage à froid avec la 0.34.0 (L10) ; avec la 0.34.1, premier appel 46 s via Atlas (non décomposé) | Moyenne |
| Ollama (image Docker) | 0.17.0 | — | Conteneur à retirer (L22) | Faible |
| chromadb/chroma (image) | `latest` de mars 2026, serveur 1.0.0 | non vérifié | **Ne pas mettre à jour** avant d'avoir corrigé la persistance (L21) | **Élevée** |
| searxng/searxng (image) | `latest` de mars 2026 | non vérifié | Fonctionnel (recherche JSON 200) | Faible |
| sentence-transformers | 3.3.1 | 6.0.1 | Embeddings mémoire : **trois versions majeures** d'écart, changements cassants probables | Moyenne |
| transformers | 4.57.6 | 5.17.0 | Transitive (embeddings) ; version majeure | Moyenne |
| chromadb | 1.5.1 | 1.5.9 | Mémoire ; client 1.5.1 avec serveur natif 1.0.0 (API v2) fonctionnel | Faible |
| fastapi / uvicorn | 0.115.6 / 0.34.0 | 0.141.1 / 0.53.0 | API ; écart important | Faible |
| pydantic | 2.10.4 | 2.13.5 | API | Faible |
| onnxruntime | 1.24.3 | 1.30.0 | Mot d'éveil, Piper | Faible |
| torch | 2.12.1+cpu | 2.14.0 | EasyOCR / embeddings ; la question CPU/CUDA prime sur la version (L11) | Moyenne |
| playwright | 1.58.0 | 1.63.0 | Toute mise à jour exige `playwright install chromium` | Faible |
| psutil | 6.1.1 | 7.2.2 | Processus ; version majeure | Faible |
| pywin32 | 308 | 312 | API Windows | Faible |
| comtypes / pycaw | 1.4.8 / 20240210 | 1.4.16 / 20251023 | Volume | Faible |
| ddgs | 9.11.3 | 9.16.0 | Repli recherche web | Faible |
| numpy | 2.4.3 | 2.5.3 | Transverse | Faible |
| websockets | 16.0 | 17.1 | Bridge navigateur ; version majeure | Faible |
| pytest / pytest-asyncio | 9.0.2 / 1.3.0 | 9.1.1 / 1.4.0 | Tests ; la gestion de la boucle asyncio intervient dans l'échec `TestVisionDisabled` | Faible |

Opportunités sans rapport de veille : piper-tts ≥ 1.8 (CLI réparé), repli TTS SAPI (déjà retenu en Notion, voix « Microsoft Hortense » fr-FR présente sur ce poste). Modèles plus performants à VRAM égale : **non évalués**, aucune source de veille disponible.

---

*Rapport Sprint A — rédigé par CHAT6 (Claude Opus 5, Claude Code Windows), 16/09/2026.*
*Traces brutes (sorties pytest complètes, JUnit XML, CSV d'échantillonnage, journaux Atlas/Ollama/sondes) conservées hors dépôt dans le répertoire temporaire de session : elles contiennent des chemins système. À transmettre sur demande.*
