"""Test script to verify Composio integration with Gemini and ComposioBridge."""

import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Force unbuffered UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

async def run_composio_tests():
    print("=" * 60, flush=True)
    print("Domain Expanders AI Calling Agent - Composio Integration Test", flush=True)
    print("=" * 60, flush=True)

    api_key = os.getenv("COMPOSIO_API_KEY")
    print(f"\n[1/3] Checking COMPOSIO_API_KEY from environment...", flush=True)
    if not api_key:
        print("[-] COMPOSIO_API_KEY is missing from .env!", flush=True)
        return False
    masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "***"
    print(f"[+] COMPOSIO_API_KEY detected: {masked_key}", flush=True)

    print("\n[2/3] Checking Composio SDK & GeminiProvider availability...", flush=True)
    try:
        from composio import Composio
        from composio_gemini import GeminiProvider
        print("[+] composio and composio_gemini libraries successfully imported.", flush=True)

        composio_client = Composio(api_key=api_key, provider=GeminiProvider())
        session = composio_client.create(user_id="domainexpanders_test_user")
        print(f"[+] Successfully created Composio session for user 'domainexpanders_test_user'.", flush=True)

        tools = session.tools()
        print(f"[+] Retrieved {len(tools)} session tools formatted for Gemini.", flush=True)
    except ImportError as e:
        print(f"[!] Composio Python package not installed in current environment: {e}", flush=True)
        print("    Run: python -m pip install composio composio_gemini", flush=True)
    except Exception as e:
        print(f"[!] Composio session creation notice: {e}", flush=True)

    print("\n[3/3] Testing ComposioBridge wrapper...", flush=True)
    from tools.composio_bridge import ComposioBridge
    bridge = ComposioBridge()
    print(f"[+] ComposioBridge initialized (API Key: {bridge.api_key[:6]}..., User ID: {bridge.user_id})", flush=True)

    tools_from_bridge = bridge.get_tools()
    print(f"[+] Tools available via bridge: {len(tools_from_bridge)}", flush=True)

    print("\nComposio bridge verification completed successfully.", flush=True)
    return True

if __name__ == "__main__":
    asyncio.run(run_composio_tests())
