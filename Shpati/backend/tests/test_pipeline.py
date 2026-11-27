from pathlib import Path

from core.config import settings
from pipeline.s9_validator import assign_tier, validate_all
from pipeline.models import NormalizedObservation, ValidationFlag


def test_settings_paths_exist():
    assert settings.storage_root.name == "storage"
    assert settings.uploaded_reports_dir.exists()
    assert settings.outputs_dir.exists()
    assert settings.catalog_path.exists()


def test_validation_tiers():
    accepted = NormalizedObservation(
        raw_test_name="Hemoglobin",
        loinc_code="718-7",
        standardized_value=13.5,
        standardized_unit="g/dL",
    )
    assert assign_tier(accepted).acceptance_decision == "accepted"

    review = NormalizedObservation(
        raw_test_name="Glucose",
        loinc_code="2345-7",
        standardized_value=None,
        validation_flags=[ValidationFlag(code="MISSING_UNIT", severity="warn", message="x")],
    )
    assert assign_tier(review).acceptance_decision == "needs_review"

    rejected = NormalizedObservation(raw_test_name="Unknown Marker")
    assert assign_tier(rejected).acceptance_decision == "rejected"


def test_validate_all_batch():
    rows = [
        NormalizedObservation(raw_test_name="A", loinc_code="1", standardized_value=1.0),
        NormalizedObservation(raw_test_name="B"),
    ]
    out = validate_all(rows)
    assert len(out) == 2
    assert out[0].acceptance_decision == "accepted"
    assert out[1].acceptance_decision == "rejected"
