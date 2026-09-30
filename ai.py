"""Modo IA: con el pedido dictado (y el texto que tenías seleccionado, si había) Gemini escribe el
texto final, que se pega en lugar del dictado. Solo corre en los dictados donde lo activás (tecla
del modo IA mientras grabás) y siempre en la PC principal. En inglés salvo que pidas otro idioma.

La clave de Gemini se guarda cifrada con DPAPI (solo tu usuario de Windows la puede leer) en
~/.dictado/gemini.key: nunca en prefs.json ni en el repo.
"""
import ctypes
import json
import urllib.error
import urllib.request
from ctypes import wintypes

from config import APP_DIR

MODEL = "gemini-3.8-flash"     # Flash (no Lite): medido ~2-4 s por pedido, buen texto en en/es
KEY_PATH = APP_DIR / "gemini.key"
SYSTEM = (
    "You write text that will be pasted directly where the user is typing (a chat, an email, a "
    "document, a prompt for another AI). Output ONLY the final text: no preface, no quotes, no "
    "explanations, no markdown unless the user asks for it. Write in English unless the user "
    "explicitly asks for another language, even if they dictate in Spanish. If SELECTED TEXT is "
    "given, apply the user's request to it and return the complete revised text. Keep names, facts "
    "and intent; don't invent details or leave placeholders unless unavoidable.")


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt = ctypes.WinDLL("crypt32")
_k32 = ctypes.WinDLL("kernel32")
_crypt.CryptProtectData.argtypes = [ctypes.POINTER(_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_BLOB),
                                    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_BLOB)]
_crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(_BLOB), ctypes.c_void_p, ctypes.POINTER(_BLOB),
                                      ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_BLOB)]
_k32.LocalFree.argtypes = [ctypes.c_void_p]


def _dpapi(data, protect):
    buf = ctypes.create_string_buffer(data, len(data))
    src, out = _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), _BLOB()
    fn = _crypt.CryptProtectData if protect else _crypt.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI falló")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        _k32.LocalFree(out.pbData)


def save_key(key):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_bytes(_dpapi(key.strip().encode("utf-8"), True))


def load_key():
    try:
        return _dpapi(KEY_PATH.read_bytes(), False).decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def available():
    return KEY_PATH.exists()


def generate(instruction, selected=None, timeout=45):
    """Texto final para pegar. Lanza RuntimeError con un mensaje para el usuario si falla."""
    key = load_key()
    if not key:
        raise RuntimeError("El modo IA no está configurado en esta PC.")
    user = f"USER REQUEST (dictated):\n{instruction}"
    if selected:
        user += f"\n\nSELECTED TEXT:\n{selected}"
    body = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}]}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(body).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"La IA respondió con un error ({e.code}).") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError("No se pudo llegar a la IA (¿sin internet?).") from e
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError("La IA no devolvió texto.") from e
    if not text:
        raise RuntimeError("La IA no devolvió texto.")
    return text
