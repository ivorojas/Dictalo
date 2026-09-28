"""Ventanas de Ajustes, Historial y Apariencia de Dictado App.

Todo se guarda solo (no hay botón Guardar): micrófono, vocabulario, sonidos y la
ventanita aplican al instante; el atajo se re-arma en vivo (callback on_hotkey).
La limpieza con IA (Gemini) sigue existiendo en config/cleaner pero no se muestra:
el dueño no la usa.
"""
import time
import tkinter as tk
from datetime import datetime
from types import SimpleNamespace

from PIL import ImageTk

import globalkey
import history
import looks
import sounds
import ui
from brand import APP_NAME, __version__, make_icon
from ui import F

HOTKEYS = [("F9", "<f9>"), ("F8", "<f8>"), ("F10", "<f10>"),
           ("Ctrl+Alt+D", "<ctrl>+<alt>+d"), ("Ctrl+Shift+Espacio", "<ctrl>+<shift>+<space>")]
PREVIEW = 3
W_SETTINGS, W_HISTORY, W_LOOKS = 560, 600, 576
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

# Opciones de la ventanita, en el orden en que se muestran
LOOK_OPTIONS = {
    "shape": [("Píldora", "pill"), ("Redondeada", "rounded"), ("Recta", "square")],
    "size": [("Chica", "small"), ("Normal", "normal"), ("Grande", "large")],
    "bg_mode": [("Sólido", "solid"), ("Cristal", "glass"), ("Sin fondo", "none")],
    "border": [("Sin borde", "none"), ("Sutil", "subtle"), ("Color", "accent"),
               ("Degradé", "gradient")],
    "shadow": [("Con sombra", True), ("Sin sombra", False)],
    "dot": [("Halo", "halo"), ("Punto", "dot"), ("Anillo", "ring"), ("Micrófono", "mic"),
            ("Ninguno", "none")],
    "dot_anim": [("Latido", "pulse"), ("Parpadeo", "blink"), ("Fijo", "still")],
    "bars": [("Redondeadas", "rounded"), ("Rectas", "square"), ("Puntos", "dots"),
             ("Onda", "wave"), ("Espejo", "mirror"), ("Bloques", "blocks")],
    "bar_count": [("8", 8), ("14", 14), ("20", 20), ("28", 28)],
    "thickness": [("Finas", "thin"), ("Normales", "normal"), ("Gruesas", "thick")],
    "colors": [("Degradé", "gradient"), ("Un color", "solid"), ("Arcoíris", "rainbow"),
               ("Arcoíris animado", "rainbow_anim")],
    "glow": [("Con resplandor", True), ("Sin resplandor", False)],
    "speed": [("Suave", "smooth"), ("Normal", "normal"), ("Rápido", "snappy")],
    "processing": [("Puntos", "dots"), ("Órbita", "orbit"), ("Onda", "wave"), ("Barra", "bar")],
    "position": [("Abajo", "bottom"), ("Arriba", "top")],
}
BAR_COLORS = ["#22d3ee", "#38bdf8", "#6366f1", "#a78bfa", "#f472b6", "#fb7185", "#f97316",
              "#facc15", "#34d399", "#ffffff"]
BG_COLORS = ["#0e0f16", "#06060b", "#111827", "#1c2130", "#1e1b4b", "#150b07", "#06141c",
             "#f8fafc"]
DOT_COLORS = ["#ff5470", "#ef4444", "#f97316", "#facc15", "#34d399", "#22d3ee", "#a78bfa",
              "#ffffff"]

_win = None
_back_to = 0
_hist_win = None
_look_win = None


def input_devices():
    """[(nombre, índice)] de micrófonos: una sola API de audio (sin duplicados) y el
    nombre completo (la API por defecto, MME, los corta a 31 caracteres)."""
    import sounddevice as sd
    out = [("Predeterminado de Windows", -1)]
    try:
        devs = sd.query_devices()
        api = sd.default.hostapi
        names = [d["name"] for d in devs]
        for i, d in enumerate(devs):
            if d.get("max_input_channels", 0) <= 0 or d.get("hostapi") != api:
                continue
            name = d["name"]
            if any(k in name for k in ("Sound Mapper", "Asignador de sonido", "Primary Sound")):
                continue
            out.append((max((n for n in names if n.startswith(name)), key=len), i))
    except Exception:
        pass
    return out


def when(t, now=None):
    now = now or time.time()
    d = now - t
    if d < 60:
        return "recién"
    if d < 3600:
        return f"hace {int(d // 60)} min"
    dt = datetime.fromtimestamp(t)
    days = (datetime.fromtimestamp(now).date() - dt.date()).days
    if days == 0:
        return f"hoy, {dt:%H:%M}"
    if days == 1:
        return f"ayer, {dt:%H:%M}"
    return f"{_DIAS[dt.weekday()]}, {dt:%H:%M}"


def day_label(t, now=None):
    dt = datetime.fromtimestamp(t)
    days = (datetime.fromtimestamp(now or time.time()).date() - dt.date()).days
    if days == 0:
        return "Hoy"
    if days == 1:
        return "Ayer"
    return f"{_DIAS[dt.weekday()].capitalize()} {dt.day}/{dt.month}"


def words(text):
    n = len(text.split())
    return f"{n} palabra{'' if n == 1 else 's'}"


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


class Context:
    """Lo que las vistas necesitan del resto de la app (inyectable para pruebas)."""

    def __init__(self, config, on_hotkey=None, status=None, on_open_hotkey=None, updates=None):
        from injector import _clipboard_set
        self.config = config
        self.updates = updates          # updater.Updater (None fuera de la app instalada)
        self.save = config.save
        self.on_hotkey = on_hotkey or (lambda: None)
        self.on_open_hotkey = on_open_hotkey or (lambda key: None)
        self.status = status or (lambda: ("Listo", "ok"))
        self.history = history.get
        self.history_version = lambda: history.version
        self.clear_history = history.clear
        self.copy = _clipboard_set
        self.devices = input_devices

    @staticmethod
    def set_sound(pack):
        sounds.set_pack(pack)
        sounds.preview()


