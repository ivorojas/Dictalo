"""Config de Dictalo — voz a texto para Windows."""
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_DIR = Path.home() / ".dictalo"
PREFS_PATH = APP_DIR / "prefs.json"


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
