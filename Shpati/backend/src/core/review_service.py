from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.config import settings
from core.utils import read_json, write_json
from pipeline.s10_fhir import build_fhir_bundle
from pipeline.models import NormalizedObservation, PatientMetadata, ProcessingMetrics, ReportMetadata, StructuredReport


class ReviewService:
    ACTIONS = {"approve", "edit_and_approve", "reject", "reset"}

    @classmethod
    def _session_path(cls, session_id: str) -> Path:
        return settings.reviews_dir / f"{session_id}.json"

    @classmethod
    def create_session(cls, report_id: str) -> dict:
        structured_path = settings.outputs_dir / report_id / "structured.json"
        if not structured_path.exists():
            raise FileNotFoundError("Report has no structured output")
        structured = read_json(structured_path)
        observations = structured.get("observations", [])
        review_items = [
            {
                "row_id": row.get("row_id"),
                "machine_row": row,
                "status": "pending",
            }
            for row in observations
            if row.get("acceptance_decision") == "needs_review"
        ]
        session = {
            "session_id": uuid4().hex,
            "report_id": report_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "review_items": review_items,
            "decisions": [],
        }
        write_json(cls._session_path(session["session_id"]), session)
        return session

    @classmethod
    def get_session(cls, session_id: str) -> dict:
        path = cls._session_path(session_id)
        if not path.exists():
            raise FileNotFoundError(session_id)
        return read_json(path)

    @classmethod
    def apply(cls, session_id: str, row_id: str, action: str, corrections: dict | None = None) -> dict:
        if action not in cls.ACTIONS:
            raise ValueError(f"Invalid action: {action}")
        session = cls.get_session(session_id)
        item = next((i for i in session["review_items"] if i["row_id"] == row_id), None)
        if item is None:
            raise ValueError("Row not in review queue")

        if action == "reset":
            item["status"] = "pending"
            item.pop("final_row", None)
        elif action == "reject":
            item["status"] = "rejected"
            item["final_row"] = item["machine_row"]
            item["final_row"]["acceptance_decision"] = "rejected"
        elif action in {"approve", "edit_and_approve"}:
            final = dict(item["machine_row"])
            if action == "edit_and_approve" and corrections:
                final.update(corrections)
            final["acceptance_decision"] = "accepted"
            final["review_provenance"] = {"source": "human_review", "action": action}
            item["status"] = action
            item["final_row"] = final

        write_json(cls._session_path(session_id), session)
        return session

    @classmethod
    def finalize(cls, session_id: str) -> dict:
        session = cls.get_session(session_id)
        report_id = session["report_id"]
        structured_path = settings.outputs_dir / report_id / "structured.json"
        structured_data = read_json(structured_path)
        observations = [NormalizedObservation(**row) for row in structured_data["observations"]]

        approved_by_id = {
            item["row_id"]: item["final_row"]
            for item in session["review_items"]
            if item.get("status") in {"approve", "edit_and_approve"} and item.get("final_row")
        }
        for obs in observations:
            if obs.row_id in approved_by_id:
                approved = approved_by_id[obs.row_id]
                obs.acceptance_decision = "accepted"
                if approved.get("interpretation"):
                    obs.interpretation = approved["interpretation"]
                if approved.get("standardized_value") is not None:
                    obs.standardized_value = approved["standardized_value"]
                if approved.get("standardized_unit"):
                    obs.standardized_unit = approved["standardized_unit"]

        report = StructuredReport(
            report=ReportMetadata(**structured_data["report"]),
            patient=PatientMetadata(**structured_data["patient"]),
            observations=observations,
            unmatched_rows=structured_data.get("unmatched_rows", []),
            raw_text=structured_data.get("raw_text", []),
            metrics=ProcessingMetrics(**structured_data.get("metrics", {})),
        )
        fhir = build_fhir_bundle(report, accepted_only=True)
        write_json(settings.outputs_dir / report_id / "fhir.json", fhir)
        write_json(structured_path, report.model_dump())
        return {"session_id": session_id, "fhir_bundle": fhir, "final_observations": report.model_dump()["observations"]}
