"""Multi-turn conversation engine and entity extraction for Domain Expanders Calling Agent."""

import os
import json
import logging
from typing import List, Dict, Any, AsyncGenerator, Optional
from google import genai
from google.genai import types
from agent.prompt import SYSTEM_PROMPT, ENTITY_EXTRACTION_PROMPT

logger = logging.getLogger("DomainExpandersAgent")

class ConversationEngine:
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.history: List[Dict[str, str]] = []
        self.extracted_lead: Dict[str, Any] = {
            "customer_name": None,
            "company_name": None,
            "phone": None,
            "service_interest": None,
            "project_scope": None,
            "budget": None,
            "timeline": None,
            "discovery_call_scheduled": False,
            "visit_date_time": None,
            "lead_stage": "New Prospect",
            "call_summary": "Call in progress..."
        }
        
        self.caller_phone: Optional[str] = None
        self.caller_context: Optional[Dict[str, Any]] = None
        self.last_tool_executed: Optional[Dict[str, Any]] = None
        self.hangup_requested: bool = False
        
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set. Responses will be simulated until configured.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)

    def reset(self):
        """Reset conversation state for a new call."""
        self.history = []
        self.caller_phone = None
        self.caller_context = None
        self.last_tool_executed = None
        self.hangup_requested = False
        self.extracted_lead = {
            "customer_name": None,
            "company_name": None,
            "phone": None,
            "service_interest": None,
            "project_scope": None,
            "budget": None,
            "timeline": None,
            "discovery_call_scheduled": False,
            "visit_date_time": None,
            "lead_stage": "New Prospect",
            "call_summary": "Call in progress..."
        }

    def set_caller_context(self, phone: str, context: Optional[Dict[str, Any]] = None):
        """Sets the active caller phone and long-term memory profile."""
        self.caller_phone = phone
        self.caller_context = context
        if phone:
            self.extracted_lead["phone"] = phone
        if context and context.get("client_name"):
            self.extracted_lead["customer_name"] = context.get("client_name")
        if context and context.get("company_name"):
            self.extracted_lead["company_name"] = context.get("company_name")

    def get_active_system_prompt(self) -> str:
        """Dynamically appends returning caller context to the system prompt."""
        prompt = SYSTEM_PROMPT
        if self.caller_context:
            name = self.caller_context.get("client_name") or "Sir/Ma'am"
            company = self.caller_context.get("company_name")
            past_service = self.caller_context.get("last_service_interest")
            past_summary = self.caller_context.get("summary")
            prompt += f"\n\n### RETURNING CALLER RECOGNITION:\n"
            prompt += f"- The caller is a RETURNING CLIENT with phone number: {self.caller_phone or 'registered'}.\n"
            prompt += f"- Client Name: {name}\n"
            if company:
                prompt += f"- Company: {company}\n"
            if past_service:
                prompt += f"- Past Project Interest: {past_service}\n"
            if past_summary:
                prompt += f"- Previous Interaction Summary: {past_summary}\n"
            prompt += "- Warmly acknowledge their returning status and continue building rapport.\n"
        return prompt

    def get_initial_greeting(self) -> str:
        """Returns personalized greeting if returning client, else standard warm greeting."""
        if self.caller_context and self.caller_context.get("client_name"):
            name = self.caller_context.get("client_name")
            greeting = f"Haanji {name} ji, Namaste! Sneha baat kar rahi hoon Domain Expanders se. Kaise hain aap?"
        else:
            greeting = "Haanji sir, Namaste! Sneha baat kar rahi hoon Domain Expanders se. Aaj main aapke business ya tech project me kaise help kar sakti hoon?"
        self.history.append({"role": "model", "text": greeting})
        return greeting

    async def stream_response(self, user_text: str) -> AsyncGenerator[str, None]:
        """Streams text chunks of agent response using Gemini Flash."""
        self.history.append({"role": "user", "text": user_text})

        # Fallback if no API key is provided yet
        if not self.client:
            simulated = "Namaste! Main Domain Expanders se Sneha baat kar rahi hoon. Aap AI calling agents ya custom software development me kya plan kar rahe hain sir?"
            self.history.append({"role": "model", "text": simulated})
            yield simulated
            return

        try:
            # Build conversation contents
            contents = []
            for msg in self.history:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["text"])]
                    )
                )

            # Try primary model and fallback to backup if unavailable
            models_to_try = [self.model_name, "gemini-3.5-flash-lite", "gemini-3.6-flash"]
            last_err = None

            for m_name in models_to_try:
                try:
                    response_stream = self.client.models.generate_content_stream(
                        model=m_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=self.get_active_system_prompt(),
                            temperature=0.7,
                            max_output_tokens=300,
                        )
                    )

                    full_reply = ""
                    for chunk in response_stream:
                        if chunk.text:
                            full_reply += chunk.text
                            yield chunk.text

                    self.history.append({"role": "model", "text": full_reply})
                    return
                except Exception as ex:
                    last_err = ex
                    continue

            raise last_err or Exception("All models failed")

        except Exception as e:
            logger.error(f"Error during Gemini response generation: {e}")
            fallback = "Ji sir, main aapki baat bilkul samajh rahi hoon. Ek baar project requirements aur timeline verify kar lein?"
            self.history.append({"role": "model", "text": fallback})
            yield fallback

    async def update_extracted_entities(self) -> Dict[str, Any]:
        """Extracts structured lead qualification parameters from history."""
        if not self.client or len(self.history) < 2:
            return self.extracted_lead

        conversation_text = "\n".join(
            [f"{'Client' if m['role'] == 'user' else 'Sneha (Domain Expanders)'}: {m['text']}" for m in self.history]
        )

        models_to_try = [self.model_name, "gemini-3.5-flash-lite", "gemini-3.6-flash"]
        for m_name in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=m_name,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(text=f"{ENTITY_EXTRACTION_PROMPT}\n\nConversation:\n{conversation_text}")
                            ]
                        )
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )

                if response.text:
                    clean_json = response.text.strip()
                    parsed = json.loads(clean_json)
                    self.extracted_lead.update(parsed)
                    return self.extracted_lead
            except Exception as e:
                logger.warning(f"Model {m_name} extraction issue: {e}")
                continue

        return self.extracted_lead
