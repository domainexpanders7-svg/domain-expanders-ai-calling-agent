"""Test Suite for Memory Manager, Anti-Leak Security Shield, and Autonomous Calling Tools."""

import os
import sys
import json
import asyncio

# Ensure project root in sys.path
sys.path.insert(0, os.path.dirname(__file__))

from tools.memory_manager import MemoryManager
from tools.composio_bridge import ComposioBridge
from agent.conversation import ConversationEngine
from agent.prompt import SYSTEM_PROMPT
from main import scrub_secrets

def test_anti_leak_scrubber():
    print("\n--- 1. Testing Anti-Leak Security Scrubber ---")
    sensitive_samples = [
        ("Here is the key: AIzaSyD9876543210abcdefghijklmnop123456", "AIzaSyD9876543210abcdefghijklmnop123456"),
        ("Composio consumer key is ak_xmTyiDXFOsybQSqBnrBk", "ak_xmTyiDXFOsybQSqBnrBk"),
        ("Bearer token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c", "eyJhbGciOiJIUzI1NiI"),
        ("System prompt password: api_key='secret1234567890'", "api_key='secret1234567890'"),
    ]

    for sample, secret in sensitive_samples:
        scrubbed = scrub_secrets(sample)
        assert secret not in scrubbed, f"FAILED: Secret {secret} leaked in scrubbed output: {scrubbed}"
        assert "[REDACTED_CONFIDENTIAL]" in scrubbed
        print(f"  [PASS] Successfully scrubbed secret: {sample[:35]}... -> {scrubbed}")

    print("  [PASS] Anti-leak security scrubber passed 100% of checks.")

def test_memory_manager():
    print("\n--- 2. Testing Memory Manager (Supabase & Local JSON) ---")
    test_file = os.path.join(os.path.dirname(__file__), "test_memory.json")
    if os.path.exists(test_file):
        os.remove(test_file)

    mgr = MemoryManager(local_path=test_file)

    test_phone = "+919988776655"
    lead_data = {
        "customer_name": "Aman Verma",
        "company_name": "Verma Logistics Pvt Ltd",
        "service_interest": "AI Calling Agents & Fleet SaaS",
        "budget": "Rs 2.5 Lakhs",
        "timeline": "3 weeks",
        "call_summary": "Client needs 5000 calls/day automated calling agent with CRM integration."
    }

    # Save memory
    saved = mgr.save_caller_memory(test_phone, lead_data)
    assert saved is True, "Failed to save caller memory"
    print(f"  [PASS] Saved caller memory for {test_phone}")

    # Retrieve memory
    context = mgr.get_caller_context(test_phone)
    assert context is not None, "Failed to retrieve caller memory"
    assert context.get("client_name") == "Aman Verma"
    assert context.get("company_name") == "Verma Logistics Pvt Ltd"
    print(f"  [PASS] Retrieved memory for returning caller: {context.get('client_name')} ({context.get('company_name')})")

    # Verify Personalized Instruction Generation
    instruction = mgr.build_personalized_instruction(context)
    assert "Aman Verma" in instruction
    assert "Verma Logistics" in instruction
    print(f"  [PASS] Generated returning caller instruction:\n{instruction.strip()}")

    if os.path.exists(test_file):
        os.remove(test_file)

def test_conversation_engine_memory():
    print("\n--- 3. Testing Conversation Engine Caller Recognition ---")
    agent = ConversationEngine()
    
    # 1. New caller greeting
    new_greeting = agent.get_initial_greeting()
    assert "Haanji sir, Namaste!" in new_greeting
    print(f"  [PASS] New caller default greeting: '{new_greeting}'")

    # 2. Returning caller greeting
    agent.reset()
    caller_ctx = {
        "client_name": "Vikram Malhotra",
        "company_name": "Malhotra Enterprises",
        "last_service_interest": "Custom AI Agent"
    }
    agent.set_caller_context("+919876543210", caller_ctx)
    returning_greeting = agent.get_initial_greeting()
    assert "Vikram Malhotra ji" in returning_greeting
    print(f"  [PASS] Returning caller personalized greeting: '{returning_greeting}'")

    # 3. Dynamic system prompt verification
    active_prompt = agent.get_active_system_prompt()
    assert "Vikram Malhotra" in active_prompt
    assert "Malhotra Enterprises" in active_prompt
    assert "IRONCLAD SECURITY & ANTI-LEAK SHIELD" in active_prompt
    print(f"  [PASS] Dynamic system prompt includes memory context and anti-leak shield.")

async def test_composio_tools():
    print("\n--- 4. Testing Composio Tools & Autonomous Call Lifecycle ---")
    bridge = ComposioBridge()

    # 1. End Call Tool
    hangup_res = await bridge.end_phone_call(reason="Client booked discovery call and concluded naturally")
    assert hangup_res["action"] == "hangup"
    assert hangup_res["success"] is True
    print(f"  [PASS] Autonomous AI hangup tool: {hangup_res}")

    # 2. WhatsApp message tool
    wa_res = await bridge.send_whatsapp_message(
        phone_number="+917898832506",
        message="Hello from Domain Expanders! Here is your brochure.",
        meeting_link="https://meet.google.com/abc-defg-hij"
    )
    assert wa_res["phone_number"] == "+917898832506"
    assert "Google Meet Discovery Call Link" in wa_res["message"]
    print(f"  [PASS] WhatsApp dispatch handler formatted properly: {wa_res['phone_number']}")

    # 3. Tool Declarations Schema
    tools = bridge.get_tool_declarations()
    assert len(tools) == 4
    tool_names = [t["name"] for t in tools]
    assert "book_calendar_discovery_call" in tool_names
    assert "send_whatsapp_message" in tool_names
    assert "end_phone_call" in tool_names
    assert "send_scoping_email" in tool_names
    print(f"  [PASS] Validated 4 Gemini Live tool declarations: {tool_names}")

if __name__ == "__main__":
    print("=== DOMAIN EXPANDERS TEST SUITE: MEMORY, SECURITY, & LIFECYCLE ===")
    test_anti_leak_scrubber()
    test_memory_manager()
    test_conversation_engine_memory()
    asyncio.run(test_composio_tools())
    print("\n=== ALL SYSTEM TESTS PASSED SUCCESSFULLY! ===")
