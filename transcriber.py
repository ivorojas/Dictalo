"""STT local con faster-whisper en CUDA."""
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

_WS = re.compile(r"\s+")
_TAIL_PAD_S = 0.5   # colchón de silencio al final (anti-alucinación al cortar en seco)

# Whisper, entrenado con subtítulos, alucina créditos de subtitulado sobre el
# silencio (típico al final): "Closed Captions by Red Bee Media", "Gracias por ver
# el video", etc. Esta lista negra los recorta del final. Frases DISTINTIVAS para no
# pisar texto real (p.ej. NO filtramos "subscribe" solo, que aparece en código).
_HALLU_END = re.compile(
    r"""(?ix)                         # ignorecase + verbose
    [\s.,!¡]*                         # separadores/puntuación previa
    (?:
        closed\ captions?\ by\ red\ bee\ media
      | closed\ caption(?:s|ing|ed)?(?:\ (?:provided\ )?by\ [^.!?,]{1,40})?
      | (?:www\.)?\s*[\w-]*\s*caption(?:s|ing)?\s*\.\s*(?:com|org|net)   # www.closedcaptioning.com
      | subtitl(?:es|ing)\ by\ red\ bee\ media
      | subtitles\ by\ the\ amara\.org\ community
      | subt[ií]tulos(?:\ realizados)?\ por\ la\ comunidad\ de\ amara\.org
      | thanks?\ for\ watching
      | thank\ you\ for\ watching
      | please\ subscribe(?:\ to\ [^.!¡]*)?
      | like\ and\ subscribe
      | gracias\ por\ ver(?:\ el)?(?:\ v[ií]deo)?
      | [¡!]*\s*suscr[ií]bete
    )
    [\s.,!¡]*$                        # hasta el final del texto
    """
)


def _strip_hallucinations(text: str) -> str:
    """Recorta del final los créditos de subtitulado que Whisper alucina sobre el
    silencio. Itera por si quedan varios apilados."""
    prev = None
    while prev != text:
        prev = text
        text = _HALLU_END.sub("", text).strip()
    return text


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


def _model_path(name):
    """Ruta local del modelo (lo baja solo la 1ra vez). En Windows sin modo desarrollador
    la caché de Hugging Face a veces falla al crear un enlace (WinError 1314) y al
    reintentar anda: sin esto, en una PC recién instalada caía a CPU aunque hubiera GPU."""
    from faster_whisper.utils import download_model
    for attempt in range(3):
        try:
            return download_model(name)
        except OSError as e:
            if attempt == 2:
                raise
            print(f"  descarga del modelo falló ({e}); reintento")
            time.sleep(1)


class _EsEnOnly:
    """Envuelve el modelo de ctranslate2 para que la detección de idioma que Whisper hace
    con la MISMA pasada del codificador (multilingual=True) elija solo entre español e
    inglés. Así en CPU hay una sola pasada (~7 s) en vez de dos, sin cambiar la regla."""
    _KEEP = ("<|es|>", "<|en|>")

    def __init__(self, model):
        self._m = model

    def __getattr__(self, name):
        return getattr(self._m, name)

    def detect_language(self, encoder_output):
        return [[r for r in res if r[0] in self._KEEP] or res
                for res in self._m.detect_language(encoder_output)]


def _finalize(text: str) -> str:
    """Normaliza espacios (junta saltos/tabs/espacios dobles en uno solo — los
    segmentos de Whisper traen espacio propio y al unirlos quedan dobles), cierra
    con punto final (salvo que ya termine en un signo: ?, !, …, etc.) y deja un
    espacio al final, así dictados consecutivos quedan separados al pegar."""
    text = _WS.sub(" ", text).strip()
    if not text:
        return text
    if text[-1].isalnum():
        text += "."
    return text + " "


class Transcriber:
    def __init__(self, config):
        self.config = config
        self._model = None
        self.device = "GPU"

    def load(self):
        from faster_whisper import WhisperModel
        dev, comp = self.config.whisper_device, self.config.whisper_compute
        print(f"  STT: {self.config.whisper_model} | {dev.upper()} {comp}")
        path = _model_path(self.config.whisper_model)
        try:
            if dev != "cuda":
                raise RuntimeError(f"device={dev}")
            self._model = WhisperModel(path, device=dev, compute_type=comp)
            self.device = "GPU"
        except Exception as e:
            # Sin NVIDIA (AMD, Intel, notebooks): CPU int8 con todos los hilos (faster-whisper
            # usa 4 por defecto; medido en un Ryzen de 6 núcleos: 12 hilos > 6 > 4).
            threads = max(4, os.cpu_count() or 4)
            print(f"  GPU no disponible ({e}); uso CPU con {threads} hilos.")
            self._model = WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=threads)
            self._model.model = _EsEnOnly(self._model.model)
            self.device = "CPU"
        # warmup
        silence = np.zeros(self.config.sample_rate, dtype=np.float32)
        list(self._model.transcribe(silence, language=self.config.whisper_language or None)[0])

    def transcribe(self, audio: np.ndarray) -> str:
        sr = self.config.sample_rate
        t0 = time.perf_counter()
        lang = self.config.whisper_language or None
        # En CPU el idioma sale de la misma pasada que transcribe (ver _EsEnOnly); en GPU,
        # una detección aparte (es rápida ahí y queda como siempre anduvo).
        single_pass = lang is None and self.device == "CPU"
        if lang is None and not single_pass:
            lang = self._detect_es_en(audio)   # restringe la detección a en/es
        # Colchón de silencio al final: si cortás el dictado justo al terminar de
        # hablar, el audio queda sin cierre y Whisper "completa"/alucina el final.
        # Este silencio le da un cierre limpio (y el speech_pad del VAD tiene de
        # dónde agarrarse). Es silencio → decodifica en milisegundos.
        audio = np.concatenate([audio, np.zeros(int(_TAIL_PAD_S * sr), dtype=np.float32)])
        text = self._decode(audio, lang, 0.5, single_pass)
        if not text:
            # El VAD descartó TODO el audio. Si había voz baja/entrecortada, un VAD
            # más sensible la recupera; si era silencio de verdad, sigue vacío.
            print("[stt] el VAD no encontró voz — reintento con VAD sensible")
            text = self._decode(audio, lang, 0.25, single_pass)
        clean = _strip_hallucinations(text)
        if clean != text:
            print(f"[stt] alucinación de subtítulos filtrada del final")
        print(f"[stt] proceso {time.perf_counter() - t0:.2f}s (audio {len(audio) / sr:.1f}s)")
        return _finalize(clean)

    def _decode(self, audio, lang, vad_threshold, single_pass=False):
        segments, _ = self._model.transcribe(
            audio,
            language="es" if single_pass else lang,   # con single_pass el idioma lo pisa cada segmento
            multilingual=single_pass,
            beam_size=5,                        # precisión (mejor en palabras/nombres ambiguos)
            condition_on_previous_text=False,   # evita arrastrar contexto/repeticiones
            hotwords=(self.config.vocabulary or None),   # sesga hacia TUS términos/nombres
            vad_filter=True,
            vad_parameters={"threshold": vad_threshold, "min_silence_duration_ms": 300},
        )
        return " ".join(s.text for s in segments).strip()

    def _detect_es_en(self, audio):
        """Detecta SOLO entre español e inglés (evita mis-detección a idiomas
        parecidos: portugués/italiano/catalán). Mismo costo que el auto-detect."""
        try:
            _, _, probs = self._model.detect_language(audio)
            p = dict(probs)
            return "es" if p.get("es", 0.0) >= p.get("en", 0.0) else "en"
        except Exception:
            return None