def sample_context():
    """Datos de ejemplo inventados (autotest del .exe e imágenes del README)."""
    now = time.time()
    items = [
        {"t": now - 90, "text": "Recordá que el viernes a la tarde tenemos la demo con el cliente, "
                                "así que el martes cerramos los cambios del checkout."},
        {"t": now - 60 * 38, "text": "Pasale a Martín el link del diseño nuevo y pedile que revise "
                                     "los textos de la pantalla de pagos."},
        {"t": now - 60 * 60 * 3, "text": "The deploy is scheduled for tomorrow morning, please "
                                         "double check the environment variables."},
        {"t": now - 86400 - 3600, "text": "Anotá: comprar pilas, llamar al dentista y reservar "
                                          "la cancha para el sábado."},
        {"t": now - 86400 * 2 + 600, "text": "Idea para el blog: cómo dictar código y mensajes "
                                             "sin tocar el teclado, con Whisper corriendo local."},
    ]
    cfg = SimpleNamespace(
        mic_index=-1, hotkey="<f9>", hotkey_display="F9", open_hotkey="ctrl+f1", sound_pack="suave",
        overlay_preset="aurora", overlay_custom={}, overlay_mine=[], bar_intensity=0.8,
        vocabulary="Claude, GitHub, Python, React, TypeScript, Docker, Kubernetes, Figma, Notion, "
                   "Slack, Vercel, Supabase, Stripe, Tailwind, PostgreSQL, Whisper, PowerShell, "
                   "VS Code, Linear, Jira")
    return SimpleNamespace(
        updates=SimpleNamespace(state="uptodate", version=None, progress=0.0, checked=now - 60 * 12,
                                check_now=lambda: None, install_now=lambda: None),
        config=cfg, save=lambda: None, on_hotkey=lambda: None, on_open_hotkey=lambda key: True,
        set_sound=lambda pack: None,
        status=lambda: ("Listo · GPU", "ok"),
        history=lambda: list(items), history_version=lambda: 0, clear_history=items.clear,
        copy=lambda text: None,
        devices=lambda: [("Predeterminado de Windows", -1),
                         ("Micrófono (USB Audio Device)", 1),
                         ("Micrófono (Realtek(R) Audio)", 2)])


class _Toast:
    """Texto del pie que muestra "✓ Guardado" un momento y vuelve a su mensaje."""

    def _toast_init(self, parent, idle):
        self._idle = idle
        self._toast_job = None
        self.saved = ui.label(parent, idle, F.tiny, ui.TEXT_3, bg=ui.BG)
        return self.saved

    def _toast(self, text, ok=True):
        self.saved.configure(text=f"✓ {text}" if ok else text, fg=ui.SUCCESS if ok else ui.WARN)
        if self._toast_job:
            self.win.after_cancel(self._toast_job)

        def back():
            self._toast_job = None
            if self.saved.winfo_exists():
                self.saved.configure(text=self._idle, fg=ui.TEXT_3)
        self._toast_job = self.win.after(1800 if ok else 4500, back)


