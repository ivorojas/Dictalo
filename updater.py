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
EVERY_S = 6 * 3600
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


def download(info, dest):
    """Baja el instalador a `dest` y lo verifica (tamaño y sha256). True si quedó bien."""
    tmp = dest.with_suffix(".part")
    h = hashlib.sha256()
    req = urllib.request.Request(info["url"], headers={"User-Agent": _UA["User-Agent"]})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            h.update(chunk)
            f.write(chunk)
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
    def __init__(self, is_idle, on_install):
        """`is_idle()`: True si se puede cerrar la app sin cortar nada.
        `on_install(version, path)`: cierra la app y lanza el instalador."""
        self.is_idle, self.on_install = is_idle, on_install
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        time.sleep(FIRST_CHECK_S)
        while True:
            try:
                self._check()
            except Exception as e:
                print(f"[update] no pude buscar actualizaciones: {e}")
            time.sleep(EVERY_S)

    def _check(self):
        info = latest()
        if not info or version_tuple(info["version"]) <= version_tuple(__version__):
            return
        DIR.mkdir(parents=True, exist_ok=True)
        dest = DIR / f"{info['version']}.exe"
        if not dest.exists():
            print(f"[update] hay versión nueva {info['version']}: descargando…")
            if not download(info, dest):
                print("[update] la descarga no coincide con la publicada; se descarta")
                return
            print("[update] descargada y verificada")
        while not self.is_idle():
            time.sleep(30)
        (DIR / "pending.txt").write_text(info["version"], encoding="utf-8")
        print(f"[update] instalando {info['version']}")
        self.on_install(info["version"], dest)
