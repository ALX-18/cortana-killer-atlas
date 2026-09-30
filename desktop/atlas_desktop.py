"""
Atlas Desktop UI (native Tkinter client).

This app provides a native desktop chat shell for Atlas backend
without requiring the browser UI.
"""

from __future__ import annotations

import json
import pathlib
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "config" / "settings.json"


class AtlasDesktop:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Atlas Desktop")
        self.root.geometry("1120x760")
        self.root.minsize(900, 620)
        self.is_busy = False

        self.colors = {
            "bg": "#f6f2e9",
            "panel": "#fffaf3",
            "panel_alt": "#efe8dc",
            "accent": "#0e7a66",
            "accent_dark": "#0b5f50",
            "text": "#1d2a26",
            "muted": "#6a6f69",
            "ok": "#2d8f52",
            "bad": "#b23a3a",
            "user": "#0f6e5d",
            "atlas": "#22486c",
            "system": "#6a6f69",
        }

        self._messages = queue.Queue()
        self._shown_confirmations: set[str] = set()
        self._build_ui()
        self._apply_theme()
        self._tick_queue()
        self.refresh_health()
        self.root.after(2000, self._poll_voice_state)

    def _load_api_base(self) -> str:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        host = cfg.get("server", {}).get("host", "127.0.0.1")
        port = int(cfg.get("server", {}).get("port", 8550))
        return f"http://{host}:{port}"

    def _build_ui(self):
        container = ttk.Frame(self.root, padding=14)
        container.pack(fill="both", expand=True)

        shell = ttk.Frame(container)
        shell.pack(fill="both", expand=True)

        sidebar = ttk.Frame(shell, style="Sidebar.TFrame", padding=12)
        sidebar.pack(side="left", fill="y")

        main = ttk.Frame(shell)
        main.pack(side="left", fill="both", expand=True, padx=(12, 0))

        brand = ttk.Label(sidebar, text="ATLAS", style="Brand.TLabel")
        brand.pack(anchor="w")
        ttk.Label(sidebar, text="Desktop Console", style="Muted.TLabel").pack(anchor="w", pady=(0, 14))

        health_card = ttk.Frame(sidebar, style="Card.TFrame", padding=10)
        health_card.pack(fill="x")
        ttk.Label(health_card, text="Backend Health", style="CardTitle.TLabel").pack(anchor="w")

        health_row = ttk.Frame(health_card, style="Card.TFrame")
        health_row.pack(fill="x", pady=(8, 0))
        self.health_dot = tk.Canvas(health_row, width=14, height=14, highlightthickness=0)
        self.health_dot.pack(side="left", padx=(0, 6))
        self.health_text = ttk.Label(health_row, text="Checking...", style="Muted.TLabel")
        self.health_text.pack(side="left")

        # Sprint E — demande d'Alexis : voir d'un coup d'oeil quand Atlas écoute.
        voice_card = ttk.Frame(sidebar, style="Card.TFrame", padding=10)
        voice_card.pack(fill="x", pady=(8, 0))
        ttk.Label(voice_card, text="Voix", style="CardTitle.TLabel").pack(anchor="w")

        voice_row = ttk.Frame(voice_card, style="Card.TFrame")
        voice_row.pack(fill="x", pady=(8, 0))
        self.voice_dot = tk.Canvas(voice_row, width=14, height=14, highlightthickness=0)
        self.voice_dot.pack(side="left", padx=(0, 6))
        self.voice_text = ttk.Label(voice_row, text="…", style="Muted.TLabel")
        self.voice_text.pack(side="left")
        self.voice_detail = ttk.Label(voice_card, text="", style="Muted.TLabel", wraplength=180)
        self.voice_detail.pack(anchor="w", pady=(6, 0))

        self.status_text = ttk.Label(sidebar, text="Ready", style="Muted.TLabel")
        self.status_text.pack(anchor="w", pady=(12, 8))

        action_card = ttk.Frame(sidebar, style="Card.TFrame", padding=10)
        action_card.pack(fill="x", pady=(4, 0))
        ttk.Label(action_card, text="Quick Actions", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Button(action_card, text="Refresh Health", style="Ghost.TButton", command=self.refresh_health).pack(fill="x", pady=(8, 0))
        ttk.Button(action_card, text="Recent Errors", style="Ghost.TButton", command=self.fetch_errors).pack(fill="x", pady=(6, 0))
        ttk.Button(action_card, text="Index Status", style="Ghost.TButton", command=self.fetch_index_status).pack(fill="x", pady=(6, 0))

        top = ttk.Frame(main)
        top.pack(fill="x")

        self.title_label = ttk.Label(top, text="Atlas Desktop", style="Title.TLabel")
        self.title_label.pack(side="left")

        self.clear_btn = ttk.Button(top, text="Clear", style="Ghost.TButton", command=self.clear_chat)
        self.clear_btn.pack(side="right")
        self.refresh_btn = ttk.Button(top, text="Refresh", style="Ghost.TButton", command=self.refresh_health)
        self.refresh_btn.pack(side="right", padx=(0, 8))

        chat_card = ttk.Frame(main, style="Card.TFrame", padding=2)
        chat_card.pack(fill="both", expand=True, pady=(10, 10))

        chat_wrap = ttk.Frame(chat_card)
        chat_wrap.pack(fill="both", expand=True)
        self.chat = tk.Text(chat_wrap, wrap="word", font=("Segoe UI", 11), padx=14, pady=12, state="disabled")
        self.chat.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(chat_wrap, orient="vertical", command=self.chat.yview)
        scroll.pack(side="right", fill="y")
        self.chat.configure(yscrollcommand=scroll.set)

        self.chat.tag_configure("user_header", foreground=self.colors["user"], font=("Segoe UI", 9, "bold"))
        self.chat.tag_configure("user_body", foreground=self.colors["text"], font=("Segoe UI", 11))
        self.chat.tag_configure("atlas_header", foreground=self.colors["atlas"], font=("Segoe UI", 9, "bold"))
        self.chat.tag_configure("atlas_body", foreground=self.colors["text"], font=("Segoe UI", 11))
        self.chat.tag_configure("system_header", foreground=self.colors["system"], font=("Segoe UI", 9, "bold"))
        self.chat.tag_configure("system_body", foreground=self.colors["muted"], font=("Segoe UI", 10, "italic"))

        composer = ttk.Frame(main)
        composer.pack(fill="x")
        self.input_var = tk.StringVar()
        self.input = ttk.Entry(composer, textvariable=self.input_var, style="Composer.TEntry")
        self.input.pack(side="left", fill="x", expand=True)
        self.input.bind("<Return>", lambda _e: self.send_message())

        self.send_btn = ttk.Button(composer, text="Send", style="Primary.TButton", command=self.send_message)
        self.send_btn.pack(side="left", padx=(8, 0))

        self._append("system", "Atlas Desktop ready. Connecte au backend local API.")

    def _apply_theme(self):
        self.root.configure(bg=self.colors["bg"])
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Sidebar.TFrame", background=self.colors["panel_alt"])
        style.configure("Card.TFrame", background=self.colors["panel"])
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"])
        style.configure("Brand.TLabel", background=self.colors["panel_alt"], foreground=self.colors["accent_dark"], font=("Segoe UI", 18, "bold"))
        style.configure("Title.TLabel", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 16, "bold"))
        style.configure("CardTitle.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Segoe UI", 10, "bold"))
        style.configure("Muted.TLabel", background=self.colors["panel_alt"], foreground=self.colors["muted"], font=("Segoe UI", 9))
        style.configure("Primary.TButton", background=self.colors["accent"], foreground="#ffffff", borderwidth=0, padding=(12, 8))
        style.map("Primary.TButton", background=[("active", self.colors["accent_dark"])])
        style.configure("Ghost.TButton", background=self.colors["panel"], foreground=self.colors["text"], borderwidth=0, padding=(10, 7))
        style.map("Ghost.TButton", background=[("active", "#e8dfd1")])
        style.configure(
            "TButton",
            background=self.colors["accent"],
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=0,
            padding=7,
        )
        style.map("TButton", background=[("active", self.colors["accent_dark"])])
        style.configure("TEntry", fieldbackground="#fffdf8", foreground=self.colors["text"], padding=6)
        style.configure("Composer.TEntry", fieldbackground="#fffefb", foreground=self.colors["text"], padding=9)

        self.chat.configure(
            bg=self.colors["panel"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
        )

    # Sprint E : couleurs alignées sur celles de l'icône de la zone de notification.
    VOICE_COLORS = {
        "repos": "#4682b4", "écoute": "#2ecc71", "suite": "#1abc9c", "réfléchit": "#f39c12",
        "parle": "#9b59b6", "arrêtée": "#7f8c8d", "problème": "#e74c3c",
    }

    def _set_voice_state(self, voice: dict):
        """Affiche l'état réel de la voix : /api/health dit ce qu'Atlas sait faire."""
        if voice is None:
            etat, detail = "arrêtée", "backend indisponible (démarrage en cours ?)"
        elif not isinstance(voice, dict) or not voice:
            etat, detail = "problème", "état inconnu"
        elif not voice.get("enabled"):
            etat, detail = "arrêtée", "voix désactivée dans la configuration"
        elif not voice.get("running"):
            etat, detail = "arrêtée", "moteur vocal arrêté"
        elif voice.get("ok"):
            etat = voice.get("activity") or "repos"
            if etat == "suite":
                detail = "je t'écoute encore : enchaîne sans « Hey Atlas »"
            else:
                detail = f"prête — dis « Hey Atlas » (transcription {voice.get('stt_device') or '?'})"
        else:
            etat = "problème"
            detail = " ; ".join(voice.get("degraded_reason") or ["cause inconnue"])[:160]

        color = self.VOICE_COLORS.get(etat, self.VOICE_COLORS["problème"])
        self.voice_dot.delete("all")
        self.voice_dot.create_oval(2, 2, 12, 12, fill=color, outline=color)
        self.voice_text.config(text=f"Atlas {etat}")
        self.voice_detail.config(text=detail)

    def _set_health_dot(self, ok: bool):
        self.health_dot.delete("all")
        color = self.colors["ok"] if ok else self.colors["bad"]
        self.health_dot.create_oval(2, 2, 12, 12, fill=color, outline=color)

    def _append(self, role: str, text: str):
        self.chat.configure(state="normal")
        prefix = {
            "user": "YOU",
            "atlas": "ATLAS",
            "system": "SYSTEM",
        }.get(role, role.upper())
        stamp = time.strftime("%H:%M:%S")
        header_tag = f"{role}_header" if role in {"user", "atlas", "system"} else "system_header"
        body_tag = f"{role}_body" if role in {"user", "atlas", "system"} else "system_body"
        self.chat.insert("end", f"[{prefix}] {stamp}\n", header_tag)
        self.chat.insert("end", f"{text}\n\n", body_tag)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def clear_chat(self):
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self._append("system", "Chat cleared.")

    def _set_busy(self, busy: bool, message: str = ""):
        self.is_busy = busy
        state = "disabled" if busy else "normal"
        self.send_btn.configure(state=state)
        self.input.configure(state=state)
        if message:
            self.status_text.configure(text=message)
        elif busy:
            self.status_text.configure(text="Sending...")
        else:
            self.status_text.configure(text="Ready")

    # Sprint F — libellés lisibles des actions à confirmer.
    ACTION_LABELS = {
        "window_close": "Fermer la fenêtre",
        "kill_process": "Arrêter le processus",
        "run_powershell": "Exécuter la commande PowerShell",
        "system_config": "Modifier le système",
        "browser_open": "Ouvrir l'adresse",
        "schedule_add": "Créer la tâche planifiée",
        "trigger_add": "Créer le déclencheur",
        "workflow_create": "Créer le workflow",
        "workflow_run": "Lancer le workflow",
    }

    def show_confirmation_dialog(self, data: dict):
        """Affiche une confirmation en attente : action, cible, motif, délai, deux boutons.

        Sprint F : une confirmation qu'on ne voit pas bloque l'action sans que personne le
        sache. Celle-ci s'affiche au premier plan, décompte son délai et se ferme d'elle-même
        à l'expiration — le moteur refuse alors par défaut.
        """
        cid = data.get("confirmation_id") or ""
        if not cid or cid in self._shown_confirmations:
            return
        self._shown_confirmations.add(cid)

        action = data.get("action") or "action"
        cible = data.get("target") or "—"
        motif = data.get("reason") or data.get("message") or "action sensible"
        restant = {"s": int(data.get("expires_in") or 60)}

        dlg = tk.Toplevel(self.root)
        dlg.title("Atlas — confirmation requise")
        dlg.transient(self.root)
        dlg.resizable(False, False)

        ttk.Label(dlg, text=self.ACTION_LABELS.get(action, action), style="CardTitle.TLabel",
                  padding=(16, 12, 16, 2)).pack(anchor="w")
        ttk.Label(dlg, text=f"Cible : {cible}", padding=(16, 2)).pack(anchor="w")
        ttk.Label(dlg, text=f"Pourquoi je demande : {motif}", wraplength=360,
                  padding=(16, 2)).pack(anchor="w")
        if data.get("level"):
            ttk.Label(dlg, text=f"Niveau : {data['level']}", padding=(16, 2)).pack(anchor="w")
        decompte = ttk.Label(dlg, text="", style="Muted.TLabel", padding=(16, 6))
        decompte.pack(anchor="w")

        boutons = ttk.Frame(dlg, padding=(12, 4, 12, 12))
        boutons.pack(fill="x")

        def fermer():
            self._shown_confirmations.discard(cid)
            try:
                dlg.destroy()
            except Exception:
                pass

        def confirmer():
            fermer()
            self._send_confirm(cid, True)

        def annuler():
            fermer()
            self._send_confirm(cid, False)

        ttk.Button(boutons, text="Confirmer", style="Primary.TButton", command=confirmer).pack(side="left", padx=4)
        ttk.Button(boutons, text="Annuler", style="Ghost.TButton", command=annuler).pack(side="left", padx=4)
        dlg.protocol("WM_DELETE_WINDOW", annuler)

        def tic():
            if not dlg.winfo_exists():
                return
            if restant["s"] <= 0:
                fermer()
                self._append("system", f"Confirmation expirée ({self.ACTION_LABELS.get(action, action)} "
                                       f"« {cible} ») : rien n'a été fait.")
                return
            decompte.config(text=f"Sans réponse, je refuse dans {restant['s']} s.")
            restant["s"] -= 1
            dlg.after(1000, tic)

        tic()
        # Une confirmation demandée à la voix doit se voir même si la fenêtre est derrière.
        dlg.lift()
        dlg.attributes("-topmost", True)
        dlg.after(1500, lambda: dlg.winfo_exists() and dlg.attributes("-topmost", False))
        dlg.focus_force()

    def show_disambiguation_dialog(self, data: dict):
        dlg = tk.Toplevel(self.root)
        dlg.title("Confirmation requise")
        dlg.transient(self.root)
        dlg.resizable(False, False)

        ttk.Label(
            dlg,
            text=data.get("message", "Confirmer l'action ?"),
            wraplength=340,
            padding=(16, 12),
        ).pack()

        btn_frame = ttk.Frame(dlg, padding=(12, 0, 12, 12))
        btn_frame.pack(fill="x")

        confirmation_id = data.get("confirmation_id", "")

        def _yes():
            dlg.destroy()
            self._send_confirm(confirmation_id, True)

        def _no():
            dlg.destroy()
            self._send_confirm(confirmation_id, False)

        ttk.Button(btn_frame, text="Oui", style="Primary.TButton", command=_yes).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="Non", style="Ghost.TButton", command=_no).pack(
            side="left", padx=4
        )

        dlg.update_idletasks()
        dlg.grab_set()
        dlg.focus_set()

    def _send_confirm(self, confirmation_id: str, accepted: bool):
        base = self._load_api_base()

        def _job():
            try:
                with httpx.Client(timeout=30.0) as client:
                    r = client.post(
                        f"{base}/api/confirm",
                        json={"confirmation_id": confirmation_id, "accepted": accepted},
                    )
                    r.raise_for_status()
                    data = r.json()
                status = data.get("status", "")
                if status == "cancelled":
                    self._messages.put(("atlas", "Action annulée."))
                elif data.get("result", {}).get("message"):
                    self._messages.put(("atlas", data["result"]["message"]))
                elif status == "expired":
                    self._messages.put(("atlas", "Confirmation expirée : rien n'a été fait."))
                else:
                    self._messages.put(("atlas", data.get("message") or f"Réponse : {status or 'inconnue'}."))
            except Exception as e:
                self._messages.put(("system", f"Confirm request failed: {e}"))
            finally:
                self._messages.put(("busy", {"busy": False, "message": "Ready"}))

        self._run_request(_job)

    def _tick_queue(self):
        try:
            while True:
                role, payload = self._messages.get_nowait()
                if role == "health":
                    ok = payload.get("status") == "ok"
                    self._set_health_dot(ok)
                    services = payload.get("services", {}) if isinstance(payload, dict) else {}
                    ollama_ok = services.get("ollama", {}).get("ok") if isinstance(services, dict) else None
                    status_line = f"API: {payload.get('status', 'unknown')}"
                    if ollama_ok is not None:
                        status_line += f" | Ollama: {'ok' if ollama_ok else 'down'}"
                    self.health_text.config(text=status_line)
                elif role == "voice":
                    self._set_voice_state(payload)
                elif role == "confirmation":
                    self.show_confirmation_dialog(payload)
                elif role == "atlas":
                    self._append("atlas", payload)
                elif role == "system":
                    self._append("system", payload)
                elif role == "busy":
                    self._set_busy(bool(payload.get("busy")), payload.get("message", ""))
                elif role == "disambiguation":
                    self.show_disambiguation_dialog(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._tick_queue)

    def _poll_voice_state(self):
        """Suit l'état de la voix toutes les 1,5 s, en silence.

        Sprint E : ce suivi appelait /api/health, qui sonde Ollama et SearXNG à chaque fois.
        Les appels s'empilaient et le fil se remplissait de « Health check failed ». On
        interroge désormais /api/voice/state, qui ne lit que l'état en mémoire, et un échec
        n'écrit rien dans la conversation.
        """
        base = self._load_api_base()

        def _job():
            try:
                with httpx.Client(timeout=2.0) as client:
                    r = client.get(f"{base}/api/voice/state")
                    r.raise_for_status()
                    self._messages.put(("voice", r.json()))
                    # Sprint F : une confirmation demandée à la voix doit apparaître ici.
                    c = client.get(f"{base}/api/confirmations")
                    if c.status_code == 200:
                        for item in c.json().get("pending", []):
                            self._messages.put(("confirmation", item))
            except Exception:
                self._messages.put(("voice", None))   # backend pas encore prêt : silence

        threading.Thread(target=_job, daemon=True).start()
        self.root.after(1500, self._poll_voice_state)

    def _run_request(self, worker):
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def refresh_health(self):
        base = self._load_api_base()

        def _job():
            last_error = None
            for _ in range(4):
                try:
                    with httpx.Client(timeout=4.0) as client:
                        r = client.get(f"{base}/api/health")
                        r.raise_for_status()
                        data = r.json()
                    self._messages.put(("health", data))
                    return
                except Exception as e:
                    last_error = e
                    time.sleep(1.0)

            self._messages.put(("health", {"status": "down"}))
            self._messages.put(("system", f"Health check failed: {last_error}"))

        self._run_request(_job)

    def fetch_errors(self):
        base = self._load_api_base()

        def _job():
            try:
                with httpx.Client(timeout=8.0) as client:
                    r = client.get(f"{base}/api/errors/recent", params={"limit": 5})
                    r.raise_for_status()
                    data = r.json()
                count = data.get("count", 0)
                if count == 0:
                    self._messages.put(("atlas", "Aucune erreur recente."))
                    return
                lines = [f"Erreurs recentes ({count}):"]
                for e in data.get("errors", []):
                    lines.append(f"- {e.get('error_code', 'ERR')} | {e.get('tool', '?')} | {e.get('error', '')}")
                self._messages.put(("atlas", "\n".join(lines)))
            except Exception as e:
                self._messages.put(("system", f"Error endpoint failed: {e}"))

        self._run_request(_job)

    def fetch_index_status(self):
        base = self._load_api_base()

        def _job():
            try:
                with httpx.Client(timeout=8.0) as client:
                    r = client.get(f"{base}/api/files/index/status")
                    r.raise_for_status()
                    data = r.json()
                self._messages.put((
                    "atlas",
                    "File index status: "
                    f"enabled={data.get('enabled')} running={data.get('running')} "
                    f"count={data.get('count')} generated_at={data.get('generated_at')}",
                ))
            except Exception as e:
                self._messages.put(("system", f"Index status failed: {e}"))

        self._run_request(_job)

    def send_message(self):
        text = self.input_var.get().strip()
        if not text or self.is_busy:
            return
        self.input_var.set("")
        self._append("user", text)
        self._messages.put(("busy", {"busy": True, "message": "Waiting for backend..."}))

        base = self._load_api_base()

        def _job():
            payload = {
                "message": text,
                "history": [],
            }
            try:
                with httpx.Client(timeout=60.0) as client:
                    r = client.post(f"{base}/api/chat", json=payload)
                    r.raise_for_status()
                    data = r.json()

                if data.get("type") == "confirmation_required":
                    self._messages.put(("confirmation", data))
                elif data.get("type") == "tool_execution":
                    # Sprint F : « Action executee. » s'affichait aussi quand RIEN n'avait été
                    # exécuté (confirmation en attente, message absent). Plus de faux succès.
                    msg = data.get("message") or "Terminé, sans détail renvoyé par l'action."
                    self._messages.put(("atlas", msg))
                elif data.get("type") == "disambiguation_required":
                    self._messages.put(("disambiguation", {
                        "confirmation_id": data.get("confirmation_id", ""),
                        "message": data.get("message", "Confirmer l'action ?"),
                        "candidates": data.get("candidates", []),
                    }))
                elif data.get("type") == "error":
                    self._messages.put(("atlas", f"Error: {data.get('error_code', 'ERR')} - {data.get('message', '')}"))
                else:
                    self._messages.put(("atlas", data.get("message", "")))
            except Exception as e:
                self._messages.put(("system", f"Request failed: {e}"))
            finally:
                self._messages.put(("busy", {"busy": False, "message": "Ready"}))

        self._run_request(_job)


def main():
    root = tk.Tk()
    app = AtlasDesktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