# ── Ajustes ──────────────────────────────────────────────────────────────────
class SettingsView(_Toast):
    def __init__(self, win, ctx):
        self.win, self.ctx = win, ctx
        self._hist_ver = None
        self._status = None
        self.area = ui.ScrollArea(win)
        self.area.pack(fill="both", expand=True)
        root = tk.Frame(self.area.inner, bg=ui.BG)
        root.pack(fill="both", expand=True, padx=(28, 16), pady=(22, 20))
        self._header(root)
        self._historial(root)      # primero: casi siempre se abre para copiar el último dictado
        self._dictado(root)
        self._ventanita(root)
        self._vocabulario(root)
        self._actualizaciones(root)
        self._footer(root)
        self._poll()

    def content_height(self):
        return self.area.inner.winfo_reqheight()

    # encabezado
    def _header(self, p):
        row = tk.Frame(p, bg=ui.BG)
        row.pack(fill="x", pady=(0, 26))
        self._logo = ImageTk.PhotoImage(make_icon(52))
        tk.Label(row, image=self._logo, bg=ui.BG, bd=0).pack(side="left")
        col = tk.Frame(row, bg=ui.BG)
        col.pack(side="left", padx=(14, 0))
        ui.label(col, APP_NAME, F.title, bg=ui.BG).pack(anchor="w")
        self.subtitle = ui.label(col, "", F.body, ui.TEXT_2, bg=ui.BG)
        self.subtitle.pack(anchor="w", pady=(2, 0))
        self.pill = ui.Pill(row)
        self.pill.pack(side="right", anchor="n", pady=(4, 0))
        self._refresh_header()

    def _refresh_header(self):
        self.subtitle.configure(text=f"Tocá {self.ctx.config.hotkey_display} para dictar en cualquier app")
        self._status = self.ctx.status()
        text, kind = self._status
        self.pill.set(text, ui.SUCCESS if kind == "ok" else ui.WARN)

    def _section(self, p, title):
        row = tk.Frame(p, bg=ui.BG)
        row.pack(fill="x", pady=(0, 10))
        ui.label(row, title, F.h2, bg=ui.BG).pack(side="left")
        return row

    # dictado: micrófono, atajo y sonidos
    def _dictado(self, p):
        self._section(p, "Dictado")
        card = ui.Card(p)
        card.pack(fill="x", pady=(0, 28))
        b = card.body
        ui.label(b, "Micrófono", F.body_sb).pack(anchor="w", pady=(0, 10))
        self.mic = ui.Select(b, self.ctx.devices(), self.ctx.config.mic_index, self._set_mic,
                             icon=ui.I_MIC)
        self.mic.pack(fill="x")
        ui.separator(b).pack(fill="x", pady=18)
        ui.label(b, "Atajo para dictar", F.body_sb).pack(anchor="w")
        ui.label(b, "Tocalo una vez para empezar y otra para terminar y pegar el texto.",
                 F.small, ui.TEXT_3).pack(anchor="w", pady=(3, 12))
        ui.ChipGroup(b, HOTKEYS, self.ctx.config.hotkey, self._set_hotkey, height=34).pack(fill="x")
        ui.separator(b).pack(fill="x", pady=18)
        ui.label(b, "Atajo para abrir esta ventana", F.body_sb).pack(anchor="w")
        ui.label(b, "Desde cualquier app. Enter copia el último dictado y cierra; Esc cierra.",
                 F.small, ui.TEXT_3).pack(anchor="w", pady=(3, 12))
        self.open_keys = ui.ChipGroup(b, globalkey.OPTIONS,
                                      getattr(self.ctx.config, "open_hotkey", "ctrl+f1"),
                                      self._set_open_hotkey, height=34)
        self.open_keys.pack(fill="x")
        ui.separator(b).pack(fill="x", pady=18)
        ui.label(b, "Sonidos", F.body_sb).pack(anchor="w")
        ui.label(b, "Al empezar, al terminar y si algo falla. Al elegir uno suena de muestra.",
                 F.small, ui.TEXT_3).pack(anchor="w", pady=(3, 12))
        ui.ChipGroup(b, [(name, pid) for pid, name in sounds.PACKS],
                     getattr(self.ctx.config, "sound_pack", "suave"), self._set_sound,
                     height=34).pack(fill="x")

    def _set_mic(self, index):
        self.ctx.config.mic_index = index
        self._saved()

    def _set_hotkey(self, value):
        self.ctx.config.hotkey = value
        self.ctx.config.hotkey_display = dict((v, t) for t, v in HOTKEYS)[value]
        self._saved()
        self.ctx.on_hotkey()
        self._refresh_header()

    def _set_open_hotkey(self, key):
        old = self.ctx.config.open_hotkey
        self.ctx.config.open_hotkey = key
        if self.ctx.on_open_hotkey(key) is False:
            self.ctx.config.open_hotkey = old
            self.ctx.on_open_hotkey(old)
            self.open_keys.set(old)
            self._toast(f"{globalkey.label(key)} ya lo usa otra app, elegí otro", ok=False)
            return
        self._saved()

    def _set_sound(self, pack):
        self.ctx.config.sound_pack = pack
        self._saved()
        self.ctx.set_sound(pack)

    # ventanita flotante
    def _ventanita(self, p):
        row = self._section(p, "Ventanita de grabación")
        ui.Button(row, "Cambiar apariencia", command=self._open_looks, kind="link", bg=ui.BG,
                  height=24, padx=2, font=F.small_sb, icon=ui.I_RIGHT, icon_right=True).pack(
            side="right", pady=(2, 0))
        card = ui.Card(p)
        card.pack(fill="x", pady=(0, 28))
        b = card.body
        self.stage = ui.Stage(b, get_style=lambda: looks.current(self.ctx.config), height=112,
                              fps=24, get_intensity=self._intensity)
        self.stage.configure(cursor="hand2")
        self.stage.bind("<ButtonRelease-1>", lambda e: self._open_looks())
        self.stage.pack(fill="x")
        row2 = tk.Frame(b, bg=ui.SURFACE)
        row2.pack(fill="x", pady=(12, 0))
        self.look_name = ui.label(row2, "", F.body_sb)
        self.look_name.pack(side="left")
        ui.label(row2, "Elegí un estilo o armá el tuyo", F.small, ui.TEXT_3).pack(side="right")
        self._refresh_look()

        ui.separator(b).pack(fill="x", pady=18)
        head = tk.Frame(b, bg=ui.SURFACE)
        head.pack(fill="x")
        ui.label(head, "Intensidad de las barras", F.body_sb).pack(side="left")
        self.int_label = ui.label(head, "", F.small_sb, ui.ACCENT)
        self.int_label.pack(side="right")
        ui.label(b, "Cuánto se mueven con tu voz: mirá la vista previa mientras lo movés. "
                    "Solo cambia cómo se ve, no cómo te entiende.", F.small, ui.TEXT_3,
                 wraplength=440).pack(anchor="w", pady=(3, 8))
        ui.Slider(b, self._intensity(), on_change=self._set_intensity,
                  on_release=lambda v: self._saved()).pack(fill="x")
        ends = tk.Frame(b, bg=ui.SURFACE)
        ends.pack(fill="x", pady=(2, 0))
        ui.label(ends, "Sutil", F.tiny, ui.TEXT_3).pack(side="left")
        ui.label(ends, "Exagerada", F.tiny, ui.TEXT_3).pack(side="right")
        self._show_intensity()

    def _intensity(self):
        return getattr(self.ctx.config, "bar_intensity", looks.DEFAULT_INTENSITY)

    def _set_intensity(self, v):
        self.ctx.config.bar_intensity = round(v, 2)     # en vivo; se guarda al soltar
        self._show_intensity()

    def _show_intensity(self):
        v = self._intensity()
        word = "Sutil" if v < 0.25 else "Media" if v < 0.5 else "Alta" if v < 0.8 else "Muy alta"
        self.int_label.configure(text=f"{word} · {round(v * 100)}%")

    def _refresh_look(self):
        if self.look_name.winfo_exists():
            self.look_name.configure(text=f"Estilo: {looks.current_name(self.ctx.config)}")

    def _open_looks(self):
        self.stage.paused = True
        open_looks(self.win, self.ctx, on_change=self._refresh_look, on_close=self._looks_closed)

    def _looks_closed(self):
        if self.stage.winfo_exists():
            self.stage.paused = False
        self._refresh_look()

    # vocabulario
    def _vocabulario(self, p):
        row = self._section(p, "Vocabulario")
        self.vocab_count = ui.label(row, "", F.small, ui.TEXT_3, bg=ui.BG)
        self.vocab_count.pack(side="right", pady=(3, 0))
        card = ui.Card(p)
        card.pack(fill="x", pady=(0, 28))
        b = card.body
        ui.label(b, "Nombres y términos que usás seguido. Ayudan a que se escriban bien.",
                 F.small, ui.TEXT_2).pack(anchor="w", pady=(0, 14))
        self.tags = ui.TagCloud(b, on_remove=self._remove_term, max_rows=2)
        self.tags.pack(fill="x")
        self.add = ui.Field(b, placeholder="Agregar un nombre o término", on_submit=self._add_terms,
                            action_icon=ui.I_ADD)
        self.add.pack(fill="x", pady=(16, 0))
        self._render_terms()

    def _terms(self):
        seen, out = set(), []
        for t in self.ctx.config.vocabulary.split(","):
            t = t.strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out

    def _render_terms(self):
        terms = self._terms()
        self.tags.set_terms(terms)
        self.vocab_count.configure(text=plural(len(terms), "término", "términos"))

    def _save_terms(self, terms):
        self.ctx.config.vocabulary = ", ".join(terms)
        self._saved()
        self._render_terms()

    def _add_terms(self, raw):
        terms = self._terms()
        known = {t.lower() for t in terms}
        for t in raw.split(","):
            t = " ".join(t.split())
            if t and t.lower() not in known:
                known.add(t.lower())
                terms.append(t)
        self.add.clear()
        self._save_terms(terms)

    def _remove_term(self, term):
        self._save_terms([t for t in self._terms() if t != term])

    # historial
    def _historial(self, p):
        row = self._section(p, "Historial")
        self.see_all = ui.Button(row, "Ver todo", command=self._open_history, kind="link",
                                 bg=ui.BG, height=24, padx=2, font=F.small_sb, icon=ui.I_RIGHT,
                                 icon_right=True)
        card = ui.Card(p, pady=6)
        card.pack(fill="x")
        self.hist_body = card.body
        ui.label(p, f"Los dictados se borran solos a los {history.RETENTION_DAYS} días.", F.tiny,
                 ui.TEXT_3, bg=ui.BG).pack(anchor="w", pady=(9, 28))
        self._render_history()

    def _render_history(self):
        for w in self.hist_body.winfo_children():
            w.destroy()
        items = self.ctx.history()
        self._hist_ver = self.ctx.history_version()
        if items:
            self.see_all.update_content(text=f"Ver todo ({len(items)})")
            self.see_all.pack(side="right", pady=(2, 0))
        else:
            self.see_all.pack_forget()
            box = tk.Frame(self.hist_body, bg=ui.SURFACE)
            box.pack(fill="x", pady=20)
            ui.label(box, ui.I_HISTORY, F.icon_lg, ui.TEXT_3, anchor="center").pack()
            ui.label(box, "Todavía no dictaste nada", F.body_sb, anchor="center").pack(pady=(10, 2))
            ui.label(box, f"Tocá {self.ctx.config.hotkey_display} y hablá: lo que dictes aparece acá.",
                     F.small, ui.TEXT_3, anchor="center").pack()
            return
        for i, it in enumerate(items[:PREVIEW]):
            if i:
                ui.separator(self.hist_body).pack(fill="x")
            self._history_row(it, latest=i == 0)

    def _history_row(self, item, latest=False):
        """El último dictado va destacado: dos líneas y un botón Copiar grande."""
        row = tk.Frame(self.hist_body, bg=ui.SURFACE)
        row.pack(fill="x", pady=10)
        if latest:
            btn = ui.Button(row, "Copiar", kind="primary", icon=ui.I_COPY, height=34, padx=14,
                            font=F.small_sb)
            btn.command = lambda: self._copy_latest(item["text"], btn)
        else:
            btn = ui.IconButton(row, ui.I_COPY)
            btn.command = lambda: self._copy(item["text"], btn)
        btn.pack(side="right", padx=(12, 0), anchor="n" if latest else "center")
        col = tk.Frame(row, bg=ui.SURFACE)
        col.pack(side="left", fill="x", expand=True)
        lines = 2 if latest else 1
        txt = ui.label(col, "", F.body, justify="left")
        txt.pack(anchor="w", fill="x")
        ui.label(col, f"{'Último · ' if latest else ''}{when(item['t'])}  ·  {words(item['text'])}",
                 F.tiny, ui.ACCENT if latest else ui.TEXT_3).pack(anchor="w", pady=(3, 0))
        col.bind("<Configure>", lambda e: txt.configure(
            wraplength=max(50, e.width - 2),
            text=ui.ellipsize(item["text"], F.body, lines * (e.width - 2) - 70 * (lines - 1))))

    def _copy_latest(self, text, btn):
        self.ctx.copy(text)
        btn.update_content(text="Copiado", icon=ui.I_CHECK)
        self._toast("Copiado al portapapeles")

        def back():
            if btn.winfo_exists():
                btn.update_content(text="Copiar", icon=ui.I_COPY)
        btn.after(1500, back)

    def _copy(self, text, btn):
        self.ctx.copy(text)
        btn.flash()
        self._toast("Copiado al portapapeles")

    def copy_latest_and_close(self):
        """Enter: copia el último dictado y cierra (salvo que estés escribiendo en un campo)."""
        if isinstance(self.win.focus_get(), tk.Entry):
            return
        items = self.ctx.history()
        if items:
            self.ctx.copy(items[0]["text"])
        close_settings()

    def _open_history(self):
        open_history(self.win, self.ctx)

    # actualizaciones
    def _actualizaciones(self, p):
        self._section(p, "Actualizaciones")
        card = ui.Card(p)
        card.pack(fill="x")
        row = tk.Frame(card.body, bg=ui.SURFACE)
        row.pack(fill="x")
        self.upd_btn = ui.Button(row, "Buscar ahora", command=self._update_action, height=34,
                                 padx=14, font=F.small_sb)
        col = tk.Frame(row, bg=ui.SURFACE)
        col.pack(side="left", fill="x", expand=True)
        ui.label(col, f"Versión {__version__}", F.body_sb).pack(anchor="w")
        self.upd_text = ui.label(col, "", F.small, ui.TEXT_3, wraplength=320)
        self.upd_text.pack(anchor="w", pady=(3, 0))
        self._upd_seen = None
        self._refresh_update()

    def _update_view(self):
        """(texto, color, botón, tipo de botón) según el estado del actualizador."""
        u = self.ctx.updates
        if u is None:
            return "Se actualiza sola en la app instalada.", ui.TEXT_3, None, None
        v = u.version
        return {
            "idle": ("Busca versiones nuevas sola cada 6 horas.", ui.TEXT_3, "Buscar ahora", "secondary"),
            "checking": ("Buscando…", ui.TEXT_3, None, None),
            "uptodate": (f"Estás en la última versión · revisado {when(u.checked)}", ui.SUCCESS,
                         "Buscar ahora", "secondary"),
            "downloading": (f"Bajando la versión {v}… {round(u.progress * 100)}%", ui.ACCENT, None, None),
            "ready": (f"La versión {v} está lista. Se instala sola cuando no estés dictando.",
                      ui.ACCENT, "Instalar ahora", "primary"),
            "installing": (f"Instalando {v}: se cierra y vuelve sola en un minuto.", ui.ACCENT, None, None),
            "error": ("No se pudo buscar (¿sin internet?).", ui.WARN, "Probar de nuevo", "secondary"),
        }[u.state]

    def _refresh_update(self):
        u = self.ctx.updates
        key = u and (u.state, u.version, round(u.progress * 100), u.checked and when(u.checked))
        if key == self._upd_seen and u is not None:
            return
        self._upd_seen = key
        text, color, btn, kind = self._update_view()
        self.upd_text.configure(text=text, fg=color)
        if btn:
            self.upd_btn.update_content(text=btn, kind=kind)
            self.upd_btn.pack(side="right", padx=(12, 0))
        else:
            self.upd_btn.pack_forget()

    def _update_action(self):
        u = self.ctx.updates
        if u.state == "ready":
            u.install_now()
        else:
            u.check_now()
            u.state = "checking"
        self._refresh_update()

    # pie
    def _footer(self, p):
        foot = tk.Frame(p, bg=ui.BG)
        foot.pack(fill="x", pady=(28, 0))
        ui.label(foot, f"{APP_NAME} {__version__}", F.tiny, ui.TEXT_3, bg=ui.BG).pack(side="left")
        self._toast_init(foot, "Los cambios se guardan solos").pack(side="right")

    def _saved(self):
        self.ctx.save()
        self._toast("Guardado")

    def _poll(self):
        """Refresca el historial y el estado mientras la ventana está abierta."""
        if not self.win.winfo_exists():
            return
        if self.ctx.history_version() != self._hist_ver:
            self._render_history()
        if self.ctx.status() != self._status:
            self._refresh_header()
        self._refresh_update()
        self.win.after(1000, self._poll)


