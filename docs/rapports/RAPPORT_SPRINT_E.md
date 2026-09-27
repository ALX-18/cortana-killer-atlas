# RAPPORT SPRINT E — La chaîne vocale, pour de bon
Date: 25/09/2026
Agent: Claude Opus 5 (CHAT6, Claude Code Windows)

> Brief : `docs/briefs/BRIEF_SPRINT_E_VOIX.md`. Références : rapport A (L1, L2, L3, C04, R02-R07), rapport D (inventaire, D-R11).
> Branche **`sprint-e`**, issue de `main` @ `68d3a13`. 6 commits, **non poussés**.

---

## 1. Résumé exécutif

**Statut global : VALIDÉ**, avec un échec franc sur un point et une limite qui vient du modèle, pas du code.

**La réponse à la question du brief — Atlas entend-il, comprend-il et répond-il à voix haute, avec Alexis au micro ? Oui.** Séance réelle du 24/09, 19 h 48 à 19 h 58 : **29 réveils, 25 cycles complets**, transcription sur GPU en 0,3 s médiane, réponses parlées par Piper. Les trois pannes du sprint A sont mortes.

| Défaut | Avant | Après | Preuve |
|---|---|---|---|
| **L1** mot d'éveil | score 0,0008 — impossible à déclencher | **0,995** | WAV réel dans le vrai code, puis 29 réveils au micro |
| **L2** transcription GPU | `cublas64_12.dll is not found` | **0,3 s médiane sur GPU** | 25 transcriptions réelles |
| **L3** synthèse | muette, exception avalée | **Atlas parle** | 25 réponses parlées, Piper |
| **C04** santé | `voice: running: true` sur une voix morte | capacité réelle détaillée | §4.4 |

**Ce qui a échoué : R04.** « Ferme la fenêtre Steam » a fermé Steam **instantanément, sans confirmation ni notification**. En cherchant pourquoi, j'ai trouvé un défaut de sécurité : le validateur lève bien le drapeau « confirmation requise », **et le moteur d'exécution l'ignore**. Seuls `kill_process`, `run_powershell` et `system_config` déclenchent une confirmation. **L'annexe A du rapport B1 affirmait le contraire** — correction en §7, D-E1. Sur décision d'Alexis, la réparation fera l'objet d'un brief dédié.

**Ce qui vient du modèle, pas du code.** R02 : Alexis compte **3 à 5 échecs sur dix** « Hey Atlas », soit 50 à 70 % de réussite. C'est exactement le **recall de 62 %** publié par l'auteur du modèle. Le code est hors de cause ; le modèle est la limite.

**Deux découvertes utiles au micro, corrigées dans la foulée.**
- Les noms d'applications étaient massacrés : « au péra » pour Opera, « stim » pour Steam, « dix cordes » pour Discord. La liste des applications connues est désormais soufflée au modèle : mesuré **2 noms corrects sur 5 → 5 sur 5**.
- La fenêtre Atlas n'indiquait rien sur la voix, et mon premier protocole lançait le backend sans interface. Corrigé : **voyant d'écoute** dans la fenêtre et dans la zone de notification.

**Une lacune que j'ai créée puis corrigée** : mon suivi d'écoute interrogeait `/api/health` toutes les 2 s, endpoint qui sonde Ollama et SearXNG à chaque appel. La fenêtre s'est remplie de « Health check failed ». Corrigé par un point d'accès léger (0,21 s) et une mise en cache des sondes.

**Prélude mémoire fait et vérifié**, dans son commit séparé : 253 éléments supprimés selon le tableau du brief, `atlas_memory` intacte, **qualité du rappel améliorée** plutôt que dégradée.

**Tests** : 12 nouveaux sur du **vrai audio et le vrai code**, plus 5 garde-fous de nettoyage sur client simulé. Suite complète : **654 passés, 4 ignorés, code 0**.

**État à l'heure du rapport :** conteneurs ChromaDB et SearXNG démarrés, Ollama 0.34.1, collection `atlas_memory_e5` active, Atlas arrêté.

---

## 2. Objectifs vs réalisation

