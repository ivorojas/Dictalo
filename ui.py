"""Kit de interfaz de Dictado App (tkinter).

Tk no suaviza bordes: las formas redondeadas (tarjetas, botones, chips, campos) se
renderizan con PIL a 4× y se muestran como imágenes → bordes suaves de verdad.
Tipografía Segoe UI Variable e íconos Segoe Fluent Icons (los de Windows 11), con
fallback a Segoe UI / Segoe MDL2 Assets en Windows 10.

Usa su propia instancia de user32/dwmapi para no pisar los prototipos ctypes que
injector.py define sobre ctypes.windll.user32.
"""
import ctypes
import json
import time
import tkinter as tk
import tkinter.font as tkfont
from ctypes import wintypes

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

import looks

# ── Paleta (misma identidad que el overlay: fondo casi negro + cian→violeta) ──
BG = "#0c0e13"
SURFACE = "#14171f"
FIELD = "#1c2029"
FIELD_HI = "#262b38"
BORDER = "#222634"
BORDER_HI = "#363d52"
TEXT = "#eceef5"
TEXT_2 = "#a3a9bd"
TEXT_3 = "#6b7189"
CYAN = "#22d3ee"
VIOLET = "#a78bfa"
ACCENT = "#b3a7ff"
SUCCESS = "#34d399"
WARN = "#fbbf24"
DANGER = "#f87171"
DANGER_BG = "#2b171c"

# ── Íconos (Segoe Fluent Icons / MDL2 Assets) ──
I_COPY, I_CHECK = "", ""
I_DOWN, I_UP, I_RIGHT = "", "", ""
I_MIC, I_ADD, I_CLOSE = "", "", ""
I_SEARCH, I_DELETE, I_HISTORY = "", "", ""
I_MIN, I_MAX, I_X = "", "", ""


class _Fonts:
    root = None


F = _Fonts()


def init(root):
    """Crea las fuentes (necesitan un Tk vivo) y el ruteo de la rueda del mouse."""
    if F.root is root:
        return
    fams = set(tkfont.families(root))

    def pick(*cands):
        return next((c for c in cands if c in fams), cands[-1])

    disp = pick("Segoe UI Variable Display Semib", "Segoe UI Semibold")
    text = pick("Segoe UI Variable Text", "Segoe UI")
    text_sb = pick("Segoe UI Variable Text Semibold", "Segoe UI Semibold")
    icons = pick("Segoe Fluent Icons", "Segoe MDL2 Assets")

    def mk(fam, px):
        return tkfont.Font(root=root, family=fam, size=-px)

    F.title, F.h1 = mk(disp, 22), mk(disp, 19)
    F.h2 = mk(text_sb, 14)
    F.body, F.body_sb = mk(text, 13), mk(text_sb, 13)
    F.small, F.small_sb = mk(text, 12), mk(text_sb, 12)
    F.tiny = mk(text, 11)
    F.icon, F.icon_sm, F.icon_lg = mk(icons, 15), mk(icons, 12), mk(icons, 34)
    F.root = root
    root.bind_all("<MouseWheel>", _on_wheel, add="+")


# ── Formas anti-aliased ──────────────────────────────────────────────────────
_SS = 4
_photos = {}


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def mix(c1, c2, t):
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _lum(c):
    r, g, b = _rgb(c)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def _render(w, h, r, fill, border, grad, bw):
    W, H = w * _SS, h * _SS
    R = min(r * _SS, (W - 1) // 2, (H - 1) // 2)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    inset = 0
    if border:
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill=_rgb(border) + (255,))
        inset = bw * _SS
    box = [inset, inset, W - 1 - inset, H - 1 - inset]
    rin = max(0, R - inset)
    if grad:
        t = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
        a, b = np.array(_rgb(grad[0]), np.float32), np.array(_rgb(grad[1]), np.float32)
        row = (a * (1 - t) + b * t).round().astype(np.uint8)
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle(box, radius=rin, fill=255)
        img.paste(Image.fromarray(np.repeat(row, H, axis=0), "RGB"), (0, 0), mask)
    elif fill:
        d.rounded_rectangle(box, radius=rin, fill=_rgb(fill) + (255,))
    return img.resize((w, h), Image.LANCZOS)


def shape(w, h, r, fill=None, border=None, grad=None, bw=1):
    """PhotoImage de un rectángulo redondeado suave. Cacheado: cada widget guarda
    su propia referencia, así vaciar el caché nunca borra una imagen en pantalla."""
    w, h = max(2, int(w)), max(2, int(h))
    key = (w, h, r, fill, border, grad, bw)
    ph = _photos.get(key)
    if ph is None:
        if len(_photos) > 600:
            _photos.clear()
        ph = _photos[key] = ImageTk.PhotoImage(_render(w, h, r, fill, border, grad, bw))
    return ph


def ellipsize(text, font, max_px):
    text = " ".join(text.split())
    if font.measure(text) <= max_px:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid].rstrip() + "…") <= max_px:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def label(parent, text="", font=None, fg=TEXT, bg=SURFACE, **kw):
    kw.setdefault("anchor", "w")
    kw.setdefault("justify", "left")
    return tk.Label(parent, text=text, font=font or F.body, fg=fg, bg=bg, bd=0,
                    padx=0, pady=0, **kw)


def separator(parent, bg=BORDER):
    return tk.Frame(parent, height=1, bg=bg)


