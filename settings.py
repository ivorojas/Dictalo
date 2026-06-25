"""Ventana de ajustes — Toplevel del root del overlay, con tema oscuro moderno.
Incluye historial de respaldo de los últimos transcriptos (con botón Copiar)."""
import tkinter as tk
from tkinter import ttk

import history
from injector import _clipboard_set

HOTKEYS = [("F9", "<f9>"), ("F8", "<f8>"), ("F10", "<f10>"),
           ("Ctrl+Alt+D", "<ctrl>+<alt>+d"), ("Ctrl+Shift+Espacio", "<ctrl>+<shift>+<space>")]

BG = "#14161e"
CARD = "#1c1f2b"
FIELD = "#252937"
FG = "#e7e9f0"
HINT = "#8b90a2"
ACCENT = "#a78bfa"

_win = None


def _input_devices():
    import sounddevice as sd
    out = [("Micrófono por defecto", -1)]
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                out.append((f"{i}: {d['name']}", i))
    except Exception:
        pass
    return out


def _style(win):
    st = ttk.Style(win)
    try:
        st.theme_use("clam")
    except Exception:
        pass
    st.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10))
    st.configure("TFrame", background=BG)
    st.configure("Card.TFrame", background=CARD)
    st.configure("TLabel", background=BG, foreground=FG)
    st.configure("Card.TLabel", background=CARD, foreground=FG)
    st.configure("Header.TLabel", font=("Segoe UI Semibold", 15), foreground="#ffffff", background=BG)
    st.configure("Sub.TLabel", font=("Segoe UI Semibold", 11), foreground="#ffffff", background=BG)
    st.configure("Hint.TLabel", foreground=HINT, background=BG, font=("Segoe UI", 9))
    st.configure("TCheckbutton", background=BG, foreground=FG)
    st.map("TCheckbutton", background=[("active", BG)])
    st.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=FG,
                 arrowcolor=FG, bordercolor=FIELD, lightcolor=FIELD, darkcolor=FIELD)
    st.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)],
           selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", FG)])
    st.configure("Accent.TButton", background=ACCENT, foreground="#13141b",
                 font=("Segoe UI Semibold", 10), borderwidth=0, padding=(16, 8))
    st.map("Accent.TButton", background=[("active", "#b9a3ff"), ("pressed", "#9579f0")])
    st.configure("Mini.TButton", background=FIELD, foreground=FG, borderwidth=0, padding=(10, 4),
                 font=("Segoe UI", 9))
    st.map("Mini.TButton", background=[("active", "#313646")])
    return st


def open_settings(root, config):
    global _win
    if _win is not None and _win.winfo_exists():
        _win.lift(); return
    win = tk.Toplevel(root)
    _win = win
    win.title("Dictalo")
    win.geometry("500x660")
    win.resizable(False, False)
    win.configure(bg=BG)
    win.attributes("-topmost", True)
    _style(win)

    frm = ttk.Frame(win, padding=22)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(1, weight=1)

    ttk.Label(frm, text="Ajustes de Dictalo", style="Header.TLabel").grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))

    ttk.Label(frm, text="Micrófono").grid(row=1, column=0, sticky="w", pady=7)
    devs = _input_devices()
    names = [n for n, _ in devs]
    dev_var = tk.StringVar(value=next((n for n, i in devs if i == config.mic_index), names[0]))
    ttk.Combobox(frm, textvariable=dev_var, values=names, state="readonly").grid(
        row=1, column=1, sticky="ew", pady=7, padx=(12, 0))

    ttk.Label(frm, text="Atajo").grid(row=2, column=0, sticky="w", pady=7)
    hk_names = [n for n, _ in HOTKEYS]
    hk_var = tk.StringVar(value=next((n for n, v in HOTKEYS if v == config.hotkey), "F9"))
    ttk.Combobox(frm, textvariable=hk_var, values=hk_names, state="readonly").grid(
        row=2, column=1, sticky="ew", pady=7, padx=(12, 0))

    clean_var = tk.BooleanVar(value=config.cleanup_enabled)
    ttk.Checkbutton(frm, text="Limpiar texto con IA (requiere GEMINI_API_KEY)",
                    variable=clean_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=10)

    ttk.Label(frm, text="Vocabulario — nombres/términos que usás", style="Sub.TLabel").grid(
        row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
    ttk.Label(frm, text="Separados por coma. Mejora que Whisper los acierte. Al instante.",
              style="Hint.TLabel").grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 6))
    vocab = tk.Text(frm, height=4, wrap="word", font=("Segoe UI", 10),
                    bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
                    highlightthickness=1, highlightbackground=CARD, highlightcolor=ACCENT, padx=8, pady=6)
    vocab.grid(row=6, column=0, columnspan=2, sticky="ew", pady=4)
    vocab.insert("1.0", config.vocabulary or "")

    status = ttk.Label(frm, text="", style="Hint.TLabel")
    status.grid(row=7, column=0, sticky="w", pady=(6, 0))

    def save():
        config.mic_index = dict(zip(names, [i for _, i in devs]))[dev_var.get()]
        config.hotkey = dict(HOTKEYS)[hk_var.get()]
        config.hotkey_display = hk_var.get()
        config.cleanup_enabled = clean_var.get()
        config.vocabulary = vocab.get("1.0", "end").strip()
        config.save()
        status.config(text="Guardado ✓  ·  vocabulario al instante; mic/atajo al reiniciar")

    ttk.Button(frm, text="Guardar", style="Accent.TButton", command=save).grid(
        row=7, column=1, sticky="e", pady=(6, 0))

    # ── Historial de respaldo ────────────────────────────────────────────────
    ttk.Label(frm, text="Historial (respaldo)", style="Sub.TLabel").grid(
        row=8, column=0, columnspan=2, sticky="w", pady=(18, 0))
    ttk.Label(frm, text="Últimos dictados. Si alguno no se pegó, recuperalo acá.",
              style="Hint.TLabel").grid(row=9, column=0, columnspan=2, sticky="w", pady=(0, 6))

    box = ttk.Frame(frm, style="Card.TFrame", padding=8)
    box.grid(row=10, column=0, columnspan=2, sticky="ew")
    box.columnconfigure(0, weight=1)

    def copy(t):
        _clipboard_set(t)
        status.config(text="Copiado al portapapeles ✓")

    items = history.get()[:5]
    if not items:
        ttk.Label(box, text="(sin historial todavía)", style="Card.TLabel",
                  foreground=HINT).grid(row=0, column=0, sticky="w", padx=4, pady=4)
    else:
        for r, t in enumerate(items):
            short = (t[:54] + "…") if len(t) > 55 else t
            ttk.Label(box, text=short, style="Card.TLabel").grid(
                row=r, column=0, sticky="w", padx=4, pady=4)
            ttk.Button(box, text="Copiar", style="Mini.TButton",
                       command=(lambda x=t: copy(x))).grid(row=r, column=1, padx=(8, 4), pady=4)


if __name__ == "__main__":
    from config import Config
    r = tk.Tk(); r.withdraw()
    open_settings(r, Config())
    r.mainloop()
