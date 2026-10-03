"""Pega texto en el campo enfocado vía clipboard + Ctrl+V.

Diseño (por qué esta vez pega donde querés):
- Dictalo NO tiene overlay ni ninguna ventana que robe el foco, así que el campo
  donde estás escribiendo MANTIENE el foco durante todo el dictado.
- Al terminar, pega en la ventana que tiene el foco EN ESE MOMENTO (la tuya).
- Guarda: si por lo que sea el foreground es una ventana del propio Dictalo,
  NO pega (evita el bug de pegarse a sí mismo).
- Ctrl+V se manda con scan code real (KEYEVENTF) — las apps Chromium/Electron
  (Claude, Slack, navegador) ignoran teclas sintéticas sin scan code.

ctypes 64-bit: restype/argtypes explícitos en todo lo que devuelve HANDLE/puntero.
"""
import ctypes
import os
import threading
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
user32.SystemParametersInfoW.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetCurrentThreadId.argtypes = []

kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
user32.OpenClipboard.restype = wintypes.BOOL
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.CloseClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.GetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040
VK_CONTROL = 0x11
VK_V = 0x56
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
MAPVK_VK_TO_VSC = 0
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 0x0002
ULONG_PTR = ctypes.c_size_t
_OUR_PID = os.getpid()


def _disable_foreground_lock():
    """Permite que un proceso de fondo devuelva el foco a otra ventana."""
    try:
        user32.SystemParametersInfoW(SPI_SETFOREGROUNDLOCKTIMEOUT, 0, 0, SPIF_SENDCHANGE)
    except Exception:
        pass


_disable_foreground_lock()


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUT_UNION(ctypes.Union):
    # Incluir MOUSEINPUT (el miembro más grande) es OBLIGATORIO: hace que INPUT
    # mida los 40 bytes que SendInput espera en x64. Sin esto SendInput falla.
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("_u",)
    _fields_ = [("type", wintypes.DWORD), ("_u", _INPUT_UNION)]


user32.SendInput.restype = wintypes.UINT
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]


def _ki(vk, up=False):
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    return _INPUT(type=INPUT_KEYBOARD,
                  ki=_KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=KEYEVENTF_KEYUP if up else 0))


def _send_one(inp):
    arr = (_INPUT * 1)(inp)
    user32.SendInput(1, arr, ctypes.sizeof(_INPUT))


def _send_ctrl_v():
    _send_one(_ki(VK_CONTROL)); time.sleep(0.03)
    _send_one(_ki(VK_V));       time.sleep(0.03)
    _send_one(_ki(VK_V, up=True)); time.sleep(0.03)
    _send_one(_ki(VK_CONTROL, up=True))


_MODS = (0x10, 0x11, 0x12, 0x5B, 0x5C)    # Shift, Ctrl, Alt, Win izq/der
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


def wait_modifiers(timeout=2.0):
    """Para pegar desde un atajo (Alt+F1): espera a que sueltes Alt/Ctrl/Shift/Win, si no el
    Ctrl+V llegaría como Ctrl+Alt+V. Si Alt está apretado, antes manda una tecla "muda" (vkE8,
    sin uso en Windows) para que al soltar Alt la app no active su barra de menú."""
    if user32.GetAsyncKeyState(VK_MENU) & 0x8000:
        _send_one(_ki(0xE8)); _send_one(_ki(0xE8, up=True))
    end = time.monotonic() + timeout
    while time.monotonic() < end and any(user32.GetAsyncKeyState(k) & 0x8000 for k in _MODS):
        time.sleep(0.01)
    time.sleep(0.03)


def _open_clipboard():
    """OpenClipboard falla si otra app (historial de Windows, gestores de
    portapapeles, el navegador) lo tiene abierto en ese instante: reintentamos."""
    for _ in range(25):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def _clipboard_get():
    if not _open_clipboard():
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = kernel32.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    except Exception:
        return None
    finally:
        user32.CloseClipboard()


def _clipboard_set(text):
    data = text.encode("utf-16-le") + b"\x00\x00"
    hMem = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(data))
    if not hMem:
        return False
    p = kernel32.GlobalLock(hMem)
    if not p:
        return False
    ctypes.memmove(p, data, len(data))
    kernel32.GlobalUnlock(hMem)
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        return bool(user32.SetClipboardData(CF_UNICODETEXT, hMem))
    finally:
        user32.CloseClipboard()


user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
_TERMINALS = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty", "PuTTY", "VirtualConsoleClass"}