| Objectif (brief) | Résultat réel | Statut |
|---|---|---|
| **Prélude** — collection active confirmée | Démarrage réel : `ChromaDB connecté — collection 'atlas_memory_e5'` | PASS |
| **Prélude** — notifications B1T-R2 constatées | Deux notifications Windows (Mode Gaming, Nettoyage Système), journalisées et vues à l'écran | PASS |
| **Prélude** — sauvegarde vérifiée | `chromadb_20260924_182312`, restauration prouvée | PASS |
| **Prélude** — suppressions selon le tableau | 253 identifiants : 15+10+3 artefacts, 225 doublons. Décomptes conformes au plan | PASS |
| **Prélude** — `atlas_memory` intacte | 489 éléments, inchangée. `atlas_conversations` intacte | PASS |
| **Prélude** — qualité du rappel non dégradée | hit@3 **64 % → 71 %**, hit@5 10/14 → 11/14 | PASS |
| **Prélude** — commit séparé | `65ab270`, avant tout travail vocal | PASS |
| Tests rouges d'abord, **vrai audio et vrai code** pour L1 et L3 | 12 tests, rouges d'abord. `predict` et `_speak_sync` **non simulés** ; seuls le micro et le haut-parleur le sont | PASS |
| E1 — mot d'éveil sur WAV réel | 0,0008 → 0,995, puis 29 réveils au micro | PASS |
| E2 — transcription GPU, **Blackwell vérifiée** | 0,3 s médiane sur `cuda`. CTranslate2 4.7.1 reconnaît la RTX 5060 sans recompilation | PASS |
| E3 — Piper produit du son, version épinglée, échecs journalisés | `piper-tts==1.4.1`, itérable d'`AudioChunk`, tout échec journalisé | PASS |
| Repli SAPI fonctionnel, journalisé, visible | `pyttsx3`, testé, annoncé dans les journaux et dans `/api/health`. **Jamais déclenché en réel** (D-E6) | PARTIEL |
| E4 — `/api/health` reflète la capacité réelle | `wake_word`, `stt`, `tts`, `ok`, `degraded_reason`, `activity` | PASS |
| E5 — action à confirmation demandée à la voix | Réponse parlée explicite + notification. **Mais `window_close` ne demande jamais de confirmation** : le chemin n'a donc pas pu être éprouvé en réel (D-E1) | PARTIEL |
| E5 — confirmation vocale réelle : analyse, **pas d'implémentation** | Annexe A. Aucun code écrit | PASS |
| E6 — VRAM remesurée avec transcription GPU | Pic **6 674 Mo sur 8 151 (82 %)**, chaîne complète | PASS |
| **E7 — R02 à R08 avec Alexis au micro** | Exécuté, deux séances. Détail en §6.3 | PASS |
| `python -m pytest tests/ -q` → code 0 | 654 passés, 4 ignorés | PASS |

---

## 3. Architecture projet mise à jour

```
cortana-killer-atlas/
├── core/
│   └── voice_engine.py                      ← modifié (int16, CUDA, Piper, SAPI, états, traces, amorçage)
├── api/
│   └── routes.py                            ← modifié (/api/health véridique, /api/voice/state, cache des sondes)
├── tools/
│   └── systray.py                           ← modifié (états lisibles, anneau d'écoute)
├── desktop/
│   └── atlas_desktop.py                     ← modifié — HORS PÉRIMÈTRE, sur demande d'Alexis (voyant d'écoute)
├── scripts/
│   ├── memory_cleanup.py                    ← NOUVEAU sprint E (prélude, protège atlas_memory)
│   └── doctor.py                            ← modifié (cuBLAS/cuDNN, repli SAPI)
├── tests/
│   ├── test_voice_chain_e.py                ← NOUVEAU sprint E (12 tests, vrai audio)
│   ├── test_memory_cleanup_guard_e.py       ← NOUVEAU sprint E (5 garde-fous, client simulé)
│   ├── test_final_v50.py                    ← modifié (fragilité : dépendait des processus ouverts)
│   └── fixtures/                            ← NOUVEAU : 5 fichiers audio 16 kHz mono
│       ├── hey_atlas_16k.wav                     « Hey Atlas », voix anglaise
│       ├── cmd_discord_fr.wav / cmd_steam_fr.wav / cmd_opera_fr.wav
│       └── cmd_conversation_fr.wav               contrepartie sans nom d'application
├── docs/
│   ├── voice_runbook.md                     ← modifié (prononciation, CUDA, synthèse, confirmation)
│   └── PROTOCOLE_VALIDATION_VOCALE_E.md     ← NOUVEAU sprint E (remis à Alexis)
├── requirements.txt                         ← modifié (piper-tts épinglé, pyttsx3, nvidia-cublas/cudnn)
└── config/settings.json                     ← inchangé ce sprint (déjà à jour depuis D)
```

Six commits : `65ab270` (prélude, séparé), `20ec8da` (les trois pannes), `1024c80` (voyant + traces), `655cc94` (protocole), `8ea4c95` (correction du déluge d'erreurs), `1eff647` (noms d'applications).

---

## 4. Détail des implémentations

### 4.1 E1 — le mot d'éveil

`_wake_callback` faisait `pcm.astype(np.float32) / 32768.0` avant d'appeler `predict`. openWakeWord attend du **PCM int16 brut** : la division écrasait l'amplitude et le score tombait à 0,0008, sous un seuil de 0,50. Le mot d'éveil ne pouvait pas se déclencher, quel que soit le micro. Une ligne supprimée.

Mesure sur le même fichier audio, avant et après : **0,0008 → 0,995**.

`_wake_score()` est extrait de `_wake_detected()` pour que le score soit journalisé et exposé.

**Découverte importante pour l'usage.** Le modèle `hey_atlas.onnx` est entraîné sur « Hey Atlas » prononcé **à l'anglaise**. La même phrase par la voix française de Piper marque **0,0008**, soit aucun déclenchement. C'est écrit dans le runbook et dans le protocole remis à Alexis : sans cette consigne, la validation aurait échoué pour une raison sans rapport avec le code.

### 4.2 E2 — la transcription sur GPU

Deux choses manquaient, et une supposition était fausse.

