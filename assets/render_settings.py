"""Renderiza una imagen de la ventana de Ajustes para el README — 100% con PIL,
sin capturar la pantalla ni usar datos reales. Reproduce el diseño de settings.py
(tema oscuro) con datos de EJEMPLO inventados.
Correr: .venv\\Scripts\\python.exe assets\\render_settings.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

S = 2                       # supersampling
W, H = 502, 692
BG = (20, 22, 30)           # #14161e
TITLE = (26, 28, 38)
CARD = (28, 31, 43)         # #1c1f2b
FIELD = (37, 41, 55)        # #252937
FG = (231, 233, 240)        # #e7e9f0
HINT = (139, 144, 162)      # #8b90a2
ACCENT = (167, 139, 250)    # #a78bfa
WHITE = (255, 255, 255)
OUT = Path(__file__).parent

# datos de EJEMPLO (inventados, nada real)
VOCAB = "Claude, GitHub, Python, React, Docker, API, Whisper, PowerShell,\nKubernetes"
HIST = [
    "Recordá comprar los pasajes para el viernes a la tarde.",
    "The meeting was moved to 3 PM — update the calendar.",
    "Revisar el informe completo antes de enviarlo al cliente.",
]


def font(size, weight="regular"):
    files = {"regular": "segoeui.ttf", "semibold": "seguisb.ttf", "bold": "segoeuib.ttf"}
    for name in (files.get(weight), "segoeui.ttf"):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size * S)
        except OSError:
            continue
    return ImageFont.load_default()


def T(v):
    return int(v * S)


img = Image.new("RGB", (W * S, H * S), BG)
d = ImageDraw.Draw(img)


def rrect(x1, y1, x2, y2, r, **kw):
    d.rounded_rectangle([T(x1), T(y1), T(x2), T(y2)], radius=T(r), **kw)


def text(x, y, s, f, fill=FG, anchor="la"):
    d.text((T(x), T(y)), s, font=f, fill=fill, anchor=anchor)


# ── barra de título ──
d.rectangle([0, 0, W * S, T(30)], fill=TITLE)
text(12, 15, "Dictalo", font(10), fill=(200, 203, 214), anchor="lm")
# controles de ventana
d.line([T(446), T(15), T(456), T(15)], fill=(170, 174, 186), width=S)                 # min
d.rectangle([T(468), T(10), T(478), T(20)], outline=(170, 174, 186), width=S)          # max
d.line([T(490), T(10), T(498), T(20)], fill=(210, 130, 140), width=S)                  # close X
d.line([T(498), T(10), T(490), T(20)], fill=(210, 130, 140), width=S)

# ── contenido ──
text(22, 62, "Ajustes de Dictalo", font(17, "semibold"), fill=WHITE, anchor="lm")


def combo(y, label, value):
    text(22, y + 13, label, font(11), anchor="lm")
    rrect(98, y, 480, y + 27, 4, fill=FIELD)
    text(108, y + 13, value, font(11), anchor="lm")
    # flecha
    ax = 465
    d.polygon([(T(ax), T(y + 11)), (T(ax + 10), T(y + 11)), (T(ax + 5), T(y + 17))], fill=FG)


combo(100, "Micrófono", "Micrófono por defecto")
combo(138, "Atajo", "F9")

# checkbox
rrect(22, 182, 35, 195, 2, outline=(90, 95, 110), width=S)
text(43, 189, "Limpiar texto con IA (requiere GEMINI_API_KEY)", font(10), anchor="lm")

# vocabulario
text(22, 226, "Vocabulario — nombres/términos que usás", font(12, "semibold"), fill=WHITE, anchor="lm")
text(22, 247, "Separados por coma. Mejora que Whisper los acierte. Al instante.", font(9), fill=HINT, anchor="lm")
rrect(22, 262, 480, 352, 4, fill=FIELD, outline=CARD, width=S)
for i, line in enumerate(VOCAB.split("\n")):
    text(31, 278 + i * 20, line, font(11), anchor="lm")

# botón Guardar
rrect(372, 364, 480, 402, 4, fill=ACCENT)
text(426, 383, "Guardar", font(11, "semibold"), fill=(19, 20, 27), anchor="mm")

# historial
text(22, 430, "Historial (respaldo)", font(12, "semibold"), fill=WHITE, anchor="lm")
text(22, 451, "Últimos dictados. Si alguno no se pegó, recuperalo acá.", font(9), fill=HINT, anchor="lm")
rrect(22, 468, 480, 578, 6, fill=CARD)
for i, t in enumerate(HIST):
    ry = 484 + i * 34
    short = (t[:52] + "…") if len(t) > 53 else t
    text(34, ry + 9, short, font(10), anchor="lm")
    rrect(392, ry, 468, ry + 20, 3, fill=FIELD)
    text(430, ry + 10, "Copiar", font(9), anchor="mm")

img.resize((W, H), Image.LANCZOS).save(OUT / "settings.png")
print("OK -> settings.png", (W, H))