# ── Historial completo ───────────────────────────────────────────────────────
class HistoryView:
    def __init__(self, win, ctx):
        self.win, self.ctx = win, ctx
        self.query = ""
        top = tk.Frame(win, bg=ui.BG)
        top.pack(fill="x", padx=28, pady=(22, 0))
        row = tk.Frame(top, bg=ui.BG)
        row.pack(fill="x")
        ui.label(row, "Historial", F.title, bg=ui.BG).pack(side="left")
        self.count = ui.label(row, "", F.small, ui.TEXT_3, bg=ui.BG)
        self.count.pack(side="left", padx=(12, 0), pady=(7, 0))
        ui.label(top, f"Tus dictados de los últimos {history.RETENTION_DAYS} días. "
                      "Después se borran solos.", F.small, ui.TEXT_2, bg=ui.BG).pack(
            anchor="w", pady=(4, 16))
        self.search = ui.Field(top, placeholder="Buscar en tus dictados", icon=ui.I_SEARCH,
                               on_change=self._filter, bg=ui.BG)
        self.search.pack(fill="x")

        self.foot = tk.Frame(win, bg=ui.BG)
        self.foot.pack(side="bottom", fill="x", padx=28, pady=(12, 18))
        ui.separator(win).pack(side="bottom", fill="x")
        self.area = ui.ScrollArea(win)
        self.area.pack(fill="both", expand=True, padx=(28, 16), pady=(18, 0))
        self._render()
        self._footer()

    def _filter(self, q):
        self.query = q
        self._render()

    def _render(self):
        for w in self.area.inner.winfo_children():
            w.destroy()
        items = self.ctx.history()
        self.count.configure(text=plural(len(items), "dictado", "dictados"))
        q = self.query.strip().lower()
        shown = [it for it in items if q in it["text"].lower()] if q else items
        if not shown:
            box = tk.Frame(self.area.inner, bg=ui.BG)
            box.pack(fill="x", pady=60)
            ui.label(box, ui.I_SEARCH if items else ui.I_HISTORY, F.icon_lg, ui.TEXT_3, bg=ui.BG,
                     anchor="center").pack()
            ui.label(box, "Nada coincide con tu búsqueda" if items else "No hay dictados",
                     F.body_sb, bg=ui.BG, anchor="center").pack(pady=(12, 3))
            ui.label(box, "Probá con otra palabra." if items
                     else "Lo que dictes va a aparecer acá.", F.small, ui.TEXT_3, bg=ui.BG,
                     anchor="center").pack()
        else:
            groups = []
            for it in shown:
                d = day_label(it["t"])
                if not groups or groups[-1][0] != d:
                    groups.append((d, []))
                groups[-1][1].append(it)
            for d, its in groups:
                ui.label(self.area.inner, d, F.small_sb, ui.TEXT_3, bg=ui.BG).pack(
                    anchor="w", pady=(0, 8))
                card = ui.Card(self.area.inner, pady=4)
                card.pack(fill="x", pady=(0, 20))
                for i, it in enumerate(its):
                    if i:
                        ui.separator(card.body).pack(fill="x")
                    self._row(card.body, it)
        self.area.to_top()

    def _row(self, parent, item):
        row = tk.Frame(parent, bg=ui.SURFACE)
        row.pack(fill="x", pady=12)
        head = tk.Frame(row, bg=ui.SURFACE)
        head.pack(fill="x")
        hhmm = datetime.fromtimestamp(item["t"]).strftime("%H:%M")
        ui.label(head, f"{hhmm}  ·  {words(item['text'])}", F.tiny, ui.TEXT_3).pack(
            side="left", anchor="n", pady=(4, 0))
        btn = ui.Button(head, "Copiar", kind="ghost", icon=ui.I_COPY, height=28, padx=10,
                        radius=8, font=F.small_sb)
        btn.command = lambda: self._copy(item["text"], btn)
        btn.pack(side="right")
        txt = ui.label(row, item["text"], F.body, wraplength=W_HISTORY - 110)
        txt.pack(fill="x", pady=(4, 0))
        row.bind("<Configure>", lambda e: txt.configure(wraplength=max(100, e.width - 4)))

    def _copy(self, text, btn):
        self.ctx.copy(text)
        btn.update_content(text="Copiado", icon=ui.I_CHECK)
        btn.itemconfigure(btn._tx, fill=ui.SUCCESS)
        btn.itemconfigure(btn._ic, fill=ui.SUCCESS)

        def back():
            if btn.winfo_exists():
                btn.update_content(text="Copiar", icon=ui.I_COPY)
        btn.after(1400, back)

    def _footer(self, confirm=False):
        for w in self.foot.winfo_children():
            w.destroy()
        has = bool(self.ctx.history())
        ui.Button(self.foot, "Cerrar", command=self.win.destroy, kind="secondary", bg=ui.BG,
                  height=34, padx=18).pack(side="right")
        if not has:
            return
        if confirm:
            ui.label(self.foot, "¿Borrar todos los dictados?", F.small_sb, bg=ui.BG).pack(
                side="left")
            ui.Button(self.foot, "Borrar", command=self._clear, kind="danger_solid", bg=ui.BG,
                      height=30, padx=12, font=F.small_sb).pack(side="left", padx=(12, 6))
            ui.Button(self.foot, "Cancelar", command=self._footer, kind="ghost", bg=ui.BG,
                      height=30, padx=10, font=F.small_sb).pack(side="left")
        else:
            ui.Button(self.foot, "Borrar todo", command=lambda: self._footer(confirm=True),
                      kind="danger", icon=ui.I_DELETE, bg=ui.BG, height=34, padx=12).pack(
                side="left")

    def _clear(self):
        self.ctx.clear_history()
        self._render()
        self._footer()


