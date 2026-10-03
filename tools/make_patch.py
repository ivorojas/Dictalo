r"""Arma los archivos de actualización de un release (ver updater.py).

    .venv\Scripts\python.exe tools\make_patch.py [manifiesto_anterior.json]

- Output\DictadoApp-manifest.json: sha256 de cada archivo de dist\DictadoApp (se sube al release
  para que el próximo pueda armar su parche).
- Output\DictadoApp-patch.zip: solo los archivos que cambiaron respecto del manifiesto anterior
  (el del release previo), con patch.json {"from", "to", "files"}. Si no se pasa el anterior,
  lo baja del último release publicado con gh. Sin anterior no hay parche (va el instalador).
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from brand import __version__  # noqa: E402

DIST = ROOT / "dist" / "DictadoApp"
OUT = ROOT / "Output"
REPO = "ivorojas/dictado-app"
MAX_PATCH = 400 << 20        # más grande que esto, mejor el instalador completo


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def manifest(dist=DIST):
    return {p.relative_to(dist).as_posix(): sha256(p) for p in sorted(dist.rglob("*")) if p.is_file()}


def previous_manifest():
    tmp = Path(tempfile.mkdtemp())
    r = subprocess.run(["gh", "release", "download", "--repo", REPO, "-p", "DictadoApp-manifest.json",
                        "-D", str(tmp)], capture_output=True, text=True)
    path = tmp / "DictadoApp-manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if r.returncode == 0 and path.exists() else None


def main():
    OUT.mkdir(exist_ok=True)
    files = manifest()
    (OUT / "DictadoApp-manifest.json").write_text(
        json.dumps({"version": __version__, "files": files}, indent=1), encoding="utf-8")
    patch = OUT / "DictadoApp-patch.zip"
    patch.unlink(missing_ok=True)
    prev = (json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1
            else previous_manifest())
    if not prev or prev["version"] == __version__:
        print(f"manifiesto {__version__} listo; sin parche (no hay versión anterior con manifiesto)")
        return
    changed = {rel: h for rel, h in files.items() if prev["files"].get(rel) != h}
    size = sum((DIST / rel).stat().st_size for rel in changed)
    if size > MAX_PATCH:
        print(f"sin parche: cambiaron {size >> 20} MB, va el instalador completo")
        return
    with zipfile.ZipFile(patch, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("patch.json", json.dumps({"from": prev["version"], "to": __version__, "files": changed}))
        for rel in changed:
            z.write(DIST / rel, rel)
    print(f"parche {prev['version']} -> {__version__}: {len(changed)} archivos, {size >> 20} MB "
          f"({patch.stat().st_size >> 20} MB comprimido)")
    for rel in changed:
        print("  ", rel)


if __name__ == "__main__":
    main()
