# Atlas — Checklist d'installation Windows

> Sprint A (16/09/2026). Procédure à suivre dans l'ordre, case par case, sur un poste
> Windows 10/11 64 bits. Chaque étape a une **vérification** : ne pas passer à la
> suivante tant qu'elle n'est pas verte. Cette checklist sert aussi de spécification
> pour le futur installeur.
>
> Établie sur le poste de Toulouse (i5-10400F, 24 Go RAM, RTX 5060 8 Go, Windows 11 Pro
> 26200). Les pièges rencontrés sur ce poste sont signalés par **⚠ Vu sur le terrain**.

Diagnostic automatique à tout moment, une fois l'étape 4 faite :

```powershell
cd assistant-bureau
python scripts\doctor.py
```

Code de retour 0 : aucun composant critique manquant. Code 1 : lire les lignes `[ECHEC]`,
chacune est suivie d'une correction.

---

## 0. Matériel et système

- [ ] Windows 10/11 64 bits, compte utilisateur avec droits d'installation.
- [ ] RAM ≥ 16 Go. Atlas + Ollama chargé occupent environ 6 à 7 Go en plus de ce qu'utilise déjà le bureau. ⚠ Vu sur le terrain : **Docker Desktop (VM WSL) ajoute ~8 Go**. Sur 24 Go, la chaîne complète a atteint 98 % de RAM (`RAPPORT_SPRINT_A.md`, annexe C.2). Envisager une limite `memory=` dans `%USERPROFILE%\.wslconfig` (arbitrage non tranché).
- [ ] GPU NVIDIA ≥ 8 Go conseillé (qwen2.5:7b). Sinon, voir la recommandation de `doctor.py`.
- [ ] Pilote NVIDIA récent. Vérification :
  ```powershell
  nvidia-smi
  ```
  Le nom du GPU et la VRAM doivent s'afficher. Les RTX 50xx exigent un pilote 570 ou plus récent.
- [ ] **Chemins longs Windows activés.** ⚠ Vu sur le terrain : avec `LongPathsEnabled=0`, `pip install torch` échoue (`OSError: [Errno 2] No such file or directory ... torch\include\...`) dès que le chemin du venv est un peu long. Vérification :
  ```powershell
  Get-ItemPropertyValue HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem -Name LongPathsEnabled
  ```
  Si le résultat est `0` : l'activer depuis un PowerShell administrateur (`New-ItemProperty ... -Value 1 -Force`) puis redémarrer, **ou** placer le dépôt dans un chemin court (ex. `C:\Atlas`).
- [ ] **(Seulement si Docker est utilisé) Virtualisation activée dans le BIOS** (Intel VT-x / AMD SVM). ⚠ Vu sur le terrain : désactivée sur ce poste. Docker Desktop affiche alors « Docker Desktop is unable to start » et WSL renvoie `HCS_E_HYPERV_NOT_INSTALLED`. Vérification :
  ```powershell
  (Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled
  ```
  Le résultat doit être `True`. ⚠ Vu sur le terrain : une fois l'hyperviseur actif (WSL2/Docker), cette propriété repasse à `False`. Vérifier alors `(Get-CimInstance Win32_ComputerSystem).HypervisorPresent`, qui doit valoir `True`. Sinon : redémarrer dans le BIOS et activer l'option. Sur de nombreuses cartes mères Intel, elle se trouve dans Advanced → CPU Configuration → Intel Virtualization Technology (emplacement variable selon le constructeur, non vérifié sur ce poste).

## 1. Git et récupération du dépôt

- [ ] Git for Windows installé : `git --version`.
- [ ] Clonage :
  ```powershell
  git clone <url-du-depot> C:\Atlas
  cd C:\Atlas
  ```
- [ ] Vérification : `assistant-bureau\main.py` existe.

## 2. Python 3.12

- [ ] Installer **Python 3.12.x** (python.org, installeur Windows 64 bits). Cocher « Add python.exe to PATH ». Les autres versions (3.13, 3.14) ne sont pas validées pour Atlas.
- [ ] Vérification :
  ```powershell
  py -0p            # doit lister -V:3.12
  py -3.12 --version
  ```
  ⚠ Vu sur le terrain : plusieurs Python coexistent (3.9, 3.12, 3.14). `python` pointait vers 3.14. Toujours créer le venv avec `py -3.12`, jamais avec `python`.

