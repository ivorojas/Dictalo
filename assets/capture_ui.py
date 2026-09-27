"""Genera las capturas del README (assets/settings.png y assets/history.png) desde
la interfaz REAL, con datos de ejemplo inventados.

La ventana se arma en pantalla pero invisible (alpha 0), atravesable por el mouse y
sin activarse; se fotografía con PrintWindow. Fuera de la pantalla Windows no pinta
los lienzos de Tk, por eso no se usa esa vía. Después se le compone un marco estilo
Windows 11 (barra de título oscura, esquinas redondeadas y sombra).
Correr: .venv\\Scripts\\python.exe assets\\capture_ui.py
"""
import ctypes
import sys
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import brand  # noqa: E402
import settings  # noqa: E402
import ui  # noqa: E402

u32 = ctypes.WinDLL("user32")
g32 = ctypes.WinDLL("gdi32")
u32.GetForegroundWindow.restype = wintypes.HWND
u32.SetForegroundWindow.argtypes = [wintypes.HWND]
u32.GetAncestor.restype = wintypes.HWND
u32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.GetWindowDC.restype = wintypes.HDC
u32.GetWindowDC.argtypes = [wintypes.HWND]
u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
u32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
u32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
g32.CreateCompatibleDC.restype = wintypes.HDC
g32.CreateCompatibleDC.argtypes = [wintypes.HDC]
g32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
g32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
g32.SelectObject.restype = wintypes.HGDIOBJ
g32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
g32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
g32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
g32.DeleteDC.argtypes = [wintypes.HDC]


class _BIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def _hidden_window(root, w, h):
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-alpha", 0.0)
    win.geometry(f"{w}x{h}+0+0")
    win.configure(bg=ui.BG)
    fg = u32.GetForegroundWindow()
    win.update_idletasks()                        # se mapea: si Windows la activa,
    if fg and u32.GetForegroundWindow() != fg:    # el foco vuelve en el acto
        u32.SetForegroundWindow(fg)
    hwnd = u32.GetAncestor(win.winfo_id(), 2) or win.winfo_id()
    u32.SetWindowLongW(hwnd, -20, u32.GetWindowLongW(hwnd, -20) | 0x08000000 | 0x80 | 0x20)
    return win


def _grab(win):
    hwnd = u32.GetAncestor(win.winfo_id(), 2) or win.winfo_id()
    r = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = u32.GetWindowDC(hwnd)
    mdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, w, h)
    old = g32.SelectObject(mdc, bmp)
    u32.PrintWindow(hwnd, mdc, 2)                 # PW_RENDERFULLCONTENT
    bih = _BIH(ctypes.sizeof(_BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bih), 0)
    g32.SelectObject(mdc, old)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")


def capture(win):
    for _ in range(6):
        win.update_idletasks()
        win.update()
        time.sleep(0.15)
        win.update()
        img = _grab(win)
        if img.getextrema() != ((0, 0), (0, 0), (0, 0)):
            return img
    raise RuntimeError("no se pudo capturar la ventana")


def frame(client, title):
    """Marco estilo Windows 11: barra de título oscura, esquinas y sombra."""
    cap, radius, pad = 32, 8, 36
    w, h = client.width, client.height + cap
    win = Image.new("RGB", (w, h), ui.BG)
    win.paste(client, (0, cap))
    d = ImageDraw.Draw(win)
    text = ImageFont.truetype("C:/Windows/Fonts/SegUIVar.ttf", 12)
    try:
        glyphs = ImageFont.truetype("C:/Windows/Fonts/SegoeIcons.ttf", 10)
    except OSError:
        glyphs = ImageFont.truetype("C:/Windows/Fonts/segmdl2.ttf", 10)
    win.paste(brand.make_icon(16), (12, 8), brand.make_icon(16))
    d.text((36, cap / 2), title, font=text, fill=ui.TEXT_2, anchor="lm")
    for i, (g, col) in enumerate(((ui.I_X, ui.TEXT_2), (ui.I_MAX, ui.TEXT_3), (ui.I_MIN, ui.TEXT_2))):
        d.text((w - 23 - i * 46, cap / 2), g, font=glyphs, fill=col, anchor="mm")

    mask = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * 4 - 1, h * 4 - 1], radius * 4, fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)
    border = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle([0, 0, w - 1, h - 1], radius,
                                             outline=ui.BORDER_HI, width=1)

    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("L", out.size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle([pad, pad + 10, pad + w, pad + h + 6], radius, fill=150)
    out.putalpha(shadow.filter(ImageFilter.GaussianBlur(16)))
    body = win.convert("RGBA")
    body.putalpha(mask)
    out.alpha_composite(body, (pad, pad))
    out.alpha_composite(border, (pad, pad))
    return out


def main():
    root = tk.Tk()
    root.withdraw()
    ui.init(root)
    ctx = settings.sample_context()
    try:
        win = _hidden_window(root, settings.W_SETTINGS, 1000)
        view = settings.SettingsView(win, ctx)
        win.update()
        win.geometry(f"{settings.W_SETTINGS}x{view.content_height()}+0+0")
        frame(capture(win), brand.APP_NAME).save(ROOT / "assets" / "settings.png")
        win.destroy()

        win = _hidden_window(root, settings.W_HISTORY, 700)
        settings.HistoryView(win, ctx)
        frame(capture(win), "Historial").save(ROOT / "assets" / "history.png")
        win.destroy()
    finally:
        root.destroy()
    print("OK -> assets/settings.png, assets/history.png")


if __name__ == "__main__":
    main()
