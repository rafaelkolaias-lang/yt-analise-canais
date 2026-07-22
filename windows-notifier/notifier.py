"""
RK YT Analyzer — Notificador do Windows.

Fica rodando em segundo plano, consultando a API do youtube-analyzer a cada
POLL_SECONDS. Quando um canal dispara "pico de views" (notificação
type=view_spike criada pelo sync), abre um POPUP personalizado no canto
inferior direito — clicar nele abre o Analytics do site já filtrado no canal.

Login: na primeira execução (ou quando a sessão expira) abre uma janelinha de
login. O token fica salvo em %APPDATA%\\RK-YT-Notifier\\config.json — sessão
"desktop" dura 1 ano, então não pede login toda hora.

Iniciar com o Windows: após o primeiro login o notificador se registra
sozinho em HKCU\\...\\Run (pode desligar na janela de Configurações — botão ⚙
do popup, ou `python notifier.py --config`).

Sem dependências externas: Python 3.10+ padrão (tkinter, urllib, winreg).
Rodar com `pythonw notifier.py` (sem janela de console) — ver README.md.
"""
from __future__ import annotations

import json
import math
import os
import queue
import socket
import struct
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
import wave
import webbrowser

try:
    import winreg
except ImportError:  # não-Windows (dev) — autostart vira no-op
    winreg = None  # type: ignore[assignment]

try:
    import winsound
except ImportError:  # não-Windows (dev) — som vira no-op
    winsound = None  # type: ignore[assignment]

APP_NAME = "RK-YT-Notifier"
DEFAULT_API_URL = "https://youtube-analyzer-api.duckdns.org"
DEFAULT_SITE_URL = "https://youtube-analyzer.duckdns.org"

POLL_SECONDS = 60
# Popup NÃO fecha sozinho — só no ✕ ou ao clicar (decisão do usuário).
POPUP_WIDTH = 340
POPUP_MARGIN = 12

# Porta local usada como "trava" de instância única (bind falhou = já tem um
# notificador rodando — evita popups duplicados com autostart + clique manual).
SINGLE_INSTANCE_PORT = 47653

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# ---------------------------------------------------------------------------
# Sons estilo game — GERADOS pelo próprio programa (8-bit/arcade).
# O winsound não controla volume na reprodução, então o volume escolhido é
# aplicado na GERAÇÃO do WAV (cache em %APPDATA%\RK-YT-Notifier\sounds).
# Volume 50% = amplitude de referência aprovada pelo usuário; acima disso o
# ganho satura de leve (clipping), o que deixa o som perceptivelmente mais alto.
# ---------------------------------------------------------------------------
SOUND_CHOICES: list[tuple[str, str]] = [
    ("Sem som", ""),
    ("Moeda (Mario)", "moeda"),
    ("Level up (arpejo)", "levelup"),
    ("Power-up (varredura)", "powerup"),
    ("Alerta arcade (3 bips)", "alerta-arcade"),
    ("Sino arcade", "sino-arcade"),
    ("Fanfarra curta", "fanfarra"),
]
DEFAULT_SOUND = "alerta-arcade"
DEFAULT_VOLUME = 50  # % — 50 = volume de referência
_SR = 44100


def _sq(f: float, t: float, duty: float = 0.5) -> float:
    return 1.0 if (f * t) % 1.0 < duty else -1.0


def _tri(f: float, t: float) -> float:
    p = (f * t) % 1.0
    return 4 * p - 1 if p < 0.5 else 3 - 4 * p


def _env(i: int, n: int, attack: float = 0.005) -> float:
    t = i / _SR
    total = n / _SR
    if t < attack:
        return t / attack
    return max(0.0, 1.0 - (t - attack) / (total - attack)) ** 1.5


def _note(freq: float, dur: float, fn=_sq, duty: float = 0.5) -> list[float]:
    n = int(_SR * dur)
    out = []
    for i in range(n):
        t = i / _SR
        v = _sq(freq, t, duty) if fn is _sq else fn(freq, t)
        out.append(v * _env(i, n))
    return out


