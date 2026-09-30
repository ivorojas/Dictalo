"""Estilos de la ventanita flotante (overlay): presets, validación y el dibujante.

Un estilo es un dict plano (ver DEFAULT). Los presets son variaciones de DEFAULT.
`render()` dibuja un cuadro RGBA con PIL: supersampling (bordes suaves) y alpha por
píxel (sombra, cristal, resplandor, sin fondo). Lo usan el overlay real (ventana
en capas de Windows) y las vistas previas de Ajustes.
"""
import colorsys
import json
import math
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DEFAULT = {
    "shape": "pill", "size": "normal", "bg": "#0e0f16", "bg_mode": "solid",
    "border": "none", "shadow": True,
    "dot": "halo", "dot_color": "#ff5470", "dot_anim": "pulse",
    "bars": "rounded", "bar_count": 14, "thickness": "normal",
    "colors": "gradient", "color1": "#22d3ee", "color2": "#a78bfa", "glow": False,
    "speed": "normal", "processing": "dots", "position": "bottom",
}

CHOICES = {
    "shape": ("pill", "rounded", "square"),
    "size": ("small", "normal", "large"),
    "bg_mode": ("solid", "glass", "none"),
    "border": ("none", "subtle", "accent", "gradient"),
    "shadow": (True, False),
    "dot": ("halo", "dot", "ring", "mic", "none"),
    "dot_anim": ("pulse", "blink", "still"),
    "bars": ("rounded", "square", "dots", "wave", "mirror", "blocks"),
    "bar_count": (8, 14, 20, 28),
    "thickness": ("thin", "normal", "thick"),
    "colors": ("gradient", "solid", "rainbow", "rainbow_anim"),
    "glow": (True, False),
    "speed": ("smooth", "normal", "snappy"),
    "processing": ("dots", "orbit", "wave", "bar"),
    "position": ("bottom", "top"),
}
_COLOR_KEYS = ("bg", "dot_color", "color1", "color2")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# (id, nombre, cambios sobre DEFAULT)
PRESETS = [
    ("aurora", "Aurora", {}),
    ("arcoiris", "Arcoíris", {"colors": "rainbow_anim", "glow": True, "dot": "ring",
                              "dot_color": "#ffffff", "bar_count": 20}),
    ("neon", "Neón", {"bg": "#06060b", "shape": "rounded", "border": "gradient", "bars": "square",
                      "color1": "#f0abfc", "color2": "#22d3ee", "glow": True, "dot": "ring",
                      "dot_color": "#f472b6"}),
    ("cristal", "Cristal", {"bg": "#1c2130", "bg_mode": "glass", "border": "subtle",
                            "colors": "solid", "color1": "#ffffff", "dot": "dot",
                            "dot_color": "#fb7185"}),
    ("minimal", "Minimal", {"size": "small", "thickness": "thin", "bar_count": 20,
                            "colors": "solid", "color1": "#e5e7eb", "dot": "none",
                            "shadow": False, "processing": "bar"}),
    ("onda", "Onda", {"bars": "wave", "bar_count": 28, "color1": "#38bdf8", "color2": "#c084fc",
                      "processing": "wave", "glow": True}),
    ("fuego", "Fuego", {"bg": "#150b07", "bars": "mirror", "color1": "#facc15",
                        "color2": "#ef4444", "glow": True, "dot_color": "#f97316"}),
    ("oceano", "Océano", {"bg": "#06141c", "shape": "rounded", "bars": "dots", "color1": "#2dd4bf",
                          "color2": "#3b82f6", "dot": "mic", "dot_color": "#5eead4",
                          "processing": "orbit"}),
    ("retro", "Retro", {"bg": "#040804", "shape": "square", "bars": "blocks", "thickness": "thick",
                        "color1": "#22c55e",
                        "color2": "#facc15", "border": "accent", "dot": "dot",
                        "dot_color": "#22c55e", "dot_anim": "blink", "shadow": False,
                        "processing": "bar", "speed": "snappy"}),
    ("claro", "Claro", {"bg": "#f8fafc", "border": "subtle", "color1": "#6366f1",
                        "color2": "#ec4899", "dot_color": "#ef4444"}),
    ("atardecer", "Atardecer", {"bg": "#1a0e14", "thickness": "thick", "bar_count": 8,
                                "color1": "#fb923c", "color2": "#db2777",
                                "dot_color": "#fda4af", "speed": "smooth"}),
    ("sinfondo", "Sin fondo", {"bg_mode": "none", "shadow": False, "glow": True,
                               "bar_count": 20}),
]
PRESET_IDS = [p[0] for p in PRESETS]
SPEED = {"smooth": 0.3, "normal": 0.6, "snappy": 0.9}
DEFAULT_INTENSITY = 0.8   # exageración visual por defecto (Ajustes → Intensidad de las barras)
MARGIN = 22
_BG_ALPHA = {"solid": 250, "glass": 176, "none": 0}
_SIZES = {"small": (44, 4, 5, 36), "normal": (56, 5, 7, 44), "large": (68, 6, 8, 52)}
_THICK = {"thin": 0.6, "normal": 1.0, "thick": 1.7}


