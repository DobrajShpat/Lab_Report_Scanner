from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class PreprocessResult:
    name: str
    image: np.ndarray
    coordinate_scale: float = 1.0


def load_image(path: str) -> np.ndarray:
    image = cv2.imread(path)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return image


def _grayscale(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _deskew(image: np.ndarray) -> np.ndarray:
    gray = _grayscale(image)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    angle = -angle
    if abs(angle) < 0.2:
        return image
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _remove_table_lines(gray: np.ndarray) -> np.ndarray:
    """Remove long table borders while preserving nearby character strokes."""
    binary_inv = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )[1]
    height, width = gray.shape[:2]
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(24, width // 18), 1)
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(24, height // 18))
    )
    horizontal = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, vertical_kernel)
    line_mask = cv2.bitwise_or(horizontal, vertical)
    line_mask = cv2.dilate(line_mask, np.ones((2, 2), np.uint8), iterations=1)
    cleaned = gray.copy()
    cleaned[line_mask > 0] = 255
    return cleaned


def _upscale(image: np.ndarray, factor: float = 2.0) -> np.ndarray:
    return cv2.resize(
        image,
        None,
        fx=factor,
        fy=factor,
        interpolation=cv2.INTER_CUBIC,
    )


def generate_variants(image: np.ndarray) -> list[PreprocessResult]:
    deskewed = _deskew(image)
    gray = _grayscale(deskewed)
    denoised = cv2.fastNlMeansDenoising(gray, None, 18, 7, 21)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(denoised)
    adaptive = cv2.adaptiveThreshold(clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    morph = cv2.morphologyEx(adaptive, cv2.MORPH_OPEN, np.ones((1, 1), np.uint8))
    sharpened = cv2.addWeighted(
        clahe, 1.8, cv2.GaussianBlur(clahe, (0, 0), 1.2), -0.8, 0
    )
    without_table_lines = _remove_table_lines(clahe)
    return [
        PreprocessResult(name="original", image=image),
        PreprocessResult(name="deskewed", image=deskewed),
        PreprocessResult(name="clahe", image=clahe),
        PreprocessResult(name="adaptive", image=adaptive),
        PreprocessResult(name="otsu", image=otsu),
        PreprocessResult(name="morph", image=morph),
        PreprocessResult(name="sharpened", image=sharpened),
        PreprocessResult(name="table_lines_removed", image=without_table_lines),
        PreprocessResult(
            name="upscaled_clahe",
            image=_upscale(clahe),
            coordinate_scale=2.0,
        ),
        PreprocessResult(
            name="upscaled_table_lines_removed",
            image=_upscale(without_table_lines),
            coordinate_scale=2.0,
        ),
    ]


def prepare_image_paths(source_path: str) -> list[str]:
    """Return image paths to OCR (PDF support via first page rasterization when available)."""
    from pathlib import Path

    path = Path(source_path)
    if path.suffix.lower() == ".pdf":
        try:
            from pdf2image import convert_from_path

            pages = convert_from_path(str(path), first_page=1, last_page=1)
            if not pages:
                raise ValueError("PDF produced no pages")
            out = path.parent / f"{path.stem}_page_1.png"
            pages[0].save(out, "PNG")
            return [str(out)]
        except Exception as exc:
            raise ValueError(f"PDF conversion failed: {exc}") from exc
    return [source_path]
