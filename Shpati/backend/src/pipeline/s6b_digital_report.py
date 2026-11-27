from __future__ import annotations

from pathlib import Path

from PIL import Image

from pipeline.models import OCRLine


def build_digital_report(source_path: Path, lines: list[OCRLine]) -> dict:
    with Image.open(source_path) as image:
        page_width, page_height = image.size

    ordered = sorted(lines, key=lambda line: (line.y_min, line.x_min))
    return {
        "page_width": page_width,
        "page_height": page_height,
        "line_count": len(ordered),
        "lines": [line.model_dump() for line in ordered],
    }
