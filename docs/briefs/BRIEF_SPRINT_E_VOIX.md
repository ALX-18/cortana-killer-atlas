# BRIEF SPRINT E — La chaîne vocale, pour de bon

**Destinataire :** CHAT6 (Claude Opus, Claude Code Windows)
**Émetteur :** Superviseur technique Atlas
**Date d'émission :** 22 septembre 2026
**Durée estimée :** 1 à 2 journées, plus une séance de validation avec Alexis au micro
**Statut :** Deuxième chantier de la reprise, après la mémoire.
**Références :** rapport A (L1, L2, L3, C04, R02-R07, annexe A.2), rapport D (inventaire, D-R11)

---

## 1. Pourquoi ce sprint

La voix est l'identité d'Atlas. Sans elle, c'est un assistant de bureau local ; avec elle, c'est ce qu'Alexis construit depuis le début.

**Et elle n'a jamais fonctionné.** Le sprint A l'a prouvé : trois pannes indépendantes, chacune suffisante à elle seule.

- **L1 — le mot d'éveil ne peut pas se déclencher.** `_wake_callback` convertit l'audio en float32 normalisé (`/32768`) ; openWakeWord attend du PCM int16. Sur le même audio : score **0,0008** avec le code actuel, **0,9951** en int16. Le mot d'éveil est structurellement mort, quel que soit le micro.
- **L2 — la transcription GPU plante** : `cublas64_12.dll is not found`. `stt_device=cuda`, aucune bibliothèque cuBLAS sur le poste.
- **L3 — la synthèse vocale est muette.** piper-tts ≥ 1.3 renvoie un générateur (API incompatible avec le code), l'exception est avalée, et le repli par la ligne de commande exige `pathvalidate` (absent en 1.4.1) et un venv activé.

S'y ajoute **C04** : `/api/health` affiche `"voice": {"running": true}` alors que la voix ne peut rien faire. Un indicateur qui ment est pire que pas d'indicateur.

**Rappel de ce qui a caché tout cela :** v6.0.2 avait livré 17 tests verts sur cette chaîne. Tous mockaient `predict`, remplaçaient `_init_wake_word` ou `_speak_sync`. Aucun n'exécutait la ligne fautive. L'audit A.2 les a classés tautologiques. **Ce sprint ne reproduira pas cette erreur** : voir §3.

---

## 2. Prélude — nettoyage de la mémoire, décidé par le superviseur

À faire **en premier**, dans un **commit séparé** du reste du sprint. Alexis a délégué cette décision au superviseur ; la voici.

### Préalables obligatoires

1. **Confirmer que `atlas_memory_e5` est bien la collection active** (D-R11). Démarrer Atlas une fois et vérifier la ligne de journal « ChromaDB connecté — collection 'atlas_memory_e5' ». Si ce n'est pas le cas, **s'arrêter** : nettoyer une collection que personne ne lit n'a aucun sens.
2. Au même démarrage, vérifier **B1T-R2** : deux notifications doivent apparaître (Mode Gaming, Nettoyage Système). Les consigner.
3. **Sauvegarde vérifiée** : `backup` puis `verify`.

### Suppressions décidées

Référence : `docs/rapports/INVENTAIRE_MEMOIRE_D.md`.

| Cible | Action | Raison |
|---|---|---|
| `atlas_documents` — 15 artefacts présumés | **Supprimer** | Fixtures de test sans ambiguïté (« Atlas 40d430 », « DOCUMENT_ONLY_MARKER ») |
| `atlas_errors` — 10 artefacts présumés | **Supprimer** | Signatures fabriquées par des tests. Ce sont elles qui ont trompé le mécanisme d'apprentissage : les garder contaminerait sa réparation future |
| `atlas_errors` — `err_d6824758fa78`, `err_0888b88f2bbf`, `err_4cd2a3a29cd7` | **Supprimer** | Écrites par le test D1, déjà documentées |
| `atlas_memory_e5` — 219 doublons | **Dédoublonner, garder la plus ancienne** | Règle de l'inventaire. La date réelle du souvenir est portée par la première occurrence |
| `atlas_documents`, `atlas_errors` — doublons restants | **Dédoublonner, garder un exemplaire** | Même règle |

### Ce qui n'est pas touché

- **`atlas_memory` (384 dimensions) : intacte.** C'est le retour arrière. La dédoublonner détruirait sa fidélité. Elle reste en l'état jusqu'à ce que `atlas_memory_e5` ait fait ses preuves en usage réel.
- `atlas_conversations` : propre, rien à faire.

