# RAPPORT SPRINT v6.0.2 — F1 Voix Partie 1 (Bloc A)

Date: 20 juillet 2026
Projet: Operation Cortana Killer / Atlas
Mission: Claude Code (session macOS), sur brief supervision "CHAT5"
Statut global: **CODE + TESTS LIVRES, CHECKPOINT SPRINT NON VALIDE** — validation micro réelle explicitement reportée par décision utilisateur (2026-07-24), non bloquant, revisité plus tard (voir section 1 et 6)

## 1. Résumé exécutif

Reprise du projet après pause. Ce sprint couvre uniquement le **Bloc A** du brief
v6.0.2 (réactivation F1 Voix Partie 1). Le **Bloc B** (validation terrain Discord/Steam)
n'a volontairement pas été traité — le brief lui-même l'exclut du périmètre code
("Ne pas coder pour ce bloc"), confirmé avec l'utilisateur en début de session.

Contrainte de session déclarée à l'utilisateur et validée par lui avant de coder :
cette session tourne sur **macOS**, alors que le brief et le code cible **Windows**
(pystray, activation micro Windows, RTX 3050). Décision actée : coder pour la
cible Windows sans l'exécuter réellement ici, en s'appuyant sur des tests
unitaires mockés côté Mac. **Aucun test avec micro réel n'a été effectué** —
ce n'est matériellement pas possible depuis cette session. Cela reste dû par
Alexis sur son poste Windows (cf. section 6).

Constat important : `core/voice_engine.py` (v4.0) et `tools/systray.py`
existaient déjà quasi complets et fonctionnels (pipeline wake word → STT → intent
→ TTS déjà câblé dans `main.py`). Le vrai gap identifié en relisant RAPPORT_V50.md
était l'absence des modèles sur disque (`data/voices/*.onnx` absent) et
`voice.enabled=false`. Le travail de ce sprint a donc porté sur : rendre le wake
word "Hey Atlas" utilisable (modèle custom, pas un mot-clé intégré OpenWakeWord),
un script de téléchargement des modèles, l'activation de la config, et la
couverture de tests correspondante.

**Décision utilisateur (2026-07-24, en cours de session)** : le modèle wake word
`hey_atlas` (`briankelley/atlas-voice-training`, release `hey_atlas-v1`) trouvé
et sourcé ce sprint est **retenu et confirmé par Alexis**, qui écarte l'autre
piste évoquée dans le brief ("Atlas V2") comme insuffisamment entraînée. L'écart
de métriques soulevé initialement (section 7) est donc considéré comme réglé —
ce sera bien `hey_atlas` en configuration. Alexis a aussi indiqué explicitement
que **les tests avec micro réel sont reportés** : ce n'est pas la priorité du
moment, ce n'est pas bloquant pour la suite du travail, et on pourra y revenir
sans souci plus tard. Je le formalise ici noir sur blanc pour que ce ne soit pas
lu comme un oubli ou un échec : **aucune commande vocale n'a été testée avec un
micro réel dans le cadre de ce sprint, par choix, pas par impossibilité
persistante.**

## 2. Objectifs vs réalisation

| Objectif (brief) | Attendu | Réalisé | Statut |
| --- | --- | --- | --- |
| Réactiver `core/voice_engine.py` | Pipeline fonctionnel | Déjà fonctionnel (v4.0) ; étendu pour wake word custom par chemin | PASS |
| Wake word "Atlas" | Modèle OpenWakeWord communautaire | `hey_atlas.onnx` (briankelley/atlas-voice-training v1) — **confirmé par Alexis** en cours de sprint, alternative "V2" du brief écartée (moins entraînée) | PASS |
| STT faster-whisper | Intégré | Déjà intégré v4.0, inchangé | PASS |
| TTS Piper FR siwis-medium | Intégré | `tts_voice` migré vers `fr_FR-siwis-medium`, modèle absent du disque tant que le script de download n'a pas tourné | PASS (code) |
| Boucle end-to-end | Wake→écoute→STT→traitement→TTS | Déjà câblée dans `main.py`, non modifiée | PASS |
| `scripts/download_voice_models.py` | Nouveau script | Livré (idempotent, 3 étapes) | PASS |
| `tests/test_voice_v602.py` | 12+ tests | 17 tests livrés, 17/17 PASS | PASS |
| `docs/voice_runbook.md` | Nouveau runbook | Livré | PASS |
| Régression 270+33+validate_v12 | 0 régression | Non exécutable intégralement sur Mac (deps Windows) — voir section 5 | PARTIEL |
| 5 commandes vocales réelles d'affilée | PASS obligatoire | **Non exécuté — reporté par décision explicite d'Alexis**, pas prioritaire ce sprint, non bloquant | REPORTÉ (décision utilisateur) |

