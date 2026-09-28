"""Atajo global para abrir Ajustes (con el historial arriba) desde cualquier app.

Usa RegisterHotKey, no un hook de teclado: Windows consume la combinación (no le
llega a la app en foco), no hay riesgo de que el hook se caiga por lentitud y, si
otra app ya la tiene registrada, RegisterHotKey falla y se puede avisar. Corre en
un hilo propio con su cola de mensajes; al llegar WM_HOTKEY llama al callback.
"""
import ctypes
import threading
from ctypes import wintypes

OPTIONS = [("Ctrl+F1", "ctrl+f1"), ("Alt+F1", "alt+f1"), ("Shift+F1", "shift+f1"),
           ("Ctrl+Shift+F1", "ctrl+shift+f1"), ("Ctrl+Alt+H", "ctrl+alt+h"), ("Ninguno", "none")]
_KEYS = {"ctrl+f1": (0x2, 0x70), "alt+f1": (0x1, 0x70), "shift+f1": (0x4, 0x70),
         "ctrl+shift+f1": (0x6, 0x70), "ctrl+alt+h": (0x3, 0x48)}   # (modificadores, tecla virtual)
_MOD_NOREPEAT, _WM_HOTKEY, _WM_QUIT, _WM_USER = 0x4000, 0x0312, 0x0012, 0x0400

_u32 = ctypes.WinDLL("user32")
_k32 = ctypes.WinDLL("kernel32")
_u32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_u32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_u32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_u32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                              wintypes.UINT, wintypes.UINT]
_u32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_k32.GetCurrentThreadId.restype = wintypes.DWORD


def label(key):
    return dict((v, t) for t, v in OPTIONS).get(key, key)


class GlobalHotkey:
    def __init__(self, on_press):
        self.on_press = on_press
        self._thread, self._tid = None, None

    def set(self, key):
        """Registra `key` (reemplaza la anterior). True si quedó activa; False si otra
        app ya la tiene; None si es "none"."""
        self.stop()
        if key not in _KEYS:
            return None
        result = {}
        ready = threading.Event()

        def run():
            msg = wintypes.MSG()
            _u32.PeekMessageW(ctypes.byref(msg), None, _WM_USER, _WM_USER, 0)   # crea la cola
            self._tid = _k32.GetCurrentThreadId()
            mod, vk = _KEYS[key]
            result["ok"] = bool(_u32.RegisterHotKey(None, 1, mod | _MOD_NOREPEAT, vk))
            ready.set()
            if not result["ok"]:
                return
            while _u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == _WM_HOTKEY:
                    try:
                        self.on_press()
                    except Exception as e:
                        print(f"[atajo] {e}")
            _u32.UnregisterHotKey(None, 1)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        ready.wait(2)
        return result.get("ok", False)

    def stop(self):
        if self._thread and self._thread.is_alive() and self._tid:
            _u32.PostThreadMessageW(self._tid, _WM_QUIT, 0, 0)
            self._thread.join(1)
        self._thread, self._tid = None, None