# ── Estilos ──────────────────────────────────────────────────────────────────
def resolve(style):
    """DEFAULT + lo que venga en `style`, descartando claves o valores inválidos
    (así un prefs.json viejo o editado a mano nunca rompe el overlay)."""
    s = dict(DEFAULT)
    for k, v in (style or {}).items():
        if k not in DEFAULT:
            continue
        if k in CHOICES and v not in CHOICES[k]:
            continue
        if k in _COLOR_KEYS and not (isinstance(v, str) and _HEX.match(v)):
            continue
        s[k] = v
    return s


def preset(pid):
    for i, _, changes in PRESETS:
        if i == pid:
            return resolve(changes)
    return resolve({})


def preset_name(pid):
    return next((name for i, name, _ in PRESETS if i == pid), None)


def current(config):
    """Estilo en uso según la config: un preset, "custom" o "mine:<nombre>"."""
    sel = getattr(config, "overlay_preset", "aurora") or "aurora"
    if sel == "custom":
        return resolve(getattr(config, "overlay_custom", {}))
    if sel.startswith("mine:"):
        name = sel[5:]
        for it in getattr(config, "overlay_mine", []) or []:
            if isinstance(it, dict) and it.get("name") == name:
                return resolve(it.get("style"))
    return preset(sel)


def current_name(config):
    sel = getattr(config, "overlay_preset", "aurora") or "aurora"
    if sel == "custom":
        return "Personalizado"
    if sel.startswith("mine:"):
        return sel[5:]
    return preset_name(sel) or "Aurora"


# ── Utilidades de color ──────────────────────────────────────────────────────
def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, t):
    a, b = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _hue(h):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 0.62, 1.0)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _lum(c):
    r, g, b = _rgb(c)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def _rgba(c, a=255):
    return _rgb(c) + (int(max(0, min(255, a))),)


def bar_colors(s, n, t=0.0):
    if s["colors"] == "solid":
        return [s["color1"]] * n
    if s["colors"] in ("rainbow", "rainbow_anim"):
        shift = t * 0.12 if s["colors"] == "rainbow_anim" else 0
        return [_hue(i / max(1, n) * 0.92 + shift) for i in range(n)]
    return [_mix(s["color1"], s["color2"], i / max(1, n - 1)) for i in range(n)]


def resample(bands, n):
    """Lleva las bandas del micrófono a `n` barras: agrupa (tomando el pico, así
    sigue vivo) si hay menos barras, interpola si hay más."""
    if not bands:
        return [0.0] * n
    b = np.asarray(bands, dtype=float)
    if n <= len(b):
        return [float(c.max()) for c in np.array_split(b, n)]
    return np.interp(np.linspace(0, len(b) - 1, n), np.arange(len(b)), b).tolist()


def exaggerate(levels, amount):
    """Curva visual de las barras. amount 0..1: 0 = tal como llega del micrófono;
    1 = muy exagerada (lo bajo se levanta mucho y lo alto llega al tope seguido).
    Solo cambia cómo se VE: la transcripción usa el audio tal cual."""
    try:
        a = max(0.0, min(1.0, float(amount)))
    except (TypeError, ValueError):
        a = DEFAULT_INTENSITY
    gain, gamma = 1 + 2.2 * a, 1 / (1 + 1.2 * a)
    return [min(1.0, (max(0.0, v) * gain) ** gamma) for v in levels]


