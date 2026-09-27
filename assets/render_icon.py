"""Genera icono.ico (todos los tamaños, dibujados uno por uno) y assets/icon.png.
Correr: .venv\\Scripts\\python.exe assets\\render_icon.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import brand  # noqa: E402

brand.save_ico(ROOT / "icono.ico")
brand.make_icon(256).save(ROOT / "assets" / "icon.png")
print("OK -> icono.ico, assets/icon.png")