### Vérification du prélude

Après suppression : décompte par collection, comparaison avec l'inventaire, liste exacte des identifiants supprimés dans le rapport. Rejouer les 20 requêtes de référence du sprint D : **la qualité du rappel ne doit pas baisser**.

---

## 3. Méthode imposée — le test rouge, sur du vrai son

La règle est inchangée : chaque défaut est reproduit par un test qui échoue, avant correction, sortie brute consignée.

**Et pour ce sprint, une exigence de plus :** les tests de L1 et L3 doivent faire passer du **vrai audio** par le **vrai code**.

- Pour L1 : un fichier WAV réel contenant « Hey Atlas », injecté dans le vrai `_wake_callback`, jusqu'au vrai modèle openWakeWord. Le test doit échouer aujourd'hui avec un score proche de 0, passer après correction avec un score élevé. **Pas de mock de `predict`.**
- Pour L3 : la vraie synthèse Piper doit produire un tableau audio non vide, de durée plausible. **Pas de mock de `_speak_sync`.**

C'est la différence entre les 17 tests de v6.0.2 et ceux de ce sprint.

---

## 4. Périmètre

**Autorisé :** `core/voice_engine.py`, `tools/systray.py`, `api/routes.py` pour `/api/health` uniquement, `requirements.txt`, `config/settings.json`, `scripts/doctor.py`, `docs/voice_runbook.md`, `tests/`, et la mémoire pour le prélude.

**Interdit :** le grounding, l'apprentissage par les erreurs, les modes, le reclassement du rappel. Chacun a sa tranche.

---

## 5. Tâches

### E1 — L1 : le mot d'éveil

Passer l'audio en int16 brut à `predict`. Test d'intégration sur WAV réel, rouge d'abord.

**Rappel important pour la suite :** le modèle `hey_atlas.onnx` est entraîné sur « **Hey** Atlas », pas sur « Atlas » seul. Le dire dans le runbook et dans les consignes données à Alexis — sinon la validation échouera pour une raison sans rapport avec le code.

### E2 — L2 : la transcription sur GPU

Décision déjà prise par le superviseur : **ne pas installer le CUDA Toolkit**, trop lourd pour la diffusion. Utiliser les paquets pip `nvidia-cublas-cu12` et `nvidia-cudnn-cu12`, à déclarer dans `requirements.txt`.

**Point de vigilance spécifique à ce poste :** la carte est une **RTX 5060, architecture Blackwell**. Les générations récentes exigent des versions récentes de CUDA, et CTranslate2 doit disposer des noyaux compilés pour cette architecture. **Vérifier, ne pas supposer.** Si CTranslate2 refuse la carte, le rapporter précisément avec les versions en jeu, et proposer une solution plutôt que de basculer silencieusement sur le processeur.

Rappel de l'enjeu : 0,16 s à chaud sur GPU contre environ 5,3 s sur processeur. Sur une chaîne vocale, le processeur n'est pas une solution, c'est un repli.

### E3 — L3 : la synthèse vocale

- Adapter `_speak_sync` à l'API actuelle de piper-tts (`AudioChunk`).
- **Épingler la version** de piper-tts dans `requirements.txt`. La dérive de versions entre venvs est documentée depuis le sprint A (L12).
- **Journaliser tout échec.** L'exception avalée est la raison pour laquelle personne n'a vu que la voix était muette.
- **Repli sur SAPI**, la voix intégrée de Windows (via `pyttsx3`), si Piper échoue — décidé dès le Sprint 0, jamais implémenté. Aucun modèle à charger, aucune VRAM, disponible nativement. Le basculement doit être **journalisé et visible**, jamais silencieux.

### E4 — C04 : un indicateur de santé qui dit vrai

`/api/health` doit refléter la **capacité réelle** de la voix, pas la simple existence du composant : modèle de mot d'éveil chargé, cuBLAS disponible, synthèse opérationnelle, et si l'on est en repli SAPI.

Le même principe que l'anomalie A : un système qui affirme fonctionner alors qu'il ne fonctionne pas est plus dangereux qu'un système qui avoue être en panne.

### E5 — Confirmation vocale : le comportement minimal sûr

La règle 3 impose une confirmation pour les actions sensibles. **Aujourd'hui, aucun chemin ne permet de confirmer à la voix.** Une commande vocale exigeant une confirmation se retrouverait exactement dans la situation de l'anomalie A : bloquée sans que personne le sache.

