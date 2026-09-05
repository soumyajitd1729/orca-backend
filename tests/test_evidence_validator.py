from datetime import datetime, timezone, timedelta

import pytest

from app.services.evidence_validator import (
    EvidenceClaim,
    EvidenceValidator,
    ValidationIssue,
    ValidationResult,
)


def _evidence(
    variable,
    value,
    unit,
    source="incois",
    confidence=0.9,
    valid_time=None,
):
    if valid_time is None:
        valid_time = datetime.now(timezone.utc)
    return {
        "variable": variable,
        "value": value,
        "unit": unit,
        "source": source,
        "confidence": confidence,
        "valid_time": valid_time,
    }


def test_valid_evidence_returns_valid():
    result = EvidenceValidator.validate(
        claims=[
            EvidenceClaim(variable="wave_height", min_confidence=0.8),
        ],
        evidence_items=[
            _evidence("wave_height", "2.5", "m", confidence=0.9),
        ],
    )
    assert result.is_valid is True
    assert "wave_height" in result.supported_claims
    assert result.overall_confidence > 0


def test_missing_evidence_returns_invalid():
    result = EvidenceValidator.validate(
        claims=[
            EvidenceClaim(variable="wave_height"),
        ],
        evidence_items=[],
    )
    assert result.is_valid is False
    assert "wave_height" in result.unsupported_claims


def test_missing_required_fields_returns_invalid():
    result = EvidenceValidator.validate(
        claims=[
            EvidenceClaim(variable="wave_height"),
        ],
        evidence_items=[
            {"variable": "wave_height", "value": "2.5"},
        ],
    )
    assert result.is_valid is False
    assert "wave_height" in result.unsupported_claims
    assert any(
        "missing required fields" in issue.issue for issue in result.issues
    )


def test_low_confidence_returns_invalid():
    result = EvidenceValidator.validate(
        claims=[
            EvidenceClaim(variable="wave_height", min_confidence=0.9),
        ],
        evidence_items=[
            _evidence("wave_height", "2.5", "m", confidence=0.5),
        ],
    )
    assert result.is_valid is False
    assert "wave_height" in result.unsupported_claims


def test_stale_evidence_returns_invalid():
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    result = EvidenceValidator.validate(
        claims=[
            EvidenceClaim(variable="wave_height", max_age_seconds=3600),
        ],
        evidence_items=[
            _evidence("wave_height", "2.5", "m", valid_time=old_time),
        ],
    )
    assert result.is_valid is False
    assert "wave_height" in result.unsupported_claims
    assert any(
        issue.severity == "warning" and "stale" in issue.issue for issue in result.issues
    )


def test_conflicting_evidence_detected():
    result = EvidenceValidator.validate(
        claims=[
            EvidenceClaim(variable="wave_height"),
        ],
        evidence_items=[
            _evidence("wave_height", "2.5", "m"),
            _evidence("wave_height", "5.0", "m"),
        ],
    )
    assert "wave_height" in result.supported_claims
    assert any(
        issue.severity == "warning" and "conflicting" in issue.issue
        for issue in result.issues
    )


def test_partial_validation_result():
    result = EvidenceValidator.validate(
        claims=[
            EvidenceClaim(variable="wave_height"),
            EvidenceClaim(variable="wind_speed"),
        ],
        evidence_items=[
            _evidence("wave_height", "2.5", "m"),
        ],
    )
    assert "wave_height" in result.supported_claims
    assert "wind_speed" in result.unsupported_claims
    assert not result.is_valid


def test_overall_confidence_calculation():
    result = EvidenceValidator.validate(
        claims=[
            EvidenceClaim(variable="wave_height"),
            EvidenceClaim(variable="wind_speed"),
        ],
        evidence_items=[
            _evidence("wave_height", "2.5", "m", confidence=0.8),
            _evidence("wind_speed", "15.0", "kt", confidence=0.9),
        ],
    )
    assert result.is_valid is True
    assert 0 <= result.overall_confidence <= 1
    assert abs(result.overall_confidence - 0.85) < 0.01


def test_evidence_validator_accepts_model_objects():
    from app.models.evidence_item import EvidenceItem

    item = EvidenceItem(
        task_id=None,
        source="incois",
        variable="wave_height",
        value="2.5",
        unit="m",
        valid_time=datetime.now(timezone.utc),
        confidence=0.9,
    )
    result = EvidenceValidator.validate(
        claims=[EvidenceClaim(variable="wave_height")],
        evidence_items=[item],
    )
    assert result.is_valid is True
    assert "wave_height" in result.supported_claims


def test_source_filter_matches_evidence():
    result = EvidenceValidator.validate(
        claims=[
            EvidenceClaim(variable="wave_height", source="incois"),
        ],
        evidence_items=[
            _evidence("wave_height", "2.5", "m", source="mosdac"),
            _evidence("wave_height", "2.5", "m", source="incois"),
        ],
    )
    assert result.is_valid is True
    assert "wave_height" in result.supported_claims


def test_source_filter_rejects_non_matching_evidence():
    result = EvidenceValidator.validate(
        claims=[
            EvidenceClaim(variable="wave_height", source="incois"),
        ],
        evidence_items=[
            _evidence("wave_height", "2.5", "m", source="mosdac"),
        ],
    )
    assert result.is_valid is False
    assert "wave_height" in result.unsupported_claims
