# BRIEF SPRINT M — Sécurisation de la mémoire long terme

**Destinataire :** CHAT6 (Claude Opus, Claude Code Windows)
**Émetteur :** Superviseur technique Atlas
**Date d'émission :** 17 septembre 2026
**Durée estimée :** ½ à 1 journée
**Statut :** **Priorité absolue.** Précède B-minimal et C.
**Référence :** rapport Sprint A, risque L21

---

## 1. Pourquoi ce sprint existe seul

Le Sprint A a établi que **toute la mémoire long terme d'Atlas ne vit que dans la couche d'écriture du conteneur Docker**.

L'image `chromadb/chroma` persiste dans `/data` (`persist_path: "/data"`), alors que `docker-compose.yml` monte le volume sur `/chroma/chroma`, qui reste vide. Côté Windows, `data/chromadb` est vide.

Conséquence : un `docker compose down`, une mise à jour d'image, une suppression ou une recréation du conteneur `assistant_chromadb` **détruit définitivement** six collections accumulées depuis février 2026 — conversations, documents, contexte applicatif, habitudes, erreurs.

**C'est le seul actif irremplaçable du projet.** Le code se réécrit, les modèles se retéléchargent, les tests se rejouent. Six mois de mémoire et d'apprentissage par les erreurs, non.

Ce sprint est isolé parce qu'on ne mélange pas une opération de sauvegarde avec autre chose.

---

## 2. Règles cardinales

> **Aucune opération destructive ou potentiellement destructive sur `assistant_chromadb`.**

Interdits sans exception dans ce sprint :

- `docker compose down`, `docker rm`, `docker compose up --force-recreate`
- Toute mise à jour ou changement de tag de l'image `chromadb/chroma`
- Toute modification de `docker-compose.yml`
- Toute migration de données
- Tout test qui écrit dans la base réelle (rappel Sprint A : `test_chroma_integration` crée et supprime une collection dans la vraie base)

> **Aucune migration n'est exécutée dans ce sprint.**

Ce sprint **sécurise** et **analyse**. La décision d'architecture appartient au superviseur et à Alexis, sur la base du rapport produit ici. La migration fera l'objet d'un sprint ultérieur, une fois la décision prise.

Modifications de code autorisées : **aucune**, hors création de scripts de sauvegarde et de restauration, qui sont de l'outillage.

---

## 3. Tâches

### M1 — Sauvegarde vérifiée, avec restauration prouvée

**La tâche la plus importante du sprint. À faire en premier, avant toute exploration.**

Une copie dont on n'a pas testé la restauration n'est pas une sauvegarde. Le `docker cp` du Sprint A est une copie non vérifiée.

1. Produire une **sauvegarde datée et horodatée** du contenu réel de `/data` dans le conteneur, hors dépôt Git, sur un emplacement pérenne du disque.
2. Calculer et consigner les **empreintes** (SHA-256) de la sauvegarde, ainsi que sa taille et son arborescence.
3. **Prouver la restauration** : démarrer un **conteneur jetable** — nom distinct, port distinct, jamais `assistant_chromadb` — y restaurer la sauvegarde, et vérifier que les six collections sont présentes avec le bon nombre de documents.
4. Comparer document par document sur un échantillon représentatif : nombre de collections, nombre d'éléments par collection, dimension des embeddings, et un échantillon de contenus.
5. Détruire le conteneur jetable. **Ne pas toucher à l'original.**

Livrable : `scripts/backup_memory.py` (ou équivalent documenté), la sauvegarde elle-même hors dépôt, et le compte rendu de la restauration vérifiée.

**Tant que M1 n'est pas terminé et prouvé, aucune autre tâche ne démarre.**

### M2 — Inventaire de ce qui est en jeu

Établir précisément ce que contient la mémoire aujourd'hui, pour savoir ce qui doit survivre à une migration :

- Les six collections : nom, nombre de documents, dimension des embeddings, modèle d'embedding utilisé, date du plus ancien et du plus récent élément
- Volume total sur disque
- Format de persistance effectif de l'image (SQLite, index, structure des répertoires)
- Version exacte de ChromaDB dans le conteneur, et version du client Python utilisée par Atlas

### M3 — Recherche d'autres états non persistés

L21 a été trouvé par hasard. La question à poser : **y en a-t-il d'autres ?**

