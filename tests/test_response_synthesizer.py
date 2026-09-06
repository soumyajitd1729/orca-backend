from unittest.mock import AsyncMock, patch

import pytest

from app.agents.response_synthesizer import ResponseSynthesizer
from app.schemas.agent import AgentResultData


def _fake_groq_response(answer="Test answer", suggestions=None, evidence_summary=None):
    suggestions = suggestions or []
    evidence_summary = evidence_summary or []
    payload = {
        "answer": answer,
        "follow_up_suggestions": suggestions,
        "evidence_summary": evidence_summary,
        "safety_badge": "SAFE",
        "fishing_suitability": "GOOD",
    }
    content = __import__("json").dumps(payload)
    return type(
        "FakeResponse",
        (),
        {
            "choices": [
                type(
                    "Choice",
                    (),
                    {"message": type("Msg", (), {"content": content})},
                )()
            ]
        },
    )()


@pytest.mark.asyncio
async def test_response_synthesizer_valid_evidence(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return _fake_groq_response(
            answer="Wave height is 2.4 m and wind speed is 15 kt.",
            suggestions=["Check PFZ zones", "View route"],
        )

    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client.chat", fake_chat)

    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="What are the conditions?",
        language="en",
        evidence=[
            {"source": "incois", "variable": "wave_height", "value": 2.4, "unit": "m"},
            {"source": "incois", "variable": "wind_speed", "value": 15.0, "unit": "kt"},
        ],
        safety_badge="SAFE",
    )
    assert result.status == "success"
    assert result.result.data["answer"] == "Wave height is 2.4 m and wind speed is 15 kt."
    assert len(result.result.data["follow_up_suggestions"]) == 2
    assert result.result.data["safety_badge"] == "SAFE"


@pytest.mark.asyncio
async def test_response_synthesizer_missing_evidence(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return _fake_groq_response(
            answer="Current safety cannot be confirmed because required marine data is unavailable.",
            suggestions=[],
        )

    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client.chat", fake_chat)

    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="Is it safe?",
        language="en",
        evidence=[],
        safety_badge=None,
    )
    assert result.status == "success"
    assert "cannot be confirmed" in result.result.data["answer"].lower()


@pytest.mark.asyncio
async def test_response_synthesizer_unavailable_safety_data(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return _fake_groq_response(
            answer="Safety assessment is currently unavailable.",
            suggestions=["Try again later"],
        )

    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client.chat", fake_chat)

    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="Is it safe?",
        language="en",
        evidence=[],
        safety_badge=None,
    )
    assert result.status == "success"
    assert "unavailable" in result.result.data["answer"].lower()


@pytest.mark.asyncio
async def test_response_synthesizer_safe_response(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return _fake_groq_response(
            answer="Conditions are safe for marine activities.",
            suggestions=["Check weather updates"],
        )

    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client.chat", fake_chat)

    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="Is it safe?",
        language="en",
        safety_badge="SAFE",
    )
    assert result.status == "success"
    assert result.result.data["safety_badge"] == "SAFE"


@pytest.mark.asyncio
async def test_response_synthesizer_caution_response(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return _fake_groq_response(
            answer="Exercise caution. Moderate hazards detected.",
            suggestions=["Monitor warnings"],
        )

    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client.chat", fake_chat)

    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="What is the risk?",
        language="en",
        safety_badge="CAUTION",
    )
    assert result.status == "success"
    assert result.result.data["safety_badge"] == "CAUTION"


@pytest.mark.asyncio
async def test_response_synthesizer_unsafe_response(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return _fake_groq_response(
            answer="Unsafe conditions. Avoid marine activities.",
            suggestions=["Seek safe harbor"],
        )

    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client.chat", fake_chat)

    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="Is it safe?",
        language="en",
        safety_badge="UNSAFE",
    )
    assert result.status == "success"
    assert result.result.data["safety_badge"] == "UNSAFE"


@pytest.mark.asyncio
async def test_response_synthesizer_multilingual(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return _fake_groq_response(
            answer="Wave height 2.4 m. Conditions safe.",
            suggestions=[],
        )

    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client.chat", fake_chat)

    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="क्या सुरक्षित है?",
        language="hi",
        evidence=[{"source": "incois", "variable": "wave_height", "value": 2.4, "unit": "m"}],
        safety_badge="SAFE",
    )
    assert result.status == "success"
    assert result.result.data["language"] == "hi"
    assert "2.4 m" in result.result.data["answer"]


@pytest.mark.asyncio
async def test_response_synthesizer_numeric_unit_preservation(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return _fake_groq_response(
            answer="Wave height is 2.4 m and wind speed is 15 kt.",
            suggestions=[],
        )

    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client.chat", fake_chat)

    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="Conditions?",
        language="en",
        evidence=[
            {"source": "incois", "variable": "wave_height", "value": 2.4, "unit": "m"},
            {"source": "incois", "variable": "wind_speed", "value": 15.0, "unit": "kt"},
        ],
    )
    assert result.status == "success"
    assert "2.4 m" in result.result.data["answer"]
    assert "15 kt" in result.result.data["answer"]


@pytest.mark.asyncio
async def test_response_synthesizer_malformed_llm_output(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return type(
            "FakeResponse",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {"message": type("Msg", (), {"content": "This is not JSON."})},
                    )()
                ]
            },
        )()

    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client.chat", fake_chat)

    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="Conditions?",
        language="en",
        evidence=[],
        safety_badge=None,
    )
    assert result.status == "partial"
    assert "issue" in result.result.data["answer"].lower() or "error" in result.result.data["answer"].lower()


@pytest.mark.asyncio
async def test_response_synthesizer_no_safety_calculation_by_llm(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return _fake_groq_response(
            answer="Based on the data, MHI is 45 and safety is CAUTION.",
            suggestions=[],
        )

    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client.chat", fake_chat)

    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="Is it safe?",
        language="en",
        safety_badge="SAFE",
    )
    assert result.status == "success"
    assert result.result.data["safety_badge"] == "SAFE"


@pytest.mark.asyncio
async def test_response_synthesizer_groq_unavailable(monkeypatch):
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "")
    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="Conditions?",
        language="en",
        evidence=[],
        safety_badge=None,
    )
    assert result.status == "partial"
    assert "unable to generate" in result.result.data["answer"].lower()
    assert any("groq_api_key_not_configured" in e for e in result.result.errors)


@pytest.mark.asyncio
async def test_response_synthesizer_groq_failure(monkeypatch):
    async def fake_chat(*args, **kwargs):
        raise RuntimeError("Groq down")

    monkeypatch.setattr("app.agents.response_synthesizer.groq_client._api_key", "fake-key")
    monkeypatch.setattr("app.agents.response_synthesizer.groq_client.chat", fake_chat)

    agent = ResponseSynthesizer(name="synthesizer")
    result = await agent.run(
        user_message="Conditions?",
        language="en",
        evidence=[],
        safety_badge=None,
    )
    assert result.status == "partial"
    assert "issue" in result.result.data["answer"].lower() or "error" in result.result.data["answer"].lower()