# ── Apariencia de la ventanita ───────────────────────────────────────────────
class LooksView(_Toast):
    def __init__(self, win, ctx, on_change=None):
        self.win, self.ctx = win, ctx
        self.on_change = on_change or (lambda: None)
        self.hover = None
        self.tab = "styles"
        top = tk.Frame(win, bg=ui.BG)
        top.pack(fill="x", padx=28, pady=(22, 0))
        ui.label(top, "Ventanita de grabación", F.title, bg=ui.BG).pack(anchor="w")
        ui.label(top, "Elegí un estilo o armá el tuyo pieza por pieza. Se guarda solo.",
                 F.small, ui.TEXT_2, bg=ui.BG).pack(anchor="w", pady=(4, 14))
        self.stage = ui.Stage(top, get_style=self._stage_style, height=150, bg=ui.BG, fps=30,
                              get_intensity=lambda: getattr(ctx.config, "bar_intensity",
                                                            looks.DEFAULT_INTENSITY))
        self.stage.pack(fill="x")
        bar = tk.Frame(top, bg=ui.BG)
        bar.pack(fill="x", pady=(14, 0))
        self.tabs = ui.Segmented(bar, [("Estilos", "styles"), ("Personalizar", "custom")],
                                 "styles", self._switch, bg=ui.BG, height=34)
        self.tabs.pack(side="left")
        ui.Segmented(bar, [("Grabando", "recording"), ("Transcribiendo", "processing")],
                     "recording", self._set_state, bg=ui.BG, height=28).pack(side="right")

        foot = tk.Frame(win, bg=ui.BG)
        foot.pack(side="bottom", fill="x", padx=28, pady=(12, 18))
        ui.separator(win).pack(side="bottom", fill="x")
        ui.Button(foot, "Listo", command=win.destroy, kind="secondary", bg=ui.BG, height=34,
                  padx=20).pack(side="right")
        self._toast_init(foot, "Los cambios se aplican al instante").pack(side="left")

        self.area = ui.ScrollArea(win)
        self.area.pack(fill="both", expand=True, padx=(28, 16), pady=(16, 0))
        self._render()

    def _stage_style(self):
        return self.hover or looks.current(self.ctx.config)

    def _set_state(self, state):
        self.stage.state = state

    def _switch(self, tab):
        self.tab = tab
        self.tabs.set(tab)
        self._render()

    def _render(self):
        for w in self.area.inner.winfo_children():
            w.destroy()
        body = tk.Frame(self.area.inner, bg=ui.BG)
        body.pack(fill="both", expand=True, pady=(0, 8))
        (self._styles if self.tab == "styles" else self._custom)(body)
        self.area.to_top()

    # pestaña Estilos
    def _styles(self, body):
        cfg = self.ctx.config
        ui.label(body, "Prearmados", F.h2, bg=ui.BG).pack(anchor="w", pady=(0, 10))
        grid = ui.Flow(body, bg=ui.BG, gap=12, gapy=12)
        grid.pack(fill="x")
        for pid, name, _ in looks.PRESETS:
            grid.put(ui.StyleCard(grid, name, looks.preset(pid), cfg.overlay_preset == pid,
                                  on_pick=lambda p=pid: self._pick(p), on_hover=self._hover,
                                  bg=ui.BG))
        ui.label(body, "Tus estilos", F.h2, bg=ui.BG).pack(anchor="w", pady=(26, 3))
        ui.label(body, "Lo que armás en Personalizar y los estilos que guardaste con nombre.",
                 F.small, ui.TEXT_3, bg=ui.BG).pack(anchor="w", pady=(0, 10))
        mine = ui.Flow(body, bg=ui.BG, gap=12, gapy=12)
        mine.pack(fill="x")
        if cfg.overlay_custom:
            mine.put(ui.StyleCard(mine, "Personalizado", looks.resolve(cfg.overlay_custom),
                                  cfg.overlay_preset == "custom",
                                  on_pick=lambda: self._pick("custom"), on_hover=self._hover,
                                  bg=ui.BG))
        for it in cfg.overlay_mine:
            name = it.get("name", "")
            mine.put(ui.StyleCard(mine, name, looks.resolve(it.get("style")),
                                  cfg.overlay_preset == "mine:" + name,
                                  on_pick=lambda n=name: self._pick("mine:" + n),
                                  on_hover=self._hover, on_delete=lambda n=name: self._delete(n),
                                  bg=ui.BG))
        mine.put(ui.ActionCard(mine, ui.I_ADD, "Crear el tuyo", lambda: self._switch("custom"),
                               bg=ui.BG))

    def _hover(self, style):
        self.hover = style

    def _pick(self, sel):
        self.ctx.config.overlay_preset = sel
        self._changed()
        self._render()

    def _delete(self, name):
        cfg = self.ctx.config
        if cfg.overlay_preset == "mine:" + name:     # si era el elegido, queda como Personalizado
            cfg.overlay_custom = looks.current(cfg)
            cfg.overlay_preset = "custom"
        cfg.overlay_mine = [it for it in cfg.overlay_mine if it.get("name") != name]
        self.hover = None
        self._changed("Estilo borrado")
        self._render()

    # pestaña Personalizar
    def _custom(self, body):
        s = looks.current(self.ctx.config)

        def group(title):
            ui.label(body, title, F.h2, bg=ui.BG).pack(anchor="w", pady=(0, 10))
            card = ui.Card(body)
            card.pack(fill="x", pady=(0, 24))
            return card.body

        def row(parent, label, key, first=False):
            ui.label(parent, label, F.body_sb).pack(anchor="w", pady=(0 if first else 16, 9))
            ui.ChipGroup(parent, LOOK_OPTIONS[key], s[key],
                         lambda v, k=key: self._set(k, v)).pack(fill="x")

        def colors(parent, label, key, palette, first=False):
            ui.label(parent, label, F.body_sb).pack(anchor="w", pady=(0 if first else 16, 9))
            ui.Swatches(parent, palette, s[key], lambda v, k=key: self._set(k, v)).pack(fill="x")

        b = group("Forma y fondo")
        row(b, "Forma", "shape", first=True)
        row(b, "Tamaño", "size")
        row(b, "Fondo", "bg_mode")
        colors(b, "Color de fondo", "bg", BG_COLORS)
        row(b, "Borde", "border")
        row(b, "Sombra", "shadow")
        b = group("Punto de grabación")
        row(b, "Estilo", "dot", first=True)
        colors(b, "Color", "dot_color", DOT_COLORS)
        row(b, "Animación", "dot_anim")
        b = group("Barras de voz")
        row(b, "Estilo", "bars", first=True)
        row(b, "Cantidad", "bar_count")
        row(b, "Grosor", "thickness")
        row(b, "Colores", "colors")
        colors(b, "Color principal", "color1", BAR_COLORS)
        colors(b, "Segundo color (para degradé y borde)", "color2", BAR_COLORS)
        row(b, "Resplandor", "glow")
        row(b, "Movimiento", "speed")
        b = group("Mientras transcribe")
        row(b, "Animación", "processing", first=True)
        b = group("Posición")
        row(b, "Dónde aparece", "position", first=True)
        b = group("Guardar como estilo propio")
        ui.label(b, "Queda en Tus estilos para volver a usarlo cuando quieras.", F.small,
                 ui.TEXT_3).pack(anchor="w", pady=(0, 12))
        line = tk.Frame(b, bg=ui.SURFACE)
        line.pack(fill="x")
        ui.Button(line, "Guardar", command=self._save_mine, kind="primary", height=40,
                  padx=20).pack(side="right", padx=(10, 0))
        self.name_field = ui.Field(line, placeholder=f"Mi estilo {len(self.ctx.config.overlay_mine) + 1}",
                                   on_submit=lambda v: self._save_mine())
        self.name_field.pack(side="left", fill="x", expand=True)

    def _set(self, key, value):
        cfg = self.ctx.config
        st = looks.current(cfg)
        st[key] = value
        cfg.overlay_custom = st
        cfg.overlay_preset = "custom"
        self._changed()

    def _save_mine(self):
        cfg = self.ctx.config
        name = (self.name_field.value().strip() or self.name_field.placeholder)[:40]
        st = looks.current(cfg)
        cfg.overlay_mine = [it for it in cfg.overlay_mine if it.get("name") != name] + \
            [{"name": name, "style": st}]
        cfg.overlay_preset = "mine:" + name
        self._changed(f"Guardado como “{name}”")
        self._switch("styles")

    def _changed(self, msg="Guardado"):
        self.ctx.save()
        self._toast(msg)
        self.on_change()


