"""Overlay flotante 'grabando' — pastilla topmost, click-through, no roba foco.

Diseño moderno: barras con puntas redondeadas que reaccionan al espectro real de
tu voz (degradé cian→violeta), punto de grabación con leve pulso. El Tk root de
este overlay es el único root de tkinter (hilo principal); Ajustes es un Toplevel.
"""
import ctypes
import math
import tkinter as tk

_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_TOPMOST = 0x00000008
_WS_EX_NOACTIVATE = 0x08000000

_W, _H = 232, 56
_BG = "#0e0f16"
_CHROMA = "#010203"
_CYAN = (34, 211, 238)
_VIOLET = (167, 139, 250)
_NBARS = 14


def _hexlerp(t):
    r = int(_CYAN[0] + (_VIOLET[0] - _CYAN[0]) * t)
    g = int(_CYAN[1] + (_VIOLET[1] - _CYAN[1]) * t)
    b = int(_CYAN[2] + (_VIOLET[2] - _CYAN[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


_COLORS = [_hexlerp(i / (_NBARS - 1)) for i in range(_NBARS)]


class Overlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.0)
        self.root.config(bg=_CHROMA)
        try:
            self.root.attributes("-transparentcolor", _CHROMA)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.root, width=_W, height=_H, bg=_CHROMA, highlightthickness=0)
        self.canvas.pack()

        self._state = "hidden"
        self._visible = False
        self._frame = 0
        self._bars = [0.0] * _NBARS
        self.get_bands = None     # callable → lista de niveles por banda (0-1)

        self._place()
        self.root.deiconify()
        self.root.after(20, self._apply_exstyles)
        self.root.after(33, self._tick)

    def _apply_exstyles(self):
        try:
            u = ctypes.windll.user32
            hwnd = u.GetAncestor(self.root.winfo_id(), 2) or self.root.winfo_id()
            ex = u.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            ex |= _WS_EX_TRANSPARENT | _WS_EX_TOOLWINDOW | _WS_EX_TOPMOST | _WS_EX_NOACTIVATE
            u.SetWindowLongW(hwnd, _GWL_EXSTYLE, ex)
        except Exception:
            pass

    def _reassert(self):
        """Reaplica lo que Windows/DWM puede resetear tras suspender o apagar el
        monitor (topmost, color transparente, ex-styles). Sin esto el overlay deja
        de aparecer después de un resume aunque la app siga funcionando."""
        try:
            self.root.attributes("-topmost", True)
            self.root.attributes("-transparentcolor", _CHROMA)
        except tk.TclError:
            pass
        self._apply_exstyles()

    def _place(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{_W}x{_H}+{(sw - _W) // 2}+{sh - _H - 96}")

    def set_state(self, state):
        self._state = state

    def stop(self):
        self.root.after(0, self.root.quit)

    def run(self):
        self.root.mainloop()

    def _tick(self):
        want = self._state in ("recording", "processing")
        if want and not self._visible:
            self._place(); self._reassert(); self.root.attributes("-alpha", 0.98); self._visible = True
        elif not want and self._visible:
            self.root.attributes("-alpha", 0.0); self._visible = False
        if self._visible:
            self._frame += 1
            self._draw(self._state)
        self.root.after(33, self._tick)   # ~30fps

    def _draw(self, state):
        c = self.canvas
        c.delete("all")
        self._round_rect(2, 2, _W - 2, _H - 2, 24, fill=_BG)
        cy = _H // 2

        # punto de grabación con leve pulso
        pulse = (math.sin(self._frame * 0.18) + 1) / 2
        dot_c = "#ff5470" if state == "recording" else "#5aa0ff"
        rr = 4.5 + pulse * 1.8
        c.create_oval(26 - rr - 3, cy - rr - 3, 26 + rr + 3, cy + rr + 3,
                      fill="", outline=dot_c, width=1)             # halo
        c.create_oval(26 - rr, cy - rr, 26 + rr, cy + rr, fill=dot_c, outline="")

        if state == "recording":
            bands = None
            if self.get_bands:
                try:
                    bands = self.get_bands()
                except Exception:
                    bands = None
            x0 = 48
            for i in range(_NBARS):
                lvl = bands[i] if bands and i < len(bands) else 0.0
                self._bars[i] += (max(0.0, min(1.0, lvl)) - self._bars[i]) * 0.7
                h = 4 + self._bars[i] * 40                          # rango amplio = dinámico
                x = x0 + i * 12
                c.create_line(x, cy - h / 2, x, cy + h / 2, width=5,
                              fill=_COLORS[i], capstyle="round")
        else:  # processing
            for i in range(3):
                a = (math.sin(self._frame * 0.2 - i * 0.7) + 1) / 2
                rd = 3 + a * 3
                x = _W // 2 - 12 + i * 14
                c.create_oval(x - rd, cy - rd, x + rd, cy + rd, fill=_hexlerp(i / 2), outline="")

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)