- **Les bibliothèques.** `nvidia-cublas-cu12` et `nvidia-cudnn-cu12` (décision du superviseur, pas de CUDA Toolkit) étaient absentes. Installées et déclarées dans `requirements.txt`.
- **Le chemin de recherche.** Les installer ne suffit pas : CTranslate2 charge ces DLL par le chemin de recherche du **processus**. `os.add_dll_directory` seul ne marche pas — vérifié, l'erreur persistait. `ensure_cuda_libraries()` ajoute les répertoires à `PATH` **avant** le premier chargement du modèle.
- **Blackwell : vérifié, pas supposé.** CTranslate2 4.7.1 répond `get_cuda_device_count() = 1` et propose `float16`, `int8`, `bfloat16` sur la RTX 5060. Aucune recompilation nécessaire.

**Mesures :** chargement du modèle 1,3 s ; première transcription 5,5 s (noyaux CUDA + détecteur de voix) ; ensuite **0,09 à 0,3 s**. Sur processeur, le sprint A mesurait environ 5,3 s.

Le coût du premier appel est désormais payé au démarrage, en tâche de fond (`_prewarm_stt`) : constaté dans les journaux d'Alexis, « Transcription préchauffée en 6,5 s (device=cuda) ».

**Le repli processeur reste possible, mais il est bruyant** : `logger.error` explicite et `/api/health` le signale. Un repli silencieux sur une chaîne vocale est un piège — 5 s au lieu de 0,3 s.

### 4.3 E3 — la synthèse vocale

Trois défauts dans la même fonction.

1. `voice.synthesize(text)` renvoie un **itérable d'`AudioChunk`** depuis piper-tts 1.3 ; le code attendait un tuple `(samples, rate)`. Corrigé : concaténation des `audio_int16_array`.
2. `except Exception: pass` avalait tout. C'est la raison pour laquelle personne n'a vu que la voix était muette pendant des mois. Chaque échec est désormais journalisé avec son type.
3. Le repli décidé au sprint 0 n'existait pas. `_speak_sapi()` utilise la voix intégrée de Windows (`pyttsx3`) : aucun modèle, aucune VRAM. Le basculement est journalisé et visible dans `/api/health`.

Version **épinglée** : `piper-tts==1.4.1`. La dérive d'API entre versions est précisément ce qui a cassé la voix.

**Mesures Piper :** synthèse de 0,35 à 0,55 s pour une phrase ordinaire, soit 0,11 à 0,13 fois le temps réel. Le temps de « parole » est donc surtout de la lecture audio, pas du calcul.

### 4.4 E4 — un indicateur de santé qui dit vrai

`/api/health` annonçait `voice: {enabled: true, running: true}` sur une chaîne incapable de fonctionner. Il décrit maintenant la **capacité** :

```json
"voice": {"enabled": true, "running": true, "activity": "repos", "ok": true,
          "degraded_reason": [],
          "wake_word": {"model_present": true, "loaded": true, "threshold": 0.5, "last_score": 0.99},
          "stt": {"device_configured": "cuda", "device_used": "cuda", "cublas_available": true},
          "tts": {"piper_ready": true, "sapi_fallback_available": true, "backend_last_used": "piper"}}
```

`degraded_reason` énumère en français ce qui manque. Un système qui affirme fonctionner alors qu'il ne fonctionne pas est plus dangereux qu'un système qui avoue être en panne — c'est le même principe que l'anomalie A du sprint B1-ter.

### 4.5 E5 — confirmation vocale : le minimum sûr

Avant, une action exigeant une confirmation renvoyait… **« C'est fait. »** Le résumé parlé ne trouvait aucun message à lire et tombait sur cette phrase par défaut. Atlas affirmait avoir agi alors que rien n'était fait.

Désormais : réponse parlée « Cette action nécessite une confirmation à l'écran. Je ne l'ai pas exécutée. », notification Windows avec le motif, journalisation, et l'état « problème » dans l'indicateur.

**Limite majeure, découverte par la séance au micro :** ce chemin ne se déclenche jamais pour `window_close`, parce que **le moteur ignore le drapeau de confirmation du validateur** (§7, D-E1). Le mécanisme est donc prouvé par test, pas en usage réel.

### 4.6 Demande d'Alexis — voir quand Atlas écoute

Hors périmètre du brief, fait sur sa demande explicite, dans un commit séparé.

- Le moteur expose une **activité** (`repos`, `écoute`, `réfléchit`, `parle`), source unique pour l'icône et la fenêtre.
- Zone de notification : couleur par état, **anneau clair pendant l'écoute**, infobulle en français.
- Fenêtre Atlas : carte « Voix » avec voyant, état et cause de panne, rafraîchie toutes les 1,5 s.
- `start_atlas_desktop.bat` est désormais le lancement recommandé dans le protocole. Ma première version lançait `main.py` seul, sans interface : erreur de ma part, relevée par Alexis.

**Correction d'une lacune que j'avais introduite.** Mon premier suivi appelait `/api/health` toutes les 2 s, or cet endpoint sonde Ollama et SearXNG à chaque appel : les requêtes s'empilaient et la fenêtre s'est remplie de « Health check failed ». Trois corrections :
- `/api/voice/state`, sans aucune sonde réseau : **0,21 s** contre 1,4 s ;
- sondes externes de `/api/health` en cache 10 s : 1,4 s puis **0,27 s** ;
- un échec du suivi n'écrit plus dans la conversation ; le voyant affiche « backend indisponible (démarrage en cours ?) », ce qui est le cas pendant la vingtaine de secondes de chargement des modèles, alors que le lanceur n'attend que 3 s.

