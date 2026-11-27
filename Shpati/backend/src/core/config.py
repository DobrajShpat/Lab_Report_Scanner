from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    repo_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[3])
    allowed_extensions: set[str] = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".pdf"}
    max_upload_mb: int = 20
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])

    @property
    def storage_root(self) -> Path:
        return self.repo_root / "storage"

    @property
    def uploaded_reports_dir(self) -> Path:
        path = self.storage_root / "uploaded_reports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def outputs_dir(self) -> Path:
        path = self.storage_root / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def reviews_dir(self) -> Path:
        path = self.storage_root / "reviews"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def catalog_path(self) -> Path:
        return Path(__file__).resolve().parents[1] / "data" / "loinc_catalog.json"


settings = Settings()
