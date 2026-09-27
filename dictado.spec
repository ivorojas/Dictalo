# -*- mode: python ; coding: utf-8 -*-
"""Build de Dictado App → ejecutable Windows sin consola (dist\\DictadoApp\\)."""
import glob
import os
import re
import sys
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct,
                                                 StringTable, VarFileInfo, VarStruct,
                                                 VSVersionInfo)

datas, binaries, hiddenimports = [], [], []
for pkg in ["faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers", "sounddevice"]:
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

hiddenimports += ["pystray._win32", "pynput.keyboard._win32", "pynput.mouse._win32",
                  "PIL.ImageTk", "PIL._imagingtk"]

# DLLs CUDA del venv que está corriendo este build → bundle a nvidia/<sub>/bin
_venv = os.path.dirname(os.path.dirname(sys.executable))
_nv = os.path.join(_venv, "Lib", "site-packages", "nvidia")
for sub in ("cublas", "cudnn", "cuda_nvrtc"):
    for dll in glob.glob(os.path.join(_nv, sub, "bin", "*.dll")):
        binaries.append((dll, os.path.join("nvidia", sub, "bin")))

# Ficha de versión del .exe (el Administrador de tareas muestra "Dictado App")
_ver = re.search(r'__version__ = "([\d.]+)"',
                 open(os.path.join(SPECPATH, "brand.py"), encoding="utf-8").read()).group(1)
_v4 = tuple(int(x) for x in (_ver + ".0.0.0").split(".")[:4])
_strings = [StringStruct(k, v) for k, v in (
    ("CompanyName", "Ivo Rojas"), ("FileDescription", "Dictado App"),
    ("FileVersion", _ver), ("InternalName", "DictadoApp"),
    ("LegalCopyright", "© 2026 Ivo Rojas · MIT"), ("OriginalFilename", "DictadoApp.exe"),
    ("ProductName", "Dictado App"), ("ProductVersion", _ver))]
version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_v4, prodvers=_v4),
    kids=[StringFileInfo([StringTable("040904B0", _strings)]),
          VarFileInfo([VarStruct("Translation", [1033, 1200])])])

a = Analysis(["main.py"], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["matplotlib", "scipy", "pandas", "pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DictadoApp",
          console=False, icon="icono.ico", version=version)
coll = COLLECT(exe, a.binaries, a.datas, name="DictadoApp")