Pour ce sprint, **le minimum** : une action à confirmation demandée à la voix doit produire une réponse **parlée** explicite (« Cette action nécessite une confirmation à l'écran »), et la confirmation doit apparaître à l'écran. **Jamais de blocage silencieux.**

La vraie confirmation par la voix (« oui » / « non ») est un sujet de conception : **analyser et proposer, sans l'implémenter**.

### E6 — Mesure VRAM avec la transcription sur GPU

Le pic mesuré au sprint A (6,5 à 6,7 Go sur 8,15) ne reflétait pas une transcription GPU fonctionnelle. Remesurer sur la chaîne complète : mot d'éveil → transcription GPU → planification → synthèse. Si le pic approche 7,5 Go, proposer des arbitrages **sans les appliquer**.

### E7 — Validation réelle, avec Alexis au micro

**Le critère qui compte.** Tout le reste prouve la logique ; seule cette étape prouve le produit.

CHAT6 prépare l'environnement et remet à Alexis un **protocole écrit et simple**. Alexis exécute. CHAT6 recueille et consigne les résultats.

| ID | Scénario | Attendu |
|---|---|---|
| R02 | Dire « **Hey Atlas** » dix fois, à un mètre | Nombre de passages en écoute sur dix |
| R03 | « Quelle heure il est » | Transcription correcte + réponse parlée |
| R04 | « Ferme cette fenêtre » | Confirmation demandée à l'écran, annoncée à la voix (E5) |
| R05 | « Comment tu vas » | Réponse conversationnelle parlée |
| R06 | Cinq cycles d'affilée | Aucun plantage, retour au repos à chaque fois |
| R07 | Latence, fin de « Hey Atlas » → premier son | Valeur mesurée, par horodatage des journaux |
| R08 | Trente minutes d'activité normale | Nombre d'éveils non sollicités |

**Note sur R03 :** le sprint A a montré que le modèle inventait l'heure (« Il est 14h32 » à 17h06, risque L4). Ce défaut n'est **pas** dans le périmètre de ce sprint. Si R03 renvoie une heure fausse alors que la transcription est juste, le consigner comme L4 persistant — **ne pas le corriger ici**, et ne pas compter R03 comme un échec de la chaîne vocale.

### E8 — Rapport

Conforme à `docs/RAPPORT_RULES.md`, 9 sections, dans `docs/rapports/RAPPORT_SPRINT_E.md`.

Doit répondre sans ambiguïté : **Atlas entend-il, comprend-il et répond-il à voix haute, avec Alexis au micro ?**

---

## 6. Critères de validation

- [ ] **Prélude :** collection active confirmée, notifications B1T-R2 constatées, sauvegarde vérifiée, suppressions faites selon le tableau, `atlas_memory` intacte, qualité du rappel non dégradée, commit séparé
- [ ] Tests rouges d'abord, **sur du vrai audio et le vrai code** pour L1 et L3
- [ ] L1 corrigé : le mot d'éveil se déclenche sur un WAV réel
- [ ] L2 corrigé : transcription sur GPU, **compatibilité Blackwell vérifiée**
- [ ] L3 corrigé : Piper produit du son, version épinglée, échecs journalisés
- [ ] Repli SAPI fonctionnel, journalisé, visible
- [ ] `/api/health` reflète la capacité réelle de la voix
- [ ] Action à confirmation demandée à la voix : réponse parlée explicite, jamais de blocage silencieux
- [ ] Confirmation vocale réelle : analyse livrée, **pas d'implémentation**
- [ ] VRAM remesurée avec transcription GPU
- [ ] **R02 à R08 exécutés avec Alexis au micro**
- [ ] `python -m pytest tests/ -q` → code 0

## 7. Rappels de méthode

- **Un test qui mocke ce qu'il prétend vérifier ne prouve rien.** C'est la leçon de v6.0.2.
- **Un échec silencieux est le pire comportement.** Vaut pour la synthèse, la confirmation, l'indicateur de santé.
- Ne pas corriger l'heure inventée, le grounding ou l'apprentissage par les erreurs. Ils ont leur tranche.
- En cas de doute sur une commande touchant Docker ou la mémoire : ne pas l'exécuter, demander.
- Un garde-fou se teste avec des commandes simulées. Règle permanente depuis I-1.
