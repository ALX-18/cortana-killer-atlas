# BRIEF SPRINT B1-TER — La validation comme invariant du stockage

**Destinataire :** CHAT6 (Claude Opus, Claude Code Windows)
**Émetteur :** Superviseur technique Atlas
**Date d'émission :** 19 septembre 2026
**Durée estimée :** ½ à 1 journée
**Statut :** **Dernier sprint de la famille sécurité.** La chaîne vocale suit immédiatement.
**Références :** rapport B1-bis, §4.1 et annexe B

---

## 1. Pourquoi ce sprint, et pourquoi c'est le dernier

Ton annexe B.2 en donne la formulation juste, et elle sert de titre à ce brief :

> **La validation doit être pensée comme un invariant du stockage, pas comme une étape du parcours de création.**

Tous les défauts corrigés jusqu'ici étaient **ponctuels** : une action au mauvais endroit, une fois. Celui-ci **s'installe**. Une action absurde enregistrée une fois se rejoue indéfiniment, longtemps après que l'utilisateur a oublié l'avoir acceptée — et les déclencheurs l'amplifient, puisqu'ils se relancent à chaque franchissement de seuil.

À quoi s'ajoute la découverte structurelle de ton §4.1 : **le chemin planificateur / déclencheurs / workflows ne passe pas par le validateur.** Tout le durcissement de B1 et B1-bis protège la requête utilisateur et le plan LLM, pas l'automatisation.

Après ce sprint, la famille sécurité est close et on passe à la voix.

---

## 2. Deux anomalies actives, à traiter en priorité

Elles ne sont pas théoriques : elles sont vraies sur la machine d'Alexis aujourd'hui.

**A. Les actions planifiées à confirmation forcée échouent en silence.** En contexte planifié, personne ne confirme : l'action reste en attente et **ne s'exécute jamais, sans le moindre avertissement**. Le workflow `mode_gaming` contient `kill_process` — il ne fait donc probablement rien quand il se déclenche, et personne n'en a jamais été informé.

C'est un défaut de correction autant que de sécurité : l'utilisateur croit qu'une automatisation fonctionne alors qu'elle ne fait rien.

**B. Le workflow `nettoyage_systeme` vide la corbeille à chaque exécution** — suppression définitive, récurrente, sans confirmation possible en contexte planifié.

---

## 3. Périmètre

**Autorisé :** `core/validator.py`, `main.py` (chemin `_execute_action`), `core/workflow_engine.py`, `core/scheduler.py`, `core/trigger_engine.py`, `tools/app_launcher.py` pour BT6, `tests/`.

**Interdit :** chaîne vocale (L1, L2, L3), L4 heure, L6 triple lancement, L9 OCR bloquant, C04 endpoint trompeur. Toute refonte du planificateur.

**Invariant 3 absolu** : aucun appel LLM dans un chemin de validation.

**Méthode imposée, inchangée : le test rouge d'abord**, sortie brute consignée, aucun effet réel.

**Règle particulière à ce sprint : ne jamais supprimer ni modifier un élément enregistré par l'utilisateur.** Les workflows, tâches planifiées et déclencheurs existants appartiennent à Alexis. CHAT6 constate, présente les options, n'agit pas.

---

## 4. Tâches

### BT1 — L'échec silencieux devient visible

Avant toute validation : une automatisation qui ne s'exécute pas doit le **dire**.

Quand une action planifiée, déclenchée ou issue d'un workflow est bloquée — confirmation impossible, validation refusée, quelle qu'en soit la raison — elle doit être **journalisée explicitement** et remontée à l'utilisateur par le canal disponible (notification, systray, endpoint d'état).

Le silence est le pire des comportements : il laisse croire que tout fonctionne.

### BT2 — Liste blanche des actions planifiables

Toute action n'a pas sa place dans une automatisation. Établir la liste de celles qui peuvent l'être, et refuser le reste à l'enregistrement.

À exclure, selon ton analyse :

- **Les actions interactives** (`window_type`, `window_hotkey`, `window_click`, `ui_click_element`) : le premier plan à l'heure du déclenchement est inconnu, donc la cible l'est aussi.
- **Les actions à confirmation forcée** : la confirmation ne peut pas avoir lieu.
- **Les actions d'automatisation elles-mêmes** : une tâche qui crée une tâche.

Proposer la liste des actions autorisées, la justifier, l'appliquer.

### BT3 — Contrôle des paramètres par les fonctions communes

Réutiliser les **mêmes fonctions pures** que le validateur (`check_url`, `check_window_title`, contrôles de bornes…), via une table outil → contrôle.

