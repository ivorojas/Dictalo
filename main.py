"""
Dictado App: dictado por voz para Windows
=========================================
Tap F9 → grabás (overlay flotante) → tap F9 → Whisper transcribe → pega en tu campo.
Corre en 2do plano (tray). Ajustes desde el ícono.
"""
import atexit
import ctypes
import faulthandler
import os
import queue
import subprocess
import sys
import threading
import time
import winsound
from datetime import datetime

from config import APP_DIR, migrate_legacy_data

# El autotest no toca los datos del usuario (ni migra ni escribe en ~/.dictado).
_SELFTEST = "--selftest-ui" in sys.argv
if not _SELFTEST:
    migrate_legacy_data()   # antes de abrir el log: la carpeta de datos puede moverse


class _Stamped:
    """Log con la hora al principio de cada línea (para saber cuándo pasó cada cosa)."""

    def __init__(self, f):
        self.f, self._bol = f, True

    def write(self, s):
        out = []
        for part in s.splitlines(keepends=True):
            if self._bol:
                out.append(time.strftime("%H:%M:%S "))
            out.append(part)
            self._bol = part.endswith("\n")
        self.f.write("".join(out))
        return len(s)

    def flush(self):
        self.f.flush()

    def fileno(self):
        return self.f.fileno()

    def __getattr__(self, name):          # isatty, encoding, etc. (algunas librerías los piden)
        return getattr(self.f, name)


