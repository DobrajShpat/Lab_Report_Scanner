from __future__ import annotations

from uuid import uuid4

from pipeline.models import NormalizedObservation, StructuredReport
from core.utils import to_fhir_datetime


def build_fhir_bundle(report: StructuredReport, accepted_only: bool = True) -> dict:
    observations = report.observations
    if accepted_only:
        observations = [obs for obs in observations if obs.acceptance_decision == "accepted" and obs.loinc_code]

    patient_id = report.patient.patient_id or f"patient-{uuid4().hex[:8]}"
    entries = [{"resource": {"resourceType": "Patient", "id": patient_id}}]
    collected_at = to_fhir_datetime(report.patient.collected_at)

    for index, obs in enumerate(observations, start=1):
        resource = {
            "resourceType": "Observation",
            "id": f"observation-{index}",
            "status": obs.status,
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": obs.loinc_code,
                        "display": obs.loinc_display or obs.raw_test_name,
                    }
                ],
                "text": obs.canonical_name or obs.raw_test_name,
            },
            "subject": {"reference": f"Patient/{patient_id}"},
        }
        if collected_at:
            resource["effectiveDateTime"] = collected_at
        if obs.standardized_value is not None:
            resource["valueQuantity"] = {
                "value": obs.standardized_value,
                "unit": obs.standardized_unit,
            }
        if obs.reference_low is not None or obs.reference_high is not None:
            ref_range: dict = {}
            if obs.reference_low is not None:
                ref_range["low"] = {"value": obs.reference_low, "unit": obs.standardized_unit}
            if obs.reference_high is not None:
                ref_range["high"] = {"value": obs.reference_high, "unit": obs.standardized_unit}
            resource["referenceRange"] = [ref_range]
        if obs.interpretation:
            resource["interpretation"] = [{"text": obs.interpretation}]
        entries.append({"resource": resource})

    return {"resourceType": "Bundle", "type": "collection", "entry": entries}