def follow(bars, target, speed):
    """Acerca las barras al objetivo: suben rápido y bajan más suave (se ven vivas)."""
    k = SPEED.get(speed, 0.6)
    up, down = min(1.0, k * 1.6), k * 0.7
    return [b + (x - b) * (up if x > b else down) for b, x in zip(bars, target)]


def fake_bands(n, t):
    """Como las bandas reales del micrófono (espectro de voz: casi todo bajo y un par
    de bandas fuertes). La vista previa las pasa por exaggerate() para mostrar el
    efecto de la intensidad elegida."""
    env = max(0.0, 0.5 * math.sin(t * 2.3) + 0.32 * math.sin(t * 5.1) + 0.28)
    loud = min(1.0, env * 1.1)
    out = []
    for i in range(n):
        f = i / max(1, n - 1)
        shape = (math.exp(-((f - 0.22) / 0.16) ** 2)
                 + 0.4 * math.exp(-((f - 0.55) / 0.12) ** 2) + 0.06)
        wob = 0.5 + 0.5 * math.sin(t * 9.0 + i * 1.7) * math.cos(t * 4.3 + i * 0.9)
        out.append(min(1.0, loud * shape * (0.45 + 0.55 * wob)))
    return out


def fake_levels(n, t):
    """Niveles que parecen voz (sílabas con pausas, más energía en graves-medios),
    para las miniaturas de la galería."""
    env = max(0.0, 0.55 * math.sin(t * 2.3) + 0.35 * math.sin(t * 5.1) + 0.3)
    out = []
    for i in range(n):
        f = i / max(1, n - 1)
        spec = 0.3 + 0.7 * math.exp(-((f - 0.35) / 0.3) ** 2)
        wob = 0.5 + 0.5 * math.sin(t * 9.0 + i * 1.7) * math.cos(t * 4.3 + i * 0.9)
        out.append(min(1.0, env * spec * (0.5 + 0.7 * wob)))
    return out


# ── Geometría y capa fija (fondo, borde, sombra) ─────────────────────────────
def geometry(s):
    h, bw, gap, dot_zone = _SIZES[s["size"]]
    step = bw + gap
    bw = max(2, round(bw * _THICK[s["thickness"]]))
    gap = max(2, step - bw) if s["thickness"] != "thick" else max(3, round(gap * 0.8))
    n = s["bar_count"]
    left = dot_zone if s["dot"] != "none" else round(h * 0.36)
    right = round(h * 0.36)
    bars_w = n * bw + (n - 1) * gap
    w = left + bars_w + right
    r = {"pill": h / 2, "rounded": h * 0.27, "square": h * 0.08}[s["shape"]]
    return {"h": h, "w": w, "bw": bw, "gap": gap, "n": n, "left": left, "bars_w": bars_w,
            "r": r, "W": w + 2 * MARGIN, "H": h + 2 * MARGIN}


def _mask(W, H, box, r, ss=4):
    m = Image.new("L", (W * ss, H * ss), 0)
    x0, y0, x1, y1 = (v * ss for v in box)
    ImageDraw.Draw(m).rounded_rectangle([x0, y0, x1 - 1, y1 - 1], radius=r * ss, fill=255)
    return m.resize((W, H), Image.LANCZOS)


def _hgrad(W, H, cols):
    """Imagen RGB W×H con un degradé horizontal entre la lista de colores."""
    stops = np.array([_rgb(c) for c in cols], dtype=np.float32)
    xs = np.linspace(0, len(stops) - 1, W)
    row = np.stack([np.interp(xs, np.arange(len(stops)), stops[:, k]) for k in range(3)], axis=-1)
    return Image.fromarray(np.repeat(row[None].round().astype(np.uint8), H, axis=0), "RGB")


_static_cache = {}


