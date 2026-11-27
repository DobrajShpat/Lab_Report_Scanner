from __future__ import annotations

import re

from pipeline.models import OCRLine, PatientMetadata, RawObservation, ReportMetadata
from core.utils import normalize_text
from pipeline.s4_layout import LayoutAnalysis, LayoutRow, analyze_layout

DATE_PATTERN = re.compile(
    r"(\d{1,2}(?:[/-][A-Za-z]{3}[/-]\d{2,4}|[/-]\d{1,2}[/-]\d{2,4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)?)"
)
VALUE_PATTERN = re.compile(r"(?P<value>-?\d+(?:[.,]\d+)?)")
RANGE_PATTERN = re.compile(r"(?P<low>-?\d+(?:[.,]\d+)?)\s*[-\u2013]\s*(?P<high>-?\d+(?:[.,]\d+)?)")
COMPARATOR_PATTERN = re.compile(r"(?P<comparator>[<>]=?)\s*(?P<value>-?\d+(?:[.,]\d+)?)")
UNIT_PATTERN_TEXT = (
    r"(mg/dl|mg/l|ug/dl|mcg/dl|ng/dl|mmol/l|umol/l|g/dl|g/l|gm/dl|gms/dl|gms%|g%|u/l|iu/l|10\^3/ul|10\^6/ul|10\^9/l|10\^12/l|x10\^3/ul|x10\^6/ul|x1000/cumm|x1000/cmm|%|fl|pg|pg/ml|ng/ml|miu/ml|m[u\u00b5]iu/ml|meq/l|cells/cmm|cells/cumm|lakhs/cumm|lakhs/cmm|lacs/cumm|lacs/cmm|millions/cumm|mill/cmm|mill/cumm|/cu\.mm|/cumm|/cmm|ml/min/1\.73m?2|seconds|ratio|mm/hr|/hpf|/lpf|presence|ph)"
)
UNIT_PATTERN = re.compile(UNIT_PATTERN_TEXT, re.IGNORECASE)
UNIT_ONLY_PATTERN = re.compile(
    r"^(%|g%|gms%|cells/cmm|cells/cumm|lakhs/cumm|lakhs/cmm|lacs/cumm|lacs/cmm|millions/cumm|mill/cmm|mill/cumm|x1000/cumm|x1000/cmm|/cu\.mm|/cumm|/cmm|10\^3/ul|10\^6/ul|10\^9/l|10\^12/l|ratio|mm/hr|/hpf|/lpf|presence|ph)$",
    re.IGNORECASE,
)
NON_RESULT_SECTIONS = {"header", "footer", "metadata", "signature"}

SECTION_KEYWORDS = {
    "cbc": "Complete Blood Count",
    "haematology": "Haematology",
    "hematology": "Haematology",
    "lipid": "Lipid Panel",
    "liver": "Liver Function",
    "thyroid": "Thyroid",
    "biochemistry": "Biochemistry",
    "chemistry": "Clinical Chemistry",
    "serology": "Serology",
    "renal": "Renal Function",
    "kidney": "Renal Function",
    "electrolyte": "Electrolytes",
    "urine": "Urinalysis",
    "coagulation": "Coagulation",
    "diabetes": "Diabetes",
}

PATIENT_FIELDS = {
    "patient": "patient_name",
    "name": "patient_name",
    "patient id": "patient_id",
    "patientid": "patient_id",
    "ipid": "patient_id",
    "id": "patient_id",
    "sex": "gender",
    "gender": "gender",
    "dob": "date_of_birth",
    "date of birth": "date_of_birth",
    "age": "date_of_birth",
}

