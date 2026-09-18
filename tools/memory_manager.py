"""Supabase & Local Persistent Vector/Profile Memory Manager for Domain Expanders Calling Agent."""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger("DomainExpandersMemory")

LOCAL_MEMORY_FILE = os.path.join(os.path.dirname(__file__), "..", "caller_memory.json")

class MemoryManager:
    """Manages caller context and interaction history across calls.
    
    Supports:
    1. Supabase PostgreSQL table (when SUPABASE_URL and SUPABASE_KEY are provided).
    2. Local JSON memory store (seamless zero-config fallback).
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        local_path: str = LOCAL_MEMORY_FILE
    ):
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.local_path = local_path
        self.supabase_client = None

        if self.supabase_url and self.supabase_key:
            try:
                from supabase import create_client
                self.supabase_client = create_client(self.supabase_url, self.supabase_key)
                logger.info(f"Supabase Memory Client connected to {self.supabase_url}")
            except ImportError:
                logger.warning("supabase-py not installed. Using local JSON memory fallback.")
            except Exception as e:
                logger.warning(f"Failed to connect to Supabase: {e}. Using local JSON memory fallback.")
        else:
            logger.info("SUPABASE_URL not configured. Operating with local persistent JSON memory.")

        self._ensure_local_storage()

    def _ensure_local_storage(self):
        """Ensures local storage file exists."""
        if not os.path.exists(self.local_path):
            try:
                with open(self.local_path, "w", encoding="utf-8") as f:
                    json.dump({}, f, indent=2)
            except Exception as e:
                logger.error(f"Error creating local memory store: {e}")

    def get_caller_context(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Retrieves past memory profile for a calling phone number."""
        if not phone_number:
            return None

        clean_phone = self._clean_phone(phone_number)

        # 1. Try Supabase first if available
        if self.supabase_client:
            try:
                response = self.supabase_client.table("caller_memories").select("*").eq("phone_number", clean_phone).execute()
                if response.data and len(response.data) > 0:
                    record = response.data[0]
                    logger.info(f"Retrieved Supabase memory for caller {clean_phone}: {record.get('client_name')}")
                    return record
            except Exception as e:
                logger.error(f"Error fetching memory from Supabase: {e}")

        # 2. Fallback to local memory
        try:
            if os.path.exists(self.local_path):
                with open(self.local_path, "r", encoding="utf-8") as f:
                    memories = json.load(f)
                    return memories.get(clean_phone)
        except Exception as e:
            logger.error(f"Error reading local caller memory: {e}")

        return None

    def save_caller_memory(self, phone_number: str, data: Dict[str, Any]) -> bool:
        """Saves or updates caller memory profile after call completion."""
        if not phone_number:
            return False

        clean_phone = self._clean_phone(phone_number)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        memory_record = {
            "phone_number": clean_phone,
            "client_name": data.get("customer_name") or data.get("client_name"),
            "company_name": data.get("company_name"),
            "last_service_interest": data.get("service_interest"),
            "budget": data.get("budget"),
            "timeline": data.get("timeline"),
            "summary": data.get("call_summary"),
            "updated_at": now_str
        }

        # 1. Save to Supabase if connected
        if self.supabase_client:
            try:
                self.supabase_client.table("caller_memories").upsert(memory_record).execute()
                logger.info(f"Caller memory upserted to Supabase for {clean_phone}")
            except Exception as e:
                logger.error(f"Failed to upsert caller memory to Supabase: {e}")

        # 2. Always maintain local JSON replica for zero-downtime safety
        try:
            memories: Dict[str, Any] = {}
            if os.path.exists(self.local_path):
                with open(self.local_path, "r", encoding="utf-8") as f:
                    try:
                        memories = json.load(f)
                    except json.JSONDecodeError:
                        memories = {}

            existing = memories.get(clean_phone, {})
            history: List[Any] = existing.get("history", [])
            if data.get("call_summary"):
                history.append({
                    "date": now_str,
                    "summary": data.get("call_summary"),
                    "service": data.get("service_interest")
                })

            memory_record["history"] = history[-5:]  # Keep last 5 call records
            memories[clean_phone] = memory_record

            with open(self.local_path, "w", encoding="utf-8") as f:
                json.dump(memories, f, indent=2, ensure_ascii=False)

            logger.info(f"Caller memory saved locally for {clean_phone}")
            return True
        except Exception as e:
            logger.error(f"Failed to save local caller memory: {e}")
            return False

    def build_personalized_instruction(self, caller_context: Optional[Dict[str, Any]]) -> str:
        """Builds a contextual prompt injection for returning callers."""
        if not caller_context:
            return ""

        name = caller_context.get("client_name") or "Sir/Ma'am"
        company = caller_context.get("company_name")
        past_service = caller_context.get("last_service_interest")
        past_summary = caller_context.get("summary")

        prompt_part = f"\n### RETURNING CALLER RECOGNITION:\n"
        prompt_part += f"- The caller is a RETURNING CLIENT who called previously.\n"
        prompt_part += f"- Known Client Name: {name}\n"
        if company:
            prompt_part += f"- Company: {company}\n"
        if past_service:
            prompt_part += f"- Previous Project Interest: {past_service}\n"
        if past_summary:
            prompt_part += f"- Past Discussion Summary: {past_summary}\n"
        prompt_part += "- Warmly acknowledge them by name if appropriate: 'Haanji {name} ji, Namaste! Sneha baat kar rahi hoon Domain Expanders se...'\n"

        return prompt_part

    @staticmethod
    def get_supabase_migration_sql() -> str:
        """Returns the PostgreSQL SQL script to create caller_memories in Supabase."""
        return """
        -- Run this in your Supabase SQL Editor:
        create table if not exists caller_memories (
            phone_number text primary key,
            client_name text,
            company_name text,
            last_service_interest text,
            budget text,
            timeline text,
            summary text,
            interaction_history jsonb default '[]'::jsonb,
            updated_at timestamp with time zone default now()
        );

        create index if not exists idx_caller_memories_phone on caller_memories(phone_number);
        """

    def _clean_phone(self, phone: str) -> str:
        """Normalizes phone numbers to standard format."""
        cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
        if not cleaned.startswith("+") and len(cleaned) == 10:
            cleaned = "+91" + cleaned
        return cleaned
