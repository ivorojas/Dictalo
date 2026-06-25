"""
Dictalo — dictado por voz para Windows
======================================
Tap F9 → grabás (overlay flotante) → tap F9 → Whisper transcribe → pega en tu campo.
Corre en 2do plano (tray). Ajustes desde el ícono.
"""
import ctypes
import os
import sys
import threading
import winsound


def _setup_stdio():
    """Sin consola (app .exe) sys.stdout es None → cualquier print mata la app.
    Mandamos todo a un log."""
    if sys.stdout is None or sys.stderr is None:
        d = os.path.join(os.path.expanduser("~"), ".dictalo")
        os.makedirs(d, exist_ok=True)
        f = open(os.path.join(d, "dictalo.log"), "w", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = f
    else:
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
            except Exception:
                pass


def _already_running():
    ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\Dictalo_SingleInstance")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


_setup_stdio()

from PIL import Image, ImageDraw
import pystray
from pynput import keyboard as kb

import sounds
import history
from config import Config
from recorder import Recorder
from transcriber import Transcriber
from cleaner import Cleaner
from injector import Injector, capture_foreground
from overlay import Overlay
from splash import Splash
from settings import open_settings


def _icon(recording=False):
    s = 64
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (235, 70, 70, 255) if recording else (40, 200, 160, 255)  # rojo / verde-agua
    d.ellipse([5, 5, s - 5, s - 5], fill=color)
    # micrófono
    d.rounded_rectangle([s * 0.40, s * 0.24, s * 0.60, s * 0.56], radius=s * 0.1, fill=(255, 255, 255, 235))
    d.rectangle([s * 0.47, s * 0.54, s * 0.53, s * 0.70], fill=(255, 255, 255, 235))
    d.rectangle([s * 0.38, s * 0.70, s * 0.62, s * 0.74], fill=(255, 255, 255, 235))
    return img


def main():
    if _already_running():
        winsound.Beep(300, 200)
        return

    config = Config()
    print("=" * 40)
    print("  Dictalo")
    print(f"  Atajo: {config.hotkey_display}  | Cleanup: {'ON' if config.cleanup_enabled else 'OFF'}")
    print("=" * 40)

    transcriber = Transcriber(config)
    recorder = Recorder(config)
    cleaner = Cleaner(config)
    injector = Injector()
    overlay = Overlay()
    overlay.get_bands = lambda: recorder.bands   # barras = espectro real de tu voz

    _busy = threading.Event()
    _ready = threading.Event()
    _target = {"hwnd": 0}
    _icon_ref = {"icon": None}

    def _warmup():
        transcriber.load()
        recorder.warmup()
        _ready.set()
        print("Listo para dictar. ✓")
        sounds.ready()
    threading.Thread(target=_warmup, daemon=True).start()

    Splash(overlay.root, _ready.is_set)   # tarjeta de carga centrada hasta que esté listo

    def set_rec_icon(v):
        ic = _icon_ref["icon"]
        if ic:
            ic.icon = _icon(v)
            ic.title = "Dictalo — grabando" if v else "Dictalo"

    def on_toggle():
        if not _ready.is_set():
            sounds.wait()
            print("[rec] aún cargando el modelo")
            return

        if recorder.is_recording:
            set_rec_icon(False)
            overlay.set_state("processing")
            audio = recorder.stop()
            n = 0 if audio is None else len(audio)
            print(f"[rec] stop — {n / config.sample_rate:.1f}s")
            if audio is None or n < config.min_frames:
                sounds.stop()
                overlay.set_state("hidden")
                return
            _busy.set()
            tgt = _target["hwnd"]

            def work():
                try:
                    raw = transcriber.transcribe(audio)
                    print(f"[stt] {raw!r}")
                    if not raw:
                        sounds.stop()
                        return
                    text = cleaner.clean(raw)
                    history.add(text)               # respaldo, por si no se pega en ningún lado
                    injector.inject(text, tgt)
                    sounds.done()
                    print(f"[ok] {text}")
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
            _target["hwnd"] = capture_foreground()   # tu ventana, antes del overlay
            print(f"[rec] grabando (target={_target['hwnd']})")
            sounds.start()
            overlay.set_state("recording")
            set_rec_icon(True)
            recorder.start()

    listener = kb.GlobalHotKeys({config.hotkey: on_toggle})
    listener.daemon = True
    listener.start()

    def do_settings(icon, item):
        overlay.root.after(0, lambda: open_settings(overlay.root, config))

    def do_quit(icon, item):
        icon.stop()
        overlay.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Dictalo", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"Atajo: {config.hotkey_display}", None, enabled=False),
        pystray.MenuItem("Ajustes…", do_settings, default=True),  # doble-clic abre esto
        pystray.MenuItem("Salir", do_quit),
    )
    icon = pystray.Icon("dictalo", _icon(), "Dictalo", menu)
    _icon_ref["icon"] = icon
    icon.run_detached()
    print("Tray arriba — cargando modelo en 2do plano...")
    overlay.run()


if __name__ == "__main__":
    main()