def _static(s, g):
    key = json.dumps([s[k] for k in ("shape", "size", "bg", "bg_mode", "border", "shadow",
                                      "color1", "color2", "bar_count", "thickness", "dot")])
    img = _static_cache.get(key)
    if img is not None:
        return img
    W, H, m = g["W"], g["H"], MARGIN
    box = [m, m, m + g["w"], m + g["h"]]
    alpha = _BG_ALPHA[s["bg_mode"]]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if s["shadow"] and alpha:
        sh = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sh).rounded_rectangle([box[0] + 3, box[1] + 7, box[2] - 3, box[3] + 5],
                                             radius=g["r"], fill=int(140 * alpha / 255))
        img.putalpha(sh.filter(ImageFilter.GaussianBlur(9)))
    body = _mask(W, H, box, g["r"])
    if alpha:
        fill = Image.new("RGBA", (W, H), _rgba(s["bg"]))
        fill.putalpha(body.point(lambda v: v * alpha // 255))
        img = Image.alpha_composite(img, fill)
    if s["border"] != "none":
        bw = 1.0 if s["border"] == "subtle" else 1.6
        inner = _mask(W, H, [box[0] + bw, box[1] + bw, box[2] - bw, box[3] - bw], g["r"] - bw)
        ring = Image.fromarray(np.clip(np.asarray(body, np.int16) - np.asarray(inner, np.int16),
                                       0, 255).astype(np.uint8), "L")
        if s["border"] == "subtle":
            light = _lum(s["bg"]) < 0.5
            src = Image.new("RGBA", (W, H), (255, 255, 255, 40) if light else (0, 0, 0, 34))
            ring = ring.point(lambda v: v * (40 if light else 34) // 255)
        elif s["border"] == "accent":
            src = Image.new("RGBA", (W, H), _rgba(s["color1"]))
        else:
            src = _hgrad(W, H, [s["color1"], s["color2"]]).convert("RGBA")
        src.putalpha(ring)
        img = Image.alpha_composite(img, src)
    if len(_static_cache) > 48:
        _static_cache.clear()
    _static_cache[key] = img
    return img


# ── Cuadro animado ───────────────────────────────────────────────────────────
_fonts = {}


def _icon_font(px):
    f = _fonts.get(px)
    if f is None:
        for name in ("SegoeIcons.ttf", "segmdl2.ttf"):
            try:
                f = ImageFont.truetype(f"C:/Windows/Fonts/{name}", px)
                break
            except OSError:
                continue
        _fonts[px] = f
    return f


def _dot(d, s, g, state, t, S):
    if s["dot"] == "none":
        return
    cx, cy = (MARGIN + g["left"] / 2) * S, (MARGIN + g["h"] / 2) * S
    rec = state == "recording"
    col = s["dot_color"] if rec else s["color1"]
    anim = s["dot_anim"] if rec else "still"
    k, a = 1.0, 255
    if anim == "pulse":
        k = 1 + 0.24 * (0.5 + 0.5 * math.sin(t * 5.5))
    elif anim == "blink":
        a = 255 * (0.25 + 0.75 * (0.5 + 0.5 * math.sin(t * 4.5)))
    r = g["h"] * 0.085 * k * S
    if s["dot"] == "mic":
        f = _icon_font(round(g["h"] * 0.36 * S))
        if f:
            d.text((cx, cy + S), "\ue720", font=f, fill=_rgba(col, a), anchor="mm")
        return
    if s["dot"] == "ring":
        rr = r * 1.3
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=_rgba(col, a), width=round(2 * S))
        return
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_rgba(col, a))
    if s["dot"] == "halo":
        rr = r + 3.4 * S
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=_rgba(col, a * 0.5), width=S)


