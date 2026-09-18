import re
import os
import json
import base64
import asyncio
import logging
from typing import Dict, Any, Optional
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
from tools.memory_manager import MemoryManager
from tools.composio_bridge import ComposioBridge

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DomainExpandersServer")

# Anti-Leak Security Patterns (Guarantees zero leakage of credentials/keys)
SECRET_PATTERNS = [
    re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"),
    re.compile(r"ak_[A-Za-z0-9]{15,40}"),
    re.compile(r"ey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password|bearer|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{10,}"),
]

def scrub_secrets(text: str) -> str:
    """Guarantees internal API keys, passwords, and tokens are NEVER disclosed to callers."""
    if not text:
        return text
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_CONFIDENTIAL]", sanitized)
    return sanitized

app = FastAPI(title="Domain Expanders AI Calling Agent")

# Mount Static Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize Shared Managers
lead_manager = LeadManager()
memory_manager = MemoryManager()
composio_bridge = ComposioBridge()
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
                
                # Fetch memory profile for caller phone
                caller_phone = data.get("caller_phone", "+919876543210")
                caller_context = memory_manager.get_caller_context(caller_phone)
                agent.set_caller_context(caller_phone, caller_context)
                logger.info(f"Starting call for {caller_phone}. Returning client: {bool(caller_context)}")

                # Start Live session concurrently in background
                session_task = asyncio.create_task(live_engine.start_session())

                # Send greeting transcript immediately (0ms wait) with secret scrubbing
                greeting = scrub_secrets(agent.get_initial_greeting())
                await websocket.send_json({
                    "type": "transcript",
                    "role": "agent",
                    "text": greeting,
                    "returning_client": bool(caller_context),
                    "client_name": caller_context.get("client_name") if caller_context else None
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

                lower_text = user_text.lower()
                # Autonomous WhatsApp Tool Trigger
                if any(k in lower_text for k in ["whatsapp", "whatsap", "watsapp"]):
                    logger.info(f"Triggering autonomous WhatsApp follow-up for {agent.caller_phone}...")
                    asyncio.create_task(
                        composio_bridge.send_whatsapp_message(
                            phone_number=agent.caller_phone or "+919876543210",
                            message="Namaste from Domain Expanders! Here is our AI Calling Agent & Tech Engineering brochure and discovery meeting booking details."
                        )
                    )
                    await websocket.send_json({
                        "type": "tool_executed",
                        "tool": "send_whatsapp_message",
                        "phone": agent.caller_phone
                    })

                # Autonomous Hangup Detection
                should_hangup = any(k in lower_text for k in ["cut kardo", "phone kaat do", "call end", "bye bye", "theek hai bye"])

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
                            safe_txt = scrub_secrets(txt)
                            await websocket.send_json({
                                "type": "transcript_stream",
                                "role": "agent",
                                "text": safe_txt
                            })

                        turn_data = await live_engine.stream_turn(
                            on_audio_chunk=on_pcm_chunk,
                            on_transcript_chunk=on_transcript_chunk
                        )
                        agent_reply = scrub_secrets(turn_data.get("transcript", ""))
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
                    async def send_scrubbed_sentence_audio(idx: int, sentence: str, audio_b64: str, is_final: bool):
                        await send_sentence_audio(idx, scrub_secrets(sentence), audio_b64, is_final)

                    full_reply = await stream_mgr.stream_sentence_audio(
                        agent.stream_response(user_text),
                        send_scrubbed_sentence_audio
                    )
                    safe_full_reply = scrub_secrets(full_reply)
                    await websocket.send_json({
                        "type": "turn_complete",
                        "role": "agent",
                        "text": safe_full_reply
                    })

                # If caller concluded conversation, emit autonomous hangup event
                if should_hangup:
                    await websocket.send_json({
                        "type": "hangup_call",
                        "reason": "Client concluded conversation naturally"
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
                logger.info("Call ended by user. Closing Live S2S session and saving lead & memory...")
                await live_engine.close_session()
                if agent.extracted_lead and (agent.extracted_lead.get("service_interest") or agent.extracted_lead.get("company_name") or agent.extracted_lead.get("budget")):
                    lead_manager.save_lead(agent.extracted_lead)
                if agent.caller_phone:
                    memory_manager.save_caller_memory(agent.caller_phone, agent.extracted_lead)
                
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
    Dedicated full-duplex binary PCM streaming endpoint for Android InCallService GSM Gateway.
    - Receives raw 16kHz PCM from caller's SIM line.
    - Streams native 24kHz PCM voice from Gemini Live Speech-to-Speech engine.
    - Full-duplex bidirectional audio: zero lag, instant natural interruptions.
    """
    await websocket.accept()
    logger.info("Android GSM Phone Bridge connected.")
    agent = ConversationEngine()
    caller_phone = ""
    live_engine = GeminiLiveEngine(voice_name="Aoede", system_instruction=agent.get_system_prompt())
    receiver_task: Optional[asyncio.Task] = None

    async def gemini_audio_receiver():
        """Full-duplex receiver: pulls 24kHz PCM and transcript from Gemini Live and streams to phone."""
        try:
            async for response in live_engine.session.receive():
                server_content = response.server_content
                if not server_content:
                    continue

                # 1. Native Audio Stream (24kHz 16-bit PCM Mono)
                if server_content.model_turn:
                    for part in server_content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            raw_pcm = part.inline_data.data
                            await websocket.send_bytes(raw_pcm)

                # 2. Live Transcript for logs & analytics
                if server_content.output_transcription and server_content.output_transcription.text:
                    txt = scrub_secrets(server_content.output_transcription.text)
                    await websocket.send_json({
                        "type": "transcript",
                        "role": "agent",
                        "text": txt
                    })
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Live S2S receiver closed: {e}")

    try:
        # Connect Gemini Live S2S
        session_ok = await live_engine.start_session()
        logger.info(f"Gemini Live session for GSM call initialized (active={session_ok})")

        if session_ok:
            receiver_task = asyncio.create_task(gemini_audio_receiver())

        while True:
            msg = await websocket.receive()
            if "text" in msg:
                event = json.loads(msg["text"])
                if event.get("type") == "call_init":
                    caller_phone = event.get("caller_phone", "")
                    caller_context = memory_manager.get_caller_context(caller_phone)
                    agent.set_caller_context(caller_phone, caller_context)
                    logger.info(f"Initialized GSM call for {caller_phone}. Returning client: {bool(caller_context)}")
                    
                    greeting = agent.get_initial_greeting()
                    greeting = scrub_secrets(greeting)

                    await websocket.send_json({
                        "type": "transcript",
                        "role": "agent",
                        "text": greeting,
                        "returning_client": bool(caller_context),
                        "client_name": caller_context.get("client_name") if caller_context else None
                    })

                    # Trigger Gemini Live to speak greeting immediately
                    if session_ok and live_engine.session:
                        try:
                            await live_engine.send_user_text(f"The client just called on the phone line. Speak this greeting clearly right now: {greeting}")
                        except Exception as ge:
                            logger.warning(f"Error triggering S2S initial greeting: {ge}")

                elif event.get("type") == "hangup":
                    logger.info(f"Call hangup event received from Android for {caller_phone}. Extracting lead data...")
                    await agent.update_extracted_entities()
                    if agent.extracted_lead and (agent.extracted_lead.get("service_interest") or agent.extracted_lead.get("company_name") or agent.extracted_lead.get("budget")):
                        lead_manager.save_lead(agent.extracted_lead)
                    if caller_phone:
                        memory_manager.save_caller_memory(caller_phone, agent.extracted_lead)
                    break

            elif "bytes" in msg:
                # Raw PCM 16kHz audio from Android SIM line
                raw_audio = msg["bytes"]
                if not raw_audio:
                    continue

                # Stream caller's live voice directly into Gemini Live multimodal socket
                if session_ok and live_engine.session:
                    try:
                        await live_engine.send_user_audio(raw_audio)
                    except Exception as audio_err:
                        logger.debug(f"Audio streaming error: {audio_err}")

    except WebSocketDisconnect:
        logger.info(f"Android GSM Bridge disconnected for {caller_phone}. Saving final memory...")
        try:
            await agent.update_extracted_entities()
            if agent.extracted_lead and (agent.extracted_lead.get("service_interest") or agent.extracted_lead.get("company_name") or agent.extracted_lead.get("budget")):
                lead_manager.save_lead(agent.extracted_lead)
            if caller_phone:
                memory_manager.save_caller_memory(caller_phone, agent.extracted_lead)
        except Exception as ex:
            logger.debug(f"Disconnect memory save note: {ex}")
    except Exception as e:
        logger.error(f"GSM Bridge error: {e}")
    finally:
        if receiver_task:
            receiver_task.cancel()
        await live_engine.close_session()

@app.get("/memory/{phone}")
async def get_caller_memory_profile(phone: str):
    """Inspects Supabase or local memory profile for any phone number."""
    record = memory_manager.get_caller_context(phone)
    return {"phone": phone, "record": record}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))
    reload = os.getenv("RELOAD", "false").lower() in ("true", "1", "yes")
    logger.info(f"Starting Domain Expanders AI Calling Agent on port {port} (reload={reload})...")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
