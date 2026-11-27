from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class OCRLine(BaseModel):
    text: str
    confidence: float
    bbox: list[list[float]]
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    source_variants: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    recovery_status: Literal["original", "consensus_recovered", "ambiguous"] = "original"


class PatientMetadata(BaseModel):
    patient_name: str | None = None
    patient_id: str | None = None
    gender: str | None = None
    date_of_birth: str | None = None
    collected_at: str | None = None
    reported_at: str | None = None


class ReportMetadata(BaseModel):
    source_file: str
    lab_name: str | None = None
    report_id: str | None = None
    extracted_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    panel_sections: list[str] = Field(default_factory=list)


class RawObservation(BaseModel):
    raw_test_name: str
    raw_value: str | None = None
    raw_unit: str | None = None
    raw_reference_range: str | None = None
    section: str | None = None
    line_text: str


class ValidationFlag(BaseModel):
    code: str
    severity: str
    message: str


class NormalizedObservation(BaseModel):
    raw_test_name: str
    canonical_name: str | None = None
    loinc_code: str | None = None
    loinc_display: str | None = None
    category: str | None = None
    value: float | None = None
    value_text: str | None = None
    standardized_value: float | None = None
    original_unit: str | None = None
    standardized_unit: str | None = None
    reference_range_text: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    interpretation: str | None = None
    status: str = "final"
    section: str | None = None
    match_strategy: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    validation_flags: list[ValidationFlag] = Field(default_factory=list)
    acceptance_decision: Literal["accepted", "needs_review", "rejected"] = "needs_review"
    row_id: str | None = None


class ProcessingMetrics(BaseModel):
    total_ocr_lines: int = 0
    mapped_observations: int = 0
    unmapped_observations: int = 0
    mapping_rate: float = 0.0
    accepted_rows: int = 0
    review_rows: int = 0
    rejected_rows: int = 0
    report_status: str = "success"
    notes: list[str] = Field(default_factory=list)


class StructuredReport(BaseModel):
    report: ReportMetadata
    patient: PatientMetadata
    observations: list[NormalizedObservation]
    unmatched_rows: list[str] = Field(default_factory=list)
    raw_text: list[str] = Field(default_factory=list)
    metrics: ProcessingMetrics = Field(default_factory=ProcessingMetrics)
