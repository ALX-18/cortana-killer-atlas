# Brief v5.1 — Reprise Voix Atlas

## Motif d'ouverture
Phase 2 v5.0 non activable: critère "modèle Piper FR disponible" non satisfait.

## Préconditions de reprise
1. Ajouter le modèle: `data/voices/fr_FR-upmc-medium.onnx`.
2. Vérifier le fichier JSON voix associé si requis (`.onnx.json`).
3. Vérifier l'environnement unique: utiliser uniquement `C:\Users\alexis\Cortana_Killer\.venv`.

## Objectifs v5.1
1. Stabiliser le cycle de vie voix au redémarrage (start/stop propre du listener).
2. Geler dépendances voix dans `requirements-voice.txt`.
3. Livrer script de démarrage préflight (`start_atlas.bat`).
4. Exécuter campagne réelle R01-R06, seuil >= 5/6 PASS.

## Critères de sortie v5.1
- Voice ON/OFF stable via systray
- Wake word opérationnel
- TTS fonctionnel sur commandes vocales
- Rapport R01-R06 joint avec traces
