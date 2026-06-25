# -*- mode: python ; coding: utf-8 -*-
"""Build de Dictalo → ejecutable Windows sin consola."""
import glob
import os
import sys
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ["faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers", "sounddevice"]:
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

hiddenimports += ["pystray._win32", "pynput.keyboard._win32", "pynput.mouse._win32"]

# DLLs CUDA del venv que está corriendo este build → bundle a nvidia/<sub>/bin
_venv = os.path.dirname(os.path.dirname(sys.executable))
_nv = os.path.join(_venv, "Lib", "site-packages", "nvidia")
for sub in ("cublas", "cudnn", "cuda_nvrtc"):
    for dll in glob.glob(os.path.join(_nv, sub, "bin", "*.dll")):
        binaries.append((dll, os.path.join("nvidia", sub, "bin")))

a = Analysis(["main.py"], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["matplotlib", "scipy", "pandas", "pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Dictalo",
          console=False, icon="icono.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="Dictalo")
