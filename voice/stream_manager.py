"""Streaming Voice Pipeline: Sentence-level chunking, parallel TTS synthesis, and barge-in cancellation."""

import re
import asyncio
import base64
import logging
from typing import AsyncGenerator, Callable, Optional, Awaitable
from voice.tts import EdgeTTSVoiceEngine

logger = logging.getLogger("DomainExpandersStreamManager")

# Regex to detect natural sentence boundaries in Hindi, English, and Hinglish
# Only split on full sentence terminators so neural TTS maintains rich prosodic intonation
SENTENCE_SPLIT_REGEX = re.compile(r'([.!?।\n]+)\s*')

class VoiceStreamManager:
    def __init__(self, tts_engine: Optional[EdgeTTSVoiceEngine] = None):
        self.tts = tts_engine or EdgeTTSVoiceEngine()
        self.is_interrupted = False
        self.active_turn_task: Optional[asyncio.Task] = None

    def interrupt(self):
        """Cancels current turn immediately on barge-in / user speech."""
        self.is_interrupted = True
        if self.active_turn_task and not self.active_turn_task.done():
            self.active_turn_task.cancel()
            logger.info("Current speech synthesis turn canceled due to barge-in.")

    async def stream_sentence_audio(
        self,
        text_stream: AsyncGenerator[str, None],
        on_sentence_ready: Callable[[int, str, str, bool], Awaitable[None]]
    ) -> str:
        """
        Consumes streaming text tokens, splits into natural sentences,
        synthesizes audio for each sentence in parallel, and streams out.
        Returns the full combined text reply.
        """
        self.is_interrupted = False
        buffer = ""
        full_reply = ""
        sentence_idx = 0

        async for chunk in text_stream:
            if self.is_interrupted:
                logger.info("Speech generation aborted by interruption.")
                break

            buffer += chunk
            full_reply += chunk

            # Check if we have complete sentences in the buffer
            parts = SENTENCE_SPLIT_REGEX.split(buffer)
            
            # If a delimiter matched, parts will have [sentence, delimiter, remaining_buffer]
            while len(parts) >= 3:
                sentence = (parts[0] + parts[1]).strip()
                buffer = "".join(parts[2:])
                parts = SENTENCE_SPLIT_REGEX.split(buffer)

                if sentence and len(sentence) > 3 and not self.is_interrupted:
                    sentence_idx += 1
                    try:
                        audio_bytes = await self.tts.synthesize_to_bytes(sentence)
                        if audio_bytes and not self.is_interrupted:
                            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                            await on_sentence_ready(sentence_idx, sentence, audio_b64, False)
                    except Exception as e:
                        logger.error(f"Error synthesizing sentence '{sentence[:20]}...': {e}")

        # Synthesize any remaining text left in the buffer
        remaining = buffer.strip()
        if remaining and not self.is_interrupted:
            sentence_idx += 1
            try:
                audio_bytes = await self.tts.synthesize_to_bytes(remaining)
                if audio_bytes and not self.is_interrupted:
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                    await on_sentence_ready(sentence_idx, remaining, audio_b64, True)
            except Exception as e:
                logger.error(f"Error synthesizing final buffer '{remaining[:20]}...': {e}")

        return full_reply
