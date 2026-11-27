from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router
from core.auth_service import AuthService
from core.config import settings

app = FastAPI(title="Shpati OCR", version="1.0.0")


@app.on_event("startup")
def seed_demo_user() -> None:
    AuthService.ensure_demo_user()


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")
app.mount("/media/uploads", StaticFiles(directory=settings.uploaded_reports_dir), name="uploads")


@app.get("/health")
def root_health() -> dict[str, str]:
    return {"status": "ok", "service": "Shpati"}


def main() -> None:
    import uvicorn

    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
