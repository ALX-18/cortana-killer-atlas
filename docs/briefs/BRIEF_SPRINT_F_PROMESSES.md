# BRIEF SPRINT F — Tenir ce qu'on promet

**Destinataire :** CHAT6 (Claude Opus, Claude Code Windows)
**Émetteur :** Superviseur technique Atlas
**Date d'émission :** 27 septembre 2026
**Durée estimée :** 1 à 2 journées, plus une courte séance au micro avec Alexis
**Statut :** Suite directe du sprint E. Décidé par Alexis.
**Références :** rapport E (D-E1, D-E2, annexe A), rapport B1 (annexe A), rapport B1-ter (anomalie A, B1T-R4)

---

## 1. Le constat qui fonde ce sprint

R04, au micro : « ferme la fenêtre Steam » a fermé Steam **instantanément, sans confirmation ni notification**.

La cause réelle dépasse cette fenêtre. **Le validateur pose `confirmation_required = True` ; le moteur ne le lit pas.** `execute_tool` applique ses propres règles, codées en dur pour trois outils seulement : `kill_process`, `run_powershell`, `system_config`. **Toute autre action marquée sensible par le validateur s'exécute sans rien demander.** La règle 3 et l'invariant 4 — « rien d'irréversible sans confirmation » — ne sont tenus que pour trois outils.

Et l'annexe A du rapport B1 affirmait « Atténué : confirmation obligatoire sur close ». **C'était faux**, et le superviseur l'a repris sans le vérifier.

### Ce n'est pas un défaut isolé, c'est la cinquième occurrence d'un même motif

| Promesse déclarée | Réalité découverte | Sprint |
|---|---|---|
| Confirmation en contexte planifié | Échouait en silence | B1-ter (anomalie A) |
| `confirm_before_run` dans les workflows | Appliqué par aucun code | B1-ter (B1T-R4) |
| `/api/health` : voix en marche | La voix était morte | A (C04) |
| « C'est fait » prononcé par Atlas | Rien n'avait été fait | E (E5) |
| Le validateur exige une confirmation | Le moteur l'ignore | E (D-E1) |

**À chaque fois, une couche déclare une garantie qu'une autre couche n'applique pas.** Chaque couche, testée isolément, est correcte ; c'est la **jonction** qui est rompue. C'est aussi la raison pour laquelle l'apprentissage par les erreurs affichait 98 % de couverture sans fonctionner (sprint D) : on vérifiait les fonctions, jamais la chaîne.

La correction ponctuelle ne suffit plus. Ce sprint en contient deux, plus un audit qui cherche la suivante **avant** qu'on la découvre par hasard.

---

## 2. Trois parties, dans cet ordre

1. **F1 — Audit des promesses** : inventaire de toutes les garanties déclarées, vérifiées de bout en bout. **D'abord**, parce qu'il dira si le problème de confirmation est unique ou s'il a des frères.
2. **F2 — Le moteur honore la confirmation**, avec son affichage à l'écran.
3. **F3 — La conversation continue devient délibérée** (D-E2).

**Règle anti-dérive :** F1 **inventorie**. Seules les promesses rompues relevant de la confirmation sont **corrigées** dans ce sprint. Les autres sont listées et priorisées pour un sprint ultérieur — même méthode qu'à l'annexe A du sprint B1, qui a donné B1-bis et B1-ter.

---

## 3. Périmètre

**Autorisé :** `core/intent_engine.py` (dont `execute_tool`, `execute_confirmed`), `core/validator.py`, `core/voice_engine.py`, `desktop/atlas_desktop.py` pour l'affichage des confirmations, `api/routes.py` pour exposer les confirmations en attente, `tools/systray.py`, `tests/`, et `docs/rapports/RAPPORT_SPRINT_B1.md` **pour y ajouter un erratum uniquement**.

**Interdit :** le grounding et l'apprentissage par les erreurs, les modes et la pré-autorisation (sprint dédié), la confirmation par la voix (voir F3), l'heure inventée (L4), la latence.

**Invariant 3 absolu** : aucun appel LLM dans un chemin de validation ou de confirmation.

**Méthode inchangée : le test rouge d'abord**, sortie brute consignée.

**Exigence propre à ce sprint :** les tests doivent être **de bout en bout** — d'une demande jusqu'à son effet observable. Un test qui vérifie que le validateur pose un drapeau ne prouve rien si personne ne vérifie que le moteur le respecte. C'est précisément ce trou que ce sprint comble.

