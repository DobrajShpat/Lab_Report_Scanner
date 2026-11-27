from pipeline.models import NormalizedObservation, PatientMetadata, ProcessingMetrics, ReportMetadata, StructuredReport
from pipeline.s11_clinical_report import build_clinical_report


def _obs(**kwargs) -> NormalizedObservation:
    return NormalizedObservation(**kwargs)


def test_clinical_report_filters_admin_noise():
    structured = StructuredReport(
        report=ReportMetadata(source_file="test.png"),
        patient=PatientMetadata(),
        observations=[
            _obs(
                raw_test_name="Hemoglobin",
                standardized_value=13.5,
                standardized_unit="g/dL",
                reference_low=12.0,
                reference_high=16.0,
                interpretation="Normal",
                acceptance_decision="accepted",
            ),
            _obs(
                raw_test_name="City Hospital Invoice No",
                standardized_value=12345,
                acceptance_decision="accepted",
            ),
            _obs(
                raw_test_name="Glucose",
                standardized_value=180,
                standardized_unit="mg/dL",
                reference_low=70,
                reference_high=100,
                interpretation="High",
                acceptance_decision="accepted",
            ),
        ],
        metrics=ProcessingMetrics(),
    )

    report = build_clinical_report(structured)
    names = [row["test_name"] for row in report["rows"]]
    assert "Hemoglobin" in names
    assert "Glucose" in names
    assert not any("invoice" in n.lower() for n in names)
    assert report["summary"]["normal"] == 1
    assert report["summary"]["high"] == 1


def test_clinical_report_infers_low():
    structured = StructuredReport(
        report=ReportMetadata(source_file="test.png"),
        patient=PatientMetadata(),
        observations=[
            _obs(
                raw_test_name="Sodium",
                standardized_value=128,
                standardized_unit="mmol/L",
                reference_low=136,
                reference_high=145,
                acceptance_decision="accepted",
            ),
        ],
        metrics=ProcessingMetrics(),
    )
    report = build_clinical_report(structured)
    assert report["rows"][0]["interpretation"] == "low"
