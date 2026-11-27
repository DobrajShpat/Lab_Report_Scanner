from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from rapidocr_onnxruntime import RapidOCR

from pipeline.models import OCRLine
from pipeline.s2_preprocess import generate_variants, load_image


@dataclass
class OCRDocument:
    best_variant: str
    lines: list[OCRLine]
    raw_blocks: list[dict[str, Any]]
    variant_diagnostics: list[dict[str, Any]]
    recovery_summary: dict[str, int]


class ScoreDrivenOCR:
    """Run an OCR variant matrix, then safely fuse corroborated reads."""

    # Everything after deskew shares the deskewed coordinate frame.
    # Never IoU-match these against "original" or digits can attach to the wrong cell.
    DESKEWED_FAMILY = frozenset(
        {
            "deskewed",
            "clahe",
            "adaptive",
            "otsu",
            "morph",
            "sharpened",
            "table_lines_removed",
            "upscaled_clahe",
            "upscaled_table_lines_removed",
        }
    )

    def __init__(self) -> None:
        self._engine = RapidOCR()

    @classmethod
    def _geometry_family(cls, variant_name: str) -> str:
        return "deskewed" if variant_name in cls.DESKEWED_FAMILY else "original"

    def extract(self, image_path: str) -> OCRDocument:
        image = load_image(image_path)
        best_variant = "original"
        best_lines: list[OCRLine] = []
        best_blocks: list[dict[str, Any]] = []
        best_score = -1.0
        best_scale = 1.0
        variant_runs: dict[str, list[OCRLine]] = {}
        diagnostics: list[dict[str, Any]] = []

        for variant in generate_variants(image):
            result, _ = self._engine(variant.image)
            if not result:
                diagnostics.append(
                    {
                        "variant": variant.name,
                        "line_count": 0,
                        "average_confidence": 0.0,
                        "score": 0.0,
                        "geometry_family": self._geometry_family(variant.name),
                    }
                )
                continue
            lines = [
                self._to_line(item, variant.name, variant.coordinate_scale)
                for item in result
            ]
            variant_runs[variant.name] = lines
            average_confidence = sum(line.confidence for line in lines) / max(len(lines), 1)
            score = len(lines) + average_confidence
            diagnostics.append(
                {
                    "variant": variant.name,
                    "line_count": len(lines),
                    "average_confidence": round(average_confidence, 4),
                    "score": round(score, 4),
                    "geometry_family": self._geometry_family(variant.name),
                }
            )
            if score > best_score:
                best_score = score
                best_variant = variant.name
                best_lines = lines
                best_scale = variant.coordinate_scale or 1.0
                best_blocks = [
                    {
                        "text": item[1],
                        "confidence": float(item[2]),
                        "bbox": [
                            [float(point[0]) / best_scale, float(point[1]) / best_scale]
                            for point in item[0]
                        ],
                    }
                    for item in result
                ]

        # Consensus only among variants that share a coordinate frame with the winner.
        compatible_runs = {
            name: lines
            for name, lines in variant_runs.items()
            if self._geometry_family(name) == self._geometry_family(best_variant)
        }
        fused_lines = self._fuse_variant_reads(
            best_variant=best_variant,
            best_lines=best_lines,
            variant_runs=compatible_runs,
        )
        recovery_summary = {
            "consensus_recovered": sum(
                line.recovery_status == "consensus_recovered" for line in fused_lines
            ),
            "ambiguous": sum(
                line.recovery_status == "ambiguous" for line in fused_lines
            ),
            "original": sum(
                line.recovery_status == "original" for line in fused_lines
            ),
        }
        return OCRDocument(
            best_variant=best_variant,
            lines=fused_lines,
            raw_blocks=best_blocks,
            variant_diagnostics=diagnostics,
            recovery_summary=recovery_summary,
        )

    @staticmethod
    def _to_line(
        item: list[Any],
        variant_name: str = "unknown",
        coordinate_scale: float = 1.0,
    ) -> OCRLine:
        scale = coordinate_scale or 1.0
        bbox = [
            [float(point[0]) / scale, float(point[1]) / scale]
            for point in item[0]
        ]
        xs = [point[0] for point in bbox]
        ys = [point[1] for point in bbox]
        return OCRLine(
            text=item[1],
            confidence=float(item[2]),
            bbox=bbox,
            x_min=min(xs),
            y_min=min(ys),
            x_max=max(xs),
            y_max=max(ys),
            source_variants=[variant_name],
        )

    @staticmethod
    def _text_key(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

    @staticmethod
    def _numeric_signature(text: str) -> str:
        return "".join(re.findall(r"[0-9.,<>-]+", text.replace(" ", "")))

    @staticmethod
    def _overlap(first: OCRLine, second: OCRLine) -> float:
        left = max(first.x_min, second.x_min)
        top = max(first.y_min, second.y_min)
        right = min(first.x_max, second.x_max)
        bottom = min(first.y_max, second.y_max)
        intersection = max(0.0, right - left) * max(0.0, bottom - top)
        if intersection <= 0:
            return 0.0
        first_area = max(1.0, first.x_max - first.x_min) * max(
            1.0, first.y_max - first.y_min
        )
        second_area = max(1.0, second.x_max - second.x_min) * max(
            1.0, second.y_max - second.y_min
        )
        return intersection / max(first_area + second_area - intersection, 1.0)

    @classmethod
    def _same_region(cls, first: OCRLine, second: OCRLine) -> bool:
        if cls._overlap(first, second) >= 0.35:
            return True
        first_height = max(first.y_max - first.y_min, 8.0)
        second_height = max(second.y_max - second.y_min, 8.0)
        first_center_y = (first.y_min + first.y_max) / 2
        second_center_y = (second.y_min + second.y_max) / 2
        vertical_close = abs(first_center_y - second_center_y) <= max(
            first_height, second_height
        ) * 0.55
        horizontal_overlap = min(first.x_max, second.x_max) - max(
            first.x_min, second.x_min
        )
        min_width = max(
            1.0,
            min(first.x_max - first.x_min, second.x_max - second.x_min),
        )
        return vertical_close and horizontal_overlap / min_width >= 0.6

    @classmethod
    def _fuse_variant_reads(
        cls,
        *,
        best_variant: str,
        best_lines: list[OCRLine],
        variant_runs: dict[str, list[OCRLine]],
    ) -> list[OCRLine]:
        """Use cross-variant agreement to recover missing/partially read text.

        No digit is synthesized. A different read is accepted only when at
        least two preprocessing variants independently agree on it.

        Callers must pass only geometry-compatible variants (same coordinate
        frame as ``best_variant``). Cross-family IoU matching is skipped here
        as a second safety gate.
        """
        best_family = cls._geometry_family(best_variant)
        clusters: list[list[tuple[str, OCRLine]]] = [
            [(best_variant, line)] for line in best_lines
        ]

        for variant_name, lines in variant_runs.items():
            if variant_name == best_variant:
                continue
            if cls._geometry_family(variant_name) != best_family:
                continue
            for line in lines:
                best_cluster: list[tuple[str, OCRLine]] | None = None
                best_overlap = 0.0
                for cluster in clusters:
                    if any(name == variant_name for name, _ in cluster):
                        continue
                    overlap = max(
                        (cls._overlap(line, existing) for _, existing in cluster),
                        default=0.0,
                    )
                    if overlap > best_overlap and any(
                        cls._same_region(line, existing) for _, existing in cluster
                    ):
                        best_overlap = overlap
                        best_cluster = cluster
                if best_cluster is None:
                    clusters.append([(variant_name, line)])
                else:
                    best_cluster.append((variant_name, line))

        fused: list[OCRLine] = []
        for cluster in clusters:
            by_text: dict[str, list[tuple[str, OCRLine]]] = defaultdict(list)
            for variant_name, line in cluster:
                by_text[cls._text_key(line.text)].append((variant_name, line))

            ranked = sorted(
                by_text.values(),
                key=lambda reads: (
                    len({variant for variant, _ in reads}),
                    sum(line.confidence for _, line in reads),
                ),
                reverse=True,
            )
            winner_reads = ranked[0]
            winner_variants = {variant for variant, _ in winner_reads}
            winner = max(winner_reads, key=lambda item: item[1].confidence)[1]
            runner_count = (
                len({variant for variant, _ in ranked[1]}) if len(ranked) > 1 else 0
            )
            has_consensus = len(winner_variants) >= 2 and len(winner_variants) > runner_count

            base = next(
                (line for variant, line in cluster if variant == best_variant),
                None,
            )
            all_variants = sorted({variant for variant, _ in cluster})

            if base is None:
                if not has_consensus or winner.confidence < 0.50:
                    continue
                selected = winner.model_copy(deep=True)
                selected.recovery_status = "consensus_recovered"
            elif has_consensus and cls._text_key(winner.text) != cls._text_key(base.text):
                selected = winner.model_copy(deep=True)
                selected.recovery_status = "consensus_recovered"
            else:
                selected = base.model_copy(deep=True)
                numeric_reads = {
                    cls._numeric_signature(line.text)
                    for _, line in cluster
                    if cls._numeric_signature(line.text)
                }
                if len(numeric_reads) > 1 and not has_consensus:
                    selected.recovery_status = "ambiguous"

            selected.source_variants = all_variants
            selected.alternatives = sorted(
                {
                    line.text.strip()
                    for _, line in cluster
                    if cls._text_key(line.text) != cls._text_key(selected.text)
                }
            )
            fused.append(selected)

        return sorted(fused, key=lambda line: (line.y_min, line.x_min))
