from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.deps import get_current_user
from core.auth_service import AuthService
from core.report_store import ReportStore

router = APIRouter(tags=["shpati"])


@router.post("/auth/register")
def register(payload: dict) -> dict:
    try:
        return AuthService.register(payload["username"], payload["password"])
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="username and password required") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth/login")
def login(payload: dict) -> dict:
    try:
        return AuthService.login(payload["username"], payload["password"])
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="username and password required") from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/auth/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return user


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "Shpati"}


@router.get("/reports")
def list_reports() -> dict:
    return ReportStore().list_reports()


@router.get("/reports/{report_id}")
def report_detail(report_id: str) -> dict:
    try:
        return ReportStore().get_detail(report_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reports/upload")
async def upload_report(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    try:
        return ReportStore().save_and_process(file.filename or "report.png", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reports/{report_id}/process")
def process_report(report_id: str) -> dict:
    try:
        return ReportStore().process_existing(report_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/reports/{report_id}")
def delete_report(report_id: str) -> dict:
    try:
        ReportStore().delete_report(report_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete report: {exc}") from exc
    return {"deleted": True, "report_id": report_id}


@router.get("/reports/{report_id}/download/{artifact}")
def download_artifact(report_id: str, artifact: str) -> FileResponse:
    try:
        path, filename, content_type = ReportStore().artifact_path(report_id, artifact)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type=content_type, filename=filename)
