# BRIEF SPRINT A — État des lieux

**Destinataire :** CHAT6 (Claude Opus, Claude Code Windows)
**Émetteur :** Superviseur technique Atlas
**Date d'émission :** 16 septembre 2026
**Durée estimée :** 2 à 3 jours
**Statut :** Premier sprint de la reprise. Bloque les sprints B et C.

---

## 1. Contexte

L'oral B3 a eu lieu le 15 septembre 2026 et s'est bien passé. Le développement, gelé depuis début août, reprend.

**Machine nouvelle :** poste fixe à Toulouse, **RTX 5060 8 Go** (remplace la RTX 3050, cédée). Kit de ventilateurs installé après des mois de fonctionnement sans aucune ventilation de boîtier — les conditions thermiques ont changé, toute mesure antérieure est non comparable.

**Dettes ouvertes, jamais soldées :**

- Atlas n'a **jamais tourné** sur une machine autre que celle d'Alexis
- La chaîne vocale n'a **jamais été validée avec un micro réel** — code livré en v6.0.2, tests entièrement mockés
- La suite complète `270 pytest + 33 custom + validate_v12` n'a **jamais été exécutée** sur environnement Windows complet
- Aucun relevé RAM/VRAM sur matériel réel

**Ce sprint transforme ces inconnues en faits mesurés.**

### État du dépôt — déjà vérifié par le superviseur

Inspection faite depuis le poste Mac le 16 septembre. **Aucune action requise, information fournie pour éviter une redite :**

