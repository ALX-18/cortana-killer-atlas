# RAPPORT SPRINT M — Sécurisation de la mémoire long terme
Date: 17/09/2026
Agent: Claude Opus 5 (CHAT6, Claude Code Windows)

> Brief : `docs/briefs/BRIEF_SPRINT_M.md`. Règles : `rapport.md/RAPPORT_RULES.md`. Référence : rapport Sprint A, risque L21.
> Dépôt : `main` @ `d4a4acf`, synchronisé avec `origin/main`. Travaux menés le 17/09/2026 entre 03:00 et 03:25 environ (heure de Paris) ; Atlas arrêté pendant tout le sprint.

---

## 1. Résumé exécutif

**Statut global : VALIDÉ**, sous réserve de la décision d'architecture (M4), qui revient au superviseur et à Alexis.

**Réponses aux trois questions du brief :**

1. **Oui, la sauvegarde est prouvée restaurable.**
   - Emplacement : `C:\Users\alexis\Atlas_backups\memoire\chromadb_20260917_030200\`.
   - Archive `chromadb_data_20260917_030200.tar` (8 468 480 o), **SHA-256 `a973059ba180ca5b49e9cd6d74a910efd79f7de6e5bfe5d5639c77eaa902c05f`**.
   - Contenu : 121 fichiers, 8 203 064 o ; `chroma.sqlite3` SHA-256 `9d0db701…81732` ; `manifest.json` SHA-256 `0706b074…4fd08`.
   - Restauration dans le conteneur jetable `atlas_memcheck_20260917_030251` : 6/6 collections ; **535/535 éléments** avec identifiants, documents et métadonnées identiques ; 81 embeddings comparés à l'identique ; 20/20 requêtes vectorielles aux distances identiques à la production. Conteneur puis copie supprimés.
   - `assistant_chromadb` est **intact** : ses 121 fichiers ont, après le sprint, les mêmes empreintes que la sauvegarde.
   - Limite : la sauvegarde est sur le **même disque** que la production (section 7, M-L1).
2. **Oui, il existe d'autres états non persistés ou non sauvegardés, mais aucun aussi grave que L21.**
   - Aucun autre état Atlas ne vit uniquement dans un conteneur : le volume du conteneur Ollama ne contient que `mistral`, présent en natif ; SearXNG n'a qu'un cache dans `/tmp`.
   - En revanche, **rien sur l'hôte n'est sauvegardé** : l'Historique des fichiers est arrêté et OneDrive ne couvre pas le dépôt. Les éléments irremplaçables hors ChromaDB sont `habits.db`, `schedules.json`, `triggers.json`, `workflow_discord_spotify.yaml` (ignoré par Git) et les journaux JSONL (annexe B).
3. **Recommandation : option A, variante « volume Docker nommé », à court terme ; ChromaDB natif à moyen terme**, en même temps que la décision sur SearXNG.
   - Mesures : le montage d'un dossier Windows est **6,4 fois plus lent** en écriture (12,5 s contre 1,95 s) ; le volume nommé est identique à la production et aussi rapide que le natif.
   - Le natif 1.5.1 lit les données **sans migration**, avec des vecteurs identiques à l'octet, et l'aller-retour vers l'image 1.4.1 fonctionne.
   - Le natif ne fait pas disparaître Docker tant que SearXNG y reste (annexe C).

**Deux constats nouveaux, à arbitrer :**
- La mémoire est **en partie polluée par les tests** : au moins 40 éléments sur 535 sont des artefacts de test évidents, dont 20 des 25 documents. De plus, 213 des 479 éléments d'`atlas_memory` sont des doublons exacts.
- 26 des 30 dossiers d'index HNSW sont **orphelins**.

Ce qui est « irremplaçable » est donc réel, mais plus petit et plus sale que supposé.

---

## 2. Objectifs vs réalisation

| Objectif attendu (brief) | Résultat réel | Statut |
|---|---|---|
| M1.1 — Sauvegarde datée et horodatée hors dépôt, emplacement pérenne | `C:\Users\alexis\Atlas_backups\memoire\chromadb_20260917_030200\` (dossier `data/` + archive tar). Même disque que la production. | PASS (réserve M-L1) |
| M1.2 — Empreintes, taille, arborescence | `SHA256SUMS` (121 fichiers + archive), `manifest.json` (taille, arborescence, image, version, résumé mémoire), `manifest.json.sha256` | PASS |
| M1.3 — Restauration prouvée en conteneur jetable (nom et port distincts) | `atlas_memcheck_20260917_030251`, port 127.0.0.1:8101, même image par identifiant, `--pull never`, restauré **depuis l'archive**. 6 collections, bons volumes. | PASS |
| M1.4 — Comparaison collections, éléments, dimension, échantillon de contenus | Comparaison **exhaustive** des identifiants, documents et métadonnées (535/535) ; embeddings sur échantillon (81) ; dimension ; 20 requêtes vectorielles production vs restauration ; extraits consignés | PASS |
| M1.5 — Conteneur jetable détruit, original intact | Jetable supprimé (`cleanup_container_absent: true`) ; production 121/121 fichiers identiques à la sauvegarde après le sprint | PASS |
| Livrable `scripts/backup_memory.py` | Livré (`backup`, `verify`), avec garde-fous | PASS |
| M2 — Inventaire (noms, volumes, dimension, modèle, dates, disque, format, versions) | Annexe A | PASS |
| M3 — Autres états non persistés + tableau perdu / re-téléchargeable | Annexe B | PASS |
| M4 — Analyse A (Docker corrigé) / B (natif), coûts, risques, réversibilité, recommandation | Annexe C ; 3 essais mesurés sur copies (bind mount, volume nommé, natif) + aller-retour de compatibilité | PASS |
| M5 — Rapport 9 sections | Ce document | PASS |
| Aucune migration, aucune modification de `docker-compose.yml`, aucun code existant modifié | Respecté (section 3) | PASS |

---

## 3. Architecture projet mise à jour

```
assistant-bureau/
├── scripts/
│   └── backup_memory.py                 ← NOUVEAU Sprint M
└── docs/rapports/
    └── RAPPORT_SPRINT_M.md              ← NOUVEAU Sprint M
