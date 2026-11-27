"""
Complete lab extractor — miss-nothing design.

Unlike the legacy one-line parser, this module:
1. Treats every OCR line as ground truth (never silently deletes).
2. Stitches multi-column OCR fragments that belong to the same lab row
   (common when RapidOCR splits Name / Value / Range / Unit onto separate lines).
3. Extracts quantitative, observed-range, comparator, and qualitative results.
4. Classifies leftover lines (header / metadata / section / noise / unknown).
5. Computes high / low / normal whenever a reference range exists.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pipeline.models import OCRLine

LineClass = Literal[
    "lab_result",
    "section_header",
    "metadata",
    "header",
    "footer",
    "noise",
    "unknown",
]

VALUE_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")
FLAGGED_VALUE_RE = re.compile(
    r"^(?P<value>-?\d+(?:[.,]\d+)?)\s*(?P<flag>[HhLl]|HIGH|LOW|high|low)?$"
)
RANGE_RE = re.compile(
    r"^(?P<low>-?\d+(?:[.,]\d+)?)\s*(?:[-\u2013\u2014\u2212]|\bto\b)\s*"
    r"(?P<high>-?\d+(?:[.,]\d+)?)(?:\s*(?P<unit>%))?$",
    re.IGNORECASE,
)
# OCR often turns "0.30" into "0 30" inside ranges
RANGE_LOOSE_RE = re.compile(
    r"^(?P<low>-?\d+(?:[.,]\d+)?|\d+\s+\d+)\s*"
    r"(?:[-\u2013\u2014\u2212]|\bto\b)\s*"
    r"(?P<high>-?\d+(?:[.,]\d+)?|\d+\s+\d+)\s*"
    r"(?P<unit>%|g%|/hpf|/lpf|cells/(?:cmm|cumm))?$",
    re.IGNORECASE,
)
COMPARATOR_RE = re.compile(r"^(?P<comp>[<>]=?)\s*(?P<value>-?\d+(?:[.,]\d+)?)$")
DUAL_RANGE_INLINE = re.compile(
    r"^(?P<name>.+?)\s+"
    r"(?P<obs_low>\d+(?:[.,]\d+)?)\s*[-\u2013]\s*(?P<obs_high>\d+(?:[.,]\d+)?)"
    r"(?:\s*(?P<unit>/HPF|/LPF|cells/cmm|%))?"
    r"\s+(?P<ref_low>\d+(?:[.,]\d+)?)\s*[-\u2013]\s*(?P<ref_high>\d+(?:[.,]\d+)?)$",
    re.IGNORECASE,
)
INLINE_SCALAR = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 /()%+.,'_-]{1,80}?)\s+"
    r"(?P<value>[<>]=?\s*-?\d+(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?)\s*"
    r"(?P<flag>[HhLl]|HIGH|LOW)?\s*"
    r"(?P<unit>[A-Za-z%/^µμ][A-Za-z0-9%/^µμ.!-]{0,24})?\s*"
    r"(?:(?P<ref_low>-?\d+(?:[.,]\d+)?)\s*"
    r"(?:[-\u2013\u2014\u2212]|\bto\b)\s*"
    r"(?P<ref_high>-?\d+(?:[.,]\d+)?)(?:\s*(?P<ref_unit>%|/HPF|/LPF))?)?$",
    re.IGNORECASE,
)
INLINE_RANGE_ONLY = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 /()%+.,'_-]{1,80}?)\s+"
    r"(?P<low>-?\d+(?:[.,]\d+)?)\s*"
    r"(?:[-\u2013\u2014\u2212]|\bto\b)\s*"
    r"(?P<high>-?\d+(?:[.,]\d+)?)(?:\s*(?P<unit>%|/HPF|/LPF))?$",
    re.IGNORECASE,
)

UNIT_TOKENS = {
    "g%",
    "gms%",
    "g/dl",
    "g/l",
    "gm/dl",
    "gm/d",
    "gms/dl",
    "mg/dl",
    "mg/l",
    "ug/dl",
    "mcg/dl",
    "ng/dl",
    "ng/ml",
    "pg/ml",
    "pg",
    "fl",
    "mmol/l",
    "umol/l",
    "meq/l",
    "u/l",
    "iu/l",
    "miu/ml",
    "uiu/ml",
    "µiu/ml",
    "μiu/ml",
    "%",
    "cells/cmm",
    "cells/cumm",
    "lakhs/cumm",
    "lakhs/cmm",
    "lacs/cumm",
    "lacs/cmm",
    "millions/cumm",
    "x1000/cumm",
    "x1000/cmm",
    "/hpf",
    "/lpf",
    "/cumm",
    "/cmm",
    "mm/hr",
    "seconds",
    "sec",
    "ratio",
    "ml",
    "ml.",
    "nrbcs/100",
    "nrbc/100",
    "nrbc's/100",
}

# Common OCR corruptions → report-style unit (None = reject as noise)
UNIT_ALIASES = {
    "mgid!": "mg/dl",
    "mgid": "mg/dl",
    "mg'dl": "mg/dl",
    "mg/d!": "mg/dl",
    "mg/d": "mg/dl",
    "mgdl": "mg/dl",
    "mg/dl": "mg/dl",
    "mg/dl.": "mg/dl",
    "mgm/l": "mg/L",
    "mg/l": "mg/L",
    "iuil": "IU/L",
    "iu/l": "IU/L",
    "u/l": "U/L",
    "gm/al": "g/dl",
    "gm/d": "g/dl",
    "gm/dl": "g/dl",
    "gms/dl": "g/dl",
    "g/dl": "g/dl",
    "g%": "g%",
    "gms%": "g%",
    "cells/cmm": "cells/cmm",
    "cells/cumm": "cells/cumm",
    "lakhs/cumm": "Lakhs/Cumm",
    "lakhs/cmm": "Lakhs/Cumm",
    "lacs/cumm": "Lakhs/Cumm",
    "mmol/l": "mmol/L",
    "meq/l": "mEq/L",
    "ug/dl": "ug/dL",
    "µg/dl": "ug/dL",
    "ng/ml": "ng/ml",
    "pg/ml": "pg/ml",
    # Frequent OCR misreads of mg/dl / ug/dL (method-column glyphs)
    "ip/aw": "mg/dl",
    "ip/aw.": "mg/dl",
    "ip/3w": "mg/dl",
    "ip/8": "mg/dl",
    "ip/8w": "mg/dl",
    "ip/bw": "mg/dl",
    "iP/aw": "mg/dl",
    "tp/bn": "ug/dL",
    "tp/bw": "ug/dL",
    # Explicit noise / non-units
    "nrbcs/100": "NRBC'S/100",
    "nrbc/100": "NRBC'S/100",
    "nrbc's/100": "NRBC'S/100",
    "nrbcs100": "NRBC'S/100",
    "nrbc100": "NRBC'S/100",
    "ip/ub": None,
    "1%": None,
    "lonexchange": None,
    "doubleindicato": None,
    "doubleindic": None,
    "acid/base": None,
    "oxidase/peroxic": None,
    "oxidase/pero": None,
    "ehrlichreactior": None,
    "ehrlichreact": None,
    "microscopic": None,
    "exchange": None,
    "ase": None,
}

QUALITATIVE_VALUES = {
    "negative",
    "positive",
    "nil",
    "absent",
    "present",
    "trace",
    "clear",
    "cloudy",
    "hazy",
    "acidic",
    "alkaline",
    "non reactive",
    "non-reactive",
    "nonreactive",
    "reactive",
    "detected",
    "not detected",
    "notdetected",
    "normal",
    "abnormal",
    "pale yellow",
    "yellow",
    "straw",
    "colourless",
    "colorless",
    "turbid",
    "slightly turbid",
    "slightlyturbid",
    "slightly cloudy",
    "slightlycloudy",
}

SECTION_WORDS = {
    "haematology",
    "hematology",
    "biochemistry",
    "chemistry",
    "serology",
    "urinalysis",
    "urine",
    "thyroid",
    "lipid",
    "liver",
    "renal",
    "kidney",
    "electrolyte",
    "coagulation",
    "diabetes",
    "cbc",
    "complete blood count",
    "differential count",
    "differential count(dc)",
    "microscopic examination",
    "clinical pathology",
}

METADATA_PREFIXES = (
    "patient",
    "invoice",
    # Keep "sample …" metadata fields, but not clinical "Sample Volume".
    "sample collected",
    "sample received",
    "sample id",
    "sample no",
    "sample number",
    "sample type",
    "sample date",
    "sample time",
    "referred",
    "doctor",
    "dr.",
    "ip ",
    "ipd",
    "bed",
    "dept",
    "lab technician",
    "technician",
    "authorized",
    "printed by",
    "printed time",
    "printed",
    "insurance",
    "result ready",
    "result verified",
    "report gen",
    "laboratory report",
    "regn",
    "receipt",
)

NOISE_EXACT = {
    "test",
    "result",
    "unit",
    "reference",
    "reference range",
    "ref range",
    "ref.",
    "normal range",
    "routine",
    "method",
    "remarks",
    "note",
    "comments",
    "*** end of report ***",
    "end of report",
    "indicates abnormal result",
    "ndicatesabnormalresult",
}

COLUMN_HEADERS = {"test", "result", "unit", "reference range", "ref range", "normal range", "biological ref"}


@dataclass
class ClassifiedLine:
    index: int
    text: str
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    recovery_status: str = "original"
    alternatives: list[str] = field(default_factory=list)
    line_class: LineClass = "unknown"
    reason: str = ""


@dataclass
class ExtractedResult:
    test_name: str
    value: str | float | None
    unit: str | None = None
    reference_range: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    interpretation: str | None = None
    section: str | None = None
    result_type: str = "quantitative"
    ocr_source_text: str = ""
    confidence: float = 0.0
    parse_status: Literal["accepted", "needs_review"] = "accepted"
    ocr_recovery_status: str = "original"
    ocr_alternatives: list[str] = field(default_factory=list)
    row_id: str = ""
    source_line_indexes: list[int] = field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _fix_ocr_number(raw: str) -> str:
    """Normalize OCR number tokens without inventing digits.

    - ``0 30`` → ``0.30`` (broken decimal)
    - ``16,700`` stays thousands (``16700``), not ``16.700``
    - ``3Z`` → ``32`` for a single known OCR glyph confusion
    """
    text = str(raw).strip().replace("%", "")
    if not text:
        return text

    # European/US decimal comma only when it is clearly fractional.
    if re.fullmatch(r"-?\d+,\d{1,2}", text):
        text = text.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
        text = text.replace(",", "")
    elif "," in text:
        # Ambiguous comma forms are left untouched for salvage/review.
        pass

    if re.fullmatch(r"-?\d+\s+\d+", text):
        left, right = re.split(r"\s+", text, maxsplit=1)
        return f"{left}.{right}"

    lookalikes = {
        "z": "2",
        "o": "0",
        "l": "1",
        "i": "1",
        "s": "5",
        "b": "8",
        "g": "9",
    }
    repaired: list[str] = []
    letter_repairs = 0
    for ch in text:
        lower = ch.lower()
        if ch.isdigit() or ch in {".", "-", "+"}:
            repaired.append(ch)
        elif lower in lookalikes and letter_repairs < 1:
            repaired.append(lookalikes[lower])
            letter_repairs += 1
        else:
            return text
    candidate = "".join(repaired)
    if letter_repairs == 1 and re.fullmatch(r"-?\d+(?:\.\d+)?", candidate):
        return candidate
    return text


def _salvage_numeric_token(
    text: str,
    *,
    allow_lookalike: bool = True,
) -> str | None:
    """Recover a numeric value from OCR junk using only characters already present."""
    raw = text.strip()
    if not raw:
        return None

    if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw) or VALUE_RE.match(raw):
        fixed = _fix_ocr_number(raw)
        if re.fullmatch(r"-?\d+(?:\.\d+)?", fixed):
            return fixed

    # Strip surrounding punctuation only. Leading letters usually mean an ID
    # code (``EB1660516``), so they must not be shaved into a fake value.
    cleaned = re.sub(r"^[^0-9A-Za-z<>-]+", "", raw)
    cleaned = re.sub(r"[*#!?]+$", "", cleaned).strip()
    if cleaned and cleaned != raw:
        fixed = _fix_ocr_number(cleaned)
        if re.fullmatch(r"-?\d+(?:\.\d+)?", fixed):
            return fixed

    if allow_lookalike:
        repaired = _fix_ocr_number(raw)
        if (
            repaired != raw
            and re.fullmatch(r"-?\d+(?:\.\d+)?", repaired)
            and sum(ch.isalpha() for ch in raw) <= 1
        ):
            return repaired

    flagged = FLAGGED_VALUE_RE.match(cleaned or raw)
    if flagged and flagged.group("flag"):
        fixed = _fix_ocr_number(flagged.group("value"))
        if re.fullmatch(r"-?\d+(?:\.\d+)?", fixed):
            return fixed
    return None


def _salvage_value_from_line(line: ClassifiedLine) -> tuple[str | None, bool]:
    """Return ``(value, used_alternative)`` from primary text or OCR alternatives."""
    primary = _salvage_numeric_token(line.text, allow_lookalike=False)
    if primary is not None:
        return primary, False
    for alternative in line.alternatives:
        recovered = _salvage_numeric_token(alternative, allow_lookalike=False)
        if recovered is not None:
            return recovered, True
    primary = _salvage_numeric_token(line.text, allow_lookalike=True)
    if primary is not None:
        return primary, True
    return None, False


def _analyte_tokens(text: str) -> list[str]:
    """Tokenize glued/CamelCase analyte labels for lab-name evidence checks."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    spaced = re.sub(r"([A-Za-z])(\d)", r"\1 \2", spaced)
    spaced = re.sub(r"(\d)([A-Za-z])", r"\1 \2", spaced)
    spaced = spaced.replace("-", " ").replace("/", " ").replace("'", " ")
    tokens = re.findall(r"[a-z0-9]+", _norm(spaced))
    compact = "".join(tokens)
    # Recover known terms glued together, e.g. ANTIGENDENGUE → antigen + dengue.
    for term in sorted(
        (token for token in LAB_NAME_TOKENS if len(token) >= 3),
        key=len,
        reverse=True,
    ):
        if term in compact and term not in tokens:
            tokens.append(term)
    return tokens


