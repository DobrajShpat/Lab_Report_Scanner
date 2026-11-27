from __future__ import annotations

from dataclasses import dataclass

from pipeline.models import OCRLine
from core.utils import normalize_text

METADATA_HINTS = (
    "patient",
    "invoice",
    "report",
    "sample",
    "receipt",
    "referr",
    "doctor",
    "consult",
    "age",
    "sex",
    "gender",
    "dob",
    "collected",
    "reported",
    "printed",
    "accession",
    "bill",
)
LAB_HINTS = ("lab", "laboratory", "diagnostic", "pathology", "hospital")
SIGNATURE_HINTS = ("signature", "authorized", "stamp", "seal")
TABLE_HINTS = (
    "%",
    "mg/dl",
    "mmol/l",
    "cells/cmm",
    "lakhs/cumm",
    "10^3/ul",
    "10^6/ul",
)


@dataclass
class LayoutRow:
    text: str
    columns: list[str]
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    region: str


@dataclass
class LayoutAnalysis:
    rows: list[LayoutRow]
    filtered_low_confidence_lines: int
    filtered_region_lines: int
    total_lines: int
    multi_column_layout: bool
    region_counts: dict[str, int]


def sort_lines(lines: list[OCRLine]) -> list[OCRLine]:
    return sorted(lines, key=lambda item: (item.y_min, item.x_min))


def analyze_layout(lines: list[OCRLine]) -> LayoutAnalysis:
    ordered = sort_lines(lines)
    if not ordered:
        return LayoutAnalysis(
            rows=[],
            filtered_low_confidence_lines=0,
            filtered_region_lines=0,
            total_lines=0,
            multi_column_layout=False,
            region_counts={},
        )

    page_width = max(line.x_max for line in ordered)
    page_height = max(line.y_max for line in ordered)
    typical_height = _median([(line.y_max - line.y_min) for line in ordered], default=18.0)
    y_tolerance = max(12.0, typical_height * 0.75)

    filtered_low_confidence_lines = 0
    filtered_region_lines = 0
    cleaned_lines: list[OCRLine] = []
    for line in ordered:
        normalized = normalize_text(line.text)
        if not normalized:
            filtered_region_lines += 1
            continue
        if line.confidence < 0.35:
            filtered_low_confidence_lines += 1
            continue
        if _is_signature_or_stamp(line, normalized, page_width, page_height):
            filtered_region_lines += 1
            continue
        cleaned_lines.append(line)

    buckets: list[list[OCRLine]] = []
    for line in cleaned_lines:
        if not buckets:
            buckets.append([line])
            continue
        last_bucket = buckets[-1]
        last_y = sum((item.y_min + item.y_max) / 2 for item in last_bucket) / len(last_bucket)
        current_y = (line.y_min + line.y_max) / 2
        if abs(current_y - last_y) <= y_tolerance:
            last_bucket.append(line)
        else:
            buckets.append([line])

    rows: list[LayoutRow] = []
    region_counts: dict[str, int] = {}
    multi_column_layout = False

    for bucket in buckets:
        ordered_bucket = sorted(bucket, key=lambda item: item.x_min)
        columns = _row_columns(ordered_bucket, page_width)
        if len(columns) > 1:
            multi_column_layout = True
        text = " ".join(columns).strip()
        if not text:
            continue
        confidence = sum(item.confidence for item in ordered_bucket) / len(ordered_bucket)
        x_min = min(item.x_min for item in ordered_bucket)
        y_min = min(item.y_min for item in ordered_bucket)
        x_max = max(item.x_max for item in ordered_bucket)
        y_max = max(item.y_max for item in ordered_bucket)
        region = _classify_region(text, confidence, x_min, y_min, x_max, y_max, page_width, page_height)
        region_counts[region] = region_counts.get(region, 0) + 1
        rows.append(
            LayoutRow(
                text=text,
                columns=columns,
                confidence=confidence,
                x_min=x_min,
                y_min=y_min,
                x_max=x_max,
                y_max=y_max,
                region=region,
            )
        )

    return LayoutAnalysis(
        rows=rows,
        filtered_low_confidence_lines=filtered_low_confidence_lines,
        filtered_region_lines=filtered_region_lines,
        total_lines=len(lines),
        multi_column_layout=multi_column_layout,
        region_counts=region_counts,
    )


def reconstruct_lines(lines: list[OCRLine]) -> list[str]:
    return [row.text for row in analyze_layout(lines).rows]


def _row_columns(lines: list[OCRLine], page_width: float) -> list[str]:
    if not lines:
        return []
    columns: list[list[OCRLine]] = [[lines[0]]]
    widths = [(line.x_max - line.x_min) for line in lines]
    typical_width = _median(widths, default=120.0)
    gap_threshold = max(page_width * 0.08, typical_width * 1.5, 80.0)

    for line in lines[1:]:
        previous = columns[-1][-1]
        gap = line.x_min - previous.x_max
        if gap > gap_threshold:
            columns.append([line])
        else:
            columns[-1].append(line)

    return [" ".join(item.text.strip() for item in column if item.text.strip()) for column in columns]


def _classify_region(
    text: str,
    confidence: float,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    page_width: float,
    page_height: float,
) -> str:
    normalized = normalize_text(text)
    top_ratio = y_min / max(page_height, 1.0)
    bottom_ratio = y_max / max(page_height, 1.0)
    width_ratio = (x_max - x_min) / max(page_width, 1.0)

    if bottom_ratio > 0.9:
        return "footer"
    if any(hint in normalized for hint in SIGNATURE_HINTS):
        return "signature"
    if top_ratio < 0.18 and any(hint in normalized for hint in LAB_HINTS):
        return "header"
    if top_ratio < 0.3 and any(hint in normalized for hint in METADATA_HINTS):
        return "metadata"
    if bottom_ratio > 0.82 and (confidence < 0.6 or width_ratio < 0.35):
        return "footer"
    if _looks_like_table_row(normalized):
        return "table"
    if width_ratio > 0.75 and top_ratio < 0.18:
        return "header"
    return "body"


def _looks_like_table_row(normalized: str) -> bool:
    digit_count = sum(character.isdigit() for character in normalized)
    has_measurement_hint = any(hint in normalized for hint in TABLE_HINTS)
    return (digit_count >= 2 and has_measurement_hint) or (" -" in normalized and digit_count >= 2)


def _is_signature_or_stamp(line: OCRLine, normalized: str, page_width: float, page_height: float) -> bool:
    bottom_ratio = line.y_max / max(page_height, 1.0)
    edge_ratio = min(line.x_min, page_width - line.x_max) / max(page_width, 1.0)
    return bottom_ratio > 0.75 and line.confidence < 0.45 and edge_ratio < 0.2


def _median(values: list[float], default: float) -> float:
    if not values:
        return default
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return float((ordered[middle - 1] + ordered[middle]) / 2)