def _bars(img, d, s, g, levels, t, S):
    n, bw, gap = g["n"], g["bw"] * S, g["gap"] * S
    x0, cy = (MARGIN + g["left"]) * S, (MARGIN + g["h"] / 2) * S
    if s["bars"] == "wave":
        return _wave(img, s, g, levels, t, S)
    cols = bar_colors(s, n, t)
    maxh, minh = g["h"] * 0.78 * S, bw          # 78% del alto: margen para no salirse nunca
    for i in range(n):
        lv = max(0.0, min(1.0, levels[i] if i < len(levels) else 0.0))
        x = x0 + i * (bw + gap)
        c = _rgba(cols[i])
        if s["bars"] in ("rounded", "square"):
            h = minh + lv * (maxh - minh)
            rad = bw / 2 if s["bars"] == "rounded" else S * 0.6
            d.rounded_rectangle([x, cy - h / 2, x + bw, cy + h / 2], radius=rad, fill=c)
        elif s["bars"] == "dots":
            slots = max(3, int(maxh / (bw * 1.6)) // 2 * 2 + 1)
            lit = 1 + 2 * round(lv * (slots - 1) / 2)
            step = maxh / slots
            for j in range(lit):
                y = cy + (j - (lit - 1) / 2) * step
                d.ellipse([x, y - bw / 2, x + bw, y + bw / 2], fill=c)
        elif s["bars"] == "mirror":
            base = (MARGIN + g["h"] * 0.62) * S
            h = minh + lv * (g["h"] * 0.52 * S - minh)
            d.rounded_rectangle([x, base - h, x + bw, base], radius=bw / 2, fill=c)
            d.rounded_rectangle([x, base + 1.5 * S, x + bw, base + 1.5 * S + h * 0.42],
                                radius=bw / 2, fill=_rgba(cols[i], 64))
        else:   # blocks (vúmetro retro)
            sq, gb = bw, max(S, bw * 0.34)
            slots = max(3, int(g["h"] * 0.8 * S / (sq + gb)))
            lit = max(1, round(lv * slots))
            base = cy + slots * (sq + gb) / 2
            for j in range(lit):
                y = base - (j + 1) * (sq + gb) + gb
                cc = _mix(s["color1"], s["color2"], j / (slots - 1)) if s["colors"] == "gradient" \
                    else cols[i]
                d.rectangle([x, y, x + sq, y + sq], fill=_rgba(cc))


def _wave(img, s, g, levels, t, S):
    n = len(levels)
    x0, cy = (MARGIN + g["left"]) * S, (MARGIN + g["h"] / 2) * S
    width, amp = g["bars_w"] * S, g["h"] * 0.4 * S
    xf = np.linspace(0, 1, max(2, n) * 10)
    y = np.interp(xf, np.linspace(0, 1, max(2, n)), (list(levels) + [0, 0])[:max(2, n)])
    y = np.convolve(y, np.ones(9) / 9, mode="same")
    a = (0.07 + 0.93 * y) * np.sin(np.pi * xf) ** 0.7 * amp
    xs = x0 + xf * width
    poly = list(zip(xs, cy - a)) + list(zip(xs[::-1], (cy + a)[::-1]))
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    cols = bar_colors(s, 24, t) if s["colors"] != "solid" else [s["color1"]] * 2
    band = _hgrad(round(width), 1, cols).resize((round(width), img.size[1]))
    layer = Image.new("RGB", img.size, (0, 0, 0))
    layer.paste(band, (round(x0), 0))
    img.paste(layer, (0, 0), mask)


def _processing(img, d, s, g, t, S):
    cx = (MARGIN + g["left"] + g["bars_w"] / 2) * S
    cy = (MARGIN + g["h"] / 2) * S
    c1, c2 = s["color1"], s["color2"] if s["colors"] == "gradient" else s["color1"]
    kind = s["processing"]
    if kind == "wave":
        lv = [0.16 + 0.3 * (0.5 + 0.5 * math.sin(t * 6 - i * 0.55)) for i in range(g["n"])]
        return _bars(img, d, s, g, lv, t, S)
    if kind == "dots":
        for i in range(3):
            a = 0.5 + 0.5 * math.sin(t * 6 - i * 0.7)
            r = (2.6 + a * 2.6) * S * g["h"] / 56
            x = cx + (i - 1) * 14 * S * g["h"] / 56
            d.ellipse([x - r, cy - r, x + r, cy + r], fill=_rgba(_mix(c1, c2, i / 2)))
    elif kind == "orbit":
        R = g["h"] * 0.22 * S
        for i in range(8):
            ang = t * 5.5 - i * 0.55
            a = 255 * (1 - i / 8)
            r = (3.2 - i * 0.25) * S * g["h"] / 56
            x, y = cx + R * math.cos(ang), cy + R * math.sin(ang)
            d.ellipse([x - r, y - r, x + r, y + r], fill=_rgba(_mix(c1, c2, i / 7), a))
    else:   # barra de progreso indeterminada
        tw, th = g["bars_w"] * 0.8 * S, 4 * S
        x0 = cx - tw / 2
        d.rounded_rectangle([x0, cy - th / 2, x0 + tw, cy + th / 2], radius=th / 2,
                            fill=_rgba(c1, 55))
        p = 0.5 + 0.5 * math.sin(t * 2.6)
        seg = tw * 0.32
        xs = x0 + p * (tw - seg)
        d.rounded_rectangle([xs, cy - th / 2, xs + seg, cy + th / 2], radius=th / 2,
                            fill=_rgba(_mix(c1, c2, p)))


# ── Modo IA: la versión "súper" de cualquier estilo ───────────────────────────
AI_COLORS = ["#ffd54a", "#ff8a3d", "#ff4fd8", "#8b5cf6", "#ffd54a"]   # dorado → naranja → magenta → violeta
AI_IN_S = 0.55          # duración de la entrada (insignia y halo); overlay la anima a ~60 cuadros/s
_ai_cache = {}


def _ease_out(p):
    return 1 - (1 - p) ** 3


def _ease_back(p, over=1.15):
    """Sale rápido, se pasa apenas y vuelve: un rebote leve, no un salto."""
    p -= 1
    return 1 + (over + 1) * p ** 3 + over * p ** 2


def _star(d, cx, cy, r, ang, fill):
    """Destello de 4 puntas (✦)."""
    pts = []
    for i in range(8):
        a = ang + i * math.pi / 4
        rr = r if i % 2 == 0 else r * 0.3
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)


