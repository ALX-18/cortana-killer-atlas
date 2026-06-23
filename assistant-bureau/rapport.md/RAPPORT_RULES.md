# 📋 RAPPORT_RULES.md
## Règles obligatoires de rapport — Opération Cortana Killer
## Applicable à tout développeur (CHAT2, CHAT3, CHAT4, CHAT5 et successeurs)

> **Sans rapport conforme → validation refusée → pas de sprint suivant.**
> Aucune exception. Aucun raccourci. Aucun rapport "light".

---

## 🔒 Principe fondateur

L'honnêteté intellectuelle est la valeur non négociable du projet Atlas.

CHAT2 a audité son propre code à 53% et cette honnêteté a déclenché la refonte architecturale qui a sauvé le projet. Tous les rapports suivants doivent maintenir ce standard.

**Un rapport honnête à 60% vaut infiniment mieux qu'un rapport gonflé à 90%.**

Un rapport qui maquille un score, cache une limite, ou omet une régression est rejeté d'office — pas renégocié, pas corrigé, **rejeté**.

---

## 📑 Les 9 sections obligatoires

Chaque rapport de fin de sprint doit contenir ces 9 sections, dans cet ordre exact, toutes non vides.

### Section 1 — Résumé exécutif
- Statut global (VALIDÉ / PARTIELLEMENT VALIDÉ / BLOQUÉ)
- État runtime au moment du rapport
- Résultats principaux en chiffres bruts (X/Y tests, régressions, scénarios réels)
- 5-10 lignes maximum

### Section 2 — Objectifs vs réalisation
Tableau comparatif obligatoire :

| Objectif attendu (brief) | Résultat réel | Statut |
|---|---|---|
| Une ligne par objectif du brief | Description factuelle | PASS / FAIL / PARTIEL |

**Règle :** un objectif non traité doit apparaître avec le statut FAIL, pas être omis.

### Section 3 — Architecture projet mise à jour
Arbre des fichiers touchés (nouveaux + modifiés).
- Marquer `← NOUVEAU vX.X` les fichiers créés
- Inclure fichiers de config, données, tests
- Ne PAS lister les fichiers non touchés

### Section 4 — Détail des implémentations (par fichier)
Pour chaque fichier touché :
- Rôle du module
- Méthodes ajoutées/modifiées
- Intégration avec le reste du pipeline
- Suffisamment détaillé pour qu'un autre développeur comprenne sans lire le code

### Section 5 — Résultats des tests
- **Commande pytest exacte utilisée** (copier-coller, pas paraphraser)
- Score précis X/Y
- **Vérification non-régression sur TOUTES les suites précédentes** — lister chacune, une par une, avec son résultat
- Si une suite n'a pas été exécutée → l'écrire explicitement en section 7 comme limite

**Interdit :** "tous les tests passent" sans détail. **Interdit :** "aucune régression détectée" sans preuve.

### Section 6 — Comportement observé en scénarios utilisateur réels
Tableau obligatoire, même si court :

| ID | Commande utilisateur | Résultat attendu | Résultat observé | Statut |
|---|---|---|---|---|

**Cette section ne peut PAS être vide.** Un sprint validé uniquement sur tests unitaires est un sprint bloqué. Les tests réels sur PC sont obligatoires pour la validation.

Si prérequis matériel manquant → documenter en section 7 et basculer le sprint en statut PARTIELLEMENT VALIDÉ avec conditions de reprise.

### Section 7 — Limites et risques identifiés
Liste honnête avec pour chaque item :
- Description précise
- **Sévérité** : Faible / Moyen / Élevé
- Mitigation proposée

**Règle :** un risque caché découvert après validation = sanction du sprint (retour en arrière possible).

### Section 8 — Checklist de validation
Reprendre **exactement** les critères du brief de sprint. Format strict :
- [x] Critère validé (avec preuve en section 5 ou 6)
- [ ] Critère non validé (avec raison factuelle)

