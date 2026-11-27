from pipeline.complete_extractor import extract_complete_report
from pipeline.models import OCRLine


def _line(text: str, y: float, x: float = 10.0, conf: float = 0.95) -> OCRLine:
    return OCRLine(
        text=text,
        confidence=conf,
        bbox=[[x, y], [x + 80, y], [x + 80, y + 20], [x, y + 20]],
        x_min=x,
        y_min=y,
        x_max=x + 80,
        y_max=y + 20,
    )


def test_stitches_multicolumn_cbc_rows():
    """RapidOCR often emits Name / Value / Range / Unit on separate lines."""
    lines = [
        _line("HAEMATOLOGY", 40),
        _line("HAEMOGLOBIN", 100, 10),
        _line("10.000", 100, 200),
        _line("g%", 115, 500),  # unit often slightly below on real scans
        _line("TOTAL LEUCOCYTE COUNT", 140, 10),
        _line("16700", 140, 200),
        _line("4000 - 11000", 140, 280),
        _line("cells/cmm", 155, 500),
        _line("NEUTROPHILS", 180, 10),
        _line("79.3", 180, 200),
        _line("50 - 70 %", 180, 280),
        _line("LYMPHOCYTES", 220, 10),
        _line("11.6", 220, 200),
        _line("20 - 40%", 220, 280),
        _line("PLATELET COUNT", 260, 10),
        _line("4.78", 260, 200),
        _line("1.50 - 4", 260, 280),
        _line("Lakhs/Cumm", 275, 500),
    ]

    report = extract_complete_report("demo.png", lines)
    names = {row["test_name"].upper(): row for row in report["rows"]}

    assert "HAEMOGLOBIN" in names
    assert names["HAEMOGLOBIN"]["value"] in (10, "10", 10.0)
    assert names["HAEMOGLOBIN"]["unit"] == "g%"

    assert "TOTAL LEUCOCYTE COUNT" in names
    assert str(names["TOTAL LEUCOCYTE COUNT"]["value"]) in {"16700", "16700.0"}
    assert names["TOTAL LEUCOCYTE COUNT"]["unit"] == "cells/cmm"
    assert names["TOTAL LEUCOCYTE COUNT"]["interpretation"] == "high"
    assert names["TOTAL LEUCOCYTE COUNT"]["reference_range"] == "4000 - 11000"

    assert "NEUTROPHILS" in names
    assert names["NEUTROPHILS"]["unit"] == "%"
    assert names["NEUTROPHILS"]["interpretation"] == "high"
    assert names["NEUTROPHILS"]["reference_range"]

    assert "LYMPHOCYTES" in names
    assert names["LYMPHOCYTES"]["interpretation"] == "low"

    assert "PLATELET COUNT" in names
    assert names["PLATELET COUNT"]["unit"] == "Lakhs/Cumm"
    assert names["PLATELET COUNT"]["interpretation"] == "high"

    assert report["summary"]["total"] >= 5


def test_lft_flagged_values_and_ranges():
    """LFT rows often have value+H/L flags and garbled OCR units in separate columns."""
    lines = [
        _line("BILIRUBIN TOTAL", 100, 110),
        _line("9.42H", 100, 740),
        _line("mgid!", 100, 970),
        _line("0.30 - 1.20", 100, 1269),
        _line("SGOT", 140, 110),
        _line("162 h", 140, 740),
        _line("IUIL", 140, 970),
        _line("0.00 - 46.00", 140, 1269),
        _line("ALBUMIN", 180, 110),
        _line("3.7 L", 180, 740),
        _line("gm/d", 180, 970),
        _line("3.80 - 5.40", 180, 1269),
        _line("TOTAL PROTEIN", 220, 110),
        _line("6.2", 220, 740),
        _line("gm/al", 220, 970),
        _line("6.20 - 8.00", 220, 1269),
        _line("GAMMAT-GT", 260, 110),
        _line("263 H", 260, 740),
        _line("0.00 - 49 00", 260, 1269),  # OCR space instead of decimal
    ]
    report = extract_complete_report("lft.png", lines)
    by_name = {row["test_name"].upper(): row for row in report["rows"]}

    bili = by_name["BILIRUBIN TOTAL"]
    assert float(bili["value"]) == 9.42
    assert bili["unit"] == "mg/dl"
    assert bili["reference_range"] == "0.30 - 1.20"
    assert bili["interpretation"] == "high"

    sgot = by_name["SGOT"]
    assert float(sgot["value"]) == 162.0
    assert sgot["unit"] == "IU/L"
    assert sgot["reference_range"] == "0.00 - 46.00"
    assert sgot["interpretation"] == "high"

    alb = by_name["ALBUMIN"]
    assert float(alb["value"]) == 3.7
    assert alb["unit"] == "g/dl"
    assert alb["interpretation"] == "low"
    assert alb["reference_range"] == "3.80 - 5.40"

    protein = by_name["TOTAL PROTEIN"]
    assert float(protein["value"]) == 6.2
    assert protein["unit"] == "g/dl"
    assert protein["interpretation"] == "normal"

    ggt = by_name["GAMMAT-GT"]
    assert float(ggt["value"]) == 263.0
    assert ggt["reference_range"] == "0.00 - 49.00"
    assert ggt["interpretation"] == "high"

