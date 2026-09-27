# Protocole de validation vocale — sprint E

**Pour Alexis, au micro.** Durée : environ 45 minutes, dont 30 d'écoute passive pendant
laquelle tu peux travailler normalement.

C'est la seule étape qui prouve le produit. Tout le reste ne prouve que la logique.

---

## Avant de commencer

1. **Dis « Hey Atlas », jamais « Atlas » seul.** Le modèle est entraîné sur l'expression
   complète, prononcée **à l'anglaise** (« hey » comme en anglais, « atlass »). Mesuré ce
   sprint : une voix anglaise marque 0,995, la même phrase en français 0,0008.
2. Branche ton micro habituel et place-toi à **un mètre**, comme pour un usage normal.
3. Lance Atlas **avec sa fenêtre** :
   ```
   C:\Users\alexis\Cortana_Killer\start_atlas_desktop.bat
   ```
   (Ma première version de ce protocole lançait `main.py` seul, sans interface : c'était une
   erreur de ma part.)
4. Dans la fenêtre Atlas, regarde la carte **« Voix »**, dans la colonne de gauche. Le voyant
   suit ce qu'Atlas fait, en direct :

   | Couleur | État |
   |---|---|
   | bleu | au repos, il attend « Hey Atlas » |
   | **vert** | **il écoute** |
   | orange | il réfléchit |
   | violet | il parle |
   | rouge | problème — la cause est écrite juste en dessous |

   L'icône de la zone de notification suit les mêmes couleurs, avec un anneau clair pendant
   l'écoute.
5. Attends la ligne `[VOIX] Transcription préchauffée en ...` dans la console. Sans elle, la
   première commande sera lente d'une dizaine de secondes.

---

## Les essais

Note simplement ce que tu observes. Les journaux gardent la trace du reste ; je les
dépouillerai ensuite.

### R02 — Le mot d'éveil (le plus important)

Dis « **Hey Atlas** » **dix fois**, à un mètre, en marquant une pause de 3 secondes entre
chaque. Ne dis rien d'autre après.

À noter : **combien de fois sur dix** Atlas passe en écoute (icône de la zone de
notification, ou ligne `Wake word detected` dans les journaux).

| Essai | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Passé en écoute ? | | | | | | | | | | |

### R03 — Une question simple

« **Hey Atlas** » … puis « **Quelle heure il est** »

À noter : la transcription est-elle correcte, et la réponse est-elle **dite à voix haute** ?

> Si Atlas invente une heure fausse, note-le mais **ce n'est pas un échec de ce sprint** :
> c'est le défaut L4, qui a sa propre tranche. Ce qui compte ici : t'a-t-il entendu, et
> t'a-t-il répondu à voix haute ?

### R04 — Une action sensible

« **Hey Atlas** » … puis « **Ferme cette fenêtre** »

Attendu : Atlas **ne ferme rien**, dit à voix haute que l'action nécessite une confirmation
à l'écran, et une notification Windows apparaît.

À noter : a-t-il parlé ? la notification est-elle apparue ? a-t-il fermé quelque chose (il ne
devrait pas) ?

### R05 — Une conversation

« **Hey Atlas** » … puis « **Comment tu vas** »

À noter : réponse parlée, cohérente ?

### R06 — Cinq cycles d'affilée

Enchaîne cinq fois « Hey Atlas » + une question de ton choix, sans redémarrer Atlas.

À noter : y a-t-il eu un plantage ? Atlas revient-il au repos après chaque cycle ?

### R07 — La latence

Pendant R05, note approximativement le délai entre la fin de « Hey Atlas » et le **premier
son** de la réponse. Une estimation suffit : je calculerai la valeur exacte à partir des
horodatages des journaux.

### R08 — Les faux déclenchements

Laisse Atlas tourner **30 minutes** pendant que tu travailles, parles, écoutes de la musique
ou une vidéo — ton usage normal.

À noter : combien de fois Atlas s'est réveillé **sans que tu l'appelles**.

---

## À la fin

1. Arrête Atlas (Ctrl+C dans la console, ou « Quitter » depuis la zone de notification).
2. Donne-moi tes observations, même approximatives.

Je récupérerai les journaux (`logs/atlas.log`) pour les mesures précises. Depuis ta première
séance, le moteur y écrit tout ce qu'il faut — il n'en gardait aucune trace jusque-là :

```
[VOIX] Mot d'éveil détecté (score=0.987, seuil=0.50) — j'écoute.
[VOIX] Transcription (0.18s, cuda) : 'quelle heure il est'
[VOIX] Cycle : écoute 2.4s + transcription 0.18s + réflexion 1.9s + parole 1.2s = 5.7s
       depuis le mot d'éveil (moteur=piper) — réponse : '...'
```

---

## Si quelque chose ne marche pas

| Symptôme | Première chose à vérifier |
|---|---|
| Aucun réveil sur « Hey Atlas » | La prononciation anglaise. Puis `python scripts/doctor.py`, section Voix |
| Réveil mais aucune réponse parlée | `/api/health` → `services.voice.tts` ; le repli voix Windows doit prendre le relais |
| Réponse très lente (plus de 10 s) | `/api/health` → `services.voice.stt.device_used` : s'il indique `cpu`, la transcription GPU a échoué |
| Réveils intempestifs | Note-les pour R08 ; le seuil `wake_word_threshold` se monte par paliers de 0,05 |
