"""Composio Bridge for Domain Expanders AI Calling Agent.

Supports Composio SDK v3 with GeminiProvider (Automatic Function Calling for Gemini)
as well as fallback to Composio MCP Server over JSON-RPC to autonomously execute:
1. Schedule Google Calendar Discovery Calls with Google Meet links.
2. Send Scoping & Confirmation emails via Gmail.
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger("ComposioBridge")

try:
    from composio import Composio
    from composio_gemini import GeminiProvider
    COMPOSIO_SDK_AVAILABLE = True
except ImportError:
    COMPOSIO_SDK_AVAILABLE = False
    Composio = None
    GeminiProvider = None

DEFAULT_MCP_URL = os.getenv("COMPOSIO_MCP_URL", "https://connect.composio.dev/mcp")
DEFAULT_API_KEY = os.getenv("COMPOSIO_API_KEY", "ak_xmTyiDXFOsybQSqBnrBk")


class ComposioBridge:
    """Interface to execute Google Calendar and Gmail tools through Composio SDK v3 & MCP."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        mcp_url: Optional[str] = None,
        user_id: str = "domainexpanders_agent",
    ):
        self.api_key = api_key or os.getenv("COMPOSIO_API_KEY", DEFAULT_API_KEY)
        self.mcp_url = mcp_url or DEFAULT_MCP_URL
        self.user_id = user_id
        self.headers = {
            "x-consumer-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        self.client = None
        self.session = None

        if COMPOSIO_SDK_AVAILABLE and self.api_key:
            try:
                self.client = Composio(api_key=self.api_key, provider=GeminiProvider())
                self.session = self.client.create(user_id=self.user_id)
                logger.info(f"Composio SDK v3 session established for user '{self.user_id}'.")
            except Exception as e:
                logger.warning(f"Could not initialize Composio SDK v3 session: {e}")

    def get_tools(self, user_id: Optional[str] = None) -> List[Any]:
        """Returns Gemini-compatible tools list from the active Composio session."""
        if not self.client:
            return []
        try:
            sess = self.session if not user_id else self.client.create(user_id=user_id)
            return sess.tools()
        except Exception as e:
            logger.error(f"Error getting Composio session tools for Gemini: {e}")
            return []

    async def _call_tool(self, tool_slug: str, arguments: Dict[str, Any], thought: str = "") -> Dict[str, Any]:
        """Executes a Composio tool using the SDK session or fallback to MCP over JSON-RPC."""
        # Try SDK session direct execution first if available
        if self.session:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self.session.execute(tool_slug, arguments=arguments)
                )
                return {"success": True, "data": result}
            except Exception as sdk_err:
                logger.warning(f"Composio SDK session execute for {tool_slug} returned error: {sdk_err}. Falling back to MCP JSON-RPC...")
        payload = {
            "jsonrpc": "2.0",
            "id": int(datetime.utcnow().timestamp() * 1000),
            "method": "tools/call",
            "params": {
                "name": "COMPOSIO_MULTI_EXECUTE_TOOL",
                "arguments": {
                    "thought": thought or f"Execute {tool_slug}",
                    "tools": [
                        {
                            "tool_slug": tool_slug,
                            "arguments": arguments,
                        }
                    ],
                    "sync_response_to_workbench": False,
                },
            },
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.post(self.mcp_url, headers=self.headers, json=payload)

            if response.status_code != 200:
                logger.error(f"Composio MCP HTTP error {response.status_code}: {response.text}")
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}

            # Parse event-stream / json-rpc response
            response_text = response.text
            data_payload = None
            for line in response_text.splitlines():
                if line.startswith("data:"):
                    json_str = line[5:].strip()
                    try:
                        data_payload = json.loads(json_str)
                        break
                    except Exception:
                        continue

            if not data_payload and response_text.strip().startswith("{"):
                try:
                    data_payload = json.loads(response_text)
                except Exception:
                    pass

            if not data_payload:
                return {"success": False, "error": "Invalid response format from Composio MCP"}

            result = data_payload.get("result", {})
            content = result.get("content", [])
            if content and isinstance(content, list):
                inner_text = content[0].get("text", "")
                parsed_inner = json.loads(inner_text)
                return {"success": True, "data": parsed_inner}

            return {"success": True, "raw": result}

        except Exception as e:
            logger.error(f"Composio MCP execution error for {tool_slug}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def book_calendar_discovery_call(
        self,
        client_name: str,
        client_email: str,
        start_datetime: str,
        duration_minutes: int = 30,
        topic: str = "AI Systems & Scalable Platform Scoping",
        notes: str = "",
    ) -> Dict[str, Any]:
        """Books a Discovery Scoping Call on Google Calendar with Google Meet link."""
        # Sanitize ISO start_datetime
        clean_time = start_datetime.strip().replace(" ", "T")
        if len(clean_time) == 10:  # Just YYYY-MM-DD
            clean_time = f"{clean_time}T11:00:00"

        # If seconds not provided
        if clean_time.count(":") == 1:
            clean_time = f"{clean_time}:00"

        summary = f"Domain Expanders Discovery Call — {client_name}"
        description = (
            f"<b>Domain Expanders Discovery & Technical Scoping Session</b><br><br>"
            f"<b>Client:</b> {client_name} ({client_email})<br>"
            f"<b>Topic:</b> {topic}<br>"
            f"<b>Notes:</b> {notes or 'Discussing AI calling agents, SaaS scaling, custom web/app development, or workflow automations.'}<br><br>"
            f"<i>Powered by Domain Expanders AI Calling Agent & Composio.</i>"
        )

        args = {
            "summary": summary,
            "description": description,
            "start_datetime": clean_time,
            "event_duration_minutes": min(max(duration_minutes, 15), 59),
            "create_meeting_room": True,
            "timezone": "Asia/Kolkata",
        }

        if client_email and "@" in client_email:
            args["attendees"] = [client_email]

        logger.info(f"Executing Google Calendar event creation for {client_name} at {clean_time}")
        result = await self._call_tool(
            tool_slug="GOOGLECALENDAR_CREATE_EVENT",
            arguments=args,
            thought=f"Book discovery scoping call for {client_name}",
        )

        meet_link = "https://meet.google.com"
        event_link = ""

        # Extract meet link if available
        try:
            tool_res = result.get("data", {}).get("data", {}).get("results", [])[0].get("response", {})
            event_data = tool_res.get("data", {})
            event_link = event_data.get("htmlLink", "")
            hangout = event_data.get("hangoutLink") or event_data.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri")
            if hangout:
                meet_link = hangout
        except Exception:
            pass

        return {
            "success": result.get("success", False),
            "client_name": client_name,
            "client_email": client_email,
            "start_datetime": clean_time,
            "summary": summary,
            "meet_link": meet_link,
            "event_link": event_link,
            "raw_result": result,
        }

    async def send_scoping_email(
        self,
        recipient_email: str,
        client_name: str,
        service_interest: str = "AI Calling Agents & SaaS Engineering",
        meeting_time: str = "Scheduled via Google Calendar",
        meet_link: str = "Google Meet invite attached",
    ) -> Dict[str, Any]:
        """Sends a confirmation and scoping briefing email via Gmail using Composio."""
        if not recipient_email or "@" not in recipient_email:
            logger.warning(f"Skipping email dispatch: Invalid email '{recipient_email}'")
            return {"success": False, "error": "Invalid recipient email"}

        subject = f"Domain Expanders — Your Discovery Scoping Call is Confirmed! 🚀"

        html_body = f"""
        <div style="font-family: 'Segoe UI', Helvetica, Arial, sans-serif; max-width: 620px; margin: 0 auto; background: #0b0f19; color: #f3f4f6; border-radius: 12px; overflow: hidden; border: 1px solid #1f293d;">
            <div style="background: linear-gradient(135deg, #0d1527 0%, #1e293b 100%); padding: 32px 28px; border-bottom: 2px solid #00f0ff;">
                <h1 style="margin: 0; color: #ffffff; font-size: 24px; letter-spacing: 0.5px;">DOMAIN EXPANDERS</h1>
                <p style="margin: 6px 0 0 0; color: #00f0ff; font-size: 13px; text-transform: uppercase; font-weight: 600; letter-spacing: 1.5px;">Your Domain. Your Empire.</p>
            </div>
            <div style="padding: 28px; line-height: 1.6;">
                <p style="font-size: 16px; margin-top: 0;">Hi <strong>{client_name or 'there'}</strong>,</p>
                <p>Thank you for speaking with Sneha from Domain Expanders today! We are thrilled to partner with you on scaling your business through precision engineering and AI.</p>
                
                <div style="background: #131b2e; border-left: 4px solid #00f0ff; padding: 18px; border-radius: 8px; margin: 24px 0;">
                    <h3 style="margin: 0 0 10px 0; color: #00f0ff; font-size: 15px;">🗓️ Discovery Call Details</h3>
                    <p style="margin: 4px 0; font-size: 14px;"><strong>Target Scope:</strong> {service_interest}</p>
                    <p style="margin: 4px 0; font-size: 14px;"><strong>Scheduled Time:</strong> {meeting_time}</p>
                    <p style="margin: 4px 0; font-size: 14px;"><strong>Video Meeting Link:</strong> <a href="{meet_link}" style="color: #38bdf8; text-decoration: underline;">{meet_link}</a></p>
                </div>

                <h4 style="color: #ffffff; margin-bottom: 8px;">What We Will Cover in 30 Minutes:</h4>
                <ul style="padding-left: 20px; color: #94a3b8; font-size: 14px;">
                    <li>Deep audit of your current digital domain and growth gaps</li>
                    <li>Technical architecture (Custom LLMs, 10k+ Concurrency SaaS, Automated Workflows)</li>
                    <li>Timeline, milestones, and dedicated engineering pod scoping</li>
                </ul>

                <p style="font-size: 14px; color: #94a3b8; margin-top: 24px;">Need to share materials beforehand or reschedule? WhatsApp us directly at <a href="https://wa.me/917898832506" style="color: #22c55e;">+91 7898832506</a> or reply to this email.</p>
                
                <div style="margin-top: 32px; padding-top: 20px; border-top: 1px solid #1e293b; font-size: 12px; color: #64748b;">
                    <p style="margin: 0;"><strong>Domain Expanders Team</strong></p>
                    <p style="margin: 4px 0;"><a href="https://www.domainexpanders.in/" style="color: #00f0ff; text-decoration: none;">www.domainexpanders.in</a> | domainexpanders7@gmail.com</p>
                </div>
            </div>
        </div>
        """

        args = {
            "recipient_email": recipient_email,
            "subject": subject,
            "body": html_body,
            "is_html": True,
        }

        logger.info(f"Executing Gmail dispatch to {recipient_email}")
        result = await self._call_tool(
            tool_slug="GMAIL_SEND_EMAIL",
            arguments=args,
            thought=f"Send discovery confirmation email to {recipient_email}",
        )

        return {
            "success": result.get("success", False),
            "recipient": recipient_email,
            "subject": subject,
            "raw_result": result,
        }