def _silence(dur: float) -> list[float]:
    return [0.0] * int(_SR * dur)


def _samples_for(key: str) -> list[float]:
    if key == "moeda":
        return _note(987.77, 0.07) + _note(1318.51, 0.45)
    if key == "levelup":
        out: list[float] = []
        for f in (523.25, 659.25, 783.99, 1046.5, 1318.5):
            out += _note(f, 0.11, duty=0.4)
        return out
    if key == "powerup":
        n = int(_SR * 0.55)
        out = []
        for i in range(n):
            t = i / _SR
            f = 250 + (1350 - 250) * (t / 0.55) ** 1.4
            f *= 1.0 + 0.01 * math.sin(2 * math.pi * 35 * t)
            out.append((1.0 if (f * t) % 1.0 < 0.5 else -1.0) * _env(i, n, 0.01))
        return out
    if key == "sino-arcade":
        n = int(_SR * 0.7)
        out = []
        for i in range(n):
            t = i / _SR
            v = (
                0.6 * math.sin(2 * math.pi * 1568 * t)
                + 0.3 * math.sin(2 * math.pi * 3136 * t)
                + 0.15 * math.sin(2 * math.pi * 4704 * t)
            )
            out.append(v * _env(i, n))
        return out
    if key == "fanfarra":
        def chord(freqs: tuple[float, ...], dur: float) -> list[float]:
            n = int(_SR * dur)
            o = []
            for i in range(n):
                t = i / _SR
                v = sum(_sq(f, t, 0.35) for f in freqs) / len(freqs)
                o.append(0.8 * v * _env(i, n))
            return o

        return chord((523.25, 659.25, 783.99), 0.16) + chord((698.46, 880.0, 1046.5), 0.4)
    # default: alerta-arcade (3 bips E6 em onda triangular)
    out = []
    for _ in range(3):
        out += _note(1318.5, 0.12, fn=_tri) + _silence(0.07)
    return out


def sound_wav_path(key: str, volume_pct: int) -> str:
    """Garante o WAV do som `key` no volume dado (gera 1x e cacheia)."""
    pct = max(5, min(100, int(volume_pct or DEFAULT_VOLUME)))
    folder = os.path.join(os.path.dirname(config_path()), "sounds")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{key}-{pct}.wav")
    if os.path.exists(path):
        return path
    gain = 0.9 * (pct / 50.0)
    frames = b"".join(
        struct.pack("<h", int(32767 * max(-1.0, min(1.0, gain * s))))
        for s in _samples_for(key)
    )
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SR)
        w.writeframes(frames)
    return path


def play_sound(cfg: dict) -> None:
    """Toca o som configurado (assíncrono, não trava a UI). '' = mudo."""
    if winsound is None:
        return
    key = cfg.get("sound", DEFAULT_SOUND)
    if not key:
        return
    if key.endswith(".wav"):  # config antiga (sons do sistema) → migra
        key = DEFAULT_SOUND
    try:
        path = sound_wav_path(key, cfg.get("volume", DEFAULT_VOLUME))
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:  # noqa: BLE001 — som é cosmético, nunca derruba o app
        pass

BG = "#141a24"
FG = "#e8edf5"
MUTED = "#8b98ab"
ACCENT = "#f0b429"
BORDER = "#2a3444"


# ---------------------------------------------------------------------------
# Config (%APPDATA%\RK-YT-Notifier\config.json)
# ---------------------------------------------------------------------------
def config_path() -> str:
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    folder = os.path.join(base, APP_NAME)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "config.json")


def load_config() -> dict:
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Autostart (registro Run do usuário atual — sem precisar de admin)
# ---------------------------------------------------------------------------
def _autostart_command() -> str:
    """Comando registrado no Run: pythonw.exe deste Python + este script."""
    exe = sys.executable
    folder, name = os.path.split(exe)
    if name.lower() == "python.exe":
        pythonw = os.path.join(folder, "pythonw.exe")
        if os.path.exists(pythonw):
            exe = pythonw
    script = os.path.abspath(__file__)
    return f'"{exe}" "{script}"'