```

Hors dépôt :

```
C:\Users\alexis\Atlas_backups\memoire\
├── chromadb_20260917_030200\                        ← SAUVEGARDE DE RÉFÉRENCE (vérifiée)
│   ├── data\                                        (121 fichiers, copie de /data)
│   ├── chromadb_data_20260917_030200.tar            (8 468 480 o, sha256 a973059b…)
│   ├── manifest.json / manifest.json.sha256
│   ├── SHA256SUMS
│   ├── verify_20260917_030228.json                  (1ère vérification : critère de requête mal posé, voir §5)
│   └── verify_20260917_030255.json                  (vérification conforme)
└── chromadb_20260917_030142_NONCONFORME_ne_pas_utiliser\   (1re tentative, signalée non conforme par le script)
```

**Fichiers existants modifiés : aucun.** `docker-compose.yml` n'a pas été modifié ; `git status` ne montre que les deux fichiers nouveaux et `data/voices/` (hérité du sprint A).

**Opérations Docker effectuées sur la production (`assistant_chromadb`), toutes en lecture :** `docker inspect`, `docker diff`, `docker exec` (`sha256sum`, `find`, `stat`, `cat /config.yaml`, `chroma --version`, `ls`), `docker cp` depuis le conteneur, et des requêtes HTTP de lecture (`version`, `collections`, `count`, `get`, `query`). **Aucun** `stop`, `restart`, `rm`, `pause`, `compose`, ni écriture HTTP.

**Objets jetables créés puis supprimés :** conteneurs `atlas_memcheck_20260917_030225`, `atlas_memcheck_20260917_030251`, `atlas_memcheck_m4docker`, `atlas_memcheck_m4roundtrip`, `atlas_memcheck_m4vol` ; volume `atlas_memcheck_vol` ; quatre conteneurs `--rm` d'inspection de volumes en lecture seule (dont deux sans effet, à cause d'une erreur d'échappement des arguments) ; serveur natif `chroma run` sur copie (port 8102) ; copies de travail dans `%TEMP%`. Vérification finale : `docker ps -a` ne liste plus que `atlas_searxng`, `assistant_chromadb`, `assistant_ollama` (arrêté depuis le sprint A), et aucun volume `memcheck` ne subsiste.

---

## 4. Détail des implémentations

### `scripts/backup_memory.py` (nouveau)

**Rôle :** sauvegarde reproductible de `/data` du conteneur ChromaDB et preuve de restauration. Dépendances : bibliothèque standard + CLI `docker`.

**Garde-fous :**
- La fonction `docker()` **refuse** toute sous-commande mutante (`rm`, `stop`, `kill`, `restart`, `pause`, `unpause`, `update`, `rename`, `compose`) dont les arguments contiennent `assistant_chromadb`.
- Le conteneur de vérification porte obligatoirement le préfixe `atlas_memcheck_` (assertion avant création et avant suppression).
- Il est créé à partir de l'**identifiant** d'image du manifeste, avec `--pull never` : aucune mise à jour d'image possible.
- La vérification restaure depuis l'**archive** vers un dossier temporaire, jamais depuis le dossier de sauvegarde lui-même, qu'un serveur pourrait modifier.

**`backup`**
1. `docker inspect` : conteneur démarré, identifiant d'image ; `/config.yaml` doit contenir `persist_path: "/data"`, sinon abandon.
2. Résumé de la mémoire par l'API (lecture) : collections, nombres d'éléments, dimension, fonction d'embedding, clés de métadonnées, dates extrêmes.
3. **Attente de stabilité** : empreintes de `/data` identiques à 10 s d'intervalle (12 essais au plus). Ajouté après la première tentative (section 5).
4. `docker cp`, puis empreintes côté hôte et **nouvelles empreintes dans le conteneur**. La copie n'est déclarée conforme que si « avant = après = copie ».
5. Archive tar, `manifest.json`, `SHA256SUMS`, `manifest.json.sha256`. Code de retour 2 si non conforme.

**`verify <dossier>`**
1. Contrôle de `manifest.json`, des 121 fichiers et de l'archive contre leurs empreintes.
2. Extraction de l'archive dans `%TEMP%`, puis `docker run` du conteneur jetable sur 127.0.0.1:`--port` et attente du heartbeat.
3. Comparaison avec le manifeste : noms de collections, volumes, dimensions.
4. Comparaison avec la production, en lecture : ensemble complet des identifiants, documents et métadonnées de chaque collection ; embeddings sur un échantillon régulier (`--samples`, 25 par défaut) ; 5 requêtes vectorielles par collection, dont les distances doivent être identiques des deux côtés (au 1e-5 près) ; l'élément sonde doit figurer dans le top 5, ou être masqué par un doublon exact à distance nulle. Indique aussi si la production a changé depuis la sauvegarde.
5. `finally` : suppression du conteneur jetable et de la copie, puis contrôle de l'absence du conteneur. Rapport `verify_<horodatage>.json` ; code 0 seulement si tout est conforme.

**Intégration :** script autonome, sans import d'Atlas. Pas encore référencé dans `docs/install_checklist.md` (recommandation P1, section 9).

### Hors périmètre
Script jetable `m4_bench.py`, hors dépôt : comparaison et mini-banc d'écriture et de lecture, **uniquement sur des copies** (ports 8102 à 8105), jamais sur la production (assertion sur le port 8001).

---

## 5. Résultats des tests

Pas de test unitaire dans ce sprint (brief : aucun code produit hors outillage). `test_chroma_integration` n'a **pas** été lancé (règle du brief). Les « tests » sont les exécutions réelles du script, avec leurs résultats bruts.

### Sauvegarde, 1re tentative — NON CONFORME (conservée comme trace)
```
python scripts/backup_memory.py backup
```
```
[03:01:45]   121 fichiers, 8203064 octets ; archive chromadb_data_20260917_030142.tar sha256=a973059ba180ca5b...
[03:01:45] NON CONFORME : la base a changé pendant la copie : ['2620e434-…/data_level0.bin', '2620e434-…/length.bin', '901a33f8-…/data_level0.bin', '901a33f8-…/length.bin', 'c7abbe3b-…/length.bin', 'ec2c6549-…/data_level0.bin', 'ec2c6549-…/length.bin']
exit=2
```
Cause : la version initiale hachait `/data`, **puis** interrogeait l'API. Au premier accès après le redémarrage du conteneur (02:45, heure de Paris ; 00:45 UTC), ChromaDB 1.4.1 a réécrit les 4 index HNSW actifs. La lecture seule par l'API **provoque donc des écritures**, un comportement important pour toute procédure future. Correction dans le script : lecture d'abord, attente de stabilité ensuite. L'archive de cette tentative a la même empreinte que la sauvegarde de référence : la copie avait bien capturé l'état final. Elle est néanmoins marquée `_NONCONFORME_ne_pas_utiliser`.

### Sauvegarde de référence — CONFORME
```
python scripts/backup_memory.py backup
```
```
[03:02:00] Conteneur assistant_chromadb — image sha256:7605e7b398f9 — chroma 1.4.1
[03:02:00] Résumé de la mémoire via l'API (lecture seule)…
[03:02:00] Attente de stabilité de /data (empreintes identiques à 10 s d'intervalle)…
[03:02:11]   stable : 121 fichiers
[03:02:11] docker cp assistant_chromadb:/data → C:\Users\alexis\Atlas_backups\memoire\chromadb_20260917_030200\data
[03:02:13]   121 fichiers, 8203064 octets ; archive chromadb_data_20260917_030200.tar sha256=a973059ba180ca5b49e9cd6d74a910efd79f7de6e5bfe5d5639c77eaa902c05f
[03:02:13]   atlas_context_apps          0 éléments  dim=None  None → None
[03:02:13]   atlas_documents            25 éléments  dim=768  2026-06-25T21:06:35.107865 → 2026-09-16T19:17:02.273799
[03:02:13]   atlas_habits                0 éléments  dim=None  None → None
[03:02:13]   atlas_errors               19 éléments  dim=768  2026-06-25T21:06:48.907751 → 2026-09-16T19:22:44.738526
[03:02:13]   atlas_memory              479 éléments  dim=384  2026-02-24T19:18:25.174270 → 2026-09-16T19:21:57.711067
[03:02:13]   atlas_conversations        12 éléments  dim=768  2026-06-25T21:06:29.328564 → 2026-09-16T19:21:06.475919
[03:02:13] Copie conforme : base inchangée pendant la copie, empreintes identiques.
exit=0
```

### Vérification, 1er passage — NON CONFORME (critère mal posé)
```
python scripts/backup_memory.py verify "C:\Users\alexis\Atlas_backups\memoire\chromadb_20260917_030200"
```
```
atlas_errors  … requête=False ["la requête vectorielle ne retrouve pas l'élément sonde"]
atlas_memory  … requête=False ["la requête vectorielle ne retrouve pas l'élément sonde"]
exit=2
```
Diagnostic sur la **production**, par une requête en lecture identique : les trois premiers résultats sont à distance ≈ 0 (−1,5e−7 et −2,4e−7) et portent **le même texte** que la sonde (doublons exacts). L'ordre entre ex æquo n'est pas garanti ; la production se comporte exactement pareil. Le critère « la sonde est première » a été remplacé par : **mêmes distances sur la production et sur la restauration**, et sonde dans le top 5 ou masquée par un doublon exact.

### Vérification de référence — CONFORME
```
python scripts/backup_memory.py verify "C:\Users\alexis\Atlas_backups\memoire\chromadb_20260917_030200"
```
```
[03:02:51]   empreintes OK (121 fichiers)
[03:02:51] 2/5 Conteneur jetable atlas_memcheck_20260917_030251 (image sha256:7605e7b398f9, port 8101, --pull never)…
[03:02:53]   atlas_context_apps          0/0      docs+méta comparés=0 embeddings comparés=0 …
[03:02:53]   atlas_conversations        12/12     docs+méta comparés=12 embeddings comparés=12 requêtes identiques=5/5 (sonde trouvée 5, masquée par doublons 0) OK
[03:02:53]   atlas_documents            25/25     docs+méta comparés=25 embeddings comparés=25 requêtes identiques=5/5 (sonde trouvée 5, masquée par doublons 0) OK
[03:02:54]   atlas_errors               19/19     docs+méta comparés=19 embeddings comparés=19 requêtes identiques=5/5 (sonde trouvée 5, masquée par doublons 0) OK
[03:02:54]   atlas_habits                0/0      …
[03:02:54]   atlas_memory              479/479    docs+méta comparés=479 embeddings comparés=25 requêtes identiques=5/5 (sonde trouvée 5, masquée par doublons 0) OK
[03:02:55] RESTAURATION PROUVÉE : collections, volumes, dimensions, documents, métadonnées, échantillon d'embeddings et requête vectorielle identiques.
exit=0
```
`verify_20260917_030255.json` : `hashes_ok=true`, `live_unchanged_since_backup=true`, `cleanup_container_absent=true`, `restorable=true`.

**Échantillon de contenus restaurés** (extrait du rapport JSON, identique en production) :
- `atlas_conversations` / `conv_371374fcecfc` : « Utilisateur: VA dans les parametres de discord / Atlas: Je lance la configuration de Discord… »
- `atlas_documents` / `doc_94195835b926` : « Le projet Atlas 40d430 est un assistant bureau Windows 100% local. » (artefact de test)
- `atlas_errors` / `err_08420c4ae4b2` : « intent=unknown cible=notepad app= »
- `atlas_memory` / `action_history_fe57dbb82900` : « Recherche effectuée : 'météo Paris'. 5 résultats trouvés via duckduckgo_fallback… »

### Intégrité de la production après le sprint
```
container_hashes("assistant_chromadb") vs manifest.json
production : fichiers 121 | identiques à la sauvegarde : 121 / 121 | écarts : []
{'atlas_context_apps': 0, 'atlas_documents': 25, 'atlas_habits': 0, 'atlas_errors': 19, 'atlas_memory': 479, 'atlas_conversations': 12}
```

### Essais M4 (sur copies de l'archive)

| Candidat | Port | Identiques à la prod. (ids / docs / méta) | Embeddings | Requêtes (distances identiques) | Écriture 50×10 éléments | 100 requêtes |
|---|---|---|---|---|---|---|
| Image 1.4.1, **dossier Windows monté** (option A telle que rédigée) | 8103 | 535/535 | identiques (écart max 0) | 20/20 | **12,484 s** | 2,021 s |
| Image 1.4.1, **volume Docker nommé** (option A, variante) | 8105 | 535/535 | identiques | 20/20 | **1,952 s** | **0,518 s** |
| **ChromaDB natif 1.5.1** (`chroma run`, option B) | 8102 | 535/535 | écart max **2,0e−8** en JSON ; **535/535 vecteurs stockés identiques à l'octet** dans SQLite | 18/20 (écart au 5e chiffre, dû à l'arrondi) | **1,926 s** | 0,702 s |
| Image 1.4.1 relisant la copie **écrite par 1.5.1** (aller-retour) | 8104 | 535/535 | identiques | 20/20 | — | — |

- Après ouverture et écriture par la 1.5.1, les versions de migration restent inchangées (`embeddings_queue` 2, `metadb` 6, `sysdb` 10) et les 21 tables sont les mêmes. Les 500 éléments écrits par la 1.5.1 sont relus par la 1.4.1.
- Chaque banc n'a été exécuté **qu'une fois** : ce sont des ordres de grandeur, pas une statistique.

---

## 6. Comportement observé en scénarios réels

| ID | Opération | Attendu | Observé | Statut |
|---|---|---|---|---|
| S01 | `backup` sur la production (1re fois) | Copie conforme | Détection d'écritures pendant la copie → NON CONFORME, code 2 | Garde-fou PASS / copie FAIL |
| S02 | `backup` corrigé | Copie conforme | Stable en 11 s, copie identique, code 0 | PASS |
| S03 | `verify` (1re fois) | Restauration prouvée | Faux négatif dû aux doublons exacts → critère corrigé | FAIL (critère) |
| S04 | `verify` corrigé | Restauration prouvée | 535/535, 20/20, conteneur supprimé, code 0 | PASS |
| S05 | Production après le sprint | Intacte | 121/121 empreintes identiques, volumes inchangés, conteneur actif | PASS |
| S06 | Natif 1.5.1 sur copie | Lecture sans perte | 535/535, vecteurs identiques à l'octet, pas de migration | PASS |
| S07 | Aller-retour 1.5.1 → 1.4.1 | Relecture | 535/535 + 500 éléments de test relus | PASS |
| S08 | Volume nommé (jetable) | Même comportement que la prod. | Identique, plus rapide que le montage Windows | PASS |
| S09 | Inspection des volumes Docker (lecture seule) | Inventaire | 4 volumes : Ollama (4,1 Go, `mistral` seul), cache SearXNG vide, un vide, un résidu Kubernetes de 1,1 Go hors projet | PASS |

Atlas lui-même n'a pas été lancé : le brief interdit toute écriture dans la base réelle, et le démarrage d'Atlas en provoque (`get_or_create_collection`, souvenirs).

---

## 7. Limites et risques identifiés

| # | Description | Sévérité | Mitigation proposée |
|---|---|---|---|
| M-L1 | La sauvegarde est sur le **même disque** que la production (C:). Une panne disque ou une réinstallation emporte les deux. | **Élevé** | Alexis : copier `chromadb_20260917_030200\` sur un support externe. Un cloud est possible, mais la mémoire contient des données personnelles (conversations, habitudes, titres de fenêtres) : à chiffrer avant. |
| M-L2 | **L21 reste ouvert** : la production vit toujours dans la couche du conteneur. La sauvegarde réduit l'impact d'une perte, pas son risque. | **Élevé** | Sprint de migration (annexe C). D'ici là : ne pas lancer `docker compose down` ni `up --force-recreate`, ne pas mettre à jour l'image ; relancer `backup` + `verify` avant toute opération Docker. |
| M-L3 | La lecture par l'API **réécrit** les index HNSW après un redémarrage : une copie « à chaud » sans contrôle peut être incohérente. | Moyen | Le script contrôle la stabilité ; toute procédure manuelle doit faire de même, ou arrêter Atlas et attendre. |
| M-L4 | **Mémoire polluée par les tests** : au moins 40/535 éléments sont des artefacts évidents (20/25 documents, 5/19 erreurs, 3/12 conversations, 12/479 souvenirs). S'y ajoutent des actions réellement exécutées par les tests (ex. `get_diagnostics` ×31). Classement heuristique, borne basse. | Moyen | Sprint B : isoler les tests de la base réelle (déjà L13/A.4). Nettoyage de la base **après** migration, et seulement sur décision. |
| M-L5 | **Doublons** : 213/479 éléments d'`atlas_memory` sont des doublons exacts de texte, ce qui dégrade le rappel (les top-k sont occupés par des copies). | Moyen | Déduplication à l'écriture (sprint B). |
| M-L6 | **Deux modèles d'embedding** : `atlas_memory` en 384 dimensions, calculées par le client Chroma (`all-MiniLM-L6-v2`, modèle anglais, cache `~/.cache/chroma`) ; les partitions en 768 dimensions (e5-base, calculées par Atlas). Toutes les collections déclarent pourtant la fonction d'embedding « default ». Une requête textuelle sans vecteur sur une partition 768 échouerait. Changer de version du client pourrait changer le modèle de `atlas_memory`. | Moyen | À figer dans la décision de migration : même client ou ré-encodage explicite. |
| M-L7 | **26 dossiers HNSW orphelins sur 30**, issus de collections supprimées (dont une du 16/09, créée par les tests du sprint A). Environ 4,4 Mo inutiles, sans risque. | Faible | Nettoyage éventuel après migration. |
| M-L8 | Version du client (1.5.1) plus récente que celle du serveur (1.4.1). Aucune anomalie constatée, mais combinaison non garantie par l'éditeur. | Faible | À aligner lors de la migration. |
| M-L9 | Bancs M4 exécutés une seule fois, avec des chemins réseau différents (port publié Docker contre boucle locale native). | Faible | Suffisant pour l'écart de facteur 6 ; à refaire si la décision dépend d'écarts < 50 %. |
| M-L10 | Aucune sauvegarde des états hôte irremplaçables (`habits.db`, `schedules.json`, `triggers.json`, `workflow_discord_spotify.yaml`, JSONL, `logs/`). | Moyen | Étendre `backup_memory.py` ou une tâche planifiée (décision). |
| M-L11 | La mémoire RAM de la VM WSL varie fortement (8,3 Go au démarrage de Docker le 16/09, 4,0 Go mesurés à 03:15). Le gain de l'option B n'est donc pas un chiffre fixe. | Faible | Mesure sur plusieurs heures si l'arbitrage RAM en dépend. |

---

## 8. Checklist de validation

- [x] **Sauvegarde produite, horodatée, empreintes consignées** : section 1 et section 5 (`SHA256SUMS`, archive `a973059b…`).
- [x] **Restauration effectivement prouvée dans un conteneur jetable, avec comparaison des six collections** : section 5, vérification de référence (6/6, 535/535, 20/20).
- [x] **Conteneur jetable détruit, `assistant_chromadb` intact et fonctionnel** : `cleanup_container_absent=true` ; production 121/121 empreintes identiques et API répondante (section 5).
- [x] **Inventaire des collections livré** : annexe A.
- [x] **Recherche d'autres états non persistés livrée, avec le tableau perdu/re-téléchargeable** : annexe B.
- [x] **Analyse comparée livrée avec recommandation argumentée** : annexe C.
- [x] **Aucune migration exécutée** : section 3 (seules des copies jetables ont été ouvertes par d'autres versions).
- [x] **Aucune modification de `docker-compose.yml`** : `git status` (section 3).
- [x] **Aucun fichier de code existant modifié** : `git status` (section 3).

---

## 9. Recommandations pour le sprint suivant

### P1 — avant tout autre sprint
- **P1.1 Copie hors machine** de la sauvegarde de référence (M-L1). Action d'Alexis.
- **P1.2 Décision d'architecture** sur la base de l'annexe C. Recommandation : volume nommé maintenant, natif avec SearXNG ensuite.
- **P1.3 Sprint de migration** (M-bis), une fois la décision prise :
  1. Arrêter Atlas.
  2. `backup` + `verify`.
  3. Copie des données vers la nouvelle destination.
  4. Vérification de la destination avec les mêmes comparaisons (`verify` adapté à une URL cible).
  5. Recréation du conteneur, qui est le **point de non-retour** pour la couche actuelle.
  6. Nouvelle vérification.
  7. Test `docker compose down` / `up` sur la nouvelle configuration.
  8. Conservation de l'ancienne sauvegarde.
- **P1.4 Interdire aux tests d'écrire dans la base réelle** (B-minimal) : base Chroma de test séparée ou `tmp_path`. Sans cela, la mémoire continue de se polluer à chaque passage de la suite.

### P2
- P2.1 Ajouter `backup_memory.py backup` + `verify` à `docs/install_checklist.md` et au protocole « avant toute opération Docker ».
- P2.2 Étendre la sauvegarde aux états hôte irremplaçables (M-L10), éventuellement par tâche planifiée hebdomadaire.
- P2.3 Épingler l'image `chromadb/chroma` par digest (`sha256:7605e7b3…`) au lieu de `:latest`, **au moment de la migration**.
- P2.4 Unifier ou documenter explicitement les fonctions d'embedding par collection (M-L6).

### P3
- P3.1 Déduplication à l'écriture (M-L5) ; nettoyage des artefacts de test et des orphelins HNSW après migration, sur décision.
- P3.2 Refaire les bancs M4 sur plusieurs passages si la décision se joue sur la performance.

### Ordre des sprints proposé
**M (fait) → M-bis (migration, décision requise) → B-minimal → C → B-complet.**

B-minimal peut précéder M-bis s'il se limite à `tests/`, mais l'isolation des tests vis-à-vis de ChromaDB (P1.4) gagne à être faite tôt : chaque exécution de la suite modifie aujourd'hui la base qu'on cherche à préserver.

---

# Annexes

## Annexe A — Inventaire de la mémoire (M2)

**Serveur :** `chroma 1.4.1` (API `/api/v2`, version d'API « 1.0.0 ») dans `assistant_chromadb`, image `chromadb/chroma:latest`, identifiant `sha256:7605e7b398f96dba833ed1b6272f815b9d33414dde45c68bd246e84447db8591` (téléchargée en février/mars 2026), Debian 13, `persist_path: "/data"`.
**Client Atlas :** `chromadb` 1.5.1 (`.venv`), `HttpClient(localhost:8001)`.

| Collection | Éléments | Dimension | Modèle d'embedding | Plus ancien | Plus récent | Clés de métadonnées | Doublons exacts | Artefacts de test (heuristique) |
|---|---|---|---|---|---|---|---|---|
| `atlas_memory` | **479** (404 `action_history`, 75 `habit`) | **384** | `all-MiniLM-L6-v2`, calculé **par le client Chroma** (`add` sans embeddings, `core/memory_manager.py` l.180) | 2026-02-24 19:18 | 2026-09-16 19:21 | category, created_at, foreground, process, query, results, sessions_seen, source, target, timestamp, tool | 213 | ≥ 12 |
| `atlas_conversations` | 12 | 768 | `intfloat/multilingual-e5-base`, calculé par Atlas (`core_conversational/memory_core.py`) | 2026-06-25 21:06 | 2026-09-16 19:21 | created_at, intent_category, success, timestamp, user_msg | 0 | ≥ 3 |
| `atlas_documents` | 25 | 768 | e5-base | 2026-06-25 21:06 | 2026-09-16 19:17 | chunk_index, created_at, ingested_at, mime_type, source, timestamp | 2 | **≥ 20** |
| `atlas_errors` | 19 | 768 | e5-base | 2026-06-25 21:06 | 2026-09-16 19:22 | app_context, cause, created_at, grounding_layer_failed, intent_category, target, timestamp | 3 | ≥ 5 |
| `atlas_context_apps` | 0 | — | — | — | — | — | — | — |
| `atlas_habits` | 0 | — | — | — | — | — | — | — |
| **Total** | **535** | | | | | | 218 | ≥ 40 |

Toutes les collections : `hnsw:space = cosine`. La fonction d'embedding déclarée côté serveur est `{"type":"known","name":"default"}` pour **toutes**, y compris celles en 768 dimensions (M-L6).

Les heures citées sont les valeurs de métadonnées brutes (`created_at` / `timestamp`), sans conversion de fuseau.

Sources des entrées `atlas_memory` : sans source 375, `duckduckgo_fallback` 45, `fallback_link` 37, `duckduckgo` 15, `searxng` 7. Documents : `atlas_e2e_doc.md` (5), les autres sans source.

**Volume et format de persistance** (analysés sur la copie, SQLite ouvert en `mode=ro&immutable=1`) :
- `/data` : 121 fichiers, **8 203 064 o** (archive 8 468 480 o) ; empreinte du conteneur (`docker diff`) : 8,61 Mo.
- `chroma.sqlite3` (2 699 264 o) : **source de vérité**. 21 tables : `collections`, `segments`, `embeddings`, `embedding_metadata` (dont documents sous `chroma:document`), `embeddings_queue` (vecteurs, 535 lignes, `max seq_id` 535), recherche plein texte FTS5, `migrations` (`embeddings_queue` v2, `metadb` v6, `sysdb` v10), `tenants` (`default_tenant`), `databases` (`default_database`). Pas de fichier `-wal` au moment de la copie.
- 30 dossiers HNSW `<uuid>/` (`header.bin`, `data_level0.bin`, `length.bin`, `link_lists.bin`, 167 à 321 Ko) ; **4 référencés** par un segment `hnsw-local-persisted` (`atlas_memory`, `atlas_conversations`, `atlas_documents`, `atlas_errors`), **26 orphelins** datés du 25/02 au 16/09/2026.
- 12 segments pour 6 collections (métadonnées + vecteurs).
- Les index HNSW sont **reconstructibles** à partir de SQLite : ce qui est irremplaçable tient en un fichier de 2,7 Mo.

**Dépendances de relecture :** pour interroger `atlas_memory` par texte, il faut le même modèle `all-MiniLM-L6-v2` que le client Chroma (`~/.cache/chroma/onnx_models`, 167 Mo sur ce poste) ; pour les partitions, `intfloat/multilingual-e5-base` (1,1 Go dans le cache Hugging Face).

---

## Annexe B — États non persistés ou non sauvegardés (M3)

Aucune sauvegarde système active : service Historique des fichiers (`fhsvc`) **arrêté**, et OneDrive (`C:\Users\alexis\OneDrive`) ne couvre pas `C:\Users\alexis\Cortana_Killer`. Le code et `settings.json` sont sur GitHub (`origin/main` = `d4a4acf`).

| Élément | Emplacement | Taille | Persisté sur l'hôte ? | Sauvegardé ? | En cas de remise à zéro de la machine |
|---|---|---|---|---|---|
| **Mémoire ChromaDB** (6 collections) | Couche d'écriture de `assistant_chromadb` (`/data`), physiquement dans `%LOCALAPPDATA%\Docker\wsl\disk\docker_data.vhdx` (22,84 Go en tout) | 8,2 Mo | **Non** (L21) | **Oui, depuis ce sprint** : `Atlas_backups\memoire\chromadb_20260917_030200`, même disque | **Irremplaçable** (en partie polluée, M-L4) |
| `data/habits.db` | Hôte | 24 Ko | Oui | Non (hors Git) | **Irremplaçable** (habitudes apprises, 131 processus) |
| `data/schedules.json`, `data/triggers.json` | Hôte | 0,9 + 0,5 Ko | Oui | Non (hors Git) | **Irremplaçable** (créés par l'utilisateur ; 2 tâches, 1 trigger) |
| `data/workflows/workflow_discord_spotify.yaml` | Hôte | 0,4 Ko | Oui | **Non** (exclu par `.gitignore:70`) | **Irremplaçable** (workflow utilisateur) |
| `data/workflows/` (4 modèles) | Hôte | 3 Ko | Oui | Oui (Git) | Récupérable (Git) |
| `data/atlas_actions.jsonl`, `audit_log.jsonl`, `file_reorg_history.jsonl` | Hôte | 186 + 4 + 3 Ko | Oui | Non | **Irremplaçable** (historique et métriques ; pollué par les tests, sprint A L13). `file_reorg_history` sert au rollback des réorganisations. |
| `data/file_index.json` | Hôte | 0,6 Ko | Oui | Non | Régénérable (réindexation) |
| `logs/atlas.log` (+ captures) | Hôte | 2 Mo | Oui | Non | Perte d'historique de diagnostic, non bloquante |
| `data/debug/`, `Cortana_Killer/data/debug/` | Hôte | ~12 Mo | Oui | Non | Jetable |
| `config/settings.json`, `config/searxng/settings.yml` | Hôte (bind mount pour SearXNG) | — | Oui | Oui (Git) ; ⚠ secret SearXNG en clair dans Git | Récupérable |
| `atlas_searxng` : état | Couche du conteneur : `/tmp/sxng_cache_*.db` (+ `/etc/ssl/certs` régénéré) ; volume anonyme `39037e82…` monté sur `/var/cache/searxng`, **vide** | 438 Ko | Non | Non | **Re-créable** (cache) ; configuration dans Git |
| `assistant_ollama` (arrêté) | Volume nommé `assistant-bureau_ollama_data` | 4,1 Go | Dans la VM | Non | **Re-téléchargeable** : ne contient que `mistral:latest`, **déjà présent en natif** (même digest `6577803aa9a0`). Aucun modèle unique. Contient aussi une clé `id_ed25519` propre au conteneur, sans usage pour Atlas. |
| Volume anonyme `bebccf9e…` | VM Docker | 1,16 Go | Dans la VM | Non | **Hors projet** : `/var` d'un nœud Kubernetes (etcd, pods) créé par Docker Desktop le 16/09 à 19:12 (heure de Paris) ; Kubernetes est **désactivé** dans les réglages. Candidat au nettoyage, sur décision. |
| Volume anonyme `853e767d…` | VM Docker | 0 | — | — | Vide, hors projet |
| Modèles Ollama natifs (qwen2.5:7b, qwen2.5:14b, minicpm-v, mistral) | `%USERPROFILE%\.ollama\models` | 21,9 Go | Oui | Non | **Re-téléchargeables** (`ollama pull`) ; seul `qwen2.5:7b` est utilisé |
| Whisper `base` | `~/.cache/huggingface/hub/models--Systran--faster-whisper-base` | 142 Mo | Oui | Non | Re-téléchargeable (téléchargé à la 1re transcription) |
| e5-base (embeddings des partitions) | `~/.cache/huggingface/hub/models--intfloat--multilingual-e5-base` | 1,1 Go | Oui | Non | Re-téléchargeable ; **indispensable** pour relire les partitions par texte |
| MiniLM (embeddings d'`atlas_memory`) | `~/.cache/chroma/onnx_models/all-MiniLM-L6-v2` | 167 Mo | Oui | Non | Re-téléchargeable par le client Chroma ; **indispensable** pour `atlas_memory` (M-L6) |
| DialoGPT-medium | `~/.cache/huggingface/hub/models--microsoft--DialoGPT-medium` | 1,7 Go | Oui | Non | **Inutilisé** par Atlas (aucune référence dans le code) : cache mort |
| EasyOCR fr+en | `~/.EasyOCR` | 94 Mo | Oui | Non | Re-téléchargeable |
| OpenWakeWord (support) | `site-packages/openwakeword/resources/models` du venv | ~2 Mo | Oui | Non | Re-téléchargeable (`download_voice_models.py`) ; perdu à chaque recréation du venv |
| `hey_atlas.onnx`, voix Piper siwis | `models/wakewords/`, `data/voices/` | 0,2 + 63 Mo | Oui | Non (hors Git) | Re-téléchargeables **tant que les sources existent** (release GitHub d'un tiers, Hugging Face) ; empreintes consignées au sprint A (`ea196d0e…`, `641d1ab0…`) |
| Environnements Python `.venv`, `venv` | Racine du dépôt | plusieurs Go | Oui | Non | Re-créables (`requirements.txt`, non figé : versions différentes à la réinstallation) |
| Sauvegardes du sprint A | `%TEMP%\claude\…\scratchpad\` | 7,6 Mo + données | Oui | — | **Volatiles** (dossier temporaire) : non vérifiées, remplacées par la sauvegarde de ce sprint |

**Synthèse — ce qui serait réellement perdu :** la mémoire ChromaDB (sauvegardée depuis ce sprint, mais sur le même disque), `habits.db`, `schedules.json`, `triggers.json`, `workflow_discord_spotify.yaml`, l'historique JSONL et les journaux. Tout le reste est re-téléchargeable ou dans Git.

---

## Annexe C — Analyse comparée : Docker corrigé contre ChromaDB natif (M4)

### Mesures communes (section 5)
- Données : **compatibles** entre 1.4.1 (conteneur) et 1.5.1 (natif), dans les deux sens, **sans migration de schéma**, vecteurs identiques à l'octet.
- Performances sur copies (une exécution) : écriture de 50×10 éléments en **12,5 s** avec un dossier Windows monté, **1,95 s** avec un volume nommé, **1,93 s** en natif ; 100 requêtes en 2,0 s / 0,52 s / 0,70 s.
- Mémoire : ChromaDB natif **128 Mo** de working set (487 Mo privés) ; conteneur ChromaDB 44 à 75 Mo ; SearXNG 120 à 135 Mo ; **VM WSL 4,0 à 8,3 Go** selon le moment (M-L11).

### Option A — conserver Docker, corriger le montage

**Modification précise** (à faire au sprint de migration, **pas ici**). Dans `docker-compose.yml`, service `chromadb` :

A1 — dossier de l'hôte (ce que le montage actuel voulait faire) :
```yaml
    volumes:
      - ./data/chromadb:/data          # au lieu de ./data/chromadb:/chroma/chroma
```
A2 — volume nommé (**recommandé** si l'on reste sur Docker) :
```yaml
    volumes:
      - chroma_data:/data
volumes:
  ollama_data:
  chroma_data:
```
Et dans les deux cas : `image: chromadb/chroma@sha256:7605e7b3…` au lieu de `:latest`.

**Procédure de migration (A1 et A2)**
1. Arrêter Atlas.
2. `backup_memory.py backup` puis `verify` (code 0 exigé).
3. Préparer la destination :
   - A1 : extraire l'archive dans `data/chromadb/` (actuellement vide).
   - A2 : `docker volume create` + `docker create` jetable + `docker cp` des données (technique validée en S08).
4. Démarrer un conteneur **jetable** sur la destination et comparer à la production (fonctions de `verify`).
5. **Point de non-retour** : `docker compose up -d --force-recreate chromadb`. La couche actuelle est détruite ; seules la sauvegarde et la destination restent.
6. Revérifier la nouvelle production contre le manifeste.
7. Tester `docker compose down` puis `up -d chromadb searxng`, et revérifier.
8. Garder la sauvegarde.

**Risques**
- A1 : **écritures 6,4 fois plus lentes** (montage Windows ↔ VM). Verrouillage SQLite sur un système de fichiers partagé : non éprouvé en charge.
- A2 : les données restent dans `docker_data.vhdx`, **invisibles depuis Windows**. La sauvegarde passe toujours par `docker cp` (le script couvre ce cas s'il reçoit un conteneur monté sur `/data`). Une réinitialisation de Docker Desktop (« Reset to factory defaults ») efface les volumes.
- Commun : l'étape 5 est irréversible pour la couche actuelle ; elle est couverte par une sauvegarde prouvée restaurable.

**Coût réel :** faible (~1 h), la procédure étant déjà outillée.
**Réversibilité :** élevée, par restauration de l'archive.

**Ce qui reste :** dépendance à Docker Desktop, WSL2 et la virtualisation BIOS (un blocage déjà rencontré au sprint A) ; VM de **4 à 8 Go de RAM** (L23) ; 22,8 Go de disque virtuel ; démarrage automatique géré par Docker (`restart: unless-stopped`, et donc aussi le service `ollama` à retirer, L22).

### Option B — ChromaDB natif

**Faisabilité :** **démontrée sur copie.** `chroma run` (paquet `chromadb` 1.5.1, déjà installé) lit les données du conteneur 1.4.1 sans migration. Tous les éléments, documents et métadonnées sont identiques, les vecteurs stockés aussi à l'octet. Seule la sérialisation JSON diffère (écart ≤ 2e−8, sans effet mesurable au-delà du 5e chiffre des distances). Aller-retour vers 1.4.1 validé. Le client et le serveur seraient alignés en 1.5.1 (M-L8 résolu).

**Procédure d'import**
1. Arrêter Atlas.
2. `backup` + `verify`.
3. Extraire l'archive dans un dossier stable de l'hôte (ex. `assistant-bureau/data/chromadb/`, déjà ignoré par Git).
4. `chroma run --path <dossier> --host 127.0.0.1 --port 8002`, sur un port temporaire.
5. Comparer à la production (fonctions de `verify`).
6. Basculer : arrêter le conteneur (point de non-retour pour la **disponibilité**, pas pour les données, puisque le conteneur n'est pas supprimé), lancer le natif sur 8001.
7. Démarrer Atlas et contrôler `/api/health` et les volumes.
8. Garder le conteneur arrêté quelques semaines comme filet de sécurité, puis le supprimer sur décision.

**Gain mémoire réel :** ~120 Mo pour le processus natif, contre 4 à 8 Go pour la VM. **Ce gain n'existe que si Docker disparaît entièrement.**

**SearXNG, honnêtement :**
- SearXNG n'a pas de distribution Windows native officielle.
- S'il reste conteneurisé, **Docker, WSL, la virtualisation BIOS et la VM restent** : le gain RAM est alors quasi nul (la VM est dimensionnée par Docker, pas par ChromaDB), et l'option B ne supprime aucune dépendance.
- Alternatives :
  - (i) abandonner SearXNG au profit du repli `ddgs`, **déjà en place** et fonctionnel (sprint A), au prix d'une dépendance à un service web tiers et d'une qualité non mesurée ici ;
  - (ii) SearXNG dans WSL sans Docker (non évalué) ;
  - (iii) garder Docker pour SearXNG seul avec une VM plafonnée (`.wslconfig`).

**Impact sur `install_checklist.md` et la diffusion :**
- Avec (i) : **trois dépendances de moins** (Docker Desktop, WSL2, virtualisation BIOS), soit l'étape la plus fragile rencontrée au sprint A. Le profil léger visé (postes à 16 Go) devient atteignable.
- Avec (iii) : aucune simplification.

**Démarrage :**
- Par Atlas (sous-processus lancé et arrêté dans `lifespan`) : le plus simple pour la diffusion, mais le code de `main.py` doit évoluer.
- Tâche planifiée à l'ouverture de session : aucun code, mais une étape d'installation de plus.
- Service Windows (via NSSM ou équivalent) : un outil tiers en plus.

À décider ; la voie « lancé par Atlas » est la plus cohérente avec « Atlas est personnel » et l'installabilité.

**Coût réel :** moyen, 0,5 à 1 jour : bascule, mécanisme de démarrage, mise à jour de la checklist et de `doctor.py`, décision SearXNG.
**Risque de perte :** faible (le conteneur reste arrêté, la sauvegarde est prouvée).
**Réversibilité :** élevée (aller-retour 1.5.1 → 1.4.1 démontré).

### Tableau de synthèse

| Critère | A1 : Docker + dossier hôte | A2 : Docker + volume nommé | B : natif (+ décision SearXNG) |
|---|---|---|---|
| Données visibles et sauvegardables depuis Windows | Oui | Non (`docker cp`) | Oui |
| Performance d'écriture mesurée | **12,5 s** | 1,95 s | 1,93 s |
| Fidélité mesurée | Identique | Identique | Vecteurs identiques à l'octet (JSON ±2e−8) |
| Coût de migration | Faible | Faible | Moyen |
| Point de non-retour | Recréation du conteneur | Recréation du conteneur | Aucun sur les données (conteneur conservé arrêté) |
| Réversibilité | Élevée | Élevée | Élevée (aller-retour prouvé) |
| RAM | VM 4–8 Go | VM 4–8 Go | ~0,1 Go **si** Docker disparaît ; sinon inchangée |
| Dépendances pour la diffusion | Docker, WSL, BIOS | Docker, WSL, BIOS | Aucune de celles-ci **si** SearXNG est abandonné ou déplacé |
| Profil léger (16 Go) | Défavorable | Défavorable | Favorable, sous condition |

### Recommandation

**Ce qui relève de la mesure :**
- Le montage d'un dossier Windows (A1, la correction la plus « évidente ») est 6,4 fois plus lent en écriture.
- Le volume nommé et le natif ont des performances équivalentes.
- Les données passent sans perte ni migration de 1.4.1 à 1.5.1, et inversement.
- ChromaDB natif occupe ~0,1 Go de RAM, contre 4 à 8 Go pour la VM Docker.
- ChromaDB ne justifie pas à lui seul la VM : SearXNG la justifie aussi.

**Ce qui relève de l'avis :**
1. **Tout de suite (sprint M-bis) : A2, volume nommé + image épinglée par digest.** C'est la correction de L21 la plus courte, la moins risquée et la plus fidèle (même binaire 1.4.1). Elle ne change ni le code, ni la checklist, ni le mode de démarrage. Pas A1, à cause des performances mesurées.
2. **Ensuite, avec la décision SearXNG : B (natif).** Seulement si Alexis accepte de se passer de SearXNG (repli `ddgs`) ou trouve une alternative hors Docker. B n'a d'intérêt que s'il fait disparaître Docker ; sinon il ajoute une pièce mobile sans rien retirer. La compatibilité mesurée rend ce second passage peu risqué.
3. Si la priorité est la diffusion à court terme (postes à 16 Go), on peut viser **B directement**, avec abandon de SearXNG : c'est plus de travail tout de suite, mais la migration de la mémoire se fait en une seule fois.

La décision appartient au superviseur et à Alexis. Aucune de ces options n'a été appliquée.

---

*Rapport Sprint M — CHAT6 (Claude Opus 5, Claude Code Windows), 17/09/2026.*
*Rapports JSON de vérification et manifeste dans le dossier de sauvegarde (ils contiennent des extraits de la mémoire : données personnelles, ne pas diffuser).*
