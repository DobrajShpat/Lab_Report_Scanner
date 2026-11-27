from __future__ import annotations

from pipeline.models import NormalizedObservation, ValidationFlag


def assign_tier(obs: NormalizedObservation) -> NormalizedObservation:
    flags = {flag.code for flag in obs.validation_flags}

    if not obs.raw_test_name or obs.raw_test_name.lower().startswith("section"):
        obs.acceptance_decision = "rejected"
        return obs

    if not obs.loinc_code:
        obs.acceptance_decision = "rejected"
        obs.validation_flags.append(
            ValidationFlag(code="UNKNOWN_TEST", severity="error", message="No LOINC mapping")
        )
        return obs

    blocking = {"IMPOSSIBLE_VALUE", "UNSAFE_UNIT_NORMALIZATION", "UNIT_SEMANTIC_MISMATCH"}
    if flags & blocking:
        obs.acceptance_decision = "rejected"
        return obs

    review_triggers = {"UNMAPPED_TEST", "LOW_MAPPING_CONFIDENCE", "MISSING_UNIT", "LOW_OCR_CONFIDENCE"}
    if flags & review_triggers or obs.standardized_value is None:
        obs.acceptance_decision = "needs_review"
        return obs

    if obs.interpretation in {"suspicious", "critical"}:
        obs.acceptance_decision = "needs_review"
        return obs

    obs.acceptance_decision = "accepted"
    return obs


def validate_all(observations: list[NormalizedObservation]) -> list[NormalizedObservation]:
    return [assign_tier(obs) for obs in observations]
