"""
Dictado App: dictado por voz para Windows
=========================================
Tap F9 → grabás (overlay flotante) → tap F9 → Whisper transcribe → pega en tu campo.
Corre en 2do plano (tray). Ajustes desde el ícono.
"""
import ctypes
import os
import queue
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
        sys.stdout = sys.stderr = f
    else:
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
            except Exception:
                pass


def _already_running():
    k = ctypes.windll.kernel32
    k.CreateMutexW(None, False, "Global\\DictadoApp_SingleInstance")
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

import sounds
import history
import looks
import ui
from brand import APP_NAME, __version__, make_tray_icon
from config import Config
from recorder import Recorder
from transcriber import Transcriber
from cleaner import Cleaner
from injector import Injector, capture_foreground
from overlay import Overlay
from splash import Splash
from settings import open_settings


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


_DEAD_PEAK = 1e-5   # ≈ -100 dBFS: por debajo, el mic entregó silencio digital (stream "muerto")


def main():
    if _SELFTEST:
        return _selftest_ui()
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
    sounds.set_pack(config.sound_pack)
    ui.init(overlay.root)

    _busy = threading.Event()
    _ready = threading.Event()
    _target = {"hwnd": 0}
    _icon_ref = {"icon": None}
    _tray = {False: make_tray_icon(False), True: make_tray_icon(True)}

    def _warmup():
        transcriber.load()
        recorder.warmup()
        history.get()          # de paso, borra lo que ya venció
        _ready.set()
        print("Listo para dictar. ✓")
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

    def on_toggle():
        if not _ready.is_set():
            sounds.wait()
            print("[rec] aún cargando el modelo")
            return

        if recorder.is_recording:
            end_hwnd = capture_foreground()      # donde estás AL CORTAR: ahí se pega
            set_rec_icon(False)
            overlay.set_state("processing")
            audio = recorder.stop()
            n = 0 if audio is None else len(audio)
            tgt = end_hwnd or _target["hwnd"]    # si al cortar no hay ventana válida, la del inicio
            print(f"[rec] stop — {n / config.sample_rate:.1f}s · pico {recorder.peak:.2e} "
                  f"rms {recorder.last_rms:.4f} · pega en={tgt}")
            if audio is None or n < config.min_frames:
                sounds.stop()
                overlay.set_state("hidden")
                return
            if recorder.peak < _DEAD_PEAK:
                # Silencio digital puro: el dispositivo (p.ej. una interfaz USB) quedó
                # "colgado" u otra app lo tomó. Reabrimos el audio y avisamos, en vez de
                # transcribir nada y quedar en silencio.
                print("[rec] el micrófono entregó silencio digital — reinicio el audio")
                recorder.refresh()
                sounds.error()
                _notify("El micrófono no captó audio. Ya lo reinicié: probá de nuevo.")
                overlay.set_state("hidden")
                return
            _busy.set()

            def work():
                try:
                    raw = transcriber.transcribe(audio)
                    print(f"[stt] {raw!r}")
                    if not raw:
                        recorder.refresh()          # por si el mic quedó en mal estado
                        sounds.error()
                        _notify("No se entendió nada del audio. Probá de nuevo.")
                        return
                    text = cleaner.clean(raw)
                    history.add(text)               # respaldo, por si no se pega en ningún lado
                    if injector.inject(text, tgt):
                        sounds.done()
                        print(f"[ok] {text}")
                    else:
                        sounds.error()
                        _notify("No se pudo pegar. El texto quedó en Ajustes → Historial.")
                except Exception as e:
                    print(f"[error] {e}")
                    sounds.error()
                finally:
                    _busy.clear()
                    overlay.set_state("hidden")
            threading.Thread(target=work, daemon=True).start()
        else:
            if _busy.is_set():
                sounds.wait()
                return
            _target["hwnd"] = capture_foreground()   # respaldo por si al cortar no hay ventana válida
            try:
                recorder.start()
            except Exception as e:
                print(f"[rec] no pude abrir el micrófono: {e}")
                sounds.error()
                return
            print(f"[rec] grabando (inicio en={_target['hwnd']}, mic={recorder.device_name()})")
            sounds.start()
            overlay.set_state("recording")
            set_rec_icon(True)

            _gen["n"] += 1
            g = _gen["n"]

            def _check_mic():
                # Aviso temprano: si a los 3s el mic sigue en silencio digital, que no
                # hables 20s al vacío.
                if recorder.is_recording and _gen["n"] == g and recorder.peak < _DEAD_PEAK:
                    print("[rec] 3s sin señal del micrófono — aviso")
                    sounds.error()
                    _notify("El micrófono no está captando audio. Cortá (F9) y probá de nuevo.")
            t = threading.Timer(3.0, _check_mic)
            t.daemon = True
            t.start()

    # pynput llama al callback DENTRO del hook de teclado de Windows. Si ahí se hace
    # algo lento (abrir el mic de una interfaz USB puede tardar cientos de ms),
    # Windows da de baja el hook en silencio y F9 deja de andar; y si ahí se lanza
    # una excepción, pynput detiene el listener. Por eso el hook solo encola y un
    # hilo aparte hace el trabajo, en orden.
    _toggles = queue.Queue()

    def _toggle_worker():
        while True:
            _toggles.get()
            try:
                on_toggle()
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
        lst = kb.GlobalHotKeys({config.hotkey: lambda: _toggles.put(1)})
        lst.daemon = True
        lst.start()
        _hk["listener"] = lst

    _arm_hotkey()

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
        return (f"Listo · {transcriber.device}", "ok")

    def do_settings(icon, item):
        overlay.root.after(0, lambda: open_settings(overlay.root, config,
                                                    on_hotkey=_hotkey_changed, status=_status))

    def do_quit(icon, item):
        icon.stop()
        overlay.stop()

    menu = pystray.Menu(
        pystray.MenuItem(APP_NAME, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda item: f"Atajo: {config.hotkey_display}", None, enabled=False),
        pystray.MenuItem("Ajustes", do_settings, default=True),  # doble-clic abre esto
        pystray.MenuItem("Salir", do_quit),
    )
    icon = pystray.Icon("dictado", _tray[False], APP_NAME, menu)
    _icon_ref["icon"] = icon
    icon.run_detached()
    print("Tray arriba — cargando modelo en 2do plano...")
    overlay.run()


if __name__ == "__main__":
    main()