- Branche `main`, synchronisée avec `origin/main`, arbre de travail propre
- **v6.0.2 est présent sur `main`** — commits `2a2389e` et `e01949a`, tous deux intitulés « F1 Voix Partie 1 (Bloc A) ». Doublon probablement dû à une reprise de push ; sans conséquence, à signaler si cela gêne
- Aucune branche locale ou distante en attente de fusion
- Les cinq livrables v6.0.2 sont présents : `scripts/download_voice_models.py`, `tests/test_voice_v602.py`, `docs/voice_runbook.md`, `core/voice_engine.py`, `config/settings.json`
- `RAPPORT_RULES.md` se trouve dans `rapport.md/` (voir A6 — ce répertoire porte une extension `.md` alors que c'en est un)

CHAT6 confirme simplement cet état côté Windows après son `git pull`, et signale toute divergence.

---

## 2. Règle cardinale

> **Aucune modification du code existant d'Atlas.**

Ce sprint **observe et mesure**. Il ne corrige pas, ne refactorise pas, ne range pas.

Raison : inspecter et modifier simultanément rend impossible de distinguer ce qui était cassé de ce que le sprint a cassé. Les corrections relèvent du sprint B, la restructuration du sprint C.

**Autorisés** — ils n'altèrent aucun comportement existant :

- Création de **nouveaux fichiers d'outillage** (`scripts/doctor.py`)
- Création de **documentation** (checklist d'installation, rapport, annexes)

**Interdit** : toute modification d'un fichier existant sous `core/`, `tools/`, `config/`, `api/`, `main.py`, ou dans `tests/`.

Si un bug critique empêche d'exécuter une tâche, le **signaler et documenter le contournement** sans corriger. En cas d'impossibilité absolue de poursuivre, la modification est autorisée mais doit figurer dans une section dédiée du rapport.

---

## 3. Tâches

### A1 — Confirmation de l'état du dépôt

`git pull`, puis confirmer côté Windows l'état décrit en section 1. Signaler toute divergence. Cinq minutes.

### A2 — Installation depuis zéro + checklist

Installer Atlas sur la machine en documentant **chaque étape**, y compris celles qui paraissent évidentes.

Livrable : `docs/install_checklist.md` — procédure ordonnée et cochable permettant à quelqu'un qui n'a jamais vu Atlas de l'installer sur une machine Windows vierge.

Couvrir au minimum : Python 3.12 et `.venv` · `requirements.txt` complet, dépendances Windows incluses (`pywin32`, `comtypes`, `pycaw`, `wmi`) · Ollama et pull du modèle · **Tesseract 5.5.0 avec vérification effective du PATH** · EasyOCR · ChromaDB · recherche web (SearXNG ou repli `ddgs`) · `config/settings.json` · modèles voix via `scripts/download_voice_models.py`.

**Rappel de l'épisode fondateur** : Tesseract n'a jamais été installé pendant 7 sprints, causant 90 s de latence, découvert par hasard au sprint v5.2. Une machine neuve reproduit ce risque pour chaque dépendance. La checklist est la parade — et la base du futur installeur de diffusion. La rédiger comme telle.

### A3 — `scripts/doctor.py`

Nouveau fichier. Diagnostic d'installation :

- Vérification de chaque dépendance avec un **message de correction actionnable**
- Détection GPU et VRAM disponible
- Recommandation automatique de taille de modèle selon la VRAM
- Code de retour non nul si un composant critique manque

Approche inspirée de `sosoj92/jarvis-assistant-vocal` (MIT) — adapter, ne pas copier, créditer en en-tête.

### A4 — Exécution complète de la suite de tests

Objectif : `270 pytest + 33 custom + validate_v12`.

Rapporter les **commandes exactes** et les **résultats bruts**, sans interprétation optimiste. Tout échec listé **nominativement** avec sa cause. Aucune formulation vague du type « échecs d'environnement » — c'est précisément ce que le rapport v6.0.2 n'avait pas pu faire.

Cas connu à confirmer : `tests/test_voice_v40.py::test_10_gpu_absent_warning_no_crash` échouait sur macOS via `import main` → `tools/process_manager.py` (constantes `psutil` Windows-only). **Attendu PASS sur Windows.** S'il échoue encore, c'est un vrai bug.

### A5 — Audit de la qualité des tests

Question posée : **ces tests prouvent-ils quelque chose, ou passent-ils à vide ?**

Le rapport v6.0.2 a livré 17 tests verts sur une chaîne vocale n'ayant jamais produit un son. C'est le symptôme à investiguer.

Analyser et rapporter :

- **Couverture réelle** par module — quels chemins ne sont jamais empruntés
- **Tests tautologiques** — ceux qui valident un mock plutôt qu'un comportement
- **Zones critiques non couvertes**, en particulier la couche de grounding, la plus fragile
- **Tests fragiles** — dépendants d'un ordre d'exécution, d'une horloge, d'un état global

Livrable : liste hiérarchisée des tests à écrire ou renforcer, avec justification. **Ne pas les écrire dans ce sprint.**

### A6 — Inventaire du code et de l'architecture

**Inventaire, pas correction.** Le superviseur a relevé les éléments suivants depuis le Mac — à compléter, confirmer ou infirmer :

**Structure du dépôt :**

- Tout le projet vit sous `assistant-bureau/`. À la racine du dépôt il n'y a que `README.md`, `.gitignore` et `requirements-core-conversational.txt` — d'où l'aspect vide sur GitHub. Objet du sprint C.
- **`rapport.md` est un répertoire**, pas un fichier, malgré son extension. Il contient `RAPPORT_RULES.md`, `DIAGNOSTIC_V22.md`, `RAPPORT_CHAT3_FIN_MISSION.md`, `RAPPORT_SUPERVISEUR_V22.md`, `RAPPORT_V23.md`. Nommage trompeur à corriger en C.
- **Six rapports à la racine** de `assistant-bureau/` : `RAPPORT_V30`, `V31`, `V40`, `V50`, `V602`, `RAPPORT_DECISION_2026-04-08`. À regrouper en C.

**Fichiers suspects à qualifier :**

- `test_kokoro.py` — **fichier vide, 0 octet**. Vestige de l'évaluation Kokoro. Confirmer qu'il n'est référencé nulle part.
- `petite_image.png` — 75 Ko à la racine, sans usage apparent. Identifier son rôle ou le classer comme mort.
- Vérifier que `.venv`, `__pycache__`, `.pytest_cache`, `logs/`, `data/` sont bien exclus par `.gitignore` et absents du suivi Git.

**Code et cohérence :**

- Code mort, avec la **preuve** qu'il n'est jamais appelé — cas connu : la stack vision MiniCPM-V, gatée depuis la Réunion #5
- Incohérences entre documentation et code réel
- Écarts par rapport aux invariants d'architecture
- Dépendances déclarées mais inutilisées, et l'inverse

Pour chaque élément : localisation, nature, criticité estimée. Le sprint B décidera.

### A7 — Relevé RAM, VRAM et températures

Contrainte matérielle : **8 Go de VRAM**. Aucune mesure antérieure n'existe, et la ventilation vient de changer.

Mesurer et rapporter :

1. RAM et VRAM au repos, Atlas démarré et inactif
2. VRAM avec le modèle de langage chargé seul
3. **Pic sur une chaîne complète** : commande vocale → OCR → planification → synthèse vocale
4. RAM système en pic sur le même scénario
5. Températures CPU et GPU en charge soutenue — première mesure depuis l'installation des ventilateurs

Si le pic VRAM approche ou dépasse 7 Go, **proposer des arbitrages documentés** (`stt_device=cpu`, whisper plus petit, déchargement entre commandes, `keep_alive` Ollama réduit) — **sans les appliquer**. L'arbitrage remonte au superviseur.

### A8 — Validation micro réelle

La dette la plus ancienne. Le micro est disponible, la machine est là.

| ID | Scénario | Attendu |
|---|---|---|
| R01 | `python scripts/download_voice_models.py` | 3 téléchargements OK, idempotence vérifiée au second lancement |
| R02 | Dire « Atlas » | Systray idle → listening |
| R03 | « Quelle heure il est » | Transcription correcte + réponse vocale |
| R04 | « Ferme cette fenêtre » | Intention exécutée + confirmation vocale |
| R05 | « Comment tu vas » | Réponse conversationnelle vocale |
| R06 | 5 commandes d'affilée | Aucun crash, retour systray idle |
| R07 | Latence mot d'éveil → premier son | Valeur mesurée |

Relever aussi le **taux de faux positifs** du wake word `hey_atlas` sur une période d'usage normal.

### A9 — Revue des rapports de veille

Lire les rapports hebdomadaires de veille de stack accumulés pendant le gel.

Livrable : **inventaire de ce qui concerne Atlas** — nouvelles versions de dépendances, changements cassants, modèles plus performants à VRAM égale, opportunités.

**Ne rien appliquer.** Toute mise à jour contaminerait les mesures A4 à A8. Chaque élément listé avec sa criticité ; le superviseur décide.

### A10 — Rapport

Conforme à `rapport.md/RAPPORT_RULES.md`, 9 sections obligatoires. À déposer dans `docs/rapports/`.

Doit répondre à **la question qui débloque la suite** :

> La suite de tests est-elle verte, ou rouge ?

De cette réponse dépend l'ordre des sprints suivants. **Verte** : on restructure avant de corriger (C puis B) — l'ordre préféré d'Alexis, qui évite de réparer des fichiers sur le point d'être déplacés. **Rouge** : il faut corriger le bloquant avant tout déplacement, car restructurer sur une suite rouge rend le déplacement invérifiable — on ne distingue plus les pannes préexistantes de celles qu'il a causées.

---

## 4. Livrables

- `docs/install_checklist.md`
- `scripts/doctor.py`
- `docs/rapports/RAPPORT_SPRINT_A.md` (RAPPORT_RULES, 9 sections)
- Section 5 : commandes et résultats bruts de la suite complète
- Section 6 : R01-R07 réellement exécutés, avec observations
- Annexes : audit qualité des tests · inventaire dette et code mort · relevé RAM/VRAM/températures · inventaire veille

## 5. Critères de validation

- [ ] État du dépôt confirmé côté Windows
- [ ] Atlas installé et démarrant, checklist suivie et livrée
- [ ] `doctor.py` livré, détecte la VRAM, recommande un modèle
- [ ] Suite complète exécutée, résultats bruts, échecs nominatifs
- [ ] Audit de qualité des tests livré
- [ ] Inventaire dette et code mort livré, incluant les points relevés en A6
- [ ] Relevé RAM/VRAM/températures chiffré
- [ ] R01-R07 exécutés avec micro réel
- [ ] Inventaire veille livré
- [ ] **Aucune modification d'un fichier existant** — ou exception signalée explicitement

## 6. Rappels de méthode

- **Honnêteté intellectuelle non négociable.** Un test non exécuté se déclare non exécuté. Aucun résultat revendiqué sans preuve reproductible. Un rapport disant « ça ne marche pas » vaut mieux qu'un rapport disant « ça marche » sans preuve.
- **Pas de scope caché.** Toute action hors périmètre est signalée.
- **Aucun passage au sprint suivant sans rapport validé.**
