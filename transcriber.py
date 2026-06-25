"""STT local con faster-whisper en CUDA."""
import os
import sys
from pathlib import Path

import numpy as np


def _register_cuda_dlls():
    """Registra las DLLs CUDA (cuBLAS/cuDNN) de los wheels nvidia-*-cu12 en el DLL
    search path. En Windows no entran solas y ctranslate2 falla con
    'cublas64_12.dll is not found'. Funciona en dev y en .exe congelado."""
    if sys.platform != "win32":
        return
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS) / "nvidia"
    else:
        base = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for sub in ("cublas", "cudnn", "cuda_nvrtc"):
        bin_dir = base / sub / "bin"
        if bin_dir.is_dir():
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


_register_cuda_dlls()


def _finalize(text: str) -> str:
    """Cierra con punto final (salvo que ya termine en un signo: ?, !, …, etc.) y
    deja un espacio al final, así dictados consecutivos quedan separados al pegar."""
    text = text.strip()
    if not text:
        return text
    if text[-1].isalnum():
        text += "."
    return text + " "


class Transcriber:
    def __init__(self, config):
        self.config = config
        self._model = None

    def load(self):
        from faster_whisper import WhisperModel
        dev, comp = self.config.whisper_device, self.config.whisper_compute
        print(f"  STT: {self.config.whisper_model} | {dev.upper()} {comp}")
        try:
            self._model = WhisperModel(self.config.whisper_model, device=dev, compute_type=comp)
        except Exception as e:
            print(f"  GPU no disponible ({e}); uso CPU.")
            self._model = WhisperModel(self.config.whisper_model, device="cpu", compute_type="int8")
        # warmup
        silence = np.zeros(self.config.sample_rate, dtype=np.float32)
        list(self._model.transcribe(silence, language=self.config.whisper_language or None)[0])

    def transcribe(self, audio: np.ndarray) -> str:
        lang = self.config.whisper_language or None
        if lang is None:
            lang = self._detect_es_en(audio)   # restringe la detección a en/es
        segments, _ = self._model.transcribe(
            audio,
            language=lang,
            beam_size=5,                        # precisión (mejor en palabras/nombres ambiguos)
            condition_on_previous_text=False,   # evita arrastrar contexto/repeticiones
            hotwords=(self.config.vocabulary or None),   # sesga hacia TUS términos/nombres
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )
        text = " ".join(s.text for s in segments).strip()
        return _finalize(text)

    def _detect_es_en(self, audio):
        """Detecta SOLO entre español e inglés (evita mis-detección a idiomas
        parecidos: portugués/italiano/catalán). Mismo costo que el auto-detect."""
        try:
            _, _, probs = self._model.detect_language(audio)
            p = dict(probs)
            return "es" if p.get("es", 0.0) >= p.get("en", 0.0) else "en"
        except Exception:
            return None
