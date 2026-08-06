# Atlas — Assistant Bureau Windows

Assistant local intelligent pour le contrôle de PC Windows.  
Utilise Ollama (LLM local) + ChromaDB (mémoire RAG) + FastAPI.

## Prérequis

- **Python 3.12+**
- **Ollama** : [ollama.com](https://ollama.com) — installer puis `ollama pull mistral`
- **Docker** : pour ChromaDB (mémoire long terme)
- **Tesseract OCR** : voir section *Prérequis système* ci-dessous

---

## Prérequis système (obligatoires)

### Tesseract OCR

Atlas utilise Tesseract pour la reconnaissance de texte à l'écran (couche OCR du grounding stack — résolution des clics sémantiques type "clique sur Bibliothèque dans Steam").

**Installation Windows :**

1. Télécharger l'installeur : https://github.com/UB-Mannheim/tesseract/wiki
2. Pendant l'installation, **cocher "Additional language data" → French** (obligatoire pour matcher les libellés FR)
3. Ajouter au PATH système : `C:\Program Files\Tesseract-OCR`
4. Vérifier dans un **nouveau** terminal (PATH refresh) :
   ```bash
   tesseract --version
   tesseract --list-langs   # doit lister 'fra' et 'eng'
   ```

**Sans Tesseract installé**, la couche OCR du grounding sera inutilisable. Atlas tombera sur la couche vision MiniCPM-V (lente : ~10s par appel), et la latence des commandes UI passera de ~5s à ~90s avec timeout global.

**Symptôme typique** : commandes "clique sur X" qui prennent > 60s + entrées `data/atlas_actions.jsonl` avec `"grounding_layer": "global_timeout"` et `tesseract=unknown` dans `logs/atlas.log`. Voir `docs/runbook.md` pour le diagnostic.

## Installation

```bash
cd assistant-bureau
pip install -r requirements.txt
```

## Lancement

### 1. Démarrer les services Docker (ChromaDB)

```bash
docker-compose up -d
```

### 2. Démarrer Ollama

```bash
ollama serve
```

### 3. Lancer Atlas

```bash
python main.py
```

### 4. Lancer Atlas Desktop (UI native)

```bash
python desktop/atlas_desktop.py
```

Ou via script Windows:

```bash
start_atlas_desktop.bat
```

L'interface web est accessible à : **http://127.0.0.1:8550**  
(port fallback automatique si 8550 est occupé)

## Tests

### Vérifier l'intégration ChromaDB

```bash
python -m pytest tests/test_chroma_integration.py -v
```

Ce test vérifie :
1. Connexion à ChromaDB (Docker doit tourner)
2. Création d'une collection de test
3. Insertion d'un document
4. Recherche par similarité
5. Nettoyage de la collection
6. Réponse de `/api/v2/heartbeat`

Doit passer en **< 5 secondes**.

## Architecture

```
assistant-bureau/
├── main.py              # Point d'entrée FastAPI (lifespan)
├── api/
│   ├── routes.py        # Endpoints REST + SSE streaming
│   └── models.py        # Schémas Pydantic
├── core/
│   ├── ollama_client.py # Client Ollama (streaming + timeout)
│   ├── intent_engine.py # Parsing tool-calls + exécution
│   ├── context_monitor.py # Contexte système + habitudes (SQLite)
│   ├── file_indexer.py  # Indexation passive des fichiers locaux (optionnel)
│   ├── memory_manager.py  # RAG mémoire (ChromaDB)
│   └── confirmation.py    # Système de confirmation 3 niveaux
├── tools/
│   ├── process_manager.py # Gestion processus
│   ├── app_launcher.py    # Lancement applications
│   ├── system_config.py   # Config système (PowerShell sécurisé)
│   └── diagnostics.py     # Diagnostics CPU/RAM/GPU/Disques
├── ui/                  # Interface web (HTML/CSS/JS)
├── config/
│   └── settings.json    # Configuration centralisée
├── data/                # SQLite, audit logs, ChromaDB data
├── tests/               # Tests d'intégration
└── docker-compose.yml   # Ollama + ChromaDB
```

## Sécurité

Les commandes PowerShell sont filtrées par allowlist/denylist (voir `settings.json`).  
Toutes les exécutions sont journalisées dans `data/audit_log.jsonl`.

## Nouvelles capacités v5.x (en cours)

### Résolution intelligente des noms d'applications
- Le lanceur d'apps tolère désormais les noms approximatifs:
	- normalisation accents/tirets/espaces
	- matching partiel
	- fuzzy matching
	- fallback via index local de fichiers (shortcuts `.lnk`, `.exe`, `.bat`, `.cmd`, `.url`)
	- suggestions en cas d'échec

### Filesystem Assistant passif (optionnel)
- Atlas peut indexer localement des fichiers en arrière-plan pour mieux résoudre les demandes ambiguës.
- Configuration dans `config/settings.json` section `filesystem_assistant`.
- Par défaut: `enabled=false` (opt-in).

Endpoints API:
- `GET /api/files/index/status`
- `POST /api/files/index/rebuild`
- `GET /api/files/search?query=<q>&limit=20`

### Reorganisation de fichiers (plan d'abord)
- Plan/simulation (aucun move): `POST /api/files/organize/plan`
- Application explicite (bloquee sans confirmation): `POST /api/files/organize/apply` avec `allow_apply=true`
- Rollback d'une operation appliquee: `POST /api/files/organize/rollback` avec `operation_id`
- Categories automatiques: documents, images, code, media, archives, spreadsheets, other