Ton rapport identifie précisément la pièce manquante : « le validateur associe des *intentions*, pas des *appels d'outil* ». C'est cette table qu'il faut écrire, et elle doit avoir **une seule définition par règle** — pas de duplication entre validateur et stockage.

### BT4 — Récursion et cycles

`workflow_run` à l'intérieur d'un workflow impose une détection de cycles et une profondeur maximale. Définir la limite, la justifier, la tester.

### BT5 — Validation aux trois moments

C'est le cœur de « invariant du stockage » : **à la création, au chargement, et à l'exécution.**

La raison est concrète : `data/schedules.json`, `data/triggers.json` et les fichiers de workflows sont des fichiers texte, modifiables à la main. Une validation qui n'aurait lieu qu'à la création serait contournée par une simple édition — volontaire ou accidentelle.

Un élément invalide trouvé au chargement doit être **désactivé et signalé**, jamais chargé en silence, et jamais supprimé.

### BT6 — Les actions encore non protégées

Traiter les actions que ton annexe A recalculée classe encore « pas du tout protégées », dont `launch_app` avec le paramètre `path`.

Ta recommandation en annexe B.1 est retenue : **option 1**, liste blanche, dans le validateur et dans l'outil. Tu notes que personne n'utilise ce paramètre — sa suppression au profit de `name` seul est donc à évaluer sérieusement plutôt qu'à écarter.

### BT7 — Sort des huit éléments enregistrés — constat, pas action

Cinq workflows, deux tâches planifiées, un déclencheur. Selon ton analyse, deux seraient refusés : `mode_gaming` (`kill_process`) et `nettoyage_systeme` (`maintenance_empty_bin`).

Pour chacun des huit : ce qu'il fait, s'il passerait les nouvelles règles, et sinon pourquoi. Pour les deux refusés, proposer des options — exception explicite, réécriture, suppression — **sans en appliquer aucune**. La décision revient à Alexis.

Signaler également tout élément qui, aujourd'hui, **ne fonctionne déjà pas** en raison de l'anomalie A. Il pourrait y en avoir d'autres que `mode_gaming`.

### BT8 — Vérification et rapport

1. Tests BT1 à BT6 verts, après avoir été vus rouges.
2. `python -m pytest tests/ -q` → **code 0**, 543 tests plus les nouveaux, écarts expliqués.
3. **Rejeu réel** : enregistrer une automatisation contenant une action interdite et vérifier qu'elle est **refusée avec un message clair** ; puis modifier à la main un fichier enregistré pour y introduire une action invalide, et vérifier qu'elle est **détectée au chargement et signalée**.
4. **Annexe A recalculée** une dernière fois : combien d'actions protégées, partiellement, pas du tout.
5. Rapport conforme à `docs/RAPPORT_RULES.md`, 9 sections, dans `docs/rapports/RAPPORT_SPRINT_B1_TER.md`.

Le point 3, second volet — l'édition manuelle du fichier — est le critère décisif. C'est lui qui prouve que la validation est bien un invariant du stockage et non une formalité d'enregistrement.

---

## 5. Critères de validation

- [ ] Tests rouges d'abord, sorties brutes, aucun effet réel
- [ ] Toute automatisation bloquée est journalisée **et signalée** à l'utilisateur
- [ ] Liste blanche des actions planifiables établie, justifiée, appliquée
- [ ] Table outil → contrôle écrite, une seule définition par règle
- [ ] Cycles et profondeur maximale traités pour `workflow_run`
- [ ] Validation effective **à la création, au chargement et à l'exécution**
- [ ] Élément invalide au chargement : désactivé et signalé, jamais supprimé
- [ ] `launch_app(path)` traité selon l'option 1
- [ ] Les 8 éléments enregistrés analysés ; **aucun modifié ni supprimé**
- [ ] `python -m pytest tests/ -q` → code 0
- [ ] **Rejeu : action interdite refusée à l'enregistrement, et fichier édité à la main détecté au chargement**
- [ ] Annexe A recalculée
- [ ] Aucun appel LLM dans un chemin de validation

## 6. Rappels de méthode

- Le test rouge d'abord, toujours.
- **Ne jamais toucher aux éléments enregistrés par l'utilisateur.** Constater, proposer, laisser décider.
- **Le silence est le pire comportement.** Une automatisation qui ne s'exécute pas doit le dire.
- En cas de doute sur une commande touchant Docker ou la mémoire : ne pas l'exécuter, demander.
- Après ce sprint : la voix.
