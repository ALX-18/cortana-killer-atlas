# RAPPORT SPRINT v4.0 — Voix & Presence

Date: 26 mars 2026
Projet: Operation Cortana Killer
Mission: CHAT4

## 1. Resume executif

Le sprint v4.0 est mis a jour selon la decision Atlas #2 revisee: wake word migre de Porcupine vers OpenWakeWord (zero compte, zero cle, zero cloud).

Stack effective:

- Wake word: OpenWakeWord
- STT: faster-whisper int8
- TTS: Piper
- Systray: pystray

Statut global:

- Migration wake word OpenWakeWord: TERMINEE
- Tests v4.0 voix: 12/12 PASS
- Regressions v3.1 + v3.0: 20/20 PASS
- Regressions consolidees historiques deja validees: 37/37 PASS (campagne precedente)
- Scenarios reels voix section 6: en attente d'execution complete sur PC

## 2. Objectifs vs realisation

| Objectif | Attendu | Realise | Statut |
| --- | --- | --- | --- |
| Wake word zero-cle | OpenWakeWord local | Integre dans voice_engine | PASS |
| Pipeline voix | Wake -> STT -> Intent -> TTS | Livre et branche | PASS |
| Systray | Ouvrir / Voix ON-OFF / Quitter + etats | Livre | PASS |
| Config voix | enabled=false + params OpenWakeWord | Livre | PASS |
| Reponse TTS courte | generate_speech_response sans markdown | Livre | PASS |
| Tests v4.0 | 12 tests | 12/12 PASS | PASS |
| Regressions | 0 regression cibles | 20/20 PASS | PASS |
| Scenarios reels R01-R06 | 5/6 minimum | A executer | EN COURS |

## 3. Architecture projet mise a jour

Fichiers majeurs v4.0:

- core/voice_engine.py: wake listener OpenWakeWord, capture micro, STT, execution pipeline, TTS.
- tools/systray.py: systray Windows avec etats idle/listening/processing/error.
- main.py: startup/shutdown voix + systray conditionnels, warning GPU degrade.
- core/ollama_client.py: suffixe de reponse vocale courte, sans markdown.
- config/settings.json: section voice OpenWakeWord.
- requirements.txt: dependances voix OpenWakeWord + ONNX runtime.
- tests/test_voice_v40.py: couverture v4.0 (12 tests).

Pipeline:

OpenWakeWord -> record audio -> faster-whisper -> IntentClassifier/Validator/ExecutionEngine -> Piper TTS

## 4. Detail des implementations (par fichier)

- core/voice_engine.py

  - Remplacement Porcupine par OpenWakeWord dans _init_wake_word().
  - Aucune cle API requise.
  - Detection threshold configurable (wake_word_threshold).
  - Stream audio micro + queue asynchrone + anti-retrigger cooldown.
  - Pipeline text existant reutilise sans duplication.

- config/settings.json

  - Bloc voice migre:
    - enabled=false
    - wake_word_model=hey_mycroft
    - wake_word_threshold=0.5
    - stt_model/base + langue fr + device cuda
    - tts_voice fr_FR-upmc-medium
    - note migration Porcupine isolee dans _init_wake_word()

- requirements.txt

  - Remplacement pvporcupine par openwakeword.
  - Ajout explicite onnxruntime.

- tests/test_voice_v40.py

  - Tests adaptes OpenWakeWord (mock wake model, plus de reference Porcupine).

## 5. Resultats des tests et non-regression

Execution locale apres migration:

- pytest tests/test_voice_v40.py -q -> 12/12 PASS
- pytest tests/test_stabilisation_v31.py tests/test_automation_v30.py -q -> 20/20 PASS

Regression historique deja validee sur cette branche:

- pytest tests/test_chroma_integration.py tests/test_voice_v40.py tests/test_stabilisation_v31.py tests/test_automation_v30.py -q -> 37/37 PASS

Conclusion:

- Migration OpenWakeWord sans regression detectee sur les suites ciblees.

## 6. Scenarios reels v4.0 (PC local)

Campagne demandee:

| ID | Scenario | Attendu | Statut |
| --- | --- | --- | --- |
| R01 | Dire wake word | Micro actif + systray listening | A faire |
| R02 | "Ouvre le bloc-notes" vocal | Bloc-notes ouvert + TTS | A faire |
| R03 | "Cherche la meteo a Paris" vocal | Recherche + TTS | A faire |
| R04 | "Active le mode gaming" vocal | Workflow + TTS | A faire |
| R05 | Systray visible | Icone Atlas presente | A faire |
| R06 | Toggle Voix ON/OFF systray | Menu fonctionnel | A faire |

Critere de passage scenario reel:

- Minimum 5/6 PASS.

## 7. Limites et risques identifies

1. Performance machine: qwen peut etre lent selon RAM/VRAM disponible, impact indirect sur ressenti vocal.
2. STT CPU degrade: warning present, latence plus elevee sans CUDA.
3. TTS depend du modele local Piper (fr_FR-upmc-medium.onnx) present sur disque.
4. OpenWakeWord premier lancement: telechargement initial des modeles requis.

## 8. Checklist de validation v4.0

- [ ] Wake word detecte -> micro actif
- [ ] Phrase vocale -> STT -> intent -> action executee
- [ ] Reponse lue via Piper TTS
- [ ] Icone Atlas visible en systray
- [ ] Menu systray Ouvrir / Voix ON-OFF / Quitter fonctionnel
- [ ] Indicateur systray idle/listening/processing/error
- [x] voice.enabled=false par defaut
- [x] Warning GPU absent present
- [x] pytest tests/test_voice_v40.py -> 12/12 PASS
- [x] 0 regression suites cibles (20/20 PASS)
- [x] Reponses vocales sans markdown

Seuil passage v5.0:

- Checklist complete + scenarios reels >= 5/6.

## 9. Plan de continuation immediat

1. Executer les 6 scenarios reels R01-R06 sur machine locale.
2. Documenter evidences (logs + observations utilisateur) dans cette section.
3. Valider score final (>=5/6) et mettre a jour checklist.
4. Si valide, soumettre gate v5.0.

---

Rapport v4.0 genere par CHAT4 (GPT 5.3 Codex).
Statut: migration OpenWakeWord terminee et testee, validation reelle section 6 en cours.
