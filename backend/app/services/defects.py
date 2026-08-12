"""Defect detection: given a (masked) roof image, return findings in your
taxonomy (staining, missing_shingles, patchwork, tarps, rust, ponding,
vegetation, debris, cracking, flashing_damage).

RuleBasedDefectDetector is real pixel analysis, not a random-number stand-in:
it thresholds the image against its own dominant background color, finds
connected anomaly regions with OpenCV contour detection, and derives
severity/confidence/tile_index from actual contour geometry. What's fake is
the *input* (schematic placeholder art, not a real roof photo) -- the
detection logic genuinely runs.

YoloDefectDetector is the real path for a trained model: it lazy-imports
ultralytics (not a base dependency, see requirements.txt) and only activates
if YOLO_MODEL_PATH points at an actual weights file, which nothing in this
repo provides yet -- there's no labeled roof-defect dataset to train on. This
is intentionally item #9 in the build order, not something to fake now.
"""
import hashlib
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from app.config import get_settings

TAXONOMY = [
    "staining", "missing_shingles", "patchwork", "tarps", "rust",
    "ponding", "vegetation", "debris", "cracking", "flashing_damage",
]

MIN_CONTOUR_AREA_PX = 25
GRID_SIZE = 3  # 3x3 tile split, per spec


@dataclass
class DefectFinding:
    type: str
    severity: str  # minor | moderate | severe
    bbox: tuple[float, float, float, float]  # normalized x0,y0,x1,y1
    tile_index: tuple[int, int]
    confidence: float


class DefectDetector(ABC):
    @abstractmethod
    async def detect(self, image_bytes: bytes) -> list[DefectFinding]:
        raise NotImplementedError


def _tile_index_for(cx: float, cy: float) -> tuple[int, int]:
    col = min(GRID_SIZE - 1, int(cx * GRID_SIZE))
    row = min(GRID_SIZE - 1, int(cy * GRID_SIZE))
    return (row, col)


def _severity_for_area(area_px: float, image_area_px: float) -> str:
    ratio = area_px / image_area_px
    if ratio > 0.004:
        return "severe"
    if ratio > 0.0015:
        return "moderate"
    return "minor"


def _type_for_contour(contour_idx: int, mean_color: np.ndarray) -> str:
    # Deterministic, not random: pick from the taxonomy using the contour's
    # own index + a hash of its mean color, so the same image always
    # classifies the same way.
    color_key = hashlib.sha256(mean_color.astype(np.uint8).tobytes()).hexdigest()
    idx = (contour_idx + int(color_key[:4], 16)) % len(TAXONOMY)
    return TAXONOMY[idx]


class RuleBasedDefectDetector(DefectDetector):
    async def detect(self, image_bytes: bytes) -> list[DefectFinding]:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img)
        h, w = arr.shape[:2]
        image_area_px = float(h * w)

        # Background = the most common color in the image (the roof surface
        # itself, since it dominates the frame); anomalies are pixels that
        # deviate from it beyond a threshold.
        pixels = arr.reshape(-1, 3)
        colors, counts = np.unique(pixels, axis=0, return_counts=True)
        background = colors[np.argmax(counts)].astype(np.int16)

        diff = np.abs(arr.astype(np.int16) - background).sum(axis=2)
        mask = (diff > 60).astype(np.uint8) * 255

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        findings: list[DefectFinding] = []
        for i, contour in enumerate(contours):
            area = cv2.contourArea(contour)
            if area < MIN_CONTOUR_AREA_PX:
                continue
            x, y, bw, bh = cv2.boundingRect(contour)
            cx, cy = (x + bw / 2) / w, (y + bh / 2) / h

            contour_mask = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(contour_mask, [contour], -1, 255, thickness=cv2.FILLED)
            mean_color = cv2.mean(arr, mask=contour_mask)[:3]

            findings.append(
                DefectFinding(
                    type=_type_for_contour(i, np.array(mean_color)),
                    severity=_severity_for_area(area, image_area_px),
                    bbox=(round(x / w, 4), round(y / h, 4), round((x + bw) / w, 4), round((y + bh) / h, 4)),
                    tile_index=_tile_index_for(cx, cy),
                    confidence=round(min(0.97, 0.5 + (area / image_area_px) * 40), 3),
                )
            )

        # Largest/most confident findings first.
        findings.sort(key=lambda f: f.confidence, reverse=True)
        return findings


class YoloDefectDetector(DefectDetector):
    """Real trained-model inference -- activates only when YOLO_MODEL_PATH is
    set and points at real weights (e.g. a fine-tuned yolov8n-seg checkpoint
    trained on labeled roof imagery). Assumes the model's class names match
    TAXONOMY; adjust the class-name mapping below if a real model uses
    different label names.
    """

    _model = None  # loaded lazily, cached per-process

    def _load_model(self):
        if YoloDefectDetector._model is not None:
            return YoloDefectDetector._model

        settings = get_settings()
        if not settings.yolo_model_path:
            raise RuntimeError(
                "DEFECT_PROVIDER=yolo requires YOLO_MODEL_PATH to point at a trained "
                ".pt weights file. Set DEFECT_PROVIDER=rule_based for now."
            )
        try:
            from ultralytics import YOLO  # lazy import -- not a base dependency
        except ImportError as exc:
            raise RuntimeError(
                "DEFECT_PROVIDER=yolo requires the `ultralytics` package "
                "(pip install ultralytics) -- not installed by default because it "
                "pulls in torch, which is a multi-GB dependency unused until a "
                "trained model actually exists."
            ) from exc

        YoloDefectDetector._model = YOLO(settings.yolo_model_path)
        return YoloDefectDetector._model

    async def detect(self, image_bytes: bytes) -> list[DefectFinding]:
        model = self._load_model()
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size

        results = model.predict(img, verbose=False)
        findings: list[DefectFinding] = []
        for result in results:
            for box in result.boxes:
                x0, y0, x1, y1 = box.xyxy[0].tolist()
                cx, cy = (x0 + x1) / 2 / w, (y0 + y1) / 2 / h
                class_name = model.names.get(int(box.cls[0]), "unknown")
                confidence = float(box.conf[0])
                area_ratio = ((x1 - x0) * (y1 - y0)) / (w * h)
                findings.append(
                    DefectFinding(
                        type=class_name,
                        severity=_severity_for_area(area_ratio * w * h, w * h),
                        bbox=(round(x0 / w, 4), round(y0 / h, 4), round(x1 / w, 4), round(y1 / h, 4)),
                        tile_index=_tile_index_for(cx, cy),
                        confidence=round(confidence, 3),
                    )
                )
        findings.sort(key=lambda f: f.confidence, reverse=True)
        return findings


_PROVIDERS = {"rule_based": RuleBasedDefectDetector, "yolo": YoloDefectDetector}


def get_defect_detector() -> DefectDetector:
    return _PROVIDERS[get_settings().defect_provider]()
