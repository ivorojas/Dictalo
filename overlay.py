"""Ventanita flotante 'grabando': ventana en capas de Windows (transparencia por
píxel → sombra, cristal, resplandor, sin fondo), siempre arriba, atravesable por el
mouse y que NUNCA toma el foco (así el Ctrl+V cae en tu campo). Cada cuadro lo dibuja
looks.render() según el estilo elegido en Ajustes.

El Tk root de acá es el único root de tkinter (hilo principal, invisible): hospeda el
mainloop y las ventanas de Ajustes/Historial/splash como Toplevel. La ventana en capas
usa DefWindowProc como procedimiento (no hay callbacks de Python) y sus mensajes los
despacha el propio mainloop de Tk, que corre en el mismo hilo.
"""
import ctypes
import time
import tkinter as tk
from ctypes import wintypes

import numpy as np

import looks

_u32 = ctypes.WinDLL("user32")
_g32 = ctypes.WinDLL("gdi32")
_k32 = ctypes.WinDLL("kernel32")

WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOPMOST = 0x80000, 0x20, 0x8
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80, 0x08000000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
ULW_ALPHA, SPI_GETWORKAREA = 0x2, 0x30


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", ctypes.c_void_p), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


class _BIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class _BLEND(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


_k32.GetModuleHandleW.restype = wintypes.HMODULE
_k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_u32.RegisterClassExW.restype = wintypes.ATOM
_u32.RegisterClassExW.argtypes = [ctypes.POINTER(_WNDCLASSEXW)]
_u32.CreateWindowExW.restype = wintypes.HWND
_u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
_u32.DestroyWindow.argtypes = [wintypes.HWND]
_u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
_u32.UpdateLayeredWindow.restype = wintypes.BOOL
_u32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                     ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                     ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
                                     ctypes.POINTER(_BLEND), wintypes.DWORD]
_u32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
_g32.CreateCompatibleDC.restype = wintypes.HDC
_g32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_g32.CreateDIBSection.restype = wintypes.HBITMAP
_g32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                  ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
_g32.SelectObject.restype = wintypes.HGDIOBJ
_g32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_g32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_g32.DeleteDC.argtypes = [wintypes.HDC]


class LayeredWindow:
    """Ventana en capas: se le pasa una imagen RGBA y la muestra tal cual."""

    CLASS = "DictadoAppOverlay"

    def __init__(self):
        hinst = _k32.GetModuleHandleW(None)
        wc = _WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(_WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(_u32.DefWindowProcW, ctypes.c_void_p).value
        wc.hInstance = hinst
        wc.lpszClassName = self.CLASS
        _u32.RegisterClassExW(ctypes.byref(wc))          # si ya estaba registrada, sigue igual
        ex = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        self.hwnd = _u32.CreateWindowExW(ex, self.CLASS, "Dictado App", WS_POPUP, 0, 0, 1, 1,
                                         None, None, hinst, None)
        if not self.hwnd:
            raise OSError("no se pudo crear la ventanita flotante")
        self._dc = _g32.CreateCompatibleDC(None)
        self._bmp, self._bits, self._size = None, None, (0, 0)
        self.visible = False

    def _surface(self, w, h):
        if (w, h) == self._size:
            return
        if self._bmp:
            _g32.DeleteObject(self._bmp)
        bih = _BIH(ctypes.sizeof(_BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)   # 32bpp de arriba abajo
        bits = ctypes.c_void_p()
        self._bmp = _g32.CreateDIBSection(self._dc, ctypes.byref(bih), 0, ctypes.byref(bits), None, 0)
        _g32.SelectObject(self._dc, self._bmp)
        self._bits, self._size = bits, (w, h)

    def show(self, img, x, y):
        w, h = img.size
        self._surface(w, h)
        a = np.asarray(img, dtype=np.uint8)
        rgb = a[..., :3].astype(np.uint16) * a[..., 3:4] // 255       # alpha premultiplicado
        bgra = np.ascontiguousarray(np.dstack((rgb[..., 2], rgb[..., 1], rgb[..., 0], a[..., 3]))
                                    .astype(np.uint8))
        ctypes.memmove(self._bits, bgra.ctypes.data, bgra.nbytes)
        ok = _u32.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(wintypes.POINT(x, y)),
                                      ctypes.byref(wintypes.SIZE(w, h)), self._dc,
                                      ctypes.byref(wintypes.POINT(0, 0)), 0,
                                      ctypes.byref(_BLEND(0, 0, 255, 1)), ULW_ALPHA)
        if not self.visible:
            # topmost + mostrar SIN activar (nunca le saca el foco a tu ventana)
            _u32.SetWindowPos(self.hwnd, wintypes.HWND(-1), 0, 0, 0, 0,
                              SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
            self.visible = True
        return bool(ok)

    def hide(self):
        _u32.ShowWindow(self.hwnd, 0)
        self.visible = False

    def destroy(self):
        _u32.DestroyWindow(self.hwnd)
        if self._bmp:
            _g32.DeleteObject(self._bmp)
        _g32.DeleteDC(self._dc)


def _position(size, where):
    """Centrado en el área de trabajo (sin la barra de tareas), abajo o arriba."""
    wa = wintypes.RECT()
    _u32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(wa), 0)
    W, H = size
    x = (wa.left + wa.right - W) // 2
    if where == "top":
        return x, wa.top + 40 - looks.MARGIN
    return x, wa.bottom - 44 - (H - looks.MARGIN)


class Overlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.get_bands = None                   # callable → bandas del micrófono (0-1)
        self.get_style = lambda: looks.resolve({})
        self.get_intensity = lambda: looks.DEFAULT_INTENSITY   # exageración visual 0-1
        self._state = "hidden"
        self._bars = []
        self._t0 = time.perf_counter()
        self._last_err = None
        self._win = LayeredWindow()
        self.root.after(33, self._tick)

    def set_state(self, state):
        self._state = state

    def stop(self):
        self.root.after(0, self.root.quit)

    def run(self):
        self.root.mainloop()

    def _tick(self):
        try:
            if self._state in ("recording", "processing"):
                self._frame()
            elif self._win.visible:
                self._win.hide()
                self._bars = []
        except Exception as e:          # nunca cortar el loop de la ventanita
            if str(e) != self._last_err:
                self._last_err = str(e)
                print(f"[overlay] {e}")
        self.root.after(33, self._tick)   # ~30fps

    def _frame(self):
        s = self.get_style()
        n = s["bar_count"]
        if self._state == "recording" and self.get_bands:
            target = looks.exaggerate(looks.resample(self.get_bands(), n), self.get_intensity())
        else:
            target = [0.0] * n
        if len(self._bars) != n:
            self._bars = [0.0] * n
        self._bars = looks.follow(self._bars, target, s["speed"])
        img = looks.render(s, self._state, self._bars, time.perf_counter() - self._t0)
        self._win.show(img, *_position(img.size, s["position"]))