### 4.7 Traces du cycle vocal, et noms d'applications

**Les traces.** La première séance d'Alexis n'a laissé **aucune mesure exploitable** : le moteur ne journalisait ni les réveils, ni les transcriptions, ni les durées. J'avais promis des mesures issues des journaux, elles étaient impossibles. Chaque cycle écrit maintenant :

```
[VOIX] Mot d'éveil détecté (score=0.990, seuil=0.50) — j'écoute.
[VOIX] Transcription (0.27s, cuda) : 'ferme la fenêtre steam'
[VOIX] Cycle : écoute 3.9s + transcription 0.25s + réflexion 2.4s + parole 2.0s = 8.5s depuis le mot d'éveil (moteur=piper) — réponse : "Fenêtre 'Steam' fermée."
```

**Les noms d'applications.** La liste des applications connues est passée en amorçage au modèle (`initial_prompt`). Mesure sur des phrases françaises synthétisées, qui reproduisent les erreurs réelles d'Alexis :

| Phrase | Sans amorçage | Avec amorçage |
|---|---|---|
| ouvre Discord | « ouvre 10 cordes » | **« Ouvre Discord »** |
| lance Steam s'il te plaît | « L'enstein s'il te plaît ? » | **« Lance Steam s'il te plaît »** |
| lance Opera GX | « Lance opéra GX » | **« Lance Opera Gx »** |

**2 noms corrects sur 5 → 5 sur 5**, sans coût en VRAM. Une contrepartie vérifie qu'une phrase ordinaire ne se voit pas injecter de nom d'application.

---

## 5. Résultats des tests

### État rouge, avant correction

Chaque défaut a été vu rouge, avec un message qui montre le défaut lui-même.

```
python -m pytest tests/test_voice_chain_e.py -q -p no:cacheprovider -rf --tb=line

test_e1_mot_deveil_declenche_sur_un_wav_reel - AssertionError: mot d'éveil non détecté sur un WAV réel (meilleur score observé : 0.0) — l'audio n'atteint pas le modèle dans le format attendu
test_e1_audio_transmis_au_modele_en_int16   - AssertionError: audio transmis en float32, openWakeWord attend int16
test_e2_transcription_gpu_sur_audio_reel    - RuntimeError: Library cublas64_12.dll is not found or cannot be loaded
test_e3_piper_produit_du_son                - AssertionError: durée invraisemblable : 0.00 s
test_e3_echec_de_synthese_journalise        - AssertionError: échec non journalisé
test_e3_repli_sapi_quand_piper_echoue       - AssertionError: repli SAPI non annoncé dans les journaux : tts unavailable: [winerror 2] le fichier spécifié est introuvable
test_e4_sante_reflete_la_capacite_reelle    - AssertionError: /api/health ne dit rien de 'wake_word' : il annonce seulement ['enabled', 'running']
test_e5_action_a_confirmation_est_annoncee   - AssertionError: Atlas annonce une action faite alors qu'une confirmation est en attente : "C'est fait."
test_e2bis_nom_application[discord]         - AssertionError: nom d'application non reconnu : Atlas a compris 'ouvre 10 cordes.' au lieu de « discord »
test_e2bis_nom_application[steam]           - AssertionError: nom d'application non reconnu : Atlas a compris "L'enstein s'il te plaît ?" au lieu de « steam »
```

Le `L2` est l'erreur exacte du sprint A. Le `"C'est fait."` de E5 est la phrase qu'Atlas prononçait alors que rien n'était fait.

**Ce que ces tests ne simulent pas**, contrairement aux 17 tests de v6.0.2 jugés tautologiques par l'audit A.2 : ni `predict`, ni `_init_wake_word`, ni `_speak_sync`, ni `transcribe`. Un vrai WAV traverse le vrai rappel audio et le vrai modèle ; la vraie synthèse Piper produit un vrai tableau audio ; la vraie transcription tourne sur le GPU. Seuls le **micro** (`sounddevice.InputStream`) et le **haut-parleur** (`sounddevice.play`) sont remplacés, pour que la suite n'ouvre pas le micro et ne parle pas toute seule.

**Deux rectifications de mes propres tests, à signaler.**
1. `test_e1_mot_deveil...` échouait d'abord avec un score de 0,0018 après correction : mon test appelait le modèle **deux fois par trame** (une fois pour le score, une fois pour la détection), ce qui faussait son tampon glissant. Le moteur, lui, donnait bien 0,995.
2. `test_e1_audio_transmis_au_modele_en_int16` utilisait la **première** trame du fichier, qui est du silence ajouté volontairement. Il prend désormais la trame la plus sonore.

### Après correction

```
python -m pytest tests/test_voice_chain_e.py -q
12 passed in 90.76s

python -m pytest tests/test_memory_cleanup_guard_e.py -q
5 passed in 0.17s
```

### Suite complète

```
python -m pytest tests/ -q
654 passed, 4 skipped in 162.43s (0:02:42)
exit=0
```

**Écart 637 → 654, expliqué :** +12 tests vocaux, +5 garde-fous de nettoyage. Aucun test supprimé.

