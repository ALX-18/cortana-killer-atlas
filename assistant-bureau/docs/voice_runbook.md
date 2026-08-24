# Atlas Voice Runbook (v6.0.2 — F1 Voix Partie 1)

## Scope
Démarrage et dépannage de la pile voix : wake word "Hey Atlas" (OpenWakeWord) →
capture micro (sounddevice) → STT (faster-whisper) → pipeline intent existant →
TTS (Piper FR). Couvre l'installation, les permissions Windows, et les pannes
les plus probables en usage réel.

Ce runbook cible **Windows** (plateforme de test réelle du sprint). Le code a
été écrit/révisé depuis une session macOS ; la validation micro/hardware réelle
est reportée par décision explicite d'Alexis (2026-07-24) — pas urgent, pas
bloquant, à reprendre quand ce sera la priorité (cf. RAPPORT_V602.md section 6).

## 0) Prérequis avant premier démarrage

1. Dépendances Python installées (`pip install -r requirements.txt`) — inclut
   `openwakeword`, `faster-whisper`, `piper-tts`, `sounddevice`, `pystray`, `onnxruntime`.
2. Modèles voix téléchargés :
   ```
   cd assistant-bureau
   python scripts/download_voice_models.py
   ```
   Ce script télécharge, de façon idempotente (ne re-télécharge pas ce qui existe déjà) :
   - Les modèles de support OpenWakeWord (melspectrogram/embedding/VAD) — installés
     dans le dossier `resources/models` du package `openwakeword`.
   - Le wake word custom **Hey Atlas** (`hey_atlas.onnx`) dans `models/wakewords/`.
     Source : [briankelley/atlas-voice-training, release `hey_atlas-v1`](https://github.com/briankelley/atlas-voice-training/releases/tag/hey_atlas-v1).
   - La voix Piper FR **fr_FR-siwis-medium** dans `data/voices/`.
     Source : [rhasspy/piper-voices (Hugging Face)](https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR/siwis/medium).
3. `config/settings.json` → `voice.enabled = true` (déjà activé par ce sprint).
4. Micro système fonctionnel et sélectionné comme périphérique d'entrée par défaut Windows.

## 1) Wake word retenu : hey_atlas

Le brief de sprint citait un modèle "Atlas V2" avec FA/H=0.2 (audit S21). Le
seul modèle "Hey Atlas" public et vérifiable trouvé pour ce sprint est
`briankelley/atlas-voice-training` (`hey_atlas-v1`), dont l'auteur publie :
**81% accuracy / 62% recall / ~1.24 faux positifs par heure** — des chiffres
différents de ceux cités dans le brief. **Alexis a tranché en session
(2026-07-24) : c'est `hey_atlas` qui est retenu**, l'autre piste évoquée dans le
brief étant jugée insuffisamment entraînée. Pas d'action requise sur ce point
sauf si le taux de faux positifs gêne concrètement à l'usage une fois testé.

**Quand les tests micro reprendront** (reportés pour l'instant, non urgent) :
mesurer le taux de faux positifs réel en conditions Windows (bruit ambiant, TV,
musique) pendant au moins 30 min d'écoute passive avant de considérer le seuil
`wake_word_threshold=0.5` comme définitif. Si trop de faux déclenchements :
augmenter `wake_word_threshold` dans `config/settings.json` (section `voice`)
par paliers de 0.05.

## 2) Démarrage

Le voice engine démarre automatiquement avec `main.py` si `voice.enabled=true` :
```
python main.py
```
L'icône systray (plateau Windows) apparaît et bascule de couleur selon l'état :
- Bleu (`idle`) : en écoute passive du wake word.
- Vert (`listening`) : wake word détecté, enregistrement de la commande.
- Orange (`processing`) : STT + pipeline intent en cours.
- Rouge (`error`) : erreur sur le dernier cycle (voir logs).

Clic droit sur l'icône → "Voix OFF/ON" pour couper/relancer sans redémarrer l'app.

## 3) ERR_VOICE_WAKEWORD_MODEL_MISSING
Symptoms:
- Au démarrage : `RuntimeError: Modele wake word custom introuvable: ...`
- Logs : `VoiceEngine demarrage echoue`

Checks:
1. Vérifier que `models/wakewords/hey_atlas.onnx` existe.
2. Vérifier `config/settings.json` → `voice.wake_word_model` (chemin relatif attendu :
   `models/wakewords/hey_atlas.onnx`).

Recovery:
1. `python scripts/download_voice_models.py`
2. Relancer `main.py`.

## 4) ERR_VOICE_MIC_PERMISSION (Windows)
Symptoms:
- Aucune détection de wake word, aucune erreur explicite dans les logs.
- `sounddevice.InputStream` lève une exception silencieuse ou reste muet.

Checks:
1. Windows Réglages → Confidentialité et sécurité → Microphone → autoriser les
   applications de bureau à accéder au microphone.
2. Vérifier le périphérique d'entrée par défaut (Réglages → Son → Entrée).
3. `python -c "import sounddevice as sd; print(sd.query_devices())"` pour lister
   les périphériques détectés.

Recovery:
1. Activer l'accès micro pour les applications de bureau.
2. Redémarrer `main.py` après changement de permission (le stream est ouvert au démarrage).

## 5) ERR_VOICE_GPU_MISSING (latence STT élevée)
Symptoms:
- Log au démarrage : `Atlas Voice : aucun GPU CUDA detecte. La transcription STT
  sera lente (~3-5s).`

Checks:
1. `nvidia-smi` (GPU détecté ?).
2. `voice.stt_device` dans `config/settings.json` (actuellement `"cuda"`).

Recovery:
1. Sur poste sans GPU dédié : passer `stt_device` à `"cpu"` (latence plus élevée
   mais fonctionnel).
2. Sur RTX 3050 : vérifier les drivers CUDA à jour.

## 6) ERR_VOICE_TTS_MODEL_MISSING
Symptoms:
- Pas de réponse audio après une commande traitée avec succès (texte présent dans les logs).
- Log : `Piper model not found: .../data/voices/fr_FR-siwis-medium.onnx`

Checks:
1. Vérifier `data/voices/fr_FR-siwis-medium.onnx` et `.onnx.json`.

Recovery:
1. `python scripts/download_voice_models.py`

## 7) Tests

```
pytest tests/test_voice_v40.py tests/test_voice_v602.py -v
```

`test_10_gpu_absent_warning_no_crash` (dans `test_voice_v40.py`) échoue sur macOS :
il importe `main.py`, qui importe transitivement `tools/process_manager.py`
(constantes `psutil.IDLE_PRIORITY_CLASS` etc., Windows uniquement). C'est une
limitation d'environnement connue, pas une régression — attendu PASS sur Windows.

## 8) Limites connues (v6.0.2 Partie 1)
- Pas d'interruption mid-speech (VAD pendant TTS) — prévu v6.1.
- Wake word "Hey Atlas" est un modèle communautaire, pas entraîné spécifiquement
  pour ce projet — recall modeste (62% publié par l'auteur), à valider en conditions réelles.
- Latence bout-en-bout non optimisée — mesure indicative uniquement ce sprint.
