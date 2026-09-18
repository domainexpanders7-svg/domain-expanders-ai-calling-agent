"""Main FastAPI application for Domain Expanders AI Calling Agent and Telephony Gateway."""

import os
import json
import base64
import asyncio
import logging
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from agent.conversation import ConversationEngine
from voice.tts import EdgeTTSVoiceEngine
from voice.stt import SpeechToTextEngine
from voice.stream_manager import VoiceStreamManager
from voice.gemini_live import GeminiLiveEngine, pcm_to_wav_bytes
from tools.lead_manager import LeadManager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DomainExpandersServer")

app = FastAPI(title="Domain Expanders AI Calling Agent")

# Mount Static Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize Shared Managers
lead_manager = LeadManager()
tts_engine = EdgeTTSVoiceEngine()
stt_engine = SpeechToTextEngine()

@app.get("/")
async def get_index():
    """Serves the interactive voice simulator web app."""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"status": "Server running", "message": "Simulator UI not found."})

@app.get("/health")
async def health_check():
    """Health check endpoint for 24/7 keep-alive."""
    return {
        "status": "healthy",
        "service": "Domain Expanders AI Calling Agent",
        "voice": tts_engine.voice,
        "leads_count": len(lead_manager.get_all_leads())
    }

@app.get("/leads")
async def get_leads():
    """Returns all recorded leads."""
    return lead_manager.get_all_leads()

# Pre-cached Greetings for Near-Instant (0ms) Call Initiation
GREETING_CACHE: Dict[str, str] = {}

async def get_cached_greeting_b64(voice_name: str, greeting_text: str) -> str:
    """Returns pre-cached greeting audio for instant call initiation."""
    cache_key = f"{voice_name}_{hash(greeting_text)}"
    if cache_key in GREETING_CACHE:
        return GREETING_CACHE[cache_key]

    try:
        engine = GeminiLiveEngine(voice_name=voice_name)
        ok = await engine.start_session()
        if ok:
            await engine.send_user_text(f"Say this exact greeting clearly: {greeting_text}")
            turn = await engine.stream_turn()
            await engine.close_session()
            if turn.get("wav_b64"):
                GREETING_CACHE[cache_key] = turn["wav_b64"]
                return GREETING_CACHE[cache_key]
    except Exception as e:
        logger.warning(f"Failed to generate S2S cached greeting for {voice_name}: {e}")

    try:
        audio_bytes = await tts_engine.synthesize_to_bytes(greeting_text)
        b64 = base64.b64encode(audio_bytes).decode("utf-8")
        GREETING_CACHE[cache_key] = b64
        return b64
    except Exception:
        return ""