**Un test existant corrigé, révélé par la séance d'Alexis.** `test_final_v50::test_05_execution_engine_breaks_recursive_replan` a échoué après sa séance : il lance `launch_app notepad` et attend un échec, mais **le Bloc-notes tournait sur le poste** depuis ses essais vocaux. Le moteur considérait l'action déjà accomplie (« idempotence »), l'échec forcé n'avait donc pas lieu et le garde-fou anti-récursion n'était jamais atteint. Vérifié : ce test échoue aussi **sans mes modifications**, et passait seulement parce que le Bloc-notes était fermé. Il ne dépend plus des processus ouverts.

**Non-régression, suite par suite** : 31 fichiers, **654 passés, 4 ignorés, 0 échec**. Les suites vocales antérieures (`test_voice_v40.py` 12, `test_voice_v602.py` 17) passent sans modification, ainsi que les suites mémoire après le nettoyage (`test_memory_quality_d.py` 11, `test_memory_v60.py` 33, `test_chroma_integration.py` 5). Les 4 ignorés sont ceux, volontaires, de B1-bis.

---

## 6. Comportement observé en scénarios réels

### 6.1 Prélude — vérification du nettoyage

Préalables, au démarrage réel d'Atlas :
```
[atlas.memory] ChromaDB connecté — localhost:8001 — collection 'atlas_memory_e5' + 5 partitions
[atlas.validator] [AUTOMATION] workflow « Mode Gaming » bloqué : … 'kill_process' …
[atlas.validator] [AUTOMATION] workflow « Nettoyage Système » bloqué : … 'maintenance_empty_bin' …
[atlas.notifier] 🔔 Notification : Atlas — automatisation bloquée — workflow « Mode Gaming » …
```
D-R11 et B1T-R2 sont donc confirmés en usage réel, notifications comprises.

Sauvegarde `chromadb_20260924_182312`, **restauration prouvée**, avant toute écriture.

| Collection | Avant | Supprimés | Après | Attendu |
|---|---|---|---|---|
| `atlas_documents` | 25 | 17 (15 artefacts + 2 doublons) | **8** | 8 |
| `atlas_errors` | 24 | 17 (10 artefacts + 3 du test D1 + 4 doublons) | **7** | 7 |
| `atlas_memory_e5` | 489 | 219 doublons | **270** | 270 |
| `atlas_memory` | 489 | **0 — protégée** | 489 | 489 |
| `atlas_conversations` | 12 | **0 — protégée** | 12 | 12 |

253 identifiants supprimés, tous consignés dans `cleanup_ids.json` avec leur motif.

**Qualité du rappel après nettoyage — elle s'améliore :**

| Mesure (20 requêtes de référence) | Avant nettoyage | Après |
|---|---|---|
| Bonne réponse en 1ʳᵉ position | 9/14 (64 %) | 9/14 (64 %) |
| Bonne réponse dans le top 3 | 9/14 (64 %) | **10/14 (71 %)** |
| Bonne réponse dans le top 5 | 10/14 | **11/14** |
| Textes distincts dans le top 5 | 1,85 | **2,75** |
| Injection parasite (6 questions sans réponse) | 2 | 2 |

Les garde-fous du nettoyage ont été testés **avec un client ChromaDB simulé** avant toute exécution, conformément à la règle permanente issue de l'incident I-1.

### 6.2 E6 — VRAM sur la chaîne complète

Mot d'éveil (WAV réel) → transcription GPU → planification (LLM) → synthèse :

| Étape | VRAM |
|---|---|
| Repos, avant chargement | 1 790 Mo |
| Modèle de mot d'éveil chargé | 1 783 Mo (il tourne sur processeur) |
| Après transcription GPU | 2 022 Mo |
| Après planification (qwen2.5:7b) | 6 674 Mo |
| Après synthèse | 6 674 Mo |
| **Pic** | **6 674 Mo sur 8 151 (82 %)** |

Le seuil d'alerte du brief (7,5 Go) n'est pas atteint. La transcription GPU ne coûte que **≈ 240 Mo** : c'est le LLM qui occupe la VRAM. Aucun arbitrage n'est donc nécessaire ; s'il le devenait, les options sont en annexe B.

### 6.3 E7 — validation réelle, Alexis au micro

Deux séances : le 24/09 de 19 h 04 à 19 h 16 (avant les traces), puis de 19 h 48 à 19 h 58 (mesurée). Chiffres issus des journaux, sauf les comptages que seuls les yeux d'Alexis pouvaient faire.

