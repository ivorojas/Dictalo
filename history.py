"""Historial de dictados (respaldo, por si alguno no se pegó y querés recuperarlo).

Cada entrada guarda su fecha; se borran solas pasados RETENTION_DAYS. Se usa desde
dos hilos (el worker agrega, la ventana de Ajustes lee) → todo bajo un lock.
`version` cambia con cada escritura para que la UI sepa cuándo refrescarse.
"""
import json
import threading
import time

from config import APP_DIR

RETENTION_DAYS = 3
_MAX = 300
_PATH = APP_DIR / "history.json"
_lock = threading.Lock()
version = 0


def _load():
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    legacy_t = None
    items = []
    for it in data:
        if isinstance(it, str):              # formato viejo: solo texto, sin fecha
            if legacy_t is None:
                legacy_t = _PATH.stat().st_mtime
            items.append({"t": legacy_t, "text": it})
        elif isinstance(it, dict) and it.get("text"):
            items.append({"t": float(it.get("t") or 0), "text": str(it["text"])})
    return items


def _save(items):
    global version
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(items, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception:
        pass
    version += 1


def _prune(items):
    cutoff = time.time() - RETENTION_DAYS * 86400
    return [it for it in items if it["t"] >= cutoff][:_MAX]


def add(text):
    text = (text or "").strip()
    if not text:
        return
    with _lock:
        _save(_prune([{"t": time.time(), "text": text}] + _load()))


def get():
    """Entradas vigentes, de la más nueva a la más vieja: [{"t": epoch, "text": str}]."""
    with _lock:
        items = _load()
        kept = _prune(items)
        if len(kept) != len(items):          # lo vencido se borra del disco, no solo se oculta
            _save(kept)
        return kept


def clear():
    with _lock:
        _save([])
