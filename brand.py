"""Identidad de Dictado App: nombre, versión e ícono.

El ícono se dibuja con PIL (supersampling → bordes suaves): cuadrado redondeado con
el degradé de la marca (cian→violeta, el mismo del overlay) y barras de onda.
Los tamaños chicos usan 3 barras alineadas a píxeles enteros, para que en la
bandeja (16-32px) se vea nítido y no una mancha.
"""
import numpy as np
from PIL import Image, ImageDraw

APP_NAME = "Dictado App"
__version__ = "1.2.3"

_SS = 8
_BRAND = ((34, 211, 238), (139, 92, 246))     # cian → violeta
_REC = ((251, 113, 133), (225, 29, 72))       # rosa → rojo (grabando)

# 3 barras "a mano" por tamaño: (ancho, separación, altura chica, altura grande)
_SMALL = {16: (2, 2, 6, 10), 20: (2, 3, 8, 12), 24: (4, 2, 8, 14), 32: (4, 4, 12, 20)}


def _gradient(size, c1, c2):
    """Degradé diagonal (arriba-izquierda → abajo-derecha)."""
    n = min(size, 256)
    t = np.add.outer(np.arange(n), np.arange(n)).astype(np.float32) / (2 * (n - 1))
    rgb = np.asarray(c1, np.float32) * (1 - t[..., None]) + np.asarray(c2, np.float32) * t[..., None]
    return Image.fromarray(rgb.round().astype(np.uint8), "RGB").resize((size, size), Image.BILINEAR)


def _bars(size, small):
    """Barras como rectángulos (x0, y0, x1, y1) en píxeles del tamaño final."""
    cy = size / 2
    if small:
        base = min(_SMALL, key=lambda s: abs(s - size)) if size <= 32 else 32
        k = size / base
        w, gap, h_lo, h_hi = (round(v * k) for v in _SMALL[base])
        heights = (h_lo, h_hi, h_lo)
    else:
        w, gap = size * 0.085, size * 0.066
        heights = tuple(size * f for f in (0.30, 0.52, 0.70, 0.52, 0.30))
    total = len(heights) * w + (len(heights) - 1) * gap
    x = (size - total) / 2
    out = []
    for h in heights:
        out.append((x, cy - h / 2, x + w, cy + h / 2))
        x += w + gap
    return out


def make_icon(size, recording=False, small=None):
    """Ícono RGBA de `size`×`size` px. `small`=True fuerza el diseño de 3 barras."""
    small = size < 40 if small is None else small
    S = size * _SS
    margin = 0 if small else round(size * 0.06) * _SS
    radius = (S - 2 * margin) * 0.26
    c1, c2 = _REC if recording else _BRAND

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([margin, margin, S - 1 - margin, S - 1 - margin],
                                           radius=radius, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(_gradient(S, c1, c2), (0, 0), mask)

    if not small:   # brillo sutil arriba (profundidad), solo donde se aprecia
        gloss = Image.linear_gradient("L").resize((S, S)).point(lambda v: max(0, 46 - v * 46 // 150))
        white = Image.new("RGBA", (S, S), (255, 255, 255, 0))
        white.putalpha(Image.composite(gloss, Image.new("L", (S, S), 0), mask))
        img = Image.alpha_composite(img, white)

    d = ImageDraw.Draw(img)
    for x0, y0, x1, y1 in _bars(size, small):
        d.rounded_rectangle([x0 * _SS, y0 * _SS, x1 * _SS - 1, y1 * _SS - 1],
                            radius=(x1 - x0) / 2 * _SS, fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


def make_tray_icon(recording=False):
    """Imagen para la bandeja. Windows la achica a 16-24px: va a 64px con el diseño
    de 3 barras (geometría múltiplo de 16 → sigue nítida al achicarse)."""
    return make_icon(64, recording, small=True)


ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def save_ico(path):
    imgs = [make_icon(s) for s in ICO_SIZES]
    imgs[-1].save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES], append_images=imgs[:-1])
