"""Microsoft Edge-TTS streaming engine with acoustic humanization and micro-pause prosody."""

import os
import re
import logging
from typing import AsyncGenerator, Optional
import edge_tts

logger = logging.getLogger("DomainExpandersVoice")

# Natural Indian neural voices:
# - hi-IN-SwaraNeural: Female Hindi (Warm & consultative)
# - hi-IN-MadhurNeural: Male Hindi (Very realistic Indian conversation)
# - en-IN-NeerjaExpressiveNeural: Female Indian English (Expressive & dynamic)
# - en-IN-PrabhatNeural: Male Indian English
DEFAULT_EDGE_VOICE = os.getenv("EDGE_TTS_VOICE", "hi-IN-SwaraNeural")
DEFAULT_RATE = os.getenv("VOICE_RATE", "+0%")  # Natural human conversational speed
DEFAULT_PITCH = os.getenv("VOICE_PITCH", "+0Hz")

GEMINI_TO_EDGE_VOICE_MAP = {
    "Aoede": "hi-IN-SwaraNeural",
    "Kore": "hi-IN-SwaraNeural",
    "Puck": "hi-IN-MadhurNeural",
    "Fenrir": "hi-IN-MadhurNeural",
    "Charon": "hi-IN-MadhurNeural",
}

class EdgeTTSVoiceEngine:
    def __init__(self, voice: Optional[str] = None, rate: Optional[str] = None, pitch: Optional[str] = None):
        selected_voice = voice or os.getenv("EDGE_TTS_VOICE") or os.getenv("DEFAULT_VOICE", "hi-IN-SwaraNeural")
        # If a Gemini S2S voice persona name was provided, map it to Edge neural voice
        self.voice = GEMINI_TO_EDGE_VOICE_MAP.get(selected_voice, selected_voice)
        self.rate = rate or os.getenv("VOICE_RATE", "+0%")
        self.pitch = pitch or os.getenv("VOICE_PITCH", "+0Hz")

    def set_voice(self, voice_name: str):
        """Switches the voice persona on the fly."""
        if voice_name:
            self.voice = voice_name
            logger.info(f"Voice persona changed to: {self.voice}")

    def _humanize_text_for_speech(self, text: str) -> str:
        """
        Cleans markdown, expands real estate abbreviations phonetically,
        and applies natural speech pauses without dead pauses.
        """
        if not text:
            return ""

        cleaned = text.strip()

        # Remove markdown symbols (*, #, _, `, etc.)
        cleaned = re.sub(r'[*#_`~]', '', cleaned)

        # Expand currency and tech abbreviations so TTS pronounces full words naturally
        cleaned = re.sub(r'\b(\d+(?:\.\d+)?)\s*(?:Cr|cr)\b', r'\1 crore', cleaned)
        cleaned = re.sub(r'\b(\d+(?:\.\d+)?)\s*(?:L|lakhs?|lac|lacs|k)\b', r'\1 lakh', cleaned)
        cleaned = re.sub(r'\bAI\b', 'A I', cleaned)
        cleaned = re.sub(r'\bSaaS\b', 'Saas', cleaned)

        # Natural conversational breathing commas (NOT ellipses which cause 500ms dead pauses)
        fillers = [
            (r'\b(Haanji|Haan ji)\b', 'Haanji,'),
            (r'\b(Arrey|Arey)\b', 'Arrey,'),
            (r'\b(Achha|Accha)\b', 'Achha,'),
            (r'\b(Actually)\b', 'Actually,'),
            (r'\b(Waise)\b', 'Waise,'),
            (r'\b(Namaste sir)\b', 'Namaste sir,'),
            (r'\b(Bilkul sir)\b', 'Bilkul sir,'),
        ]
        for pattern, replacement in fillers:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        # Replace robotic multiple dots or commas with clean single commas
        cleaned = re.sub(r'\.{2,}', ', ', cleaned)
        cleaned = re.sub(r',{2,}', ',', cleaned)
        cleaned = re.sub(r'\s+,', ',', cleaned)

        return cleaned

    async def stream_audio_chunks(self, text: str) -> AsyncGenerator[bytes, None]:
        """Streams audio binary chunks as they arrive from Edge-TTS."""
        if not text or not text.strip():
            return

        speech_text = self._humanize_text_for_speech(text)

        try:
            communicate = edge_tts.Communicate(
                text=speech_text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch
            )
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
        except Exception as e:
            logger.error(f"EdgeTTS synthesis error for '{text[:25]}...': {e}")

    async def synthesize_to_bytes(self, text: str) -> bytes:
        """Synthesizes text to a complete audio byte buffer."""
        audio_buffer = bytearray()
        async for chunk in self.stream_audio_chunks(text):
            audio_buffer.extend(chunk)
        return bytes(audio_buffer)
