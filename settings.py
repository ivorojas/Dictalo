"""Ventanas de Ajustes e Historial de Dictado App.

Todo se guarda solo (no hay botón Guardar): el micrófono y el vocabulario aplican
al instante y el atajo se re-arma en vivo (callback on_hotkey de main).
La limpieza con IA (Gemini) sigue existiendo en config/cleaner pero no se muestra:
el dueño no la usa.
"""
import time
import tkinter as tk
from datetime import datetime
from types import SimpleNamespace

from PIL import ImageTk

import history
import ui
from brand import APP_NAME, __version__, make_icon
from ui import F

HOTKEYS = [("F9", "<f9>"), ("F8", "<f8>"), ("F10", "<f10>"),
           ("Ctrl+Alt+D", "<ctrl>+<alt>+d"), ("Ctrl+Shift+Espacio", "<ctrl>+<shift>+<space>")]
PREVIEW = 3
W_SETTINGS, W_HISTORY = 560, 600
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

_win = None
_hist_win = None


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

    def __init__(self, config, on_hotkey=None, status=None):
        from injector import _clipboard_set
        self.config = config
        self.save = config.save
        self.on_hotkey = on_hotkey or (lambda: None)
        self.status = status or (lambda: ("Listo", "ok"))
        self.history = history.get
        self.history_version = lambda: history.version
        self.clear_history = history.clear
        self.copy = _clipboard_set
        self.devices = input_devices


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
        mic_index=-1, hotkey="<f9>", hotkey_display="F9",
        vocabulary="Claude, GitHub, Python, React, TypeScript, Docker, Kubernetes, Figma, Notion, "
                   "Slack, Vercel, Supabase, Stripe, Tailwind, PostgreSQL, Whisper, PowerShell, "
                   "VS Code, Linear, Jira")
    return SimpleNamespace(
        config=cfg, save=lambda: None, on_hotkey=lambda: None,
        status=lambda: ("Listo · GPU", "ok"),
        history=lambda: list(items), history_version=lambda: 0, clear_history=items.clear,
        copy=lambda text: None,
        devices=lambda: [("Predeterminado de Windows", -1),
                         ("Micrófono (USB Audio Device)", 1),
                         ("Micrófono (Realtek(R) Audio)", 2)])