# ── Apertura ─────────────────────────────────────────────────────────────────
def open_history(parent, ctx):
    global _hist_win
    if _hist_win is not None and _hist_win.winfo_exists():
        _hist_win.lift()
        _hist_win.focus_force()
        return
    win = tk.Toplevel(parent)
    _hist_win = win
    win.withdraw()
    win.title("Historial")
    win.configure(bg=ui.BG)
    win.transient(parent)
    win.minsize(480, 420)
    HistoryView(win, ctx)
    ui.set_icon(win)
    ui.show_window(win, W_HISTORY, min(720, win.winfo_screenheight() - 120), over=parent)
    win.bind("<Escape>", lambda e: win.destroy())


def open_looks(parent, ctx, on_change=None, on_close=None):
    global _look_win
    if _look_win is not None and _look_win.winfo_exists():
        _look_win.lift()
        _look_win.focus_force()
        return
    win = tk.Toplevel(parent)
    _look_win = win
    win.withdraw()
    win.title("Apariencia")
    win.configure(bg=ui.BG)
    win.transient(parent)
    win.resizable(False, True)
    win.minsize(W_LOOKS, 520)
    LooksView(win, ctx, on_change)
    ui.set_icon(win)
    ui.show_window(win, W_LOOKS, min(860, win.winfo_screenheight() - 110), over=parent)
    win.bind("<Escape>", lambda e: win.destroy())
    if on_close:
        win.bind("<Destroy>", lambda e: on_close() if e.widget is win else None, add="+")