def _has_microscopy_cue(
    *,
    analyte_parts: list[str],
    section: str | None,
    range_unit: str | None,
) -> bool:
    if _is_microscopy_unit(range_unit):
        return True
    section_l = (section or "").lower()
    if any(token in section_l for token in ("urine", "microscopic", "urinalysis")):
        return True
    joined = " ".join(_analyte_tokens(" ".join(analyte_parts)))
    return any(
        token in joined
        for token in (
            "pus",
            "epithelial",
            "cast",
            "casts",
            "crystal",
            "crystals",
            "rbc",
            "wbc",
            "bacteria",
        )
    )


def _parse_float(value: str | float | None) -> float | None:
    if value is None:
        return None
    try:
        return float(_fix_ocr_number(value))
    except ValueError:
        return None


def _unit_key(text: str) -> str:
    return re.sub(r"[^a-z0-9/%]", "", _norm(text).replace(" ", ""))


def _is_method_noise(text: str) -> bool:
    t = _norm(text)
    if t.startswith(("method", "melhod", "metiod", "methode", "metod")):
        return True
    if t.startswith("method:") or "method:" in t or "melhod:" in t or "metiod:" in t:
        return True
    method_terms = globals().get("METHOD_ONLY_TERMS")
    if method_terms and _contains_context_term(text, method_terms):
        return True
    return False


def _normalize_unit(text: str) -> str | None:
    """Return a report-style unit string, or None if not a real unit."""
    raw = text.strip()
    if not raw or _is_method_noise(raw):
        return None
    t = _norm(raw).replace(" ", "")
    key = _unit_key(raw)

    if t in UNIT_ALIASES:
        return UNIT_ALIASES[t]
    if key in UNIT_ALIASES:
        return UNIT_ALIASES[key]
    if re.fullmatch(r"nrbc'?s?/100", t, re.IGNORECASE):
        return "NRBC'S/100"
    if t in UNIT_TOKENS:
        # Preserve common on-report spellings
        if t in {"g%", "gms%", "cells/cmm", "cells/cumm", "lakhs/cumm", "lakhs/cmm", "/hpf", "/lpf", "%"}:
            if t == "gms%":
                return "g%"
            if t.startswith("lakhs") or t.startswith("lacs"):
                return "Lakhs/Cumm"
            if t == "/hpf":
                return "/HPF"
            if t == "/lpf":
                return "/LPF"
            return raw if raw in {"g%", "%"} else t
        return raw

    if key in UNIT_TOKENS:
        return key

    # Strip OCR punctuation noise: mgid!, mg/d!, IUIL
    if re.fullmatch(r"(g|gm|gms|mg|ug|mcg|ng|pg|mmol|umol|meq|u|iu|miu|uiu|µiu|μiu)(%|/?d?l|/?ml)?", key):
        stem = re.match(r"(g|gm|gms|mg|ug|mcg|ng|pg|mmol|umol|meq|u|iu|miu|uiu)", key)
        if stem and key.endswith("dl"):
            base = stem.group(1)
            if base in {"gm", "gms"}:
                return "g/dl"
            return f"{base}/dl"
        if stem and key.endswith("ml"):
            return f"{stem.group(1)}/ml"
        if key in {"iuil", "iul"}:
            return "IU/L"
        if key.endswith("%"):
            return "g%" if key.startswith("g") else "%"
        return key

    # Reject long alphabetic "units" that are really method/technique crumbs
    if len(key) > 12 and not any(ch in key for ch in "/%"):
        return None
    if re.search(r"(exchange|indicat|oxidase|ehrlich|microscopic|hexokinase|turbid|diazo)", key):
        return None
    return None


def _is_unit(text: str) -> bool:
    return _normalize_unit(text) is not None