def _ai_badge_base(D):
    """Parte fija de la insignia (resplandor + disco con degradé + aro), supersampleada ×3."""
    key = ("badge", D)
    base = _ai_cache.get(key)
    if base is None:
        S, pad = 3, D // 2
        size = (D + 2 * pad) * S
        c, R = size / 2, D / 2 * S
        glow = Image.new("L", (size, size), 0)
        ImageDraw.Draw(glow).ellipse([c - R * 1.2, c - R * 1.2, c + R * 1.2, c + R * 1.2], fill=230)
        base = Image.new("RGBA", (size, size), _rgba("#ffb347"))
        base.putalpha(glow.filter(ImageFilter.GaussianBlur(pad * S / 2.2)))
        disc = Image.new("L", (size, size), 0)
        ImageDraw.Draw(disc).ellipse([c - R, c - R, c + R, c + R], fill=255)
        grad = _hgrad(size, size, ["#ffd54a", "#ff8a3d", "#ff4fd8"]).rotate(35).convert("RGBA")
        grad.putalpha(disc)
        base = Image.alpha_composite(base, grad)
        ImageDraw.Draw(base).ellipse([c - R, c - R, c + R, c + R], outline=(255, 255, 255, 170),
                                     width=max(1, int(1.4 * S)))
        _ai_cache[key] = base
    return base