def _setup_stdio():
    """Sin consola (app .exe) sys.stdout es None → cualquier print mata la app.
    Mandamos todo a un log. Append (no se trunca) para conservar evidencia entre
    reinicios — clave para diagnosticar fallas tras suspender; con un tope de
    tamaño para que no crezca sin límite."""
    if sys.stdout is None or sys.stderr is None:
        if _SELFTEST:
            import tempfile
            d, name = tempfile.gettempdir(), "dictado-selftest.log"
        else:
            d, name = str(APP_DIR), "dictado.log"
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        try:
            if os.path.getsize(p) > 2_000_000:
                os.replace(p, p + ".old")
        except OSError:
            pass
        f = open(p, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = _Stamped(f)
        # Una caída interna (de C, no de Python) mata el proceso sin Traceback y sin consola
        # donde verlo: faulthandler escribe en el log en qué parte del código estaba cada hilo.
        faulthandler.enable(file=f, all_threads=True)
        atexit.register(lambda: print("[salida] el proceso terminó"))
    else:
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
            except Exception:
                pass


_mutex = {"h": None}   # se suelta antes de auto-actualizar (el instalador lo espera libre)


def _already_running():
    k = ctypes.windll.kernel32
    k.CreateMutexW.restype = ctypes.c_void_p
    _mutex["h"] = k.CreateMutexW(None, False, "Global\\DictadoApp_SingleInstance")
    if k.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
        return True
    # La versión anterior ("Dictalo") abierta a la vez pelearía por el mismo atajo.
    k.OpenMutexW.restype = ctypes.c_void_p
    h = k.OpenMutexW(0x00100000, False, "Global\\Dictalo_SingleInstance")   # SYNCHRONIZE
    if h:
        k.CloseHandle(ctypes.c_void_p(h))
        return True
    return False


_setup_stdio()

import pystray
from pynput import keyboard as kb

import globalkey
import remote
import updater
import sounds
import history
import looks
import ui
from brand import APP_NAME, __version__, make_tray_icon
from config import Config
from recorder import NBANDS, Recorder
from transcriber import Transcriber
from cleaner import Cleaner
from injector import Injector, capture_foreground
from overlay import Overlay
from splash import Splash
from settings import open_settings, toggle_settings


def _selftest_ui():
    """`DictadoApp.exe --selftest-ui`: arma Ajustes e Historial con datos de ejemplo,
    sin mostrarlos, y anota el resultado en el log. Verifica la interfaz del .exe."""
    import tkinter as tk
    import traceback
    from settings import selftest
    fg = ui.foreground()
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()
    ui.restore_foreground(fg)          # crear el root lo activa un instante
    try:
        selftest(root)
        print("[selftest] interfaz OK")
    except Exception as e:
        traceback.print_exc()
        print(f"[selftest] FALLÓ: {e}")
    finally:
        root.destroy()
        ui.restore_foreground(fg)


class _HotKeys(kb.GlobalHotKeys):
    """GlobalHotKeys que también acepta teclas inyectadas. pynput las descarta, pero así
    llegan las de Cruce (teclado de la notebook usado en esta PC, vía SendInput): sin
    esto, F9 no respondía. Nuestro propio Ctrl+V inyectado no es un atajo: no hay eco."""

    def _on_press(self, key, injected):
        for hotkey in self._hotkeys:
            hotkey.press(self.canonical(key))

    def _on_release(self, key, injected):
        for hotkey in self._hotkeys:
            hotkey.release(self.canonical(key))


_DEAD_PEAK = 1e-5   # ≈ -100 dBFS: por debajo, el mic entregó silencio digital (stream "muerto")


def main():
    if _SELFTEST:
        return _selftest_ui()
    if getattr(sys, "frozen", False) and updater.installing():
        print("[update] hay una actualización instalándose: no arranco encima")
        ctypes.windll.user32.MessageBoxW(
            None, f"{APP_NAME} se está actualizando.\nSe vuelve a abrir sola en un minuto.",
            APP_NAME, 0x40 | 0x10000 | 0x40000)   # ICONINFORMATION | SETFOREGROUND | TOPMOST
        return
    if _already_running():
        winsound.Beep(300, 200)
        return

    config = Config()
    print("=" * 40)
    print(f"  {APP_NAME} {__version__} · inicio {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  Atajo: {config.hotkey_display}  | Cleanup: {'ON' if config.cleanup_enabled else 'OFF'}")
    print("=" * 40)

    transcriber = Transcriber(config)
    recorder = Recorder(config)
    cleaner = Cleaner(config)
    injector = Injector()
    overlay = Overlay()
    overlay.get_bands = lambda: recorder.bands   # barras = espectro real de tu voz
    overlay.get_style = lambda: looks.current(config)   # estilo elegido en Ajustes
    overlay.get_intensity = lambda: config.bar_intensity
    sounds.set_pack(config.sound_pack)
    ui.init(overlay.root)

    _busy = threading.Event()
    _ready = threading.Event()
    _target = {"hwnd": 0}
    _icon_ref = {"icon": None}
    _tray = {False: make_tray_icon(False), True: make_tray_icon(True)}

    role = config.remote_role if config.remote_role in ("main", "terminal") else "off"
    print(f"  Dos PCs (Cruce): {role}")

    def _warmup():
        if role != "terminal":             # la terminal no graba ni transcribe: no carga el modelo
            transcriber.load()
            recorder.warmup()
        history.get()          # de paso, borra lo que ya venció
        _ready.set()
        print("Listo para dictar. ✓" if role != "terminal" else "Listo: dicta con la PC principal. ✓")
        sounds.ready()
    threading.Thread(target=_warmup, daemon=True).start()

    Splash(overlay.root, _ready.is_set)   # tarjeta de carga centrada hasta que esté listo

    def set_rec_icon(v):
        ic = _icon_ref["icon"]
        if ic:
            ic.icon = _tray[v]
            ic.title = f"{APP_NAME} (grabando)" if v else APP_NAME

    def _notify(msg):
        ic = _icon_ref["icon"]
        if ic:
            try:
                ic.notify(msg, APP_NAME)
            except Exception:
                pass

    _gen = {"n": 0}   # id de grabación (para que un chequeo viejo no afecte a una nueva)

    _last_use = {"t": time.time()}

    # Dos PCs: `origin` es de dónde vino el F9 ("local" o "remote" = la otra PC vía Cruce). Un
    # dictado se devuelve a donde arrancó (_rec["origin"]): acá se pega o suena como siempre;
    # para "remote" se le mandan a la otra PC los estados (ventanita) y el texto.
    _rec = {"origin": "local", "id": 0}   # id = ms de inicio del dictado (crece aunque la app se reinicie)

    # Cruce manda los mensajes chicos por un canal ordenado y los grandes (un texto largo) por
    # otro: entre ellos no hay orden. Cada mensaje lleva "id" = número de dictado para que la
    # otra PC descarte lo viejo.
    def _show(origin, state):
        if origin == "remote":
            remote.send({"t": "state", "s": state, "id": _rec["id"]})
        else:
            overlay.set_state(state)

    def _fail(origin, msg=None):
        if origin == "remote":
            remote.send({"t": "error", "msg": msg or "", "id": _rec["id"]})
        else:
            sounds.error()
            if msg:
                _notify(msg)

    def _stream_levels(g):
        """Mientras graba un dictado de la otra PC, le manda el espectro (~10 por segundo)."""
        while recorder.is_recording and _gen["n"] == g:
            remote.send({"t": "state", "s": "recording", "id": _rec["id"],
                         "b": [round(float(b), 2) for b in recorder.bands]})
            time.sleep(0.1)

    def on_toggle(origin="local"):
        _last_use["t"] = time.time()
        if origin == "local" and role != "off" and remote.driving_other():
            print("[rec] F9 ignorado: el cursor está en la otra PC (Cruce se lo manda allá)")
            return
        if role == "terminal":
            return _toggle_on_main()
        if not _ready.is_set():
            if origin == "remote":
                _fail(origin, "La PC principal todavía está cargando el modelo.")
            else:
                sounds.wait()
            print("[rec] aún cargando el modelo")
            return

        if recorder.is_recording:
            origin = _rec["origin"]              # se devuelve a donde arrancó
            end_hwnd = capture_foreground() if origin == "local" else 0   # donde estás AL CORTAR
            set_rec_icon(False)
            _show(origin, "processing")
            audio = recorder.stop()
            n = 0 if audio is None else len(audio)
            tgt = end_hwnd or _target["hwnd"]    # si al cortar no hay ventana válida, la del inicio
            print(f"[rec] stop — {n / config.sample_rate:.1f}s · pico {recorder.peak:.2e} "
                  f"rms {recorder.last_rms:.4f} · pega en={'la otra PC' if origin == 'remote' else tgt}")
            if audio is None or n < config.min_frames:
                if origin == "local":
                    sounds.stop()
                _show(origin, "hidden")
                return
            if recorder.peak < _DEAD_PEAK:
                # Silencio digital puro: el dispositivo (p.ej. una interfaz USB) quedó
                # "colgado" u otra app lo tomó. Reabrimos el audio y avisamos, en vez de
                # transcribir nada y quedar en silencio.
                print("[rec] el micrófono entregó silencio digital — reinicio el audio")
                recorder.refresh()
                _fail(origin, "El micrófono no captó audio. Ya lo reinicié: probá de nuevo.")
                _show(origin, "hidden")
                return
            _busy.set()

            def work():
                try:
                    raw = transcriber.transcribe(audio)
                    print(f"[stt] {raw!r}")
                    if not raw:
                        recorder.refresh()          # por si el mic quedó en mal estado
                        _fail(origin, "No se entendió nada del audio. Probá de nuevo.")
                        return
                    text = cleaner.clean(raw)
                    history.add(text)               # respaldo, por si no se pega en ningún lado
                    if origin == "remote":
                        if remote.send({"t": "text", "text": text, "id": _rec["id"]}):
                            print(f"[ok] enviado a la otra PC: {text}")
                        else:
                            sounds.error()
                            _notify("No se pudo mandar el texto a la otra PC. Quedó en Ajustes → Historial.")
                    elif injector.inject(text, tgt):
                        sounds.done()
                        print(f"[ok] {text}")
                    else:
                        sounds.error()
                        _notify("No se pudo pegar. El texto quedó en Ajustes → Historial.")
                except Exception as e:
                    print(f"[error] {e}")
                    _fail(origin)
                finally:
                    _busy.clear()
                    _show(origin, "hidden")
            threading.Thread(target=work, daemon=True).start()
        else:
            if _busy.is_set():
                if origin == "remote":
                    _fail(origin, "La PC principal todavía está transcribiendo el dictado anterior.")
                else:
                    sounds.wait()
                return
            _rec["origin"], _rec["id"] = origin, int(time.time() * 1000)
            _target["hwnd"] = capture_foreground() if origin == "local" else 0
            try:
                recorder.start()
            except Exception as e:
                print(f"[rec] no pude abrir el micrófono: {e}")
                _fail(origin, "La PC principal no pudo abrir el micrófono.")
                return
            print(f"[rec] grabando (inicio en={'la otra PC' if origin == 'remote' else _target['hwnd']}, "
                  f"mic={recorder.device_name()})")
            set_rec_icon(True)

            _gen["n"] += 1
            g = _gen["n"]
            if origin == "remote":
                threading.Thread(target=_stream_levels, args=(g,), daemon=True).start()
            else:
                sounds.start()
                overlay.set_state("recording")

            def _check_mic():
                # Aviso temprano: si a los 3s el mic sigue en silencio digital, que no
                # hables 20s al vacío.
                if recorder.is_recording and _gen["n"] == g and recorder.peak < _DEAD_PEAK:
                    print("[rec] 3s sin señal del micrófono — aviso")
                    _fail(origin, "El micrófono no está captando audio. Cortá (F9) y probá de nuevo.")
            t = threading.Timer(3.0, _check_mic)
            t.daemon = True
            t.start()

    # Terminal (esta PC no transcribe): F9 le pide el dictado a la principal y lo que vuelve
    # (estados, texto) llega por _on_remote.
    _term = {"bands": [0.0] * NBANDS, "state": "hidden", "asked": 0.0, "id": 0}

    def _toggle_on_main():
        if not remote.send({"t": "toggle"}):
            sounds.error()
            _notify("No se pudo llegar a la PC principal. ¿Está prendida, con Cruce conectado y "
                    "Dictado App abierta?")
            return
        if _term["state"] == "hidden":
            asked = _term["asked"] = time.time()

            def _no_answer():
                if _term["asked"] == asked and _term["state"] == "hidden":
                    print("[cruce] la PC principal no respondió")
                    sounds.error()
                    _notify("La PC principal no respondió. ¿Tiene Dictado App abierta como Principal?")
            threading.Timer(3.0, _no_answer).start()

    def _on_remote(data):
        kind = data.get("t")
        if role == "main" and kind == "toggle":
            _toggles.put("remote")
        elif role == "terminal" and kind == "state":
            state, did = data.get("s"), data.get("id", 0)
            if state not in ("recording", "processing", "hidden") or did < _term["id"]:
                return                                  # de un dictado anterior
            if state == "recording" and (did != _term["id"] or _term["state"] != "recording"):
                sounds.start()
            if data.get("b"):
                _term["bands"] = data["b"]
            _term["id"], _term["state"] = did, state
            set_rec_icon(state == "recording")
            overlay.set_state(state)
        elif role == "terminal" and kind == "text":
            text = str(data.get("text", ""))
            if data.get("id", 0) >= _term["id"]:       # un texto que llega tarde no cierra un dictado nuevo
                _term["state"] = "hidden"
                overlay.set_state("hidden")
                set_rec_icon(False)
            if not text:
                return
            history.add(text)
            if injector.inject(text, capture_foreground()):   # en el campo donde estás AHORA
                sounds.done()
                print(f"[ok] recibido de la PC principal: {text}")
            else:
                sounds.error()
                _notify("No se pudo pegar. El texto quedó en Ajustes → Historial.")
        elif role == "terminal" and kind == "error":
            if data.get("id", 0) < _term["id"]:
                return
            _term["state"] = "hidden"
            overlay.set_state("hidden")
            set_rec_icon(False)
            sounds.error()
            if data.get("msg"):
                _notify(data["msg"])

    if role == "terminal":
        overlay.get_bands = lambda: _term["bands"]

    # pynput llama al callback DENTRO del hook de teclado de Windows. Si ahí se hace
    # algo lento (abrir el mic de una interfaz USB puede tardar cientos de ms),
    # Windows da de baja el hook en silencio y F9 deja de andar; y si ahí se lanza
    # una excepción, pynput detiene el listener. Por eso el hook solo encola y un
    # hilo aparte hace el trabajo, en orden.
    _toggles = queue.Queue()

    def _toggle_worker():
        while True:
            origin = _toggles.get()
            try:
                on_toggle(origin)
            except Exception as e:
                print(f"[error] toggle: {e}")
                sounds.error()
                overlay.set_state("hidden")
                set_rec_icon(False)
    threading.Thread(target=_toggle_worker, daemon=True).start()

    _hk = {"listener": None}

    def _arm_hotkey():
        old = _hk["listener"]
        if old is not None:
            try:
                old.stop()
            except Exception:
                pass
        lst = _HotKeys({config.hotkey: lambda: _toggles.put("local")})
        lst.daemon = True
        lst.start()
        _hk["listener"] = lst

    _arm_hotkey()
    link = remote.Link(_on_remote) if role != "off" else None   # mensajes de la otra PC (Cruce)

    def _watchdog():
        """Tras suspender/resumir, Windows da de baja el hook de teclado de pynput
        (F9 deja de responder) y el device de audio puede quedar stale. Detectamos
        el resume por el salto del reloj y re-armamos el hotkey + refrescamos audio."""
        last = time.time()
        while True:
            time.sleep(5)
            now = time.time()
            gap = now - last
            last = now
            if gap > 30:   # salto grande = la PC estuvo suspendida
                print(f"[watchdog] resume detectado (gap {gap:.0f}s) — re-armo hotkey + refresco audio")
                _arm_hotkey()
                if not recorder.is_recording:
                    recorder.refresh()
    threading.Thread(target=_watchdog, daemon=True).start()

    def _hotkey_changed():
        """Ajustes cambió el atajo: se re-arma en vivo, sin reiniciar."""
        _arm_hotkey()
        print(f"[hotkey] atajo ahora: {config.hotkey_display}")
        ic = _icon_ref["icon"]
        if ic:
            ic.update_menu()

    def _status():
        if not _ready.is_set():
            return ("Cargando modelo", "wait")
        if role == "terminal":
            return ("Usa la PC principal", "ok") if link and link.connected else ("Sin Cruce", "wait")
        return (f"Listo · {transcriber.device}", "ok")

    def _arm_global(hk, key, what):
        ok = hk.set(key)
        print(f"[atajo] {what}: {globalkey.label(key)} "
              f"({'activo' if ok else 'ya lo usa otra app' if ok is False else 'desactivado'})")
        if _icon_ref["icon"]:
            _icon_ref["icon"].update_menu()
        return ok

    def _set_open_hotkey(key):
        return _arm_global(open_key, key, "abrir Ajustes")

    def _set_copy_hotkey(key):
        return _arm_global(copy_key, key, "copiar el último dictado")

    def copy_last(*_):
        """Atajo (Alt+F1) o menú: el último dictado al portapapeles, sin abrir nada. Solo
        cuando lo pedís: si no, el portapapeles queda con lo que hayas copiado vos."""
        items = history.get()
        if not items:
            sounds.error()
            print("[copiar] no hay dictados para copiar")
            return
        from injector import _clipboard_set
        if _clipboard_set(items[0]["text"]):
            sounds.done()
            print("[copiar] último dictado copiado")
        else:
            sounds.error()
            print("[copiar] no pude usar el portapapeles")

    def _idle():
        return (_ready.is_set() and not recorder.is_recording and not _busy.is_set()
                and time.time() - _last_use["t"] > updater.IDLE_S)

    def _close_for_update():
        open_key.stop()
        copy_key.stop()
        icon.stop()

    upd = None
    if getattr(sys, "frozen", False) and config.auto_update:
        try:   # el actualizador nunca puede impedir que la app arranque
            upd = _start_updater(_notify, _idle, _close_for_update,
                                 lambda: _icon_ref["icon"] and _icon_ref["icon"].update_menu())
        except Exception as e:
            print(f"[update] no pude iniciar el actualizador: {e}")

    def _set_model(name):
        """Ajustes cambió el modelo (solo se ofrece sin NVIDIA): se recarga en 2do plano
        (la 1ra vez lo baja); mientras tanto el estado dice "Cargando modelo"."""
        config.whisper_model = name
        _ready.clear()

        def reload():
            try:
                transcriber.load()
            except Exception as e:
                print(f"[stt] no pude cargar {name}: {e}")
                sounds.error()
            else:
                sounds.ready()
            finally:
                _ready.set()
        threading.Thread(target=reload, daemon=True).start()

    def _restart(_role=None):
        """Cambiar el papel de Dos PCs cambia qué se carga al arrancar: se reinicia sola. Suelta
        los atajos y el mutex ANTES de abrir la nueva, así ella los puede tomar."""
        print("[salida] reinicio para aplicar el cambio de Dos PCs")
        open_key.stop()
        copy_key.stop()
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_mutex["h"]))
        args = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable,
                                                                      os.path.abspath(sys.argv[0])]
        subprocess.Popen(args, close_fds=True, creationflags=0x00000008)   # DETACHED_PROCESS
        icon.stop()
        os._exit(0)

    settings_kw = dict(on_hotkey=_hotkey_changed, status=_status, on_open_hotkey=_set_open_hotkey,
                       on_copy_hotkey=_set_copy_hotkey, on_role=_restart, updates=upd, on_model=_set_model,
                       stt_device=lambda: transcriber.device if _ready.is_set() else None)

    def do_settings(icon, item):
        overlay.root.after(0, lambda: open_settings(overlay.root, config, **settings_kw))

    def _open_key_pressed():
        back = capture_foreground()
        overlay.root.after(0, lambda: toggle_settings(overlay.root, config, back_to=back,
                                                      **settings_kw))

    open_key = globalkey.GlobalHotkey(_open_key_pressed)
    _set_open_hotkey(config.open_hotkey)
    copy_key = globalkey.GlobalHotkey(copy_last)
    _set_copy_hotkey(config.copy_hotkey)

    def do_quit(icon, item):
        print("[salida] Salir desde el menú del ícono")
        open_key.stop()
        copy_key.stop()
        icon.stop()
        overlay.stop()

    def _update_label(item):
        if upd is None:
            return ""
        if upd.state == "ready":
            return f"Instalar la versión {upd.version}"
        if upd.state == "checking":
            return "Buscando actualizaciones…"
        if upd.state in ("downloading", "installing"):
            return f"Bajando la versión {upd.version}…"
        return "Buscar actualizaciones"

    def do_update(icon, item):
        """Del menú del ícono: instala si ya bajó; si no, busca ya y avisa el resultado."""
        if upd.state == "ready":
            upd.install_now()
            return
        upd.check_now()

        def report():
            time.sleep(0.5)
            for _ in range(120):
                if upd.state != "checking":
                    break
                time.sleep(0.5)
            icon.update_menu()
            msg = {"uptodate": f"Ya tenés la última versión ({__version__}).",
                   "downloading": f"Hay una versión nueva ({upd.version}). La estoy bajando; "
                                  "te aviso cuando esté lista.",
                   "error": "No se pudo buscar actualizaciones (¿sin internet?)."}.get(upd.state)
            if msg:
                _notify(msg)
        threading.Thread(target=report, daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem(f"{APP_NAME} {__version__}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda item: f"Atajo: {config.hotkey_display}", None, enabled=False),
        pystray.MenuItem(lambda item: "Ajustes" if config.open_hotkey == "none"
                         else f"Ajustes ({globalkey.label(config.open_hotkey)})",
                         do_settings, default=True),  # doble-clic abre esto
        pystray.MenuItem(lambda item: "Copiar el último dictado" if config.copy_hotkey == "none"
                         else f"Copiar el último dictado ({globalkey.label(config.copy_hotkey)})",
                         copy_last),
        pystray.MenuItem(_update_label, do_update, visible=upd is not None),
        pystray.MenuItem("Salir", do_quit),
    )
    icon = pystray.Icon("dictado", _tray[False], APP_NAME, menu)
    _icon_ref["icon"] = icon
    icon.run_detached()
    print("Tray arriba — cargando modelo en 2do plano...")
    overlay.run()
    print("[salida] terminó el loop principal de la interfaz")


def _start_updater(notify, is_idle, stop, refresh_menu):
    """Solo en el .exe instalado: avisa si recién se actualizó y busca versiones nuevas."""
    done = updater.just_updated()
    if done:
        print(f"[update] actualizada a {done}")
        threading.Timer(5, lambda: notify(f"Se actualizó a la versión {done}.")).start()

    def install(version, path):
        notify(f"Actualizando a la versión {version}. Vuelve sola en un minuto.")
        time.sleep(3)
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_mutex["h"]))
        updater.run_installer(path, sys.executable)
        stop()
        os._exit(0)

    def ready(version):
        notify(f"La versión {version} está lista: se instala sola cuando no estés dictando "
               "(o ya mismo desde el menú del ícono).")
        refresh_menu()

    return updater.Updater(is_idle, install, ready)


if __name__ == "__main__":
    main()
