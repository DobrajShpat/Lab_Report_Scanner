import numpy as np

from pipeline.models import OCRLine
from pipeline.complete_extractor import extract_complete_report
from pipeline.s2_preprocess import generate_variants
from pipeline.s3_ocr import ScoreDrivenOCR


def _line(text: str, confidence: float = 0.8, x: float = 100, y: float = 100) -> OCRLine:
    return OCRLine(
        text=text,
        confidence=confidence,
        bbox=[[x, y], [x + 80, y], [x + 80, y + 20], [x, y + 20]],
        x_min=x,
        y_min=y,
        x_max=x + 80,
        y_max=y + 20,
    )


def test_consensus_recovers_partially_read_number():
    base = _line("2.5", 0.82)
    recovered_a = _line("12.5", 0.76)
    recovered_b = _line("12.5", 0.79)

    fused = ScoreDrivenOCR._fuse_variant_reads(
        best_variant="clahe",
        best_lines=[base],
        variant_runs={
            "clahe": [base],
            "adaptive": [recovered_a],
            "upscaled_clahe": [recovered_b],
        },
    )

    assert len(fused) == 1
    assert fused[0].text == "12.5"
    assert fused[0].recovery_status == "consensus_recovered"
    assert "2.5" in fused[0].alternatives


def test_single_disagreement_is_kept_and_marked_ambiguous():
    base = _line("12.5", 0.85)
    alternate = _line("17.5", 0.83)

    fused = ScoreDrivenOCR._fuse_variant_reads(
        best_variant="clahe",
        best_lines=[base],
        variant_runs={"clahe": [base], "adaptive": [alternate]},
    )

    assert fused[0].text == "12.5"
    assert fused[0].recovery_status == "ambiguous"
    assert fused[0].alternatives == ["17.5"]


def test_missing_line_requires_two_variant_reads():
    recovered_a = _line("16700", 0.72)
    recovered_b = _line("16700", 0.78)

    # Best variant won overall but missed this token; two peers must agree.
    fused = ScoreDrivenOCR._fuse_variant_reads(
        best_variant="adaptive",
        best_lines=[],
        variant_runs={"clahe": [recovered_a], "sharpened": [recovered_b]},
    )

    assert len(fused) == 1
    assert fused[0].text == "16700"
    assert fused[0].recovery_status == "consensus_recovered"


def test_original_and_deskewed_families_are_not_fused():
    """Overlapping boxes across geometry frames must not swap digits."""
    base = _line("72", 0.9, x=100, y=100)
    # Same AABB as base, but from deskewed family — must be ignored.
    deskewed_peer_a = _line("7.2", 0.88, x=100, y=100)
    deskewed_peer_b = _line("7.2", 0.91, x=100, y=100)

    fused = ScoreDrivenOCR._fuse_variant_reads(
        best_variant="original",
        best_lines=[base],
        variant_runs={
            "original": [base],
            "clahe": [deskewed_peer_a],
            "adaptive": [deskewed_peer_b],
        },
    )

    assert len(fused) == 1
    assert fused[0].text == "72"
    assert fused[0].recovery_status == "original"
    assert fused[0].alternatives == []


def test_preprocess_includes_line_removal_and_upscaled_recovery_variants():
    image = np.full((120, 240, 3), 255, dtype=np.uint8)
    variants = {variant.name: variant for variant in generate_variants(image)}

    assert "table_lines_removed" in variants
    assert "upscaled_clahe" in variants
    assert variants["upscaled_clahe"].image.shape[:2] == (240, 480)
    assert variants["upscaled_clahe"].coordinate_scale == 2.0


def test_ambiguous_digit_marks_clinical_row_for_review():
    name = _line("GLUCOSE", x=10)
    value = _line("125", x=220)
    value.recovery_status = "ambiguous"
    value.alternatives = ["123", "128"]
    unit = _line("mg/dl", x=340)
    reference = _line("70 - 140", x=460)

    report = extract_complete_report(
        "ambiguous.png", [name, value, unit, reference]
    )

    assert report["rows"][0]["value"] == "125"
    assert report["rows"][0]["parse_status"] == "needs_review"
    assert report["rows"][0]["ocr_recovery_status"] == "ambiguous"
    assert report["rows"][0]["ocr_alternatives"] == ["123", "128"]
