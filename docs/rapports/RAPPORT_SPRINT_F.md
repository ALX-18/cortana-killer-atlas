# RAPPORT SPRINT F — Les promesses tenues
Date: 02/10/2026 (travaux et audit : 30/09/2026)
Agent: Claude Opus 5.5 (CHAT6, Claude Code Windows)

> Brief : `docs/briefs/BRIEF_SPRINT_F_PROMESSES.md`. Références : rapport E (R04, D-E1, D-E2, annexe A), rapport B1 (annexe A), rapport B1-ter.
> Branche **`sprint-f`**, issue de `main` @ `c2534a0`. 6 commits, **non poussés**.

---

## 1. Résumé exécutif

**Statut global : PARTIELLEMENT VALIDÉ.** Le code, les tests et l'audit sont terminés. **La séance réelle F-R1 à F-R6 n'a pas eu lieu.**

**Décision d'Alexis du 02/10/2026 :** la séance au micro est **reportée**, faute de temps ; une beta est visée pour la fin de la semaine. Le rapport est rendu en l'état, et la séance sera reprise plus tard. Conséquence à connaître avant la beta : **le dialogue de confirmation de la fenêtre Atlas n'a jamais été vu fonctionner en réel** (§7, risque élevé ; conditions de reprise en §9).

**État au moment du rapport :** Atlas arrêté. Docker Desktop était arrêté au dernier constat (30/09), donc ChromaDB et SearXNG aussi. Collection active inchangée : `atlas_memory_e5`. Aucune écriture en mémoire, aucune commande Docker pendant le sprint.

**La réponse à la question du brief : le problème de confirmation était-il unique ? Non.** L'audit F1 lui a trouvé **cinq frères**, dont un plus grave que lui.