def open_settings(root, config, on_hotkey=None, status=None, on_open_hotkey=None, back_to=0,
                  updates=None):
    """`back_to`: la ventana donde estabas al abrirla con el atajo; al cerrarla con
    Enter o Esc el foco vuelve ahí (para pegar el dictado copiado con Ctrl+V)."""
    global _win, _back_to
    if _win is not None and _win.winfo_exists():
        _back_to = back_to or _back_to
        ui.bring_to_front(_win)
        return
    _back_to = back_to
    ui.init(root)
    win = tk.Toplevel(root)
    _win = win
    win.withdraw()
    win.title(APP_NAME)
    win.configure(bg=ui.BG)
    win.resizable(False, True)
    win.minsize(W_SETTINGS, 420)
    view = SettingsView(win, Context(config, on_hotkey, status, on_open_hotkey, updates))
    ui.set_icon(win)
    max_h = win.winfo_screenheight() - 110
    ui.show_window(win, W_SETTINGS, max_h, fit=lambda: min(max_h, view.content_height()))
    ui.bring_to_front(win)
    win.bind("<Escape>", lambda e: close_settings())
    win.bind("<Return>", lambda e: view.copy_latest_and_close())


def settings_open():
    return _win is not None and _win.winfo_exists() and _win.state() == "normal"


