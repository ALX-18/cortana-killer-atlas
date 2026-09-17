# BRIEF SPRINT M-BIS — Migration de la mémoire vers un volume nommé

**Destinataire :** CHAT6 (Claude Opus, Claude Code Windows)
**Émetteur :** Superviseur technique Atlas
**Date d'émission :** 17 septembre 2026
**Durée estimée :** ½ journée
**Statut :** Clôt le risque L21. Précède B-minimal et C.
**Références :** rapports Sprint A (L21) et Sprint M (annexe C, P1.3)

---

## 1. Décision d'architecture actée

Sur la base de l'annexe C du rapport M, le superviseur retient :

> **Option A, variante « volume Docker nommé »**, avec **épinglage de l'image par digest**.

Justification, mesurée : le volume nommé est **6,4 fois plus rapide** en écriture que le montage d'un dossier Windows (1,95 s contre 12,48 s pour 500 écritures) et se comporte à l'identique de la production. Surtout, `docker compose down` **ne supprime pas** un volume nommé — ce qui clôt L21.

**Réserve assumée et documentée :** un volume nommé réside dans le VHDX de WSL. Il protège du scénario probable (recréation ou suppression du conteneur) mais **pas** du scénario catastrophique (réinitialisation de Docker Desktop, corruption WSL, panne disque). C'est le rôle de la sauvegarde externe, hors périmètre de ce sprint.

Le passage à ChromaDB natif reste une option de moyen terme, à trancher conjointement avec le sort de SearXNG. Hors périmètre ici.

---

## 2. Préalable bloquant

> **La sauvegarde de référence doit avoir été copiée sur un support externe par Alexis avant le démarrage de ce sprint.**

