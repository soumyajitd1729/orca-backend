from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from app.agents.base_agent import BaseAgent, AgentResult
from app.connectors.groq_client import groq_client
from app.schemas.agent import AgentResultData, NormalizedIntent

logger = logging.getLogger("orca")

FALLBACK_LANGUAGE = "en"

KNOWN_LOCATIONS = {
    "kakinada": (16.9891, 82.2475),
    "chennai": (13.0827, 80.2707),
    "visakhapatnam": (17.6868, 83.2185),
    "mumbai": (19.0760, 72.8777),
    "kochi": (9.9312, 76.2673),
    "mangalore": (12.9173, 74.8560),
    "goa": (15.2993, 74.1244),
    "kolkata": (22.5726, 88.3639),
    "paradip": (20.3167, 86.6167),
    "haldia": (22.0333, 88.0667),
    "ennore": (13.2500, 80.3167),
    "tuticorin": (8.7642, 78.1348),
    "mandapam": (9.2833, 79.1167),
}


class IntentAgent(BaseAgent):
    async def _execute(
        self,
        message: str,
        user_location: Optional[str] = None,
        user_lat: Optional[float] = None,
        user_lon: Optional[float] = None,
        requested_radius_km: Optional[float] = None,
    ) -> AgentResultData:
        task_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        errors: list[str] = []

        intent_data = self._fallback_intent(
            message,
            user_location=user_location,
            user_lat=user_lat,
            user_lon=user_lon,
            requested_radius_km=requested_radius_km,
        )

        if groq_client._api_key:
            try:
                llm_data = await self._parse_with_groq(message, user_location)
                if llm_data:
                    intent_data = self._merge_intent_data(intent_data, llm_data)
            except Exception as exc:
                logger.warning("IntentAgent Groq parsing failed: %s", exc)
                errors.append(f"llm_unavailable: {exc}")
        else:
            errors.append("groq_api_key_not_configured")

        resolved_lat, resolved_lon = self._resolve_coordinates(
            intent_data, user_lat, user_lon
        )
        intent_data["latitude"] = resolved_lat
        intent_data["longitude"] = resolved_lon

        completed_at = datetime.utcnow()
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        return AgentResultData(
            agent_name=self.name,
            task_id=task_id,
            status="success" if not errors else "partial",
            data=intent_data,
            evidence=[],
            errors=errors,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 3),
            source_status="llm" if groq_client._api_key else "fallback",
        )

    async def _parse_with_groq(self, message: str, user_location: Optional[str] = None) -> Optional[dict]:
        system_prompt = (
            "You are a marine intent parser for the ORCA system. "
            "Extract structured intent from the user message. "
            "Respond with valid JSON only, no markdown. "
            "Never output latitude or longitude coordinates. "
            "Only return a location name string if present."
        )
        user_prompt = (
            f"Message: {message}\n"
            f"User location hint: {user_location or 'none'}\n"
            "Return JSON with keys: "
            "query_type (warnings|pfz|fishing|weather|route|general), "
            "location_name (string or null), "
            "time_expression (string or null), "
            "language (ISO 639-1 code, default en), "
            "requested_radius_km (number or null, default 10), "
            "route_start (object with lat/lon or null), "
            "route_end (object with lat/lon or null), "
            "weather_intent (boolean), "
            "pfz_intent (boolean), "
            "warning_intent (boolean), "
            "route_intent (boolean). "
            "Do not include latitude or longitude for the main query location."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await groq_client.chat(messages=messages, temperature=0.0)
        content = response.choices[0].message.content or "{}"

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group())

        if not isinstance(data, dict):
            return None

        if "intents" in data and not isinstance(data["intents"], list):
            data["intents"] = [str(data["intents"])]

        if "language" not in data or not data["language"]:
            data["language"] = FALLBACK_LANGUAGE

        return data

    @staticmethod
    def _merge_intent_data(base: dict, llm: dict) -> dict:
        merged = dict(base)
        for key, value in llm.items():
            if value is not None:
                merged[key] = value
        return merged

    @staticmethod
    def _resolve_coordinates(
        intent_data: dict,
        user_lat: Optional[float],
        user_lon: Optional[float],
    ) -> tuple[Optional[float], Optional[float]]:
        if user_lat is not None and user_lon is not None:
            return user_lat, user_lon

        location_name = intent_data.get("location_name")
        if isinstance(location_name, str) and location_name.strip():
            normalized = location_name.strip().lower()
            if normalized in KNOWN_LOCATIONS:
                return KNOWN_LOCATIONS[normalized]

        return None, None

    @staticmethod
    def _parse_time_expression(message: str) -> Optional[str]:
        msg_lower = message.lower()
        if "tomorrow morning" in msg_lower:
            return "tomorrow_morning"
        if "tomorrow afternoon" in msg_lower:
            return "tomorrow_afternoon"
        if "tomorrow evening" in msg_lower:
            return "tomorrow_evening"
        if "tomorrow" in msg_lower:
            return "tomorrow"
        if "today" in msg_lower:
            return "today"
        return None

    @staticmethod
    def _fallback_intent(
        message: str,
        user_location: Optional[str] = None,
        user_lat: Optional[float] = None,
        user_lon: Optional[float] = None,
        requested_radius_km: Optional[float] = None,
    ) -> dict:
        msg_lower = message.lower()
        intents: list[str] = []
        if any(word in msg_lower for word in ["warning", "warnings", "imd", "cyclone", "storm"]):
            intents.append("warnings")
        if any(word in msg_lower for word in ["pfz", "fishing", "fish", "catch"]):
            intents.append("pfz")
        if any(word in msg_lower for word in ["weather", "wind", "wave", "forecast", "sst"]):
            intents.append("weather")
        if any(word in msg_lower for word in ["route", "path", "voyage", "navigate"]):
            intents.append("route")

        if not intents:
            intents.append("general")

        if any(word in msg_lower for word in ["pfz", "fishing", "fish"]):
            query_type = "fishing"
        elif any(word in msg_lower for word in ["warning", "warnings", "imd"]):
            query_type = "warnings"
        elif any(word in msg_lower for word in ["weather", "wind", "wave", "forecast"]):
            query_type = "weather"
        elif any(word in msg_lower for word in ["route", "path", "voyage"]):
            query_type = "route"
        else:
            query_type = "general"

        return {
            "query_type": query_type,
            "location_name": user_location,
            "time_expression": IntentAgent._parse_time_expression(message),
            "language": FALLBACK_LANGUAGE,
            "requested_radius_km": requested_radius_km,
            "route_start": None,
            "route_end": None,
            "weather_intent": "weather" in intents,
            "pfz_intent": "pfz" in intents,
            "warning_intent": "warnings" in intents,
            "route_intent": "route" in intents,
            "intents": intents,
            "raw_message": message,
        }
