# Atlas v5.0 Runbook

## Scope
This runbook covers the 5 most frequent operational failures and how to diagnose/recover fast.

## 1) ERR_MODEL_UNAVAILABLE
Symptoms:
- `/api/chat` returns model unavailable
- `/api/health` shows `ollama.ok=false`

Checks:
1. Run `ollama list` and confirm the model exists.
2. Check port 11434: `netstat -ano | findstr 11434`.
3. Verify config model in `config/settings.json` (`ollama.model`).

Recovery:
1. Restart Ollama service.
2. Pull model if missing: `ollama pull qwen2.5:14b`.
3. Recheck with `/api/health`.

## 2) ERR_MODEL_TIMEOUT
Symptoms:
- `/api/chat` timeouts on long responses

Checks:
1. CPU/GPU usage saturation.
2. `stream_timeout_seconds` in `config/settings.json`.
3. Prompt complexity and large context size.

Recovery:
1. Increase `stream_timeout_seconds`.
2. Reduce prompt/history size.
3. Ensure no competing heavy workloads.

## 3) ERR_RECURSION_DETECTED / ERR_REPLAN_LIMIT
Symptoms:
- Plan execution stops with recursion/replan error

Checks:
1. Inspect recent structured logs: `/api/errors/recent`.
2. Validate planner output for repeated actions.
3. Validate validator mapping for the failed step.

Recovery:
1. Simplify user intent into smaller tasks.
2. Add deterministic guard in validator for that intent.
3. Re-run and confirm no repeated plan signature.

## 4) Web search degraded (SearXNG/DDGS)
Symptoms:
- Search returns degraded message
- `/api/health` shows `searxng.ok=false`

Checks:
1. SearXNG container state: `docker ps`.
2. SearXNG JSON API: `http://localhost:8888/search?q=test&format=json`.
3. Timeout values in `config/settings.json`: `searxng_timeout_seconds`, `ddgs_timeout_seconds`.

Recovery:
1. Restart SearXNG container.
2. Ensure `config/searxng/settings.yml` allows JSON format.
3. Keep DDGS fallback enabled.

## 5) Mono-instance lock / startup collision
Symptoms:
- Startup exits with message that another instance is active
- Port 8550/9999 collision

Checks:
1. Existing process already running (`python`, `uvicorn`).
2. Lock file presence: `data/atlas.lock`.
3. Port occupancy for 8550 and 9999.

Recovery:
1. Stop the previous Atlas process cleanly.
2. Retry startup once ports are free.
3. If stale lock suspected after crash, verify no running Atlas process then remove `data/atlas.lock`.

## 6) Commandes "clique sur X" très lentes (> 60s) — Tesseract manquant
Symptoms:
- `clique sur Bibliothèque dans Steam` (ou similaire) prend 60 à 90s avant d'échouer
- Le client UI affiche "timed out" / "Request failed: timed out"
- `data/atlas_actions.jsonl` : entrée avec `"tool": "ui_click_element"`, `"latency_ms": 90000+`, `"grounding_layer": "global_timeout"`
- `logs/atlas.log` : ligne `[OCR] ... tesseract=unknown`

Cause probable :
Tesseract OCR n'est pas installé ou n'est pas dans le PATH système. La couche OCR du grounding stack est sautée silencieusement, le pipeline tombe sur la couche vision MiniCPM-V qui est ~20× plus lente.

Checks:
1. Dans un terminal **fraîchement ouvert** (pour un PATH à jour) :
   ```
   tesseract --version
   tesseract --list-langs
   ```
2. Vérifier que `fra` et `eng` apparaissent dans la liste des langues.
3. Dans `logs/atlas.log` après une commande UI, chercher la ligne `[OCR] Recherche: ... tesseract=X.Y.Z`. Si la valeur est `unknown` → Tesseract injoignable depuis Atlas.

Recovery:
1. Installer Tesseract depuis https://github.com/UB-Mannheim/tesseract/wiki
2. **Cocher "Additional language data" → French** dans l'installeur
3. Ajouter `C:\Program Files\Tesseract-OCR` au PATH système
4. **Redémarrer le terminal puis Atlas** (le PATH n'est rafraîchi qu'au démarrage du process)
5. Ré-exécuter la commande et confirmer dans `atlas_actions.jsonl` :
   - `"grounding_layer": "ocr"` (ou `"cache"` au 2ᵉ appel)
   - `"latency_ms"` en dessous de 6000

Voir aussi : `README.md` → Prérequis système.

## Verification commands
- API global health: `GET /api/health`
- Actionable errors: `GET /api/errors/recent?limit=20`
- Structured logs: `GET /api/logs/recent?limit=50`
- Grounding metrics: `GET /api/metrics/grounding?limit=200`
