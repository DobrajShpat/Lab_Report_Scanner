from __future__ import annotations

import re
from pathlib import Path

import orjson


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-") or "report"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def write_json(path: Path, payload: object) -> None:
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))


def read_json(path: Path) -> object:
    return orjson.loads(path.read_bytes())


def to_fhir_datetime(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace(" ", "T") if "T" not in value else value