# ── Componentes ──────────────────────────────────────────────────────────────
class Card(tk.Canvas):
    """Tarjeta redondeada. El contenido va en `.body`; la altura sigue al contenido."""

    def __init__(self, parent, bg=BG, fill=SURFACE, border=BORDER, radius=14, padx=18, pady=16):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, height=2 * pady + 2)
        self.fill, self.border, self.radius, self.padx, self.pady = fill, border, radius, padx, pady
        self.body = tk.Frame(self, bg=fill)
        self._bgid = self.create_image(0, 0, anchor="nw")
        self._win = self.create_window(padx, pady, window=self.body, anchor="nw")
        self._img = None
        self.bind("<Configure>", self._on_canvas)
        self.body.bind("<Configure>", self._on_body)

    def _on_canvas(self, e):
        self.itemconfigure(self._win, width=max(1, e.width - 2 * self.padx))
        self._paint(e.width, int(self["height"]))

    def _on_body(self, e):
        h = e.height + 2 * self.pady
        if int(self["height"]) != h:
            self.configure(height=h)
        self._paint(self.winfo_width(), h)

    def _paint(self, w, h):
        if w > 2 and h > 2:
            self._img = shape(w, h, self.radius, fill=self.fill, border=self.border)
            self.itemconfigure(self._bgid, image=self._img)


#          relleno     hover       texto    texto hover  degradé
_KINDS = {
    "primary": (None, None, BG, BG, (CYAN, VIOLET)),
    "secondary": (FIELD, FIELD_HI, TEXT, TEXT, None),
    "ghost": (None, FIELD, TEXT_2, TEXT, None),
    "link": (None, None, ACCENT, TEXT, None),
    "danger": (None, DANGER_BG, DANGER, DANGER, None),
    "danger_solid": ("#d9424a", "#e8545b", "#ffffff", "#ffffff", None),
    "chip": (FIELD, FIELD_HI, TEXT_2, TEXT, None),
    "chip_on": (None, None, BG, BG, (CYAN, VIOLET)),
}


class Button(tk.Canvas):
    def __init__(self, parent, text="", command=None, kind="secondary", icon=None, bg=SURFACE,
                 height=34, padx=14, radius=9, font=None, icon_right=False):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.icon, self.command, self.kind = text, icon, command, kind
        self._font, self._ifont = font or F.body_sb, F.icon_sm
        self._h, self._padx, self._r, self._icon_right = height, padx, radius, icon_right
        self._hover = False
        self._img = None
        self._bgid = self.create_image(0, 0, anchor="nw")
        self._ic = self.create_text(0, 0, anchor="w", font=self._ifont)
        self._tx = self.create_text(0, 0, anchor="w", font=self._font)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self.update_content()

    def update_content(self, text=None, icon=None, kind=None):
        if text is not None:
            self.text = text
        if icon is not None:
            self.icon = icon or None
        if kind is not None:
            self.kind = kind
        tw = self._font.measure(self.text) if self.text else 0
        iw = self._ifont.measure(self.icon) if self.icon else 0
        gap = 7 if (self.text and self.icon) else 0
        self.W =tw + iw + gap + 2 * self._padx
        self.configure(width=self.W)
        mid = self._h / 2
        if self._icon_right:
            self.coords(self._tx, self._padx, mid)
            self.coords(self._ic, self._padx + tw + gap, mid + 1)
        else:
            self.coords(self._ic, self._padx, mid + 1)
            self.coords(self._tx, self._padx + iw + gap, mid)
        self.itemconfigure(self._ic, text=self.icon or "")
        self.itemconfigure(self._tx, text=self.text)
        self._paint()

    def _paint(self):
        fill, hover, fg, fg_h, grad = _KINDS[self.kind]
        on = self._hover
        f = hover if (on and hover) else fill
        g = grad
        if grad and on:
            g = (mix(grad[0], "#ffffff", 0.14), mix(grad[1], "#ffffff", 0.14))
        if f or g:
            self._img = shape(self.W, self._h, self._r, fill=f, grad=g)
            self.itemconfigure(self._bgid, image=self._img, state="normal")
        else:
            self.itemconfigure(self._bgid, state="hidden")
        col = fg_h if on else fg
        self.itemconfigure(self._tx, fill=col)
        self.itemconfigure(self._ic, fill=col)

    def _set_hover(self, v):
        self._hover = v
        self._paint()

    def _click(self, e):
        if 0 <= e.x <= self.W and 0 <= e.y <= self._h and self.command:
            self.command()


class IconButton(tk.Canvas):
    """Botón de ícono (cuadrado redondeado que aparece al pasar el mouse)."""

    def __init__(self, parent, icon, command=None, bg=SURFACE, size=32, color=TEXT_3,
                 hover_color=TEXT, hover_fill=FIELD_HI):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.icon, self.command = icon, command
        self._s, self._c, self._hc, self._hf = size, color, hover_color, hover_fill
        self._img = shape(size, size, 8, fill=hover_fill)
        self._bgid = self.create_image(0, 0, anchor="nw", image=self._img, state="hidden")
        self._ic = self.create_text(size / 2, size / 2 + 1, text=icon, font=F.icon, fill=color)
        self._flash_job = None
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonRelease-1>", self._click)

    def _hover(self, on):
        self.itemconfigure(self._bgid, state="normal" if on else "hidden")
        if not self._flash_job:
            self.itemconfigure(self._ic, fill=self._hc if on else self._c)

    def _click(self, e):
        if 0 <= e.x <= self._s and 0 <= e.y <= self._s and self.command:
            self.command()

    def flash(self, icon=I_CHECK, color=SUCCESS, ms=1400):
        """Muestra otro ícono un momento (p.ej. ✓ después de copiar)."""
        if self._flash_job:
            self.after_cancel(self._flash_job)
        self.itemconfigure(self._ic, text=icon, fill=color)

        def back():
            self._flash_job = None
            if self.winfo_exists():
                self.itemconfigure(self._ic, text=self.icon, fill=self._c)
        self._flash_job = self.after(ms, back)