NOISE_FRAGMENTS = [
    "invoice no",
    "result ready",
    "result verified",
    "printed time",
    "printed by",
    "authorized by",
    "end of report",
    "routine",
    "dept/unit",
    " bed ",
    " ip ",
    "sample type",
    "referred by",
    "indicates abnormal result",
    "insurance",
    "lab technician",
    "iso 9001",
    "computer generated",
    "not valid for medico legal purpose",
    "notvalidformedico-legalpurpose",
    "professional opinion",
    "clinical correlation",
    "scope of accreditation",
    "receiptid",
    "serial no",
    "report gen at",
    "report generated",
    "sample collected at",
    "samplel",
    "sample ",
    "invoice",
    "regn no",
    "sr no",
    "sri no",
    "expected value",
    "am j clin nutr",
    "ofvitamind",
    "laboratory report",
    "government",
    "hospital",
    "diagnostic center",
    "diagnosticcenter",
    "pathology labs",
    "pathologylabs",
    "requisition",
    "ward ",
    "note:",
    "remarks:",
    "method :",
    "referred by dr",
    "all tpa",
    "digital x ray",
    "ct-scan",
    "ambulance facility",
    "delhi jal board",
    "accreditation",
    "consensus of expert",
    "urgent need",
    "measurementof",
    "vitamin d status",
    "metabolized",
    "hydroxylation",
    "comments",
    "3d/4d",
    "spirit tocare",
    "date of collection",
    "reporting date",
    "mean normal prothrombin",
    "m~",
    "m2",
    "25-oh)is",
    "differential count",
    "rishabh mandir",
    "kavi nagar",
    "regn no. mci",
    "rmcno",
    "fullycomputerizedlaboratory",
    "equippedwithlatesttechnology",
    "sarvodaya hospital",
    "jhajjarroad",
    "cinno",
    "equipped with computerisedauto chemistry",
    "nosp",
    "website :",
    "www.",
    "host defence and tissue repair",
    "acute phase reactants",
    "innormalhealthyindividuals",
    "microscopicexamination",
]

LAB_NAME_HINTS = ("laboratory", "lab", "diagnostic", "pathology", "hospital")


