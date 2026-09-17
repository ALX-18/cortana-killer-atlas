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
        self._build_ui()
        self._apply_theme()
        self._tick_queue()
        self.refresh_health()

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
                else:
                    self._messages.put(("atlas", data.get("message", "Action effectuée.")))
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

                if data.get("type") == "tool_execution":
                    msg = data.get("message") or "Action executee."
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
