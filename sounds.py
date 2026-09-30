"""Sonidos breves sintetizados con numpy (sin archivos ni librerías externas).

Hay varios packs para elegir en Ajustes. Cada sonido es una mezcla de senoidales
con envolvente suave (ataque corto + decay) → sin clicks. "Silencio" no suena nada
(los avisos de error igual aparecen como notificación).
"""
import numpy as np

try:
    import sounddevice as sd
except Exception:
    sd = None

_SR = 44100

PACKS = [("suave", "Suave"), ("burbuja", "Burbuja"), ("digital", "Digital"),
         ("campana", "Campana"), ("silencio", "Silencio")]


def _t(dur):
    return np.linspace(0, dur, int(_SR * dur), endpoint=False, dtype=np.float32)


def _env(n, attack=0.008, decay=3.2):
    e = np.ones(n, dtype=np.float32)
    a = int(_SR * attack)
    if a > 0:
        e[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
    e *= np.exp(-np.linspace(0.0, decay, n, dtype=np.float32))
    return e


def _note(freq, dur, vol=0.22, harm=0.25):
    t = _t(dur)
    w = np.sin(2 * np.pi * freq * t) + harm * np.sin(2 * np.pi * 2 * freq * t)
    return (w / (1 + harm)) * _env(len(t)) * vol


def _chirp(f0, f1, dur, vol=0.17):
    """Barrido de frecuencia (efecto burbuja)."""
    t = _t(dur)
    phase = 2 * np.pi * (f0 * t + (f1 - f0) * t * t / (2 * dur))
    return np.sin(phase) * _env(len(t), attack=0.004, decay=4.0) * vol


def _beep(freq, dur, vol=0.25):
    """Pitido digital: onda cuasi-cuadrada suavizada (armónicos impares)."""
    t = _t(dur)
    w = sum(np.sin(2 * np.pi * freq * k * t) / k for k in (1, 3, 5))
    e = np.ones(len(t), dtype=np.float32)
    ramp = int(_SR * 0.004)
    e[:ramp] = np.linspace(0, 1, ramp)
    e[-ramp:] = np.linspace(1, 0, ramp)
    return (w / 1.53) * e * vol


def _bell(freq, dur, vol=0.18):
    """Campanita: parciales inarmónicos que se apagan a distinto ritmo."""
    t = _t(dur)
    w = np.zeros(len(t), dtype=np.float32)
    for mult, amp, dec in ((1.0, 1.0, 5.0), (2.76, 0.45, 8.0), (5.4, 0.2, 12.0)):
        w += amp * np.sin(2 * np.pi * freq * mult * t) * np.exp(-dec * t / dur)
    ramp = int(_SR * 0.003)
    w[:ramp] *= np.linspace(0, 1, ramp)
    return w / 1.65 * vol


def _seq(*parts):
    return np.concatenate(parts).astype(np.float32)


def _gap(dur):
    return np.zeros(int(_SR * dur), dtype=np.float32)


def _build(pack):
    if pack == "silencio":
        return {}
    if pack == "burbuja":
        return {"ready": _seq(_chirp(420, 700, 0.08), _gap(0.02), _chirp(560, 940, 0.1)),
                "start": _chirp(500, 900, 0.09), "stop": _chirp(760, 430, 0.09),
                "done": _seq(_chirp(700, 1050, 0.06), _gap(0.015), _chirp(900, 1300, 0.07)),
                "error": _chirp(260, 150, 0.22, vol=0.2), "wait": _chirp(480, 560, 0.08, vol=0.13)}
    if pack == "digital":
        return {"ready": _seq(_beep(880, 0.05), _gap(0.03), _beep(1320, 0.07)),
                "start": _beep(1046, 0.045), "stop": _beep(784, 0.045),
                "done": _seq(_beep(1175, 0.04), _gap(0.025), _beep(1568, 0.05)),
                "error": _seq(_beep(220, 0.08), _gap(0.03), _beep(196, 0.1)),
                "wait": _beep(620, 0.05, vol=0.18)}
    if pack == "campana":
        return {"ready": _seq(_bell(659, 0.25)[: int(_SR * 0.09)], _bell(988, 0.35)),
                "start": _bell(880, 0.22), "stop": _bell(660, 0.22),
                "done": _bell(1319, 0.3), "error": _bell(294, 0.4, vol=0.2),
                "wait": _bell(587, 0.18, vol=0.12)}
    return {"ready": _seq(_note(523, 0.10), _note(784, 0.16)),     # suave (el original)
            "start": _note(660, 0.09, vol=0.20), "stop": _note(495, 0.08, vol=0.16),
            "done": _note(880, 0.11, vol=0.18), "error": _note(196, 0.20, vol=0.20, harm=0.1),
            "wait": _note(415, 0.10, vol=0.16)}


def _mix(*layers):
    n = max(len(x) for x in layers)
    out = np.zeros(n, dtype=np.float32)
    for x in layers:
        out[:len(x)] += x
    return out


def _at(x, delay):
    return np.concatenate([_gap(delay), x])


def _lowpass(x, cutoff):
    """Filtro de un polo (saca la aspereza digital de los agudos), aplicado en frecuencia: al
    instante aunque el sonido sea largo. Con relleno de ceros, así no "da la vuelta"."""
    a = np.exp(-2 * np.pi * cutoff / _SR)
    size = 1 << int(np.ceil(np.log2(len(x) * 2)))
    w = 2 * np.pi * np.fft.rfftfreq(size)
    h = (1 - a) / (1 - a * np.exp(-1j * w))
    return np.fft.irfft(np.fft.rfft(x, size) * h, size)[:len(x)].astype(np.float32)


def _reverb(x, dur=1.1, mix=0.28, seed=3):
    """Cola de sala: convolución con ruido que decae y se oscurece (respuesta de impulso sintética)."""
    rng = np.random.default_rng(seed)
    n = int(_SR * dur)
    ir = rng.standard_normal(n).astype(np.float32) * np.exp(-np.linspace(0, 7.5, n, dtype=np.float32))
    ir = _lowpass(ir, 3800)
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x) + n].astype(np.float32)
    return _mix(x * (1 - mix), wet * mix * 1.8)


