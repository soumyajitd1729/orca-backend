from datetime import datetime, timezone, timedelta

import pytest

from app.services.safety_engine import SafetyEngine, SafetyResult, HazardBreakdown


def _observation(
    variable,
    value,
    unit,
    quality_flag="good",
    confidence=0.9,
    valid_time=None,
):
    if valid_time is None:
        valid_time = datetime.now(timezone.utc)
    return {
        "variable": variable,
        "value": value,
        "unit": unit,
        "quality_flag": quality_flag,
        "confidence": confidence,
        "valid_time": valid_time,
    }


def _warning(
    type,
    severity,
    issued_by="IMD",
    valid_from=None,
    valid_to=None,
):
    if valid_from is None:
        valid_from = datetime.now(timezone.utc) - timedelta(hours=1)
    if valid_to is None:
        valid_to = datetime.now(timezone.utc) + timedelta(hours=1)
    return {
        "type": type,
        "severity": severity,
        "issued_by": issued_by,
        "valid_from": valid_from.isoformat() if isinstance(valid_from, datetime) else valid_from,
        "valid_to": valid_to.isoformat() if isinstance(valid_to, datetime) else valid_to,
    }


def test_mhi_range_0_to_100():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[
            _observation("wave_height", 7.0, "m"),
            _observation("wind_speed", 60.0, "kt"),
        ],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.marine_hazard_index is not None
    assert 0 <= result.marine_hazard_index <= 100


def test_hazard_breakdown_populated():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[
            _observation("wave_height", 5.0, "m"),
            _observation("wind_speed", 40.0, "kt"),
        ],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.hazard_breakdown is not None
    assert result.hazard_breakdown.wave is not None
    assert result.hazard_breakdown.wind is not None


def test_safe_decision():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[
            _observation("wave_height", 1.0, "m"),
            _observation("wind_speed", 10.0, "kt"),
        ],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.safety_badge == "SAFE"
    assert result.marine_hazard_index < 40


def test_caution_decision():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[
            _observation("wave_height", 3.0, "m"),
            _observation("wind_speed", 25.0, "kt"),
        ],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.safety_badge == "CAUTION"
    assert 40 <= result.marine_hazard_index < 70


def test_unsafe_decision():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[
            _observation("wave_height", 7.0, "m"),
            _observation("wind_speed", 60.0, "kt"),
        ],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.safety_badge == "UNSAFE"
    assert result.marine_hazard_index >= 70


def test_insufficient_data_returns_indeterminate():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.is_indeterminate is True
    assert result.safety_badge is None
    assert result.marine_hazard_index is None


def test_stale_data_increases_mhi():
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[
            _observation("wave_height", 1.0, "m", valid_time=old_time),
        ],
        pfz_zones=[],
        geofence_violations=[],
        source_health={"incois": {"status": "stale"}},
    )
    assert result.marine_hazard_index is not None
    assert result.marine_hazard_index >= 10


def test_imd_precedence_prevents_safe():
    result = SafetyEngine.evaluate(
        warnings=[
            _warning("cyclone", "high", issued_by="IMD"),
        ],
        observations=[
            _observation("wave_height", 1.0, "m"),
            _observation("wind_speed", 10.0, "kt"),
        ],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.safety_badge != "SAFE"
    assert result.marine_hazard_index >= 40


def test_imd_extreme_precedence_forces_unsafe():
    result = SafetyEngine.evaluate(
        warnings=[
            _warning("cyclone", "extreme", issued_by="IMD"),
        ],
        observations=[
            _observation("wave_height", 1.0, "m"),
            _observation("wind_speed", 10.0, "kt"),
        ],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.safety_badge == "UNSAFE"
    assert result.marine_hazard_index >= 70


def test_imd_precedence_with_unavailable_data():
    result = SafetyEngine.evaluate(
        warnings=[
            _warning("cyclone", "extreme", issued_by="IMD"),
        ],
        observations=[],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.safety_badge is not None
    assert result.safety_badge != "SAFE"
    assert result.marine_hazard_index >= 40


def test_fishing_suitability_excellent_with_pfz():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[
            _observation("wave_height", 1.0, "m"),
            _observation("wind_speed", 10.0, "kt"),
        ],
        pfz_zones=[{"score": 0.9}],
        geofence_violations=[],
    )
    assert result.fishing_suitability == "EXCELLENT"


def test_fishing_suitability_poor_when_unsafe():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[
            _observation("wave_height", 7.0, "m"),
        ],
        pfz_zones=[{"score": 0.9}],
        geofence_violations=[],
    )
    assert result.fishing_suitability == "POOR"


def test_fishing_suitability_fair_without_pfz():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[
            _observation("wave_height", 1.0, "m"),
        ],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.fishing_suitability == "FAIR"


def test_deterministic_results():
    inputs = dict(
        warnings=[],
        observations=[
            _observation("wave_height", 3.0, "m"),
            _observation("wind_speed", 25.0, "kt"),
        ],
        pfz_zones=[],
        geofence_violations=[],
    )
    result1 = SafetyEngine.evaluate(**inputs)
    result2 = SafetyEngine.evaluate(**inputs)
    assert result1.marine_hazard_index == result2.marine_hazard_index
    assert result1.safety_badge == result2.safety_badge
    assert result1.fishing_suitability == result2.fishing_suitability


def test_missing_wave_data_returns_none_breakdown():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[
            _observation("wind_speed", 10.0, "kt"),
        ],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.hazard_breakdown.wave is None
    assert result.hazard_breakdown.wind is not None


def test_geofence_violation_increases_hazard():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[
            _observation("wave_height", 1.0, "m"),
        ],
        pfz_zones=[],
        geofence_violations=[{"id": "mpa-1", "name": "Gulf of Mannar"}],
    )
    assert result.hazard_breakdown.geofence == 100.0
    assert result.marine_hazard_index >= 30


def test_lightning_warning_increases_hazard():
    result = SafetyEngine.evaluate(
        warnings=[
            _warning("lightning", "moderate", issued_by="IMD"),
        ],
        observations=[
            _observation("wave_height", 1.0, "m"),
        ],
        pfz_zones=[],
        geofence_violations=[],
    )
    assert result.hazard_breakdown.lightning == 100.0
