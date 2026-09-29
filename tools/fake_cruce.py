"""Cruce de mentira para probar Dos PCs sin la otra PC: sirve la API por named pipe
(state / send / subscribe) y lo que una conexión manda con "send" le llega a las OTRAS
conexiones suscriptas, como si fuera la otra PC.

    .venv\\Scripts\\python.exe tools\\fake_cruce.py [nombre del pipe]
"""
import ctypes
import json
import sys
import threading
from ctypes import wintypes

NAME = sys.argv[1] if len(sys.argv) > 1 else r"\\.\pipe\Cruce.Api"
_k = ctypes.WinDLL("kernel32", use_last_error=True)
_k.CreateNamedPipeW.restype = wintypes.HANDLE
_k.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
_k.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
_k.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_k.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_k.FlushFileBuffers.argtypes = [wintypes.HANDLE]
_k.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
_k.CloseHandle.argtypes = [wintypes.HANDLE]
INVALID = wintypes.HANDLE(-1).value

subs = {}           # handle → lock
subs_lock = threading.Lock()
sent = []           # registro para las pruebas


def write(h, obj):
    data = (json.dumps(obj) + "\n").encode("utf-8")
    n = wintypes.DWORD()
    return _k.WriteFile(h, data, len(data), ctypes.byref(n), None)


def lines(h):
    buf = b""
    chunk = ctypes.create_string_buffer(65536)
    n = wintypes.DWORD()
    while _k.ReadFile(h, chunk, 65536, ctypes.byref(n), None) and n.value:
        buf += chunk.raw[:n.value]
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line


def _drop(h):
    with subs_lock:
        subs.pop(h, None)
    _k.DisconnectNamedPipe(h)
    _k.CloseHandle(h)


def serve(h):
    try:
        for line in lines(h):
            req = json.loads(line)
            cmd = req.get("cmd")
            if cmd == "state":
                write(h, {"mode": "Local", "peer": "FAKE", "connected": True, "self": "TEST"})
            elif cmd == "send":
                sent.append(req.get("data"))
                with subs_lock:
                    targets = [s for s in subs if s != h]
                delivered = False
                for s in targets:
                    if write(s, {"from": "FAKE", "data": req.get("data")}):
                        delivered = True
                    else:
                        _drop(s)                  # el suscriptor se fue
                write(h, {"ok": True} if delivered else {"ok": False, "error": "peer desconectado"})
            elif cmd == "subscribe":
                # Desde acá solo se le escribe: un pipe sincrónico no puede leer y escribir el
                # mismo handle desde dos hilos (el WriteFile esperaría al ReadFile pendiente).
                with subs_lock:
                    subs[h] = True
                return
    except Exception:
        pass
    _drop(h)


def run():
    while True:
        h = _k.CreateNamedPipeW(NAME, 3, 0, 255, 65536, 65536, 0, None)   # DUPLEX, BYTE, ilimitadas
        if h == INVALID:
            raise OSError(ctypes.get_last_error(), "CreateNamedPipe")
        _k.ConnectNamedPipe(h, None)      # si ya estaba conectado (ERROR_PIPE_CONNECTED) igual sirve
        threading.Thread(target=serve, args=(h,), daemon=True).start()


if __name__ == "__main__":
    print(f"Cruce falso escuchando en {NAME}")
    run()