def _pluck(freq, dur, vol):
    """Nota "de cristal": 3 capas levemente desafinadas (coro) + un armónico suave, ataque redondo."""
    t = _t(dur)
    w = np.zeros(len(t), dtype=np.float32)
    for cents, amp in ((-6, 0.34), (0, 0.42), (6, 0.34)):
        f = freq * 2 ** (cents / 1200)
        w += amp * (np.sin(2 * np.pi * f * t) + 0.18 * np.sin(2 * np.pi * 2 * f * t))
    return w * _env(len(t), attack=0.012, decay=4.2) * vol


def _air(dur, vol, rise=True):
    """Brillo de aire: ruido filtrado que crece (o se apaga) muy suave."""
    rng = np.random.default_rng(11)
    n = int(_SR * dur)
    x = _lowpass(rng.standard_normal(n).astype(np.float32), 7000)
    x -= _lowpass(x, 2500)                       # queda la banda alta, sin graves
    shape = np.clip(np.sin(np.linspace(0, np.pi, n, dtype=np.float32)), 0, 1) ** (1.5 if rise else 3)
    return x * shape * vol


def _finish(x, peak=0.32):
    x = _lowpass(x, 9000)
    ramp = int(_SR * 0.01)
    x[-ramp:] *= np.linspace(1, 0, ramp, dtype=np.float32)
    return (x / (np.max(np.abs(x)) + 1e-9) * peak).astype(np.float32)


def _ai_sounds():
    # Activar: arpegio ascendente (Do mayor 9) de notas de cristal + brillo de aire que crece, en sala.
    on = _mix(*[_at(_pluck(f, 0.5, 0.6 - i * 0.05), i * 0.045)
                for i, f in enumerate((523.3, 659.3, 784.0, 987.8, 1174.7))],
              _at(_air(0.45, 0.05), 0.05))
    # Al pegar: acorde de campanas de cristal (quinta + octava) que se apaga despacio.
    done = _mix(_pluck(784.0, 0.9, 0.5), _at(_pluck(1174.7, 0.85, 0.42), 0.03),
                _at(_pluck(1568.0, 0.8, 0.32), 0.07), _at(_air(0.5, 0.035, rise=False), 0.02))
    return {"ai_on": _finish(_reverb(on), 0.30), "ai_done": _finish(_reverb(done, 1.3), 0.28)}


# Modo IA: iguales en todos los packs (se distinguen de propósito del resto); en "silencio", nada.
_AI = _ai_sounds()

_sounds = dict(_build("suave"), **_AI)


def set_pack(name):
    global _sounds
    _sounds = _build(name if name in dict(PACKS) else "suave")
    if _sounds:
        _sounds.update(_AI)


def _play(key):
    s = _sounds.get(key)
    if sd is None or s is None:
        return
    try:
        sd.play(s, _SR)
    except Exception:
        pass


def preview():
    """Muestra del pack: empezar + pegado."""
    if sd is None or "start" not in _sounds:
        return
    try:
        sd.play(_seq(_sounds["start"], _gap(0.28), _sounds["done"]), _SR)
    except Exception:
        pass


def ready():  _play("ready")
def start():  _play("start")
def stop():   _play("stop")
def done():   _play("done")
def error():  _play("error")
def wait():   _play("wait")
def ai_on():   _play("ai_on")
def ai_done(): _play("ai_done")