| ID | Scénario | Résultat observé | Statut |
|---|---|---|---|
| **R02** | « Hey Atlas » dix fois, à un mètre | **3 à 5 échecs sur 10** (compte d'Alexis), soit 50 à 70 % de réussite. Scores des réveils réussis : médiane **0,982**, min 0,529, max 0,995 | PARTIEL — limite du modèle (recall publié : 62 %) |
| **R03** | « Quelle heure il est » | Transcription **exacte** : « Quelle heure est-il ? ». Réponse parlée. Mais **« Il est 14:32 à Paris »** à 19 h 54 | PASS pour la chaîne vocale ; **L4 persistant**, hors périmètre |
| **R04** | « Ferme cette fenêtre » puis « ferme la fenêtre Steam » | « cette » a été pris pour un nom de fenêtre. Puis **Steam a été fermé instantanément, sans confirmation ni notification** (confirmé par Alexis) | **FAIL** — voir D-E1 |
| **R05** | « Comment tu vas » | « Comment vas-tu ? » transcrit, réponse conversationnelle parlée | PASS |
| **R06** | Cinq cycles d'affilée | **Aucun plantage**, retour au repos à chaque fois. 25 cycles complets sur la séance | PASS |
| **R07** | Latence fin de « Hey Atlas » → premier son | Total médian **16,4 s** (min 6,9 s, max 62,8 s). Décomposition ci-dessous | PASS, mesuré |
| **R08** | Écoute passive | Conditions difficiles (musique + Alexis qui chante) : **1 seul faux déclenchement**. Séance du soir, environ 40 min allumé dont une trentaine sans interaction : **0 faux déclenchement**, confirmé par l'absence de toute ligne de réveil dans les journaux après 19 h 58 | PASS |

**Décomposition de la latence (25 cycles réels) :**

| Étape | Médiane | Min | Max |
|---|---|---|---|
| Écoute, jusqu'au silence | 5,5 s | 1,9 s | 11,8 s |
| **Transcription (GPU)** | **0,3 s** | 0,1 s | 3,8 s |
| Réflexion (LLM) | 2,7 s | 1,8 s | 24,4 s |
| Parole (synthèse + lecture) | 5,0 s | 1,0 s | 26,2 s |
| **Total depuis le mot d'éveil** | **16,4 s** | 6,9 s | 62,8 s |

La transcription n'est plus un facteur. Ce qui coûte : l'attente de fin de phrase (1,5 s de silence après la voix), la réflexion du LLM, et la **lecture** de la réponse. La synthèse elle-même ne prend que 0,35 à 0,55 s (mesuré §4.3), donc **Atlas commence à parler environ 9 s après le mot d'éveil, soit environ 5 s après que l'utilisateur a fini de parler.**

**Ce qu'Alexis a signalé de lui-même, et qui compte.**
- *« Sur les 5 questions, pas eu de bug, et il revenait à chaque fois sans que j'aie besoin de dire Hey Atlas, donc pratique. »* Cette reprise sans mot d'éveil **n'est pas voulue** : c'est la file audio qui n'est pas vidée (D-E2). L'effet plaît ; la cause est un défaut.
- *« Il a du mal avec la prononciation, exemple le "au péra" alors que c'était Opera, et y'en a pas mal, idem pour "stim", "lens opéragé x". »* Traité en §4.7 ; reste à confirmer au micro.
- *« Il s'active très peu quand je fais mes affaires. »* Confirmé par les journaux : aucun réveil pendant la période sans interaction.

**Sur le taux de faux déclenchements, restons prudents.** Un seul en conditions difficiles et aucun en usage normal, c'est encourageant et cohérent avec les 1,24 par heure publiés par l'auteur du modèle. Mais je ne connais pas la durée exacte de la séance avec musique : ces deux observations ne suffisent pas à établir un taux horaire. Il faudrait une écoute passive chronométrée pour cela.

---

## 7. Limites et risques identifiés

| ID | Description | Sévérité | Mitigation proposée |
|---|---|---|---|
| **D-E1** | **Fermer une fenêtre ne demande jamais confirmation.** Le validateur pose `confirmation_required = True`, et `execute_tool` ne le lit pas : il applique ses propres règles, limitées à `kill_process`, `run_powershell` et `system_config`. Vérifié : `needs_confirmation("window_close", …)` renvoie `None`. **L'annexe A du rapport B1 affirmait « Atténué : confirmation obligatoire sur close » — c'est faux, et je le corrige ici.** Révélé par R04. | **Élevé** | Faire honorer le drapeau du validateur par le moteur. Décision d'Alexis : **brief dédié**, pas ce sprint |
| **D-E2** | **La file audio n'est jamais vidée.** Tout ce que le micro capte pendant qu'Atlas enregistre, réfléchit et **parle** s'accumule, puis est analysé au retour au repos : **17 réveils sur 29 se sont déclenchés moins de 0,2 s après la fin d'un cycle**, dont 4 suivis d'une transcription vide. Atlas peut donc réagir à sa propre voix. Décision d'Alexis : consigner seulement. | Moyen | En faire un comportement **délibéré** : vider la file, puis ouvrir une fenêtre de suite de quelques secondes où Atlas écoute sans mot d'éveil — c'est ce qu'Alexis apprécie, mais assumé et borné |
| **D-E3** | **Recall du mot d'éveil : 50 à 70 %.** Trois à cinq « Hey Atlas » sur dix ne déclenchent rien. Le code est hors de cause (0,995 sur un WAV propre) ; c'est le modèle communautaire, dont l'auteur publie 62 %. | Moyen | Baisser `wake_word_threshold` par paliers de 0,05 en surveillant les faux positifs, ou entraîner un modèle sur la voix d'Alexis (piste à chiffrer) |
| **D-E4** | Le modèle n'entend « Hey Atlas » qu'**à l'anglaise** : 0,0008 avec une voix française. Contrainte d'usage, pas un défaut. | Faible | Documenté dans le runbook et le protocole |
| **D-E5** | **L4 persistant, hors périmètre :** « Il est 14:32 à Paris » à 19 h 54. La transcription était juste ; c'est le modèle qui invente l'heure. | Moyen | Sa propre tranche. Ne pas l'imputer à la chaîne vocale |
| **D-E6** | **Le repli SAPI n'a jamais servi en réel** : Piper a fonctionné à chaque cycle. Il est prouvé par test, pas en usage. | Faible | Le vérifier une fois en renommant le modèle Piper, hors séance de validation |
| **D-E7** | **L'amorçage par les noms d'applications n'est pas encore éprouvé au micro.** Mesuré sur voix synthétique : 2/5 → 5/5. La voix d'Alexis peut donner d'autres résultats. | Moyen | Court essai au micro : « lance Steam », « ouvre Discord », « lance Opera GX » |
| **D-E8** | **Latence médiane 16,4 s**, dont 5,5 s d'attente de fin de phrase et 5,0 s de lecture de la réponse. Utilisable, mais loin d'une conversation. | Moyen | Réduire le silence de fin (1,5 s → 0,8 s), raccourcir les réponses parlées, et jouer la synthèse au fil de l'eau plutôt qu'après |
| **D-E9** | **Le message « aucun GPU CUDA détecté » au démarrage est faux.** Il s'appuie sur torch, installé en version **sans CUDA** (`2.12.1+cpu`), alors que la transcription passe par CTranslate2 et tourne bien sur la carte. | Faible | Fonder le message sur `ensure_cuda_libraries()`, ou installer une version CUDA de torch si la vision en a besoin |
| **D-E10** | Le journal se termine par `Accept failed on a socket` / `WinError 64` quand la fenêtre Atlas se déconnecte. Bruit Windows connu, pas un plantage, mais journalisé en ERREUR. | Faible | Étendre le filtre asyncio déjà présent dans `main.py` à cette erreur |
| **D-E11** | **`desktop/atlas_desktop.py` est hors du périmètre du brief**, modifié sur demande explicite d'Alexis (voyant d'écoute), dans un commit séparé. | Faible | Signalé ; le superviseur peut refuser l'ajout |
| **D-E12** | **Deux régressions que j'ai moi-même introduites** avant de les corriger : le suivi d'écoute saturait le backend (§4.6), et deux de mes tests étaient mal écrits (§5). Les deux ont été trouvées par l'usage d'Alexis ou par la mesure, pas par relecture. | Faible | Consigné pour mémoire |
| **D-E13** | La transcription reste imparfaite sur les phrases longues ou hésitantes (« Mais en premier plan, la fenêtre au pérage X »), ce qui produit des commandes absurdes exécutées comme telles (`launch_app ', je t'étais demandé fermer'`). | Moyen | Refuser les cibles manifestement issues d'une mauvaise transcription, côté validateur (hors périmètre ici) |