# ── Ajustes ──────────────────────────────────────────────────────────────────
class SettingsView:
    def __init__(self, win, ctx):
        self.win, self.ctx = win, ctx
        self._hist_ver = None
        self._status = None
        self._toast_job = None
        self.area = ui.ScrollArea(win)
        self.area.pack(fill="both", expand=True)
        root = tk.Frame(self.area.inner, bg=ui.BG)
        root.pack(fill="both", expand=True, padx=(28, 16), pady=(22, 20))
        self._header(root)
        self._dictado(root)
        self._vocabulario(root)
        self._historial(root)
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

    # dictado: micrófono + atajo
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
        self.keys = tk.Frame(b, bg=ui.SURFACE)
        self.keys.pack(fill="x")
        self._render_keys()

    def _render_keys(self):
        for w in self.keys.winfo_children():
            w.destroy()
        for text, value in HOTKEYS:
            on = value == self.ctx.config.hotkey
            ui.Button(self.keys, text, kind="chip_on" if on else "chip", height=34, padx=14,
                      radius=17, font=F.body_sb,
                      command=lambda t=text, v=value: self._set_hotkey(t, v)).pack(
                side="left", padx=(0, 8))

    def _set_mic(self, index):
        self.ctx.config.mic_index = index
        self._saved()

    def _set_hotkey(self, text, value):
        if value == self.ctx.config.hotkey:
            return
        self.ctx.config.hotkey, self.ctx.config.hotkey_display = value, text
        self._saved()
        self.ctx.on_hotkey()
        self._render_keys()
        self._refresh_header()

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
                 ui.TEXT_3, bg=ui.BG).pack(anchor="w", pady=(9, 0))
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
            self._history_row(it)

    def _history_row(self, item):
        row = tk.Frame(self.hist_body, bg=ui.SURFACE)
        row.pack(fill="x", pady=10)
        btn = ui.IconButton(row, ui.I_COPY)
        btn.command = lambda: self._copy(item["text"], btn)
        btn.pack(side="right", padx=(12, 0))
        col = tk.Frame(row, bg=ui.SURFACE)
        col.pack(side="left", fill="x", expand=True)
        txt = ui.label(col, "", F.body)
        txt.pack(anchor="w", fill="x")
        ui.label(col, f"{when(item['t'])}  ·  {words(item['text'])}", F.tiny,
                 ui.TEXT_3).pack(anchor="w", pady=(3, 0))
        col.bind("<Configure>", lambda e: txt.configure(
            text=ui.ellipsize(item["text"], F.body, e.width - 2)))

    def _copy(self, text, btn):
        self.ctx.copy(text)
        btn.flash()
        self._toast("Copiado al portapapeles")

    def _open_history(self):
        open_history(self.win, self.ctx)

    # pie
    def _footer(self, p):
        foot = tk.Frame(p, bg=ui.BG)
        foot.pack(fill="x", pady=(28, 0))
        ui.label(foot, f"{APP_NAME} {__version__}", F.tiny, ui.TEXT_3, bg=ui.BG).pack(side="left")
        self.saved = ui.label(foot, "Los cambios se guardan solos", F.tiny, ui.TEXT_3, bg=ui.BG)
        self.saved.pack(side="right")

    def _saved(self):
        self.ctx.save()
        self._toast("Guardado")

    def _toast(self, text):
        self.saved.configure(text=f"✓ {text}", fg=ui.SUCCESS)
        if self._toast_job:
            self.win.after_cancel(self._toast_job)

        def back():
            self._toast_job = None
            if self.saved.winfo_exists():
                self.saved.configure(text="Los cambios se guardan solos", fg=ui.TEXT_3)
        self._toast_job = self.win.after(1800, back)

    def _poll(self):
        """Refresca el historial y el estado mientras la ventana está abierta."""
        if not self.win.winfo_exists():
            return
        if self.ctx.history_version() != self._hist_ver:
            self._render_history()
        if self.ctx.status() != self._status:
            self._refresh_header()
        self.win.after(1500, self._poll)


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


def open_settings(root, config, on_hotkey=None, status=None):
    global _win
    if _win is not None and _win.winfo_exists():
        _win.deiconify()
        _win.lift()
        _win.focus_force()
        return
    ui.init(root)
    win = tk.Toplevel(root)
    _win = win
    win.withdraw()
    win.title(APP_NAME)
    win.configure(bg=ui.BG)
    win.resizable(False, True)
    win.minsize(W_SETTINGS, 420)
    view = SettingsView(win, Context(config, on_hotkey, status))
    ui.set_icon(win)
    max_h = win.winfo_screenheight() - 110
    ui.show_window(win, W_SETTINGS, max_h, fit=lambda: min(max_h, view.content_height()))
    win.bind("<Escape>", lambda e: win.destroy())


def selftest(root):
    """Construye Ajustes e Historial con datos de ejemplo SIN mostrarlos (ventanas
    retiradas: no aparecen ni roban foco) y los destruye. Verifica que el .exe arma
    bien la interfaz: fuentes, imágenes suavizadas (PIL→Tk) y componentes."""
    ui.init(root)
    ctx = sample_context()
    for View in (SettingsView, HistoryView):
        win = tk.Toplevel(root)
        win.withdraw()
        View(win, ctx)
        win.update_idletasks()
        win.destroy()
    ui.shape(300, 120, 14, fill=ui.SURFACE, border=ui.BORDER)
    ui.shape(120, 34, 17, grad=(ui.CYAN, ui.VIOLET))
    return True
