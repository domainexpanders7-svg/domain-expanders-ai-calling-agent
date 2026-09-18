import asyncio
from dotenv import load_dotenv
load_dotenv()

async def test_components():
    print("[1/4] Testing LeadManager...")
    from tools.lead_manager import LeadManager
    manager = LeadManager()
    success = manager.save_lead({
        "customer_name": "Rohan Sharma",
        "company_name": "TechCorp Solutions",
        "service_interest": "AI Voice Calling Agent",
        "project_scope": "Inbound customer support automation",
        "budget": "2-3 Lakhs",
        "timeline": "Immediate (2 weeks)",
        "discovery_call_scheduled": True,
        "visit_date_time": "Friday 4:00 PM",
        "lead_stage": "Discovery Call Scheduled",
        "call_summary": "Wants an AI calling agent for customer support."
    })
    leads = manager.get_all_leads()
    print(f"-> Lead saved: {success}, Total leads: {len(leads)}")

    print("\n[2/4] Testing Edge-TTS voice generation...")
    from voice.tts import EdgeTTSVoiceEngine
    engine = EdgeTTSVoiceEngine()
    test_text = "Namaste sir! Domain Expanders me aapka swagat hai."
    audio_bytes = await engine.synthesize_to_bytes(test_text)
    print(f"-> Synthesized '{test_text}' into {len(audio_bytes)} bytes of MP3 audio.")
    assert len(audio_bytes) > 1000, "Audio output is too small or failed."

    print("\n[3/4] Testing ConversationEngine & Gemini streaming...")
    from agent.conversation import ConversationEngine
    agent = ConversationEngine()
    greeting = agent.get_initial_greeting()
    print(f"-> Initial greeting: '{greeting}'")

    print("-> Testing live user question: 'Humein apne SaaS platform ke liye AI voice calling agent integrate karwana hai'")
    streamed_reply = ""
    async for chunk in agent.stream_response("Humein apne SaaS platform ke liye AI voice calling agent integrate karwana hai"):
        streamed_reply += chunk
    print(f"-> Agent live reply received: {len(streamed_reply)} chars")

    print("\n[4/4] Testing entity extraction...")
    entities = await agent.update_extracted_entities()
    print(f"-> Extracted Entities: Service={entities.get('service_interest')}, Company={entities.get('company_name')}, Budget={entities.get('budget')}")

    print("\n[5/5] Testing Gemini Live S2S Native Audio Engine...")
    from voice.gemini_live import GeminiLiveEngine
    live_engine = GeminiLiveEngine()
    connected = await live_engine.start_session()
    print(f"-> Gemini Live S2S connected: {connected}")
    assert connected, "Gemini Live S2S session could not be established."
    await live_engine.send_user_text("Namaste Sneha ji, AI voice agent ki pricing aur architecture batao.")
    turn_res = await live_engine.stream_turn()
    print(f"-> S2S Transcript received: '{turn_res.get('transcript')}'")
    print(f"-> S2S WAV Audio size: {len(turn_res.get('wav_bytes', b''))} bytes")
    assert len(turn_res.get('wav_bytes', b'')) > 5000, "Audio output should contain realistic speech."
    await live_engine.close_session()

    print("\nSUCCESS: All components verified including Gemini Native Speech-to-Speech!")

if __name__ == "__main__":
    asyncio.run(test_components())