def close_settings():
    """Cierra Ajustes. Si estabas en ella, el foco vuelve a la ventana desde donde la
    abriste; si estabas en otra app, no se toca."""
    global _win
    focused = False
    if _win is not None and _win.winfo_exists():
        focused = ui.foreground() == ui.hwnd_of(_win)
        _win.destroy()
    _win = None
    if focused and _back_to:
        from injector import _focus_window
        _focus_window(_back_to)


def toggle_settings(root, config, back_to=0, **kw):
    """El atajo global abre y cierra con la misma tecla: si Ajustes está abierta (aunque
    esté detrás de otra ventana) la cierra; si está cerrada o minimizada, la abre al frente."""
    if settings_open():
        close_settings()
    else:
        open_settings(root, config, back_to=back_to, **kw)


def selftest(root):
    """Construye Ajustes, Historial y Apariencia (sus dos pestañas) con datos de
    ejemplo SIN mostrarlos (no aparecen ni roban foco), dibuja todos los estilos de
    la ventanita y prueba la ventana en capas fuera de la pantalla."""
    ui.init(root)
    ctx = sample_context()
    for build in (lambda w: SettingsView(w, ctx), lambda w: HistoryView(w, ctx),
                  lambda w: LooksView(w, ctx), lambda w: LooksView(w, ctx)._switch("custom")):
        win = tk.Toplevel(root)
        win.withdraw()
        build(win)
        win.update_idletasks()
        win.destroy()
    win = tk.Toplevel(root)
    win.withdraw()
    view = SettingsView(win, ctx)
    ctx.updates.version = "9.9.9"
    for state in ("idle", "checking", "uptodate", "downloading", "ready", "installing", "error"):
        ctx.updates.state, ctx.updates.progress = state, 0.42
        view._refresh_update()
    ctx.updates.state = "uptodate"
    win.destroy()
    ui.shape(300, 120, 14, fill=ui.SURFACE, border=ui.BORDER)
    ui.shape(120, 34, 17, grad=(ui.CYAN, ui.VIOLET))
    for pid in looks.PRESET_IDS:
        s = looks.preset(pid)
        looks.render(s, "recording", looks.fake_levels(s["bar_count"], 1.0), 1.0)
        looks.render(s, "processing", [0.0] * s["bar_count"], 1.0)
    from overlay import LayeredWindow
    lw = LayeredWindow()
    ok = lw.show(looks.render(looks.preset("aurora"), "recording", [0.5] * 14, 0.5), -9000, -9000)
    lw.hide()
    lw.destroy()
    if not ok:
        raise RuntimeError("UpdateLayeredWindow falló")
    return True