Vérifier, pour chaque service et chaque composant, si un état vit uniquement dans un conteneur ou dans un emplacement non sauvegardé :

- `atlas_searxng` : configuration, secret, éventuel cache
- Le conteneur `assistant_ollama` arrêté au Sprint A : contient-il des modèles qui n'existent pas dans l'Ollama natif ?
- Modèles Ollama natifs : emplacement, volume, sauvegardés ou non
- Modèles Whisper, EasyOCR, OpenWakeWord, Piper : emplacements de cache, re-téléchargeables ou non
- `habits.db`, fichiers JSONL, `settings.json` : sur l'hôte, confirmés, et couverts ou non par une sauvegarde
- Tout autre volume Docker nommé ou anonyme rattaché au projet

Livrable : un tableau de **tout ce qui serait perdu** en cas de remise à zéro de la machine, avec la mention « re-téléchargeable » ou « irremplaçable ».

### M4 — Analyse comparée : Docker corrigé contre ChromaDB natif

Analyse d'aide à la décision. **Aucune mise en œuvre.**

**Option A — conserver Docker, corriger le montage du volume**

- Chemin exact à monter, modification précise de `docker-compose.yml`
- Procédure de migration : comment déplacer les données existantes vers le volume monté sans les perdre
- Risques de la migration, et point de non-retour éventuel
- Ce qui reste : dépendance à Docker Desktop, à WSL, et aux 8,3 Go de la VM (risque L23)

**Option B — ChromaDB en natif, suppression de la dépendance Docker**

- Faisabilité : version native équivalente à celle du conteneur, compatibilité du format de persistance
- Procédure d'import des données existantes, et vérification d'intégrité après import
- Gain mémoire réel attendu (WSL disparaît-il entièrement, ou Docker reste-t-il requis par SearXNG ?)
- Conséquence sur SearXNG : si SearXNG reste conteneurisé, Docker ne disparaît pas — l'évaluer honnêtement
- Impact sur `docs/install_checklist.md` et sur la diffusion : une dépendance de moins ou non ?
- Comportement au démarrage : service, tâche planifiée, ou lancement par Atlas ?

Pour chaque option : **coût de migration réel**, risque de perte, réversibilité, et impact sur le profil léger visé pour la diffusion.

Clore par une **recommandation argumentée**, en séparant ce qui relève de la mesure de ce qui relève de l'avis.

### M5 — Rapport

Conforme à `rapport.md/RAPPORT_RULES.md`, 9 sections. À déposer dans `docs/rapports/RAPPORT_SPRINT_M.md`.

Doit répondre sans ambiguïté à :

1. La sauvegarde est-elle **prouvée restaurable** ? Où se trouve-t-elle, quelles sont ses empreintes ?
2. Existe-t-il **d'autres états non persistés** dans le projet ?
3. Docker corrigé ou natif : quelle recommandation, et sur quelles mesures ?

---

## 4. Livrables

- `scripts/backup_memory.py` — sauvegarde reproductible et documentée
- Sauvegarde vérifiée, hors dépôt, emplacement et empreintes consignés dans le rapport
- `docs/rapports/RAPPORT_SPRINT_M.md`
- Annexe : inventaire des collections (M2)
- Annexe : tableau des états non persistés (M3)
- Annexe : analyse comparée avec recommandation (M4)

## 5. Critères de validation

- [ ] Sauvegarde produite, horodatée, empreintes consignées
- [ ] **Restauration effectivement prouvée** dans un conteneur jetable, avec comparaison des six collections
- [ ] Conteneur jetable détruit, `assistant_chromadb` intact et fonctionnel
- [ ] Inventaire des collections livré
- [ ] Recherche d'autres états non persistés livrée, avec le tableau perdu/re-téléchargeable
- [ ] Analyse comparée livrée avec recommandation argumentée
- [ ] **Aucune migration exécutée**
- [ ] **Aucune modification de `docker-compose.yml`**
- [ ] Aucun fichier de code existant modifié

## 6. Rappels de méthode

- **En cas de doute sur une commande touchant `assistant_chromadb`, ne pas l'exécuter et poser la question.** Une opération destructive irréversible ne se rattrape pas par un rapport honnête.
- Honnêteté intellectuelle non négociable : aucune vérification revendiquée sans preuve reproductible.
- Pas de scope caché. Toute action hors périmètre est signalée.