def autostart_enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """Liga/desliga o início junto com o Windows. Retorna True se aplicou."""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def acquire_single_instance() -> socket.socket | None:
    """Bind numa porta local como trava. None = já existe instância rodando."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        s.listen(1)
        return s
    except OSError:
        return None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class AuthRequired(Exception):
    pass


def api_request(cfg: dict, method: str, path: str, body: dict | None = None) -> dict:
    url = cfg.get("api_url", DEFAULT_API_URL).rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    token = cfg.get("token")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise AuthRequired()
        raise


def do_login(cfg: dict, username: str, password: str) -> None:
    """Chama /api/auth/login como client=desktop e persiste o token."""
    resp = api_request(
        {**cfg, "token": None},
        "POST",
        "/api/auth/login",
        {"username": username, "password": password, "client": "desktop"},
    )
    cfg["token"] = resp["token"]
    save_config(cfg)


def fetch_spikes(cfg: dict) -> list[dict]:
    resp = api_request(cfg, "GET", "/api/notifications?limit=50")
    return [i for i in resp.get("items", []) if i.get("type") == "view_spike"]


# ---------------------------------------------------------------------------
# UI — popups personalizados
# ---------------------------------------------------------------------------
class PopupStack:
    """Empilha popups no canto inferior direito, do mais novo pro mais velho."""

    def __init__(self, root: tk.Tk, on_settings=None):
        self.root = root
        self.on_settings = on_settings
        self.popups: list[tk.Toplevel] = []

    def _relayout(self) -> None:
        # Canto SUPERIOR direito; o popup mais novo fica no topo e os demais
        # descem na pilha.
        sw = self.root.winfo_screenwidth()
        y = POPUP_MARGIN
        for win in self.popups:
            if not win.winfo_exists():
                continue
            win.update_idletasks()
            h = win.winfo_reqheight()
            win.geometry(f"{POPUP_WIDTH}x{h}+{sw - POPUP_WIDTH - POPUP_MARGIN}+{y}")
            y += h + POPUP_MARGIN

    def show(self, title: str, message: str, link_url: str | None) -> None:
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)          # sem borda/título do Windows
        win.attributes("-topmost", True)
        win.configure(bg=BORDER)

        inner = tk.Frame(win, bg=BG, padx=12, pady=10)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        head = tk.Frame(inner, bg=BG)
        head.pack(fill="x")
        tk.Label(
            head, text="🔥 " + title, bg=BG, fg=ACCENT,
            font=("Segoe UI", 10, "bold"), anchor="w",
            wraplength=POPUP_WIDTH - 80, justify="left",
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            head, text="✕", bg=BG, fg=MUTED, bd=0, cursor="hand2",
            activebackground=BG, activeforeground=FG,
            command=lambda: self._close(win),
        ).pack(side="right")
        if self.on_settings is not None:
            tk.Button(
                head, text="⚙", bg=BG, fg=MUTED, bd=0, cursor="hand2",
                activebackground=BG, activeforeground=FG,
                command=self.on_settings,
            ).pack(side="right", padx=(0, 4))

        tk.Label(
            inner, text=message, bg=BG, fg=FG, font=("Segoe UI", 9),
            anchor="w", justify="left", wraplength=POPUP_WIDTH - 30,
        ).pack(fill="x", pady=(4, 6))

        tk.Label(
            inner, text="Clique para abrir no Analytics →", bg=BG, fg=MUTED,
            font=("Segoe UI", 8), anchor="w",
        ).pack(fill="x")

        def open_link(_event=None):
            if link_url:
                webbrowser.open(link_url)
            self._close(win)

        for w in (win, inner, *inner.winfo_children()):
            if isinstance(w, tk.Button):
                continue
            w.bind("<Button-1>", open_link)
            if hasattr(w, "configure"):
                try:
                    w.configure(cursor="hand2")
                except tk.TclError:
                    pass

        self.popups.insert(0, win)
        self._relayout()

    def _close(self, win: tk.Toplevel) -> None:
        if win in self.popups:
            self.popups.remove(win)
        try:
            win.destroy()
        except tk.TclError:
            pass
        self._relayout()


class LoginDialog(tk.Toplevel):
    """Janela de login simples. Preenche cfg['token'] em caso de sucesso."""

    def __init__(self, root: tk.Tk, cfg: dict, on_done):
        super().__init__(root)
        self.cfg = cfg
        self.on_done = on_done
        self.title("RK YT Analyzer — Login")
        self.configure(bg=BG, padx=16, pady=14)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        tk.Label(
            self, text="Entrar no RK Youtube Analyzer", bg=BG, fg=FG,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        tk.Label(self, text="Usuário", bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=1, column=0, sticky="w"
        )
        self.user_entry = tk.Entry(self, width=28)
        self.user_entry.grid(row=1, column=1, pady=3)

        tk.Label(self, text="Senha", bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=2, column=0, sticky="w"
        )
        self.pass_entry = tk.Entry(self, width=28, show="•")
        self.pass_entry.grid(row=2, column=1, pady=3)

        self.status = tk.Label(self, text="", bg=BG, fg="#e5534b", font=("Segoe UI", 8))
        self.status.grid(row=3, column=0, columnspan=2, sticky="w")

        tk.Button(
            self, text="Entrar", command=self.submit, cursor="hand2",
            bg=ACCENT, fg="#1a1a1a", bd=0, padx=16, pady=4,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=4, column=0, columnspan=2, pady=(10, 0))

        self.user_entry.focus_set()
        self.bind("<Return>", lambda _e: self.submit())
        # Centraliza
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def submit(self) -> None:
        username = self.user_entry.get().strip()
        password = self.pass_entry.get()
        if not username or not password:
            self.status.configure(text="Preencha usuário e senha.")
            return
        self.status.configure(text="Entrando…", fg=MUTED)
        self.update_idletasks()
        try:
            do_login(self.cfg, username, password)
        except AuthRequired:
            self.status.configure(text="Usuário ou senha inválidos.", fg="#e5534b")
            return
        except Exception:
            self.status.configure(text="Falha ao falar com a API.", fg="#e5534b")
            return
        # Primeiro login OK → registra o início automático com o Windows
        # (a menos que o usuário já tenha desligado nas Configurações).
        if self.cfg.get("autostart", True):
            if set_autostart(True):
                self.cfg["autostart"] = True
                save_config(self.cfg)
        self.destroy()
        self.on_done()


class SettingsDialog(tk.Toplevel):
    """
    Área de configuração do notificador:
      - Iniciar junto com o Windows (liga/desliga o registro Run).
      - URLs da API e do site.
      - Sair da conta (apaga o token — pede login de novo).
      - Encerrar o notificador.
    """

    def __init__(self, root: tk.Tk, cfg: dict, on_logout=None, on_quit=None):
        super().__init__(root)
        self.cfg = cfg
        self.on_logout = on_logout
        self.on_quit = on_quit
        self.title("RK YT Notifier — Configurações")
        self.configure(bg=BG, padx=16, pady=14)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        tk.Label(
            self, text="Configurações do notificador", bg=BG, fg=FG,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self.autostart_var = tk.BooleanVar(value=autostart_enabled())
        tk.Checkbutton(
            self, text="Iniciar junto com o Windows",
            variable=self.autostart_var, bg=BG, fg=FG, selectcolor=BG,
            activebackground=BG, activeforeground=FG,
            font=("Segoe UI", 9), cursor="hand2",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        tk.Label(self, text="API", bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=2, column=0, sticky="w"
        )
        self.api_entry = tk.Entry(self, width=42)
        self.api_entry.insert(0, cfg.get("api_url", DEFAULT_API_URL))
        self.api_entry.grid(row=2, column=1, pady=3)

        tk.Label(self, text="Site", bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=3, column=0, sticky="w"
        )
        self.site_entry = tk.Entry(self, width=42)
        self.site_entry.insert(0, cfg.get("site_url", DEFAULT_SITE_URL))
        self.site_entry.grid(row=3, column=1, pady=3)

        # Som do alerta
        tk.Label(self, text="Som", bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=4, column=0, sticky="w"
        )
        current_file = cfg.get("sound", DEFAULT_SOUND)
        current_label = next(
            (label for label, f in SOUND_CHOICES if f == current_file),
            SOUND_CHOICES[1][0],
        )
        self.sound_var = tk.StringVar(value=current_label)
        sound_row = tk.Frame(self, bg=BG)
        sound_row.grid(row=4, column=1, sticky="w", pady=3)
        menu = tk.OptionMenu(sound_row, self.sound_var, *[l for l, _ in SOUND_CHOICES])
        menu.configure(bg=BG, fg=FG, activebackground=BG, activeforeground=FG,
                       highlightthickness=0, font=("Segoe UI", 9))
        menu.pack(side="left")
        tk.Button(
            sound_row, text="▶ Testar", cursor="hand2",
            command=self.test_sound, bg=BG, fg=MUTED, bd=1,
            padx=8, pady=2, font=("Segoe UI", 8),
        ).pack(side="left", padx=(8, 0))

        # Volume do som (50% = volume de referência)
        tk.Label(self, text="Volume", bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=5, column=0, sticky="w"
        )
        self.volume_var = tk.IntVar(value=int(cfg.get("volume", DEFAULT_VOLUME)))
        tk.Scale(
            self, from_=5, to=100, resolution=5, orient="horizontal",
            variable=self.volume_var, bg=BG, fg=FG, troughcolor=BORDER,
            highlightthickness=0, length=220, font=("Segoe UI", 8),
        ).grid(row=5, column=1, sticky="w", pady=3)

        self.status = tk.Label(self, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.status.grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

        btns = tk.Frame(self, bg=BG)
        btns.grid(row=7, column=0, columnspan=2, sticky="we", pady=(10, 0))
        tk.Button(
            btns, text="Salvar", command=self.save, cursor="hand2",
            bg=ACCENT, fg="#1a1a1a", bd=0, padx=16, pady=4,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        tk.Button(
            btns, text="Sair da conta", command=self.logout, cursor="hand2",
            bg=BG, fg=MUTED, bd=1, padx=10, pady=3, font=("Segoe UI", 9),
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            btns, text="Encerrar notificador", command=self.quit_app,
            cursor="hand2", bg=BG, fg="#e5534b", bd=1, padx=10, pady=3,
            font=("Segoe UI", 9),
        ).pack(side="right")

        # Centraliza
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def _selected_sound_file(self) -> str:
        label = self.sound_var.get()
        return next((f for l, f in SOUND_CHOICES if l == label), DEFAULT_SOUND)

    def test_sound(self) -> None:
        play_sound(
            {"sound": self._selected_sound_file(), "volume": self.volume_var.get()}
        )

    def save(self) -> None:
        wanted = self.autostart_var.get()
        applied = set_autostart(wanted)
        self.cfg["autostart"] = wanted
        self.cfg["api_url"] = self.api_entry.get().strip() or DEFAULT_API_URL
        self.cfg["site_url"] = self.site_entry.get().strip() or DEFAULT_SITE_URL
        self.cfg["sound"] = self._selected_sound_file()
        self.cfg["volume"] = int(self.volume_var.get())
        save_config(self.cfg)
        if wanted and not applied:
            self.status.configure(text="Salvo — mas não consegui registrar o autostart.", fg="#e5534b")
        else:
            self.status.configure(text="Salvo.", fg=MUTED)

    def logout(self) -> None:
        self.cfg.pop("token", None)
        save_config(self.cfg)
        self.status.configure(text="Sessão apagada — o login será pedido de novo.", fg=MUTED)
        if self.on_logout:
            self.on_logout()

    def quit_app(self) -> None:
        if self.on_quit:
            self.on_quit()
        else:
            self.destroy()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class NotifierApp:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.cfg.setdefault("api_url", DEFAULT_API_URL)
        self.cfg.setdefault("site_url", DEFAULT_SITE_URL)
        save_config(self.cfg)

        self.root = tk.Tk()
        self.root.withdraw()  # sem janela principal — só popups
        self.stack = PopupStack(self.root, on_settings=self.open_settings)
        self.results: queue.Queue = queue.Queue()
        self.login_open = False
        self.settings_win: SettingsDialog | None = None

    # ---- configurações ----
    def open_settings(self) -> None:
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return
        self.settings_win = SettingsDialog(
            self.root,
            self.cfg,
            on_logout=self.ask_login_if_needed,
            on_quit=self.quit,
        )

    def quit(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ---- polling em thread (não trava a UI) ----
    def poll_async(self) -> None:
        def worker():
            try:
                spikes = fetch_spikes(self.cfg)
                self.results.put(("ok", spikes))
            except AuthRequired:
                self.results.put(("auth", None))
            except Exception:
                self.results.put(("err", None))

        threading.Thread(target=worker, daemon=True).start()

    def handle_results(self) -> None:
        try:
            while True:
                kind, payload = self.results.get_nowait()
                if kind == "ok":
                    self.on_spikes(payload)
                elif kind == "auth":
                    self.ask_login_if_needed()
        except queue.Empty:
            pass
        self.root.after(500, self.handle_results)

    def on_spikes(self, spikes: list[dict]) -> None:
        last_seen = int(self.cfg.get("last_seen_id", 0) or 0)
        max_id = max((int(s["id"]) for s in spikes), default=0)

        if "last_seen_id" not in self.cfg:
            # Primeira rodada: só ancora o ponteiro (não re-notifica picos velhos).
            self.cfg["last_seen_id"] = max_id
            save_config(self.cfg)
            return

        new_items = sorted(
            (s for s in spikes if int(s["id"]) > last_seen),
            key=lambda s: int(s["id"]),
        )
        if new_items:
            play_sound(self.cfg)
        for s in new_items[-3:]:  # no máximo 3 popups por rodada
            meta = {}
            try:
                meta = json.loads(s.get("metadata_json") or "{}")
            except ValueError:
                pass
            link = meta.get("link")
            site = self.cfg.get("site_url", DEFAULT_SITE_URL).rstrip("/")
            url = site + link if isinstance(link, str) and link.startswith("/") else site
            self.stack.show(
                title=s.get("title") or "Pico de views",
                message=s.get("message") or "",
                link_url=url,
            )
        if max_id > last_seen:
            self.cfg["last_seen_id"] = max_id
            save_config(self.cfg)

    def ask_login_if_needed(self) -> None:
        if self.login_open:
            return
        if self.cfg.get("token"):
            # Token existe mas deu 401 → sessão morreu; apaga e pede login.
            self.cfg.pop("token", None)
            save_config(self.cfg)
        self.login_open = True

        def done():
            self.login_open = False
            self.poll_async()

        LoginDialog(self.root, self.cfg, done)

    def tick(self) -> None:
        # Recarrega o config do disco a cada rodada — assim mudanças feitas
        # pela janela de Configurações (inclusive em outro processo via
        # --config) valem sem reiniciar. Preserva estado em memória mais novo.
        disk = load_config()
        disk.update({k: v for k, v in self.cfg.items() if k in ("token", "last_seen_id")})
        self.cfg.update(disk)
        if not self.login_open:
            self.poll_async()
        self.root.after(POLL_SECONDS * 1000, self.tick)

    def run(self) -> None:
        if not self.cfg.get("token"):
            self.ask_login_if_needed()
        self.root.after(500, self.handle_results)
        self.tick()
        self.root.mainloop()


def run_config_only() -> None:
    """Modo `--config`: abre só a janela de configurações e sai ao fechar."""
    root = tk.Tk()
    root.withdraw()
    cfg = load_config()
    cfg.setdefault("api_url", DEFAULT_API_URL)
    cfg.setdefault("site_url", DEFAULT_SITE_URL)
    win = SettingsDialog(root, cfg, on_quit=root.destroy)
    win.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    if "--config" in sys.argv:
        run_config_only()
        sys.exit(0)
    lock = acquire_single_instance()
    if lock is None:
        # Já tem um notificador rodando — não duplica.
        sys.exit(0)
    NotifierApp().run()