class Tag(tk.Canvas):
    """Etiqueta con ✕ para quitarla (vocabulario)."""

    H = 30

    def __init__(self, parent, text, on_remove, bg=SURFACE):
        self.text, self.on_remove = text, on_remove
        tw = F.small.measure(text)
        self.W =12 + tw + 30
        super().__init__(parent, width=self.W, height=self.H, bg=bg, highlightthickness=0, bd=0)
        self._img_n = shape(self.W, self.H, 15, fill=FIELD, border=BORDER)
        self._img_h = shape(self.W, self.H, 15, fill=FIELD, border=BORDER_HI)
        self._xbg = shape(20, 20, 10, fill=FIELD_HI)
        self._bgid = self.create_image(0, 0, anchor="nw", image=self._img_n)
        self.create_text(12, self.H / 2, text=text, font=F.small, fill=TEXT, anchor="w")
        cx = self.W - 16
        self._xb = self.create_image(cx, self.H / 2, image=self._xbg, state="hidden")
        self._x = self.create_text(cx, self.H / 2 + 1, text=I_CLOSE, font=F.icon_sm, fill=TEXT_3)
        self.bind("<Enter>", lambda e: self.itemconfigure(self._bgid, image=self._img_h))
        self.bind("<Leave>", lambda e: self._leave())
        self.bind("<Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._click)

    def _on_x(self, x):
        return x >= self.W - 28

    def _motion(self, e):
        on = self._on_x(e.x)
        self.itemconfigure(self._xb, state="normal" if on else "hidden")
        self.itemconfigure(self._x, fill=TEXT if on else TEXT_3)
        self.configure(cursor="hand2" if on else "")

    def _leave(self):
        self.itemconfigure(self._bgid, image=self._img_n)
        self.itemconfigure(self._xb, state="hidden")
        self.itemconfigure(self._x, fill=TEXT_3)

    def _click(self, e):
        if self._on_x(e.x) and 0 <= e.y <= self.H:
            self.on_remove(self.text)


class TagCloud(tk.Frame):
    """Etiquetas en filas que se acomodan al ancho. Colapsada muestra `max_rows`
    filas con un "Ver N más" al final; expandida muestra todo + "Ocultar"."""

    def __init__(self, parent, on_remove, bg=SURFACE, max_rows=2, gap=6):
        super().__init__(parent, bg=bg, height=1)
        self.on_remove, self.max_rows, self.gap = on_remove, max_rows, gap
        self.expanded = False
        self.tags = []
        self.toggle = Button(self, "", command=self._toggle, kind="link", bg=bg, height=Tag.H,
                             padx=8, font=F.small_sb, icon_right=True)
        self.bind("<Configure>", lambda e: self._layout())

    def set_terms(self, terms):
        for t in self.tags:
            t.destroy()
        self.tags = [Tag(self, t, self.on_remove, bg=self["bg"]) for t in terms]
        self._layout()

    def _toggle(self):
        self.expanded = not self.expanded
        self._layout()

    def _rows(self, W):
        pos, x, row = [], 0, 0
        for t in self.tags:
            w = int(t["width"])
            if x and x + w > W:
                x, row = 0, row + 1
            pos.append([t, x, row])
            x += w + self.gap
        return pos

    def _layout(self):
        W = self.winfo_width()
        if W <= 1:
            return
        g, H = self.gap, Tag.H
        pos = self._rows(W)
        for t in self.tags:
            t.place_forget()
        self.toggle.place_forget()
        overflows = bool(pos) and pos[-1][2] >= self.max_rows
        if overflows and not self.expanded:
            visible = [p for p in pos if p[2] < self.max_rows]
            for _ in range(3):   # el ancho del botón depende de cuántas quedan ocultas
                self.toggle.update_content(text=f"Ver {len(pos) - len(visible)} más", icon=I_DOWN)
                while visible:
                    last = [p for p in visible if p[2] == self.max_rows - 1]
                    end = last[-1][1] + int(last[-1][0]["width"]) + g if last else 0
                    if end + int(self.toggle["width"]) <= W:
                        break
                    visible.pop()
            for t, x, row in visible:
                t.place(x=x, y=row * (H + g))
            last = [p for p in visible if p[2] == self.max_rows - 1]
            end = last[-1][1] + int(last[-1][0]["width"]) + g if last else 0
            self.toggle.place(x=end, y=(self.max_rows - 1) * (H + g))
            rows = self.max_rows
        else:
            for t, x, row in pos:
                t.place(x=x, y=row * (H + g))
            rows = (pos[-1][2] + 1) if pos else 0
            if overflows:
                self.toggle.update_content(text="Ocultar", icon=I_UP)
                end = pos[-1][1] + int(pos[-1][0]["width"]) + g
                if end + int(self.toggle["width"]) > W:
                    end, rows = 0, rows + 1
                self.toggle.place(x=end, y=(rows - 1) * (H + g))
        h = max(1, rows * H + max(0, rows - 1) * g)
        if int(self["height"]) != h:
            self.configure(height=h)


class Field(tk.Canvas):
    """Campo de texto redondeado con ícono, placeholder y acción opcional."""

    def __init__(self, parent, placeholder="", icon=None, on_submit=None, on_change=None,
                 bg=SURFACE, height=40, action_icon=None):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0, cursor="xterm")
        self.placeholder, self.on_submit, self.on_change = placeholder, on_submit, on_change
        self._h, self._focus = height, False
        self._img = None
        self._bgid = self.create_image(0, 0, anchor="nw")
        x = 14
        if icon:
            self.create_text(x, height / 2 + 1, text=icon, font=F.icon, fill=TEXT_3, anchor="w")
            x += F.icon.measure(icon) + 10
        self._x0 = x
        self.entry = tk.Entry(self, bd=0, relief="flat", bg=FIELD, fg=TEXT_3, font=F.body,
                              insertbackground=TEXT, highlightthickness=0, insertwidth=1,
                              selectbackground=mix(VIOLET, FIELD, 0.55), selectforeground=TEXT)
        self._ew = self.create_window(x, height / 2, window=self.entry, anchor="w")
        self.action = None
        if action_icon:
            self.action = IconButton(self, action_icon, command=self._submit, bg=FIELD, size=30,
                                     color=TEXT_2)
            self._aw = self.create_window(0, height / 2, window=self.action, anchor="e")
        self._ph = True
        self.entry.insert(0, placeholder)
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self.entry.bind("<Return>", lambda e: self._submit())
        self.entry.bind("<KeyRelease>", lambda e: self.on_change and self.on_change(self.value()))
        self.bind("<Configure>", self._resize)
        self.bind("<Button-1>", lambda e: self.entry.focus_set())

    def value(self):
        return "" if self._ph else self.entry.get()

    def clear(self):
        self.entry.delete(0, "end")
        if not self._focus:
            self._show_placeholder()

    def _show_placeholder(self):
        self._ph = True
        self.entry.delete(0, "end")
        self.entry.insert(0, self.placeholder)
        self.entry.configure(fg=TEXT_3)

    def _focus_in(self, e):
        self._focus = True
        if self._ph:
            self._ph = False
            self.entry.delete(0, "end")
            self.entry.configure(fg=TEXT)
        self._paint()

    def _focus_out(self, e):
        self._focus = False
        if not self.entry.get():
            self._show_placeholder()
        self._paint()

    def _submit(self):
        if self.on_submit and self.value().strip():
            self.on_submit(self.value())

    def _resize(self, e):
        right = 6 + (30 if self.action else 8)
        self.itemconfigure(self._ew, width=max(20, e.width - self._x0 - right))
        if self.action:
            self.coords(self._aw, e.width - 6, self._h / 2)
        self._paint()

    def _paint(self):
        w = self.winfo_width()
        if w > 2:
            border = mix(ACCENT, FIELD, 0.35) if self._focus else BORDER
            self._img = shape(w, self._h, 10, fill=FIELD, border=border)
            self.itemconfigure(self._bgid, image=self._img)