**Interdit :** cocher un critère sans preuve. **Interdit :** inventer de nouveaux critères plus faciles.

### Section 9 — Recommandations pour le sprint suivant
Priorités classées P1/P2/P3 :
- P1 : blocants / fiabilité
- P2 : robustesse technique
- P3 : performance / qualité

Inclure la dette identifiée en section 7.

---

## 🚨 Règles transversales

### Honnêteté > Performance
Un rapport honnête sur un sprint partiellement raté est valorisé.
Un rapport maquillé sur un sprint "réussi" est sanctionné.

### Tests réels > Tests unitaires
Le superviseur ne valide jamais un sprint uniquement sur des tests unitaires.
La section 6 doit contenir des scénarios exécutés sur PC réel.

### Documenter ce qui ne marche pas
Un test qui échoue → dans le rapport.
Un prérequis manquant → dans le rapport.
Un comportement intermittent → dans le rapport.
Bloquer un sprint honnêtement vaut mieux que faire semblant.

### Pas de nouveau scope caché
Ce qui est hors brief mais a été ajouté → doit être listé en section 4 et justifié en section 9.
Le superviseur peut refuser un ajout hors scope même s'il est bien fait.

### Aucun score ne peut être maquillé
53% c'est 53%.
"13/13 PASS sur une suite ciblée" ne dit pas "0 régression sur l'ensemble".
"Les tests critiques passent" n'est pas une mesure, c'est une opinion.

### Les consultants externes (GPT, Kimi) ne valident pas les rapports
Seul le superviseur valide. Les consultants peuvent être cités comme source d'une décision architecturale, jamais comme autorité de validation.

---

## 🔍 Cas spéciaux

### Sprint bloqué par prérequis externe
Si un test réel est impossible parce qu'un prérequis hors contrôle du développeur manque (clé API, modèle, hardware) :
- Statut du sprint : **PARTIELLEMENT VALIDÉ**
- Section 6 : documenter le blocage
- Section 7 : lister le prérequis avec sévérité Élevé
- Section 8 : critères impactés non cochés
- Section 9 : conditions précises de reprise

### Sprint de hardening / post-validation
Si le sprint corrige un sprint précédent déjà validé :
- Expliciter en section 1 : "Sprint post-validation de vX.X"
- Section 2 : objectifs = ce qui était cassé en réel
- Ne pas réclamer de nouveau score global — documenter seulement les fixes

### Passation entre développeurs
Dernier rapport du développeur sortant doit inclure :
- Liste des limites non résolues (section 7 détaillée)
- État exact du repo (branches, commits de référence)
- Prérequis pour reprendre (environnement, dépendances, configs)

---

## ✅ Ce qui déclenche une validation

- Les 9 sections présentes et non vides
- Scores factuels avec commandes pytest exactes
- Section 6 avec scénarios réels documentés
- Checklist cohérente avec les critères du brief
- Limites déclarées honnêtement
- 0 régression sur suites précédentes (ou explication si suite non exécutée)

## ❌ Ce qui déclenche un rejet immédiat

- Section manquante ou vide
- Score sans commande de reproduction
- "Aucune régression" sans liste des suites vérifiées
- Cocher un critère du brief sans preuve
- Scope ajouté sans justification
- Ton promotionnel / commercial au lieu de factuel

---

## 📝 Format de transmission

Le rapport se transmet en **Markdown**, directement dans la conversation avec le superviseur.
Pas de PDF, pas de captures d'écran seules, pas de résumé verbal.
Le rapport doit être lisible brut.

Titre obligatoire :
```
# RAPPORT SPRINT vX.X — [Nom du sprint]
Date: JJ/MM/AAAA
Agent: [Modèle] (CHATx)
```

---

*RAPPORT_RULES.md — Opération Cortana Killer*
*Rédigé par le superviseur Claude — Avril 2026*
*Applicable à toute mission, tout développeur, tout sprint*
*Version 1.0 — Règles immuables*