Source : `C:\Users\alexis\Atlas_backups\memoire\chromadb_20260917_030200\` (8,5 Mo).

CHAT6 **demande confirmation à Alexis** et ne commence pas sans. Si la copie n'est pas faite, le sprint s'arrête à cette ligne.

---

## 3. Principe directeur : supprimer le point de non-retour

La procédure proposée au rapport M (P1.3) recrée le conteneur en cours de route, ce qui détruit la couche d'écriture actuelle — un point de non-retour au milieu de l'opération.

**On l'évite.** Le conteneur de production actuel n'est ni supprimé ni recréé : il est seulement **arrêté**, et conservé intact jusqu'à ce que la nouvelle configuration ait fait ses preuves à l'usage.

Séquence retenue :

1. Le nouveau conteneur est créé **à côté**, sur un **port distinct**, avec le volume nommé.
2. Il est vérifié intégralement pendant que l'ancien vit encore.
3. Le basculement n'a lieu qu'après vérification conforme.
4. L'ancien conteneur reste **arrêté mais présent** pendant une période de confiance.

À tout moment avant l'étape 3, l'abandon consiste à supprimer le nouveau conteneur et à ne rien changer.

---

## 4. Règles

**Autorisé dans ce sprint, contrairement aux précédents :**

- Modifier `docker-compose.yml` (c'est l'objet du sprint)
- Créer un volume Docker nommé
- Créer, arrêter et supprimer des conteneurs **autres** que `assistant_chromadb`
- Arrêter `assistant_chromadb`

**Interdit sans exception :**

- `docker rm assistant_chromadb` — l'ancien conteneur est conservé
- `docker compose down` tant que le basculement n'est pas vérifié
- Toute mise à jour de l'image `chromadb/chroma` : on réutilise le digest `sha256:7605e7b398f96dba833ed1b6272f815b9d33414dde45c68bd246e84447db8591`, avec `--pull never`
- Toute suppression de la sauvegarde de référence
- Tout nettoyage de la mémoire : artefacts de test, doublons, index orphelins. **Hors périmètre**, décision ultérieure
- Tout ré-encodage d'embeddings (M-L6) : investigation dédiée décidée, après ce sprint
- Lancer la suite de tests : `test_chroma_integration` écrit dans la base réelle

**Atlas doit être arrêté pendant toute l'opération.**

---

## 5. Tâches

### MB1 — Confirmation du préalable et sauvegarde fraîche

1. Confirmer auprès d'Alexis que la copie externe est faite.
2. Relancer `python scripts/backup_memory.py backup` pour disposer d'un état immédiatement antérieur à la migration, puis `verify`. Consigner l'emplacement et les empreintes.
3. Consigner l'état de départ : nombre d'éléments par collection, empreintes des 121 fichiers.

### MB2 — Création du volume nommé et copie des données

1. Créer le volume nommé (nom explicite, par exemple `atlas_chromadb_data`).
2. Y copier le contenu de `/data` de la production, par un conteneur temporaire ou depuis la sauvegarde vérifiée — préciser la méthode retenue et pourquoi.
3. Vérifier les empreintes **dans le volume** : les 121 fichiers doivent correspondre à la sauvegarde.

### MB3 — Nouveau conteneur en parallèle, sur port distinct

1. Créer le nouveau conteneur à partir du **digest** épinglé, avec `--pull never`, monté sur le volume nommé, publié sur un **port temporaire** (par exemple 8011) — jamais 8001 tant que l'ancien tourne.
2. L'ancien conteneur reste actif pendant cette étape.
3. Vérifier le nouveau avec la rigueur du sprint M : six collections, 535 éléments, identifiants, documents, métadonnées, échantillon d'embeddings, requêtes vectorielles aux mêmes distances que la production.

Adapter `backup_memory.py verify` pour accepter une URL cible, ou documenter la méthode équivalente employée.

**Si la vérification échoue : arrêt du sprint, suppression du nouveau conteneur, rapport. Rien d'autre n'est touché.**

### MB4 — Basculement

Seulement si MB3 est conforme.

1. Arrêter Atlas s'il tourne.
2. Arrêter `assistant_chromadb` — **sans le supprimer**.
3. Republier le nouveau conteneur sur le port **8001**, celui qu'attend Atlas.
4. Vérifier de nouveau : heartbeat, six collections, volumes corrects.
5. Mettre à jour `docker-compose.yml` : volume nommé, image épinglée par digest, service cohérent avec le conteneur en place.
6. Démarrer Atlas, vérifier `/api/health` et une lecture de mémoire réelle.

### MB5 — Épreuve de vérité

C'est le test que tout ceci vise à rendre possible.

1. `docker compose down` puis `docker compose up -d`.
2. Vérifier que **les six collections et les 535 éléments sont toujours là**.
3. Consigner le résultat. Si les données ont disparu, restaurer immédiatement depuis la sauvegarde et rapporter l'échec.

Ce test valide que L21 est clos. Sans lui, le sprint n'a rien prouvé.

### MB6 — Sauvegarde sur la nouvelle architecture

1. Relancer `backup` + `verify` contre la nouvelle configuration.
2. Adapter `backup_memory.py` si nécessaire pour qu'il fonctionne avec le volume nommé.
3. Vérifier que la procédure de sauvegarde reste valide après migration — une sauvegarde qui ne marche plus après une migration est un risque réintroduit.

### MB7 — Rapport

Conforme à `rapport.md/RAPPORT_RULES.md`, 9 sections. Dans `docs/rapports/RAPPORT_SPRINT_M_BIS.md`.

Doit répondre à :

1. Les 535 éléments ont-ils survécu au `docker compose down` / `up` ?
2. La procédure de sauvegarde fonctionne-t-elle encore sur la nouvelle architecture ?
3. L'ancien conteneur est-il conservé, et dans quel état ?

Indiquer aussi la **date à partir de laquelle l'ancien conteneur pourra être supprimé** — proposition : une semaine d'usage normal sans incident, sur décision du superviseur.

---

## 6. Critères de validation

- [ ] Copie externe confirmée par Alexis avant démarrage
- [ ] Sauvegarde fraîche prise et vérifiée avant toute modification
- [ ] Volume nommé créé, empreintes des 121 fichiers conformes
- [ ] Nouveau conteneur vérifié sur port temporaire pendant que l'ancien vivait
- [ ] Basculement effectué, Atlas fonctionnel, `/api/health` conforme
- [ ] **`docker compose down` / `up` exécuté, 535 éléments intacts après**
- [ ] Sauvegarde et vérification fonctionnelles sur la nouvelle architecture
- [ ] `assistant_chromadb` **conservé, arrêté, non supprimé**
- [ ] Image épinglée par digest dans `docker-compose.yml`
- [ ] Aucun nettoyage de mémoire, aucun ré-encodage
- [ ] Aucun fichier de code existant modifié hors `docker-compose.yml` et `scripts/backup_memory.py`

## 7. Rappels de méthode

- **En cas de doute sur une commande, ne pas l'exécuter et poser la question.** La règle du sprint M reste en vigueur : une opération irréversible ne se rattrape pas par un rapport honnête.
- Le sprint peut s'arrêter à tout moment avant MB4 sans conséquence. Après MB4, l'ancien conteneur reste le filet.
- Honnêteté intellectuelle non négociable. Aucune vérification revendiquée sans preuve reproductible.
