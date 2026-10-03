"""Actualización automática desde los releases de GitHub.

Cada 10 minutos pregunta cuál es la última versión publicada (una consulta chica a la
API pública de GitHub, sin mandar ningún dato). Si es más nueva, la baja en 2do plano,
la verifica con el sha256 que publica GitHub y, cuando no estás dictando hace un rato,
la instala: la app avisa, se cierra y vuelve a abrir sola (conserva ajustes, vocabulario
e historial).

Dos formas de instalar:
- Parche (lo normal): el release trae DictadoApp-patch.zip con solo los archivos que
  cambiaron desde la versión anterior (~20 MB: el .exe con el código; las DLLs de CUDA
  casi nunca cambian). Un .cmd los copia encima cuando la app ya se cerró, guardando
  copia de lo que pisa: si algo falla, lo vuelve atrás. Tarda segundos.
- Instalador completo (~1 GB, ~1 min): si no hay parche para tu versión (te salteaste
  una) o si el parche ya falló una vez.
Solo corre en el .exe instalado (nunca en desarrollo ni en el autotest).
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from brand import __version__
from config import APP_DIR

REPO = "ivorojas/dictado-app"
ASSET = "DictadoApp-Setup.exe"
PATCH = "DictadoApp-patch.zip"
FIRST_CHECK_S = 60
EVERY_S = 600
IDLE_S = 30           # sin dictar hace 30 s → se puede instalar (con aviso y cuenta atrás)
APP_ID = "{D1C7A10E-0001-4B91-9A55-DICTALOAPP001}"
DIR = APP_DIR / "update"
_UA = {"User-Agent": f"DictadoApp/{__version__}", "Accept": "application/vnd.github+json"}


def version_tuple(v):
    return tuple(int(n) for n in re.findall(r"\d+", v)[:3])


def latest():
    """{"version", "url", "size", "sha256"} del último release, o None si no hay instalador."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest", headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        rel = json.load(r)
    assets = {}
    for a in rel.get("assets", []):
        digest = a.get("digest") or ""
        assets[a.get("name")] = {"url": a["browser_download_url"], "size": a["size"],
                                 "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else None}
    if ASSET not in assets:
        return None
    return dict(assets[ASSET], version=rel["tag_name"].lstrip("v"), patch=assets.get(PATCH))


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


def _safe(rel):
    parts = rel.replace("\\", "/").split("/")
    return bool(rel) and ":" not in rel and not rel.startswith("/") and ".." not in parts


def prepare_patch(zip_path, stage):
    """Abre el parche, comprueba que sea para ESTA versión y lo extrae a `stage` verificando
    el sha256 de cada archivo. Devuelve la lista de archivos (rutas relativas) o None."""
    shutil.rmtree(stage, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        meta = json.loads(z.read("patch.json"))
        files = meta.get("files") or {}
        if meta.get("from") != __version__ or not files or not all(_safe(r) for r in files):
            return None
        for rel, digest in files.items():
            data = z.read(rel)
            if hashlib.sha256(data).hexdigest() != digest:
                return None
            out = stage / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
    return sorted(files)


def _q(p):
    return f'"{p}"'


def patch_script(stage, files, version, relaunch, pid):
    """El .cmd que aplica el parche: espera a que esta app se cierre (un .exe en uso no se
    puede pisar), guarda copia de lo que va a pisar, copia (reintenta si un antivirus tiene
    el archivo) y, si una copia falla, vuelve todo atrás. Al final abre la app, haya salido
    bien o no. None si alguna ruta no se puede escribir en un .cmd."""
    app, bak = Path(relaunch).parent, DIR / "backup"
    if any(c in str(p) for p in (stage, app, bak) for c in '%!^&"'):
        return None
    rels = [r.replace("/", "\\") for r in files]
    key = rf"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1"
    lines = ["@echo off", "set N=0", ":w",
             f'tasklist /fi "PID eq {pid}" /nh 2>nul | find "{pid}" >nul || goto go',
             "set /a N+=1", "if %N% geq 60 goto go", "ping -n 2 127.0.0.1 >nul", "goto w", ":go",
             f"rmdir /s /q {_q(bak)} >nul 2>&1"]
    lines += [f"call :put {_q(stage / r)} {_q(app / r)} {_q(bak / r)} || goto undo" for r in rels]
    lines += [f'reg query "{key}" >nul 2>&1 && reg add "{key}" /v DisplayVersion /d {version} /f >nul 2>&1',
              f'start "" {_q(relaunch)}', "exit /b 0", ":undo"]
    lines += [f"if exist {_q(bak / r)} (copy /y {_q(bak / r)} {_q(app / r)} >nul) "
              f"else (del /f /q {_q(app / r)} >nul 2>&1)" for r in rels]
    lines += [f'start "" {_q(relaunch)}', "exit /b 1",
              ":put",
              'if exist "%~2" (if not exist "%~dp3" mkdir "%~dp3")',
              'if exist "%~2" (copy /y "%~2" "%~3" >nul || exit /b 1)',
              'if not exist "%~dp2" mkdir "%~dp2"',
              "set T=0", ":put_try",
              'copy /y "%~1" "%~2" >nul && exit /b 0',
              "set /a T+=1", "if %T% geq 10 exit /b 1", "ping -n 2 127.0.0.1 >nul", "goto put_try"]
    return "\r\n".join(lines) + "\r\n"


def run_patch(stage, files, version, relaunch, pid):
    """Lanza el .cmd del parche desacoplado de esta app (que se cierra enseguida)."""
    text = patch_script(stage, files, version, relaunch, pid)
    if text is None:
        return False
    script = DIR / "apply.cmd"
    try:
        script.write_text(text, encoding="oem")
    except (UnicodeEncodeError, OSError):
        return False
    flags = 0x00000200 | 0x08000000   # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    subprocess.Popen(f'cmd /c "{script}"', creationflags=flags, close_fds=True)
    return True


def run_installer(path, relaunch):
    """Lanza el instalador en silencio, desacoplado de esta app (que se cierra enseguida),
    y al terminar vuelve a abrir `relaunch`, haya salido bien o no (nunca te quedás sin app)."""
    flags = 0x00000200 | 0x08000000   # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    cmd = (f'cmd /c ""{path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART '
           f'& start "" "{relaunch}""')
    subprocess.Popen(cmd, creationflags=flags, close_fds=True)


def _pending():
    """Versión cuyo instalador se lanzó (marca escrita justo antes), o None."""
    try:
        return (DIR / "pending.txt").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def installing():
    """True si una actualización se está instalando AHORA: hay marca reciente y su
    instalador está en uso (Windows no deja abrir para escribir un .exe que corre).
    Si abrís la app en ese minuto, no tiene que arrancar encima del instalador."""
    v = _pending()
    if not v or version_tuple(v) <= version_tuple(__version__):
        return False
    try:
        if time.time() - (DIR / "pending.txt").stat().st_mtime > 600:
            return False              # un instalador colgado no puede bloquear la app para siempre
        with open(DIR / f"{v}.exe", "ab"):
            return False
    except PermissionError:
        return True
    except OSError:
        return False


def just_updated():
    """Versión a la que se actualizó en este arranque (para avisar), o None. Limpia lo que ya
    no sirve (instaladores, parches, copias de respaldo); si algo sigue en uso, queda para la próxima."""
    v = _pending()
    done = __version__ if v == __version__ else None
    if not DIR.is_dir():
        return done
    cur = version_tuple(__version__)
    for p in DIR.iterdir():
        name = p.name
        ver = name[6:] if name.startswith("stage-") else name[:-10] if name.endswith("-patch.zip") else None
        stale = (p.suffix == ".part"
                 or (p.suffix == ".exe" and version_tuple(p.stem) <= cur)
                 or (ver is not None and version_tuple(ver) <= cur)
                 or name in ("backup", "apply.cmd")
                 or (name == "pending.txt" and (done or not v or version_tuple(v) < cur)))
        if stale:
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink(missing_ok=True)
            except OSError:
                pass
    return done


class Updater:
    """Busca, baja e instala. Su estado lo muestra Ajustes:
    state: "idle" (todavía no buscó) | "checking" | "uptodate" | "downloading" | "ready"
           | "installing" | "error";  version: la nueva;  progress: 0-1;  checked: cuándo buscó."""

    def __init__(self, is_idle, on_install, on_ready=None, on_soon=None):
        """`is_idle()`: True si se puede cerrar la app sin cortar nada.
        `on_install(version, how)`: cierra la app e instala; how = ("patch", carpeta, archivos)
        o ("full", instalador).  `on_ready(version)`: la versión nueva ya bajó.
        `on_soon(version, manual)`: avisa con cuenta atrás; False si mientras tanto empezaste
        a dictar (se vuelve a esperar)."""
        self.is_idle, self.on_install, self.on_ready, self.on_soon = is_idle, on_install, on_ready, on_soon
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
        v = self.version = info["version"]
        DIR.mkdir(parents=True, exist_ok=True)
        how = self._get_patch(info) or self._get_full(info)
        if how is None:
            self.state = "error"
            return
        self.state = "ready"
        if self.on_ready:
            self.on_ready(v)
        while True:
            while not (self._now.is_set() or self.is_idle()):
                self._now.wait(5)
            manual = self._now.is_set()
            self._now.clear()
            if self.on_soon is None or self.on_soon(v, manual):
                break
        self.state = "installing"
        (DIR / "pending.txt").write_text(v, encoding="utf-8")
        print(f"[update] instalando {v} ({'parche' if how[0] == 'patch' else 'instalador completo'})")
        if self.on_install(v, how) is False:
            self.state = "error"

    def _download(self, asset, dest, what):
        if dest.exists():
            return True
        print(f"[update] hay versión nueva {self.version}: bajando {what}…")
        self.state, self.progress = "downloading", 0.0
        if not download(asset, dest, lambda f: setattr(self, "progress", f)):
            print("[update] la descarga no coincide con la publicada; se descarta")
            return False
        print(f"[update] {what} bajado y verificado")
        return True

    def _get_patch(self, info):
        """("patch", carpeta, archivos) si hay parche para esta versión, si no None."""
        v, asset = info["version"], info.get("patch")
        if not asset:
            return None
        if _pending() == v:
            print("[update] el parche ya se intentó y no quedó: uso el instalador completo")
            return None
        try:
            z, stage = DIR / f"{v}-patch.zip", DIR / f"stage-{v}"
            if not self._download(asset, z, "el parche"):
                return None
            files = prepare_patch(z, stage)
            script = files and patch_script(stage, files, v, sys.executable, 0)
            if not script:
                print("[update] el parche no es para esta versión: uso el instalador completo")
                return None
            script.encode("oem")
            return ("patch", stage, files)
        except Exception as e:
            print(f"[update] no pude preparar el parche ({e}): uso el instalador completo")
            return None

    def _get_full(self, info):
        dest = DIR / f"{info['version']}.exe"
        return ("full", dest) if self._download(info, dest, "el instalador") else None
