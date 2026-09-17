# RAPPORT DECISIONNEL — 08/04/2026

Projet: Operation Cortana Killer (assistant-bureau)
Version de reference: v4.0
Objet: Decision de pilotage sur la fonctionnalite voix

## 1. Contexte

La commande de wake-up Atlas reste instable en execution reelle. Le risque principal est un blocage du planning si l'equipe continue a investir sur la voix maintenant.

Decision proposee par le pilotage: mettre la voix en pause temporaire et poursuivre les lots coeur produit.

## 2. Etat technique actuel

- La stack voix v4.0 a ete migree vers OpenWakeWord + faster-whisper + Piper.
- Les tests automatises voix sont valides (12/12).
- Les incidents reels observes sont principalement operationnels (multi-instances, environnements Python differents, collisions de ports), ce qui degrade la fiabilite du wake-up en usage courant.
- Configuration de runtime ajustee pour debloquer le projet: voice.enabled=false.

## 3. Analyse impact / risque

### Risque si on continue la voix maintenant

- Derive de delai forte.
- Mobilisation d'effort sur debug environnement/ops au lieu des fonctionnalites coeur.
- Faible predictibilite du temps restant avant stabilite utilisateur.

### Risque si on met la voix en pause

- Fonctionnalite vocale non livree dans l'immediat.
- Besoin d'un lot de reprise dedie plus tard.

### Benefice de la pause

- Recentrage sur les livrables a plus forte valeur immediat.
- Avancement du projet sans blocage.
- Reduction de la pression technique sur une brique encore sensible.

## 4. Decision recommandee

Valider la pause temporaire de la voix et poursuivre le plan produit principal.

Statut recommande: GO SANS VOIX (temporaire)

## 5. Plan d'execution (court terme)

1. Maintenir voice.enabled=false jusqu'a decision de reprise.
2. Prioriser les chantiers coeur projet (API, intents, automation, workflow, robustesse runtime).
3. Conserver la base voix existante sans extension fonctionnelle pendant cette phase.
4. Definir un lot "Voix Stabilisation" isole avec criteres d'entree/sortie clairs.

## 6. Conditions de reprise du lot voix

- Environnement d'execution unique et reproductible (interpreter, dependances, ports).
- Procedure de demarrage unique sans multi-instance.
- Campagne scenarios reels R01-R06 planifiee et tracee.
- Objectif d'acceptation: >= 5/6 scenarios reels PASS en conditions normales d'usage.

## 7. Decision attendue

Arbitrage comite projet:

- Option A (recommandee): pause voix et poursuite immediate du coeur produit.
- Option B: maintien focus voix jusqu'a stabilisation complete (impact delai eleve).

## 8. Conclusion

Au vu des risques planning et de la nature des incidents actuels, la strategie la plus robuste est de suspendre temporairement la voix pour proteger l'avancement global. La reprise voix se fera dans un lot dedie, cadre, et mesurable.