---

## 8. Checklist de validation

- [x] **Prélude** : collection active confirmée (§6.1), notifications B1T-R2 constatées (§6.1), sauvegarde vérifiée, suppressions faites selon le tableau, `atlas_memory` intacte, **qualité du rappel améliorée** (hit@3 64 % → 71 %), commit séparé `65ab270`.
- [x] Tests rouges d'abord, **sur du vrai audio et le vrai code** pour L1 et L3 (§5 : ni `predict` ni `_speak_sync` simulés).
- [x] L1 corrigé : le mot d'éveil se déclenche sur un WAV réel (0,0008 → 0,995) **et au micro** (29 réveils).
- [x] L2 corrigé : transcription sur GPU (0,3 s médiane), **compatibilité Blackwell vérifiée** et non supposée.
- [x] L3 corrigé : Piper produit du son, version épinglée à 1.4.1, échecs journalisés.
- [x] Repli SAPI fonctionnel, journalisé, visible — **jamais déclenché en réel** (D-E6).
- [x] `/api/health` reflète la capacité réelle de la voix (§4.4).
- [x] Action à confirmation demandée à la voix : réponse parlée explicite, jamais de blocage silencieux. **Mais le cas réel ne se produit pas pour `window_close`** (D-E1).
- [x] Confirmation vocale réelle : analyse livrée en annexe A, **aucun code écrit**.
- [x] VRAM remesurée avec transcription GPU : pic 6 674 Mo sur 8 151 (§6.2).
- [x] **R02 à R08 exécutés avec Alexis au micro** (§6.3). R04 est un **échec**, consigné comme tel.
- [x] `python -m pytest tests/ -q` → code 0 (654 passés, 4 ignorés).

