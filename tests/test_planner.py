import pytest

from app.orchestration.planner import (
    KNOWN_AGENTS,
    MAX_PLAN_DEPTH,
    SAFETY_QUERY_TYPES,
    create_plan,
)
from app.schemas.agent import NormalizedIntent


def test_fishing_plan_contains_required_agents():
    intent = NormalizedIntent(query_type="fishing")
    plan = create_plan(intent)
    agent_names = [step.agent_name for step in plan.steps]
    assert "IntentAgent" in agent_names
    assert "WeatherAgent" in agent_names
    assert "PFZAgent" in agent_names
    assert "WarningsAgent" in agent_names
    assert "SafetyEngine" in agent_names
    assert "EvidenceValidator" in agent_names
    assert "ResponseSynthesizer" in agent_names


def test_warning_plan_contains_required_agents():
    intent = NormalizedIntent(query_type="warnings")
    plan = create_plan(intent)
    agent_names = [step.agent_name for step in plan.steps]
    assert "IntentAgent" in agent_names
    assert "WarningsAgent" in agent_names
    assert "EvidenceValidator" in agent_names
    assert "ResponseSynthesizer" in agent_names
    assert "SafetyEngine" in agent_names


def test_weather_plan_contains_required_agents():
    intent = NormalizedIntent(query_type="weather")
    plan = create_plan(intent)
    agent_names = [step.agent_name for step in plan.steps]
    assert "IntentAgent" in agent_names
    assert "WeatherAgent" in agent_names
    assert "EvidenceValidator" in agent_names
    assert "ResponseSynthesizer" in agent_names


def test_pfz_plan_contains_required_agents():
    intent = NormalizedIntent(query_type="pfz")
    plan = create_plan(intent)
    agent_names = [step.agent_name for step in plan.steps]
    assert "IntentAgent" in agent_names
    assert "PFZAgent" in agent_names
    assert "EvidenceValidator" in agent_names
    assert "ResponseSynthesizer" in agent_names


def test_route_plan_contains_required_agents():
    intent = NormalizedIntent(query_type="route")
    plan = create_plan(intent)
    agent_names = [step.agent_name for step in plan.steps]
    assert "IntentAgent" in agent_names
    assert "RouteAgent" in agent_names
    assert "EvidenceValidator" in agent_names
    assert "ResponseSynthesizer" in agent_names
    assert "SafetyEngine" in agent_names


def test_general_plan_skips_domain_agents():
    intent = NormalizedIntent(query_type="general")
    plan = create_plan(intent)
    agent_names = [step.agent_name for step in plan.steps]
    assert "IntentAgent" in agent_names
    assert "ResponseSynthesizer" in agent_names
    assert "WeatherAgent" not in agent_names
    assert "PFZAgent" not in agent_names
    assert "WarningsAgent" not in agent_names


def test_unknown_agent_rejected():
    original = create_plan.__code__
    import app.orchestration.planner as planner_module

    original_known = planner_module.KNOWN_AGENTS.copy()
    try:
        planner_module.KNOWN_AGENTS = {"IntentAgent", "ResponseSynthesizer"}
        intent = NormalizedIntent(query_type="weather")
        with pytest.raises(ValueError, match="Unknown agent"):
            create_plan(intent)
    finally:
        planner_module.KNOWN_AGENTS = original_known


def test_max_plan_depth_enforced():
    import app.orchestration.planner as planner_module

    original_max = planner_module.MAX_PLAN_DEPTH
    try:
        planner_module.MAX_PLAN_DEPTH = 1
        intent = NormalizedIntent(query_type="fishing")
        with pytest.raises(ValueError, match="exceeds maximum allowed depth"):
            create_plan(intent)
    finally:
        planner_module.MAX_PLAN_DEPTH = original_max


def test_safety_engine_cannot_be_bypassed_for_route():
    intent = NormalizedIntent(query_type="route", route_intent=True)
    plan = create_plan(intent)
    agent_names = [step.agent_name for step in plan.steps]
    assert "SafetyEngine" in agent_names
    assert "EvidenceValidator" in agent_names


def test_safety_engine_cannot_be_bypassed_for_warnings():
    intent = NormalizedIntent(query_type="warnings", warning_intent=True)
    plan = create_plan(intent)
    agent_names = [step.agent_name for step in plan.steps]
    assert "SafetyEngine" in agent_names
    assert "EvidenceValidator" in agent_names


def test_plan_steps_are_deduplicated():
    intent = NormalizedIntent(query_type="fishing")
    plan = create_plan(intent)
    agent_names = [step.agent_name for step in plan.steps]
    assert len(agent_names) == len(set(agent_names))


def test_plan_dependencies_are_valid():
    intent = NormalizedIntent(query_type="fishing")
    plan = create_plan(intent)
    step_names = {step.agent_name for step in plan.steps}
    for step in plan.steps:
        for dep in step.depends_on:
            assert dep in step_names


def test_plan_requires_safety_evaluation_for_fishing():
    intent = NormalizedIntent(query_type="fishing")
    plan = create_plan(intent)
    assert plan.requires_safety_evaluation is True


def test_plan_does_not_require_safety_for_general():
    intent = NormalizedIntent(query_type="general")
    plan = create_plan(intent)
    assert plan.requires_safety_evaluation is False