def copy_selection(timeout=0.5):
    """Texto seleccionado en la ventana en foco (para el modo IA): manda Ctrl+C con scan codes
    y, si el portapapeles cambió, lo lee y lo deja como estaba. "" si no había selección.
    En terminales NO se manda Ctrl+C (ahí corta el programa que está corriendo)."""
    fg = user32.GetForegroundWindow()
    if not fg or _is_ours(fg) or _class_name(fg) in _TERMINALS:
        return ""
    seq = user32.GetClipboardSequenceNumber()
    old = _clipboard_get()
    _send_one(_ki(VK_CONTROL)); time.sleep(0.02)
    _send_one(_ki(0x43)); time.sleep(0.02)                     # C
    _send_one(_ki(0x43, up=True)); time.sleep(0.02)
    _send_one(_ki(VK_CONTROL, up=True))
    end = time.time() + timeout
    while time.time() < end and user32.GetClipboardSequenceNumber() == seq:
        time.sleep(0.02)
    if user32.GetClipboardSequenceNumber() == seq:
        return ""                                               # no había nada seleccionado
    _clipboard_settle()             # algunas apps escriben en dos pasos: esperar a que terminen
    text = _clipboard_get() or ""
    if old is not None:
        for _ in range(4):          # devolver lo tuyo y verificar que ninguna escritura tardía lo pise
            _clipboard_set(old)
            mine = user32.GetClipboardSequenceNumber()
            time.sleep(0.15)
            if user32.GetClipboardSequenceNumber() == mine:
                break
    return text.strip()


def _clipboard_settle(quiet=0.12, limit=0.8):
    """Espera hasta que el portapapeles lleve `quiet` s sin cambiar (máximo `limit` s)."""
    last, t_last, end = user32.GetClipboardSequenceNumber(), time.time(), time.time() + limit
    while time.time() < end:
        cur = user32.GetClipboardSequenceNumber()
        if cur != last:
            last, t_last = cur, time.time()
        elif time.time() - t_last >= quiet:
            return
        time.sleep(0.02)


def _win_info(hwnd):
    title = ctypes.create_unicode_buffer(200)
    cls = ctypes.create_unicode_buffer(200)
    user32.GetWindowTextW(hwnd, title, 200)
    user32.GetClassNameW(hwnd, cls, 200)
    return f"'{title.value}' [{cls.value}]"


def _is_ours(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == _OUR_PID


_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(hwnd, buf, 128)
    return buf.value


def capture_foreground():
    """Ventana en foco AHORA. Devuelve 0 si es nuestra o si es el escritorio/barra
    de tareas (pegar ahí nunca es lo que querés)."""
    fg = user32.GetForegroundWindow()
    if not fg or _is_ours(fg) or _class_name(fg) in _SHELL_CLASSES:
        return 0
    return fg


def _focus_window(hwnd):
    """Devuelve el foco a hwnd (con foreground-lock desactivado + ALT-tap)."""
    if not hwnd or user32.GetForegroundWindow() == hwnd:
        return
    our = kernel32.GetCurrentThreadId()
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    try:
        if fg_thread and fg_thread != our:
            attached = bool(user32.AttachThreadInput(our, fg_thread, True))
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(our, fg_thread, False)


class Injector:
    def inject(self, text: str, target_hwnd=0, keep=False):
        """`keep`: el texto queda en el portapapeles (si no, vuelve lo que tenías copiado)."""
        if not text:
            return False
        # target_hwnd = la ventana donde estabas AL CORTAR (F9). Normalmente ya tiene
        # el foco y no se toca nada; solo se re-enfoca si cambió durante la
        # transcripción. Nunca a una ventana nuestra.
        if target_hwnd and not _is_ours(target_hwnd):
            _focus_window(target_hwnd)
            time.sleep(0.12)

        fg = user32.GetForegroundWindow()
        print(f"[inject] destino hwnd={fg} {_win_info(fg)}")
        if _is_ours(fg):
            print("[inject] ABORTADO: el foco quedó en una ventana de Dictalo")
            return False

        old = _clipboard_get()
        if not _clipboard_set(text):
            print("[inject] ABORTADO: no pude escribir el portapapeles (otra app lo tenía tomado)")
            return False
        time.sleep(0.05)
        _send_ctrl_v()                       # ← acá pega; inject() vuelve enseguida
        print(f"[inject] Ctrl+V enviado ({len(text)} chars)")
        # Restaurar el clipboard en 2do plano: NO bloquea el sonido/overlay de fin.
        # 1s de margen: algunas apps (Electron/navegador cargado) leen el pegado
        # tarde y, si restaurábamos antes, pegaban lo que tenías copiado.
        if old is not None and not keep:
            mine = user32.GetClipboardSequenceNumber()

            def _restore():
                time.sleep(1.0)
                # Si en ese segundo copiaste otra cosa (un link), es tuya: no se pisa con lo viejo.
                if user32.GetClipboardSequenceNumber() != mine:
                    print("[inject] copiaste otra cosa mientras tanto: no restauro el portapapeles")
                    return
                _clipboard_set(old)
            threading.Thread(target=_restore, daemon=True).start()
        return True