Périmètre : `core/voice_engine.py`, `tools/systray.py`, `api/routes.py`, `requirements.txt`, `scripts/doctor.py`, `docs/voice_runbook.md`, `tests/`, et la mémoire pour le prélude — tous autorisés. **Deux dépassements, tous deux signalés :** `desktop/atlas_desktop.py` (demande d'Alexis) et `/api/voice/state` ajouté à `api/routes.py` alors que le brief n'autorisait que `/api/health` — c'est précisément ce qui a résolu la saturation du backend.

---

## 9. Recommandations pour le sprint suivant

### P1
1. **Faire honorer le drapeau de confirmation par le moteur** (D-E1). C'est une faille de sécurité : fermer une fenêtre, à la voix comme au clavier, ne demande rien. Le brief dédié décidé par Alexis devrait aussi corriger l'annexe A du rapport B1.
2. **Assumer la conversation continue** (D-E2) : vider la file audio et ouvrir une fenêtre de suite bornée. Alexis apprécie l'effet ; il ne doit plus dépendre d'un défaut, ni faire réagir Atlas à sa propre voix.
3. **Confirmer au micro l'amorçage des noms d'applications** (D-E7) : cinq minutes suffisent.

### P2
4. **Réduire la latence** (D-E8) : silence de fin à 0,8 s, réponses parlées plus courtes, lecture au fil de la synthèse.
5. **Le recall du mot d'éveil** (D-E3) : essayer `wake_word_threshold` à 0,45 puis 0,40 en comptant les faux positifs sur 30 minutes, et chiffrer l'entraînement d'un modèle sur la voix d'Alexis.
6. Corriger le message trompeur « aucun GPU CUDA détecté » (D-E9) et le bruit `WinError 64` (D-E10).
7. Refuser les cibles issues d'une transcription manifestement fausse (D-E13).

### P3
8. Vérifier une fois le repli SAPI en conditions réelles (D-E6).
9. Reports toujours ouverts : `confirm_before_run` non appliqué (B1T-R4), endpoint d'état des automatisations (B1T-R8), reclassement du rappel mémoire (D-R2), nettoyage de `assistant-bureau/data/`.

---

# Annexe A — E5 : la confirmation par la voix (analyse, sans implémentation)

Le brief demande d'analyser, pas de coder. Voici l'état de la question.

**Ce qui existe aujourd'hui.** Une action sensible demandée à la voix produit une réponse parlée explicite et une notification. Rien ne permet de répondre « oui » à la voix.

**Quatre questions de conception, dans l'ordre de difficulté.**

1. **Comment écouter la réponse ?** Le micro n'écoute qu'après le mot d'éveil. Deux voies : ouvrir une fenêtre d'écoute de quelques secondes juste après la question — c'est la même mécanique que la « conversation continue » de D-E2, donc une brique commune — ou exiger un nouveau « Hey Atlas », plus sûr mais pénible pour un simple « oui ».

2. **Comment être sûr que c'est bien « oui » ?** Trois risques concrets, tous observés dans les journaux de la séance : la transcription se trompe (« ouais », « OK », « vas-y », « mouais »), elle capte la télévision ou une conversation, et elle peut transcrire un « non » en quelque chose d'ambigu. Une confirmation acquise par erreur sur une action destructrice est pire que pas de confirmation du tout. Il faut donc une liste blanche de formulations acceptées, **et** un score de confiance minimal, **et** un refus par défaut en cas de doute — jamais l'inverse.

3. **Quelles actions peuvent être confirmées à la voix ?** Je recommande de distinguer deux niveaux. Les actions réversibles (fermer une fenêtre, réduire, ancrer) pourraient l'être. Les actions irréversibles (tuer un processus, vider la corbeille, PowerShell, arrêt système) ne devraient **jamais** l'être : un « oui » mal entendu ne se rattrape pas. C'est cohérent avec la règle 3 et avec l'esprit des sprints B1.

4. **Que voit l'utilisateur ?** La confirmation doit rester visible à l'écran même quand elle est demandée à la voix, avec un délai d'expiration court et un refus par défaut. Aujourd'hui, une confirmation en attente ne s'affiche nulle part dans la fenêtre Atlas : c'est un prérequis, pas un détail.

**Coût estimé :** une demi-journée pour la fenêtre d'écoute et la reconnaissance du « oui », autant pour l'affichage et les tests, plus une séance au micro. **Prérequis indispensable : D-E1.** Tant que le moteur ignore le drapeau de confirmation, il n'y a rien à confirmer.

**Recommandation :** traiter D-E1 d'abord, puis la fenêtre d'écoute commune avec D-E2, et n'ouvrir la confirmation vocale qu'aux actions réversibles.

---

# Annexe B — Arbitrages VRAM, si le besoin apparaît (non appliqués)

Le pic mesuré est de 6 674 Mo sur 8 151, soit 82 %, sous le seuil d'alerte du brief. Aucun arbitrage n'est nécessaire aujourd'hui. Si la marge devenait insuffisante — par exemple en ajoutant la vision — les leviers sont, du moins au plus coûteux en qualité :

| Levier | Gain estimé | Effet |
|---|---|---|
| Réduire `keep_alive` d'Ollama (10 min actuellement) | jusqu'à 4,5 Go entre deux usages | Recharge le LLM après une pause : première réponse lente |
| Transcription en `int8` sur processeur | ≈ 240 Mo | Revient au défaut L2 : 5 s par phrase. À éviter |
| Modèle LLM plus petit (qwen2.5:3b) | ≈ 2 Go | Réponses moins bonnes, planification moins fiable |
| Décharger le LLM pendant la synthèse | ≈ 4,5 Go ponctuels | Complexité élevée, gain temporaire |

La transcription GPU ne coûtant que 240 Mo, elle n'est pas le bon endroit pour économiser.

---

*Rapport Sprint E — CHAT6 (Claude Opus 5, Claude Code Windows), 25/09/2026.*