## 3. Architecture projet mise à jour

Fichiers touchés ce sprint :

- `core/voice_engine.py` : ajout de `_resolve_wake_word_model()` (résout un
  chemin de fichier custom vs. un mot-clé OpenWakeWord intégré) ; `_init_wake_word()`
  gère les deux cas avec erreur explicite si le modèle custom est absent ;
  `_wake_detected()` utilise une clé de score dédiée (`_wake_score_key`) car
  OpenWakeWord indexe ses scores par le nom de fichier (sans extension) quand on
  lui passe un chemin, pas par le chemin complet.
- `config/settings.json` : `voice.enabled=true`, `wake_word_model` pointe vers
  `models/wakewords/hey_atlas.onnx`, `tts_voice=fr_FR-siwis-medium`, notes de
  provenance ajoutées (`_note_wake_word`, `_note_tts`).
- `scripts/download_voice_models.py` (nouveau) : télécharge modèles de support
  OpenWakeWord, wake word "Hey Atlas", voix Piper FR — idempotent, échec par étape
  isolé (un échec ne bloque pas les autres téléchargements).
- `tests/test_voice_v602.py` (nouveau, 17 tests).
- `docs/voice_runbook.md` (nouveau).
- `tools/systray.py` : non modifié — relu, déjà fonctionnel (import pystray/PIL
  différé avec fallback silencieux, states idle/listening/processing/error).
- `main.py` : non modifié — le câblage voice_engine/systray au démarrage
  existait déjà (lignes ~313-390).

Pipeline inchangé :

```
OpenWakeWord (Hey Atlas) -> sounddevice record -> faster-whisper ->
IntentClassifier/Validator/ExecutionEngine -> Piper TTS (fr_FR-siwis-medium)
```

Nouveau flux de préparation avant premier lancement :

```
python scripts/download_voice_models.py -> config/settings.json (voice.enabled=true) -> python main.py
```

## 4. Détail des implémentations par fichier

