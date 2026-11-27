from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from core.config import settings
from core.utils import slugify


def ingest_upload(filename: str, content: bytes) -> tuple[str, Path]:
    suffix = Path(filename).suffix.lower()
    if suffix not in settings.allowed_extensions:
        raise ValueError(f"Unsupported file type: {suffix}")

    base = slugify(Path(filename).stem)
    stored_name = f"{base}-{uuid4().hex[:8]}{suffix}"
    target = settings.uploaded_reports_dir / stored_name
    target.write_bytes(content)
    report_id = slugify(target.stem)
    return report_id, target