class Select(tk.Frame):
    """Selector: un campo que despliega sus opciones debajo, dentro de la ventana."""

    ROW = 36

    def __init__(self, parent, options, value, on_change, icon=None, bg=SURFACE):
        super().__init__(parent, bg=bg)
        self.options, self.value, self.on_change, self.icon = options, value, on_change, icon
        self._bg, self._open, self._hover = bg, False, False
        self._img = None
        self.head = tk.Canvas(self, height=42, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.head.pack(fill="x")
        self._hbg = self.head.create_image(0, 0, anchor="nw")
        self._hic = self.head.create_text(14, 22, text=icon or "", font=F.icon, fill=TEXT_2,
                                          anchor="w")
        self._htx = self.head.create_text(0, 21, font=F.body, fill=TEXT, anchor="w")
        self._hch = self.head.create_text(0, 22, font=F.icon_sm, fill=TEXT_2, anchor="e")
        self.head.bind("<Configure>", lambda e: self._paint_head())
        self.head.bind("<Enter>", lambda e: self._set_hover(True))
        self.head.bind("<Leave>", lambda e: self._set_hover(False))
        self.head.bind("<ButtonRelease-1>", lambda e: self.toggle())
        self.panel = None

    def _label(self):
        for text, v in self.options:
            if v == self.value:
                return text
        return f"Dispositivo {self.value} (no disponible)"

    def _set_hover(self, on):
        self._hover = on
        self._paint_head()

    def _paint_head(self):
        w = self.head.winfo_width()
        if w <= 2:
            return
        border = mix(ACCENT, FIELD, 0.35) if self._open else (BORDER_HI if self._hover else BORDER)
        self._img = shape(w, 42, 10, fill=FIELD, border=border)
        self.head.itemconfigure(self._hbg, image=self._img)
        x = 14 + (F.icon.measure(self.icon) + 10 if self.icon else 0)
        self.head.coords(self._htx, x, 21)
        self.head.itemconfigure(self._htx, text=ellipsize(self._label(), F.body, w - x - 44))
        self.head.coords(self._hch, w - 14, 22)
        self.head.itemconfigure(self._hch, text=I_UP if self._open else I_DOWN)

    def toggle(self):
        self._open = not self._open
        if self._open:
            self.panel = Card(self, bg=self._bg, fill=FIELD, border=BORDER, radius=10,
                              padx=5, pady=5)
            self.panel.pack(fill="x", pady=(6, 0))
            for text, v in self.options:
                self._row(self.panel.body, text, v)
        elif self.panel:
            self.panel.destroy()
            self.panel = None
        self._paint_head()

    def _row(self, parent, text, v):
        c = tk.Canvas(parent, height=self.ROW, bg=FIELD, highlightthickness=0, bd=0, cursor="hand2")
        c.pack(fill="x")
        sel = v == self.value
        bgid = c.create_image(0, 0, anchor="nw", state="hidden")
        tx = c.create_text(12, self.ROW / 2, font=F.body_sb if sel else F.body,
                           fill=TEXT if sel else TEXT_2, anchor="w")
        ck = c.create_text(0, self.ROW / 2 + 1, text=I_CHECK if sel else "", font=F.icon_sm,
                           fill=ACCENT, anchor="e")

        def paint(e=None):
            w = c.winfo_width()
            if w > 2:
                c._img = shape(w, self.ROW, 7, fill=FIELD_HI)
                c.itemconfigure(bgid, image=c._img)
                c.itemconfigure(tx, text=ellipsize(text, F.body, w - 44))
                c.coords(ck, w - 12, self.ROW / 2 + 1)

        def pick(e):
            if 0 <= e.x <= c.winfo_width() and 0 <= e.y <= self.ROW:
                self.value = v
                self.toggle()
                self.on_change(v)

        c.bind("<Configure>", paint)
        c.bind("<Enter>", lambda e: c.itemconfigure(bgid, state="normal"))
        c.bind("<Leave>", lambda e: c.itemconfigure(bgid, state="hidden"))
        c.bind("<ButtonRelease-1>", pick)


class Pill(tk.Canvas):
    """Pastilla de estado: punto de color + texto."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, height=28, bg=bg, highlightthickness=0, bd=0)
        self._img = None
        self._bgid = self.create_image(0, 0, anchor="nw")
        self._dot = self.create_oval(0, 0, 0, 0, width=0)
        self._tx = self.create_text(0, 14, font=F.small_sb, anchor="w")

    def set(self, text, color):
        w = F.small_sb.measure(text) + 34
        self.configure(width=w)
        self._img = shape(w, 28, 14, fill=SURFACE, border=BORDER)
        self.itemconfigure(self._bgid, image=self._img)
        self.coords(self._dot, 12, 11, 18, 17)
        self.itemconfigure(self._dot, fill=color)
        self.coords(self._tx, 24, 14)
        self.itemconfigure(self._tx, text=text, fill=TEXT_2)


class Flow(tk.Frame):
    """Acomoda sus hijos en filas según el ancho disponible (como palabras)."""

    def __init__(self, parent, bg=SURFACE, gap=6, gapy=6):
        super().__init__(parent, bg=bg, height=1)
        self.gap, self.gapy = gap, gapy
        self.items = []
        self.bind("<Configure>", lambda e: self._flow())

    def put(self, w):
        self.items.append(w)
        self._flow()
        return w

    def clear(self):
        for w in self.items:
            w.destroy()
        self.items = []

    def _flow(self):
        W = self.winfo_width()
        if W <= 1:
            return
        x = y = rowh = 0
        for w in self.items:
            ww, wh = w.winfo_reqwidth(), w.winfo_reqheight()
            if x and x + ww > W:
                x, y, rowh = 0, y + rowh + self.gapy, 0
            w.place(x=x, y=y)
            x += ww + self.gap
            rowh = max(rowh, wh)
        h = max(1, y + rowh)
        if int(self["height"]) != h:
            self.configure(height=h)


class _Choice:
    """Opciones excluyentes como chips; la elegida lleva el degradé de la marca."""

    def _chips(self, options, value, on_change, bg, height, place):
        self.value, self.on_change = value, on_change
        self._btns = {}
        for text, v in options:
            b = Button(self, text, kind="chip_on" if v == value else "chip", bg=bg, height=height,
                       padx=13, radius=height // 2, font=F.small_sb,
                       command=lambda v=v: self._pick(v))
            self._btns[v] = b
            place(b)

    def _pick(self, v):
        if v != self.value:
            self.set(v)
            self.on_change(v)

    def set(self, v):
        old, new = self._btns.get(self.value), self._btns.get(v)
        if old:
            old.update_content(kind="chip")
        self.value = v
        if new:
            new.update_content(kind="chip_on")


class ChipGroup(Flow, _Choice):
    """Chips que se acomodan en varias filas si no entran."""

    def __init__(self, parent, options, value, on_change, bg=SURFACE, height=32):
        Flow.__init__(self, parent, bg=bg)
        self._chips(options, value, on_change, bg, height, self.put)


class Segmented(tk.Frame, _Choice):
    """Chips en una sola fila (pestañas, conmutadores)."""

    def __init__(self, parent, options, value, on_change, bg=SURFACE, height=32):
        tk.Frame.__init__(self, parent, bg=bg)
        self._chips(options, value, on_change, bg, height,
                    lambda b: b.pack(side="left", padx=(0, 6)))


class Swatches(Flow):
    """Muestras de color redondas; la elegida con un anillo. El "+" abre el selector
    de colores de Windows (y ese color queda como una muestra más)."""

    S = 30

    def __init__(self, parent, colors, value, on_change, bg=SURFACE):
        super().__init__(parent, bg=bg, gap=6)
        self.colors, self.value, self.on_change, self._bg = list(colors), value, on_change, bg
        self._render()

    def _render(self):
        self.clear()
        extra = [] if any(c.lower() == self.value.lower() for c in self.colors) else [self.value]
        for c in self.colors + extra:
            self.put(self._swatch(c))
        self.put(self._plus())

    def _swatch(self, color):
        S = self.S
        c = tk.Canvas(self, width=S, height=S, bg=self._bg, highlightthickness=0, bd=0,
                      cursor="hand2")
        c._imgs = []
        if color.lower() == self.value.lower():
            c._imgs += [shape(S, S, S // 2, fill=ACCENT), shape(S - 4, S - 4, (S - 4) // 2,
                                                                  fill=self._bg)]
            c.create_image(0, 0, anchor="nw", image=c._imgs[0])
            c.create_image(2, 2, anchor="nw", image=c._imgs[1])
            inner = S - 10
        else:
            inner = S - 6
        edge = BORDER_HI if abs(_lum(color) - _lum(self._bg)) < 0.12 else None
        c._imgs.append(shape(inner, inner, inner // 2, fill=color, border=edge))
        c.create_image((S - inner) // 2, (S - inner) // 2, anchor="nw", image=c._imgs[-1])
        c.bind("<ButtonRelease-1>", lambda e: self._pick(color))
        return c

    def _plus(self):
        S = self.S
        c = tk.Canvas(self, width=S, height=S, bg=self._bg, highlightthickness=0, bd=0,
                      cursor="hand2")
        c._img = shape(S - 6, S - 6, (S - 6) // 2, fill=FIELD, border=BORDER_HI)
        c.create_image(3, 3, anchor="nw", image=c._img)
        c.create_text(S / 2, S / 2 + 1, text=I_ADD, font=F.icon_sm, fill=TEXT_2)
        c.bind("<ButtonRelease-1>", lambda e: self._custom())
        return c

    def _custom(self):
        from tkinter import colorchooser
        _, hexc = colorchooser.askcolor(color=self.value, parent=self.winfo_toplevel(),
                                        title="Elegí un color")
        if hexc:
            self._pick(hexc.lower())

    def _pick(self, color):
        self.value = color
        self._render()
        self.on_change(color)


_walls = {}


def wallpaper(w, h, bg=SURFACE, radius=12):
    """Fondo tipo escritorio (degradé con manchas de color) con esquinas redondeadas,
    para ver bien los estilos con cristal o sin fondo."""
    key = (w, h, bg, radius)
    if key in _walls:
        return _walls[key]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    t = (x / max(1, w) * 0.65 + y / max(1, h) * 0.35)[..., None]
    base = np.array([26, 32, 54], np.float32) * (1 - t) + np.array([58, 38, 88], np.float32) * t
    img = Image.fromarray(base.astype(np.uint8), "RGB")
    blob = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(blob)
    d.ellipse([w * 0.05, h * 0.15, w * 0.40, h * 1.3], fill=(30, 105, 135))
    d.ellipse([w * 0.62, -h * 0.5, w * 1.05, h * 0.65], fill=(135, 60, 125))
    img = ImageChops.screen(img, blob.filter(ImageFilter.GaussianBlur(max(4, h * 0.3))))
    mask = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * 4 - 1, h * 4 - 1], radius * 4, fill=255)
    out = Image.new("RGBA", (w, h), _rgb(bg) + (255,))
    out.paste(img, (0, 0), mask.resize((w, h), Image.LANCZOS))
    if len(_walls) > 24:
        _walls.clear()
    _walls[key] = out
    return out


class Stage(tk.Canvas):
    """Vista previa animada de la ventanita (voz simulada) sobre un fondo tipo
    escritorio. Solo dibuja mientras está visible y no pausada."""

    def __init__(self, parent, get_style, height=130, bg=SURFACE, fps=25, radius=12):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self.get_style, self.state, self.paused = get_style, "recording", False
        self._bg, self._r, self._ms = bg, radius, int(1000 / fps)
        self._photo = None
        self._item = self.create_image(0, 0, anchor="nw")
        self._bars, self._t0 = [], time.perf_counter()
        self._job = self.after(50, self._tick)

    def _tick(self):
        self._job = None
        try:
            if not self.winfo_exists():
                return
            if not self.paused and self.winfo_ismapped():
                w, h = self.winfo_width(), self.winfo_height()
                if w > 20 and h > 20:
                    self._draw(w, h)
        except tk.TclError:
            return
        self._job = self.after(self._ms, self._tick)

    def _draw(self, w, h):
        t = time.perf_counter() - self._t0
        s = self.get_style()
        n = s["bar_count"]
        target = looks.fake_levels(n, t) if self.state == "recording" else [0.0] * n
        if len(self._bars) != n:
            self._bars = [0.0] * n
        k = looks.SPEED[s["speed"]]
        self._bars = [b + (x - b) * k for b, x in zip(self._bars, target)]
        frame = looks.render(s, self.state, self._bars, t)
        sc = min(1.0, (w - 16) / frame.width, (h - 4) / frame.height)
        if sc < 1:
            frame = frame.resize((max(1, round(frame.width * sc)), max(1, round(frame.height * sc))),
                                 Image.LANCZOS)
        comp = wallpaper(w, h, self._bg, self._r).copy()
        comp.alpha_composite(frame, ((w - frame.width) // 2, (h - frame.height) // 2))
        if self._photo is None or (self._photo.width(), self._photo.height()) != (w, h):
            self._photo = ImageTk.PhotoImage(comp)
            self.itemconfigure(self._item, image=self._photo)
        else:
            self._photo.paste(comp)

    def destroy(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        super().destroy()


class StyleCard(tk.Canvas):
    """Tarjeta de la galería: miniatura del estilo + nombre. La elegida lleva borde
    de acento; las del usuario muestran ✕ para borrarlas."""

    W, H = 164, 102
    _thumbs = {}

    def __init__(self, parent, name, style, selected, on_pick, on_hover=None, on_delete=None,
                 bg=SURFACE):
        super().__init__(parent, width=self.W, height=self.H, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.style, self.selected = style, selected
        self.on_pick, self.on_hover, self.on_delete = on_pick, on_hover, on_delete
        self._hover, self._img = False, None
        self._bgid = self.create_image(0, 0, anchor="nw")
        self._thumb = self._make_thumb()
        self.create_image(7, 7, anchor="nw", image=self._thumb)
        self.create_text(12, self.H - 16, text=ellipsize(name, F.small_sb, self.W - 40),
                         font=F.small_sb, fill=TEXT if selected else TEXT_2, anchor="w")
        if selected:
            self.create_text(self.W - 14, self.H - 15, text=I_CHECK, font=F.icon_sm, fill=ACCENT)
        if on_delete:
            self._xbg = shape(24, 24, 12, fill=BG)
            self._xb = self.create_image(self.W - 21, 21, image=self._xbg, state="hidden")
            self._x = self.create_text(self.W - 21, 22, text=I_CLOSE, font=F.icon_sm, fill=TEXT,
                                       state="hidden")
        self._paint()
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonRelease-1>", self._click)

    def _make_thumb(self):
        key = json.dumps(self.style, sort_keys=True)
        ph = StyleCard._thumbs.get(key)
        if ph is None:
            tw, th = self.W - 14, self.H - 40
            frame = looks.render(self.style, "recording",
                                 looks.fake_levels(self.style["bar_count"], 1.35), 1.35)
            sc = min((tw - 10) / frame.width, (th + 12) / frame.height)
            frame = frame.resize((max(1, round(frame.width * sc)), max(1, round(frame.height * sc))),
                                 Image.LANCZOS)
            comp = wallpaper(tw, th, FIELD, 8).copy()
            comp.alpha_composite(frame, ((tw - frame.width) // 2, (th - frame.height) // 2))
            ph = ImageTk.PhotoImage(comp)
            if len(StyleCard._thumbs) > 80:
                StyleCard._thumbs.clear()
            StyleCard._thumbs[key] = ph
        return ph

    def _paint(self):
        border = ACCENT if self.selected else (BORDER_HI if self._hover else BORDER)
        self._img = shape(self.W, self.H, 12, fill=FIELD, border=border, bw=2 if self.selected else 1)
        self.itemconfigure(self._bgid, image=self._img)

    def _on_x(self, e):
        return self.on_delete and e.x >= self.W - 34 and e.y <= 34

    def _enter(self, e):
        self._hover = True
        self._paint()
        if self.on_delete:
            self.itemconfigure(self._xb, state="normal")
            self.itemconfigure(self._x, state="normal")
        if self.on_hover:
            self.on_hover(self.style)

    def _leave(self, e):
        self._hover = False
        self._paint()
        if self.on_delete:
            self.itemconfigure(self._xb, state="hidden")
            self.itemconfigure(self._x, state="hidden")
        if self.on_hover:
            self.on_hover(None)

    def _click(self, e):
        if not (0 <= e.x <= self.W and 0 <= e.y <= self.H):
            return
        if self._on_x(e):
            self.on_delete()
        else:
            self.on_pick()


class ActionCard(tk.Canvas):
    """Tarjeta con ícono y texto, del mismo tamaño que StyleCard (p.ej. "Crear el tuyo")."""

    def __init__(self, parent, icon, text, command, bg=SURFACE):
        W, H = StyleCard.W, StyleCard.H
        super().__init__(parent, width=W, height=H, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2")
        self._imgs = (shape(W, H, 12, fill=bg, border=BORDER_HI), shape(W, H, 12, fill=FIELD,
                                                                          border=ACCENT))
        self._bgid = self.create_image(0, 0, anchor="nw", image=self._imgs[0])
        self.create_text(W / 2, H / 2 - 12, text=icon, font=F.icon_lg, fill=ACCENT)
        self.create_text(W / 2, H / 2 + 22, text=text, font=F.small_sb, fill=TEXT_2)
        self.bind("<Enter>", lambda e: self.itemconfigure(self._bgid, image=self._imgs[1]))
        self.bind("<Leave>", lambda e: self.itemconfigure(self._bgid, image=self._imgs[0]))
        self.bind("<ButtonRelease-1>", lambda e: command())


class ScrollArea(tk.Frame):
    """Área con scroll vertical y una barra fina propia (se oculta si no hace falta)."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=1)
        self.bar = tk.Canvas(self, width=12, bg=bg, highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self._thumb = None
        self._drag = None
        self.inner.bind("<Configure>", lambda e: self._region())
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.configure(yscrollcommand=lambda f, l: self._paint_bar())
        self.bar.bind("<Configure>", lambda e: self._paint_bar())
        self.bar.bind("<Button-1>", self._drag_start)
        self.bar.bind("<B1-Motion>", self._drag_move)
        self.bar.bind("<Enter>", lambda e: self._paint_bar(hover=True))
        self.bar.bind("<Leave>", lambda e: self._paint_bar())
        self.after_idle(self._register_wheel)

    def _register_wheel(self):
        if self.winfo_exists():
            _areas[str(self.winfo_toplevel())] = self
            self.bind("<Destroy>", lambda e: _areas.pop(str(self.winfo_toplevel()), None)
                      if e.widget is self else None)

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        self._region()

    def _region(self):
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(),
                                            self.inner.winfo_reqheight()))
        self._paint_bar()

    def scroll(self, px):
        self.canvas.yview_scroll(int(px), "units")

    def to_top(self):
        self.canvas.yview_moveto(0)

    def _paint_bar(self, hover=False):
        self.bar.delete("all")
        first, last = self.canvas.yview()
        H = self.bar.winfo_height()
        if last - first >= 0.999 or H < 20:
            return
        y0 = first * H
        h = max(36, (last - first) * H)
        y0 = min(y0, H - h)
        self._thumb = shape(6, h, 3, fill=TEXT_3 if hover else BORDER_HI)
        self.bar.create_image(3, y0, image=self._thumb, anchor="nw")

    def _drag_start(self, e):
        self._drag = (e.y, self.canvas.yview()[0])

    def _drag_move(self, e):
        if self._drag and self.bar.winfo_height():
            y, f0 = self._drag
            self.canvas.yview_moveto(f0 + (e.y - y) / self.bar.winfo_height())