| Défaut | Avant | Après | Preuve |
|---|---|---|---|
| **Dualité validateur / moteur** (cause de R04) | 5 outils marqués « à confirmer » exécutés directement : `window_close`, `schedule_add`, `trigger_add`, `workflow_run`, `workflow_create` | une seule table, `CONFIRMATION_POLICY` ; le moteur l'applique partout | 15 tests de bout en bout, 12 vus rouges |
| **Confirmations invisibles** | `message=None` → la fenêtre affichait « Action executee. » alors que **rien** n'avait été fait | dialogue : action, cible, motif, décompte, deux boutons ; les demandes vocales s'y affichent aussi | routes testées ; **dialogue non constaté en réel** (séance reportée) |
| **Processus « intouchable » tuable en un clic** | `csrss.exe` : confirmation proposée, un clic suffisait | refus sans confirmation possible (décision d'Alexis) | test vu rouge |
| **Aucune expiration** | une confirmation restait pendante indéfiniment ; un refus ne la retirait même pas | 60 s, puis refus par défaut ; un refus retire l'attente | tests vus rouges |
| **Une page web pouvait confirmer à la place d'Alexis** | CORS « * » : une page ouverte dans le navigateur demandait l'action, lisait l'identifiant, puis la validait | `/api/confirm` et `/api/confirmations` refusent toute origine étrangère (403) | test vu rouge : la fenêtre a été « fermée » par la page |
| **Suppressions définitives hors table** | vider la corbeille, supprimer une tâche d'Alexis : exécutées sans accord si elles parvenaient au moteur | dans la table, « toujours » | test vu rouge |

**La faille la plus grave n'était pas R04.** Pendant l'audit, j'ai vérifié qui peut appeler `/api/confirm`. L'API n'écoute que sur 127.0.0.1, mais `main.py` accepte toutes les origines. Conséquence : n'importe quelle page ouverte dans le navigateur d'Alexis, pendant qu'Atlas tourne, pouvait envoyer « exécute cette commande PowerShell » puis confirmer elle-même. Le test l'a prouvé sur le vrai routeur. C'est corrigé pour la confirmation. Le CORS « * » lui-même est dans `main.py`, hors périmètre : une page peut toujours déclencher les actions **sans** confirmation (lancer une application, taper du texte dans une fenêtre nommée). C'est la **P1** du prochain sprint (§9).

**F3 — la conversation continue est construite, plus subie.**
- La file audio est vidée **après** la parole. Preuve : le vrai modèle, rejoué sur le vrai « Hey Atlas » pendant qu'Atlas parle, donne **0 réveil** (1 avant).
- Une fenêtre de suite de **6 s** prend la question suivante, avec au plus **5 enchaînements** : une télévision allumée ne fait pas d'Atlas un micro ouvert.
- La fenêtre est **visible** : voyant turquoise, « suite ».
- Un « oui » dit dans cette fenêtre **ne valide jamais** une confirmation. Atlas répond qu'elle se donne à l'écran. Testé sur 5 formulations.

**F4 fait** : l'erratum est ajouté au rapport B1, le texte d'origine est intact.

**Tests** : **32 nouveaux**, de bout en bout, tous vus rouges sauf les témoins de non-régression (§5). Suite complète : **685 passés, 5 ignorés, code 0**.

**Hors F2, inventorié sans correction** (annexe A) :
- « retiens que… » échoue sur « Outil inconnu » ;
- la télémétrie du client ChromaDB est active ;
- la clé `confirm_before_run` des workflows n'est jamais lue ;
- l'apprentissage par les erreurs ne fonctionne pas (connu depuis D).

---

## 2. Objectifs vs réalisation

| Objectif (brief) | Résultat réel | Statut |
|---|---|---|
| **F1** — inventaire de toutes les promesses, vérifiées de bout en bout | 36 promesses, annexe A : 23 tenues (dont 5 corrigées par F), 8 partielles, 3 non tenues hors confirmation (inventoriées), 1 non vérifiable | PASS |
| F1 — conséquence et sévérité pour chaque promesse non tenue | Annexe A, colonne « Conséquence / sévérité » | PASS |
| F1 — ne corriger que la confirmation | Trois défauts de confirmation trouvés par l'audit ont été corrigés (suppressions, origine, refus non retiré). Rien d'autre n'a été touché | PASS |
| **F2.1** — une seule source de vérité, l'autre supprimée | `CONFIRMATION_POLICY` (validateur). `_DESTRUCTIVE_VERBS`, neuf `confirmation = True/False` épars et les listes codées en dur d'`execute_tool` sont **supprimés** | PASS |
| F2.2 — le moteur la respecte pour toutes les actions | `ExecutionEngine.execute` (drapeau dérivé de la table) et `execute_tool` (même table). Balayage de toutes les intentions : test `une_seule_source_de_verite` | PASS |
| F2.3 — confirmation affichée : action, cible, deux boutons | Dialogue desktop, alimenté par `/api/chat` et `/api/confirmations` (routes testées). **Le dialogue lui-même (Tk) n'a aucun test et n'a pas été vu en réel** : F-R1 reportée | PARTIEL |
| F2.4 — expiration courte, refus par défaut, justifiée | 60 s (§4.1). Testé en avançant l'horloge | PASS |
| F2.5 — le chemin vocal se déclenche en réel | Test de bout en bout, micro simulé : « ferme la fenêtre » à la voix → phrase attendue, rien de fermé. **En réel : non constaté**, F-R1 reportée | PARTIEL |
| F2.6 — les automatisations ne sont pas rouvertes | Portée « interactif » : un workflow planifié n'est pas bloqué ; une automatisation ne peut toujours pas fermer de fenêtre. 29 tests B1-ter verts | PASS |
| **F3** — file vidée après la parole | Vrai modèle, vrai audio : 1 réveil → 0 | PASS |
| F3 — fenêtre de suite bornée et visible | 6 s, 5 enchaînements au plus, état « suite » dans le systray et la fenêtre | PASS |
| F3 — un « oui » ne valide jamais une confirmation, prouvé | 5 formulations, la confirmation reste pendante, rien d'exécuté | PASS |
| **F4** — erratum au rapport B1 | Ajouté en fin de rapport, texte d'origine intact, complété par les frères trouvés en F1 | PASS |
| Invariant 3 — zéro LLM dans la validation et la confirmation | `validator.py`, `confirmation.py`, `request_confirmation`, `execute_confirmed` : aucun import ni appel au client Ollama (vérifié à la lecture) | PASS |
| `python -m pytest tests/ -q` → code 0 | 685 passés, 5 ignorés | PASS |
| **Séance au micro F-R1 à F-R6** | **Non exécutée.** Reportée sur décision d'Alexis (02/10/2026), beta visée en fin de semaine | FAIL |

---

## 3. Architecture projet mise à jour

```
cortana-killer-atlas/
├── core/
│   ├── validator.py               ← modifié (CONFIRMATION_POLICY, source unique ; drapeaux épars supprimés)
│   ├── intent_engine.py           ← modifié (request_confirmation, expiration, liste des attentes ;
│   │                                         listes codées en dur supprimées)
│   └── voice_engine.py            ← modifié (fenêtre de suite, file vidée, acquiescement nu refusé)
├── api/
│   └── routes.py                  ← modifié (type confirmation_required, GET /api/confirmations,
│                                             refus retiré, origine étrangère refusée)
├── desktop/
│   └── atlas_desktop.py           ← modifié (dialogue de confirmation, état « suite », fin du faux succès)
├── tools/
│   └── systray.py                 ← modifié (état « suite », turquoise)
├── tests/
│   ├── test_confirmation_f.py     ← NOUVEAU (22 tests, de bout en bout)
│   └── test_voice_followup_f.py   ← NOUVEAU (10 tests, vrai modèle d'éveil)
└── docs/rapports/
    └── RAPPORT_SPRINT_B1.md       ← erratum ajouté en fin, rien d'autre
```

Six commits, dont celui du présent rapport. Les cinq commits de code :
- `9d25555` : F2 ;
- `6baa7f8` : F3 et l'affichage ;
- `3974a24` : erratum F4 ;
- `92134ae` : suppressions définitives ;
- `2d9b4ca` : origine.

Aucun fichier hors périmètre n'a été modifié. `main.py` et `core/confirmation.py` sont intacts.

---

## 4. Détail des implémentations

### 4.1 F2 — une seule source de vérité

**Choix : la table vit dans le validateur, et le moteur la lit.** Le validateur est le lieu de la décision déterministe (invariant 3). C'est lui que les tests B1 et B1-ter interrogent déjà, et il sait si l'appel est interactif. Le moteur ne décide plus, il applique : `confirmation_reason(outil, interactive=...)`.

`CONFIRMATION_POLICY` a deux portées :
- **toujours** : `kill_process`, `run_powershell`, `system_config`, `window_close`, `browser_open`, `maintenance_empty_bin`, `schedule_remove` ;
- **interactif** : `schedule_add`, `trigger_add`, `workflow_create`, `workflow_run`. Ce sont des actions qu'une automatisation lance légitimement : un workflow planifié exécute `workflow_run` depuis B1-ter, et le bloquer aurait cassé les automatisations d'Alexis (F2.6).

Ce qui est **supprimé** :
- `_DESTRUCTIVE_VERBS` ;
- neuf lignes `confirmation = True/False` dispersées dans `resolve` ;
- dans `execute_tool`, les trois blocs codés en dur (`kill_process`/`system_config`, `browser_open`, le `needs_confirmation` générique).

Le drapeau `confirmation_required` du validateur est désormais **dérivé** de la table : il ne peut plus diverger.

**Point d'application.** `ExecutionEngine.execute` lit le drapeau avant tout appel d'outil. `execute_tool` relit la table (portée « toujours ») pour les appels directs. Toute demande passe par `request_confirmation`, qui :
- refuse net un processus système (`always_protected`, décision d'Alexis) ;
- met l'action en attente avec sa cible, son motif, son niveau, sa date de création et son **expiration** ;
- renvoie une réponse complète : `confirmation_id`, `action`, `target`, `reason`, `expires_in`.

**Expiration : 60 s.**
- C'est le temps de lire le dialogue et de cliquer, y compris après une demande vocale faite de l'autre bout de la pièce.
- Au-delà, le contexte a pu changer : la fenêtre « Steam » peut être une autre, le processus a pu redémarrer. Exécuter une vieille demande serait agir sur une situation que personne n'a vue.
- Sans réponse, c'est un **refus** : `purge_expired_confirmations` retire l'attente et `execute_confirmed` répond `expired`.

**Ce que j'ai corrigé en passant, parce que c'est la confirmation** : un refus via `/api/confirm` utilisait `get_pending` et laissait l'attente en mémoire. Il utilise maintenant `resolve_pending`.

### 4.2 F2 — la confirmation se voit

- **`/api/chat`** renvoie `type: confirmation_required` avec les champs du dialogue. Avant, `type: tool_execution`, `message: None`, et la fenêtre écrivait « Action executee. ».
- **`GET /api/confirmations`** liste les attentes. La fenêtre desktop l'interroge avec l'état vocal, toutes les 2 s : c'est ainsi qu'une demande **vocale** apparaît à l'écran.
- **Le dialogue** (`show_confirmation_dialog`) :
  - affiche un libellé lisible (« Fermer la fenêtre »), la cible, le motif, le niveau, et un décompte « Sans réponse, je refuse dans N s » ;
  - propose **Confirmer** et **Annuler** ; fermer la fenêtre du dialogue vaut refus ;
  - se met au premier plan 1,5 s ;
  - n'est ouvert qu'une fois par demande ;
  - se ferme seul à l'expiration et l'écrit dans la conversation.
- **Plus de faux succès.** Le repli « Action executee. » est remplacé par un message qui ne prétend rien. L'état `expired` est annoncé.
- **`/api/chat/stream`** (interface web) : vérifié à la lecture. L'élément de `tool_results` porte `status: confirmation_required`, et `ui/app.js:303` affiche alors les boutons Oui/Non. Il n'y a pas de test de bout en bout (annexe A, P22).

### 4.3 F2 — ce que l'audit a ajouté

**Suppressions définitives.** `maintenance_empty_bin` et `schedule_remove` n'étaient pas dans la table. Aucune intention ne les produit, et les automatisations les excluent : elles sont aujourd'hui inatteignables. Mais le moteur les exécutait s'il les recevait, et « le moteur honore la confirmation pour toutes les actions » ne peut pas reposer sur une absence. Elles sont ajoutées, portée « toujours ».

**Seule Alexis confirme.**
- `/api/confirm` et `/api/confirmations` refusent (403) toute requête dont l'en-tête `Origin` n'est pas Atlas (`http://127.0.0.1:<port>` ou `http://localhost:<port>`).
- Un navigateur envoie toujours cet en-tête sur une requête venue d'une autre origine. La fenêtre desktop (httpx) n'en envoie aucun, et l'interface web est servie par Atlas lui-même.
- Le rebinding DNS est couvert aussi, parce que l'origine serait celle du domaine hostile.
- La demande refusée **reste pendante** pour Alexis.

### 4.4 F3 — la conversation continue, délibérée

Le cycle `_on_wake_word` devient une boucle :
1. écoute ;
2. transcription ;
3. réponse ;
4. **vidage de la file audio et remise à zéro du modèle d'éveil** (`_drain_wake_audio`) ;
5. fenêtre de suite.

**Fenêtre de suite.** `_record_audio(wait_for_speech=6.0)` : sans début de parole en 6 s, l'enregistrement s'arrête et le cycle se termine. Six secondes, parce qu'au micro (sprint E) Alexis enchaînait dans les secondes qui suivaient la réponse. Plus long, Atlas devient un micro ouvert.

**Plafond : 5 enchaînements (`MAX_FOLLOW_UPS`).** Je ne l'avais pas prévu. Le test hérité `test_voice_v40::test_06` m'a fait remarquer qu'une parole continue rouvrait la fenêtre sans fin. Avec une télévision allumée, Atlas aurait répondu à la pièce. Le test du plafond a été vu rouge avant la correction.

**Visible.** L'activité `follow_up` s'affiche « suite » : turquoise dans la zone de notification (« il t'écoute encore, sans « Hey Atlas » »), et dans la fenêtre (« je t'écoute encore : enchaîne sans « Hey Atlas » »).

**Interdiction.** `is_bare_affirmation` reconnaît un acquiescement nu (« oui », « Oui. », « ok vas-y », « confirme », « d'accord », etc.). Si une confirmation attend, Atlas ne traite pas la phrase comme une commande et répond « Je ne valide pas de confirmation à la voix : réponds à l'écran, dans la fenêtre Atlas. ». La règle vaut dans la fenêtre de suite **et** après « Hey Atlas ». La confirmation vocale réelle reste une conception à part (rapport E, annexe A), hors périmètre.

### 4.5 F4 — erratum

Il est ajouté en fin de `RAPPORT_SPRINT_B1.md` : le texte du brief (27/09), puis un complément daté du 30/09 qui nomme les frères trouvés par l'audit et les confirmations invisibles. La dernière ligne rappelle que le texte d'origine n'a pas été modifié.

---

## 5. Résultats des tests

### État rouge, avant correction

`tests/test_confirmation_f.py`, première version (15 tests) :

```
FAILED ...::test_f2_fermer_une_fenetre_attend_la_confirmation - AssertionError: fenêtre fermée sans confirmation : [('window_close', {'title': 'bloc-notes'})]
FAILED ...::test_f2_actions_marquees_par_le_validateur_attendent_la_confirmation[automation-schedule-params0] - AssertionError: schedule_add exécuté sans confirmation
FAILED ...::test_f2_actions_marquees_par_le_validateur_attendent_la_confirmation[automation-trigger-params1] - AssertionError: trigger_add exécuté sans confirmation
FAILED ...::test_f2_actions_marquees_par_le_validateur_attendent_la_confirmation[automation-workflow-params2] - AssertionError: workflow_run exécuté sans confirmation
FAILED ...::test_f2_une_seule_source_de_verite - AssertionError: marqués « à confirmer » mais exécutés directement : ['window_mgmt/close → window_close', 'automation/schedule → schedule_add', 'automation/trigger ...
FAILED ...::test_f2_confirmer_execute_l_action_une_seule_fois - AssertionError: aucune confirmation demandée
FAILED ...::test_f2_refuser_n_execute_rien_et_efface_l_attente - AssertionError: aucune confirmation demandée
FAILED ...::test_f2_expiration_refus_par_defaut - AssertionError: aucune confirmation demandée
FAILED ...::test_f2_la_fenetre_recoit_la_confirmation - AssertionError: exécuté sans confirmation : [('window_close', {'title': 'bloc-notes'})]
FAILED ...::test_f2_les_confirmations_en_attente_sont_exposees - AssertionError: aucune route n'expose les confirmations en attente : une demande vocale resterait invisible
FAILED ...::test_f2_processus_systeme_refuse_sans_confirmation_possible - AssertionError: « csrss.exe » est un processus système : une confirmation est proposée, un clic suffirait à le tuer
FAILED ...::test_f2_voix_fermer_une_fenetre_annonce_la_confirmation - AssertionError: fenêtre fermée à la voix sans confirmation : [('window_close', {'title': 'bloc-notes'})]
12 failed, 3 passed in 41.21s
```

Les 3 tests déjà verts sont des **témoins de non-régression**, verts avant comme après :
- un processus ordinaire reste confirmable ;
- un workflow planifié n'est pas bloqué ;
- une automatisation ne peut pas fermer de fenêtre.

Ajouts issus de l'audit F1 :

```
FAILED ...::test_f2_une_suppression_definitive_attend_la_confirmation_meme_hors_intention[maintenance_empty_bin-args0]
       AssertionError: maintenance_empty_bin exécuté sans confirmation : [('maintenance_empty_bin', {})]
FAILED ...::test_f2_une_suppression_definitive_attend_la_confirmation_meme_hors_intention[schedule_remove-args1]
2 failed, 15 deselected in 1.45s

E       AssertionError: une page web a validé la confirmation : [('window_close', {'title': 'bloc-notes'})]
E       AssertionError: 200 {"pending":[{"confirmation_id":"cbb5c0ec","action":"window_close","target":"bloc-notes",...}]}
FAILED ...::test_f2_une_page_web_ne_peut_pas_valider_une_confirmation
FAILED ...::test_f2_une_page_web_ne_voit_pas_les_confirmations
2 failed, 3 passed, 17 deselected in 8.65s
```

Là encore, les 3 tests verts sont des témoins : la fenêtre desktop et l'interface web confirment toujours.

`tests/test_voice_followup_f.py` :

```
FAILED ...::test_f3_pas_de_reveil_sur_le_son_capte_pendant_la_parole - AssertionError: 1 réveil(s) sur du son capté pendant qu'Atlas parlait
FAILED ...::test_f3_la_fenetre_de_suite_prend_la_question_suivante - AssertionError: seule la première question a été traitée : ['quelle heure il est']
FAILED ...::test_f3_la_fenetre_de_suite_est_bornee - ImportError: cannot import name 'FOLLOW_UP_SECONDS' from 'core.voice_engine'
FAILED ...::test_f3_la_fenetre_de_suite_se_voit - AssertionError: aucune écoute de suite
FAILED ...::test_f3_un_oui_dans_la_fenetre_de_suite_ne_valide_pas_la_confirmation[oui] - AssertionError: le « oui » n'a pas reçu de réponse explicite : ["Cette action nécessite une confirmation à l'écran. Je ne...
  (idem pour « Oui. », « ok vas-y », « confirme », « d'accord »)
9 failed in 3.16s

FAILED ...::test_f3_une_parole_continue_ne_rouvre_pas_la_fenetre_indefiniment - AssertionError: aucun plafond d'enchaînements défini
1 failed in 0.74s
```

**Honnêteté sur les tests « oui ».** Avant F3, un « oui » ne validait pas non plus de confirmation, pour une raison simple : il n'y avait pas de fenêtre de suite, donc pas de « oui » entendu. Le rouge portait sur l'absence de réponse explicite. Ces tests protègent la fenêtre de suite que F3 **crée**. Ils ne prouvent pas une faille antérieure.

`test_f3_la_fenetre_de_suite_est_bornee` a d'abord échoué sur un `ImportError`, ce qui est la leçon B1 : un rouge qui ne teste rien. Je l'ai réécrit pour constater le comportement d'abord et lire la constante ensuite. Son rouge final porte sur l'absence d'écoute de suite.

**Mocks.** Les outils sont remplacés par des **enregistreurs** : aucun effet réel, aucune fenêtre fermée. Les tests vocaux simulent le micro et le haut-parleur. Le modèle d'éveil et son rappel audio sont les vrais.

### Après correction

`tests/test_confirmation_f.py` : 22 passés. `tests/test_voice_followup_f.py` : 10 passés.

### Suite complète

```
.venv\Scripts\python.exe -m pytest tests/ -q -rs
SKIPPED [4] tests\test_action_safety_b1_bis.py:433: un nouvel onglet vide est légitime (« ouvre un nouvel onglet » : pas de clé url)
SKIPPED [1] tests\test_web_v20.py:31: SearXNG non démarré (docker compose up -d)
685 passed, 5 skipped in 133.90s (0:02:13)
exit=0
```

**Écart avec E (654 passés, 4 ignorés)** : +32 nouveaux tests et +1 ignoré. `test_web_v20` est ignoré parce que Docker Desktop était arrêté, donc SearXNG aussi. Ce n'est pas lié au code : 654 − 1 + 32 = 685.

**Un test hérité rouge en cours de route**, `test_voice_v40::test_06_full_pipeline_mock` (`assert '' == 'c est fait'`). Ma première boucle exigeait `_running` et passait un argument nouveau à `_record_audio`. Je l'ai corrigé dans le code, pas dans le test : le premier cycle est inconditionnel. C'est ce test qui a révélé le besoin d'un plafond (§4.4).

---

## 6. Comportement observé en scénarios réels

### 6.1 Sondes réelles sur le moteur (sans effet)

Menées avec les outils remplacés par des enregistreurs, sur le vrai classifieur, le vrai validateur et le vrai moteur :
- « retiens que le code du portail est 4521 » est classé `memory/remember` (1,01), puis échoue sur `Outil inconnu : 'memory_save'` (`ERR_UNKNOWN_TOOL`). « tu te souviens du code du portail ? » est classé `remember` (0,96), pas `recall`.
- `maintenance_empty_bin`, `schedule_remove`, `trigger_toggle`, `set_priority` : aucune intention ne les produit, et le planificateur ne peut pas les produire, car chaque étape repasse par le validateur (`planner.py:192`).
- `web/navigate` → `browser_navigate` ouvre une adresse **sans** confirmation, alors que `browser_open` l'exige (annexe A, P13).

### 6.2 Environnement

Docker Desktop était arrêté pendant le sprint : ChromaDB et SearXNG indisponibles. Rien n'a été lancé ni modifié côté Docker ou mémoire. **Il faut démarrer Docker Desktop avant la séance au micro.**

### 6.3 Séance au micro avec Alexis — F-R1 à F-R6

**Non exécutée.** Décision d'Alexis du 02/10/2026 : la séance est reportée, une beta étant visée pour la fin de la semaine. Aucun des six scénarios n'a été joué ; aucune ligne `[CONFIRMATION]` ni `[VOIX] Fenêtre de suite` n'existe donc dans `logs/atlas.log` pour ce sprint.

Ce que cela laisse sans preuve réelle :
- **F-R1 à F-R3** : le dialogue de confirmation (affichage, boutons, décompte, expiration). Les routes qui l'alimentent sont testées ; le dialogue ne l'est pas.
- **F-R4 et F-R5** : la fenêtre de suite avec un vrai micro, dans une vraie pièce (bruit, durée de 6 s).
- **F-R6** : le refus du « oui », prouvé seulement avec un micro simulé.

Le protocole reste celui du tableau ci-dessous. La colonne « Observé » sera remplie à la reprise.

| ID | Scénario | Attendu | Observé |
|---|---|---|---|
| F-R1 | « Hey Atlas, ferme la fenêtre Steam » | Atlas annonce la confirmation ; le dialogue s'affiche ; Steam reste ouvert | — |
| F-R2 | Confirmer à l'écran | Steam se ferme | — |
| F-R3 | Refuser ; puis laisser expirer une autre demande (60 s) | Rien ne se ferme dans les deux cas | — |
| F-R4 | Après une réponse, enchaîner sans « Hey Atlas » | Pris en compte, voyant turquoise « suite » | — |
| F-R5 | Attendre la fin de la fenêtre (> 6 s), parler sans « Hey Atlas » | Ignoré, voyant bleu « repos » | — |
| F-R6 | « oui » pendant la fenêtre de suite, confirmation affichée | Non validée ; Atlas répond que ça se fait à l'écran | — |

---

## 7. Limites et risques identifiés

- **CORS « * » dans `main.py`** (hors périmètre). La confirmation est protégée, mais une page web ouverte pendant qu'Atlas tourne peut toujours déclencher par `/api/chat` les actions **sans** confirmation : lancer une application connue, taper ou envoyer des touches dans une fenêtre nommée, ouvrir une adresse par `browser_navigate`, effacer un souvenir ou **toute une catégorie** de la mémoire (`DELETE /api/memory/category/{x}`, sans confirmation ni sauvegarde). **Sévérité : haute.** Correction simple : restreindre `allow_origins` aux origines d'Atlas (P1).
- **« Intouchable » affiché sur un jeu ou une fenêtre chargée au premier plan, mais confirmable.** C'est la décision d'Alexis : refus absolu seulement pour les processus système. Le libellé « 🔴 INTOUCHABLE » reste affiché dans le dialogue alors qu'un clic suffit. Ce libellé est trompeur, à renommer (annexe A, P08).
- **Validation réelle absente — sévérité : élevée.** La séance F-R1 à F-R6 est reportée (décision d'Alexis, 02/10/2026). Le dialogue de confirmation de la fenêtre desktop (Tk) n'a **aucun test automatique** et n'a jamais été vu fonctionner. Or F2 rend ce dialogue obligatoire : si le dialogue ne s'ouvre pas, « ferme cette fenêtre » reste bloqué 60 s puis est refusé, sans que l'utilisateur sache pourquoi. C'est exactement le risque nommé par le brief (F2.3, « un prérequis, pas un confort »). Rien de dangereux ne s'exécute dans ce cas : le défaut serait un blocage, pas une action non voulue.
- **Le décompte du dialogue part de `expires_in` à l'affichage.** Pour une demande vocale, la fenêtre la découvre au sondage suivant, jusqu'à 2 s plus tard : le décompte affiché peut sous-estimer le temps restant de 2 s. C'est sans risque, le moteur fait foi.
- **Liste d'acquiescements finie.** Une formulation absente (« carrément », « fais-le ») est traitée comme une commande ordinaire. Elle **ne valide pas** la confirmation pour autant : aucun chemin vocal ne mène à `execute_confirmed`. La liste sert à répondre clairement, pas à protéger.
- **La fenêtre de suite dépend du seuil de début de parole** de `_record_audio`. Un bruit fort dans les 6 s ouvre un enregistrement, transcrit puis traité comme une question. Le plafond de 5 limite les dégâts ; F-R5, reportée, devait le mesurer.

---

## 8. Checklist de validation

- [x] F1 — audit complet en annexe A, statut et sévérité pour chaque promesse
- [x] F1 — seules les promesses de confirmation corrigées
- [x] F2 — une seule source de vérité ; l'autre supprimée
- [x] F2 — le moteur l'applique à toutes les actions (balayage des intentions + appels directs)
- [ ] F2 — dialogue visible avec action, cible, deux boutons — **non constaté, F-R1 reportée**
- [x] F2 — expiration 60 s, refus par défaut
- [ ] F2 — chemin vocal en réel — **non constaté, F-R1 reportée**
- [x] F2 — automatisations non rouvertes (29 tests B1-ter verts)
- [x] F3 — file vidée après la parole (vrai modèle)
- [x] F3 — fenêtre bornée, plafonnée, visible
- [x] F3 — « oui » jamais validant, prouvé par test
- [x] F4 — erratum ajouté, texte d'origine intact
- [x] Tests vus rouges avant correction, sortie brute consignée
- [x] Aucun effet réel dans les tests (enregistreurs, micro simulé)
- [x] Invariant 3 : aucun appel LLM dans validation ni confirmation
- [x] `pytest tests/ -q` → code 0 (685 / 5)
- [x] Aucune commande Docker, aucune écriture en mémoire
- [ ] Séance au micro F-R1 à F-R6 — **reportée sur décision d'Alexis (02/10/2026)**

---

## 9. Recommandations pour le sprint suivant

### P0 — Reprise de la validation réelle (reportée)

**Décisions d'Alexis en vigueur, à reprendre :**
- **Séance au micro reportée** (02/10/2026), beta visée pour la fin de la semaine. À rejouer : F-R1 à F-R6, protocole en §6.3.
- **Processus protégés** : refus absolu pour les processus système seulement ; jeux et fenêtre active chargée restent confirmables (annexe A, P08).
- **`browser_navigate`** : non tranché (point 3 ci-dessous).

**Conditions de reprise :** Docker Desktop démarré, Steam ouvert, `start_atlas_desktop.bat`. Durée : une dizaine de minutes.

**Minimum conseillé avant la beta, sans micro, trois minutes :** taper « ferme la fenêtre Steam » dans la fenêtre Atlas, et vérifier que le dialogue s'ouvre, que **Annuler** ne ferme rien et que **Confirmer** ferme Steam. Cela couvre F-R1 à F-R3 au clavier, soit la seule partie du sprint qui n'a aucun test.

### P1 — Sécurité
1. **Restreindre le CORS** de `main.py` aux origines d'Atlas. C'est le reste de la faille corrigée ici pour la confirmation.
2. **Protéger `DELETE /api/memory/category/{x}`** : suppression de masse sans confirmation ni sauvegarde, sans appelant connu. Il faut soit la retirer, soit exiger une sauvegarde vérifiée (comme `memory_cleanup`).
3. **Décider pour `browser_navigate`** : le même effet que `browser_open` sans confirmation. Soit on confirme les deux, soit aucun. C'est une décision d'Alexis (annexe A, P13).

### P2 — Promesses non tenues hors confirmation
4. **Mémoire à la demande** : `memory_save`/`memory_recall`/`memory_forget` sont annoncés par le classifieur mais n'ont pas d'outil. « Retiens que… » échoue sur « Outil inconnu ». Il faut aussi corriger « tu te souviens » classé `remember`.
5. **Télémétrie du client ChromaDB** : `ANONYMIZED_TELEMETRY=FALSE` est posé côté serveur (docker-compose), mais le client dans le processus Atlas l'a active (200 lignes « Anonymized telemetry enabled » dans `atlas.log`). Cela touche les invariants 1 et 6.
6. **`confirm_before_run`** des workflows : la clé n'est jamais lue. En interactif, `workflow_run` est désormais toujours confirmé, donc la clé est sans objet. Il faut la retirer des YAML ou la lire.

### P3
7. **Renommer « 🔴 INTOUCHABLE »** quand le niveau reste confirmable (jeu, fenêtre active chargée).
8. **Statut global de `/api/health`** : il ignore la voix, qui peut être morte avec `status: ok`.
9. **Test de bout en bout de `/api/chat/stream`** pour la confirmation.
10. **Dédoublonnage de la partition « erreurs »** de la mémoire (seul `save()` dédoublonne).

---

## Annexe A — Audit des promesses (F1)

Statuts :
- **tenue** : prouvée de bout en bout par un test ;
- **partielle** : appliquée sur un chemin, pas sur un autre, ou sans test de bout en bout ;
- **non tenue** ;
- **non vérifiable**, avec la raison.

« Avant F » indique le statut trouvé par l'audit, quand F l'a changé.

### A.1 Invariants de la roadmap

| # | Promesse | Déclarée où | Appliquée où | Test de bout en bout ? | Statut | Conséquence / sévérité |
|---|---|---|---|---|---|---|
| P01 | Inv. 1 — tout est local | Roadmap (Notion), rapport A | Ollama, ChromaDB, Piper, Whisper locaux ; API sur 127.0.0.1 | Non | **partielle** | Le client ChromaDB envoie une télémétrie d'usage anonyme (pas le contenu des souvenirs) ; le serveur l'a coupée, pas le client. **Moyenne.** La recherche web sort par nature, à la demande. |
| P02 | Inv. 2 — boucle contrôlée : classifieur → validateur → moteur | Roadmap | `routes.chat_endpoint`, `chat_stream_endpoint`, `voice_engine._run_text_pipeline` ; plans : chaque étape repasse par le validateur (`planner.py:192`) ; automatisations : `check_automation_action` (B1-ter) | Oui (B1, B1-bis, B1-ter, F) | **tenue** | — |
| P03 | Inv. 3 — validateur déterministe, zéro LLM dans la validation **et la confirmation** | Roadmap, brief F | `validator.py`, `confirmation.py`, `request_confirmation`, `execute_confirmed` : aucun import du client Ollama | Non : vérifié à la lecture et par import | **tenue** (lecture) | — |
| P04 | Inv. 4 — rien d'irréversible sans confirmation | Roadmap, rapport B1 annexe A | Avant F : 3 outils sur 9 marqués. Après F : `CONFIRMATION_POLICY`, appliquée dans `ExecutionEngine.execute` et `execute_tool` | Oui, `test_confirmation_f.py` | Avant F **non tenue** → **tenue** | Avant : « ferme Steam » fermait Steam (R04) ; créer une tâche planifiée, un déclencheur ou lancer un workflow se faisait sans accord. **Haute.** |
| P05 | Inv. 4 — c'est Alexis qui confirme | Implicite dans l'invariant 4 | Avant F : n'importe quelle origine (CORS « * »). Après F : garde d'origine sur `/api/confirm`, `/api/confirmations` | Oui (`une_page_web_ne_peut_pas_valider…`) | Avant F **non tenue** → **tenue** | Avant : une page web ouverte pouvait demander `run_powershell` et le confirmer elle-même. **Critique.** |
| P06 | Inv. 5 — observabilité | Roadmap | Journal d'actions, codes `ERR_*`, `[CONFIRMATION]`, `[VOIX]`, `ERR_AUTOMATION_BLOCKED` | Partiel (B1-ter : blocage journalisé) | **tenue** | — |
| P07 | Inv. 6 — personnel | Roadmap | Données dans `data/`, ChromaDB local | — | **non vérifiable** | Promesse de nature, pas de comportement. Voir la télémétrie en P01. |

### A.2 Confirmation à trois niveaux et protection des processus

| # | Promesse | Déclarée où | Appliquée où | Test de bout en bout ? | Statut | Conséquence / sévérité |
|---|---|---|---|---|---|---|
| P08 | 🔴 INTOUCHABLE : jamais arrêté | `confirmation.classify_process`, roadmap | Avant F : confirmation proposée, un clic suffisait. Après F : `always_protected` refusé sans confirmation (`ERR_PROTECTED_PROCESS`), revérifié dans `execute_confirmed`. Jeux et fenêtre active chargée : **restent confirmables** (décision d'Alexis) | Oui (`processus_systeme_refuse…`) | Avant F **non tenue** → **partielle** (par décision) | Avant : un clic pouvait tuer `csrss.exe`, donc Windows. **Critique.** Reste : le libellé « INTOUCHABLE » affiché sur un jeu confirmable, **faible**. |
| P09 | 🟡 DEMANDE : confirmation | `classify_process`, `needs_confirmation` | `request_confirmation` (niveau, motif, suggestion) | Oui (`processus_ordinaire_reste_confirmable`) | **tenue** | — |
| P10 | 🟢 LIBRE : arrêté sans demande | `classify_process` | `kill_process` est « toujours » confirmé (commentaire `confirmation.py:135`) | Oui | **tenue** (plus stricte que déclarée) | — |

### A.3 Décisions du validateur

| # | Promesse | Déclarée où | Appliquée où | Test de bout en bout ? | Statut | Conséquence / sévérité |
|---|---|---|---|---|---|---|
| P11 | Le drapeau `confirmation_required` est respecté | `validator.resolve` | Avant F : ignoré par le moteur. Après F : dérivé de la table, lu par le moteur | Oui (`une_seule_source_de_verite`, sur toutes les intentions) | Avant F **non tenue** → **tenue** | Cause racine de R04. **Haute.** |
| P12 | Refus B1/B1-bis : frappe ou raccourci sans cible, fenêtre sans titre, clic hors écran ou hors fenêtre, texte de contrôle, lancement par chemin | `validator._reject`, outils | Validateur **et** outils (`window_controller`, `app_launcher.check_app_name`) | Oui, `test_action_safety_b1_bis.py` (validateur + outil) | **tenue** | — |
| P13 | Ouvrir une adresse externe exige une confirmation | `CONFIRMATION_POLICY["browser_open"]` (héritée d'`execute_tool`) | `browser_open` : oui. **`web/navigate` → `browser_navigate` : même effet, sans confirmation** | Non | **partielle** | L'adresse est filtrée (http/https, B1-bis) ; ouvrir une page n'est pas irréversible. L'incohérence est réelle mais **faible**. C'est une décision d'Alexis (§9), pas corrigée ici. |
| P14 | URL hors liste blanche refusée | `browser_bridge.check_url`, validateur | Validateur + pont navigateur | Oui (B1-bis BS4) | **tenue** | — |

### A.4 Règles du moteur (`execute_tool`, `execute_confirmed`)

| # | Promesse | Déclarée où | Appliquée où | Test de bout en bout ? | Statut | Conséquence / sévérité |
|---|---|---|---|---|---|---|
| P15 | Listes codées en dur de confirmation | `execute_tool` (avant F) | **Supprimées** : remplacées par la table | — | sans objet | — |
| P16 | Une suppression définitive attend l'accord | Règle « rien ne s'efface sans l'accord d'Alexis » | Avant F : `maintenance_empty_bin`, `schedule_remove` absents de toute liste. Après F : « toujours » | Oui (`…meme_hors_intention`) | Avant F **non tenue** (inatteignable) → **tenue** | Aucune conséquence observée : aucun chemin ne les atteint. Défaut latent, **moyen**. |
| P17 | Confirmer exécute une fois, refuser n'exécute rien | `execute_confirmed`, `/api/confirm` | `resolve_pending` dans les deux cas (avant F, le refus laissait l'attente) | Oui | Avant F **partielle** → **tenue** | Avant : une attente refusée restait confirmable. **Moyenne.** |
| P18 | Une confirmation n'attend pas indéfiniment | Brief F (nouvelle) | `expires_at`, `purge_expired_confirmations`, `execute_confirmed` → `expired` | Oui (horloge avancée) | **tenue** (nouvelle) | Avant : aucune expiration. **Moyenne.** |

### A.5 Automatisations (B1-ter)

| # | Promesse | Déclarée où | Appliquée où | Test de bout en bout ? | Statut | Conséquence / sévérité |
|---|---|---|---|---|---|---|
| P19 | Validation à la création, au chargement, à l'exécution | Rapport B1-ter | `check_automation_action(s)`, moteurs, `main.execute_automation_action` | Oui, 29 tests `test_automation_safety_b1_ter.py` | **tenue** | — |
| P20 | Les actions à confirmation restent exclues des automatisations ; la table F ne rouvre rien | Brief F2.6 | `_AUTOMATION_EXCLUSIONS` + portée « interactif » | Oui (`une_automatisation_ne_peut_toujours_pas_fermer…`, `un_workflow_planifie_n_est_pas_bloque`) | **tenue** | — |
| P21 | `confirm_before_run: true` dans un workflow demande une confirmation | YAML des workflows | **Jamais lue** (B1T-R4). En interactif, `workflow_run` est désormais toujours confirmé ; en planifié, les actions sont en liste blanche | Non | **non tenue** (sans effet dangereux) | La clé ment. **Faible.** |

### A.6 Indicateurs et messages

| # | Promesse | Déclarée où | Appliquée où | Test de bout en bout ? | Statut | Conséquence / sévérité |
|---|---|---|---|---|---|---|
| P22 | L'interface web affiche une confirmation | `ui/app.js:303` | `/api/chat/stream` → `tool_results[].status` | Non | **partielle** | Vérifiée à la lecture. **Faible.** |
| P23 | « Action executee. » signifie qu'une action a été exécutée | `atlas_desktop.py` | Avant F : affiché aussi quand rien n'était fait. Après F : confirmation → dialogue ; repli honnête | Route oui ; **affichage Tk : non** (F-R1 reportée) | Avant F **non tenue** → **partielle** (affichage jamais constaté) | Avant : Alexis croyait l'action faite. **Haute.** |
| P24 | « Cette action nécessite une confirmation à l'écran » (voix, E5) | `voice_engine._run_text_pipeline` | Ne se déclenchait jamais : le moteur n'exigeait pas de confirmation | Oui (`voix_fermer_une_fenetre…`, micro simulé) ; réel non constaté | Avant F **non vérifiable** → **tenue** (par test) | — |
| P25 | « C'est fait. » (voix) signifie qu'une action a réussi | `voice_engine.py:797` | Dit quand aucune action n'a renvoyé de message ; les confirmations, refus et échecs sont traités avant (E5) | Partiel | **partielle** | Un outil qui réussit sans message est annoncé « C'est fait. », ce qui est exact. Un outil qui échoue sans `status: error` le serait aussi. **Faible.** |
| P26 | `/api/health` reflète la capacité vocale réelle | Rapport E (E4) | Détail `voice` exact ; **le statut global l'ignore** | Oui (E4) | **partielle** | `status: ok` avec une voix morte. **Faible.** |
| P27 | `/api/voice/state` donne l'activité | Rapport E | `_set_activity`, dont « suite » | Oui (E4, F3) | **tenue** | — |
| P28 | Le voyant montre quand Atlas écoute, y compris sans mot d'éveil | Rapport E, brief F3 | Systray + fenêtre, état « suite » | Activité testée ; couleur du voyant non constatée | **tenue** (par test) | — |

### A.7 Voix (F3)

| # | Promesse | Déclarée où | Appliquée où | Test de bout en bout ? | Statut | Conséquence / sévérité |
|---|---|---|---|---|---|---|
| P29 | Atlas ne réagit pas à ce qu'il entend en parlant | Brief F3 | `_drain_wake_audio` après chaque parole | Oui, vrai modèle | **tenue** (nouvelle) | Avant : 17 réveils sur 29 au micro (E). |
| P30 | Fenêtre de suite bornée | Brief F3 | 6 s, 5 enchaînements | Oui | **tenue** | — |
| P31 | La fenêtre de suite ne valide jamais une confirmation | Brief F3 | `is_bare_affirmation` + aucun chemin vocal vers `execute_confirmed` | Oui, 5 formulations | **tenue** | — |

### A.8 Mémoire et garde-fous

| # | Promesse | Déclarée où | Appliquée où | Test de bout en bout ? | Statut | Conséquence / sévérité |
|---|---|---|---|---|---|---|
| P32 | Pas de doublon à l'écriture | Rapport D (D5) | `MemoryManager.save()` ; **la partition « erreurs » ne passe pas par là** | Oui pour `save` (D5) | **partielle** | Les erreurs répétées s'accumulent. **Faible.** |
| P33 | « Retiens / rappelle-toi / oublie » | `INTENT_CATEGORIES["memory"]` | **Aucun outil** : `memory_save`, `memory_recall`, `memory_forget` absents de `TOOL_HANDLERS` | Sonde réelle (§6.1) | **non tenue** | « Retiens que le code du portail est 4521 » → « Outil inconnu ». Alexis peut croire l'information retenue. **Moyenne.** |
| P34 | Atlas apprend de ses erreurs | Roadmap, rapport D | Ne fonctionne pas (D) | — | **non tenue** | Connu depuis D. Hors périmètre F (interdit). |
| P35 | `backup_memory` : pas de sauvegarde déclarée bonne sans vérification | `scripts/backup_memory.py` | Vérification de restauration | Oui, client simulé (`test_backup_memory_guard.py`) | **tenue** | — |
| P36 | `memory_cleanup` : `atlas_memory` protégée, rien sans liste explicite | `scripts/memory_cleanup.py` | `PROTECTED`, liste d'identifiants | Oui, client simulé (`test_memory_cleanup_guard_e.py`) | **tenue** | — |

**Bilan** : 36 promesses.

| Statut | Nombre | Promesses |
|---|---|---|
| Tenue | 23 | 13 d'emblée : P02, P03, P06, P09, P10, P12, P14, P19, P20, P27, P28, P35, P36. 5 corrigées par F : P04, P05, P11, P16, P17. 5 créées ou rendues effectives par F : P18, P24, P29, P30, P31. |
| Partielle | 8 | P01, P08, P13, P22, P23, P25, P26, P32 |
| Non tenue, hors confirmation | 3 | P21, P33, P34 (inventoriées, §9) |
| Non vérifiable | 1 | P07 |
| Sans objet | 1 | P15 (supprimée) |

P24 était non vérifiable avant F : le chemin ne se déclenchait jamais. La séance au micro étant reportée (décision d'Alexis, 02/10/2026), P24 et P28 ne sont tenues que par test, et P23 reste partielle tant que le dialogue n'a pas été vu en réel.