# -------------------------------------------------------------
# Browser Simulator WebSocket (/ws/browser)
# -------------------------------------------------------------
@app.websocket("/ws/browser")
async def browser_websocket(websocket: WebSocket):
    await websocket.accept()
    logger.info("Browser client connected to voice simulator.")
    
    agent = ConversationEngine()
    live_engine = GeminiLiveEngine(voice_name="Aoede")
    stream_mgr = VoiceStreamManager(tts_engine)

    async def send_sentence_audio(idx: int, sentence: str, audio_b64: str, is_final: bool):
        """Sends each sentence audio packet to the client as soon as synthesized."""
        try:
            await websocket.send_json({
                "type": "audio_chunk",
                "sentence_idx": idx,
                "text": sentence,
                "audio_base64": audio_b64,
                "mime_type": "audio/mp3",
                "is_final": is_final
            })
        except Exception as e:
            logger.warning(f"Failed to stream sentence chunk #{idx}: {e}")

    async def trigger_entity_extraction():
        """Extracts leads in the background without blocking conversation audio."""
        try:
            updated_lead = await agent.update_extracted_entities()
            await websocket.send_json({
                "type": "lead_update",
                "lead": updated_lead
            })
        except Exception as e:
            logger.warning(f"Background entity extraction issue: {e}")

    try:
        # Send initial saved leads
        await websocket.send_json({
            "type": "saved_leads",
            "leads": lead_manager.get_all_leads()
        })

        greeting_cancelled = False

        while True:
            message_text = await websocket.receive_text()
            data = json.loads(message_text)
            event_type = data.get("type")

            if event_type == "start_call":
                agent.reset()
                greeting_cancelled = False
                selected_voice = data.get("voice", "Aoede")
                live_engine.set_voice(selected_voice)
                
                # Start Live session concurrently in background
                session_task = asyncio.create_task(live_engine.start_session())

                # Send greeting transcript immediately (0ms wait)
                greeting = agent.get_initial_greeting()
                await websocket.send_json({
                    "type": "transcript",
                    "role": "agent",
                    "text": greeting
                })

                # Stream initial greeting audio instantly from cache
                wav_b64 = await get_cached_greeting_b64(selected_voice, greeting)
                if wav_b64 and not greeting_cancelled:
                    await websocket.send_json({
                        "type": "audio_chunk",
                        "is_greeting": True,
                        "sentence_idx": 1,
                        "text": greeting,
                        "audio_base64": wav_b64,
                        "mime_type": "audio/wav",
                        "is_final": True
                    })

                # Ensure Live session is connected for caller's first response
                try:
                    await session_task
                except Exception as e:
                    logger.warning(f"Background session connection notice: {e}")

            elif event_type == "interrupt":
                logger.info("Caller interrupted agent speech.")
                greeting_cancelled = True
                stream_mgr.interrupt()

            elif event_type in ("user_speech", "user_audio"):
                greeting_cancelled = True
                stream_mgr.interrupt()

                # Handle either direct text or raw audio blob
                user_text = ""
                if event_type == "user_audio":
                    raw_b64 = data.get("audio_base64", "")
                    mime = data.get("mime_type", "audio/webm")
                    if raw_b64:
                        audio_bytes = base64.b64decode(raw_b64)
                        user_text = await stt_engine.transcribe_audio(audio_bytes, mime_type=mime)
                        if user_text:
                            # Send transcribed text back to client display
                            await websocket.send_json({
                                "type": "transcript",
                                "role": "user",
                                "text": user_text
                            })
                else:
                    user_text = data.get("text", "").strip()

                if not user_text:
                    continue

                logger.info(f"Processing turn for input: '{user_text}'")
                agent.history.append({"role": "user", "text": user_text})

                # Attempt Gemini Live S2S with real-time PCM chunk streaming
                s2s_handled = False
                if live_engine.session:
                    try:
                        await live_engine.send_user_text(user_text)

                        async def on_pcm_chunk(pcm_bytes: bytes):
                            chunk_b64 = base64.b64encode(pcm_bytes).decode("utf-8")
                            await websocket.send_json({
                                "type": "s2s_pcm_chunk",
                                "audio_pcm_b64": chunk_b64
                            })

                        async def on_transcript_chunk(txt: str):
                            await websocket.send_json({
                                "type": "transcript_stream",
                                "role": "agent",
                                "text": txt
                            })

                        turn_data = await live_engine.stream_turn(
                            on_audio_chunk=on_pcm_chunk,
                            on_transcript_chunk=on_transcript_chunk
                        )
                        agent_reply = turn_data.get("transcript", "")
                        wav_b64 = turn_data.get("wav_b64", "")

                        if agent_reply:
                            agent.history.append({"role": "model", "text": agent_reply})
                            await websocket.send_json({
                                "type": "turn_complete",
                                "role": "agent",
                                "text": agent_reply,
                                "fallback_wav_b64": wav_b64
                            })
                            s2s_handled = True
                    except Exception as live_err:
                        logger.warning(f"Live S2S turn failed, attempting fallback: {live_err}")

                # Resilient Fallback to Streamed Text + TTS if Live session unavailable
                if not s2s_handled:
                    full_reply = await stream_mgr.stream_sentence_audio(
                        agent.stream_response(user_text),
                        send_sentence_audio
                    )
                    await websocket.send_json({
                        "type": "turn_complete",
                        "role": "agent",
                        "text": full_reply
                    })

                # Trigger entity extraction in background (zero latency impact)
                asyncio.create_task(trigger_entity_extraction())

            elif event_type == "set_voice":
                new_voice = data.get("voice")
                if new_voice:
                    live_engine.set_voice(new_voice)
                    tts_engine.set_voice(new_voice)
                    if live_engine.session:
                        asyncio.create_task(live_engine.start_session())
                    logger.info(f"Dynamic voice persona updated: {new_voice}")

            elif event_type == "end_call":
                logger.info("Call ended by user. Closing Live S2S session and saving lead...")
                await live_engine.close_session()
                if agent.extracted_lead and (agent.extracted_lead.get("service_interest") or agent.extracted_lead.get("company_name") or agent.extracted_lead.get("budget")):
                    lead_manager.save_lead(agent.extracted_lead)
                
                await websocket.send_json({
                    "type": "saved_leads",
                    "leads": lead_manager.get_all_leads()
                })

    except WebSocketDisconnect:
        logger.info("Browser client disconnected.")
        await live_engine.close_session()
    except Exception as e:
        logger.error(f"WebSocket session error: {e}")
        await live_engine.close_session()

