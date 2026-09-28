"""Actualización automática desde los releases de GitHub.

Cada 6 horas pregunta cuál es la última versión publicada (una consulta a la API
pública de GitHub, sin mandar ningún dato). Si es más nueva, baja el instalador en
2do plano, verifica su sha256 contra el que publica GitHub y, cuando no estás
dictando hace un rato, lo instala en silencio: la app se cierra, el instalador la
reemplaza (conserva ajustes, vocabulario e historial) y la vuelve a abrir.
Solo corre en el .exe instalado (nunca en desarrollo ni en el autotest).
"""
import hashlib
import json
import re
import subprocess
import threading
import time
import urllib.request

from brand import __version__
from config import APP_DIR

REPO = "ivorojas/dictado-app"
ASSET = "DictadoApp-Setup.exe"
FIRST_CHECK_S = 90
EVERY_S = 3600
IDLE_S = 120          # sin dictar hace 2 min → se puede instalar
DIR = APP_DIR / "update"
_UA = {"User-Agent": f"DictadoApp/{__version__}", "Accept": "application/vnd.github+json"}


def version_tuple(v):
    return tuple(int(n) for n in re.findall(r"\d+", v)[:3])


def latest():
    """{"version", "url", "size", "sha256"} del último release, o None si no hay instalador."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest", headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        rel = json.load(r)
    for a in rel.get("assets", []):
        if a.get("name") == ASSET:
            digest = a.get("digest") or ""
            return {"version": rel["tag_name"].lstrip("v"), "url": a["browser_download_url"],
                    "size": a["size"],
                    "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else None}
    return None


def download(info, dest, progress=None):
    """Baja el instalador a `dest` y lo verifica (tamaño y sha256). True si quedó bien.
    `progress(fracción)` se llama a medida que baja."""
    tmp = dest.with_suffix(".part")
    h = hashlib.sha256()
    got = 0
    req = urllib.request.Request(info["url"], headers={"User-Agent": _UA["User-Agent"]})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            h.update(chunk)
            f.write(chunk)
            got += len(chunk)
            if progress:
                progress(got / info["size"])
    ok = tmp.stat().st_size == info["size"] and (info["sha256"] is None
                                                 or h.hexdigest() == info["sha256"])
    if ok:
        tmp.replace(dest)
    else:
        tmp.unlink(missing_ok=True)
    return ok


def run_installer(path, relaunch):
    """Lanza el instalador en silencio, desacoplado de esta app (que se cierra enseguida),
    y al terminar vuelve a abrir `relaunch`, haya salido bien o no (nunca te quedás sin app)."""
    flags = 0x00000200 | 0x08000000   # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    cmd = (f'cmd /c ""{path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART '
           f'& start "" "{relaunch}""')
    subprocess.Popen(cmd, creationflags=flags, close_fds=True)


def just_updated():
    """Versión a la que se actualizó en este arranque (para avisar), o None. Limpia los
    instaladores que ya no sirven."""
    marker = DIR / "pending.txt"
    done = None
    try:
        if marker.read_text(encoding="utf-8").strip() == __version__:
            done = __version__
    except OSError:
        pass
    if DIR.is_dir():
        for p in DIR.iterdir():
            if done or p.suffix in (".part", ".txt") or version_tuple(p.stem) <= version_tuple(__version__):
                p.unlink(missing_ok=True)
    return done


class Updater:
    """Busca, baja e instala. Su estado lo muestra Ajustes:
    state: "idle" (todavía no buscó) | "checking" | "uptodate" | "downloading" | "ready"
           | "installing" | "error";  version: la nueva;  progress: 0-1;  checked: cuándo buscó."""

    def __init__(self, is_idle, on_install, on_ready=None):
        """`is_idle()`: True si se puede cerrar la app sin cortar nada.
        `on_install(version, path)`: cierra la app y lanza el instalador.
        `on_ready(version)`: la versión nueva ya bajó (para avisar)."""
        self.is_idle, self.on_install, self.on_ready = is_idle, on_install, on_ready
        self.state, self.version, self.progress, self.checked = "idle", None, 0.0, None
        self._wake = threading.Event()      # "Buscar ahora"
        self._now = threading.Event()       # "Instalar ahora"
        threading.Thread(target=self._loop, daemon=True).start()

    def check_now(self):
        if self.state not in ("checking", "downloading", "ready", "installing"):
            self._wake.set()

    def install_now(self):
        if self.state == "ready":
            self._now.set()

    def _loop(self):
        self._wake.wait(FIRST_CHECK_S)
        while True:
            self._wake.clear()
            try:
                self._check()
            except Exception as e:
                self.state = "error"
                print(f"[update] no pude buscar actualizaciones: {e}")
            self._wake.wait(EVERY_S)

    def _check(self):
        self.state = "checking"
        info = latest()
        self.checked = time.time()
        if not info or version_tuple(info["version"]) <= version_tuple(__version__):
            self.state = "uptodate"
            print(f"[update] al día ({__version__}; última publicada {info and info['version']})")
            return
        self.version = info["version"]
        DIR.mkdir(parents=True, exist_ok=True)
        dest = DIR / f"{info['version']}.exe"
        if not dest.exists():
            print(f"[update] hay versión nueva {info['version']}: descargando…")
            self.state, self.progress = "downloading", 0.0
            if not download(info, dest, lambda f: setattr(self, "progress", f)):
                print("[update] la descarga no coincide con la publicada; se descarta")
                self.state = "error"
                return
            print("[update] descargada y verificada")
        self.state = "ready"
        if self.on_ready:
            self.on_ready(info["version"])
        while not (self._now.is_set() or self.is_idle()):
            self._now.wait(30)
        self.state = "installing"
        (DIR / "pending.txt").write_text(info["version"], encoding="utf-8")
        print(f"[update] instalando {info['version']}")
        self.on_install(info["version"], dest)
