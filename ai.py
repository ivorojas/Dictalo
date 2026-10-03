"""Modo IA: con el pedido dictado (y el texto que tenías seleccionado, si había) Gemini escribe el
texto final, que se pega en lugar del dictado. Solo corre en los dictados donde lo activás (tecla
del modo IA mientras grabás) y siempre en la PC principal. En inglés salvo que pidas otro idioma.

La clave de Gemini se guarda cifrada con DPAPI (solo tu usuario de Windows la puede leer) en
~/.dictado/gemini.key: nunca en prefs.json ni en el repo.
"""
import ctypes
import json
import re
import urllib.error
import urllib.request
from ctypes import wintypes

from config import APP_DIR

MODEL = "gemini-3.1-flash-lite"   # por defecto: el más barato que sigue disponible y tan rápido como el que más (~1.5 s)
# Elegibles en Ajustes (config.ai_model). Si uno deja de existir en la API, se avisa al usarlo.
MODELS = [("3.1 Flash Lite", "gemini-3.1-flash-lite"), ("3.5 Flash Lite", "gemini-3.5-flash-lite"),
          ("3.5 Flash", "gemini-3.5-flash"), ("3.8 Flash", "gemini-3.8-flash"),
          ("2.5 Flash", "gemini-2.5-flash")]
# Lo lento era que el modelo "piensa" antes de escribir (300-500 tokens: 3.8 Flash ~3 s → ~1.7 s sin
# pensar; 3.5 Flash ~3.3 → ~1.3; 2.5 Flash ~1.8 → ~0.9). Para redactar un mensaje no hace falta: se
# pide lo mínimo que acepta cada modelo (los Lite ya no piensan). Medido el 2026-10-03.
_THINK = {"gemini-3.8-flash": {"thinkingLevel": "low"}, "gemini-3.5-flash": {"thinkingBudget": 0},
          "gemini-2.5-flash": {"thinkingBudget": 0}}
KEY_PATH = APP_DIR / "gemini.key"
SYSTEM = (
    "You write text that will be pasted directly where the user is typing (a chat, an email, a "
    "document, a prompt for another AI). Output ONLY the final text: no preface, no quotes, no "
    "explanations, no markdown unless the user asks for it. Write in English unless the user "
    "explicitly asks for another language, even if they dictate in Spanish. If SELECTED TEXT is "
    "given, apply the user's request to it and return the complete revised text. Keep names, facts "
    "and intent; don't invent details or leave placeholders unless unavoidable. Never use em dashes "
    "or en dashes; use commas, periods or parentheses instead.")
_DASH = re.compile(r"\s*[—–]\s*")       # raya y semiraya: el dueño no las quiere nunca


_RANGE = re.compile(r"(\d)\s*[—–]\s*(\d)")


def _no_dashes(text):
    """Por si el modelo igual las pone: "a—b" / "a — b" → "a, b"; entre números ("3–5") → "3-5"."""
    return _DASH.sub(", ", _RANGE.sub(r"\1-\2", text)).replace(" ,", ",")


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


def generate(instruction, selected=None, model=None, timeout=45):
    """Texto final para pegar. Lanza RuntimeError con un mensaje para el usuario si falla."""
    model = model or MODEL
    key = load_key()
    if not key:
        raise RuntimeError("El modo IA no está configurado en esta PC.")
    user = f"USER REQUEST (dictated):\n{instruction}"
    if selected:
        user += f"\n\nSELECTED TEXT:\n{selected}"
    body = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}]}
    if model in _THINK:
        body["generationConfig"] = {"thinkingConfig": _THINK[model]}

    def ask():
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(body).encode("utf-8"),
            headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    try:
        try:
            data = ask()
        except urllib.error.HTTPError as e:
            if e.code != 400 or "generationConfig" not in body:
                raise
            del body["generationConfig"]      # Google cambió qué acepta ese modelo: sin el ajuste
            data = ask()
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f"El modelo {model} ya no está disponible: elegí otro en Ajustes.") from e
        raise RuntimeError(f"La IA respondió con un error ({e.code}).") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError("No se pudo llegar a la IA (¿sin internet?).") from e
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError("La IA no devolvió texto.") from e
    if not text:
        raise RuntimeError("La IA no devolvió texto.")
    return _no_dashes(text)
