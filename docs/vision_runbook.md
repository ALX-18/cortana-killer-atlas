# Vision Runbook — F2 OCR Consolidé (v6.0)

> **Décision Réunion Atlas #5 (25/05/2026) : OCR-only.** Pas de VLM (MiniCPM-V /
> Moondream / Florence-2). Le code MiniCPM-V est conservé *gated* (`vision_enabled=false`)
> mais n'est jamais appelé. Réintroduction conditionnelle en v6.1 si l'OCR prouve
> son insuffisance sur Electron.

## Grounding stack (v6.0)

```
1. UIA / pywinauto (Win32)         ~3s    timeout 3.0s
2. Cache coordonnées               ~0.5s  timeout 0.5s
3. OCR Tesseract                   ~5s    timeout 5.0s
3.5 OCR EasyOCR (fallback)         ~4s    timeout 4.0s   ← F2 v6.0
4. Heuristiques Electron (cond.)   ~0.5s  timeout 0.5s   ← F2 v6.0
( vision MiniCPM-V — gated off )
GROUNDING_TOTAL_TIMEOUT = 20s
```

## EasyOCR (couche 3.5)

- Modèle PyTorch open source, langues **fr + en**, GPU auto-détecté.
- Chargé une seule fois au 1er usage (`_get_easyocr_reader`), ~4-5s de chargement initial.
- Activée après échec de Tesseract, avant le timeout global.
- Dégradation gracieuse : si `easyocr` non installé → couche sautée silencieusement.

**Comparatif Tesseract vs EasyOCR** (`scripts/compare_ocr_engines.py`, libellés UI FR) :

| Moteur | Précision | Latence moy. (après warmup) |
|---|---|---|
| Tesseract | 8/8 | ~396 ms |
| EasyOCR | 8/8 | ~221 ms |

→ Tesseract reste en couche 3 (pas de chargement modèle, démarrage immédiat).
EasyOCR en fallback : plus robuste sur l'anti-aliasing / glyphes difficiles.

## Heuristiques Electron (couche 4 conditionnelle)

Fichier : `tools/electron_heuristics.yaml`. Pour les icônes **sans texte** où l'OCR
échoue. Position définie par ancre (`top-left`/`bottom-left`/…) + offset relatif à
la fenêtre.

- Activation : process listé dans le YAML **et** OCR échoué.
- App non listée → couche sautée, message clair, pas de crash.
- Apps couvertes : Discord (paramètres, accueil), Slack/VSCode (à compléter terrain).

Ajouter une icône : éditer le YAML, pas de code.
```yaml
discord:
  process_name: "Discord.exe"
  icons:
    parametres:
      anchor: bottom-left
      offset_x: 220
      offset_y: -18
      aliases: ["engrenage", "settings", "réglages"]
```

## Cas d'usage F2

| CU | Commande | Stack |
|---|---|---|
| CU-1 | « Lis-moi ce qui est à l'écran » | capture + OCR full + résumé Qwen 7B |
| CU-2 | « Clique sur l'engrenage de Discord » | heuristiques Electron Discord |
| CU-3 | « Que fais-je actuellement ? » | foreground + OCR titre + résumé Qwen |
| CU-4 | « Résume cette page » | OCR full + résumé Qwen |
| CU-5 | « Que vois-tu à l'écran ? » | idem CU-1 |

CU-1/3/4/5 routés vers le tool `screen_read` (catégorie `vision`).
CU-2 reste un clic (`ui_click_element`) résolu par les heuristiques Electron.

## Diagnostic

| Symptôme | Cause | Action |
|---|---|---|
| EasyOCR jamais déclenché | Tesseract réussit toujours | normal (EasyOCR = fallback) |
| 1er appel vision lent (~5s) | Chargement modèle EasyOCR | normal, puis chaud |
| Icône Discord ratée | Offset YAML à recalibrer | ajuster `electron_heuristics.yaml` |
| App Electron non reconnue | Process absent du YAML | ajouter la section app |

## Tests

```bash
pytest tests/test_vision_v60.py -q            # 24 tests (heuristiques, stack, CU)
python scripts/compare_ocr_engines.py         # comparatif Tesseract/EasyOCR
```
