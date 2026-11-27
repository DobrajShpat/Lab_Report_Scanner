from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import settings
from core.utils import ensure_dir, write_json
from pipeline.complete_extractor import extract_complete_report
from pipeline.s2_preprocess import prepare_image_paths
from pipeline.s3_ocr import ScoreDrivenOCR
from pipeline.s6b_digital_report import build_digital_report


class PipelineManager:
    def __init__(self) -> None:
        self.ocr = ScoreDrivenOCR()

    def process(self, report_id: str, source_path: Path) -> dict[str, Any]:
        output_dir = ensure_dir(settings.outputs_dir / report_id)
        stage_status: list[dict[str, str]] = []

        def mark(stage: str, state: str = "done") -> None:
            stage_status.append({"stage": stage, "status": state})

        mark("Ingestion")
        image_paths = prepare_image_paths(str(source_path))
        mark("Preprocess")

        ocr_doc = self.ocr.extract(image_paths[0])
        ocr_payload = {
            "source_file": source_path.name,
            "selected_variant": ocr_doc.best_variant,
            "lines": [line.model_dump() for line in ocr_doc.lines],
            "raw_blocks": ocr_doc.raw_blocks,
            "variant_diagnostics": ocr_doc.variant_diagnostics,
            "recovery_summary": ocr_doc.recovery_summary,
        }
        write_json(output_dir / "ocr.json", ocr_payload)
        mark("OCR Engine")

        digital_report = build_digital_report(source_path, ocr_doc.lines)
        write_json(output_dir / "digital_report.json", digital_report)
        mark("Digital Reproduction")

        clinical_report = extract_complete_report(source_path.name, ocr_doc.lines)
        write_json(output_dir / "clinical_report.json", clinical_report)
        write_json(
            output_dir / "ocr_text.json",
            {
                "generated_at": clinical_report["generated_at"],
                "source": "rapidocr",
                "description": "Full OCR ground truth — every detected line.",
                "line_count": clinical_report["ocr_text"]["line_count"],
                "lines": clinical_report["ocr_text"]["lines"],
                "text": clinical_report["ocr_text"]["text"],
            },
        )
        mark("Complete Extraction")

        summary_metrics = {
            "total_ocr_lines": len(ocr_doc.lines),
            "selected_variant": ocr_doc.best_variant,
            "lab_results": clinical_report["summary"]["total"],
            "normal": clinical_report["summary"]["normal"],
            "high": clinical_report["summary"]["high"],
            "low": clinical_report["summary"]["low"],
            "coverage": clinical_report["summary"]["coverage"],
            "ocr_recovery": ocr_doc.recovery_summary,
            "engine": clinical_report["engine"],
        }
        write_json(output_dir / "evaluation.json", summary_metrics)

        return {
            "report_id": report_id,
            "stage_status": stage_status,
            "ocr": ocr_payload,
            "digital_report": digital_report,
            "clinical_report": clinical_report,
            "summary_metrics": summary_metrics,
        }