_areas = {}


def _on_wheel(e):
    try:
        w = e.widget.winfo_containing(e.x_root, e.y_root)
    except (KeyError, tk.TclError):
        return
    if w is not None:
        area = _areas.get(str(w.winfo_toplevel()))
        if area:
            area.scroll(-e.delta / 120 * 56)


# ── Ventana ──────────────────────────────────────────────────────────────────
_u32 = ctypes.WinDLL("user32")
_u32.GetAncestor.restype = wintypes.HWND
_u32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_dwm = ctypes.WinDLL("dwmapi")
_dwm.DwmSetWindowAttribute.restype = ctypes.c_long
_dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p,
                                       wintypes.DWORD]


_u32.GetForegroundWindow.restype = wintypes.HWND
_u32.SetForegroundWindow.argtypes = [wintypes.HWND]


def foreground():
    return _u32.GetForegroundWindow()


def restore_foreground(hwnd):
    """Crear el Tk root lo activa un instante: se le devuelve el foco a quien lo
    tenía (funciona porque la app deja el bloqueo de foco de Windows en 0)."""
    if hwnd and _u32.GetForegroundWindow() != hwnd:
        _u32.SetForegroundWindow(hwnd)


def hwnd_of(win):
    return _u32.GetAncestor(win.winfo_id(), 2) or win.winfo_id()