def _ai_badge(D, t, state):
    """Insignia con el ✦ girando (más rápido mientras procesa)."""
    tile = _ai_badge_base(D).copy()
    size = tile.size[0]
    c, R = size / 2, D / 2 * 3
    d = ImageDraw.Draw(tile)
    spin = t * (5.5 if state == "processing" else 1.6)
    _star(d, c, c, R * 0.62, spin, (255, 255, 255, 255))
    _star(d, c + R * 0.42, c - R * 0.42, R * 0.2, -spin * 1.4, (255, 255, 255, 220))
    return tile.resize((size // 3, size // 3), Image.BILINEAR)


def ai_frame(img, s, state, t, p):
    """Versión modo IA de un cuadro ya dibujado (cualquier estilo: trabaja sobre la silueta de la
    forma): halo vibrante que late y cambia de color, insignia ✦ que entra desde la derecha y,
    mientras procesa, un destello que recorre la ventanita. `p` = avance de la entrada (0 a 1).
    Agranda el lienzo igual a los dos lados, así la ventanita sigue centrada."""
    g = geometry(s)
    W, H = img.size
    D = max(18, round(g["h"] * 0.78))
    gap = max(6, round(g["h"] * 0.16))
    ext = D + gap
    W2 = W + 2 * ext
    key = (W, H, g["w"], g["h"], g["r"], D)
    base = _ai_cache.get(key)
    if base is None:
        body = Image.new("L", (W2, H), 0)
        body.paste(_mask(W, H, [MARGIN, MARGIN, MARGIN + g["w"], MARGIN + g["h"]], g["r"]), (ext, 0))
        halo = np.asarray(body.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.GaussianBlur(9)),
                          np.float32) / 255 * 1.35
        grad = np.asarray(_hgrad(W2, H, AI_COLORS), np.uint8)
        base = (np.asarray(body, np.float32) / 255, halo, grad)
        if len(_ai_cache) > 16:
            _ai_cache.clear()
        _ai_cache[key] = base
    body, halo, grad = base
    p = max(0.0, min(1.0, p))
    e = _ease_out(p)                # una sola curva para todo: fundido, deslizamiento y halo
    pulse = 0.6 + 0.4 * math.sin(t * 7)
    alpha = np.clip(halo * pulse * e * 255, 0, 255).astype(np.uint8)
    canvas = Image.fromarray(np.dstack([np.roll(grad, int(t * 90) % W2, axis=1), alpha]), "RGBA")
    canvas.alpha_composite(img, (ext, 0))
    if state == "processing":
        x0, x1 = ext + MARGIN, ext + MARGIN + g["w"]
        bx = x0 + ((t * 0.9) % 1.4 - 0.2) * (x1 - x0)
        xs = np.arange(W2, dtype=np.float32)
        band = np.exp(-((xs - bx) / (g["h"] * 0.55)) ** 2)[None, :] * body * 110 * e
        shine = np.zeros((H, W2, 4), np.uint8)
        shine[..., :3] = 255
        shine[..., 3] = np.clip(band, 0, 255).astype(np.uint8)
        canvas.alpha_composite(Image.fromarray(shine, "RGBA"))
    q = 0.45 + 0.55 * _ease_back(p) if p < 1 else 1.0     # arranca a media escala: crece sin saltar
    if e > 0.01:
        tile = _ai_badge(D, t, state)
        if q != 1.0:
            n = max(2, round(tile.size[0] * q))
            tile = tile.resize((n, n), Image.BICUBIC)
        if e < 1.0:                                        # fundido de entrada
            a = np.asarray(tile.getchannel("A"), np.float32) * e
            tile.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
        cx = ext + MARGIN + g["w"] + gap + D / 2 - (1 - e) * D * 0.5
        cy = MARGIN + g["h"] / 2
        _paste(canvas, tile, round(cx - tile.size[0] / 2), round(cy - tile.size[1] / 2))
    return canvas


def warm_ai(s):
    """Precalcula lo fijo del modo IA para el estilo `s` (así el primer cuadro no se traba)."""
    g = geometry(s)
    ai_frame(render(s, "recording", [0.0] * g["n"], 0.0), s, "recording", 0.0, 1.0)


def _paste(canvas, tile, x, y):
    """alpha_composite que recorta lo que cae afuera del lienzo (en vez de fallar)."""
    l, t = max(0, -x), max(0, -y)
    r = min(tile.size[0], canvas.size[0] - x)
    b = min(tile.size[1], canvas.size[1] - y)
    if r > l and b > t:
        canvas.alpha_composite(tile.crop((l, t, r, b)), (x + l, y + t))


def render(s, state, levels, t):
    """Cuadro RGBA del overlay. `s` ya resuelto; state: "recording" o "processing"."""
    g = geometry(s)
    S = 2
    layer = Image.new("RGBA", (g["W"] * S, g["H"] * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    _dot(d, s, g, state, t, S)
    if state == "recording":
        _bars(layer, d, s, g, levels, t, S)
    else:
        _processing(layer, d, s, g, t, S)
    layer = layer.resize((g["W"], g["H"]), Image.LANCZOS)
    if s["glow"]:
        glow = layer.filter(ImageFilter.GaussianBlur(5))
        glow.putalpha(glow.getchannel("A").point(lambda v: min(255, v * 17 // 10)))
        layer = Image.alpha_composite(glow, layer)
    return Image.alpha_composite(_static(s, g), layer)
