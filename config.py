"""Config de Dictado App (voz a texto para Windows)."""
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_DIR = Path.home() / ".dictado"
PREFS_PATH = APP_DIR / "prefs.json"
_LEGACY_DIR = Path.home() / ".dictalo"   # la app antes se llamaba "Dictalo"


def migrate_legacy_data():
    """Trae los datos de la versión anterior (vocabulario, historial, log). Si la
    carpeta vieja está en uso y no se puede mover, copia lo esencial."""
    if APP_DIR.exists() or not _LEGACY_DIR.is_dir():
        return
    try:
        _LEGACY_DIR.rename(APP_DIR)
        old_log = APP_DIR / "dictalo.log"
        if old_log.exists():
            old_log.rename(APP_DIR / "dictado.log")
    except OSError:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        for name in ("prefs.json", "history.json"):
            try:
                shutil.copy2(_LEGACY_DIR / name, APP_DIR / name)
            except OSError:
                pass


@dataclass
class Config:
    # Audio
    sample_rate: int = 16000
    mic_index: int = -1            # -1 = mic por defecto
    min_frames: int = 6000        # descarta clips < ~0.4s

    # Whisper local (faster-whisper / CUDA)
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "cuda"
    whisper_compute: str = "int8"
    whisper_language: str = ""    # "" = auto

    # Vocabulario propio: nombres/términos que usás, para que Whisper no los erre.
    # Editable en Ajustes. Se aplica en vivo (sin reiniciar).
    vocabulary: str = ("Claude, Claude Code, Anthropic, ChatGPT, OpenAI, Gemini, Cursor, "
                       "GitHub, VS Code, Visual Studio Code, Python, JavaScript, TypeScript, "
                       "React, Node, npm, Docker, Git, API, Whisper, Wispr Flow, PowerShell, Linux")

    # Limpieza IA (opcional, off por defecto)
    cleanup_enabled: bool = False
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = "gemini-2.5-flash-lite"

    # Hotkey (pynput GlobalHotKeys, modo toggle)
    hotkey: str = "<f9>"
    hotkey_display: str = "F9"

    # Ventanita flotante: estilo elegido (id de preset, "custom" o "mine:<nombre>"),
    # el personalizado en edición y los guardados por el usuario (ver looks.py)
    overlay_preset: str = "aurora"
    overlay_custom: dict = field(default_factory=dict)
    overlay_mine: list = field(default_factory=list)
    bar_intensity: float = 0.8     # cuánto se exagera el movimiento de las barras (0-1, solo visual)

    # Sonidos: pack elegido (ver sounds.PACKS)
    sound_pack: str = "suave"

    def __post_init__(self):
        self._load()

    def _load(self):
        if not PREFS_PATH.exists():
            return
        try:
            for k, v in json.loads(PREFS_PATH.read_text(encoding="utf-8")).items():
                if hasattr(self, k) and k != "gemini_api_key":
                    setattr(self, k, v)
        except Exception:
            pass

    def save(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.pop("gemini_api_key", None)
        PREFS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