def _colorref(c):
    r, g, b = _rgb(c)
    return r | (g << 8) | (b << 16)


def style_window(win, caption=BG):
    """Barra de título nativa oscura y del mismo color que la ventana (Windows 11;
    en Windows 10 queda en modo oscuro). Mantiene todo lo nativo: mover, snap, etc."""
    try:
        hwnd = hwnd_of(win)
        for attr, val in ((20, 1), (35, _colorref(caption)), (34, _colorref(BORDER)),
                          (36, _colorref(TEXT_2))):
            v = ctypes.c_int(val)
            _dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


def set_icon(win):
    from brand import make_icon
    win._icons = [ImageTk.PhotoImage(make_icon(s)) for s in (32, 16)]
    win.iconphoto(False, *win._icons)


def show_window(win, w, h, over=None, fit=None):
    """Muestra la ventana centrada (sobre `over` si se pasa), con la barra de título
    oscura y sin parpadeo blanco: se arma invisible (alpha 0), y si hay `fit()` el
    alto final sale del contenido ya acomodado."""
    win.geometry(f"{w}x{h}")
    win.attributes("-alpha", 0.0)
    win.deiconify()
    win.update()
    if fit:
        h = max(200, int(fit()))
    if over is not None and over.winfo_exists():
        x = over.winfo_rootx() + (over.winfo_width() - w) // 2
        y = over.winfo_rooty() + (over.winfo_height() - h) // 2 - 20
    else:
        x = (win.winfo_screenwidth() - w) // 2
        y = max(20, (win.winfo_screenheight() - h) // 2 - 30)
    win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
    win.update_idletasks()
    style_window(win)
    win.lift()
    win.attributes("-topmost", True)
    win.after(40, lambda: win.winfo_exists() and win.attributes("-alpha", 1.0))
    win.after(450, lambda: win.winfo_exists() and win.attributes("-topmost", False))
    win.focus_force()