---

## 4. Tâches

### F1 — Audit des promesses

Recenser **toutes les garanties de sécurité ou de comportement déclarées** dans le projet, et vérifier pour chacune qu'elle est tenue **de la demande jusqu'à l'effet**.

Une « promesse », c'est tout ce qui affirme un comportement : un drapeau (`confirmation_required`), un champ de configuration, une clé de workflow, un invariant de la roadmap, un message affiché ou prononcé, une valeur exposée par l'API, un commentaire de garde-fou.

Sources à couvrir au minimum :

- les **six invariants** de la roadmap, en particulier l'invariant 4 et la **confirmation à trois niveaux** avec la **protection des processus** (intouchable / demande / libre) ;
- tous les drapeaux et décisions posés par `core/validator.py` ;
- les règles codées en dur dans `execute_tool` et `execute_confirmed` ;
- les garanties des automatisations établies en B1-ter (validation à la création, au chargement, à l'exécution) ;
- les indicateurs exposés par `/api/health` et `/api/voice/state` ;
- les messages qu'Atlas prononce ou affiche pour annoncer un résultat ;
- la déduplication à l'écriture en mémoire (sprint D) ;
- les garde-fous de `scripts/backup_memory.py` et `scripts/memory_cleanup.py`.

**Livrable :** un tableau.

| Promesse | Déclarée où | Appliquée où | Test de bout en bout ? | Statut |
|---|---|---|---|---|

Statut : **tenue** (prouvée de bout en bout) · **partielle** · **non tenue** · **non vérifiable** (et pourquoi).

Pour chaque promesse non tenue : conséquence réelle pour l'utilisateur, et sévérité.

**Ne corriger ici que ce qui relève de la confirmation (F2).** Le reste est inventorié.

### F2 — Le moteur honore la confirmation

**La cause racine est une dualité :** deux endroits décident si une action exige une confirmation — le drapeau du validateur, et la liste codée en dur dans le moteur. C'est cette dualité qui a laissé passer `window_close`.

1. **Une seule source de vérité** pour « cette action exige-t-elle une confirmation ? ». Proposer laquelle, la justifier, et supprimer l'autre — ou faire de l'une la dérivée stricte de l'autre. Deux listes qui divergent, c'est le défaut lui-même.
2. **Le moteur respecte cette décision pour toutes les actions**, pas seulement les trois actuelles.
3. **La confirmation en attente doit apparaître dans la fenêtre Atlas**, avec l'action, sa cible, et deux boutons explicites. L'annexe A du rapport E l'a relevé : aujourd'hui une confirmation en attente ne s'affiche nulle part. **C'est un prérequis, pas un confort** : si le moteur exige une confirmation que l'interface ne montre pas, chaque « ferme cette fenêtre » restera bloqué sans que l'utilisateur le sache — on recréerait l'anomalie A sur le chemin interactif.
4. **Expiration courte et refus par défaut.** Une confirmation sans réponse ne doit jamais rester pendante indéfiniment, ni finir par s'exécuter. Définir le délai, le justifier.
5. **Le chemin vocal du sprint E doit enfin se déclencher en réel** : une action à confirmation demandée à la voix produit la réponse parlée « Cette action nécessite une confirmation à l'écran » et la confirmation s'affiche.
6. **Cohérence avec les automatisations (B1-ter)** : les actions à confirmation restent exclues des automatisations. Vérifier que la nouvelle source de vérité ne rouvre rien.

### F3 — La conversation continue, délibérée

Aujourd'hui, la file audio n'est jamais vidée : tout ce que le micro capte pendant qu'Atlas enregistre, réfléchit et **parle** s'accumule, puis est analysé au retour au repos. 17 réveils sur 29 sont partis moins de 0,2 s après la fin d'un cycle. Alexis apprécie l'effet — enchaîner sans redire « Hey Atlas ». Il faut le garder, mais le **construire**.

1. **Vider la file audio** à la fin de chaque cycle, **après** qu'Atlas a fini de parler, pour qu'il ne puisse jamais réagir à sa propre voix.
2. **Ouvrir une fenêtre de suite bornée** : quelques secondes pendant lesquelles Atlas écoute sans mot d'éveil. Proposer la durée, la justifier. Passé ce délai, retour au mot d'éveil.
3. **La fenêtre est visible** : l'indicateur d'écoute ajouté au sprint E doit la montrer, distinctement du repos.
4. **La fenêtre de suite n'accepte PAS de confirmation.** C'est une interdiction explicite. La confirmation par la voix est un sujet de conception à part (annexe A du rapport E) : liste blanche des formulations, score de confiance minimal, refus par défaut, réservée aux actions réversibles. **Si un « oui » capté dans la fenêtre de suite pouvait valider une action, on aurait construit la confirmation vocale sans aucune de ses protections.** Un test doit le prouver.
5. Cette fenêtre est aussi la brique que la future confirmation vocale réutilisera : la concevoir proprement.

### F4 — Erratum dans le rapport B1

Ajouter **en fin de `RAPPORT_SPRINT_B1.md`** un erratum daté, sans réécrire le texte d'origine :

> Erratum du 27/09/2026 — L'annexe A indiquait pour `window_close` : « Atténué : confirmation obligatoire sur close ». C'était inexact : le moteur ignorait le drapeau de confirmation du validateur. Découvert au sprint E (R04, D-E1), corrigé au sprint F.

Un rapport qui dit faux doit être corrigé par un ajout traçable, pas par une réécriture silencieuse.

### F5 — Validation, et rapport

1. Tests F1 à F3 verts, après avoir été vus rouges, **de bout en bout**.
2. `python -m pytest tests/ -q` → **code 0**, 654 tests plus les nouveaux, écarts expliqués.
3. **Séance courte au micro avec Alexis :**

| ID | Scénario | Attendu |
|---|---|---|
| F-R1 | « Hey Atlas, ferme la fenêtre Steam » | Atlas annonce qu'une confirmation est nécessaire ; la confirmation s'affiche ; **Steam reste ouvert** |
| F-R2 | Confirmer à l'écran | Steam se ferme |
| F-R3 | Refuser à l'écran, puis laisser expirer une autre demande | Rien ne se ferme dans les deux cas |
| F-R4 | Après une réponse d'Atlas, enchaîner une question sans « Hey Atlas » | Pris en compte dans la fenêtre de suite |
| F-R5 | Attendre la fin de la fenêtre, parler sans « Hey Atlas » | Ignoré |
| F-R6 | Dire « oui » pendant la fenêtre de suite alors qu'une confirmation est affichée | **La confirmation n'est pas validée** |

4. Rapport conforme à `docs/RAPPORT_RULES.md`, 9 sections, dans `docs/rapports/RAPPORT_SPRINT_F.md`, avec le **tableau de l'audit** en annexe.

---

## 5. Critères de validation

- [ ] Audit des promesses livré : tableau complet, statut de chaque promesse, sévérité des promesses non tenues
- [ ] **Une seule source de vérité** pour la confirmation ; la dualité supprimée
- [ ] Le moteur honore la confirmation **pour toutes les actions concernées**
- [ ] Confirmation en attente **affichée dans la fenêtre Atlas**, avec expiration et refus par défaut
- [ ] Chemin vocal de confirmation déclenché en réel
- [ ] Aucune réouverture des automatisations (B1-ter)
- [ ] File audio vidée après la parole ; Atlas ne réagit pas à sa propre voix
- [ ] Fenêtre de suite bornée, visible, justifiée
- [ ] **La fenêtre de suite ne valide aucune confirmation** — prouvé par test
- [ ] Erratum ajouté au rapport B1, sans réécriture
- [ ] Tests **de bout en bout**, rouges d'abord
- [ ] `python -m pytest tests/ -q` → code 0
- [ ] **F-R1 à F-R6 exécutés avec Alexis au micro**

## 6. Rappels de méthode

- **Tester la jonction, pas seulement les couches.** C'est la leçon commune des cinq promesses rompues.
- **Un échec silencieux est le pire comportement.** Une confirmation invisible en est un.
- Inventorier ce que l'audit trouve ; ne corriger que la confirmation. Le reste aura sa tranche.
- En cas de doute sur une commande touchant Docker ou la mémoire : ne pas l'exécuter, demander.
- Un garde-fou se teste avec des commandes simulées. Règle permanente depuis I-1.

---

## 7. Note pour plus tard, hors périmètre

**Le mot d'éveil n'est reconnu que prononcé à l'anglaise** (D-E4 : 0,0008 avec une voix française). Décision d'Alexis : à trancher **avant le programme de test externe**. Consigné comme prérequis dans la roadmap.