# -------------------------------------------------------------
# Android Phone Telephony Bridge WebSocket (/ws/call)
# -------------------------------------------------------------
@app.websocket("/ws/call")
async def telephony_bridge_websocket(websocket: WebSocket):
    """
    Dedicated binary PCM streaming endpoint for Android InCallService GSM Gateway.
    Receives raw 16kHz audio from phone line and returns Edge-TTS audio chunks.
    """
    await websocket.accept()
    logger.info("Android GSM Phone Bridge connected.")
    agent = ConversationEngine()
    stream_mgr = VoiceStreamManager(tts_engine)

    try:
        greeting = agent.get_initial_greeting()
        audio_bytes = await tts_engine.synthesize_to_bytes(greeting)
        await websocket.send_bytes(audio_bytes)

        while True:
            msg = await websocket.receive()
            if "bytes" in msg:
                # Raw PCM 16kHz audio from Android SIM line
                raw_audio = msg["bytes"]
                user_text = await stt_engine.transcribe_audio(raw_audio, mime_type="audio/wav")
                if user_text:
                    async def send_to_phone(idx, sentence, audio_b64, is_final):
                        chunk = base64.b64decode(audio_b64)
                        await websocket.send_bytes(chunk)

                    await stream_mgr.stream_sentence_audio(
                        agent.stream_response(user_text),
                        send_to_phone
                    )
            elif "text" in msg:
                event = json.loads(msg["text"])
                if event.get("type") == "hangup":
                    logger.info("Call hangup event received from Android Phone Bridge. Extracting lead data...")
                    await agent.update_extracted_entities()
                    if agent.extracted_lead and (agent.extracted_lead.get("service_interest") or agent.extracted_lead.get("company_name") or agent.extracted_lead.get("budget")):
                        lead_manager.save_lead(agent.extracted_lead)
                    break
    except WebSocketDisconnect:
        logger.info("Android GSM Bridge disconnected. Performing final lead extraction...")
        try:
            await agent.update_extracted_entities()
            if agent.extracted_lead and (agent.extracted_lead.get("service_interest") or agent.extracted_lead.get("company_name") or agent.extracted_lead.get("budget")):
                lead_manager.save_lead(agent.extracted_lead)
        except Exception as ex:
            logger.debug(f"Disconnect lead extract note: {ex}")
    except Exception as e:
        logger.error(f"GSM Bridge error: {e}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))
    reload = os.getenv("RELOAD", "false").lower() in ("true", "1", "yes")
    logger.info(f"Starting Domain Expanders AI Calling Agent on port {port} (reload={reload})...")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
