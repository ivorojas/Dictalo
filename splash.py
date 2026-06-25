"""Splash de carga — tarjeta centrada con animación mientras carga el modelo.
Mismo estilo que el overlay. Se cierra solo cuando la app está lista."""
import ctypes
import math
import tkinter as tk

_CHROMA = "#010203"
_BG = "#0e0f16"
_CYAN = (34, 211, 238)
_VIOLET = (167, 139, 250)
_NB = 7


def _hexlerp(t):
    r = int(_CYAN[0] + (_VIOLET[0] - _CYAN[0]) * t)
    g = int(_CYAN[1] + (_VIOLET[1] - _CYAN[1]) * t)
    b = int(_CYAN[2] + (_VIOLET[2] - _CYAN[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


_COLORS = [_hexlerp(i / (_NB - 1)) for i in range(_NB)]


class Splash:
    def __init__(self, root, is_ready):
        self.root = root
        self.is_ready = is_ready
        self.W, self.H = 300, 150
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=_CHROMA)
        try:
            self.win.attributes("-transparentcolor", _CHROMA)
        except tk.TclError:
            pass
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.win.geometry(f"{self.W}x{self.H}+{(sw - self.W) // 2}+{(sh - self.H) // 2}")
        self.c = tk.Canvas(self.win, width=self.W, height=self.H, bg=_CHROMA, highlightthickness=0)
        self.c.pack()
        self._frame = 0
        self.win.after(20, self._noactivate)
        self.win.after(33, self._tick)

    def _noactivate(self):
        try:
            u = ctypes.windll.user32
            hwnd = u.GetAncestor(self.win.winfo_id(), 2) or self.win.winfo_id()
            ex = u.GetWindowLongW(hwnd, -20)
            u.SetWindowLongW(hwnd, -20, ex | 0x08000000 | 0x00000080)  # NOACTIVATE|TOOLWINDOW
        except Exception:
            pass

    def _tick(self):
        if self.is_ready():
            try:
                self.win.destroy()
            except Exception:
                pass
            return
        self._frame += 1
        self._draw()
        self.root.after(33, self._tick)

    def _draw(self):
        c = self.c
        c.delete("all")
        self._round_rect(4, 4, self.W - 4, self.H - 4, 22, fill=_BG)
        c.create_text(self.W // 2, 46, text="Dictalo", fill="#ffffff",
                      font=("Segoe UI Semibold", 18))
        c.create_text(self.W // 2, 72, text="Cargando modelo…", fill="#8b90a2",
                      font=("Segoe UI", 10))
        # barras con onda de carga (cian→violeta)
        cy = 110
        x0 = self.W // 2 - (_NB * 14) // 2 + 4
        for i in range(_NB):
            a = (math.sin(self._frame * 0.22 - i * 0.6) + 1) / 2
            h = 6 + a * 22
            x = x0 + i * 14
            c.create_line(x, cy - h / 2, x, cy + h / 2, width=6,
                          fill=_COLORS[i], capstyle="round")

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.c.create_polygon(pts, smooth=True, **kw)
