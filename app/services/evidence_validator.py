from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("orca")

REQUIRED_EVIDENCE_FIELDS = ["source", "variable", "value", "unit", "valid_time", "confidence"]


@dataclass
class EvidenceClaim:
    variable: str
    source: Optional[str] = None
    min_confidence: float = 0.0
    max_age_seconds: Optional[float] = None


@dataclass
class ValidationIssue:
    claim: str
    issue: str
    severity: str


@dataclass
class ValidationResult:
    is_valid: bool
    supported_claims: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    overall_confidence: float = 0.0


class EvidenceValidator:
    @staticmethod
    def _normalize_evidence(item: Any) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            return item.model_dump()
        if isinstance(item, dict):
            return item
        if hasattr(item, "__dict__"):
            return {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
        return {}

    @staticmethod
    def _is_evidence_stale(
        evidence: dict[str, Any], max_age_seconds: Optional[float]
    ) -> bool:
        if max_age_seconds is None:
            return False
        valid_time = evidence.get("valid_time")
        if valid_time is None:
            return True
        if isinstance(valid_time, datetime):
            now = datetime.now(timezone.utc)
            valid_time_utc = (
                valid_time if valid_time.tzinfo else valid_time.replace(tzinfo=timezone.utc)
            )
            age = (now - valid_time_utc).total_seconds()
            return age > max_age_seconds
        if isinstance(valid_time, str):
            try:
                parsed = datetime.fromisoformat(valid_time.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                age = (now - parsed).total_seconds()
                return age > max_age_seconds
            except (ValueError, TypeError):
                return True
        return True

    @staticmethod
    def _check_required_fields(evidence: dict[str, Any]) -> list[str]:
        missing = []
        for field_name in REQUIRED_EVIDENCE_FIELDS:
            if field_name not in evidence or evidence[field_name] is None:
                missing.append(field_name)
        return missing

    @staticmethod
    def _match_evidence_to_claim(
        evidence_items: list[dict[str, Any]],
        claim: EvidenceClaim,
    ) -> list[dict[str, Any]]:
        matches = []
        for item in evidence_items:
            if item.get("variable") != claim.variable:
                continue
            if claim.source and item.get("source") != claim.source:
                continue
            matches.append(item)
        return matches

    @staticmethod
    def _detect_conflicts(
        evidence_items: list[dict[str, Any]],
    ) -> list[ValidationIssue]:
        by_variable: dict[str, list[dict[str, Any]]] = {}
        for item in evidence_items:
            var = item.get("variable")
            if var not in by_variable:
                by_variable[var] = []
            by_variable[var].append(item)

        conflicts = []
        for var, items in by_variable.items():
            if len(items) > 1:
                values = set()
                for item in items:
                    val = item.get("value")
                    if val is not None:
                        values.add(str(val))
                if len(values) > 1:
                    conflicts.append(
                        ValidationIssue(
                            claim=var,
                            issue=f"conflicting values: {', '.join(sorted(values))}",
                            severity="warning",
                        )
                    )
        return conflicts

    @staticmethod
    def validate(
        claims: list[EvidenceClaim],
        evidence_items: list[Any],
    ) -> ValidationResult:
        normalized_items = [EvidenceValidator._normalize_evidence(item) for item in evidence_items]

        supported_claims: list[str] = []
        unsupported_claims: list[str] = []
        issues: list[ValidationIssue] = []
        confidences: list[float] = []

        for claim in claims:
            matches = EvidenceValidator._match_evidence_to_claim(normalized_items, claim)

            if not matches:
                unsupported_claims.append(claim.variable)
                issues.append(
                    ValidationIssue(
                        claim=claim.variable,
                        issue="no supporting evidence found",
                        severity="error",
                    )
                )
                continue

            best = max(matches, key=lambda e: float(e.get("confidence", 0.0)))

            missing_fields = EvidenceValidator._check_required_fields(best)
            if missing_fields:
                unsupported_claims.append(claim.variable)
                issues.append(
                    ValidationIssue(
                        claim=claim.variable,
                        issue=f"missing required fields: {', '.join(missing_fields)}",
                        severity="error",
                    )
                )
                continue

            confidence = float(best.get("confidence", 0.0))
            if confidence < claim.min_confidence:
                unsupported_claims.append(claim.variable)
                issues.append(
                    ValidationIssue(
                        claim=claim.variable,
                        issue=f"confidence {confidence:.2f} below minimum {claim.min_confidence:.2f}",
                        severity="error",
                    )
                )
                continue

            if EvidenceValidator._is_evidence_stale(best, claim.max_age_seconds):
                unsupported_claims.append(claim.variable)
                issues.append(
                    ValidationIssue(
                        claim=claim.variable,
                        issue="evidence is stale",
                        severity="warning",
                    )
                )
                continue

            supported_claims.append(claim.variable)
            confidences.append(confidence)

        conflict_issues = EvidenceValidator._detect_conflicts(normalized_items)
        issues.extend(conflict_issues)

        overall_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )
        has_errors = any(issue.severity == "error" for issue in issues)
        is_valid = len(unsupported_claims) == 0 and not has_errors

        return ValidationResult(
            is_valid=is_valid,
            supported_claims=supported_claims,
            unsupported_claims=unsupported_claims,
            issues=issues,
            overall_confidence=overall_confidence,
        )
