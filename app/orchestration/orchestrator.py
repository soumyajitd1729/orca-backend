from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from app.agents.base_agent import BaseAgent, AgentResult
from app.agents.intent_agent import IntentAgent
from app.agents.pfz_agent import PFZAgent
from app.agents.route_agent import RouteAgent
from app.agents.response_synthesizer import ResponseSynthesizer
from app.agents.warnings_agent import WarningsAgent
from app.agents.weather_agent import WeatherAgent
from app.config import settings
from app.connectors.groq_client import groq_client
from app.repositories import evidence_repository
from app.schemas.agent import (
    AgentEvidence,
    AgentResultData,
    AgentTraceEntry,
    ExecutionPlan,
    NormalizedIntent,
    OrchestrationContext,
    OrchestrationResult,
    PlanStep,
    SynthesisResponse,
)
from app.services.evidence_validator import EvidenceClaim, EvidenceValidator, ValidationResult
from app.services.safety_engine import SafetyEngine

logger = logging.getLogger("orca")


class Orchestrator:
    def __init__(self, db, context: OrchestrationContext, max_concurrency: int | None = None) -> None:
        self.db = context.db if hasattr(context, "db") else db
        self.context = context
        self.semaphore = asyncio.Semaphore(max_concurrency or settings.MAX_CONCURRENT_AGENTS)
        self.agent_results: dict[str, AgentResult] = {}
        self.agent_trace: list[AgentTraceEntry] = []
        self.aggregated_evidence: list[AgentEvidence] = []
        self.request_id: str | None = getattr(context, "request_id", None)
        if self.request_id:
            import app.resilience.logging as logging_utils
            logging_utils.request_context.set(request_id=self.request_id)

    async def execute(self, intent: NormalizedIntent) -> OrchestrationResult:
        task_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        errors: list[str] = []

        plan = self._build_plan(intent)
        overall_status = "success"

        try:
            deadline = started_at + __import__("datetime").timedelta(
                seconds=settings.CHAT_REQUEST_DEADLINE_SECONDS
            )
            await asyncio.wait_for(
                self._execute_plan(plan),
                timeout=settings.CHAT_REQUEST_DEADLINE_SECONDS,
            )
        except asyncio.TimeoutError:
            overall_status = "timeout"
            errors.append("orchestration_timeout")
        except Exception as exc:
            overall_status = "error"
            errors.append(f"orchestration_error: {exc}")

        if overall_status == "success":
            for agent_result in self.agent_results.values():
                if hasattr(agent_result, "status") and agent_result.status == "timeout":
                    overall_status = "timeout"
                    errors.append("agent_timeout")
                    break
                if hasattr(agent_result, "status") and agent_result.status == "error":
                    overall_status = "error"
                    break

        self._enforce_evidence_limits()

        safety_result = self._extract_safety_result()
        validation_result = self._extract_validation_result()
        synthesis_result = self._extract_synthesis_result()

        completed_at = datetime.utcnow()

        return OrchestrationResult(
            task_id=task_id,
            intent=intent,
            plan=plan,
            agent_results=self._collect_agent_results(),
            agent_trace=self.agent_trace,
            aggregated_evidence=self.aggregated_evidence,
            safety_result=safety_result,
            validation_result=validation_result,
            synthesis_result=synthesis_result,
            errors=errors,
            overall_status=overall_status,
            request_id=self.request_id,
        )

    def _build_plan(self, intent: NormalizedIntent) -> ExecutionPlan:
        from app.orchestration.planner import create_plan
        return create_plan(intent)

    def _validate_plan(self, plan: ExecutionPlan) -> None:
        step_map = {step.agent_name: step for step in plan.steps}

        known_agents = {
            "IntentAgent",
            "WeatherAgent",
            "PFZAgent",
            "WarningsAgent",
            "RouteAgent",
            "SafetyEngine",
            "EvidenceValidator",
            "ResponseSynthesizer",
        }

        for step in plan.steps:
            if step.agent_name not in known_agents:
                raise ValueError(f"Unknown agent in plan: {step.agent_name}")

        def _check_circular(name: str, visited: set[str], path: set[str]) -> bool:
            if name in path:
                return True
            if name in visited:
                return False
            visited.add(name)
            path.add(name)
            step = step_map.get(name)
            if step:
                for dep in step.depends_on:
                    if _check_circular(dep, visited, path):
                        return True
            path.remove(name)
            return False

        visited: set[str] = set()
        for step in plan.steps:
            if _check_circular(step.agent_name, visited, set()):
                raise ValueError("Circular dependency detected in execution plan")

    async def _execute_plan(self, plan: ExecutionPlan) -> None:
        self._validate_plan(plan)
        step_map = {step.agent_name: step for step in plan.steps}
        completed: dict[str, AgentResult] = {}
        pending = set(step_map.keys())

        while pending:
            ready = []
            for name in list(pending):
                step = step_map[name]
                if set(step.depends_on).issubset(completed.keys()):
                    ready.append(name)

            if not ready and pending:
                raise RuntimeError("Cannot execute plan: unsatisfied dependencies")

            tasks = []
            for name in ready:
                pending.discard(name)
                step = step_map[name]
                deps = {dep: completed[dep] for dep in step.depends_on}
                tasks.append(self._bounded_execute(name, step, deps))

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for name, result in zip(ready, results):
                    if isinstance(result, Exception):
                        agent_result = AgentResult(
                            status="error",
                            error=str(result),
                            attempts=0,
                        )
                    else:
                        agent_result = result
                    self.agent_results[name] = agent_result
                    completed[name] = agent_result
                    self._collect_evidence_from_agent(name, agent_result)

    async def _bounded_execute(self, name: str, step: PlanStep, deps: dict[str, AgentResult]) -> AgentResult:
        async with self.semaphore:
            started_at = datetime.utcnow()
            try:
                result = await asyncio.wait_for(
                    self._execute_step(name, step, deps),
                    timeout=settings.CHAT_TIMEOUT_SECONDS,
                )
                completed_at = datetime.utcnow()
                duration_ms = (completed_at - started_at).total_seconds() * 1000

                trace_entry = AgentTraceEntry(
                    agent_name=name,
                    status=result.status,
                    task_id=getattr(result.result, "task_id", None) if hasattr(result, "result") else None,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=round(duration_ms, 3),
                    dependencies=list(step.depends_on),
                    error=result.error,
                )
                self.agent_trace.append(trace_entry)
                return result
            except asyncio.TimeoutError:
                completed_at = datetime.utcnow()
                duration_ms = (completed_at - started_at).total_seconds() * 1000
                trace_entry = AgentTraceEntry(
                    agent_name=name,
                    status="timeout",
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=round(duration_ms, 3),
                    dependencies=list(step.depends_on),
                    error=f"timeout after {settings.CHAT_TIMEOUT_SECONDS}s",
                )
                self.agent_trace.append(trace_entry)
                return AgentResult(status="timeout", error=f"timeout after {settings.CHAT_TIMEOUT_SECONDS}s")
            except Exception as exc:
                completed_at = datetime.utcnow()
                duration_ms = (completed_at - started_at).total_seconds() * 1000
                trace_entry = AgentTraceEntry(
                    agent_name=name,
                    status="error",
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=round(duration_ms, 3),
                    dependencies=list(step.depends_on),
                    error=str(exc),
                )
                self.agent_trace.append(trace_entry)
                raise

    async def _execute_step(self, name: str, step: PlanStep, deps: dict[str, AgentResult]) -> AgentResult:
        if name == "IntentAgent":
            return await self._run_intent_agent()
        elif name == "WeatherAgent":
            return await self._run_weather_agent(deps)
        elif name == "PFZAgent":
            return await self._run_pfz_agent(deps)
        elif name == "WarningsAgent":
            return await self._run_warnings_agent(deps)
        elif name == "RouteAgent":
            return await self._run_route_agent(deps)
        elif name == "SafetyEngine":
            return self._run_safety_engine(deps)
        elif name == "EvidenceValidator":
            return self._run_evidence_validator(deps)
        elif name == "ResponseSynthesizer":
            return await self._run_response_synthesizer(deps)
        else:
            raise ValueError(f"Unknown agent: {name}")

    def _get_intent_from_deps(self, deps: dict[str, AgentResult]) -> dict:
        intent_result = deps.get("IntentAgent")
        if intent_result and hasattr(intent_result, "result") and intent_result.result:
            return intent_result.result.data or {}
        return {}

    def _get_agent_data(self, deps: dict[str, AgentResult], agent_name: str) -> Any:
        result = deps.get(agent_name)
        if result and hasattr(result, "result") and result.result:
            return result.result.data
        return None

    async def _run_intent_agent(self) -> AgentResult:
        agent = IntentAgent(name="intent")
        return await agent.run(
            message=self.context.user_message,
            user_location=self.context.user_location,
            user_lat=self.context.user_lat,
            user_lon=self.context.user_lon,
            requested_radius_km=self.context.requested_radius_km,
        )

    async def _run_weather_agent(self, deps: dict[str, AgentResult]) -> AgentResult:
        intent_data = self._get_intent_from_deps(deps)
        agent = WeatherAgent(name="weather")
        return await agent.run(
            db=self.context.db,
            lat=intent_data.get("latitude") or 0.0,
            lon=intent_data.get("longitude") or 0.0,
            radius_km=intent_data.get("requested_radius_km") or 10.0,
        )

    async def _run_pfz_agent(self, deps: dict[str, AgentResult]) -> AgentResult:
        intent_data = self._get_intent_from_deps(deps)
        agent = PFZAgent(name="pfz")
        return await agent.run(
            db=self.context.db,
            lat=intent_data.get("latitude") or 0.0,
            lon=intent_data.get("longitude") or 0.0,
            radius_km=intent_data.get("requested_radius_km") or 10.0,
        )

    async def _run_warnings_agent(self, deps: dict[str, AgentResult]) -> AgentResult:
        intent_data = self._get_intent_from_deps(deps)
        agent = WarningsAgent(name="warnings")
        return await agent.run(
            db=self.context.db,
            lat=intent_data.get("latitude") or 0.0,
            lon=intent_data.get("longitude") or 0.0,
            radius_km=intent_data.get("requested_radius_km") or 10.0,
        )

    async def _run_route_agent(self, deps: dict[str, AgentResult]) -> AgentResult:
        agent = RouteAgent(name="route")
        return await agent.run(
            db=self.context.db,
            waypoints=self.context.route_waypoints or [],
            vessel_type=self.context.vessel_type,
            max_wave_height=self.context.max_wave_height,
        )

    def _run_safety_engine(self, deps: dict[str, AgentResult]) -> AgentResult:
        warnings_data = self._get_agent_data(deps, "WarningsAgent") or []
        observations_data = self._get_agent_data(deps, "WeatherAgent") or []
        pfz_zones_data = self._get_agent_data(deps, "PFZAgent") or []
        route_data = self._get_agent_data(deps, "RouteAgent") or {}
        geofence_violations = route_data.get("geofence_violations", []) if isinstance(route_data, dict) else []

        warnings_list = []
        if isinstance(warnings_data, list):
            for w in warnings_data:
                if isinstance(w, dict):
                    warnings_list.append(w)

        observations_list = []
        if isinstance(observations_data, list):
            for o in observations_data:
                if isinstance(o, dict):
                    observations_list.append(o)

        pfz_list = []
        if isinstance(pfz_zones_data, list):
            for p in pfz_zones_data:
                if isinstance(p, dict):
                    pfz_list.append(p)

        source_health = self._build_source_health(deps)

        safety_result = SafetyEngine.evaluate(
            warnings=warnings_list,
            observations=observations_list,
            pfz_zones=pfz_list,
            geofence_violations=geofence_violations,
            source_health=source_health,
        )

        evidence_items = []
        if safety_result.hazard_breakdown:
            if safety_result.hazard_breakdown.wave is not None:
                evidence_items.append(AgentEvidence(
                    source="safety_engine",
                    variable="wave_hazard_score",
                    value=safety_result.hazard_breakdown.wave,
                    unit="score",
                    confidence=1.0,
                    why_it_matters="Deterministic wave hazard score.",
                ))
            if safety_result.hazard_breakdown.wind is not None:
                evidence_items.append(AgentEvidence(
                    source="safety_engine",
                    variable="wind_hazard_score",
                    value=safety_result.hazard_breakdown.wind,
                    unit="score",
                    confidence=1.0,
                    why_it_matters="Deterministic wind hazard score.",
                ))
        self.aggregated_evidence.extend(evidence_items)

        return AgentResult(
            status="success",
            result=safety_result,
            attempts=1,
        )

    def _run_evidence_validator(self, deps: dict[str, AgentResult]) -> AgentResult:
        claims = [
            EvidenceClaim(variable="wave_hazard_score", min_confidence=0.0),
            EvidenceClaim(variable="wind_hazard_score", min_confidence=0.0),
            EvidenceClaim(variable="lightning_hazard_score", min_confidence=0.0),
            EvidenceClaim(variable="geofence_hazard_score", min_confidence=0.0),
            EvidenceClaim(variable="warning", min_confidence=0.0),
            EvidenceClaim(variable="pfz_score", min_confidence=0.0),
            EvidenceClaim(variable="route_cost", min_confidence=0.0),
            EvidenceClaim(variable="temperature", min_confidence=0.0),
            EvidenceClaim(variable="salinity", min_confidence=0.0),
            EvidenceClaim(variable="sst", min_confidence=0.0),
            EvidenceClaim(variable="wave_height", min_confidence=0.0),
            EvidenceClaim(variable="wind_speed", min_confidence=0.0),
        ]

        evidence_items = []
        for item in self.aggregated_evidence:
            evidence_items.append(item.model_dump())

        for name, result in deps.items():
            if hasattr(result, "result") and result.result and hasattr(result.result, "evidence"):
                for ev in result.result.evidence:
                    evidence_items.append(ev.model_dump() if hasattr(ev, "model_dump") else dict(ev))

        validation_result = EvidenceValidator.validate(claims, evidence_items)

        return AgentResult(
            status="success",
            result=validation_result,
            attempts=1,
        )

    async def _run_response_synthesizer(self, deps: dict[str, AgentResult]) -> AgentResult:
        safety_result = None
        for name, result in deps.items():
            if name == "SafetyEngine" and result and hasattr(result, "result") and result.result:
                safety_result = result.result
                break

        validation_result = None
        for name, result in deps.items():
            if name == "EvidenceValidator" and result and hasattr(result, "result") and result.result:
                validation_result = result.result
                break

        validated_evidence = []
        if validation_result and hasattr(validation_result, "supported_claims"):
            for item in self.aggregated_evidence:
                if item.variable in validation_result.supported_claims:
                    validated_evidence.append(item.model_dump() if hasattr(item, "model_dump") else dict(item))

        warnings_data = self._get_agent_data(deps, "WarningsAgent") or []
        warnings_list = []
        if isinstance(warnings_data, list):
            for w in warnings_data:
                if isinstance(w, dict):
                    warnings_list.append(w)

        all_evidence = []
        for item in self.aggregated_evidence:
            all_evidence.append(item.model_dump() if hasattr(item, "model_dump") else dict(item))

        agent_results_summary = []
        for name, result in deps.items():
            agent_results_summary.append({
                "agent_name": name,
                "status": result.status if hasattr(result, "status") else "unknown",
                "error": result.error if hasattr(result, "error") else None,
            })

        agent = ResponseSynthesizer(name="synthesizer")
        return await agent.run(
            user_message=self.context.user_message,
            language=self.context.language or "en",
            evidence=all_evidence,
            safety_badge=getattr(safety_result, "safety_badge", None),
            fishing_suitability=getattr(safety_result, "fishing_suitability", None),
            hazard_breakdown={
                "wave": getattr(getattr(safety_result, "hazard_breakdown", None), "wave", None),
                "wind": getattr(getattr(safety_result, "hazard_breakdown", None), "wind", None),
                "lightning": getattr(getattr(safety_result, "hazard_breakdown", None), "lightning", None),
                "geofence": getattr(getattr(safety_result, "hazard_breakdown", None), "geofence", None),
            } if safety_result else None,
            warnings=warnings_list,
            agent_results=agent_results_summary,
            follow_up_suggestions=[],
        )

    def _extract_safety_result(self) -> Optional[dict]:
        result = self.agent_results.get("SafetyEngine")
        if result and hasattr(result, "result") and result.result:
            safety = result.result
            return {
                "marine_hazard_index": getattr(safety, "marine_hazard_index", None),
                "safety_badge": getattr(safety, "safety_badge", None),
                "hazard_breakdown": {
                    "wave": getattr(getattr(safety, "hazard_breakdown", None), "wave", None),
                    "wind": getattr(getattr(safety, "hazard_breakdown", None), "wind", None),
                    "lightning": getattr(getattr(safety, "hazard_breakdown", None), "lightning", None),
                    "geofence": getattr(getattr(safety, "hazard_breakdown", None), "geofence", None),
                } if safety else None,
                "fishing_suitability": getattr(safety, "fishing_suitability", None),
                "is_indeterminate": getattr(safety, "is_indeterminate", False),
                "reasons": getattr(safety, "reasons", []),
            }
        return None

    def _extract_validation_result(self) -> Optional[dict]:
        result = self.agent_results.get("EvidenceValidator")
        if result and hasattr(result, "result") and result.result:
            validation = result.result
            return {
                "is_valid": getattr(validation, "is_valid", False),
                "supported_claims": getattr(validation, "supported_claims", []),
                "unsupported_claims": getattr(validation, "unsupported_claims", []),
                "issues": [
                    {
                        "claim": getattr(issue, "claim", ""),
                        "issue": getattr(issue, "issue", ""),
                        "severity": getattr(issue, "severity", ""),
                    }
                    for issue in getattr(validation, "issues", [])
                ],
                "overall_confidence": getattr(validation, "overall_confidence", 0.0),
            }
        return None

    def _extract_synthesis_result(self) -> Optional[dict]:
        result = self.agent_results.get("ResponseSynthesizer")
        if result and hasattr(result, "result") and result.result:
            synthesis = result.result
            if hasattr(synthesis, "model_dump"):
                return synthesis.model_dump()
            return dict(synthesis)
        return None

    def _collect_agent_results(self) -> list[AgentResultData]:
        results = []
        for name, agent_result in self.agent_results.items():
            result_data = None
            if hasattr(agent_result, "result") and agent_result.result:
                if hasattr(agent_result.result, "model_dump"):
                    result_data = agent_result.result.model_dump()
                else:
                    result_data = dict(agent_result.result) if isinstance(agent_result.result, dict) else str(agent_result.result)
            results.append(AgentResultData(
                agent_name=name,
                status=agent_result.status if hasattr(agent_result, "status") else "unknown",
                data=result_data,
                errors=[agent_result.error] if hasattr(agent_result, "error") and agent_result.error else [],
                attempts=agent_result.attempts if hasattr(agent_result, "attempts") else 0,
            ))
        return results

    def _build_source_health(self, deps: dict[str, AgentResult]) -> dict[str, Any]:
        health: dict[str, Any] = {}
        for name, result in deps.items():
            if not hasattr(result, "result") or not result.result:
                continue
            agent_result_data = result.result
            if hasattr(agent_result_data, "source_status"):
                source_status = agent_result_data.source_status
            elif hasattr(result, "status"):
                source_status = result.status
            else:
                source_status = "unknown"
            health[name] = {"status": source_status}
        return health

    def _enforce_evidence_limits(self) -> None:
        max_evidence = getattr(settings, "MAX_AGGREGATED_EVIDENCE", 500)
        if len(self.aggregated_evidence) > max_evidence:
            logger.warning(
                "Enforcing aggregated evidence limit: %d > %d",
                len(self.aggregated_evidence),
                max_evidence,
            )
            priority_order = {
                "warning": 0,
                "wave_hazard_score": 1,
                "wind_hazard_score": 2,
                "lightning_hazard_score": 3,
                "geofence_hazard_score": 4,
                "pfz_score": 5,
                "route_cost": 6,
                "sst": 7,
                "temperature": 8,
                "salinity": 9,
            }

            def sort_key(ev: AgentEvidence) -> tuple[int, str, str]:
                return (
                    priority_order.get(ev.variable, 99),
                    ev.source or "",
                    ev.variable or "",
                )

            self.aggregated_evidence.sort(key=sort_key)
            self.aggregated_evidence = self.aggregated_evidence[:max_evidence]

    def _collect_evidence_from_agent(self, name: str, result: AgentResult) -> None:
        agent_data = None
        if hasattr(result, "result") and result.result:
            agent_data = result.result
        elif hasattr(result, "evidence"):
            agent_data = result
        if not agent_data:
            return
        if hasattr(agent_data, "evidence"):
            for ev in agent_data.evidence:
                if hasattr(ev, "model_dump"):
                    ev_dict = ev.model_dump()
                elif hasattr(ev, "__dict__"):
                    ev_dict = {k: v for k, v in ev.__dict__.items() if not k.startswith("_")}
                else:
                    ev_dict = dict(ev)
                existing_keys = {
                    (e.source, e.variable, e.valid_time, e.value)
                    for e in self.aggregated_evidence
                }
                key = (ev_dict.get("source"), ev_dict.get("variable"), ev_dict.get("valid_time"), ev_dict.get("value"))
                if key not in existing_keys:
                     self.aggregated_evidence.append(ev)

