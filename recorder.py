"""Captura de micrófono 16kHz mono + espectro en vivo para el overlay."""
from typing import Optional

import numpy as np
import sounddevice as sd

NBANDS = 14


class Recorder:
    def __init__(self, config):
        self.config = config
        self.is_recording = False
        self.level = 0.0
        self.bands = [0.0] * NBANDS    # espectro (FFT) en vivo, una por barra
        self._frames = []
        self._stream: Optional[sd.InputStream] = None

    def warmup(self):
        """La 1ra apertura del stream tarda ~1-2s; abrir/cerrar una vez deja el
        primer dictado real instantáneo."""
        try:
            s = sd.InputStream(
                samplerate=self.config.sample_rate, channels=1, dtype="float32",
                device=self.config.mic_index if self.config.mic_index >= 0 else None,
                blocksize=1024,
            )
            s.start(); s.stop(); s.close()
        except Exception:
            pass

    def start(self):
        self.level = 0.0
        self.bands = [0.0] * NBANDS
        self._frames = []
        self.is_recording = True
        self._stream = sd.InputStream(
            samplerate=self.config.sample_rate, channels=1, dtype="float32",
            device=self.config.mic_index if self.config.mic_index >= 0 else None,
            callback=self._cb, blocksize=1024,
        )
        self._stream.start()

    def _cb(self, indata, frames, time_info, status):
        self._frames.append(indata.copy())
        x = indata[:, 0].astype(np.float32)
        n = len(x)
        rms = float(np.sqrt(np.mean(x ** 2)))
        self.level = 0.55 * self.level + 0.45 * min(1.0, rms * 14)

        # Espectro por FFT → bandas log en el rango de voz (~80-4000Hz).
        # "shape" = forma del espectro (varía entre bandas) ; "loud" = volumen.
        try:
            spec = np.abs(np.fft.rfft(x * np.hanning(n)))
            sr = self.config.sample_rate
            bmin = max(1, int(80 * n / sr))
            bmax = min(len(spec) - 1, max(bmin + NBANDS, int(4000 * n / sr)))
            edges = np.logspace(np.log10(bmin), np.log10(bmax), NBANDS + 1).astype(int)
            raw = np.empty(NBANDS, dtype=np.float32)
            for j in range(NBANDS):
                a, b = edges[j], max(edges[j] + 1, edges[j + 1])
                raw[j] = spec[a:b].mean()
            shape = raw / (raw.max() + 1e-6)              # 0..1 relativo entre bandas
            # Compuerta de silencio + amplificación con curva: aunque hables bajito,
            # las barras se expanden bien y notable (más sensible/dinámico).
            gate = 0.004
            loud = 0.0 if rms < gate else min(1.0, ((rms - gate) * 38) ** 0.55)
            target = shape * loud
            prev = np.asarray(self.bands, dtype=np.float32)
            self.bands = (0.35 * prev + 0.65 * target).tolist()
        except Exception:
            pass

    def stop(self) -> Optional[np.ndarray]:
        self.is_recording = False
        self.level = 0.0
        self.bands = [0.0] * NBANDS
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return None
        return np.concatenate(self._frames).flatten()
