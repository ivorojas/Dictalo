"""Dictado entre dos PCs a través de Cruce (el compartidor de teclado y mouse del dueño).

Papeles (config.pc_role; ver effective_role):
- "auto" (por defecto): con placa NVIDIA es "main"; sin NVIDIA y con Cruce conectado a la otra
  PC es "terminal"; si no, "off". Así no hay que configurar nada.
- "off": esta PC dicta sola (como siempre).
- "main": esta PC graba y transcribe también los dictados que se empiezan en la otra.
- "terminal": esta PC no graba ni transcribe (no carga el modelo): F9 le pide el dictado a la
  principal, muestra la ventanita con lo que le llega y pega el texto acá.
El texto se pega en la PC que recibió el F9 DE CIERRE (con Cruce, las teclas van a la PC donde
está el cursor: es donde estás apuntando, con cualquier combinación de teclado y mouse).

Regla de F9 en las dos PCs: si Cruce dice que esta PC está manejando la otra (Mode=Remote), F9
se ignora acá: Cruce ya se lo manda a la otra, que es donde está el cursor.

De Cruce se usa:
- el registro HKCU\\Software\\Cruce\\Presence (Mode, Peer, Pid): dónde está el cursor.
- la API local por named pipe (una línea JSON por pedido) para pasar mensajes a la otra PC:
  {"cmd":"send","app":"dictado","data":{...}} → {"ok":true}
  {"cmd":"subscribe","app":"dictado"} → una línea {"from":..,"data":{..}} por mensaje recibido.
Mensajes de Dictado: {"t":"toggle"} (terminal → principal); {"t":"state","s":"recording"|
"processing"|"hidden","b":[bandas]}, {"t":"text","text":..} y {"t":"error","msg":..}
(principal → terminal).
"""
import ctypes
import io
import json
import threading
import time
import winreg
from ctypes import wintypes

PIPE = r"\\.\pipe\Cruce.Api"
APP = "dictado"


def has_cuda():
    """¿Hay placa NVIDIA usable? (sin cargar el modelo)"""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def effective_role(chosen, cuda=None):
    """Papel real de esta PC. En "auto": con NVIDIA siempre principal (sin Cruce no cambia nada);
    sin NVIDIA, "terminal" solo si Cruce está conectado a la otra PC."""
    if chosen in ("off", "main", "terminal"):
        return chosen
    if has_cuda() if cuda is None else cuda:
        return "main"
    mode, peer = presence()
    return "terminal" if mode and peer else "off"

_k32 = ctypes.WinDLL("kernel32")
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


def _alive(pid):
    h = _k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = wintypes.DWORD()
    ok = _k32.GetExitCodeProcess(h, ctypes.byref(code))
    _k32.CloseHandle(h)
    return bool(ok) and code.value == 259          # STILL_ACTIVE


_live = {"state": None, "feed": None}   # último estado que empujó Cruce (suscripción "_state")


def _on_state(data):
    _live["state"] = data if isinstance(data.get("mode"), str) else None


def presence():
    """(modo, peer) de Cruce: "Local" | "Remote" | "Controlled", o (None, "") si no corre.
    Sale del estado que Cruce empuja por su API en cada cambio (instantáneo); el registro
    Presence queda de respaldo (Cruce 1.19 dejó de escribirlo). peer = "" si la otra PC no
    está conectada."""
    if _live["feed"] is None:
        _live["feed"] = Link(_on_state, app="_state", on_drop=lambda: _live.update(state=None),
                             quiet=True)
        for _ in range(20):                    # la 1ra vez espera el estado inicial (~ms)
            if _live["state"] is not None or not _live["feed"].connected and _ > 5:
                break
            time.sleep(0.01)
    st = _live["state"]
    if st is not None:
        return st["mode"], (st.get("peer") or "") if st.get("connected") else ""
    return _registry_presence()


def _registry_presence():
    """Respaldo si la API no responde: el registro Presence de Cruce (≤1.18)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Cruce\Presence") as k:
            mode = winreg.QueryValueEx(k, "Mode")[0]
            peer = winreg.QueryValueEx(k, "Peer")[0]
            pid = winreg.QueryValueEx(k, "Pid")[0]
    except OSError:
        return None, ""
    return (mode, peer) if _alive(pid) else (None, "")


def driving_other():
    """True si esta PC está manejando la otra (el cursor está allá)."""
    return presence()[0] == "Remote"


def _request(obj):
    try:
        with open(PIPE, "r+b", buffering=0) as f:
            f.write((json.dumps(obj) + "\n").encode("utf-8"))
            line = f.readline()
        return json.loads(line) if line else None
    except (OSError, ValueError):
        return None


def send(data):
    """Manda un mensaje a la Dictado de la otra PC. False si Cruce o la otra PC no están."""
    r = _request({"cmd": "send", "app": APP, "data": data})
    return bool(r and r.get("ok"))


class Link:
    """Recibe los mensajes de la otra PC (`on_message(data)`); se reconecta solo si Cruce se
    cierra o todavía no tiene la API."""

    RETRY_S = 3

    def __init__(self, on_message, app=APP, on_drop=None, quiet=False):
        self.on_message, self.app, self.on_drop, self.quiet = on_message, app, on_drop, quiet
        self.connected = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        logged = self.quiet
        while True:
            try:
                with open(PIPE, "r+b", buffering=0) as f:
                    f.write((json.dumps({"cmd": "subscribe", "app": self.app}) + "\n").encode("utf-8"))
                    self.connected = True
                    if not self.quiet:
                        print("[cruce] conectado")
                    logged = self.quiet
                    reader = io.BufferedReader(f, 65536)   # sin buffer, readline lee de a 1 byte
                    for line in iter(reader.readline, b""):
                        try:
                            msg = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(msg, dict) and isinstance(msg.get("data"), dict):
                            try:
                                self.on_message(msg["data"])
                            except Exception as e:
                                print(f"[cruce] error manejando un mensaje: {e}")
            except OSError as e:
                if not logged:
                    print(f"[cruce] sin conexión con Cruce ({e.__class__.__name__}); reintento solo")
                    logged = True
            if self.connected and not self.quiet:
                print("[cruce] desconectado")
            self.connected = False
            if self.on_drop:
                self.on_drop()
            time.sleep(self.RETRY_S)
