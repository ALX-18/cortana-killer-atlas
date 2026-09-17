# BRIEF SPRINT C — Restructuration du dépôt

**Destinataire :** CHAT6 (Claude Opus, Claude Code Windows)
**Émetteur :** Superviseur technique Atlas
**Date d'émission :** 17 septembre 2026
**Durée estimée :** 1 journée
**Statut :** Possible parce que la suite est verte. Précède B-complet.
**Références :** rapports A (A6, L20), M-bis (R-6, R-7), B-minimal

---

## 1. Objectif

Trois choses, dans cet ordre de priorité :

1. **Sortir Atlas de `assistant-bureau/`** — aujourd'hui la racine du dépôt ne contient que `README.md`, `.gitignore` et `requirements-core-conversational.txt`, ce qui donne un dépôt d'apparence vide sur GitHub.
2. **Ranger les rapports et la documentation.**
3. **Supprimer le code mort et les vestiges** inventoriés au sprint A.

Structure cible : **aplatie**. Le contenu de `assistant-bureau/` remonte à la racine du dépôt, et `assistant-bureau/` disparaît.

---

## 2. Préalable : la suite est verte, elle doit le rester

Le sprint B-minimal a établi la référence : `python -m pytest tests/ -q` → **code 0, 376 tests passés**.

C'est la seule chose qui rend ce sprint vérifiable. Un déplacement qui casse quelque chose se verra immédiatement, à condition de mesurer avant et après **la même chose**.

**Fusionner `sprint-b-minimal` dans `main` avant de commencer**, et travailler sur une nouvelle branche `sprint-c`.

---

## 3. Les trois pièges

### Piège 1 — L'environnement virtuel ne se déplace pas

`.venv` vit dans `assistant-bureau/`. Un environnement virtuel Python contient des **chemins absolus** dans ses scripts : le déplacer le casse. Il faut le **recréer** à la nouvelle racine.

Et recréer un venv avec un `requirements.txt` non figé (risque L12 : dérive constatée entre venvs — piper 1.4.1 → 1.8.0, torch 2.12.1 → 2.14.0) peut installer des versions différentes.

**Conséquence : sans précaution, on ne saurait pas si une suite devenue rouge l'est à cause du déplacement ou d'un changement de dépendances.** Deux variables changées en même temps, aucune conclusion possible.

Parade obligatoire :

- `pip freeze` **avant**, conservé comme référence
- Recréation du venv à la nouvelle racine
- `pip freeze` **après**, comparé au précédent
- **Toute dérive de version est signalée dans le rapport**, même si la suite reste verte

**Ne pas supprimer l'ancien venv** tant que le nouveau n'a pas fait passer les 376 tests.

### Piège 2 — Deux `README.md` vont entrer en collision

Il existe `README.md` à la racine du dépôt **et** `assistant-bureau/README.md`. L'aplatissement les met au même endroit.

Les comparer, décider lequel survit ou les fusionner, et **le dire dans le rapport**. Ne pas en écraser un silencieusement.

Même vigilance pour tout autre nom en double découvert pendant le déplacement.

### Piège 3 — Les chemins sont calculés partout

Le déplacement casse tout ce qui construit un chemin. À passer en revue systématiquement, pas au jugé :

- `docker-compose.yml` — montage lié de `config/searxng`
- `start_atlas_desktop.bat`
- `scripts/doctor.py`, `scripts/backup_memory.py`
- `tests/conftest.py` — construit la racine temporaire du projet
- `api/routes.py` — reconstruit ses chemins depuis son propre `__file__` (défaut connu, **ne pas corriger ici**, c'est B-complet ; vérifier seulement que le déplacement ne l'aggrave pas)
- `main.py` — `logs/`, `data/debug`
- Tout `Path(__file__).parent.parent` du code

Utiliser `git mv` pour que l'historique suive les fichiers.

---

## 4. Tâches

### C1 — Référence avant déplacement

1. Fusionner `sprint-b-minimal` dans `main`, créer `sprint-c`.
2. `python -m pytest tests/ -q` → consigner la sortie brute et le code de retour.
3. `pip freeze` → fichier de référence hors dépôt.
4. Inventaire des fichiers suivis par Git, pour comparaison après déplacement.
5. Sauvegarde `backup` + `verify` de la mémoire. Le sprint touche `docker-compose.yml`.

### C2 — Aplatissement

Remonter le contenu de `assistant-bureau/` à la racine, par `git mv`, en traitant les collisions (piège 2).

Structure cible :

```
cortana-killer-atlas/
├── core/  core_conversational/  tools/  api/  ui/  desktop/
├── tests/  scripts/  config/  data/  logs/  models/
├── docs/
│   ├── briefs/  rapports/
│   ├── install_checklist.md  voice_runbook.md
│   └── RAPPORT_RULES.md
├── main.py  docker-compose.yml  requirements*.txt
├── README.md  .gitignore
└── atlas-extension/
```

### C3 — Rangement de la documentation