class ReportParser:
    def parse(
        self, source_file: str, lines: list[OCRLine]
    ) -> tuple[ReportMetadata, PatientMetadata, list[str], list[RawObservation], dict[str, object]]:
        layout = analyze_layout(lines)
        report = ReportMetadata(source_file=source_file)
        patient = PatientMetadata()
        observations: list[RawObservation] = []
        current_section: str | None = None

        report.lab_name = self._extract_lab_name(layout)
        raw_text = [row.text for row in layout.rows]

        for row in layout.rows:
            line = self._sanitize_line(row.text)
            normalized = normalize_text(line)
            if not normalized:
                continue

            if self._maybe_capture_report_metadata(row, line, normalized, report, patient):
                continue

            if self._is_noise_row(row, normalized):
                continue

            for keyword, section_name in SECTION_KEYWORDS.items():
                if keyword in normalized and section_name not in report.panel_sections:
                    report.panel_sections.append(section_name)
                    current_section = section_name

            if row.region in NON_RESULT_SECTIONS:
                continue

            row_text = self._merge_columns_for_result(row)
            row_observation = self._parse_observation_row(row_text, current_section)
            if row_observation:
                observations.append(row_observation)

        diagnostics = {
            "total_ocr_lines": layout.total_lines,
            "retained_layout_lines": len(layout.rows),
            "filtered_low_confidence_lines": layout.filtered_low_confidence_lines,
            "filtered_region_lines": layout.filtered_region_lines,
            "multi_column_layout": layout.multi_column_layout,
            "region_counts": layout.region_counts,
            "candidate_rows": len(observations),
        }
        return report, patient, raw_text, observations, diagnostics

    def _extract_lab_name(self, layout: LayoutAnalysis) -> str | None:
        candidates: list[tuple[int, str]] = []
        for row in layout.rows:
            normalized = normalize_text(row.text)
            if any(hint in normalized for hint in LAB_NAME_HINTS):
                score = 0
                if row.region == "header":
                    score += 3
                if any(hint in normalized for hint in ("laboratory", "diagnostic", "pathology")):
                    score += 3
                score += min(len(row.text) // 12, 4)
                candidates.append((score, row.text))
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1][:120]

    def _maybe_capture_report_metadata(
        self,
        row: LayoutRow,
        line: str,
        normalized: str,
        report: ReportMetadata,
        patient: PatientMetadata,
    ) -> bool:
        lower = normalized.lower()
        if "date of collection" in lower or "reporting date" in lower:
            collected_match = re.search(
                r"date of collection\s*([0-9A-Za-z:/ -]+?)(?=\s+reporting date|$)",
                line,
                re.IGNORECASE,
            )
            reporting_match = re.search(r"reporting date\s*([0-9A-Za-z:/ -]+)", line, re.IGNORECASE)
            if collected_match:
                date_match = DATE_PATTERN.search(collected_match.group(1))
                if date_match:
                    patient.collected_at = date_match.group(1)
            if reporting_match:
                date_match = DATE_PATTERN.search(reporting_match.group(1))
                if date_match:
                    patient.reported_at = date_match.group(1)
            if collected_match or reporting_match:
                return True

        patient_id_match = re.search(
            r"(?:patient\s*id|patientid|ipid)\s*[:.]?\s*([A-Za-z-]*\d[A-Za-z0-9/-]*)",
            line,
            re.IGNORECASE,
        )
        if patient_id_match:
            candidate = patient_id_match.group(1).upper()
            if not (re.fullmatch(r"\d{1,2}", candidate) and re.search(r"\d{1,2}:\d{2}:\d{2}", line)):
                patient.patient_id = candidate
                return True

        if row.region == "metadata":
            for label, attr in PATIENT_FIELDS.items():
                if lower.startswith(label):
                    parts = re.split(r":", line, maxsplit=1)
                    if len(parts) == 2:
                        value = parts[1].strip()
                        if value:
                            if attr == "gender":
                                value = value.lower()
                            setattr(patient, attr, value)
                            return True

        if "report id" in lower or "accession" in lower or "receiptid" in lower:
            parts = re.split(r":", line, maxsplit=1)
            if len(parts) == 2:
                report.report_id = parts[1].strip()
                return True

        if "collected" in lower or "collection date" in lower:
            match = DATE_PATTERN.search(line)
            if match:
                patient.collected_at = match.group(1)
                return True

        if "reported" in lower or "validated" in lower or "printed" in lower:
            match = DATE_PATTERN.search(line)
            if match:
                patient.reported_at = match.group(1)
                return True

        return False

    def _merge_columns_for_result(self, row: LayoutRow) -> str:
        if len(row.columns) < 2:
            return row.text
        if row.region == "table":
            return " ".join(row.columns).strip()
        return row.text

    def _parse_observation_row(self, line: str, section: str | None) -> RawObservation | None:
        match_line = line
        ranges = list(RANGE_PATTERN.finditer(match_line))

        if len(ranges) >= 2:
            return self._parse_dual_range_row(match_line, ranges[0], ranges[-1], section)

        if len(ranges) == 1:
            return self._parse_single_range_row(match_line, ranges[0], section)

        return self._parse_scalar_row(match_line, section)

    def _parse_dual_range_row(
        self,
        line: str,
        observed_range: re.Match[str],
        reference_range: re.Match[str],
        section: str | None,
    ) -> RawObservation | None:
        test_name = line[: observed_range.start()].strip(" :-|")
        if len(test_name) < 2 or self._looks_like_metadata_prefix(test_name):
            return None

        value = observed_range.group(0).replace(" ", "")
        remainder = line[observed_range.end() : reference_range.start()]
        unit_match = UNIT_PATTERN.search(remainder)
        unit = unit_match.group(1) if unit_match else None
        reference_text = reference_range.group(0)

        cleaned_test = self._clean_test_name(test_name)
        if len(cleaned_test) < 2 or cleaned_test.isdigit():
            return None

        return RawObservation(
            raw_test_name=cleaned_test,
            raw_value=value,
            raw_unit=unit,
            raw_reference_range=reference_text,
            section=section,
            line_text=line,
        )

    def _parse_single_range_row(
        self,
        line: str,
        reference_range: re.Match[str],
        section: str | None,
    ) -> RawObservation | None:
        before_reference = line[: reference_range.start()]
        match = self._select_measurement_match(before_reference)
        if not match:
            return None

        value_span = match.span()
        test_name = before_reference[: value_span[0]].strip(" :-|")
        if len(test_name) < 2 or self._looks_like_metadata_prefix(test_name):
            return None

        value = match.group("value").replace(",", ".")
        remainder = before_reference[value_span[1] :].strip()
        unit_match = UNIT_PATTERN.search(remainder)
        unit = unit_match.group(1) if unit_match else None
        reference_text = reference_range.group(0)

        cleaned_test = self._clean_test_name(test_name)
        if len(cleaned_test) < 2 or cleaned_test.isdigit():
            return None
        if unit is None and not self._looks_like_test_name(cleaned_test):
            return None

        return RawObservation(
            raw_test_name=cleaned_test,
            raw_value=value,
            raw_unit=unit,
            raw_reference_range=reference_text,
            section=section,
            line_text=line,
        )

    def _parse_scalar_row(self, line: str, section: str | None) -> RawObservation | None:
        match = self._select_measurement_match(line)
        if not match:
            return None

        value_span = match.span()
        test_name = line[: value_span[0]].strip(" :-|")
        if len(test_name) < 2 or self._looks_like_metadata_prefix(test_name):
            return None

        value = match.group("value").replace(",", ".")
        remainder = line[value_span[1] :].strip()
        unit_match = UNIT_PATTERN.search(remainder)
        unit = unit_match.group(1) if unit_match else None
        range_match = RANGE_PATTERN.search(remainder)
        reference_text = range_match.group(0) if range_match else None
        comparator_match = COMPARATOR_PATTERN.search(remainder)
        if comparator_match and not reference_text:
            reference_text = comparator_match.group(0)

        if unit:
            unit_position = remainder.lower().find(unit.lower())
            if unit_position > 0 and not reference_text:
                tail = remainder[unit_position + len(unit) :].strip(" |")
                if tail:
                    reference_text = tail

        cleaned_test = self._clean_test_name(test_name)
        if len(cleaned_test) < 2 or cleaned_test.isdigit():
            return None
        if unit is None and reference_text is None and not self._looks_like_test_name(cleaned_test):
            return None

        return RawObservation(
            raw_test_name=cleaned_test,
            raw_value=value,
            raw_unit=unit,
            raw_reference_range=reference_text,
            section=section,
            line_text=line,
        )

    @staticmethod
    def _clean_test_name(test_name: str) -> str:
        cleaned_test = re.sub(r"\{[^}]*\}", "", test_name)
        cleaned_test = re.sub(r"\s+\d+(?:[.,]\d+)?\s*[A-Za-z/%][A-Za-z0-9/%.-]*$", "", cleaned_test)
        cleaned_test = re.sub(r"\s{2,}", " ", cleaned_test).strip(" :-|")
        return cleaned_test

    def _select_measurement_match(self, line: str) -> re.Match[str] | None:
        matches = list(VALUE_PATTERN.finditer(line))
        if not matches:
            return None

        best_match: re.Match[str] | None = None
        best_score = -10
        for match in matches:
            if self._is_false_negative_fragment(line, match):
                continue

            prefix = line[: match.start()]
            suffix = line[match.end() :]
            prefix_norm = normalize_text(prefix)
            suffix_norm = normalize_text(suffix)
            score = 0

            if re.search(r"[a-zA-Z]", prefix):
                score += 2
            if UNIT_PATTERN.search(suffix):
                score += 4
            if re.match(rf"^\s*{UNIT_PATTERN_TEXT}", suffix, re.IGNORECASE):
                score += 6
            if re.match(r"^\s*[hl]?\s*[a-z/!.%]+\s+\d+(?:[.,]\d+)?\s*[-\u2013]\s*\d", suffix, re.IGNORECASE):
                score += 5
            if RANGE_PATTERN.search(suffix) or COMPARATOR_PATTERN.search(suffix):
                score += 3
            if re.match(r"^\s+\d+(?:[.,]\d+)?\s*[-\u2013]\s*\d", suffix):
                score += 4
            if re.search(r"\b(?:less than|up to)\b", suffix_norm):
                score += 2
            if "%" in suffix or "high" in suffix_norm or "low" in suffix_norm:
                score += 1
            if match.start() > 0 and line[match.start() - 1].isalpha():
                score -= 8
            if match.end() < len(line) and line[match.end()].isalpha():
                score -= 8
            if match.start() > 0 and line[match.start() - 1] in {"/", "\\"}:
                score -= 3
            if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", line[match.start() :]):
                score -= 5
            if re.match(r"^\s*[-/]*\s*[a-zA-Z]", suffix):
                score -= 4
            if UNIT_PATTERN.search(prefix):
                score -= 5
            if prefix_norm in {"test", "date of collection", "patient id", "srl no", "reg no"}:
                score -= 5
            if self._looks_like_metadata_prefix(prefix):
                score -= 6

            if score > best_score:
                best_score = score
                best_match = match

        return best_match if best_score > 0 else None

    @staticmethod
    def _is_false_negative_fragment(line: str, match: re.Match[str]) -> bool:
        start = match.start()
        if match.group(0).startswith("-") and start > 0 and line[start - 1].isdigit():
            return True
        if start > 0 and line[start - 1] in {"-", "\u2013"} and line[max(0, start - 2)].isdigit():
            return True
        return False

    @staticmethod
    def _sanitize_line(line: str) -> str:
        return (
            line.replace("ÃƒÂ¯Ã‚Â¼Ã…Â¡", ":")
            .replace("Ã¯Â¼Å¡", ":")
            .replace("Ã¢â‚¬â€", "-")
            .replace("Ã¢â‚¬â€œ", "-")
            .replace("\u2013", "-")
            .strip()
        )

    def _is_noise_row(self, row: LayoutRow, normalized: str) -> bool:
        if row.region in {"footer", "signature"}:
            return True
        if normalized.startswith("ip bed"):
            return True
        if re.fullmatch(r"\d{1,2} \d{2} \d{2}am \d{1,2} \d{2} \d{2}pm", normalized):
            return True
        if "website" in normalized or "www" in normalized:
            return True
        if " ph " in f" {normalized} " or " ph." in normalized:
            return True
        if re.search(r"\b\d{6,}\b", normalized) and ("road" in normalized or "extension" in normalized):
            return True
        return any(fragment in normalized for fragment in NOISE_FRAGMENTS)

    @staticmethod
    def _looks_like_test_name(line: str) -> bool:
        normalized = normalize_text(line)
        test_hints = [
            "vitamin",
            "bilirubin",
            "ast",
            "alt",
            "ggt",
            "albumin",
            "protein",
            "globulin",
            "ratio",
            "magnesium",
            "haemoglobin",
            "platelet",
            "leukocyte",
            "lymphocyte",
            "eosinophil",
            "monocyte",
            "basophil",
        ]
        return any(hint in normalized for hint in test_hints)

    @staticmethod
    def _looks_like_metadata_prefix(text: str) -> bool:
        normalized = normalize_text(text)
        return any(
            normalized.startswith(prefix)
            for prefix in (
                "invoice",
                "patient",
                "receipt",
                "srl",
                "sr",
                "regn",
                "kj-",
                "report",
                "diagnostic",
                "pathology",
                "hospital",
                "doctor",
                "dr",
                "sample",
            )
        )
