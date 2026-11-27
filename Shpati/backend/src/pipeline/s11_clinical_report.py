from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pipeline.models import NormalizedObservation, StructuredReport

ADMIN_FRAGMENTS = (
    "invoice",
    "hospital",
    "diagnostic center",
    "pathology lab",
    "authorized by",
    "printed by",
    "printed time",
    "report generated",
    "report gen",
    "referred by",
    "doctor",
    "consultant",
    "signature",
    "website",
    "www.",
    "accreditation",
    "iso ",
    "registration",
    "regn no",
    "receipt",
    "bill no",
    "sample collected at",
    "end of report",
    "computer generated",
    "medico legal",
    "address",
    "phone",
    "email",
    "laboratory report",
    "government",
)

OBSERVED_RANGE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*[-\u2013]\s*(\d+(?:[.,]\d+)?)$")


def _parse_float(value: str | float | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _is_admin_noise(obs: NormalizedObservation) -> bool:
    name = (obs.raw_test_name or "").lower()
    if any(fragment in name for fragment in ADMIN_FRAGMENTS):
        return True
    if name.startswith("section ") or name in {"test", "result", "reference range", "unit"}:
        return True
    return False


def _display_value(obs: NormalizedObservation) -> str | float | None:
    if obs.value_text:
        return obs.value_text
    if obs.standardized_value is not None:
        return obs.standardized_value
    if obs.value is not None:
        return obs.value
    return None


def _infer_interpretation(obs: NormalizedObservation) -> str | None:
    if obs.interpretation:
        return obs.interpretation.strip().lower()

    low = obs.reference_low
    high = obs.reference_high
    if low is None and high is None:
        return None

    if obs.value_text:
        match = OBSERVED_RANGE.match(str(obs.value_text).replace(" ", ""))
        if match and low is not None and high is not None:
            obs_low = _parse_float(match.group(1))
            obs_high = _parse_float(match.group(2))
            if obs_low is not None and obs_high is not None:
                if obs_low >= low and obs_high <= high:
                    return "normal"
                if obs_high > high:
                    return "high"
                if obs_low < low:
                    return "low"
                return "normal"

    value = obs.standardized_value if obs.standardized_value is not None else obs.value
    if value is None:
        return None
    if low is not None and value < low:
        return "low"
    if high is not None and value > high:
        return "high"
    if low is not None or high is not None:
        return "normal"
    return None


def _is_clinical_row(obs: NormalizedObservation) -> bool:
    if obs.acceptance_decision == "rejected":
        return False
    if _is_admin_noise(obs):
        return False
    if _display_value(obs) is None:
        return False
    if not (obs.raw_test_name or "").strip():
        return False
    return True


def build_clinical_report(structured: StructuredReport) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    summary = {"total": 0, "normal": 0, "high": 0, "low": 0, "unclassified": 0}

    for obs in structured.observations:
        if not _is_clinical_row(obs):
            continue

        interpretation = _infer_interpretation(obs)
        test_name = obs.canonical_name or obs.loinc_display or obs.raw_test_name
        value = _display_value(obs)
        unit = obs.standardized_unit or obs.original_unit
        reference = obs.reference_range_text
        if reference is None and obs.reference_low is not None and obs.reference_high is not None:
            reference = f"{obs.reference_low} - {obs.reference_high}"

        row = {
            "row_id": obs.row_id,
            "test_name": test_name.strip(),
            "value": value,
            "unit": unit,
            "reference_range": reference,
            "reference_low": obs.reference_low,
            "reference_high": obs.reference_high,
            "interpretation": interpretation,
            "section": obs.section,
            "loinc_code": obs.loinc_code,
            "ocr_source_text": (obs.provenance or {}).get("line_text"),
        }
        rows.append(row)

        summary["total"] += 1
        if interpretation == "normal":
            summary["normal"] += 1
        elif interpretation == "high":
            summary["high"] += 1
        elif interpretation == "low":
            summary["low"] += 1
        else:
            summary["unclassified"] += 1

    sections: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = row.get("section") or "General"
        sections.setdefault(key, []).append(row)

    ocr_lines = [str(row["ocr_source_text"]).strip() for row in rows if row.get("ocr_source_text")]
    ocr_text = {
        "line_count": len(ocr_lines),
        "lines": ocr_lines,
        "text": "\n".join(ocr_lines),
    }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "rows": rows,
        "sections": sections,
        "ocr_text": ocr_text,
    }


def build_ocr_text_artifact(clinical_report: dict[str, Any]) -> dict[str, Any]:
    ocr_text = clinical_report.get("ocr_text") or {}
    return {
        "generated_at": clinical_report.get("generated_at"),
        "source": "rapidocr",
        "description": "OCR-detected text for clinical lab rows only; administrative content excluded.",
        "line_count": ocr_text.get("line_count", 0),
        "lines": ocr_text.get("lines", []),
        "text": ocr_text.get("text", ""),
    }