- **`rapport.md` est un répertoire portant une extension de fichier.** Le supprimer en tant que tel : son contenu (`RAPPORT_RULES.md`, `DIAGNOSTIC_V22.md`, `RAPPORT_CHAT3_FIN_MISSION.md`, `RAPPORT_SUPERVISEUR_V22.md`, `RAPPORT_V23.md`) rejoint `docs/`.
- **`RAPPORT_RULES.md` va dans `docs/`**, à la racine de la documentation : c'est une règle du projet, pas un rapport.
- Les six rapports de la racine de `assistant-bureau/` (`RAPPORT_V30`, `V31`, `V40`, `V50`, `V602`, `RAPPORT_DECISION_2026-04-08`) rejoignent `docs/rapports/`.
- Mettre à jour toutes les références à ces chemins, notamment dans les briefs et rapports existants.

### C4 — Correction des chemins

Reprendre la liste du piège 3, fichier par fichier. Vérifier, ne pas supposer.

### C5 — Recréation de l'environnement et vérification

1. Créer le nouveau venv à la racine.
2. Installer `requirements.txt`.
3. `pip freeze`, comparer à la référence C1, **signaler toute dérive**.
4. `python -m pytest tests/ -q` → **doit renvoyer 0 avec 376 tests**.
5. Si le compte diffère de 376, expliquer chaque écart. Un test qui disparaît silencieusement est un test perdu.
6. Démarrer Atlas, vérifier `/api/health` et une lecture de mémoire réelle.
7. `python scripts/doctor.py` → cohérent avec la nouvelle arborescence.

**Tant que C5 n'est pas conforme, aucun nettoyage.** On ne mélange pas un déplacement raté avec des suppressions.

### C6 — Suppression du code mort et des vestiges

Seulement après C5 conforme. Éléments inventoriés au sprint A, à confirmer avant suppression :

- **Stack vision MiniCPM-V** — gatée depuis la Réunion #5, preuve de non-appel établie au sprint A (`_try_vision` à 1 % de couverture). Suppression conditionnelle et documentée.
- `test_kokoro.py` à la racine — **fichier vide, 0 octet**
- `core_conversational/test_kokoro.py` — 0 % de couverture, à qualifier
- `petite_image.png` — 75 Ko, sans usage apparent
- Scripts ad hoc restants dans `tests/` (`debug_*.py`, `api_*_check.py`…) que B-minimal n'a pas traités : les déplacer vers `scripts/manual/` comme les quatre précédents
- `DialoGPT-medium` dans le cache Hugging Face — 1,7 Go, aucune référence dans le code (cache hors dépôt, simple signalement à Alexis)

Pour chaque suppression : la **preuve** qu'il n'est référencé nulle part (`grep` sur tout le dépôt), consignée dans le rapport.

### C7 — Hygiène Git et Docker

- **`.gitignore`** : ajouter `data/voices/`. Le fichier `data/voices/fr_FR-siwis-medium.onnx.json` a été versionné par erreur au commit `6a3453b` (risque L20) — le retirer du suivi (`git rm --cached`) sans le supprimer du disque.
- **Épingler l'image SearXNG par digest** (R-6), comme ChromaDB.
- **Volume nommé pour `/var/cache/searxng`** (R-7) : un volume anonyme est créé à chaque recréation du conteneur, et `39037e82…` est déjà orphelin.
- Vérifier qu'aucun secret ne subsiste dans le dépôt, en particulier celui de SearXNG dans `config/searxng/settings.yml`.

### C8 — Vérification finale et rapport

1. Suite verte de nouveau après le nettoyage : **376, ou écart expliqué**.
2. Atlas démarre, `/api/health` conforme.
3. `docker compose down` puis `up -d` : les 535 éléments sont toujours là.
4. Comparaison de l'inventaire Git avant/après : aucun fichier perdu par accident.
5. Rapport conforme à RAPPORT_RULES, 9 sections, dans `docs/rapports/RAPPORT_SPRINT_C.md`.

---

## 5. Critères de validation

- [ ] `sprint-b-minimal` fusionnée dans `main`, travail sur `sprint-c`
- [ ] Référence C1 consignée : suite, `pip freeze`, inventaire Git, sauvegarde mémoire
- [ ] `assistant-bureau/` a disparu, contenu à la racine, historique préservé (`git mv`)
- [ ] Collision des deux `README.md` traitée et documentée
- [ ] `rapport.md` n'existe plus en tant que répertoire ; `RAPPORT_RULES.md` dans `docs/`
- [ ] Rapports regroupés dans `docs/rapports/`
- [ ] Nouveau venv créé, **dérive de dépendances signalée**
- [ ] **`python -m pytest tests/ -q` → code 0, 376 tests**, avant et après nettoyage
- [ ] Atlas démarre, `/api/health` conforme, `doctor.py` cohérent
- [ ] `docker compose down` / `up` : 535 éléments intacts
- [ ] Suppressions justifiées par une preuve de non-référencement
- [ ] `data/voices/` ignoré, `.onnx.json` retiré du suivi
- [ ] Image SearXNG épinglée, volume nommé pour son cache
- [ ] Aucun fichier perdu (inventaire comparé)

## 6. Rappels de méthode

- **Un seul changement de nature à la fois.** Déplacer, vérifier, puis nettoyer. Jamais les deux ensemble.
- Ne pas corriger de défaut produit. Les chemins dispersés de `api/routes.py`, le mot d'éveil, le TTS : c'est B-complet.
- L'ancien venv reste jusqu'à ce que le nouveau ait fait passer les 376 tests.
- En cas de doute sur une commande touchant Docker ou la base : ne pas l'exécuter, demander.
- Un garde-fou se teste avec des commandes simulées. Règle permanente depuis I-1.
