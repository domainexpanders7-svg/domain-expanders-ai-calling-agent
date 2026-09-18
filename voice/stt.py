"""Speech-To-Text (STT) transcriber using Gemini Multimodal Audio processing."""

import os
import logging
from typing import Optional
from google import genai
from google.genai import types

logger = logging.getLogger("DomainExpandersSTT")

class SpeechToTextEngine:
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-3.5-flash-lite"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("STT_MODEL", model_name)
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        """Transcribes raw audio bytes into clean spoken text (Hinglish/Hindi/English)."""
        if not self.client:
            logger.warning("Gemini Client not initialized for STT.")
            return ""

        if not audio_bytes or len(audio_bytes) < 500:
            return ""

        prompt = (
            "Listen to this audio snippet from a real estate phone call. "
            "Transcribe the exact words spoken by the caller in natural Hindi, Hinglish, or English. "
            "Do not add any preamble, explanation, or quotes. Output ONLY the raw spoken text. "
            "If the audio contains only silence or background noise, return an empty string."
        )

        models_to_try = [self.model_name, "gemini-3.5-flash", "gemini-flash-latest"]
        
        for m_name in models_to_try:
            try:
                audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
                response = self.client.models.generate_content(
                    model=m_name,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[audio_part, types.Part.from_text(text=prompt)]
                        )
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=150
                    )
                )

                if response.text:
                    transcript = response.text.strip()
                    logger.info(f"Server STT ({m_name}) Transcribed: '{transcript}'")
                    return transcript
            except Exception as e:
                logger.warning(f"STT model {m_name} failed: {e}")
                continue

        return ""
