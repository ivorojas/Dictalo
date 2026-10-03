"""Splash de carga: tarjeta centrada con el ícono y una onda animada mientras carga
el modelo. Mismo estilo que el overlay. Se cierra sola cuando la app está lista."""
import ctypes
import math
import tkinter as tk

from PIL import ImageTk

import ui
from brand import APP_NAME, make_icon

_CHROMA = "#010203"
_NB = 7
_COLORS = [ui.mix(ui.CYAN, ui.VIOLET, i / (_NB - 1)) for i in range(_NB)]


class Splash:
    W, H = 320, 184

    def __init__(self, root, is_ready, text="Cargando el modelo de voz…"):
        """`is_ready()`: se cierra cuando da True. `text`: texto o función que lo devuelve
        (se actualiza en cada cuadro, p. ej. una cuenta atrás)."""
        self.root = root
        self.is_ready = is_ready
        self.text = text
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
        c = self.c = tk.Canvas(self.win, width=self.W, height=self.H, bg=_CHROMA,
                               highlightthickness=0)
        c.pack()
        self._card = ui.shape(self.W - 8, self.H - 8, 22, fill="#0f1117", border=ui.BORDER_HI)
        self._logo = ImageTk.PhotoImage(make_icon(46))
        c.create_image(4, 4, image=self._card, anchor="nw")
        c.create_image(self.W // 2, 52, image=self._logo)
        c.create_text(self.W // 2, 101, text=APP_NAME, fill=ui.TEXT, font=ui.F.h1)
        self._text = c.create_text(self.W // 2, 124, text=self._now_text(), fill=ui.TEXT_2,
                                   font=ui.F.small)
        self._bars = [c.create_line(0, 0, 0, 0, width=5, fill=col, capstyle="round")
                      for col in _COLORS]
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

    def _now_text(self):
        return self.text() if callable(self.text) else self.text

    def _tick(self):
        if self.is_ready():
            try:
                self.win.destroy()
            except Exception:
                pass
            return
        self._frame += 1
        if callable(self.text):
            self.c.itemconfigure(self._text, text=self._now_text())
        cy, x0 = 156, self.W // 2 - (_NB - 1) * 7
        for i, bar in enumerate(self._bars):
            a = (math.sin(self._frame * 0.22 - i * 0.6) + 1) / 2
            h = 5 + a * 16
            x = x0 + i * 14
            self.c.coords(bar, x, cy - h / 2, x, cy + h / 2)
        self.root.after(33, self._tick)