def test_dual_range_and_qualitative():
    lines = [
        _line("PUS CELLS-URINE 2-4 /HPF 0-5", 100),
        _line("Colour", 140, 10),
        _line("Pale Yellow", 140, 200),
        _line("Ketones", 180, 10),
        _line("Negative", 180, 200),
        _line("Urine pH", 220, 10),
        _line("6.0", 220, 200),
        _line("4.5 - 8.0", 220, 280),
    ]
    report = extract_complete_report("urine.png", lines)
    by_name = {row["test_name"].upper(): row for row in report["rows"]}

    pus = next(row for row in report["rows"] if "PUS" in row["test_name"].upper())
    assert pus["interpretation"] == "normal"
    assert pus["value"] == "2-4"

    assert "COLOUR" in by_name or any("COLOUR" in n or "COLOR" in n for n in by_name)
    assert any(row["value"] == "Negative" or str(row["value"]).lower() == "negative" for row in report["rows"])

    ph = next(row for row in report["rows"] if "PH" in row["test_name"].upper())
    assert ph["interpretation"] == "normal"
    assert ph["reference_range"] == "4.5 - 8.0"


def test_never_drops_ocr_ground_truth():
    lines = [_line("Patient ID", 20), _line("HAEMOGLOBIN", 100, 10), _line("13.5", 100, 200), _line("g/dL", 100, 320)]
    report = extract_complete_report("x.png", lines)
    assert report["ocr_text"]["line_count"] == 4
    assert len(report["line_classes"]) == 4
    assert report["summary"]["total"] >= 1


def test_rejects_patient_address_ids_methods_and_section_labels():
    lines = [
        _line("Mr: SHV KUMAR GARG", 20, 10),
        _line("SAMRAT PALACE, MEERUT 250003", 20, 220),
        _line("127234", 20, 600),
        _line("KANNADA", 50, 10),
        _line("575004", 50, 220),
        _line("PHYSICAL", 80, 10),
        _line("20", 80, 220),
        _line("ml", 80, 320),
        _line("CHEMICAL EXAMINATION", 110, 10),
        _line("NIL", 110, 220),
        _line("HEXOKINASE", 140, 10),
        _line("120.5", 140, 220),
        _line("mg/dl", 140, 320),
        _line("80 - 140", 140, 440),
        _line("REMARKS", 170, 10),
        _line("NON-REACTIVE", 170, 220),
        # Genuine result remains.
        _line("SERUM IRON", 210, 10),
        _line("65.0", 210, 220),
        _line("ug/dL", 210, 320),
        _line("60 - 160", 210, 440),
    ]

    report = extract_complete_report("metadata.png", lines)
    names = {row["test_name"].upper() for row in report["rows"]}

    assert names == {"SERUM IRON"}
    assert report["rows"][0]["value"] == "65"
    assert report["rows"][0]["unit"] == "ug/dL"
    assert report["ocr_text"]["line_count"] == len(lines)


def test_keeps_real_qualitative_urinalysis_without_range():
    lines = [
        _line("TRANSPARENCY", 100, 10),
        _line("CLEAR", 100, 220),
        _line("ALBUMIN", 140, 10),
        _line("NIL", 140, 220),
        _line("BACTERIA", 180, 10),
        _line("NIL", 180, 220),
    ]

    report = extract_complete_report("urine.png", lines)
    assert {row["test_name"].upper() for row in report["rows"]} == {
        "TRANSPARENCY",
        "ALBUMIN",
        "BACTERIA",
    }


def test_uses_analyte_name_instead_of_assay_method():
    lines = [
        _line("BLOOD SUGAR RANDOM", 100, 10),
        _line("HEXOKINASE", 130, 10),
        _line("120.5", 125, 400),
        _line("mg/dl", 130, 600),
        _line("80 - 140", 135, 800),
        _line("CRP (QUANTITATIVE)", 190, 10),
        _line("Immunoturbidimetry", 220, 10),
        _line("44.8", 215, 400),
        _line("mg/L", 220, 600),
        _line("0 - 8", 225, 800),
    ]

    report = extract_complete_report("methods.png", lines)
    names = {row["test_name"].upper() for row in report["rows"]}

    assert "BLOOD SUGAR RANDOM" in names
    assert "CRP (QUANTITATIVE)" in names
    assert "HEXOKINASE" not in names
    assert "IMMUNOTURBIDIMETRY" not in names


def test_extracts_complete_row_from_single_ocr_box():
    lines = [
        _line("GLUCOSE 125 mg/dl 70 - 140", 100, 10),
        _line("KETONES Negative", 140, 10),
    ]

    report = extract_complete_report("inline.png", lines)
    by_name = {row["test_name"].upper(): row for row in report["rows"]}

    assert by_name["GLUCOSE"]["value"] == "125"
    assert by_name["GLUCOSE"]["unit"] == "mg/dl"
    assert by_name["GLUCOSE"]["reference_range"] == "70 - 140"
    assert by_name["GLUCOSE"]["interpretation"] == "normal"
    assert by_name["KETONES"]["value"].lower() == "negative"


def test_recovers_split_and_unicode_normal_ranges():
    lines = [
        _line("SERUM IRON", 100, 10),
        _line("65", 100, 220),
        _line("ug/dL", 100, 320),
        _line("60", 100, 440),
        _line("–", 100, 500),
        _line("160", 100, 530),
        _line("CALCIUM", 150, 10),
        _line("9.4", 150, 220),
        _line("mg/dl", 150, 320),
        _line("(8.5 to 10.5)", 150, 440),
    ]

    report = extract_complete_report("split-ranges.png", lines)
    by_name = {row["test_name"].upper(): row for row in report["rows"]}

    assert by_name["SERUM IRON"]["reference_range"] == "60 - 160"
    assert by_name["SERUM IRON"]["interpretation"] == "normal"
    assert by_name["CALCIUM"]["reference_range"] == "8.5 - 10.5"
    assert by_name["CALCIUM"]["interpretation"] == "normal"


def test_keeps_named_range_when_observed_value_is_missing():
    report = extract_complete_report(
        "missing-value.png",
        [_line("TOTAL CHOLESTEROL 125 - 200", 100, 10)],
    )

    assert len(report["rows"]) == 1
    row = report["rows"][0]
    assert row["test_name"] == "TOTAL CHOLESTEROL"
    assert row["value"] is None
    assert row["reference_range"] == "125 - 200"
    assert row["parse_status"] == "needs_review"


def test_nearest_row_gets_its_observed_value_and_normal_range():
    lines = [
        _line("GLUCOSE", 100, 10),
        _line("125", 125, 220),
        _line("70 - 140", 125, 440),
        _line("CREATININE", 170, 10),
        _line("1.1", 150, 220),
        _line("0.6 - 1.3", 150, 440),
    ]

    report = extract_complete_report("alignment.png", lines)
    by_name = {row["test_name"].upper(): row for row in report["rows"]}

    assert by_name["GLUCOSE"]["value"] == "125"
    assert by_name["GLUCOSE"]["reference_range"] == "70 - 140"
    assert by_name["CREATININE"]["value"] == "1.1"
    assert by_name["CREATININE"]["reference_range"] == "0.6 - 1.3"


def test_attaches_one_sided_normal_range():
    lines = [
        _line("TOTAL CHOLESTEROL", 100, 10),
        _line("185", 100, 220),
        _line("mg/dl", 100, 320),
        _line("Up to 200", 100, 440),
    ]

    report = extract_complete_report("one-sided.png", lines)
    row = report["rows"][0]

    assert row["reference_range"] == "<= 200"
    assert row["reference_low"] is None
    assert row["reference_high"] == 200
    assert row["interpretation"] == "normal"


def test_recovers_nucleated_rbc_and_sample_volume():
    lines = [
        _line("NucleatedRBC", 100, 10),
        _line("0.0", 100, 220),
        _line("NRBC'S/100", 100, 320),
        _line("Sample Volume", 150, 10),
        _line("20", 150, 220),
        _line("ml", 150, 320),
    ]

    report = extract_complete_report("nrbc.png", lines)
    by_name = {row["test_name"].upper(): row for row in report["rows"]}

    assert any("NUCLEATED" in name and "RBC" in name for name in by_name)
    nrbc = next(row for row in report["rows"] if "NUCLEATED" in row["test_name"].upper())
    assert nrbc["value"] == "0"
    assert nrbc["unit"] == "NRBC'S/100"
    assert by_name["SAMPLE VOLUME"]["value"] == "20"
    assert by_name["SAMPLE VOLUME"]["unit"] == "ml"


def test_recovers_urine_transparency_and_dengue_ns1():
    lines = [
        _line("TRANSPARENCY", 100, 10),
        _line("SLIGHTLYTURBID", 100, 220),
        _line("NS-1ANTIGENDENGUE", 180, 10),
        _line("NON-REACTIVE", 210, 220),
    ]

    report = extract_complete_report("qual.png", lines)
    values = {row["test_name"].upper(): str(row["value"]).lower() for row in report["rows"]}

    assert any("TRANSPARENCY" in name for name in values)
    assert any("slightly" in value and "turbid" in value.replace(" ", "") for value in values.values())
    assert any("NS" in name or "DENGUE" in name for name in values)
    assert any(value.replace(" ", "").replace("-", "") == "nonreactive" for value in values.values())


def test_repairs_ocr_corrupt_range_and_reclaims_orphan_ferritin_range():
    lines = [
        _line("MCH", 100, 10),
        _line("31.2", 100, 220),
        _line("pg", 100, 320),
        _line("27-3Z", 100, 440),
        _line("FERRITIN", 160, 10),
        _line("168.3", 160, 220),
        _line("ng/ml", 160, 320),
        # Rejected neighbor band used to block orphan reclaim of this range.
        _line("XQZ", 168, 10),
        _line("30 - 350", 168, 440),
    ]

    report = extract_complete_report("ranges.png", lines)
    by_name = {row["test_name"].upper(): row for row in report["rows"]}

    assert by_name["MCH"]["reference_range"] == "27 - 32"
    assert by_name["FERRITIN"]["reference_range"] == "30 - 350"
    assert by_name["FERRITIN"]["interpretation"] == "normal"


def test_pus_cells_prefers_numeric_reference_over_nil():
    lines = [
        _line("PUSCELLS", 100, 10),
        _line("5-6", 100, 200),
        _line("/HPF", 100, 280),
        _line("1-2", 100, 360),
        _line("NIL", 100, 500),
    ]

    report = extract_complete_report("pus.png", lines)
    row = next(r for r in report["rows"] if "PUS" in r["test_name"].upper())

    assert row["value"] == "5-6"
    assert row["reference_range"] == "1 - 2"
    assert row["reference_range"].upper() != "NIL"


def test_keeps_thousands_comma_without_inventing_decimal():
    lines = [
        _line("TOTAL LEUCOCYTE COUNT", 100, 10),
        _line("16,700", 100, 220),
        _line("cells/cmm", 100, 320),
        _line("4000 - 11000", 100, 440),
    ]

    report = extract_complete_report("thousands.png", lines)
    row = report["rows"][0]

    assert str(row["value"]).replace(",", "") == "16700"
    assert row["value"] != "16.7"
    assert row["interpretation"] == "high"


def test_salvages_trailing_ocr_junk_and_alternatives():
    dirty = _line("125*", 100, 220)
    dirty.alternatives = []
    alt = _line("12S", 140, 220)
    alt.alternatives = ["125"]
    alt.recovery_status = "ambiguous"

    report = extract_complete_report(
        "salvage.png",
        [
            _line("GLUCOSE", 100, 10),
            dirty,
            _line("mg/dl", 100, 320),
            _line("70 - 140", 100, 440),
            _line("UREA", 140, 10),
            alt,
            _line("mg/dl", 140, 320),
            _line("10 - 50", 140, 440),
        ],
    )
    by_name = {row["test_name"].upper(): row for row in report["rows"]}

    assert by_name["GLUCOSE"]["value"] == "125"
    assert by_name["UREA"]["value"] == "125"
    assert by_name["UREA"]["parse_status"] == "needs_review"


def test_glued_unit_on_range_and_comparator_reference():
    lines = [
        _line("CREATININE", 100, 10),
        _line("1.1", 100, 220),
        _line("0.7 - 1.3 mg/dl", 100, 440),
        _line("CRP", 150, 10),
        _line("44.8", 150, 220),
        _line("mg/L", 150, 320),
        _line("< 8", 150, 440),
    ]

    report = extract_complete_report("glued.png", lines)
    by_name = {row["test_name"].upper(): row for row in report["rows"]}

    assert by_name["CREATININE"]["reference_range"] == "0.7 - 1.3"
    assert by_name["CREATININE"]["unit"] == "mg/dl"
    assert by_name["CRP"]["reference_range"] == "< 8"
    assert by_name["CRP"]["reference_high"] == 8


def test_name_plus_normal_range_is_not_fake_observed_value():
    report = extract_complete_report(
        "hb-range-only.png",
        [_line("HAEMOGLOBIN", 100, 10), _line("12.0 - 16.0", 100, 440)],
    )

    assert len(report["rows"]) == 1
    row = report["rows"][0]
    assert row["value"] is None
    assert row["reference_range"] == "12.0 - 16.0"
    assert row["parse_status"] == "needs_review"


def test_rescues_row_when_value_and_range_are_detectable():
    """A far-split row must still reach the report, flagged for review."""
    lines = [
        _line("SERUM MAGNESIUM", 100, 10),
        # Value/unit/range drift far below the label, beyond normal stitching.
        _line("2.1", 260, 220),
        _line("mg/dl", 260, 320),
        _line("1.7 - 2.4", 260, 440),
    ]

    report = extract_complete_report("rescue.png", lines)
    row = next(r for r in report["rows"] if "MAGNESIUM" in r["test_name"].upper())

    assert row["value"] == "2.1"
    assert row["reference_range"] == "1.7 - 2.4"
    assert row["interpretation"] == "normal"
    assert row["parse_status"] == "needs_review"


def test_rescue_does_not_invent_rows_from_metadata():
    lines = [
        _line("Mr: SHIV KUMAR", 20, 10),
        _line("250003", 20, 220),
        _line("12 - 16", 20, 440),
    ]

    report = extract_complete_report("rescue-metadata.png", lines)

    assert report["rows"] == []


def test_unit_before_value_and_wrapped_analyte_name():
    lines = [
        _line("MEAN CORPUSCULAR", 100, 10),
        _line("HEMOGLOBIN", 118, 10),
        _line("g%", 125, 300),
        _line("13.5", 125, 220),
        _line("12 - 16", 125, 440),
        _line("ZINC", 180, 10),
        _line("80", 180, 220),
        _line("ug/dL", 180, 320),
    ]

    report = extract_complete_report("wrap.png", lines)
    names = {row["test_name"].upper(): row for row in report["rows"]}

    assert any("MEAN CORPUSCULAR" in name and "HEMOGLOBIN" in name for name in names)
    mch = next(row for row in report["rows"] if "MEAN CORPUSCULAR" in row["test_name"].upper())
    assert mch["unit"] == "g%"
    assert mch["value"] == "13.5"
    assert names["ZINC"]["value"] == "80"
