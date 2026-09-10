from unittest.mock import AsyncMock, patch

import pytest

from app.agents.intent_agent import IntentAgent
from app.schemas.agent import AgentResultData, NormalizedIntent, NormalizedIntent


@pytest.mark.asyncio
async def test_intent_agent_marine_warning_query(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="What are the current IMD warnings?")
    assert isinstance(result.result, AgentResultData)
    assert result.result.status in ("success", "partial")
    assert result.result.data["query_type"] == "warnings"
    assert "warnings" in result.result.data["intents"]


@pytest.mark.asyncio
async def test_intent_agent_fishing_pfz_query(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="Where can I fish near Kakinada?")
    assert result.result.data["query_type"] == "fishing"
    assert "pfz" in result.result.data["intents"]


@pytest.mark.asyncio
async def test_intent_agent_weather_query(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="What is the wave height forecast?")
    assert result.result.data["query_type"] == "weather"
    assert "weather" in result.result.data["intents"]


@pytest.mark.asyncio
async def test_intent_agent_route_query(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="Plan a route from Chennai to Visakhapatnam")
    assert result.result.data["query_type"] == "route"
    assert "route" in result.result.data["intents"]


@pytest.mark.asyncio
async def test_intent_agent_extracts_location_name(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="Is it safe to fish near Kakinada?", user_location="Kakinada")
    assert result.result.data["location_name"] == "Kakinada"


@pytest.mark.asyncio
async def test_intent_agent_supplied_user_location(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="Are there any warnings?", user_location="Chennai")
    assert result.result.data["location_name"] == "Chennai"


@pytest.mark.asyncio
async def test_intent_agent_groq_unavailable(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="What are the warnings?")
    assert isinstance(result.result, AgentResultData)
    assert result.result.status == "partial"
    assert any("groq_api_key_not_configured" in e for e in result.result.errors)
    assert result.result.data["query_type"] == "warnings"


@pytest.mark.asyncio
async def test_intent_agent_no_fabricated_coordinates(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="Is it safe near Kakinada?")
    assert "latitude" not in result.result.data or result.result.data.get("latitude") is None
    assert "longitude" not in result.result.data or result.result.data.get("longitude") is None


@pytest.mark.asyncio
async def test_intent_agent_general_fallback(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="Hello ORCA")
    assert result.result.data["query_type"] == "general"
    assert "general" in result.result.data["intents"]


@pytest.mark.asyncio
async def test_intent_agent_groq_failure_fallback(monkeypatch):
    async def fake_chat(*args, **kwargs):
        raise RuntimeError("Groq down")

    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.intent_agent.groq_client.chat", fake_chat)

    agent = IntentAgent(name="intent")
    result = await agent.run(message="What are the warnings?")
    assert isinstance(result.result, AgentResultData)
    assert result.result.status == "partial"
    assert any("llm_unavailable" in e for e in result.result.errors)
    assert result.result.data["query_type"] == "warnings"


@pytest.mark.asyncio
async def test_intent_agent_resolves_known_location_coordinates(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="Is it safe near Kakinada?", user_location="Kakinada")
    assert result.result.data["latitude"] == 16.9891
    assert result.result.data["longitude"] == 82.2475


@pytest.mark.asyncio
async def test_intent_agent_uses_explicit_coordinates(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(
        message="Is it safe here?",
        user_location="unknown place",
        user_lat=10.0,
        user_lon=20.0,
    )
    assert result.result.data["latitude"] == 10.0
    assert result.result.data["longitude"] == 20.0


@pytest.mark.asyncio
async def test_intent_agent_no_coordinates_for_unknown_location(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="Is it safe at Atlantis?", user_location="Atlantis")
    assert result.result.data.get("latitude") is None
    assert result.result.data.get("longitude") is None


@pytest.mark.asyncio
async def test_intent_agent_extended_fields_present(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="What is the wave forecast?", requested_radius_km=25.0)
    data = result.result.data
    assert "requested_radius_km" in data
    assert data["requested_radius_km"] == 25.0
    assert "weather_intent" in data
    assert data["weather_intent"] is True
    assert "language" in data
    assert data["language"] == "en"


@pytest.mark.asyncio
async def test_intent_agent_multilingual_language(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="नमस्ते", user_location="Kakinada")
    assert result.result.data["language"] == "en"
    assert result.result.data["location_name"] == "Kakinada"


@pytest.mark.asyncio
async def test_intent_agent_no_coordinate_hallucination_from_llm(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return type(
            "FakeResponse",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {
                            "message": type(
                                "Msg", (), {"content": '{"query_type": "fishing", "latitude": 99.0, "longitude": 99.0}'}
                            )
                        },
                    )()
                ]
            },
        )()

    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.intent_agent.groq_client.chat", fake_chat)

    agent = IntentAgent(name="intent")
    result = await agent.run(message="Where can I fish?", user_location="Kakinada")
    assert result.result.data["latitude"] == 16.9891
    assert result.result.data["longitude"] == 82.2475


@pytest.mark.asyncio
async def test_intent_agent_time_expression_tomorrow_morning(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="Is it safe to fish tomorrow morning?")
    assert result.result.data["time_expression"] == "tomorrow_morning"
    assert result.result.data["query_type"] == "fishing"


@pytest.mark.asyncio
async def test_intent_agent_time_expression_tomorrow_evening(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="Is it safe to fish tomorrow evening?")
    assert result.result.data["time_expression"] == "tomorrow_evening"


@pytest.mark.asyncio
async def test_intent_agent_time_expression_tomorrow_afternoon(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="What about tomorrow afternoon?")
    assert result.result.data["time_expression"] == "tomorrow_afternoon"


@pytest.mark.asyncio
async def test_intent_agent_time_expression_tomorrow(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="What will the weather be like tomorrow?")
    assert result.result.data["time_expression"] == "tomorrow"


@pytest.mark.asyncio
async def test_intent_agent_time_expression_today(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="What is the weather today?")
    assert result.result.data["time_expression"] == "today"


@pytest.mark.asyncio
async def test_intent_agent_time_expression_none_for_current_weather(monkeypatch):
    monkeypatch.setattr("app.agents.intent_agent.groq_client._api_key", "")
    agent = IntentAgent(name="intent")
    result = await agent.run(message="What is the weather condition at my location?")
    assert result.result.data["time_expression"] is None
