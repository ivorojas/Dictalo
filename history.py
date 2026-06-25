"""Historial de transcripciones (respaldo). Guarda los últimos N en disco, por si
alguno no se pegó en ningún campo y querés recuperarlo."""
import json
from pathlib import Path

_PATH = Path.home() / ".dictalo" / "history.json"
_MAX = 12


def add(text):
    text = (text or "").strip()
    if not text:
        return
    try:
        items = get()
        items.insert(0, text)
        items = items[:_MAX]
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(items, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception:
        pass


def get():
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []
