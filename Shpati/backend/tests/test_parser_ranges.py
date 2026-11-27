import re

from pipeline.s5_parser import RANGE_PATTERN, ReportParser


def test_dual_range_observed_and_reference():
    parser = ReportParser()
    obs = parser._parse_observation_row("PUS CELLS-URINE 2-4 /HPF 0-5", None)
    assert obs is not None
    assert obs.raw_test_name == "PUS CELLS-URINE"
    assert obs.raw_value == "2-4"
    assert obs.raw_reference_range == "0-5"
    assert obs.raw_unit and "hpf" in obs.raw_unit.lower()


def test_dual_range_with_spaced_reference():
    parser = ReportParser()
    obs = parser._parse_observation_row("EpithelialCells-Urine 1-2 /HPF 0 - 5", None)
    assert obs is not None
    assert obs.raw_value == "1-2"
    assert obs.raw_reference_range == "0 - 5"


def test_scalar_value_with_reference_range():
    parser = ReportParser()
    obs = parser._parse_observation_row("Hemoglobin 13.5 g/dL 12.0 - 16.0", None)
    assert obs is not None
    assert obs.raw_value == "13.5"
    assert obs.raw_reference_range == "12.0 - 16.0"


def test_false_negative_fragment_skipped():
    parser = ReportParser()
    line = "PUS CELLS-URINE 2-4 /HPF 0-5"
    matches = list(re.finditer(r"-?\d+(?:[.,]\d+)?", line))
    negative_match = next(m for m in matches if m.group(0) == "-4")
    assert parser._is_false_negative_fragment(line, negative_match) is True


def test_range_pattern_matches_spaced_hyphen():
    match = RANGE_PATTERN.search("normal 0 - 5 end")
    assert match is not None
    assert match.group("low") == "0"
    assert match.group("high") == "5"
