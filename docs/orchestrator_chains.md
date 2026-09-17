# Orchestrator Chains — F3 Multi-app Orchestration (v6.0)

## Modèle

`core/orchestrator.py` — DAG léger à exécution **séquentielle**. Le Planner (Qwen 7B)
décompose une requête en steps ; l'orchestrateur les exécute via l'ExecutionEngine
en respectant les dépendances et une politique d'échec par step.

### OrchestrationStep
| Champ | Rôle |
|---|---|
| `id` | identifiant unique du step |
| `action` | nom d'outil / verbe d'intent |
| `params` | paramètres de l'action |
| `depends_on` | liste d'ids dont ce step dépend (doivent avoir **réussi**) |
| `on_failure` | `abort` / `skip` / `ask_user` / `rollback` |
| `verify` | callable optionnel de vérification post-exécution |
| `rollback_action` | `{action, params}` pour la politique `rollback` |

### Politiques on_failure
- **abort** : stoppe toute la chaîne (statut global `aborted`).
- **skip** : ignore le step, continue (statut global `partial`).
- **ask_user** : met la chaîne en pause (statut `paused`), attend confirmation.
- **rollback** : tente l'action inverse (best-effort) puis stoppe.

Un step dont une dépendance n'a pas réussi est automatiquement `skipped`.

### Statut global
`success` (tout OK) · `partial` (des skips) · `aborted` · `paused`.

### Journalisation
Chaque step est logué en JSONL dédié (`data/atlas_actions.jsonl`) via
`log_orchestration_step` : `{orchestration_id, step_id, status, latency_ms, error,
pipeline_stage: "orchestration"}`.

## Chaînes démo (`build_demo_chain`)

### C1 — Mode travail
```
close_discord (abort) → open_vscode (abort) → open_spotify (skip)
```
Si Discord refuse de se fermer → abort. Si Spotify échoue → on continue quand même.

### C2 — Briefing matin
```
read_mails [MOCK F6] (skip) → météo (skip) → calendrier [MOCK] (skip)
```
Étapes indépendantes ; toute étape échouée est simplement sautée.
Les mails (F6) sont mockés en v6.0.

### C3 — Mode gaming
```
close_prod (skip) → launch_steam (abort) → launch_game (ask_user)
```
Si le jeu n'est pas trouvé → pause + demande à l'utilisateur.

## Utilisation

```python
from core.orchestrator import get_orchestrator, build_demo_chain
res = await get_orchestrator().run(build_demo_chain("c1"))
# res = {orchestration_id, status, steps: [{step_id, status, latency_ms, error}, ...]}
```

L'exécuteur est injectable (`Orchestrator(executor=...)`) pour les tests sans LLM/app réelle.

## Tests

```bash
pytest tests/test_orchestrator_v60.py -q   # 14 tests (policies, topo, chaînes)
```

## Limites v6.0
- Exécution **séquentielle** uniquement (pas de parallélisme de branches).
- C2 mails mockés (F6 non livré).
- Pas d'endpoint API dédié (orchestration déclenchée programmatiquement / via planner).