## 3. Environnement virtuel

Le script `start_atlas_desktop.bat` attend le venv **à la racine du dépôt**, dans `.venv` (à côté de `assistant-bureau\`).

- [ ] Création et activation :
  ```powershell
  cd C:\Atlas
  py -3.12 -m venv .venv
  .\.venv\Scripts\Activate.ps1
  python --version     # 3.12.x
  python -m pip install --upgrade pip
  ```
  Si PowerShell refuse le script d'activation, lancer une fois `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- [ ] **Toujours lancer Atlas depuis un terminal où le venv est activé.** ⚠ Vu sur le terrain : le repli TTS appelle l'exécutable `piper`, qui n'est trouvé que si `.venv\Scripts` est dans le PATH. `start_atlas_desktop.bat` n'active pas le venv (anomalie remontée au sprint B).

## 4. Dépendances Python

- [ ] Installation (environ 10 min, ~2 Go téléchargés, torch compris) :
  ```powershell
  cd assistant-bureau
  python -m pip install -r requirements.txt
  ```
  Les paquets Windows `pywin32`, `comtypes`, `pycaw` et `wmi` en font partie.
- [ ] **Paquets absents de `requirements.txt` mais utilisés** (anomalie remontée au sprint B) :
  ```powershell
  python -m pip install easyocr pypdf
  python -m pip install pytest pytest-asyncio     # seulement pour lancer les tests
  ```
  - `easyocr` : couche OCR 2 du grounding. Sans lui, la couche est ignorée silencieusement.
  - `pypdf` : ingestion de PDF dans la mémoire.
- [ ] **Navigateur Playwright** (commandes « ouvre une page ») : à relancer après chaque installation ou mise à jour de `playwright`. ⚠ Vu sur le terrain : sans cette étape, l'échec est `BrowserType.launch: Executable doesn't exist ... chromium-1243`.
  ```powershell
  python -m playwright install chromium
  ```
- [ ] Vérification :
  ```powershell
  python -m pip check          # "No broken requirements found."
  python -c "import win32api, comtypes, pycaw, wmi, pywinauto; print('win ok')"
  ```
- [ ] Note : `requirements.txt` ne fixe pas la plupart des versions (`>=`). Deux installations à des dates différentes n'obtiennent donc pas les mêmes versions. ⚠ Vu sur le terrain : le venv historique a piper-tts 1.4.1 et torch 2.12.1, une installation neuve du 16/09/2026 a piper-tts 1.8.0 et torch 2.14.0.
- [ ] Note GPU : `pip` installe **torch en version CPU**. EasyOCR et les embeddings tournent donc sur CPU, et `main.py` affiche au démarrage un avertissement « aucun GPU CUDA » **même si le GPU fonctionne** pour la voix (faster-whisper utilise CTranslate2, qui voit bien le GPU). Installer torch CUDA est un arbitrage du sprint B, **non appliqué** ici.

## 5. Tesseract OCR 5.5.0 (obligatoire)

> Épisode fondateur : Tesseract absent pendant 7 sprints, soit environ 90 s de latence par commande « clique sur X », découvert par hasard au sprint v5.2. Ne pas sauter cette étape.

- [ ] Télécharger l'installeur UB-Mannheim 5.5.0 (64 bits) : https://github.com/UB-Mannheim/tesseract/wiki
- [ ] Pendant l'installation : **Additional language data → cocher French**.
- [ ] Ajouter `C:\Program Files\Tesseract-OCR` au **PATH système** (Paramètres → Système → Informations système → Paramètres avancés → Variables d'environnement).
- [ ] **Fermer et rouvrir le terminal** (et l'IDE) : le PATH n'est relu qu'au lancement d'un processus.
- [ ] Vérification **dans le nouveau terminal**, venv activé :
  ```powershell
  where.exe tesseract                  # C:\Program Files\Tesseract-OCR\tesseract.exe
  tesseract --version                  # tesseract v5.5.0...
  tesseract --list-langs               # doit contenir eng ET fra
  python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
  ```
  La dernière commande prouve que **Python** trouve le binaire, ce qui compte réellement.

## 6. EasyOCR (couche OCR 2)

- [ ] Installé à l'étape 4 (`pip install easyocr`).
- [ ] Préchargement des modèles fr+en (~100 Mo, dans `%USERPROFILE%\.EasyOCR\model`) :
  ```powershell
  python -c "import easyocr; easyocr.Reader(['fr','en'], verbose=False); print('easyocr ok')"
  ```
- [ ] Vérification : `dir $env:USERPROFILE\.EasyOCR\model` doit lister `craft_mlt_25k.pth` et `latin_g2.pth`.

## 7. Ollama et modèle de langage

- [ ] Installer Ollama : https://ollama.com/download. Il démarre avec Windows (icône systray). Version validée : 0.34.0.
- [ ] Récupérer le modèle **configuré** (et non `mistral`, comme l'indiquait l'ancien README) :
  ```powershell
  ollama pull qwen2.5:7b
  ```
  Le modèle doit correspondre à `ollama.model` dans `config\settings.json`. Pour une autre VRAM, suivre la recommandation de `python scripts\doctor.py`.
- [ ] Vérification :
  ```powershell
  ollama list                                   # qwen2.5:7b présent
  curl.exe -s http://127.0.0.1:11434/api/tags   # répond en JSON
  ```
- [ ] ⚠ **Ne pas lancer le service `ollama` de `docker-compose.yml`** en plus de l'Ollama natif : les deux veulent le port 11434. Démarrer uniquement les services nommés (étape 8).

## 8. ChromaDB (mémoire long terme)

Atlas attend ChromaDB sur `localhost:8001` (`memory.chroma_port`). Sans lui, Atlas démarre en « mode dégradé » sans mémoire. Deux options :

**Option A — Docker (voie documentée)**, qui exige l'étape 0 « virtualisation » :
- [ ] Docker Desktop installé et démarré (`docker info` répond).
- [ ] Depuis `assistant-bureau\` :
  ```powershell
  docker compose up -d chromadb searxng
  ```
  ⚠ **Ne jamais** lancer `docker compose up -d` sans nommer les services : le service `ollama` démarrerait aussi et prendrait `[::]:11434`. Il redémarre ensuite **à chaque lancement de Docker Desktop** (`restart: unless-stopped`). Vu sur le terrain : `localhost:11434` répondait par l'Ollama du conteneur (0.17.0, sans `qwen2.5:7b`). Si c'est déjà fait :
  ```powershell
  docker stop assistant_ollama
  ```
- [ ] ⚠ **Persistance de la mémoire** : l'image `chromadb/chroma` actuelle écrit dans `/data`, alors que `docker-compose.yml` monte `data\chromadb` sur `/chroma/chroma`. Les données restent donc **dans le conteneur** : `docker compose down`, `docker rm` ou une mise à jour de l'image les effacent. Tant que ce n'est pas corrigé (sprint B) :
  ```powershell
  docker exec assistant_chromadb sh -c "grep persist_path /config.yaml"   # "/data" = problème présent
  docker cp assistant_chromadb:/data C:\Atlas_backup\chromadb_$(Get-Date -Format yyyyMMdd)
  ```
  `python scripts\doctor.py` signale ce problème en CRITIQUE.

**Option B — natif, sans Docker** (utilisée au sprint A, faute de virtualisation) :
- [ ] Dans un terminal dédié, venv activé :
  ```powershell
  cd assistant-bureau
  chroma run --path data\chromadb_native --host localhost --port 8001
  ```
  ⚠ Ne pas pointer `--path` sur `data\chromadb` s'il contient déjà une base créée par l'image Docker : la compatibilité de format entre versions n'a pas été vérifiée.

- [ ] Vérification (A ou B) :
  ```powershell
  curl.exe -s http://localhost:8001/api/v2/heartbeat    # {"nanosecond heartbeat": ...}
  ```

## 9. Recherche web

- [ ] **SearXNG** (`localhost:8888`) : démarré par `docker compose up -d searxng` (option A ci-dessus). Vérification : `curl.exe -s http://localhost:8888/healthz`.
- [ ] **Repli `ddgs`** : installé par `requirements.txt`, utilisé automatiquement si SearXNG ne répond pas. Vérification :
  ```powershell
  python -c "from ddgs import DDGS; print(len(list(DDGS().text('python', max_results=3))))"
  ```
  Le résultat doit être `3` (nécessite Internet).
- [ ] Au moins l'un des deux doit fonctionner.

## 10. Configuration `config\settings.json`

Le fichier est versionné et fonctionne tel quel. Points à relire :

- [ ] `ollama.model` = un modèle présent dans `ollama list`.
- [ ] `ollama.base_url` = `http://127.0.0.1:11434`.
- [ ] `memory.chroma_host` / `memory.chroma_port` = `localhost` / `8001`.
- [ ] `web.searxng_url` = `http://localhost:8888`.
- [ ] `server.port` = `8550` (doit être libre).
- [ ] `voice.enabled` : `true` active micro, mot d'éveil et systray au démarrage. Mettre `false` si le poste n'a pas de micro.
- [ ] `voice.stt_device` : `cuda` si GPU NVIDIA, sinon `cpu`.
- [ ] `grounding.vision_enabled` : laisser à `false` (décision Réunion #4/#5).
- [ ] Vérification : `python -c "import json; json.load(open('config/settings.json', encoding='utf-8')); print('json ok')"`.

## 11. Modèles voix

- [ ] Venv activé, depuis `assistant-bureau\` :
  ```powershell
  python scripts\download_voice_models.py
  ```
  Environ 64 Mo en tout : modèles de support OpenWakeWord, `models\wakewords\hey_atlas.onnx` (205 Ko) et `data\voices\fr_FR-siwis-medium.onnx` (+ `.json`).
- [ ] Vérification : relancer la même commande. Toutes les lignes doivent être `[SKIP] ... deja present` et le code de retour doit valoir 0.
- [ ] ⚠ Les modèles de support OpenWakeWord sont stockés **dans le venv** (`site-packages\openwakeword\resources\models`). Il faut **relancer ce script après chaque recréation du venv**.
- [ ] Micro : Paramètres Windows → Confidentialité et sécurité → Microphone → autoriser les **applications de bureau**. Choisir le micro par défaut dans Paramètres → Son → Entrée.
- [ ] Vérification :
  ```powershell
  python -c "import sounddevice as sd; print(sd.query_devices(kind='input')['name'])"
  ```
- [ ] Mot d'éveil : le modèle est entraîné sur **« Hey Atlas »** (anglais), pas sur « Atlas » seul.
- [ ] **Modèle STT whisper** : il n'est pas couvert par `download_voice_models.py`. Il est téléchargé depuis Hugging Face (`Systran/faster-whisper-base`, ~145 Mo) à la **première** transcription, ce qui ralentit la première commande vocale et exige Internet. Préchargement :
  ```powershell
  python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8'); print('whisper ok')"
  ```
- [ ] **STT sur GPU (`voice.stt_device=cuda`) : cuBLAS 12 requis.** ⚠ Vu sur le terrain : sans CUDA Toolkit 12, chaque transcription échoue avec `RuntimeError: Library cublas64_12.dll is not found or cannot be loaded`. Toute la chaîne vocale est alors en erreur. Options (arbitrage sprint B) :
  - installer les DLL cuBLAS 12 (`pip install nvidia-cublas-cu12`, puis rendre leur dossier `bin` visible dans le PATH), ou le CUDA Toolkit 12.x. **Non testé au sprint A** ;
  - contournement constaté au sprint A, **non recommandé en production** : ajouter `%LOCALAPPDATA%\Programs\Ollama\lib\ollama\cuda_v12` au PATH du terminal qui lance Atlas ;
  - ou `voice.stt_device=cpu` (~5,3 s par transcription de 3 s mesurés, contre ~1,6 s sur GPU à chaud).
  Vérification :
  ```powershell
  python -c "import numpy as np; from faster_whisper import WhisperModel; m=WhisperModel('base', device='cuda', compute_type='int8'); list(m.transcribe(np.zeros(16000, dtype='float32'))[0]); print('stt cuda ok')"
  ```
  Le tout premier appel GPU sur RTX 50xx peut prendre plus de 30 s (compilation des noyaux CUDA, mise en cache ensuite). Commande de vérification rédigée d'après le test du sprint A (bruit de 3 s), non exécutée telle quelle.
- [ ] **TTS** : vérifier qu'une phrase est réellement prononcée. ⚠ Vu sur le terrain : avec piper-tts 1.4.1, aucun son (API Python incompatible avec le code et CLI `piper` cassé, faute de `pathvalidate`). Avec piper-tts 1.8.0, le son ne sort que si le venv est **activé**, via le CLI `piper`. Vérification, venv activé :
  ```powershell
  "Bonjour, je suis Atlas." | piper --model data\voices\fr_FR-siwis-medium.onnx --output_file $env:TEMP\atlas_tts.wav
  ```
  Le fichier WAV doit être créé et non vide.

## 12. Dossiers runtime

- [ ] ⚠ Créer `logs\`. Il n'est pas versionné (`.gitignore`), et `main.py` y ouvre `atlas.log` **à l'import** sans créer le dossier, ce qui fait planter un clone neuf avec `FileNotFoundError`.
  ```powershell
  cd assistant-bureau
  mkdir logs -ErrorAction SilentlyContinue
  mkdir data -ErrorAction SilentlyContinue
  ```

## 13. Premier lancement

- [ ] `python scripts\doctor.py` renvoie le code 0.
- [ ] Toujours depuis `assistant-bureau\`, venv activé (le grounding écrit ses captures dans `data\debug`, un chemin relatif au **répertoire courant**) :
  ```powershell
  python main.py
  ```
- [ ] Vérifications :
  ```powershell
  curl.exe -s http://127.0.0.1:8550/health          # "status":"ok", "memory_connected":true
  curl.exe -s http://127.0.0.1:8550/api/health      # état Tesseract, vision, services
  ```
  Dans `logs\atlas.log` doivent apparaître : `Tesseract OCR : tesseract v5.5.0`, `Mémoire : connectée` et, si la voix est activée, `VoiceEngine demarre`.
- [ ] Interface web : http://127.0.0.1:8550.
- [ ] Interface bureau (optionnelle) : `python desktop\atlas_desktop.py`.

## 14. Tests (optionnel, développeurs)

```powershell
cd assistant-bureau
$env:PYTHONIOENCODING = "utf-8"
python -m pytest tests/ -q --continue-on-collection-errors
python tests\test_architecture_v23.py
python tests\test_interaction_v22.py
python tests\validate_v12.py
```

⚠ Sans `--continue-on-collection-errors`, `pytest tests/` s'arrête avant d'exécuter le moindre test : `tests/test_api_clean.py` et `tests/test_stream_fix.py` sont des scripts qui appellent l'API au moment de l'import. ⚠ Si Atlas tourne pendant les tests, ces deux scripts lui envoient de vraies commandes (« ouvre steam »). ⚠ Plusieurs tests écrivent dans les vrais fichiers de `data\` (`habits.db`, `audit_log.jsonl`).

---

### Récapitulatif de l'installation validée au sprint A

| Composant | Version constatée | Vérifié par |
|---|---|---|
| Windows | 11 Pro 10.0.26200 | `systeminfo` |
| Python | 3.12.3 | `py -3.12 --version` |
| Tesseract | 5.5.0.20241111 (eng, fra, osd) | `doctor.py` |
| Ollama | natif 0.34.0 puis 0.34.1 (mise à jour automatique), modèle qwen2.5:7b ; conteneur Docker arrêté | `doctor.py` |
| ChromaDB | Docker `chromadb/chroma:latest` (serveur 1.0.0, persistance défectueuse) ; natif 1.5.1 testé aussi | heartbeat, `doctor.py` |
| SearXNG | Docker `searxng/searxng:latest` (après activation de la virtualisation) ; recherche JSON 200 | `curl /healthz`, `doctor.py` |
| Pilote NVIDIA | 616.92, RTX 5060 8151 Mio | `nvidia-smi` |
| Modèles voix | hey_atlas.onnx 205 430 o, siwis 63 201 294 o | `download_voice_models.py` x2 |
