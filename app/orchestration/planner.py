from __future__ import annotations

import logging
from typing import Optional

from app.schemas.agent import ExecutionPlan, NormalizedIntent, PlanStep

logger = logging.getLogger("orca")

KNOWN_AGENTS = {
    "IntentAgent",
    "WeatherAgent",
    "PFZAgent",
    "WarningsAgent",
    "RouteAgent",
    "SafetyEngine",
    "EvidenceValidator",
    "ResponseSynthesizer",
}

MAX_PLAN_DEPTH = 4

SAFETY_QUERY_TYPES = {"fishing", "warnings", "route", "weather"}


def _is_safety_query(intent: NormalizedIntent) -> bool:
    if intent.query_type in SAFETY_QUERY_TYPES:
        return True
    if intent.warning_intent or intent.pfz_intent or intent.weather_intent:
        return True
    return False


def _deduplicate_steps(steps: list[PlanStep]) -> list[PlanStep]:
    seen = set()
    unique = []
    for step in steps:
        if step.agent_name not in seen:
            seen.add(step.agent_name)
            unique.append(step)
    return unique


def _validate_plan(steps: list[PlanStep]) -> list[str]:
    issues = []

    step_map = {step.agent_name: step for step in steps}

    def _get_depth(agent_name: str, visited: Optional[set] = None) -> int:
        if visited is None:
            visited = set()
        if agent_name in visited:
            return 0
        visited.add(agent_name)
        step = step_map.get(agent_name)
        if not step or not step.depends_on:
            return 0
        return 1 + max(_get_depth(dep, visited) for dep in step.depends_on)

    max_depth = max((_get_depth(name) for name in step_map), default=0)
    if max_depth > MAX_PLAN_DEPTH:
        issues.append(
            f"Plan depth {max_depth} exceeds maximum allowed depth {MAX_PLAN_DEPTH}"
        )

    for step in steps:
        if step.agent_name not in KNOWN_AGENTS:
            issues.append(f"Unknown agent in plan: {step.agent_name}")

    return issues


def _build_fishing_plan(intent: NormalizedIntent) -> list[PlanStep]:
    steps = [
        PlanStep(agent_name="IntentAgent", depends_on=[], input_mapping={}),
        PlanStep(agent_name="WeatherAgent", depends_on=["IntentAgent"], input_mapping={}),
        PlanStep(agent_name="PFZAgent", depends_on=["IntentAgent"], input_mapping={}),
        PlanStep(agent_name="WarningsAgent", depends_on=["IntentAgent"], input_mapping={}),
        PlanStep(agent_name="SafetyEngine", depends_on=["WeatherAgent", "PFZAgent", "WarningsAgent"], input_mapping={}),
        PlanStep(agent_name="EvidenceValidator", depends_on=["SafetyEngine"], input_mapping={}),
        PlanStep(agent_name="ResponseSynthesizer", depends_on=["EvidenceValidator"], input_mapping={}),
    ]
    return steps


def _build_warnings_plan(intent: NormalizedIntent) -> list[PlanStep]:
    steps = [
        PlanStep(agent_name="IntentAgent", depends_on=[], input_mapping={}),
        PlanStep(agent_name="WarningsAgent", depends_on=["IntentAgent"], input_mapping={}),
        PlanStep(agent_name="SafetyEngine", depends_on=["WarningsAgent"], input_mapping={}),
        PlanStep(agent_name="EvidenceValidator", depends_on=["SafetyEngine"], input_mapping={}),
        PlanStep(agent_name="ResponseSynthesizer", depends_on=["EvidenceValidator"], input_mapping={}),
    ]
    return steps


def _build_weather_plan(intent: NormalizedIntent) -> list[PlanStep]:
    steps = [
        PlanStep(agent_name="IntentAgent", depends_on=[], input_mapping={}),
        PlanStep(agent_name="WeatherAgent", depends_on=["IntentAgent"], input_mapping={}),
        PlanStep(agent_name="EvidenceValidator", depends_on=["WeatherAgent"], input_mapping={}),
        PlanStep(agent_name="ResponseSynthesizer", depends_on=["EvidenceValidator"], input_mapping={}),
    ]
    return steps


def _build_pfz_plan(intent: NormalizedIntent) -> list[PlanStep]:
    steps = [
        PlanStep(agent_name="IntentAgent", depends_on=[], input_mapping={}),
        PlanStep(agent_name="PFZAgent", depends_on=["IntentAgent"], input_mapping={}),
        PlanStep(agent_name="EvidenceValidator", depends_on=["PFZAgent"], input_mapping={}),
        PlanStep(agent_name="ResponseSynthesizer", depends_on=["EvidenceValidator"], input_mapping={}),
    ]
    return steps


def _build_route_plan(intent: NormalizedIntent) -> list[PlanStep]:
    steps = [
        PlanStep(agent_name="IntentAgent", depends_on=[], input_mapping={}),
        PlanStep(agent_name="RouteAgent", depends_on=["IntentAgent"], input_mapping={}),
        PlanStep(agent_name="EvidenceValidator", depends_on=["RouteAgent"], input_mapping={}),
    ]
    if _is_safety_query(intent):
        steps.append(
            PlanStep(agent_name="SafetyEngine", depends_on=["EvidenceValidator"], input_mapping={})
        )
        steps.append(
            PlanStep(agent_name="ResponseSynthesizer", depends_on=["SafetyEngine"], input_mapping={})
        )
    else:
        steps.append(
            PlanStep(agent_name="ResponseSynthesizer", depends_on=["EvidenceValidator"], input_mapping={})
        )
    return steps


def _build_general_plan(intent: NormalizedIntent) -> list[PlanStep]:
    steps = [
        PlanStep(agent_name="IntentAgent", depends_on=[], input_mapping={}),
        PlanStep(agent_name="ResponseSynthesizer", depends_on=["IntentAgent"], input_mapping={}),
    ]
    return steps


def create_plan(intent: NormalizedIntent) -> ExecutionPlan:
    if intent.query_type == "fishing":
        steps = _build_fishing_plan(intent)
    elif intent.query_type == "warnings":
        steps = _build_warnings_plan(intent)
    elif intent.query_type == "weather":
        steps = _build_weather_plan(intent)
    elif intent.query_type == "pfz":
        steps = _build_pfz_plan(intent)
    elif intent.query_type == "route":
        steps = _build_route_plan(intent)
    else:
        steps = _build_general_plan(intent)

    steps = _deduplicate_steps(steps)

    issues = _validate_plan(steps)
    if issues:
        logger.error("Plan validation failed: %s", issues)
        raise ValueError(f"Invalid execution plan: {'; '.join(issues)}")

    requires_safety = _is_safety_query(intent)

    return ExecutionPlan(
        steps=steps,
        max_depth=MAX_PLAN_DEPTH,
        requires_safety_evaluation=requires_safety,
    )
