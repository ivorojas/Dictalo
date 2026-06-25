"""Sonidos suaves y breves (sintetizados con numpy, sin librerías externas).

Reemplazan a winsound.Beep (que es un cuadrado seco). Cada sonido es una mezcla
de senoidales con envolvente suave (ataque corto + decay) → sin clicks, agradable.
"""
import numpy as np

try:
    import sounddevice as sd
except Exception:
    sd = None

_SR = 44100


def _env(n, attack=0.008, decay=3.2):
    e = np.ones(n, dtype=np.float32)
    a = int(_SR * attack)
    if a > 0:
        e[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
    e *= np.exp(-np.linspace(0.0, decay, n, dtype=np.float32))
    return e


def _note(freq, dur, vol=0.22, harm=0.25):
    t = np.linspace(0, dur, int(_SR * dur), endpoint=False, dtype=np.float32)
    w = np.sin(2 * np.pi * freq * t) + harm * np.sin(2 * np.pi * 2 * freq * t)
    return (w / (1 + harm)) * _env(len(t)) * vol


def _seq(*notes):
    return np.concatenate(notes).astype(np.float32)


def _silence(dur):
    return np.zeros(int(_SR * dur), dtype=np.float32)


# Sonidos pregenerados (suaves, < ~250ms)
_READY = _seq(_note(523, 0.10), _note(784, 0.16))                 # do→sol, chime de "listo"
_START = _note(660, 0.09, vol=0.20)                              # blip de inicio
_STOP = _note(495, 0.08, vol=0.16)                               # blip de corte
_DONE = _note(880, 0.11, vol=0.18)                               # confirmación de pegado
_ERROR = _note(196, 0.20, vol=0.20, harm=0.1)                    # error grave y suave
_WAIT = _note(415, 0.10, vol=0.16)                               # "todavía cargando"


def _play(samples):
    if sd is None:
        return
    try:
        sd.play(samples, _SR)
    except Exception:
        pass


def ready():  _play(_READY)
def start():  _play(_START)
def stop():   _play(_STOP)
def done():   _play(_DONE)
def error():  _play(_ERROR)
def wait():   _play(_WAIT)
