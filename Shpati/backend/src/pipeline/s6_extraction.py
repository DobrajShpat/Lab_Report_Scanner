from __future__ import annotations

from pipeline.models import OCRLine, PatientMetadata, RawObservation, ReportMetadata
from pipeline.s4_layout import analyze_layout
from pipeline.s5_parser import ReportParser


def run_layout(ocr_lines: list[OCRLine]) -> dict:
    analysis = analyze_layout(ocr_lines)
    return {
        "regions": analysis.region_counts,
        "multi_column": analysis.multi_column_layout,
        "retained_lines": len(analysis.rows),
        "total_lines": analysis.total_lines,
    }


def run_parser(source_file: str, ocr_lines: list[OCRLine]) -> tuple[ReportMetadata, PatientMetadata, list[str], list[RawObservation], dict]:
    parser = ReportParser()
    report_meta, patient_meta, raw_text, raw_observations, diagnostics = parser.parse(source_file, ocr_lines)
    return report_meta, patient_meta, raw_text, raw_observations, diagnostics


def extract_rows(
    source_file: str,
    ocr_lines: list[OCRLine],
) -> dict:
    report_meta, patient_meta, raw_text, raw_observations, diagnostics = run_parser(source_file, ocr_lines)
    layout = run_layout(ocr_lines)
    return {
        "report": report_meta.model_dump(),
        "patient": patient_meta.model_dump(),
        "raw_text": raw_text,
        "raw_observations": [row.model_dump() for row in raw_observations],
        "diagnostics": diagnostics,
        "layout": layout,
    }
