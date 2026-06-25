"""Limpieza opcional del texto con Gemini (off por defecto)."""

PROMPT = """\
Sos un editor de dictado. Recibís una transcripción cruda de voz y devolvés SOLO
el texto corregido, sin comillas ni explicaciones.
- Eliminá muletillas (eh, este, o sea, mmm) y falsos arranques.
- Puntuá y capitalizá según el sentido.
- Si hay auto-corrección ("a las 2, no, mejor 4"), dejá solo la versión final.
- No traduzcas ni cambies el significado.

Transcripción:
"""


class Cleaner:
    def __init__(self, config):
        self.config = config
        self._client = None
        if config.cleanup_enabled and config.gemini_api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=config.gemini_api_key)
            except Exception:
                self._client = None

    def clean(self, text: str) -> str:
        if not self._client or not text:
            return text
        try:
            r = self._client.models.generate_content(
                model=self.config.gemini_model, contents=PROMPT + text)
            return r.text.strip()
        except Exception:
            return text
