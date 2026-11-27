from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Any

from core.config import settings
from core.utils import read_json, slugify, write_json
from pipeline.pipeline_manager import PipelineManager
from pipeline.s1_ingestion import ingest_upload


class ReportStore:
    def list_reports(self) -> dict[str, Any]:
        reports = []
        for path in sorted(settings.uploaded_reports_dir.glob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            report_id = slugify(path.stem)
            reports.append(self._summary_for(report_id, path))

        analyzed = [r for r in reports if r["has_ocr"]]
        line_counts = [r["ocr_lines"] for r in analyzed if r["ocr_lines"]]

        return {
            "reports": reports,
            "total_reports": len(reports),
            "analyzed_reports": len(analyzed),
            "pending_reports": len([r for r in reports if not r["has_ocr"]]),
            "total_ocr_lines": sum(line_counts),
        }

    def get_detail(self, report_id: str) -> dict[str, Any]:
        source = self._find_source(report_id)
        output_dir = settings.outputs_dir / report_id
        detail: dict[str, Any] = {
            "summary": self._summary_for(report_id, source),
            "assets": {
                "original_image_url": f"/media/uploads/{source.name}",
            },
        }
        for key, filename in (
            ("ocr", "ocr.json"),
            ("digital_report", "digital_report.json"),
            ("clinical_report", "clinical_report.json"),
            ("structured_report", "structured.json"),
            ("ocr_text", "ocr_text.json"),
        ):
            path = output_dir / filename
            if path.exists():
                detail[key] = read_json(path)
        return detail

    def save_and_process(self, filename: str, content: bytes) -> dict[str, Any]:
        report_id, path = ingest_upload(filename, content)
        result = PipelineManager().process(report_id, path)
        write_json(settings.outputs_dir / report_id / "evaluation.json", result["summary_metrics"])
        return {**result, "summary": self._summary_for(report_id, path)}

    def process_existing(self, report_id: str) -> dict[str, Any]:
        source = self._find_source(report_id)
        result = PipelineManager().process(report_id, source)
        write_json(settings.outputs_dir / report_id / "evaluation.json", result["summary_metrics"])
        return {**result, "summary": self._summary_for(report_id, source)}

    def delete_report(self, report_id: str) -> None:
        source = self._find_source(report_id)
        source.unlink(missing_ok=True)
        output_dir = settings.outputs_dir / report_id
        if output_dir.exists():
            shutil.rmtree(output_dir)

    def artifact_path(self, report_id: str, artifact: str) -> tuple[Path, str, str]:
        source = self._find_source(report_id)
        if artifact == "original":
            content_type, _ = mimetypes.guess_type(source.name)
            return source, source.name, content_type or "application/octet-stream"
        mapping = {
            "ocr": "ocr.json",
            "digital": "digital_report.json",
            "clinical": "clinical_report.json",
            "structured": "structured.json",
            "evaluation": "evaluation.json",
        }
        if artifact not in mapping:
            raise FileNotFoundError(artifact)
        path = settings.outputs_dir / report_id / mapping[artifact]
        if not path.exists():
            raise FileNotFoundError(artifact)
        return path, path.name, "application/json"

    def _find_source(self, report_id: str) -> Path:
        for path in settings.uploaded_reports_dir.iterdir():
            if path.is_file() and slugify(path.stem) == report_id:
                return path
        raise FileNotFoundError(report_id)

    def _summary_for(self, report_id: str, source: Path) -> dict[str, Any]:
        ocr_path = settings.outputs_dir / report_id / "ocr.json"
        clinical_path = settings.outputs_dir / report_id / "clinical_report.json"
        if not ocr_path.exists():
            return {
                "id": report_id,
                "source_file": source.name,
                "title": source.stem,
                "status": "pending",
                "has_ocr": False,
                "ocr_lines": 0,
                "lab_results": 0,
                "original_image_url": f"/media/uploads/{source.name}",
            }

        ocr = read_json(ocr_path)
        lines = ocr.get("lines", [])
        clinical = read_json(clinical_path) if clinical_path.exists() else None
        summary = (clinical or {}).get("summary") or {}
        return {
            "id": report_id,
            "source_file": source.name,
            "title": source.stem,
            "status": "ready",
            "has_ocr": True,
            "ocr_lines": len(lines),
            "lab_results": summary.get("total", 0),
            "normal": summary.get("normal", 0),
            "high": summary.get("high", 0),
            "low": summary.get("low", 0),
            "selected_variant": ocr.get("selected_variant"),
            "original_image_url": f"/media/uploads/{source.name}",
        }
