"""Renderiza imágenes promocionales del overlay para el README.

Reproduce fielmente el diseño real de overlay.py (pastilla oscura, punto de
grabación, 14 barras con degradé cian→violeta) usando PIL, a alta resolución.
Correr: .venv\\Scripts\\python.exe assets\\render.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 8                      # escala (supersampling para bordes suaves)
W, H = 232, 56
BG = (14, 15, 22)          # #0e0f16
CYAN = (34, 211, 238)
VIOLET = (167, 139, 250)
NBARS = 14
OUT = Path(__file__).parent


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _canvas(pad=18):
    img = Image.new("RGBA", ((W + pad * 2) * S, (H + pad * 2) * S), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), pad * S


def _pill(d, ox, oy):
    # sombra suave para que la pastilla oscura se vea en fondos claros y oscuros
    for i, a in ((10, 30), (6, 45), (3, 60)):
        d.rounded_rectangle([ox - i, oy - i, ox + W * S + i, oy + H * S + i],
                            radius=26 * S, outline=(0, 0, 0, a), width=2 * S)
    d.rounded_rectangle([ox, oy, ox + W * S, oy + H * S], radius=24 * S, fill=BG + (255,))


def _dot(d, ox, oy, color):
    cx, cy = ox + 26 * S, oy + H * S // 2
    r = 6 * S
    d.ellipse([cx - r - 3 * S, cy - r - 3 * S, cx + r + 3 * S, cy + r + 3 * S],
              outline=color + (120,), width=1 * S)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (255,))


def render_recording():
    img, d, pad = _canvas()
    _pill(d, pad, pad)
    _dot(d, pad, pad, (255, 84, 112))                       # punto rojo
    cy = pad + H * S // 2
    heights = [0.30, 0.52, 0.74, 0.95, 0.60, 0.86, 1.0,
               0.72, 0.90, 0.55, 0.80, 0.62, 0.40, 0.26]
    x0 = pad + 48 * S
    bw = 5 * S
    for i in range(NBARS):
        h = (4 + heights[i] * 40) * S
        x = x0 + i * 12 * S
        col = lerp(CYAN, VIOLET, i / (NBARS - 1))
        d.rounded_rectangle([x - bw // 2, cy - h // 2, x + bw // 2, cy + h // 2],
                            radius=bw // 2, fill=col + (255,))
    img.resize((img.width // 2, img.height // 2), Image.LANCZOS).save(OUT / "overlay-recording.png")


def render_processing():
    img, d, pad = _canvas()
    _pill(d, pad, pad)
    _dot(d, pad, pad, (90, 160, 255))                       # punto azul
    cy = pad + H * S // 2
    for i in range(3):
        rd = (4 + i * 1.5) * S
        x = pad + (W // 2 - 12 + i * 14) * S
        col = lerp(CYAN, VIOLET, i / 2)
        d.ellipse([x - rd, cy - rd, x + rd, cy + rd], fill=col + (255,))
    img.resize((img.width // 2, img.height // 2), Image.LANCZOS).save(OUT / "overlay-processing.png")


if __name__ == "__main__":
    render_recording()
    render_processing()
    print("OK ->", [p.name for p in OUT.glob("overlay-*.png")])
