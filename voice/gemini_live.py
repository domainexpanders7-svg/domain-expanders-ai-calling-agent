"""Speech-to-Speech (S2S) Gemini Live Engine for Domain Expanders Calling Agent.

Uses Google Gemini's official Multimodal Live API (gemini-2.5-flash-native-audio-latest)
which provides 100% human-sounding conversational voice in Hindi/Hinglish
under Google AI Studio's Free Tier.
"""

import os
import io
import wave
import base64
import logging
from typing import AsyncGenerator, Optional, Callable, Dict, Any
from google import genai
from google.genai import types
from agent.prompt import SYSTEM_PROMPT

logger = logging.getLogger("DomainExpandersGeminiLive")

DEFAULT_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-latest")
DEFAULT_VOICE = "Aoede"  # Warm, professional female voice (Sneha)

def pcm_to_wav_bytes(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """Encodes raw 16-bit PCM (mono, 24kHz) into standard playable WAV format."""
    if not pcm_data:
        return b""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)       # Mono
        wf.setsampwidth(2)      # 16-bit (2 bytes)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buffer.getvalue()


class GeminiLiveEngine:
    """Manages real-time bidirectional Speech-to-Speech sessions with Gemini Live API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        voice_name: str = DEFAULT_VOICE,
        system_instruction: str = SYSTEM_PROMPT,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or DEFAULT_LIVE_MODEL
        self.voice_name = voice_name
        self.system_instruction = system_instruction
        self.session = None
        self._session_context = None

        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set. Gemini Live S2S will not be functional.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)

    def set_voice(self, voice_name: str) -> None:
        """Updates voice persona (Aoede, Kore, Puck, Fenrir, Charon)."""
        self.voice_name = voice_name
        logger.info(f"Gemini Live voice persona set to: {self.voice_name}")

    def build_config(self) -> types.LiveConnectConfig:
        """Builds configuration for Gemini Live S2S with audio output and live transcription."""
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=self.system_instruction)]
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_name
                    )
                )
            ),
        )

    async def start_session(self) -> bool:
        """Connects a new Live S2S session."""
        if not self.client:
            logger.error("Cannot start Gemini Live session: Client not initialized.")
            return False

        try:
            await self.close_session()
            config = self.build_config()
            self._session_context = self.client.aio.live.connect(
                model=self.model_name,
                config=config,
            )
            self.session = await self._session_context.__aenter__()
            logger.info(f"Gemini Live S2S session connected (model: {self.model_name}, voice: {self.voice_name})")
            return True
        except Exception as e:
            logger.error(f"Failed to connect Gemini Live session: {e}", exc_info=True)
            self.session = None
            return False

    async def close_session(self) -> None:
        """Gracefully closes active Live session."""
        if self._session_context:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Session cleanup note: {e}")
            self._session_context = None
            self.session = None

    async def send_user_text(self, text: str) -> None:
        """Sends user text message to Gemini Live session."""
        if not self.session:
            raise RuntimeError("Gemini Live session is not connected.")
        await self.session.send_realtime_input(text=text)

    async def send_user_audio(self, pcm_16k_bytes: bytes) -> None:
        """Sends raw 16kHz PCM audio chunk from microphone to Gemini Live."""
        if not self.session:
            raise RuntimeError("Gemini Live session is not connected.")
        await self.session.send_realtime_input(
            audio=types.Blob(
                data=pcm_16k_bytes,
                mime_type="audio/pcm;rate=16000",
            )
        )

    async def stream_turn(
        self,
        on_audio_chunk: Optional[Callable[[bytes], Any]] = None,
        on_transcript_chunk: Optional[Callable[[str], Any]] = None,
    ) -> Dict[str, Any]:
        """Receives Gemini Live S2S streaming turn.

        Yields audio chunks and transcript fragments via callbacks as they arrive in real-time.
        Returns total audio bytes, wav bytes, and full transcript.
        """
        if not self.session:
            raise RuntimeError("Gemini Live session is not active.")

        collected_pcm = bytearray()
        full_transcript = []

        async for response in self.session.receive():
            server_content = response.server_content
            if not server_content:
                continue

            # 1. Live transcription of model's spoken words
            if server_content.output_transcription and server_content.output_transcription.text:
                chunk_text = server_content.output_transcription.text
                full_transcript.append(chunk_text)
                if on_transcript_chunk:
                    res = on_transcript_chunk(chunk_text)
                    if hasattr(res, "__await__"):
                        await res

            # 2. Native audio stream (24kHz 16-bit PCM)
            if server_content.model_turn:
                for part in server_content.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        raw_pcm = part.inline_data.data
                        collected_pcm.extend(raw_pcm)
                        if on_audio_chunk:
                            res = on_audio_chunk(raw_pcm)
                            if hasattr(res, "__await__"):
                                await res

            # 3. Turn complete
            if server_content.turn_complete:
                break

        full_text = "".join(full_transcript).strip()
        wav_bytes = pcm_to_wav_bytes(bytes(collected_pcm), sample_rate=24000)

        return {
            "transcript": full_text,
            "pcm_bytes": bytes(collected_pcm),
            "wav_bytes": wav_bytes,
            "wav_b64": base64.b64encode(wav_bytes).decode("utf-8") if wav_bytes else "",
        }