from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from app.agents.base_agent import BaseAgent, AgentResult
from app.connectors.groq_client import groq_client
from app.schemas.agent import AgentResultData, SynthesisResponse

logger = logging.getLogger("orca")

SUPPORTED_LANGUAGES = {"en", "hi", "te"}


class ResponseSynthesizer(BaseAgent):
    async def _execute(
        self,
        user_message: str,
        language: str = "en",
        evidence: Optional[list[dict]] = None,
        safety_badge: Optional[str] = None,
        fishing_suitability: Optional[str] = None,
        hazard_breakdown: Optional[dict] = None,
        warnings: Optional[list[dict]] = None,
        agent_results: Optional[list[dict]] = None,
        follow_up_suggestions: Optional[list[str]] = None,
    ) -> AgentResultData:
        task_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        errors: list[str] = []

        if language not in SUPPORTED_LANGUAGES:
            language = "en"
            errors.append(f"unsupported_language_fallback_to_en: {language}")

        evidence = evidence or []
        warnings = warnings or []
        agent_results = agent_results or []
        follow_up_suggestions = follow_up_suggestions or []

        if not groq_client._api_key:
            return AgentResultData(
                agent_name=self.name,
                task_id=task_id,
                status="partial",
                data=SynthesisResponse(
                    answer="I am currently unable to generate a natural-language response. "
                    "Please try again later or consult official marine safety sources.",
                    follow_up_suggestions=[],
                    language=language,
                    evidence_summary=[],
                    safety_badge=safety_badge,
                    fishing_suitability=fishing_suitability,
                ).model_dump(),
                evidence=[],
                errors=errors + ["groq_api_key_not_configured"],
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=0.0,
                source_status="fallback",
            )

        try:
            synthesis = await self._synthesize_with_groq(
                user_message=user_message,
                language=language,
                evidence=evidence,
                safety_badge=safety_badge,
                fishing_suitability=fishing_suitability,
                hazard_breakdown=hazard_breakdown,
                warnings=warnings,
                agent_results=agent_results,
                follow_up_suggestions=follow_up_suggestions,
            )
        except Exception as exc:
            logger.warning("ResponseSynthesizer Groq call failed: %s", exc)
            return AgentResultData(
                agent_name=self.name,
                task_id=task_id,
                status="partial",
                data=SynthesisResponse(
                    answer="I encountered an issue generating the response. "
                    "The structured data is available, but the explanation could not be produced.",
                    follow_up_suggestions=[],
                    language=language,
                    evidence_summary=[],
                    safety_badge=safety_badge,
                    fishing_suitability=fishing_suitability,
                ).model_dump(),
                evidence=[],
                errors=errors + [f"synthesis_failed: {exc}"],
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=0.0,
                source_status="error",
            )

        completed_at = datetime.utcnow()
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        return AgentResultData(
            agent_name=self.name,
            task_id=task_id,
            status="success",
            data=synthesis.model_dump(),
            evidence=[],
            errors=errors,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 3),
            source_status="llm",
        )

    async def _synthesize_with_groq(
        self,
        user_message: str,
        language: str,
        evidence: list[dict],
        safety_badge: Optional[str],
        fishing_suitability: Optional[str],
        hazard_breakdown: Optional[dict],
        warnings: list[dict],
        agent_results: list[dict],
        follow_up_suggestions: list[str],
    ) -> SynthesisResponse:
        system_prompt = (
            "You are a marine safety assistant for the ORCA system. "
            "Generate a concise, accurate natural-language response using ONLY the provided evidence. "
            "Do NOT invent values, units, or safety assessments. "
            "Preserve all numeric values and units exactly as provided. "
            "If evidence is missing for a safety-critical claim, explicitly state that current safety cannot be confirmed. "
            "Respond with valid JSON only, no markdown."
        )

        evidence_summary = []
        for item in evidence:
            evidence_summary.append(
                {
                    "source": item.get("source"),
                    "variable": item.get("variable"),
                    "value": item.get("value"),
                    "unit": item.get("unit"),
                    "confidence": item.get("confidence"),
                }
            )

        user_prompt = (
            f"User question: {user_message}\n"
            f"Language: {language}\n"
            f"Safety badge: {safety_badge or 'unavailable'}\n"
            f"Fishing suitability: {fishing_suitability or 'unavailable'}\n"
            f"Hazard breakdown: {hazard_breakdown or {}}\n"
            f"Active warnings: {json.dumps(warnings, default=str)}\n"
            f"Evidence summary: {json.dumps(evidence_summary, default=str)}\n"
            f"Agent results: {json.dumps(agent_results, default=str)}\n"
            f"Follow-up suggestions: {json.dumps(follow_up_suggestions, default=str)}\n"
            "Return JSON with keys: "
            "answer (string), "
            "follow_up_suggestions (array of strings), "
            "evidence_summary (array of objects with source, variable, value, unit, confidence), "
            "safety_badge (string or null), "
            "fishing_suitability (string or null)."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await groq_client.chat(messages=messages, temperature=0.0)
        content = response.choices[0].message.content or "{}"

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in LLM response")

        data = json.loads(match.group())

        if not isinstance(data, dict):
            raise ValueError("LLM response is not a JSON object")

        required_keys = {"answer"}
        missing = required_keys - set(data.keys())
        if missing:
            raise ValueError(f"LLM response missing required keys: {missing}")

        return SynthesisResponse(
            answer=str(data.get("answer", "")),
            follow_up_suggestions=[str(s) for s in data.get("follow_up_suggestions", [])],
            language=language,
            evidence_summary=data.get("evidence_summary", []),
            safety_badge=safety_badge,
            fishing_suitability=fishing_suitability,
        )
