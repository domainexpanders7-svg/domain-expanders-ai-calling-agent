"""Lead management and CRM sync for Domain Expanders."""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger("DomainExpandersLeads")

LEADS_FILE = os.path.join(os.path.dirname(__file__), "..", "leads.json")

class LeadManager:
    def __init__(self, storage_path: str = LEADS_FILE):
        self.storage_path = storage_path
        self._ensure_storage()

    def _ensure_storage(self):
        """Creates storage file if it doesn't exist."""
        if not os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=2)
            except Exception as e:
                logger.error(f"Error creating leads storage: {e}")

    def save_lead(self, lead_data: Dict[str, Any]) -> bool:
        """Saves or updates lead in persistent storage."""
        try:
            leads: List[Dict[str, Any]] = []
            if os.path.exists(self.storage_path):
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    try:
                        leads = json.load(f)
                    except json.JSONDecodeError:
                        leads = []

            # Add timestamp and ID
            record = dict(lead_data)
            record["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            record["id"] = f"DE-{int(datetime.now().timestamp())}"

            leads.append(record)

            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(leads, f, indent=2, ensure_ascii=False)

            logger.info(f"Lead saved successfully: {record['id']} - {record.get('customer_name')}")
            return True
        except Exception as e:
            logger.error(f"Failed to save lead: {e}")
            return False

    def get_all_leads(self) -> List[Dict[str, Any]]:
        """Returns all saved leads."""
        if not os.path.exists(self.storage_path):
            return []
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
