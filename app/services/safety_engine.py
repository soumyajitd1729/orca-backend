from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.enums import WarningSeverity

logger = logging.getLogger("orca")

WAVE_HEIGHT_MODERATE_M = 2.0
WAVE_HEIGHT_HIGH_M = 4.0
WAVE_HEIGHT_EXTREME_M = 6.0

WIND_SPEED_MODERATE_KT = 20.0
WIND_SPEED_HIGH_KT = 35.0
WIND_SPEED_EXTREME_KT = 50.0

IMD_CRITICAL_SEVERITIES = {WarningSeverity.high, WarningSeverity.extreme}

MHI_SAFE_MAX = 39
MHI_CAUTION_MAX = 69


@dataclass
class HazardBreakdown:
    wave: Optional[float] = None
    wind: Optional[float] = None
    lightning: Optional[float] = None
    geofence: Optional[float] = None


@dataclass
class SafetyResult:
    marine_hazard_index: Optional[float] = None
    safety_badge: Optional[str] = None
    hazard_breakdown: HazardBreakdown = field(default_factory=HazardBreakdown)
    fishing_suitability: Optional[str] = None
    is_indeterminate: bool = False
    reasons: list[str] = field(default_factory=list)


class SafetyEngine:
    @staticmethod
    def _get_numeric_value(observation: dict[str, Any]) -> Optional[float]:
        value = observation.get("value")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_imd_warning(warning: dict[str, Any]) -> bool:
        issued_by = (warning.get("issued_by") or "").lower()
        return "imd" in issued_by

    @staticmethod
    def _normalize_severity(severity: Any) -> Optional[WarningSeverity]:
        if isinstance(severity, WarningSeverity):
            return severity
        if isinstance(severity, str):
            try:
                return WarningSeverity(severity.lower())
            except ValueError:
                return None
        return None

    @staticmethod
    def _get_imd_min_mhi(
        warnings: list[dict[str, Any]],
    ) -> tuple[Optional[float], Optional[str]]:
        for warning in warnings:
            if not SafetyEngine._is_imd_warning(warning):
                continue
            severity = SafetyEngine._normalize_severity(warning.get("severity"))
            if severity == WarningSeverity.extreme:
                return 70.0, "extreme IMD warning active"
            if severity == WarningSeverity.high:
                return 40.0, "high IMD warning active"
        return None, None

    @staticmethod
    def _calculate_wave_hazard(
        observations: list[dict[str, Any]],
    ) -> tuple[Optional[float], Optional[str]]:
        wave_values = []
        for obs in observations:
            variable = (obs.get("variable") or "").lower()
            if "wave" in variable:
                value = SafetyEngine._get_numeric_value(obs)
                if value is not None:
                    wave_values.append(value)

        if not wave_values:
            return None, "wave data unavailable"

        max_wave = max(wave_values)
        if max_wave >= WAVE_HEIGHT_EXTREME_M:
            score = 100.0
            reason = f"extreme wave height {max_wave:.1f}m"
        elif max_wave >= WAVE_HEIGHT_HIGH_M:
            score = 70.0
            reason = f"high wave height {max_wave:.1f}m"
        elif max_wave >= WAVE_HEIGHT_MODERATE_M:
            score = 30.0
            reason = f"moderate wave height {max_wave:.1f}m"
        else:
            score = 0.0
            reason = f"calm wave height {max_wave:.1f}m"

        return score, reason

    @staticmethod
    def _calculate_wind_hazard(
        observations: list[dict[str, Any]],
    ) -> tuple[Optional[float], Optional[str]]:
        wind_values = []
        for obs in observations:
            variable = (obs.get("variable") or "").lower()
            if "wind" in variable:
                value = SafetyEngine._get_numeric_value(obs)
                if value is not None:
                    wind_values.append(value)

        if not wind_values:
            return None, "wind data unavailable"

        max_wind = max(wind_values)
        if max_wind >= WIND_SPEED_EXTREME_KT:
            score = 100.0
            reason = f"extreme wind speed {max_wind:.1f}kt"
        elif max_wind >= WIND_SPEED_HIGH_KT:
            score = 70.0
            reason = f"high wind speed {max_wind:.1f}kt"
        elif max_wind >= WIND_SPEED_MODERATE_KT:
            score = 30.0
            reason = f"moderate wind speed {max_wind:.1f}kt"
        else:
            score = 0.0
            reason = f"calm wind speed {max_wind:.1f}kt"

        return score, reason

    @staticmethod
    def _calculate_lightning_hazard(
        warnings: list[dict[str, Any]],
    ) -> tuple[Optional[float], Optional[str]]:
        for warning in warnings:
            warning_type = (warning.get("type") or "").lower()
            if "lightning" in warning_type:
                return 100.0, "lightning warning active"
        return 0.0, "no lightning warning"

    @staticmethod
    def _calculate_geofence_hazard(
        geofence_violations: list[dict[str, Any]],
    ) -> tuple[Optional[float], Optional[str]]:
        if geofence_violations:
            return 100.0, f"{len(geofence_violations)} geofence violation(s)"
        return 0.0, "no geofence violations"

    @staticmethod
    def _calculate_staleness_penalty(
        source_health: Optional[dict[str, Any]],
    ) -> float:
        if not source_health:
            return 0.0
        penalty = 0.0
        for source_name, source_data in source_health.items():
            status = (source_data.get("status") or "").lower()
            if status in ("stale", "unavailable"):
                penalty += 5.0
        return min(penalty, 15.0)

    @staticmethod
    def _calculate_fishing_suitability(
        mhi: float,
        pfz_zones: list[dict[str, Any]],
        safety_badge: Optional[str],
    ) -> Optional[str]:
        if safety_badge == "UNSAFE":
            return "POOR"

        if safety_badge == "CAUTION":
            return "FAIR"

        if not pfz_zones:
            return "FAIR"

        scores = []
        for zone in pfz_zones:
            score = zone.get("score")
            if score is not None:
                try:
                    scores.append(float(score))
                except (TypeError, ValueError):
                    pass

        if not scores:
            return "FAIR"

        avg_score = sum(scores) / len(scores)
        if avg_score >= 0.7:
            return "EXCELLENT"
        if avg_score >= 0.4:
            return "GOOD"
        return "FAIR"

    @staticmethod
    def evaluate(
        warnings: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        pfz_zones: list[dict[str, Any]],
        geofence_violations: list[dict[str, Any]],
        source_health: Optional[dict[str, Any]] = None,
    ) -> SafetyResult:
        reasons: list[str] = []

        wave_score, wave_reason = SafetyEngine._calculate_wave_hazard(observations)
        wind_score, wind_reason = SafetyEngine._calculate_wind_hazard(observations)
        lightning_score, lightning_reason = SafetyEngine._calculate_lightning_hazard(
            warnings
        )
        geofence_score, geofence_reason = SafetyEngine._calculate_geofence_hazard(
            geofence_violations
        )

        hazard_breakdown = HazardBreakdown(
            wave=wave_score,
            wind=wind_score,
            lightning=lightning_score,
            geofence=geofence_score,
        )

        scores = [
            s
            for s in [wave_score, wind_score, lightning_score, geofence_score]
            if s is not None
        ]
        if not scores:
            return SafetyResult(
                is_indeterminate=True,
                reasons=["no hazard data available"],
                hazard_breakdown=hazard_breakdown,
            )

        if wave_score is None and wind_score is None and not warnings:
            return SafetyResult(
                is_indeterminate=True,
                reasons=["no observation or warning data available"],
                hazard_breakdown=hazard_breakdown,
            )

        mhi = max(scores)
        active_hazards = [s for s in scores if s > 0]
        if len(active_hazards) > 1:
            mhi += 10.0
            reasons.append("multiple concurrent hazards detected")

        missing_critical = []
        if wave_score is None:
            missing_critical.append("wave")
        if wind_score is None:
            missing_critical.append("wind")
        if missing_critical:
            mhi += 10.0
            reasons.append(f"uncertainty: missing {', '.join(missing_critical)} data")

        staleness_penalty = SafetyEngine._calculate_staleness_penalty(source_health)
        if staleness_penalty > 0:
            mhi += staleness_penalty
            reasons.append("uncertainty: stale data sources")

        imd_min_mhi, imd_reason = SafetyEngine._get_imd_min_mhi(warnings)
        if imd_min_mhi is not None:
            reasons.append(f"IMD precedence: {imd_reason}")
            mhi = max(mhi, imd_min_mhi)

        mhi = min(max(mhi, 0.0), 100.0)

        if mhi >= 70:
            safety_badge = "UNSAFE"
        elif mhi >= 40:
            safety_badge = "CAUTION"
        else:
            safety_badge = "SAFE"

        if wave_reason:
            reasons.append(f"wave: {wave_reason}")
        if wind_reason:
            reasons.append(f"wind: {wind_reason}")
        if lightning_reason:
            reasons.append(f"lightning: {lightning_reason}")
        if geofence_reason:
            reasons.append(f"geofence: {geofence_reason}")

        fishing_suitability = SafetyEngine._calculate_fishing_suitability(
            mhi=mhi,
            pfz_zones=pfz_zones,
            safety_badge=safety_badge,
        )

        return SafetyResult(
            marine_hazard_index=round(mhi, 2),
            safety_badge=safety_badge,
            hazard_breakdown=hazard_breakdown,
            fishing_suitability=fishing_suitability,
            is_indeterminate=False,
            reasons=reasons,
        )
