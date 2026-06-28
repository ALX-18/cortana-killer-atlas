# core_conversational Runbook (v6.0.1)

Module cross-platform extrait du cœur conversationnel d'Atlas, partagé avec
**Manman** (fork Mac M). Décision Réunion Atlas #6.

## Pourquoi

Manman réutilise le LLM client, l'identité (avec persona overlay), la mémoire
vectorielle et la classification conversationnelle d'Atlas — **sans embarquer le
code Windows** (grounding, fenêtres, OCR…).

## Architecture

```
core_conversational/           # ZÉRO dépendance Windows
├── identity.py        # IdentityCard + persona overlay + identité Atlas
├── llm_client.py      # LLMClient (httpx) + garde linguistique
├── memory_core.py     # embeddings e5 + ConversationalMemory
├── intent_minimal.py  # MinimalClassifier conversationnel
└── README.md
```

## Délégation depuis Atlas (sans régression)

Atlas **réutilise** le package via façades (API inchangée → 0 régression) :
- `core/embeddings.py` → délègue à `core_conversational.memory_core`
- `core/ollama_client.py` → `SYSTEM_PROMPT_IDENTITY`, `contains_non_latin_script`,
  `LANG_FALLBACK_MESSAGE` importés du package.

## Mécanisme persona overlay

```python
IdentityCard(base_identity, persona_overlay=None).build_system_prompt()
```
- **Atlas** : `atlas_identity()` (sans overlay) → identité Atlas par défaut.
- **Manman** : `IdentityCard(base, persona_overlay=PERSONA_EMILIE)` → prompt enrichi
  d'une section `PERSONA SPÉCIFIQUE`.

## Validation cross-platform (Mac M, par Alexis)

```bash
cd ~/Projet/cortana-killer-atlas
git pull
cd assistant-bureau/core_conversational
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r ../../requirements-core-conversational.txt
python -m pytest ../tests/test_core_conversational.py -v
```
ALL PASS sur Mac → extraction validée, Sprint B Manman peut démarrer.

## Garantie de pureté

Le test `TestNoWindowsDeps` échoue si un module du package importe une dépendance
Windows (pywin32, pywinauto, comtypes, pycaw, wmi, pygetwindow, pyautogui, ctypes,
msvcrt, pytesseract, easyocr) ou un outil Atlas Windows (grounding, window_controller…).

## Tests

```bash
pytest tests/test_core_conversational.py -q   # 15 tests (pureté, identité, garde, mémoire)
```