**core/voice_engine.py**
- `_resolve_wake_word_model()` : si la valeur config contient `/`, `\` ou finit
  par `.onnx`/`.tflite`, elle est traitée comme un chemin (résolu relatif à la
  racine projet si non-absolu) ; sinon comme un mot-clé OpenWakeWord intégré
  (comportement v4.0 inchangé, avec téléchargement auto via `oww_utils`).
- `_init_wake_word()` : branche "chemin custom" — vérifie l'existence du fichier,
  lève `RuntimeError` explicite renvoyant vers `scripts/download_voice_models.py`
  si absent ; sinon charge le modèle et fixe `_wake_score_key` au nom de fichier
  sans extension (ex: `hey_atlas`). Branche "mot-clé intégré" — logique v4.0
  inchangée (retry + auto-download).
- `_wake_detected()` : lit désormais le score via `_wake_score_key` au lieu de
  l'ancien `_wake_word_model` (qui contenait le chemin complet — bug potentiel
  non déclenché en v4.0 car seul un mot-clé intégré était utilisé jusqu'ici).
- Fallback par défaut de `tts_voice` mis à jour vers `fr_FR-siwis-medium`
  (n'affecte que le cas où la clé serait absente de `config/settings.json`).

**config/settings.json**
- Section `voice` : `enabled: false → true`, `wake_word_model: "hey_mycroft" →
  "models/wakewords/hey_atlas.onnx"`, `tts_voice: "fr_FR-upmc-medium" →
  "fr_FR-siwis-medium"`. Deux notes de provenance ajoutées pour tracer les
  sources et l'écart de métriques (section 7).

**scripts/download_voice_models.py** (nouveau)
- `download_file(url, dest, min_bytes)` : téléchargement streamé, écriture
  atomique via fichier `.part` puis rename, skip si déjà présent, rejet si
  taille anormalement faible (protection contre une page d'erreur HTML
  téléchargée à la place du binaire).
- `download_openwakeword_support_models()` : appelle
  `openwakeword.utils.download_models()` avec un sentinel qui ne matche aucun
  modèle officiel, pour ne récupérer que les modèles de support toujours requis
  (melspectrogram/embedding/VAD) sans télécharger les ~8 wake words officiels
  inutiles.
- `download_wake_word_model()` / `download_piper_voice()` : téléchargements
  ciblés vers `models/wakewords/` et `data/voices/`.
- `main()` : orchestration des 3 étapes, résumé, code retour non-nul si un
  échec.

**tests/test_voice_v602.py** (nouveau, 17 tests)
- Résolution du wake word (mot-clé vs chemin relatif vs chemin absolu) : 3 tests.
- `_init_wake_word` avec modèle custom (erreur si absent, chargement + score
  key si présent) : 2 tests.
- `_wake_detected` avec clé de score dédiée (détecté / sous le seuil) : 2 tests.
- Régression config (`voice.enabled`, `tts_voice`, `wake_word_model` attendus) : 1 test.
- `download_voice_models.py` (skip si présent, téléchargement, rejet fichier
  trop petit, URLs/dest attendues pour wake word et Piper, gestion absence
  openwakeword, appel avec sentinel, code retour `main()`) : 9 tests.

**docs/voice_runbook.md** (nouveau)
- Prérequis, procédure de démarrage, 4 pannes documentées (modèle wake word
  absent, permission micro Windows, GPU absent, modèle TTS absent), section
  dédiée à l'écart de métriques wake word, limites connues.

## 5. Résultats des tests

Environnement : macOS, `.venv` Python 3.12 avec les dépendances cross-platform
de `requirements-mac-manman.txt` + `pytest`/`pytest-asyncio` installés pour
cette session (pas de `pywin32`/`comtypes`/`pycaw`/`wmi` — packages Windows-only
présents dans `requirements.txt` principal).

```
pytest tests/test_voice_v602.py -v
-> 17 passed
```

```
pytest tests/test_voice_v40.py tests/test_voice_v602.py -v
-> 28 passed, 1 failed (test_10_gpu_absent_warning_no_crash)
```

`test_10` échoue sur Mac car il fait `import main`, qui importe transitivement
`tools/process_manager.py` (constantes `psutil.IDLE_PRIORITY_CLASS`,
Windows-only). **Pré-existant, confirmé en baseline avant toute modification de
ce sprint** — pas une régression introduite ici. Attendu PASS sur Windows.

Suite complète du dépôt (`pytest tests/ -q`, en excluant les fichiers dont la
collecte échoue pour des raisons déjà connues et sans rapport avec ce sprint —
`playwright` non installé, tests nécessitant un serveur Chroma/API vivant,
constantes `psutil` Windows-only) :

```
183 passed, 8 skipped, 30 failed, 4 errors
```

Les 30 échecs + 4 erreurs relèvent tous de dépendances d'environnement
(pywin32/psutil Windows, serveur ChromaDB non démarré, serveur API non
démarré) — **aucun échec dans les modules touchés par ce sprint**
(`core/voice_engine.py`, `tools/systray.py`, `config/settings.json`) en dehors
du `test_10` déjà expliqué.

**Limite honnête** : je ne peux pas revendiquer "270 pytest + 33 custom +
validate_v12 ALL PASS" comme l'exige le brief — cette validation intégrale
nécessite l'environnement Windows complet (deps `pywin32`/`comtypes`/`pycaw`/`wmi`,
serveurs Ollama/Chroma/SearXNG démarrés). Ce que je peux affirmer avec
confiance : aucune régression détectée sur ce qui est exécutable depuis macOS,
et le diff de ce sprint est scopé aux fichiers listés en section 3/4.

## 6. Comportement observé en scénarios utilisateur réels (obligatoire)

**Aucun scénario réel n'a été exécuté dans cette session — et c'est volontaire,
pas un manque.** Le brief exige explicitement "Voix testée avec micro réel
obligatoire" ; cette exigence n'est **pas remplie** par ce sprint. Alexis a
explicitement demandé de reporter les tests micro : ce n'est pas la priorité du
moment, ce n'est pas bloquant, et le sujet sera repris plus tard sans souci.
Je le note clairement pour la traçabilité du sprint, sans en faire un problème :
la stack voix (wake word, STT, TTS, boucle end-to-end) était déjà câblée avant
ce sprint (v4.0) et n'a pas été modifiée dans sa logique d'exécution — seule la
résolution du modèle wake word a changé (section 4). Le risque résiduel qu'un
souci se révèle uniquement à l'usage réel (permissions micro Windows, faux
positifs du wake word, latence) reste donc présent mais assumé et reporté.

Ce qui reste à faire par Alexis, quand il le décidera (checklist section 8) :

| ID | Scénario | Attendu | Statut |
| --- | --- | --- | --- |
| R01 | `python scripts/download_voice_models.py` | 3 téléchargements OK | À FAIRE |
| R02 | Dire "Atlas" (wake word) | Systray passe idle→listening | À FAIRE |
| R03 | "Quelle heure il est" (question simple) | STT correct + réponse TTS | À FAIRE |
| R04 | "Ferme cette fenêtre" (action) | Intent exécuté + TTS confirmation | À FAIRE |
| R05 | "Comment tu vas" (conversation) | Réponse conversationnelle TTS | À FAIRE |
| R06 | 5 commandes d'affilée sans crash | Aucun crash, systray revient idle | À FAIRE |
| R07 | Mesure latence wake→réponse audio | Valeur indicative notée | À FAIRE |

## 7. Limites et risques identifiés

| Risque | Sévérité | Détail | Mitigation |
| --- | --- | --- | --- |
| Écart métriques wake word "Atlas" | Faible (résolu) | Brief citait "V2, FA/H=0.2" ; seule source publique trouvée (`briankelley/atlas-voice-training hey_atlas-v1`) publie 81%/62%/~1.24 FA/h. **Tranché par Alexis en session : `hey_atlas` retenu**, l'alternative "V2" jugée insuffisamment entraînée. | Documenté dans `voice_runbook.md`. À affiner seulement si le taux de faux positifs réel gêne à l'usage. |
| Validation hardware réelle absente | Moyenne — **reportée par choix, pas par contrainte** | Aucun test micro/Windows n'a été fait. Le pipeline n'a jamais retourné end-to-end avec du vrai audio depuis ce sprint. Alexis a explicitement demandé de reporter ce test, ce n'est pas urgent. | Bloc de tests R01-R07 (section 6) à exécuter quand Alexis le décidera — aucune urgence, aucun blocage du reste du travail. |
| Régression full-suite non confirmée sur Windows | Moyenne | Seule la régression cross-platform (voix + ce qui tourne sans deps Windows) a été vérifiée ici. | Relancer `pytest` complet sur le poste Windows après merge. |
| `main()` de `download_voice_models.py` non exécuté réellement (seulement mocké en tests) | Moyenne | Les 3 URLs (Piper HF, wake word GitHub) ont été vérifiées comme résolvant (HTTP 302 valide pour le wake word), mais aucun octet n'a été téléchargé dans cette session — pas d'exécution de téléchargement de fichier sans confirmation explicite. | Premier `python scripts/download_voice_models.py` réel à faire par Alexis — sera aussi le premier test de bout en bout du script. |
| Latence STT sans GPU | Faible | Non mesurée ce sprint (indicatif v6.1). | `stt_device` configurable cpu/cuda. |

## 8. Checklist de validation (avec preuves)

- [x] `core/voice_engine.py` supporte un wake word custom par chemin de fichier — `tests/test_voice_v602.py::test_02,03,05`
- [x] Erreur explicite si modèle wake word custom absent — `tests/test_voice_v602.py::test_04`
- [x] `config/settings.json` : `voice.enabled=true`, `tts_voice=fr_FR-siwis-medium`, `wake_word_model` pointe vers le modèle custom — `tests/test_voice_v602.py::test_08`
- [x] `scripts/download_voice_models.py` livré, idempotent, testé unitairement — `tests/test_voice_v602.py::test_09-17`
- [x] `docs/voice_runbook.md` livré
- [x] `pytest tests/test_voice_v602.py` → 17/17 PASS
- [x] `pytest tests/test_voice_v40.py` → 11/12 PASS (1 échec pré-existant Windows-only, documenté)
- [ ] Wake word "Atlas" détecte réellement (micro réel) — **reporté par décision utilisateur (2026-07-24), non bloquant**
- [ ] STT transcrit réellement une commande vocale — **reporté, idem**
- [ ] TTS répond réellement à voix haute — **reporté, idem**
- [ ] 5 commandes vocales d'affilée réelles sans crash — **reporté, idem**
- [ ] 270 pytest + 33 custom + validate_v12 ALL PASS sur environnement Windows complet — **non vérifiable depuis macOS, à faire quand Alexis reprend le poste Windows**
- [x] Bloc B non codé, conformément au brief et à la décision utilisateur de début de session
- [x] Choix du wake word "hey_atlas" confirmé par Alexis en session (2026-07-24)

**Conclusion checkpoint (section 5 du brief) : sprint NON validé au sens strict
du brief**, mais par un choix assumé d'Alexis et non par un blocage technique. Le
code, le wake word retenu, les modèles (script de download), les tests
unitaires et la doc sont livrés et prêts à l'usage. La validation réelle (micro,
5 commandes, régression Windows complète) est volontairement reportée — rien
n'empêche de l'exécuter dès que ce sera la priorité.

## 9. Recommandations pour le sprint suivant

1. **Pas d'urgence sur les tests micro** : reportés par choix d'Alexis, à
   reprendre quand ce sera la priorité (probablement avant la démo B3, pas
   nécessairement tout de suite). Quand ce sera le cas :
   `scripts/download_voice_models.py` sur le poste Windows, puis les scénarios
   R01-R07 (section 6).
2. Le choix du wake word est tranché (`hey_atlas`) — pas d'action requise sauf
   si le taux de faux positifs gêne à l'usage une fois testé.
3. Si le taux de faux positifs réel dépasse ce qui est jugé acceptable pour la
   démo, envisager l'entraînement d'un wake word custom (mentionné comme
   optionnel v6.1 dans le brief) — le pipeline `_resolve_wake_word_model()`
   livré ce sprint supporte déjà nativement un modèle custom par chemin, donc
   aucun changement de code ne serait requis, seulement un nouveau fichier
   `.onnx` et une mise à jour de config.
4. Une fois la validation hardware Windows faite (quand Alexis le décidera),
   relancer la suite pytest intégrale (`pytest tests/ -q`) pour confirmer les
   270+33+validate_v12 réellement, ce qui n'a pas pu être fait depuis cette
   session macOS.
5. Le reste de la roadmap (v6.0.3 F1 Partie 2, ou v6.1 F5 UI démo) peut
   avancer sans attendre la validation micro — rien dans ce sprint ne bloque
   dessus.

---

Rapport v6.0.2 (Bloc A) généré par Claude (Claude Code, session macOS).
Statut: code/tests/doc livrés, wake word "hey_atlas" confirmé par Alexis —
validation terrain réelle (micro Bloc A + Bloc B) reportée par choix explicite
de l'utilisateur, non bloquant, à reprendre sans souci quand ce sera prioritaire.
