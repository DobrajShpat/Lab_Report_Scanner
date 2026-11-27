from __future__ import annotations

import difflib
import re
from typing import Any

from pipeline.models import NormalizedObservation, PatientMetadata, RawObservation, ValidationFlag
from core.utils import normalize_text
from data.catalog import LoincCatalog


OBSERVED_RANGE_PATTERN = re.compile(
    r"^(?P<low>\d+(?:[.,]\d+)?)\s*[-\u2013]\s*(?P<high>\d+(?:[.,]\d+)?)$"
)


class ObservationMapper:
    def __init__(self, catalog: LoincCatalog) -> None:
        self.catalog = catalog
        self._items = self.catalog.items()
        self._alias_index: dict[str, list[dict[str, Any]]] = {}
        for item in self._items:
            for alias in item["aliases"]:
                normalized_alias = normalize_text(alias)
                self._alias_index.setdefault(normalized_alias, []).append(item)

    def normalize(self, raw: RawObservation, patient: PatientMetadata | None = None) -> NormalizedObservation:
        normalized_name = normalize_text(raw.raw_test_name)
        matched_test, match_strategy = self._match_test(normalized_name, raw.section)

        observation = NormalizedObservation(
            raw_test_name=raw.raw_test_name,
            original_unit=raw.raw_unit,
            reference_range_text=raw.raw_reference_range,
            section=raw.section,
            provenance={
                "raw_value": raw.raw_value,
                "raw_unit": raw.raw_unit,
                "raw_reference_range": raw.raw_reference_range,
                "line_text": raw.line_text,
            },
        )
        observation.value = self._parse_float(raw.raw_value)
        observed_range = self._parse_observed_range(raw.raw_value)
        if observed_range:
            observation.value_text = raw.raw_value.replace(" ", "")
            observation.value = observed_range["low"]
            observation.provenance["observed_range"] = observed_range

        if matched_test is None:
            observation.validation_flags.append(
                ValidationFlag(
                    code="UNMAPPED_TEST",
                    severity="warning",
                    message=f"Could not map test name '{raw.raw_test_name}' to catalog.",
                )
            )
            return observation

        observation.canonical_name = matched_test["canonical_name"]
        observation.loinc_code = matched_test["loinc_code"]
        observation.loinc_display = matched_test["loinc_display"]
        observation.category = matched_test.get("category")
        observation.standardized_unit = matched_test.get("canonical_unit")
        observation.match_strategy = match_strategy

        converted_value, converted_unit = self._convert_unit(observation.value, raw.raw_unit, matched_test)
        observation.standardized_value = converted_value
        if converted_unit:
            observation.standardized_unit = converted_unit

        reference_details = self._parse_reference_range(raw.raw_reference_range, patient, matched_test)
        ref_low = reference_details["low"]
        ref_high = reference_details["high"]
        comparator = reference_details["comparator"]

        if ref_low is not None:
            ref_low, _ = self._convert_unit(ref_low, raw.raw_unit, matched_test)
        if ref_high is not None:
            ref_high, _ = self._convert_unit(ref_high, raw.raw_unit, matched_test)

        observation.reference_low = ref_low
        observation.reference_high = ref_high
        observation.provenance["reference_selection"] = reference_details["selection"]
        if comparator:
            observation.provenance["reference_comparator"] = comparator

        observation.interpretation = self._interpret(
            observation.standardized_value,
            ref_low,
            ref_high,
            comparator,
            observed_range=observed_range,
        )
        observation.validation_flags.extend(self._validate(observation, matched_test, reference_details))
        return observation

    def _match_test(self, normalized_name: str, section: str | None) -> tuple[dict[str, Any] | None, str | None]:
        exact_matches: list[dict[str, Any]] = []
        substring_matches: list[tuple[int, dict[str, Any]]] = []
        candidates = self._generate_name_candidates(normalized_name)

        for candidate in candidates:
            exact_matches.clear()
            for item in self._alias_index.get(candidate, []):
                exact_matches.append(item)
            if exact_matches:
                return self._prefer_section_match(exact_matches, section), "alias"

        for candidate in candidates:
            for alias, items in self._alias_index.items():
                if len(alias) < 3:
                    continue
                if alias in candidate or candidate in alias:
                    for item in items:
                        substring_matches.append((len(alias), item))
            if substring_matches:
                best_length = max(length for length, _ in substring_matches)
                best_matches = [item for length, item in substring_matches if length == best_length]
                return self._prefer_section_match(best_matches, section), "substring"

        close: list[str] = []
        for candidate in candidates:
            close = difflib.get_close_matches(candidate, list(self._alias_index.keys()), n=1, cutoff=0.8)
            if close:
                return self._alias_index[close[0]][0], "fuzzy"
        return None, None

    def _generate_name_candidates(self, normalized_name: str) -> list[str]:
        candidates: list[str] = []

        def add(value: str) -> None:
            value = normalize_text(value)
            if value and value not in candidates:
                candidates.append(value)

        add(normalized_name)

        working = normalized_name
        replacements = {
            "proteln": "protein",
            "potassum": "potassium",
            "dired": "direct",
            "wethod": "method",
            "mcihod": "method",
            "metiod": "method",
            "merliod": "method",
            "aspurtate": "aspartate",
            "erritin": "ferritin",
            "haemotocrit": "hematocrit",
        }
        for source, target in replacements.items():
            working = working.replace(source, target)
        add(working)

        if "monocyte" in working and ("x1000/cumm" in working or "x1000/cmm" in working):
            add("absolute monocyte count")
        if "basophil" in working and ("x1000/cumm" in working or "x1000/cmm" in working):
            add("absolute basophil count")
        if "plateletcrit" in working or working.startswith("pct"):
            add("plateletcrit")
        if "plcr" in working:
            add("platelet large cell ratio")

        cleaned = re.sub(r"\b(?:serum|plasma|blood)\s*/?\s*\d+[a-z]*\b", " ", working)
        cleaned = re.sub(r"\b(?:method|investigation)\b\s*:?\s*", " ", cleaned)
        cleaned = re.sub(
            r"\b(?:direct|dired|ise|potentiometric|calculated|photometric|turbidimetry|turhidimetry|diazotized|ifcc|god/pod|elfa|ferrozine|multipoine|rate|with|psp|p s p)\b",
            " ",
            cleaned,
        )
        cleaned = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:x1000/cumm|x1000/cmm|lacs/cumm|lakhs/cumm|mmol/l|mg/dl|mg/l|u/l|iu/l|g/dl|gms%|gm/al|gm/d)\b.*", " ", cleaned)
        cleaned = re.sub(r"\b[#><]+\b", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        add(cleaned)

        if "glucose" in cleaned and ("random" in cleaned or "rbs" in cleaned):
            add("random glucose")
        if ("bloodsugar" in cleaned or "blood sugar" in cleaned) and ("random" in cleaned or "rand" in cleaned):
            add("random glucose")
        if "c reactive" in cleaned:
            add("c reactive protein")
            add("crp")
        if "bilirubin" in cleaned and "direct" not in cleaned and "indirect" not in cleaned:
            if "conjugated" in cleaned or "atrectbilirubi" in cleaned:
                add("direct bilirubin")
        if "bilirubin" in cleaned and ("indirect" in cleaned or "unconjugated" in cleaned):
            add("indirect bilirubin")
        if "bilirubin" in cleaned and ("direct" in cleaned or "conjugated" in cleaned):
            add("direct bilirubin")
        if "saturation" in cleaned:
            add("transferrin saturation")
        if "albumin serum" in cleaned or "serum albumin" in cleaned:
            add("albumin")
        if "amylase" in cleaned:
            add("amylase")
        if "lipase" in cleaned:
            add("lipase")
        if "cholesterol" in cleaned and "hdl" not in cleaned and "ldl" not in cleaned and "vldl" not in cleaned:
            add("total cholesterol")
        if "triglyceride" in cleaned:
            add("triglycerides")
        if "ferritin" in cleaned:
            add("ferritin")

        return candidates

    @staticmethod
    def _prefer_section_match(matches: list[dict[str, Any]], section: str | None) -> dict[str, Any]:
        if not section or len(matches) == 1:
            return matches[0]
        normalized_section = normalize_text(section)
        for item in matches:
            category = normalize_text(str(item.get("category", "")))
            canonical_name = normalize_text(str(item.get("canonical_name", "")))
            if category and category in normalized_section:
                return item
            if "urine" in normalized_section and "urine" in canonical_name:
                return item
        return matches[0]

    def _convert_unit(
        self,
        value: float | None,
        unit: str | None,
        matched_test: dict[str, Any],
    ) -> tuple[float | None, str | None]:
        if value is None:
            return None, matched_test.get("canonical_unit")
        if not unit:
            return value, matched_test.get("canonical_unit")

        normalized_unit = normalize_text(unit)
        normalized_unit = self._normalize_unit_alias(normalized_unit)
        canonical_unit = self._normalize_unit_alias(normalize_text(matched_test.get("canonical_unit", "")))
        canonical_name = matched_test.get("canonical_name")

        if canonical_name == "White Blood Cells" and normalized_unit in {"cells/cmm", "", "10^9/l"} and value > 1000:
            return round(value / 1000, 4), matched_test.get("canonical_unit")
        if canonical_name == "White Blood Cells" and normalized_unit == "10^9/l":
            return value, matched_test.get("canonical_unit")
        if canonical_name == "Red Blood Cells" and normalized_unit in {"millions/cumm", "", "10^12/l"}:
            return value, matched_test.get("canonical_unit")
        if canonical_name == "Platelets" and normalized_unit == "lakhs/cumm":
            return round(value * 100, 4), matched_test.get("canonical_unit")
        if normalized_unit == canonical_unit:
            return value, matched_test.get("canonical_unit")

        conversions = matched_test.get("unit_conversions", {})
        if normalized_unit in conversions:
            rule = conversions[normalized_unit]
            converted = round((value * rule.get("factor", 1.0)) + rule.get("offset", 0.0), 4)
            return converted, rule.get("target_unit", matched_test.get("canonical_unit"))

        unit_aliases = matched_test.get("unit_aliases", {})
        if normalized_unit in unit_aliases:
            return value, unit_aliases[normalized_unit]

        return value, unit

    def _parse_reference_range(
        self,
        raw_range: str | None,
        patient: PatientMetadata | None,
        matched_test: dict[str, Any],
    ) -> dict[str, Any]:
        details = {"low": None, "high": None, "selection": "none", "comparator": None}
        if not raw_range:
            return details

        normalized = normalize_text(raw_range)

        sex_ranges = self._extract_labeled_ranges(normalized, ("male", "female"))
        patient_gender = normalize_text(patient.gender) if patient and patient.gender else ""
        if sex_ranges:
            if patient_gender.startswith("m") and "male" in sex_ranges:
                details.update({"low": sex_ranges["male"][0], "high": sex_ranges["male"][1], "selection": "male"})
                return details
            if patient_gender.startswith("f") and "female" in sex_ranges:
                details.update({"low": sex_ranges["female"][0], "high": sex_ranges["female"][1], "selection": "female"})
                return details
            details.update({"low": sex_ranges[next(iter(sex_ranges))][0], "high": sex_ranges[next(iter(sex_ranges))][1], "selection": "sex-unspecified"})
            return details

        age_ranges = self._extract_labeled_ranges(normalized, ("adult", "child", "children", "pediatric"))
        if age_ranges:
            preferred_key = "adult" if "adult" in age_ranges else next(iter(age_ranges))
            details.update({"low": age_ranges[preferred_key][0], "high": age_ranges[preferred_key][1], "selection": preferred_key})
            return details

        comparator_match = re.search(r"([<>]=?)\s*(-?\d+(?:[.,]\d+)?)", raw_range)
        if comparator_match:
            comparator = comparator_match.group(1)
            value = self._parse_float(comparator_match.group(2))
            if comparator.startswith("<"):
                details.update({"low": None, "high": value, "selection": "comparator", "comparator": comparator})
            else:
                details.update({"low": value, "high": None, "selection": "comparator", "comparator": comparator})
            return details

        match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*[-â€“]\s*(-?\d+(?:[.,]\d+)?)", raw_range)
        if not match:
            return details
        details.update(
            {
                "low": self._parse_float(match.group(1)),
                "high": self._parse_float(match.group(2)),
                "selection": matched_test.get("canonical_unit", "generic"),
            }
        )
        return details

    @staticmethod
    def _extract_labeled_ranges(normalized: str, labels: tuple[str, ...]) -> dict[str, tuple[float, float]]:
        extracted: dict[str, tuple[float, float]] = {}
        for label in labels:
            pattern = rf"{label}\s*[:\-]?\s*(-?\d+(?:[.,]\d+)?)\s*[-â€“]\s*(-?\d+(?:[.,]\d+)?)"
            match = re.search(pattern, normalized)
            if match:
                low = ObservationMapper._parse_float(match.group(1))
                high = ObservationMapper._parse_float(match.group(2))
                if low is not None and high is not None:
                    extracted[label] = (low, high)
        return extracted

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _parse_observed_range(raw_value: str | None) -> dict[str, float] | None:
        if not raw_value:
            return None
        match = OBSERVED_RANGE_PATTERN.match(raw_value.strip().replace(" ", ""))
        if not match:
            match = OBSERVED_RANGE_PATTERN.match(raw_value.strip())
        if not match:
            return None
        low = ObservationMapper._parse_float(match.group("low"))
        high = ObservationMapper._parse_float(match.group("high"))
        if low is None or high is None:
            return None
        return {"low": low, "high": high}

    @staticmethod
    def _interpret(
        value: float | None,
        low: float | None,
        high: float | None,
        comparator: str | None,
        observed_range: dict[str, float] | None = None,
    ) -> str | None:
        if observed_range and low is not None and high is not None:
            obs_low = observed_range["low"]
            obs_high = observed_range["high"]
            if obs_low >= low and obs_high <= high:
                return "normal"
            if obs_high > high:
                return "high"
            if obs_low < low:
                return "low"
            return "normal"

        if value is None or (low is None and high is None):
            return None
        if comparator and comparator.startswith("<") and high is not None:
            return "high" if value > high else "normal"
        if comparator and comparator.startswith(">") and low is not None:
            return "low" if value < low else "normal"
        if low is not None and value < low:
            return "low"
        if high is not None and value > high:
            return "high"
        return "normal"

    def _validate(
        self,
        observation: NormalizedObservation,
        matched_test: dict[str, Any],
        reference_details: dict[str, Any],
    ) -> list[ValidationFlag]:
        flags: list[ValidationFlag] = []
        plausible_low = matched_test.get("plausible_low")
        plausible_high = matched_test.get("plausible_high")
        value = observation.standardized_value
        if value is not None and plausible_low is not None and value < plausible_low:
            flags.append(
                ValidationFlag(
                    code="PHYSIOLOGICALLY_IMPLAUSIBLE_LOW",
                    severity="warning",
                    message=f"Value {value} is below plausible minimum {plausible_low}.",
                )
            )
        if value is not None and plausible_high is not None and value > plausible_high:
            flags.append(
                ValidationFlag(
                    code="PHYSIOLOGICALLY_IMPLAUSIBLE_HIGH",
                    severity="warning",
                    message=f"Value {value} is above plausible maximum {plausible_high}.",
                )
            )
        if observation.original_unit and observation.standardized_unit:
            original_norm = self._normalize_unit_alias(normalize_text(observation.original_unit))
            standard_norm = self._normalize_unit_alias(normalize_text(observation.standardized_unit))
            if original_norm != standard_norm:
                flags.append(
                    ValidationFlag(
                        code="UNIT_STANDARDIZED",
                        severity="info",
                        message=f"Unit standardized from {observation.original_unit} to {observation.standardized_unit}.",
                    )
                )
        if reference_details["selection"] == "sex-unspecified":
            flags.append(
                ValidationFlag(
                    code="REFERENCE_RANGE_GENDER_AMBIGUOUS",
                    severity="info",
                    message="Sex-specific range detected but patient gender was unavailable, so the first range was used.",
                )
            )
        if reference_details["selection"] in {"adult", "child", "children", "pediatric"}:
            flags.append(
                ValidationFlag(
                    code="REFERENCE_RANGE_AGE_SELECTED",
                    severity="info",
                    message=f"Age-labeled reference range selected: {reference_details['selection']}.",
                )
            )
        return flags

    @staticmethod
    def _normalize_unit_alias(unit: str) -> str:
        aliases = {
            "g%": "g/dl",
            "gms%": "g/dl",
            "gms/dl": "g/dl",
            "gm/dl": "g/dl",
            "g dl": "g/dl",
            "mg dl": "mg/dl",
            "mg l": "mg/l",
            "mmol l": "mmol/l",
            "umol l": "umol/l",
            "miu/ml": "miu/ml",
            "muiu/ml": "miu/ml",
            "10 3/ul": "10^3/ul",
            "10 6/ul": "10^6/ul",
            "10^9/l": "10^3/ul",
            "10^12/l": "10^6/ul",
            "x10^3/ul": "10^3/ul",
            "x10^6/ul": "10^6/ul",
            "x1000/cumm": "10^3/ul",
            "x1000/cmm": "10^3/ul",
            "/cu.mm": "10^3/ul",
            "/cumm": "10^3/ul",
            "/cmm": "10^3/ul",
            "lacs/cumm": "lakhs/cumm",
            "lacs/cmm": "lakhs/cumm",
        }
        return aliases.get(unit, unit)