def _display_number(raw: str | float | None) -> str | float | None:
    """Keep numeric results readable while staying faithful to OCR digits."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        text = f"{raw:.6f}".rstrip("0").rstrip(".")
        return text
    text = _fix_ocr_number(str(raw)).strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return str(raw).strip()
    if "." in text:
        whole, frac = text.split(".", 1)
        frac = frac.rstrip("0")
        return f"{whole}.{frac}" if frac else whole
    return text


def _parse_flagged_value(text: str) -> tuple[str, str | None] | None:
    """Parse '9.42H', '162 h', '3.7 L' → (value, flag_hint)."""
    match = FLAGGED_VALUE_RE.match(text.strip())
    if not match:
        return None
    value = _fix_ocr_number(match.group("value"))
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        return None
    flag = match.group("flag")
    if not flag:
        # Bare number — only accept via VALUE_RE path to avoid swallowing ranges
        raw = text.strip()
        if VALUE_RE.match(raw) or re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
            return value, None
        return None
    hint = "high" if flag.upper().startswith("H") else "low"
    return value, hint


def _is_qualitative(text: str) -> bool:
    t = _norm(text)
    if t in QUALITATIVE_VALUES:
        return True
    compact = t.replace(" ", "").replace("-", "")
    return any(q.replace(" ", "").replace("-", "") == compact for q in QUALITATIVE_VALUES)


def _is_section(text: str) -> bool:
    t = _norm(text)
    compact = re.sub(r"[^a-z0-9]", "", t)
    # Exact section titles only — do not treat "Urine pH" as a section
    for s in SECTION_WORDS:
        if t == s or compact == re.sub(r"[^a-z0-9]", "", s):
            return True
    return False


def _is_metadata(text: str) -> bool:
    t = _norm(text)
    if t in NOISE_EXACT or t in COLUMN_HEADERS:
        return True
    return any(t == p.strip() or t.startswith(p) for p in METADATA_PREFIXES)


def _looks_like_id_or_code(text: str) -> bool:
    t = text.strip()
    if re.fullmatch(r"[A-Z]?\d{5,}", t):
        return True
    if re.fullmatch(r"[A-Z]{0,3}-?\d{4,}", t, re.IGNORECASE):
        return True
    if re.fullmatch(r"[A-Z]-?\d{5,}", t, re.IGNORECASE):
        return True
    if re.search(r"\b(icu|ward|bed|ipd|opid)\b", t, re.IGNORECASE) and not re.search(r"[a-z]{4,}", _norm(t).replace("icu", "").replace("ward", "").replace("bed", "").replace("ipd", "")):
        return True
    if re.fullmatch(r"[A-Z0-9][A-Z0-9\-/]{4,}", t) and sum(ch.isdigit() for ch in t) >= 3:
        return True
    return False


LAB_NAME_TOKENS = {
    "count",
    "counts",
    "level",
    "levels",
    "ratio",
    "index",
    "volume",
    "width",
    "cells",
    "cell",
    "serum",
    "blood",
    "urine",
    "total",
    "free",
    "direct",
    "indirect",
    "absolute",
    "mean",
    "average",
    "protein",
    "proteln",  # OCR typo for protein
    "albumin",
    "globulin",
    "reactive",
    "bilirubin",
    "creatinine",
    "cholesterol",
    "triglyceride",
    "hemoglobin",
    "haemoglobin",
    "platelet",
    "leucocyte",
    "leukocyte",
    "glucose",
    "sodium",
    "potassium",
    "chloride",
    "calcium",
    "phosphorus",
    "iron",
    "ferritin",
    "tsh",
    "t3",
    "t4",
    "hba1c",
    "inr",
    "pt",
    "aptt",
    "esr",
    "crp",
    "wbc",
    "rbc",
    "pcv",
    "mcv",
    "mch",
    "mchc",
    "rdw",
    "mpv",
    "pus",
    "epithelial",
    "cast",
    "casts",
    "crystal",
    "crystals",
    "ketone",
    "ketones",
    "nitrite",
    "nitrites",
    "colour",
    "color",
    "appearance",
    "reaction",
    "quantity",
    "transparency",
    "urobilinogen",
    "sugar",
    "bacteria",
    "microorganism",
    "microorganisms",
    "nucleated",
    "nrbc",
    "nrbcs",
    "dengue",
    "antigen",
    "ns1",
    "ns",
    "volume",
    "zinc",
    "amylase",
    "lipase",
    "troponin",
    "vitamin",
    "folate",
    "cobalamin",
    "specific",
    "gravity",
    "ph",
}

NON_RESULT_LABELS = {
    "physical",
    "physical examination",
    "physicalexamination",
    "chemical examination",
    "chemicalexamination",
    "microscopic examination",
    "microscopicexamination",
    "remarks",
    "remark",
    "interpretation",
    "result",
    "results",
    "method",
    "test",
}

METHOD_ONLY_TERMS = {
    "hexokinase",
    "immunoturbidimetry",
    "turbidimetry",
    "elfa method",
    "elfamethod",
    "diazo",
    "photometry",
}

ADDRESS_OR_ORG_TERMS = {
    "hospital",
    "clinic",
    "laboratory",
    "diagnostic",
    "medical centre",
    "medical center",
    "palace",
    "meerut",
    "kannada",
    "road",
    "street",
    "nagar",
    "chowk",
    "district",
    "city",
    "phone",
    "mobile",
}


def _contains_context_term(text: str, terms: set[str]) -> bool:
    normalized = _norm(text)
    compact = re.sub(r"[^a-z0-9]", "", normalized)
    for term in terms:
        term_norm = _norm(term)
        if " " in term_norm:
            if term_norm in normalized:
                return True
        elif re.search(rf"\b{re.escape(term_norm)}\b", normalized):
            return True
        elif term_norm in {"hospital", "clinic", "laboratory", "diagnostic"} and term_norm in compact:
            return True
    return False


def _is_method_only_label(text: str) -> bool:
    return _contains_context_term(text, METHOD_ONLY_TERMS)


def _looks_like_person_name(text: str) -> bool:
    t = text.strip()
    if re.search(r"\d", t):
        return False
    if re.search(r"[-/()]", t):
        # Hyphenated clinical labels (C-Reactive Protein), not people
        return False
    parts = [p for p in re.split(r"\s+", t) if p]
    if not (2 <= len(parts) <= 4):
        return False
    if any(_norm(p) in LAB_NAME_TOKENS for p in parts):
        return False
    # Lab analytes are often ALL CAPS; person names on prints usually aren't uniform all-caps jargon
    if sum(1 for p in parts if p.isupper() and len(p) > 2) >= 2:
        return False
    return all(re.fullmatch(r"[A-Za-z][A-Za-z.\-']{1,20}", p) for p in parts)


def _looks_like_analyte(text: str) -> bool:
    t = _norm(text)
    if not t or VALUE_RE.match(t) or RANGE_RE.match(t) or RANGE_LOOSE_RE.match(t) or _is_unit(t) or _is_qualitative(t):
        return False
    compact = re.sub(r"[^a-z0-9]", "", t)
    non_result_labels = globals().get("NON_RESULT_LABELS", set())
    if t in non_result_labels or compact in {
        re.sub(r"[^a-z0-9]", "", label) for label in non_result_labels
    }:
        return False
    if _is_method_noise(text):
        return False
    # Never treat flagged numeric results as analyte names
    flagged = _parse_flagged_value(text)
    if flagged and flagged[1] is not None:
        return False
    if _is_metadata(t) or _is_section(t) or t in COLUMN_HEADERS:
        return False
    if re.match(r"^(mr|mrs|ms|miss|dr)[\s.:]", t):
        return False
    if _looks_like_id_or_code(text) or _looks_like_person_name(text):
        return False
    if len(t) < 2:
        return False
    if not re.search(r"[a-z]", t):
        return False
    # Mostly-numeric tokens with a trailing flag letter are values, not names
    if re.fullmatch(r"-?\d+(?:[.,]\d+)?\s*[hHlL]", t):
        return False
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?\s*(am|pm)?", t):
        return False
    if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*", t):
        return False
    # Reject bare department crumbs
    if t in {"neurology", "cardiology", "orthopedics", "no", "no:", "yes"}:
        return False
    # Hospital / org crumbs
    if "hospital" in t and not any(tok in t for tok in ("count", "glucose", "blood", "urine")):
        return False
    # Glued labels such as NucleatedRBC / NS-1ANTIGENDENGUE still count.
    if any(token in LAB_NAME_TOKENS for token in _analyte_tokens(text)):
        return True
    return True


def _is_valid_result_row(row: ExtractedResult) -> tuple[bool, str | None]:
    """Conservatively reject metadata and method text masquerading as lab rows."""
    name = _norm(row.test_name)
    compact = re.sub(r"[^a-z0-9]", "", name)
    source = _norm(row.ocr_source_text)

    if not name or name in NON_RESULT_LABELS or compact in {
        re.sub(r"[^a-z0-9]", "", label) for label in NON_RESULT_LABELS
    }:
        return False, "section_or_boilerplate"

    if re.match(r"^(mr|mrs|ms|miss|dr)\b", name):
        return False, "person_name"
    if _contains_context_term(name, ADDRESS_OR_ORG_TERMS):
        return False, "address_or_organization"
    if _is_method_only_label(name):
        return False, "method_not_analyte"
    if "method" in name or "method)" in name:
        return False, "method_not_analyte"

    # A person/address line can be stitched into a later numeric identifier.
    if re.search(r"\b(mr|mrs|miss|patient|address|phone|mobile)\s*[:.]", source):
        return False, "patient_metadata"
    if _contains_context_term(source, ADDRESS_OR_ORG_TERMS) and re.search(r"\b\d{5,6}\b", source):
        return False, "address_or_organization"

    has_lab_name_evidence = any(
        token in LAB_NAME_TOKENS for token in _analyte_tokens(row.test_name)
    ) or bool(
        re.search(
            r"\b(sgot|sgpt|alt|ast|ggt|plcr|pct|tibc|rdw|mpv|mcv|mch|mchc|wbc|rbc|tsh|inr|aptt|esr|crp|ns-?1)\b",
            name,
        )
    )
    has_result_evidence = bool(
        row.unit
        or row.reference_range
        or row.interpretation
        or row.result_type == "qualitative"
    )

    # Range-only leftovers from OCR noise are not clinical rows. Keep the range
    # token free so orphan attachment can give it to the real analyte.
    if row.value is None and not has_lab_name_evidence:
        return False, "incomplete_without_lab_name"

    # Unknown labels paired only with a bare number are commonly IDs, dates,
    # postal codes, or header fragments. Keep them in OCR text, not results.
    if not has_lab_name_evidence and not has_result_evidence:
        return False, "insufficient_lab_evidence"

    # Names dominated by punctuation/OCR garbage are not safe clinical labels.
    letters = sum(ch.isalpha() for ch in row.test_name)
    if letters < 2 or (len(row.test_name) > 8 and letters / len(row.test_name) < 0.45):
        return False, "garbled_label"

    return True, None


def _infer_interpretation(
    value: str | float | None,
    low: float | None,
    high: float | None,
    *,
    observed_low: float | None = None,
    observed_high: float | None = None,
) -> str | None:
    if low is None and high is None:
        return None
    if observed_low is not None and observed_high is not None and low is not None and high is not None:
        if observed_low >= low and observed_high <= high:
            return "normal"
        if observed_high > high:
            return "high"
        if observed_low < low:
            return "low"
        return "normal"
    numeric = _parse_float(value)
    if numeric is None:
        return None
    if low is not None and numeric < low:
        return "low"
    if high is not None and numeric > high:
        return "high"
    return "normal"


def _row_id(name: str, value: Any, unit: str | None) -> str:
    payload = f"{name}|{value}|{unit or ''}"
    return f"row_{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


def classify_lines(ocr_lines: list[OCRLine]) -> list[ClassifiedLine]:
    ordered = sorted(
        enumerate(ocr_lines),
        key=lambda item: (item[1].y_min, item[1].x_min),
    )
    classified: list[ClassifiedLine] = []
    page_height = max((line.y_max for line in ocr_lines), default=1.0) or 1.0

    for index, line in ordered:
        text = (line.text or "").strip()
        item = ClassifiedLine(
            index=index,
            text=text,
            confidence=float(line.confidence or 0),
            x_min=float(line.x_min),
            y_min=float(line.y_min),
            x_max=float(line.x_max),
            y_max=float(line.y_max),
            recovery_status=line.recovery_status,
            alternatives=list(line.alternatives),
        )
        t = _norm(text)
        if not t:
            item.line_class = "noise"
            item.reason = "empty"
        elif item.y_min / page_height > 0.92 and (
            _is_metadata(text) or t in NOISE_EXACT or "printed" in t or "authorized" in t
        ):
            item.line_class = "footer"
            item.reason = "bottom_band"
        elif _is_section(text):
            item.line_class = "section_header"
            item.reason = "section_keyword"
        elif t in COLUMN_HEADERS or t in NOISE_EXACT:
            item.line_class = "noise"
            item.reason = "table_header_or_boilerplate"
        elif _is_metadata(text):
            item.line_class = "metadata"
            item.reason = "metadata_prefix"
        elif item.y_min / page_height < 0.12 and _is_metadata(text):
            item.line_class = "header"
            item.reason = "top_metadata"
        else:
            item.line_class = "unknown"
            item.reason = "candidate"
        classified.append(item)
    return classified


def _group_into_bands(lines: list[ClassifiedLine], y_tolerance: float = 22.0) -> list[list[ClassifiedLine]]:
    """Group OCR fragments that share approximately the same vertical band.

    Uses an anchor-y (first fragment in the band) so rows do not chain-merge when
    consecutive analytes sit close together vertically. Also avoids packing two
    left-column analyte names into one band.
    """
    usable = [line for line in lines if line.line_class in {"unknown", "section_header"} and line.text]
    if not usable:
        return []

    page_width = max((line.x_max for line in usable), default=1000.0) or 1000.0
    name_x_cut = page_width * 0.38

    def _is_left_analyte(line: ClassifiedLine) -> bool:
        return line.x_min <= name_x_cut and _looks_like_analyte(line.text)

    bands: list[list[ClassifiedLine]] = []
    current: list[ClassifiedLine] = [usable[0]]
    anchor_y = (usable[0].y_min + usable[0].y_max) / 2

    for line in usable[1:]:
        y = (line.y_min + line.y_max) / 2
        height = max(line.y_max - line.y_min, 12.0)
        same_band = abs(y - anchor_y) <= max(y_tolerance, height * 0.85)
        if same_band and _is_left_analyte(line) and any(_is_left_analyte(c) for c in current):
            same_band = False
        if same_band:
            current.append(line)
        else:
            bands.append(sorted(current, key=lambda c: c.x_min))
            current = [line]
            anchor_y = y
    bands.append(sorted(current, key=lambda c: c.x_min))
    return _stitch_row_fragments(_merge_wrapped_analyte_names(bands))


def _merge_wrapped_analyte_names(
    bands: list[list[ClassifiedLine]],
    y_tolerance: float = 28.0,
) -> list[list[ClassifiedLine]]:
    """Join stacked left-column name fragments such as MEAN CORPUSCULAR / HEMOGLOBIN."""
    if not bands:
        return bands
    merged: list[list[ClassifiedLine]] = []
    index = 0
    while index < len(bands):
        band = bands[index]
        name_only = (
            _band_has_name(band)
            and not _band_has_result_token(band)
            and all(
                _looks_like_analyte(item.text) or item.line_class == "section_header"
                for item in band
            )
        )
        if name_only and index + 1 < len(bands):
            nxt = bands[index + 1]
            next_continues = (
                _band_has_name(nxt)
                and abs(_band_y(nxt) - _band_y(band)) <= y_tolerance
                and _looks_like_analyte(sorted(nxt, key=lambda item: item.x_min)[0].text)
            )
            if next_continues:
                merged.append(
                    sorted([*band, *nxt], key=lambda item: (item.y_min, item.x_min))
                )
                index += 2
                continue
        merged.append(band)
        index += 1
    return merged


def _band_y(band: list[ClassifiedLine]) -> float:
    return sum((c.y_min + c.y_max) / 2 for c in band) / max(len(band), 1)


def _band_has_name(band: list[ClassifiedLine]) -> bool:
    return any(_looks_like_analyte(c.text) for c in band)


def _band_has_result_token(band: list[ClassifiedLine]) -> bool:
    for c in band:
        t = c.text.strip()
        if VALUE_RE.match(t) or _parse_flagged_value(t) or _is_qualitative(t):
            return True
        if COMPARATOR_RE.match(t):
            return True
    return False


def _stitch_row_fragments(bands: list[list[ClassifiedLine]], y_tolerance: float = 70.0) -> list[list[ClassifiedLine]]:
    """Assign split value/range bands to their nearest analyte row.

    Every nameless fragment is assigned to at most one name anchor. This avoids
    the previous first-match behavior where one row could absorb values and
    normal ranges belonging to adjacent rows.
    """
    if not bands:
        return bands

    anchor_indexes = [i for i, band in enumerate(bands) if _band_has_name(band)]
    if not anchor_indexes:
        return bands

    assignments: dict[int, list[int]] = {i: [] for i in anchor_indexes}
    assigned_fragments: set[int] = set()

    for i, band in enumerate(bands):
        if i in assignments or _band_has_name(band):
            continue
        # Section headers are context, never result-column fragments.
        if any(item.line_class == "section_header" for item in band):
            continue
        normalized_texts = {_norm(item.text) for item in band}
        if any(
            text in NON_RESULT_LABELS or _is_metadata(text)
            for text in normalized_texts
        ):
            continue
        contains_method = any(_is_method_noise(item.text) for item in band)
        contains_unclassified_words = any(
            re.search(r"[A-Za-z]", item.text)
            and not _is_method_noise(item.text)
            and not _is_unit(item.text)
            and not _is_qualitative(item.text)
            and _split_range_and_unit(item.text)[0] is None
            for item in band
        )
        if contains_unclassified_words:
            continue
        contains_qualitative = any(_is_qualitative(item.text) for item in band)
        y = _band_y(band)
        candidates: list[tuple[float, int]] = []
        for anchor_index in anchor_indexes:
            anchor_y = _band_y(bands[anchor_index])
            # Assay-method lines describe the analyte immediately above them;
            # never pull them backward into the next clinical row.
            if contains_method and anchor_y > y:
                continue
            distance = abs(y - anchor_y)
            if contains_qualitative:
                # Qualitative results may sit farther from a name-only analyte
                # (e.g. Dengue NS-1 + NON-REACTIVE). Keep them tight when the
                # anchor already has a scalar so neighboring rows stay clean.
                if _band_has_result_token(bands[anchor_index]):
                    effective_tolerance = min(y_tolerance, 32.0)
                else:
                    effective_tolerance = y_tolerance
            else:
                effective_tolerance = y_tolerance
            if distance <= effective_tolerance:
                candidates.append((distance, anchor_index))
        if not candidates:
            continue
        # Stable tie-break by reading order.
        _, nearest_anchor = min(candidates, key=lambda item: (item[0], item[1]))
        assignments[nearest_anchor].append(i)
        assigned_fragments.add(i)

    merged: list[list[ClassifiedLine]] = []
    for i, band in enumerate(bands):
        if i in assigned_fragments:
            continue
        if i in assignments:
            combined = list(band)
            for fragment_index in assignments[i]:
                combined.extend(bands[fragment_index])
            merged.append(sorted(combined, key=lambda c: (c.x_min, c.y_min)))
        else:
            merged.append(band)

    # Preserve reading order
    merged.sort(key=_band_y)
    return merged


def _split_range_and_unit(text: str) -> tuple[str | None, str | None, float | None, float | None]:
    """Parse common normal-range styles without inventing digits."""
    raw = text.strip().strip("()[]")
    glued = re.match(
        r"^(?P<low>-?\d+(?:[.,]\d+)?|\d+\s+\d+)\s*"
        r"(?:[-\u2013\u2014\u2212]|\bto\b)\s*"
        r"(?P<high>-?\d+\s+\d+|-?\d+[A-Za-z]|[A-Za-z]\d+(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?)\s*"
        r"(?P<unit>.+)?$",
        raw,
        re.IGNORECASE,
    )
    if not glued:
        return None, None, None, None
    low_raw = _fix_ocr_number(glued.group("low"))
    high_raw = _fix_ocr_number(glued.group("high"))
    # Reject if high side still isn't numeric after OCR digit repair.
    if _parse_float(high_raw) is None or _parse_float(low_raw) is None:
        return None, None, None, None
    range_unit_raw = (glued.group("unit") or "").strip()
    range_unit = _normalize_unit(range_unit_raw) if range_unit_raw else None
    if range_unit_raw and range_unit is None:
        return None, None, None, None
    return (
        f"{low_raw} - {high_raw}",
        range_unit,
        _parse_float(low_raw),
        _parse_float(high_raw),
    )


def _split_reference_bound(
    text: str,
) -> tuple[str | None, str | None, float | None, float | None]:
    """Parse one-sided normal limits such as ``< 200`` or ``Above 60``."""
    raw = text.strip().strip("()[]")
    bound = re.match(
        r"^(?P<label><=?|>=?|up\s*to|upto|less\s+than|below|under|"
        r"more\s+than|above|over)\s*"
        r"(?P<value>-?\d+(?:[.,]\d+)?)\s*"
        r"(?P<unit>%|g%|cells/(?:cmm|cumm)|/hpf|/lpf)?$",
        raw,
        re.IGNORECASE,
    )
    if not bound:
        return None, None, None, None
    label = _norm(bound.group("label")).replace(" ", "")
    value_raw = _fix_ocr_number(bound.group("value"))
    value = _parse_float(value_raw)
    unit = _normalize_unit(bound.group("unit")) if bound.group("unit") else None
    upper_bound = label in {
        "<",
        "<=",
        "upto",
        "lessthan",
        "below",
        "under",
    }
    symbol = "<=" if label in {"<=", "upto"} else ("<" if upper_bound else (">=" if label == ">=" else ">"))
    return (
        f"{symbol} {value_raw}",
        unit,
        None if upper_bound else value,
        value if upper_bound else None,
    )


def _coalesce_split_ranges(
    pieces: list[tuple[str, ClassifiedLine]],
) -> list[tuple[str, ClassifiedLine]]:
    """Join OCR-split ``low`` / dash / ``high`` fragments before parsing.

    Coordinates remain tied to the original OCR lines through the containing
    band's source indexes; this only reconstructs punctuation already present.
    """
    combined: list[tuple[str, ClassifiedLine]] = []
    i = 0
    number = r"-?\d+(?:[.,]\d+)?"
    separator = r"(?:[-\u2013\u2014\u2212]|to)"
    while i < len(pieces):
        text, line = pieces[i]
        stripped = text.strip()
        if i + 2 < len(pieces):
            middle = pieces[i + 1][0].strip()
            end = pieces[i + 2][0].strip()
            if (
                re.fullmatch(number, stripped)
                and re.fullmatch(separator, middle, re.IGNORECASE)
                and re.fullmatch(number, end)
            ):
                combined.append((f"{stripped} - {end}", line))
                i += 3
                continue
        if i + 1 < len(pieces):
            end = pieces[i + 1][0].strip()
            trailing = re.fullmatch(rf"(?P<low>{number})\s*{separator}", stripped, re.IGNORECASE)
            leading = re.fullmatch(rf"{separator}\s*(?P<high>{number})", end, re.IGNORECASE)
            if trailing and re.fullmatch(number, end):
                combined.append((f"{trailing.group('low')} - {end}", line))
                i += 2
                continue
            if re.fullmatch(number, stripped) and leading:
                combined.append((f"{stripped} - {leading.group('high')}", line))
                i += 2
                continue
        combined.append((text, line))
        i += 1
    return combined


def _is_microscopy_unit(unit: str | None) -> bool:
    if not unit:
        return False
    return _norm(unit).replace(" ", "") in {"/hpf", "/lpf", "cells/cmm", "cells/cumm"}


def _clean_analyte_name(name: str) -> str:
    """Strip trailing value/unit/flag fragments that leaked into the name."""
    cleaned = name.strip(" :,-")
    cleaned = re.sub(
        r"\s+-?\d+(?:[.,]\d+)?\s*(?:[HhLl]|HIGH|LOW)?\s*(?:[A-Za-z%/^µμ.][A-Za-z0-9%/^µμ.!]{0,12})?\s*$",
        "",
        cleaned,
    ).strip(" :,-")
    return cleaned or name.strip(" :,-")


def _choose_reference_range(
    value: str | float | None,
    ranges: list[tuple[str, str | None, float | None, float | None, int | None]],
) -> tuple[str, str | None, float | None, float | None, int | None] | None:
    """Pick the reference interval that best fits a scalar value when several are present."""
    if not ranges:
        return None
    if len(ranges) == 1:
        return ranges[0]
    numeric = _parse_float(value)
    if numeric is None:
        return ranges[-1]

    containing = [
        r
        for r in ranges
        if (r[2] is None or numeric >= r[2])
        and (r[3] is None or numeric <= r[3])
        and (r[2] is not None or r[3] is not None)
    ]
    if containing:
        # Prefer the tightest containing interval
        return min(
            containing,
            key=lambda r: (
                (r[3] - r[2])
                if r[2] is not None and r[3] is not None
                else float("inf")
            ),
        )

    def _distance(r: tuple[str, str | None, float | None, float | None, int | None]) -> float:
        low, high = r[2], r[3]
        if low is None and high is None:
            return 1e9
        if low is not None and numeric < low:
            return low - numeric
        if high is not None and numeric > high:
            return numeric - high
        return 0.0

    return min(ranges, key=_distance)


def _parse_band(band: list[ClassifiedLine], section: str | None) -> ExtractedResult | None:
    # Keep (text, line) pairs so unused range fragments can be released for orphan attach
    pieces = [(c.text.strip(), c) for c in band if c.text.strip()]
    if not pieces:
        return None

    # RapidOCR sometimes returns a complete row as one text box. Expand that
    # box into logical fields so it follows the same parser as split columns.
    if len(pieces) == 1:
        original_text, original_line = pieces[0]
        number_tokens = re.findall(r"-?\d+(?:[.,]\d+)?", original_text)
        range_only = INLINE_RANGE_ONLY.match(original_text)
        # With exactly two numbers joined by a range separator, interpreting
        # the first number as a truncated scalar would invent a result.
        prefer_range_only = bool(
            range_only
            and len(number_tokens) == 2
            and _looks_like_analyte(range_only.group("name"))
        )
        inline = None if prefer_range_only else INLINE_SCALAR.match(original_text)
        if inline and _looks_like_analyte(inline.group("name")):
            expanded = [
                (inline.group("name"), original_line),
                (
                    f"{inline.group('value')}{inline.group('flag') or ''}",
                    original_line,
                ),
            ]
            if inline.group("unit"):
                expanded.append((inline.group("unit"), original_line))
            if inline.group("ref_low") and inline.group("ref_high"):
                reference = (
                    f"{inline.group('ref_low')} - {inline.group('ref_high')}"
                )
                if inline.group("ref_unit"):
                    reference += f" {inline.group('ref_unit')}"
                expanded.append((reference, original_line))
            pieces = expanded
        else:
            if range_only and _looks_like_analyte(range_only.group("name")):
                reference = (
                    f"{range_only.group('low')} - {range_only.group('high')}"
                )
                if range_only.group("unit"):
                    reference += f" {range_only.group('unit')}"
                pieces = [
                    (range_only.group("name"), original_line),
                    (reference, original_line),
                ]
            else:
                normalized = _norm(original_text)
                for qualitative_value in sorted(
                    QUALITATIVE_VALUES, key=len, reverse=True
                ):
                    if not normalized.endswith(qualitative_value):
                        continue
                    name_end = len(original_text) - len(qualitative_value)
                    name = original_text[:name_end].strip(" :,-")
                    value_text = original_text[name_end:].strip()
                    if name and _looks_like_analyte(name):
                        pieces = [
                            (name, original_line),
                            (value_text, original_line),
                        ]
                    break

    pieces = _coalesce_split_ranges(pieces)

    texts = [t for t, _ in pieces]
    if len(texts) == 1 and _is_section(texts[0]):
        return None

    joined = " ".join(texts)
    indexes = [c.index for c in band]
    conf = sum(c.confidence for c in band) / max(len(band), 1)
    recovery_status = (
        "ambiguous"
        if any(c.recovery_status == "ambiguous" for c in band)
        else (
            "consensus_recovered"
            if any(c.recovery_status == "consensus_recovered" for c in band)
            else "original"
        )
    )
    recovery_alternatives = sorted(
        {alternative for c in band for alternative in c.alternatives}
    )

    dual = DUAL_RANGE_INLINE.match(joined)
    # Reject when a scalar result was swallowed into the name (e.g. "SG 1.030 5.5-6.5 1.005-1.025")
    if dual and re.search(r"-?\d+(?:[.,]\d+)?\s*$", dual.group("name").strip()):
        dual = None
    if dual:
        obs_low = _parse_float(dual.group("obs_low"))
        obs_high = _parse_float(dual.group("obs_high"))
        ref_low = _parse_float(dual.group("ref_low"))
        ref_high = _parse_float(dual.group("ref_high"))
        value_text = f"{dual.group('obs_low')}-{dual.group('obs_high')}"
        unit = dual.group("unit")
        return ExtractedResult(
            test_name=_clean_analyte_name(dual.group("name")),
            value=value_text,
            unit=unit,
            reference_range=f"{dual.group('ref_low')} - {dual.group('ref_high')}",
            reference_low=ref_low,
            reference_high=ref_high,
            interpretation=_infer_interpretation(None, ref_low, ref_high, observed_low=obs_low, observed_high=obs_high),
            section=section,
            result_type="observed_range",
            ocr_source_text=joined,
            confidence=conf,
            parse_status=(
                "needs_review" if recovery_status == "ambiguous" else "accepted"
            ),
            ocr_recovery_status=recovery_status,
            ocr_alternatives=recovery_alternatives,
            row_id=_row_id(dual.group("name"), value_text, unit),
            source_line_indexes=indexes,
        )

    analyte_parts: list[str] = []
    value: str | None = None
    unit: str | None = None
    pending_unit: str | None = None
    qualitative: str | None = None
    observed_range: str | None = None
    obs_low: float | None = None
    obs_high: float | None = None
    flag_hint: str | None = None
    scalar_value = False
    used_alternative_value = False
    collected_ranges: list[tuple[str, str | None, float | None, float | None, int | None]] = []
    unused_range_indexes: list[int] = []

    for t, line in pieces:
        tn = _norm(t)

        if _is_section(t) or _is_method_noise(t):
            continue
        if tn in COLUMN_HEADERS or tn in NOISE_EXACT:
            continue
        compact = tn.replace(" ", "")
        if compact in UNIT_ALIASES and UNIT_ALIASES[compact] is None:
            continue
        if _unit_key(t) in UNIT_ALIASES and UNIT_ALIASES[_unit_key(t)] is None:
            continue

        ref_candidate, range_unit, low, high = _split_range_and_unit(t)
        if ref_candidate is not None:
            if value is None and analyte_parts and not collected_ranges:
                # Only treat an interval as an observed microscopy count when
                # there is microscopy evidence. Otherwise it is a normal range.
                likely_observed = _has_microscopy_cue(
                    analyte_parts=analyte_parts,
                    section=section,
                    range_unit=range_unit,
                ) and (
                    low is not None
                    and high is not None
                    and low >= 0
                    and high <= 30
                    and (high - low) <= 20
                )
                if likely_observed:
                    observed_range = ref_candidate.replace(" - ", "-")
                    obs_low, obs_high = low, high
                    value = observed_range
                    if range_unit:
                        unit = range_unit
                else:
                    collected_ranges.append(
                        (ref_candidate, range_unit, low, high, line.index)
                    )
            else:
                collected_ranges.append((ref_candidate, range_unit, low, high, line.index))
            if range_unit and not unit:
                unit = range_unit
            continue

        flagged = _parse_flagged_value(t)
        if flagged and value is None:
            value, hint = flagged
            value = _fix_ocr_number(value)
            scalar_value = True
            if hint:
                flag_hint = hint
            if observed_range:
                collected_ranges.append(
                    (observed_range.replace("-", " - "), None, obs_low, obs_high, None)
                )
                observed_range = None
                obs_low = obs_high = None
            if pending_unit and not unit:
                unit = pending_unit
                pending_unit = None
            continue
        if flagged and value is not None and observed_range and not scalar_value:
            collected_ranges.append(
                (observed_range.replace("-", " - "), None, obs_low, obs_high, None)
            )
            observed_range = None
            obs_low = obs_high = None
            value, hint = flagged
            value = _fix_ocr_number(value)
            scalar_value = True
            if hint:
                flag_hint = hint
            continue

        salvaged, from_alternative = _salvage_value_from_line(line)
        if salvaged is not None and value is None:
            value = salvaged
            scalar_value = True
            used_alternative_value = used_alternative_value or from_alternative
            if observed_range:
                collected_ranges.append(
                    (observed_range.replace("-", " - "), None, obs_low, obs_high, None)
                )
                observed_range = None
                obs_low = obs_high = None
            if pending_unit and not unit:
                unit = pending_unit
                pending_unit = None
            continue

        comp = COMPARATOR_RE.match(t)
        if comp and value is None:
            value = f"{comp.group('comp')}{_fix_ocr_number(comp.group('value'))}"
            scalar_value = True
            if pending_unit and not unit:
                unit = pending_unit
                pending_unit = None
            continue
        if comp and value is not None:
            bound_value = _fix_ocr_number(comp.group("value"))
            symbol = comp.group("comp")
            upper = symbol.startswith("<")
            collected_ranges.append(
                (
                    f"{symbol} {bound_value}",
                    None,
                    None if upper else _parse_float(bound_value),
                    _parse_float(bound_value) if upper else None,
                    line.index,
                )
            )
            continue

        bound_candidate, bound_unit, bound_low, bound_high = _split_reference_bound(t)
        if bound_candidate is not None and value is not None:
            collected_ranges.append(
                (bound_candidate, bound_unit, bound_low, bound_high, line.index)
            )
            continue

        normalized_unit = _normalize_unit(t)
        if normalized_unit is not None:
            if value is not None or qualitative is not None:
                unit = normalized_unit
            else:
                pending_unit = normalized_unit
            continue

        if _is_qualitative(t):
            if value is None:
                qualitative = t
                value = t
                if pending_unit and not unit and _is_microscopy_unit(pending_unit):
                    unit = pending_unit
                    pending_unit = None
            elif not scalar_value:
                collected_ranges.append((t, None, None, None, line.index))
            else:
                collected_ranges.append((t, None, None, None, line.index))
            continue

        if _looks_like_analyte(t) and value is None and qualitative is None:
            analyte_parts.append(t.strip(" :,-"))
            continue

        # Only accept real units — never stash method crumbs into unit
        if analyte_parts and value is not None and unit is None and 1 <= len(t) <= 24:
            maybe = _normalize_unit(t)
            if maybe:
                unit = maybe

    if pending_unit and not unit and (value is not None or qualitative is not None):
        unit = pending_unit
    name = _clean_analyte_name(" ".join(analyte_parts))
    # Strip leading method crumbs that leaked into the name
    name = re.sub(r"^(?:method|melhod|metiod)\s*:\s*", "", name, flags=re.IGNORECASE).strip()

    if not name:
        inline = INLINE_SCALAR.match(joined)
        if inline and _looks_like_analyte(inline.group("name")):
            name = _clean_analyte_name(inline.group("name"))
            if value is None:
                value = inline.group("value")
                scalar_value = True
            if inline.group("flag"):
                flag_hint = "high" if inline.group("flag").upper().startswith("H") else "low"
            if unit is None and inline.group("unit"):
                unit = _normalize_unit(inline.group("unit"))
            if inline.group("ref_low"):
                collected_ranges.append(
                    (
                        f"{inline.group('ref_low')} - {inline.group('ref_high')}",
                        None,
                        _parse_float(inline.group("ref_low")),
                        _parse_float(inline.group("ref_high")),
                        None,
                    )
                )

    if not name:
        return None

    ref_text: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    chosen_range_index: int | None = None

    if scalar_value and collected_ranges:
        # Numeric refs only for best-fit; qualitative refs take last non-numeric
        numeric_ranges = [
            r for r in collected_ranges if r[2] is not None or r[3] is not None
        ]
        qualitative_refs = [
            r for r in collected_ranges if r[2] is None and r[3] is None
        ]
        chosen = _choose_reference_range(value, numeric_ranges) if numeric_ranges else None
        if chosen is None and qualitative_refs:
            chosen = qualitative_refs[-1]
        if chosen:
            ref_text, range_unit, ref_low, ref_high, chosen_range_index = chosen
            if range_unit and not unit:
                unit = range_unit
            for r in collected_ranges:
                if r[4] is not None and r[4] != chosen_range_index:
                    unused_range_indexes.append(r[4])
    elif observed_range and collected_ranges:
        # Observed microscopy count + explicit reference. Prefer numeric refs;
        # never promote NIL/NEGATIVE into the normal-range field.
        numeric_refs = [
            r for r in collected_ranges if r[2] is not None or r[3] is not None
        ]
        chosen = numeric_refs[-1] if numeric_refs else None
        if chosen:
            ref_text, range_unit, ref_low, ref_high, chosen_range_index = chosen
            if range_unit and not unit:
                unit = range_unit
            for r in collected_ranges:
                if r[4] is not None and r[4] != chosen_range_index:
                    unused_range_indexes.append(r[4])
        else:
            for r in collected_ranges:
                if r[4] is not None:
                    unused_range_indexes.append(r[4])
    elif not scalar_value and not observed_range and collected_ranges and qualitative:
        numeric_refs = [
            r for r in collected_ranges if r[2] is not None or r[3] is not None
        ]
        if numeric_refs:
            ref_text, range_unit, ref_low, ref_high, chosen_range_index = numeric_refs[0]
            if range_unit and not unit:
                unit = range_unit
        elif not _is_qualitative(collected_ranges[-1][0]):
            ref_text = collected_ranges[-1][0]
    elif not scalar_value and observed_range and not collected_ranges:
        # Keep observed microscopy / dual-range style value
        pass
    elif not scalar_value and not observed_range and collected_ranges and not qualitative:
        # Name + range(s) only with no scalar: treat as observed microscopy only
        # when cues exist; otherwise keep as normal-range incomplete row.
        first = collected_ranges[0]
        if _has_microscopy_cue(
            analyte_parts=analyte_parts,
            section=section,
            range_unit=first[1],
        ) and (
            first[2] is not None
            and first[3] is not None
            and first[2] >= 0
            and first[3] <= 30
            and (first[3] - first[2]) <= 20
        ):
            observed_range = first[0].replace(" - ", "-")
            obs_low, obs_high = first[2], first[3]
            value = observed_range
            if len(collected_ranges) > 1:
                ref_text, range_unit, ref_low, ref_high, chosen_range_index = collected_ranges[-1]
                if range_unit and not unit:
                    unit = range_unit
        else:
            # Likely a reference interval with missing result value
            ref_text, range_unit, ref_low, ref_high, chosen_range_index = collected_ranges[-1]
            if range_unit and not unit:
                unit = range_unit
            if ref_text is None:
                ref_text = first[0]
                ref_low, ref_high = first[2], first[3]
    kept_indexes = [idx for idx in indexes if idx not in unused_range_indexes]

    if value is None and qualitative is None:
        if _looks_like_analyte(name) and not _is_section(name):
            return ExtractedResult(
                test_name=name,
                value=None,
                unit=unit,
                reference_range=ref_text,
                reference_low=ref_low,
                reference_high=ref_high,
                section=section,
                result_type="incomplete",
                ocr_source_text=joined,
                confidence=conf,
                parse_status="needs_review",
                row_id=_row_id(name, None, unit),
                source_line_indexes=kept_indexes,
            )
        return None

    display_value: str | float | None = qualitative or value
    if qualitative is None and observed_range is None and scalar_value:
        display_value = _display_number(value)
    elif qualitative is None and observed_range:
        display_value = observed_range

    interpretation = _infer_interpretation(
        display_value if qualitative is None else None,
        ref_low,
        ref_high,
        observed_low=obs_low,
        observed_high=obs_high,
    )
    if interpretation is None and flag_hint:
        interpretation = flag_hint

    result_type = (
        "qualitative"
        if qualitative
        else ("observed_range" if observed_range and not scalar_value else "quantitative")
    )
    status: Literal["accepted", "needs_review"] = (
        "accepted"
        if (
            display_value is not None
            and recovery_status != "ambiguous"
            and not used_alternative_value
        )
        else "needs_review"
    )

    return ExtractedResult(
        test_name=name,
        value=display_value,
        unit=unit,
        reference_range=ref_text,
        reference_low=ref_low,
        reference_high=ref_high,
        interpretation=interpretation,
        section=section,
        result_type=result_type,
        ocr_source_text=joined,
        confidence=conf,
        parse_status=status,
        ocr_recovery_status=recovery_status,
        ocr_alternatives=recovery_alternatives,
        row_id=_row_id(name, display_value, unit),
        source_line_indexes=kept_indexes,
    )


def _attach_orphan_ranges(
    results: list[ExtractedResult],
    classified: list[ClassifiedLine],
    used_indexes: set[int],
    y_tolerance: float = 70.0,
) -> None:
    """Attach unused right-column range fragments to nearby results missing reference_range."""
    y_by_index = {c.index: (c.y_min + c.y_max) / 2 for c in classified}
    x_by_index = {c.index: c.x_min for c in classified}

    orphans: list[tuple[ClassifiedLine, str, float | None, float | None]] = []
    for item in classified:
        if item.index in used_indexes:
            continue
        if item.line_class in {"header", "footer", "metadata", "noise", "section_header"}:
            continue
        ref_text, _, low, high = _split_range_and_unit(item.text)
        if ref_text is None:
            ref_text, _, low, high = _split_reference_bound(item.text)
        if ref_text is None:
            continue
        orphans.append((item, ref_text, low, high))

    if not orphans:
        return

    # Score every (orphan, row) pair; assign greedily by best unique distance.
    by_line_index = {c.index: c for c in classified}
    candidates: list[tuple[float, int, int]] = []  # dist, orphan_i, row_i
    for oi, (item, ref_text, low, high) in enumerate(orphans):
        item_y = y_by_index[item.index]
        for ri, row in enumerate(results):
            if row.reference_range:
                continue
            src = row.source_line_indexes
            row_ys = [y_by_index[idx] for idx in src if idx in y_by_index]
            row_xs = [x_by_index[idx] for idx in src if idx in x_by_index]
            if not row_ys:
                continue
            row_y = min(row_ys)
            value_xs = []
            for idx in src:
                line = by_line_index.get(idx)
                if line is None:
                    continue
                token = line.text.strip()
                if (
                    VALUE_RE.match(token)
                    or _parse_flagged_value(token) is not None
                    or _is_qualitative(token)
                    or _salvage_numeric_token(token) is not None
                ):
                    value_xs.append(line.x_min)
            anchor_x = max(value_xs) if value_xs else (min(row_xs) if row_xs else 0.0)
            dist = abs(row_y - item_y)
            if dist > y_tolerance:
                continue
            # Soft preference: ranges usually sit to the right of the value.
            penalty = 0.0 if item.x_min >= anchor_x - 20 else 12.0
            candidates.append((dist + penalty, oi, ri))

    candidates.sort()
    used_orphans: set[int] = set()
    used_rows: set[int] = set()
    for dist, oi, ri in candidates:
        if oi in used_orphans or ri in used_rows:
            continue
        item, ref_text, low, high = orphans[oi]
        row = results[ri]
        row.reference_range = ref_text
        row.reference_low = low
        row.reference_high = high
        row.interpretation = _infer_interpretation(row.value, low, high) or row.interpretation
        row.source_line_indexes = list(dict.fromkeys([*row.source_line_indexes, item.index]))
        used_indexes.add(item.index)
        used_orphans.add(oi)
        used_rows.add(ri)

def _attach_orphan_units(
    results: list[ExtractedResult],
    classified: list[ClassifiedLine],
    used_indexes: set[int],
    y_tolerance: float = 48.0,
) -> None:
    """Attach unused unit-column tokens (often slightly below the value) to nearby rows."""
    y_by_index = {c.index: (c.y_min + c.y_max) / 2 for c in classified}
    x_by_index = {c.index: c.x_min for c in classified}

    orphans: list[tuple[ClassifiedLine, str]] = []
    for item in classified:
        if item.index in used_indexes:
            continue
        if item.line_class in {"header", "footer", "metadata", "noise", "section_header"}:
            continue
        unit = _normalize_unit(item.text)
        if not unit:
            continue
        orphans.append((item, unit))

    if not orphans:
        return

    candidates: list[tuple[float, int, int]] = []
    for oi, (item, unit) in enumerate(orphans):
        item_y = y_by_index[item.index]
        for ri, row in enumerate(results):
            if row.unit:
                continue
            if row.result_type == "qualitative" and not _is_microscopy_unit(unit):
                # Don't force chemistry units onto colour/appearance rows
                if unit not in {"%", "/HPF", "/LPF"}:
                    continue
            src = row.source_line_indexes
            row_ys = [y_by_index[idx] for idx in src if idx in y_by_index]
            row_xs = [x_by_index[idx] for idx in src if idx in x_by_index]
            if not row_ys:
                continue
            row_y = min(row_ys)
            row_xmax = max(row_xs) if row_xs else 0.0
            # Unit column is typically right of the value
            if item.x_min + 10 < row_xmax and item.x_min < 700:
                # still allow if clearly far right
                pass
            dist = abs(row_y - item_y)
            # Prefer units slightly below or aligned with the row
            if dist <= y_tolerance:
                # Soft preference for right-side units
                penalty = 0.0 if item.x_min >= row_xmax - 30 else 8.0
                candidates.append((dist + penalty, oi, ri))

    candidates.sort()
    used_orphans: set[int] = set()
    used_rows: set[int] = set()
    for _score, oi, ri in candidates:
        if oi in used_orphans or ri in used_rows:
            continue
        item, unit = orphans[oi]
        row = results[ri]
        row.unit = unit
        row.source_line_indexes = list(dict.fromkeys([*row.source_line_indexes, item.index]))
        used_indexes.add(item.index)
        used_orphans.add(oi)
        used_rows.add(ri)


def _rescue_value_range_rows(
    results: list[ExtractedResult],
    classified: list[ClassifiedLine],
    used_indexes: set[int],
    rejected_indexes: dict[int, str],
    y_tolerance: float = 26.0,
) -> None:
    """Emit rows for leftovers that still show an observed value plus a range.

    A complete result is detectable evidence, so it belongs in the report rather
    than only in the review queue. These rows are always ``needs_review`` because
    their label was never confidently matched to an analyte column.
    """
    leftovers = [
        item
        for item in classified
        if item.index not in used_indexes
        and item.index not in rejected_indexes
        and item.text.strip()
        and item.line_class
        not in {"header", "footer", "metadata", "noise", "section_header", "lab_result"}
    ]
    if not leftovers:
        return

    leftovers.sort(key=lambda item: ((item.y_min + item.y_max) / 2, item.x_min))
    groups: list[list[ClassifiedLine]] = []
    for item in leftovers:
        center = (item.y_min + item.y_max) / 2
        if groups and abs(_band_y(groups[-1]) - center) <= y_tolerance:
            groups[-1].append(item)
        else:
            groups.append([item])

    # Name-only leftovers can be adopted by a value+range group whose label
    # drifted into its own band.
    name_only_groups: dict[int, list[ClassifiedLine]] = {}
    for position, group in enumerate(groups):
        if all(_looks_like_analyte(item.text) for item in group):
            name_only_groups[position] = group
    claimed_names: set[int] = set()

    for position, group in enumerate(groups):
        if position in name_only_groups:
            continue
        group.sort(key=lambda item: item.x_min)
        value_item: ClassifiedLine | None = None
        value_text: str | None = None
        flag_hint: str | None = None
        range_item: ClassifiedLine | None = None
        reference: tuple[str, float | None, float | None] | None = None
        unit: str | None = None
        name_parts: list[ClassifiedLine] = []

        for item in group:
            token = item.text.strip()
            ref_text, range_unit, low, high = _split_range_and_unit(token)
            if ref_text is None:
                ref_text, range_unit, low, high = _split_reference_bound(token)
            if ref_text is not None and reference is None:
                range_item = item
                reference = (ref_text, low, high)
                if range_unit and unit is None:
                    unit = range_unit
                continue

            flagged = _parse_flagged_value(token)
            if flagged and value_text is None:
                value_text, flag_hint = flagged
                value_item = item
                continue

            salvaged = _salvage_numeric_token(token, allow_lookalike=False)
            if salvaged is not None and value_text is None:
                value_text = salvaged
                value_item = item
                continue

            normalized_unit = _normalize_unit(token)
            if normalized_unit is not None:
                if unit is None:
                    unit = normalized_unit
                continue

            if _looks_like_analyte(token):
                name_parts.append(item)

        if value_text is None or reference is None or value_item is None:
            continue

        if not name_parts:
            group_y = _band_y(group)
            nearest = min(
                (
                    candidate_position
                    for candidate_position in name_only_groups
                    if candidate_position not in claimed_names
                ),
                key=lambda candidate_position: abs(
                    _band_y(name_only_groups[candidate_position]) - group_y
                ),
                default=None,
            )
            if nearest is None:
                continue
            claimed_names.add(nearest)
            name_parts = list(name_only_groups[nearest])

        row_items = [*name_parts, *group]
        name = _clean_analyte_name(" ".join(item.text for item in name_parts))
        candidate = ExtractedResult(
            test_name=name,
            value=_display_number(value_text),
            unit=unit,
            reference_range=reference[0],
            reference_low=reference[1],
            reference_high=reference[2],
            section=None,
            result_type="quantitative",
            ocr_source_text=" ".join(item.text for item in row_items),
            confidence=sum(item.confidence for item in row_items)
            / max(len(row_items), 1),
            parse_status="needs_review",
            source_line_indexes=[item.index for item in row_items],
        )
        candidate.interpretation = (
            _infer_interpretation(candidate.value, reference[1], reference[2]) or flag_hint
        )
        valid, _reason = _is_valid_result_row(candidate)
        if not valid:
            continue

        candidate.row_id = _row_id(name, candidate.value, unit)
        results.append(candidate)
        used_indexes.update(candidate.source_line_indexes)
        if range_item is not None:
            used_indexes.add(range_item.index)


def extract_complete_report(source_file: str, ocr_lines: list[OCRLine]) -> dict[str, Any]:
    classified = classify_lines(ocr_lines)
    bands = _group_into_bands(classified)

    results: list[ExtractedResult] = []
    current_section: str | None = None
    used_indexes: set[int] = set()
    rejected_indexes: dict[int, str] = {}

    for band in bands:
        # Update section if band is a section header
        if len(band) == 1 and band[0].line_class == "section_header":
            current_section = band[0].text.strip()
            continue
        if band and all(b.line_class == "section_header" for b in band):
            current_section = " ".join(b.text for b in band).strip()
            continue

        parsed = _parse_band(band, current_section)
        if parsed is None:
            continue
        # Preserve a named row when OCR found its normal range but missed the
        # observed value. It is explicit review data, never an invented value.
        if parsed.value is None and not parsed.reference_range:
            continue
        valid, rejection_reason = _is_valid_result_row(parsed)
        if not valid:
            for idx in parsed.source_line_indexes:
                rejected_indexes[idx] = rejection_reason or "non_lab_content"
            continue
        results.append(parsed)
        used_indexes.update(parsed.source_line_indexes)

    # Rejected metadata must not masquerade as new rows, but pure range/unit
    # tokens from rejected bands remain available for orphan attachment
    # (e.g. Ferritin value kept while ``30 - 350`` was rejected with method noise).
    for idx, _reason in rejected_indexes.items():
        item = next((line for line in classified if line.index == idx), None)
        if item is None:
            used_indexes.add(idx)
            continue
        if _split_range_and_unit(item.text)[0] is not None:
            continue
        if _split_reference_bound(item.text)[0] is not None:
            continue
        if _normalize_unit(item.text) is not None:
            continue
        used_indexes.add(idx)
    _attach_orphan_ranges(results, classified, used_indexes)
    _attach_orphan_units(results, classified, used_indexes)
    used_indexes.difference_update(rejected_indexes)

    # Any leftover that still shows value + reference range is a real result.
    _rescue_value_range_rows(results, classified, used_indexes, rejected_indexes)
    results.sort(
        key=lambda row: min(
            (
                line.y_min
                for line in classified
                if line.index in row.source_line_indexes
            ),
            default=0.0,
        )
    )

    # Differential count rows often omit repeating "%" on every line
    for row in results:
        if row.unit:
            continue
        section = (row.section or "").lower()
        name = row.test_name.lower()
        if "differential" in section or name in {
            "neutrophils",
            "lymphocytes",
            "eosinophils",
            "monocytes",
            "basophils",
        }:
            numeric = _parse_float(row.value)
            if numeric is not None and 0 <= numeric <= 100:
                row.unit = "%"

    # Mark classified lines consumed by results
    index_to_class = {c.index: c for c in classified}
    for idx, reason in rejected_indexes.items():
        if idx in index_to_class:
            index_to_class[idx].line_class = "noise"
            index_to_class[idx].reason = reason
    for row in results:
        for idx in row.source_line_indexes:
            if idx in index_to_class:
                index_to_class[idx].line_class = "lab_result"
                index_to_class[idx].reason = "extracted"

    # Build review queue for unknown lines that look like analytes but were not extracted
    review_lines: list[dict[str, Any]] = []
    for item in classified:
        if item.index in used_indexes or item.index in rejected_indexes:
            continue
        if item.line_class in {"header", "footer", "metadata", "noise", "section_header", "lab_result"}:
            continue
        if _looks_like_analyte(item.text) or VALUE_RE.match(item.text.strip()) or _is_qualitative(item.text):
            review_lines.append(
                {
                    "text": item.text,
                    "confidence": item.confidence,
                    "line_index": item.index,
                    "reason": "unmerged_candidate",
                }
            )
            item.line_class = "unknown"
            item.reason = "unmerged_candidate"

    summary = {
        "total": len(results),
        "normal": sum(1 for r in results if r.interpretation == "normal"),
        "high": sum(1 for r in results if r.interpretation == "high"),
        "low": sum(1 for r in results if r.interpretation == "low"),
        "unclassified": sum(1 for r in results if r.interpretation is None),
        "needs_review": sum(1 for r in results if r.parse_status == "needs_review"),
        "ocr_recovered": sum(
            1 for r in results if r.ocr_recovery_status == "consensus_recovered"
        ),
        "ocr_ambiguous": sum(
            1 for r in results if r.ocr_recovery_status == "ambiguous"
        ),
        "review_lines": len(review_lines),
        "ocr_lines": len(ocr_lines),
        "coverage": round(len(used_indexes) / len(ocr_lines), 4) if ocr_lines else 0.0,
    }

    rows = [
        {
            "row_id": r.row_id,
            "test_name": r.test_name,
            "value": r.value,
            "unit": r.unit,
            "reference_range": r.reference_range,
            "reference_low": r.reference_low,
            "reference_high": r.reference_high,
            "interpretation": r.interpretation,
            "section": r.section or "General",
            "result_type": r.result_type,
            "ocr_source_text": r.ocr_source_text,
            "confidence": round(r.confidence, 4),
            "parse_status": r.parse_status,
            "ocr_recovery_status": r.ocr_recovery_status,
            "ocr_alternatives": r.ocr_alternatives,
        }
        for r in results
    ]

    sections: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        sections.setdefault(row["section"], []).append(row)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_file": source_file,
        "engine": "complete_extractor_v7",
        "summary": summary,
        "rows": rows,
        "sections": sections,
        "review_lines": review_lines,
        "line_classes": [
            {
                "index": c.index,
                "text": c.text,
                "class": c.line_class,
                "reason": c.reason,
                "confidence": round(c.confidence, 4),
                "recovery_status": c.recovery_status,
                "alternatives": c.alternatives,
            }
            for c in classified
        ],
        "ocr_text": {
            "line_count": len(ocr_lines),
            "lines": [line.text for line in ocr_lines],
            "text": "\n".join(line.text for line in ocr_lines),
        },
    }
