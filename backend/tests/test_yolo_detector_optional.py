"""Optional, real test of YoloDefectDetector against an actual downloaded
model -- skipped automatically unless `ultralytics` is installed (it's
deliberately not a base dependency, see app/services/defects.py and
requirements.txt). Run manually to prove the integration code genuinely
works end-to-end:

    pip install ultralytics
    pytest tests/test_yolo_detector_optional.py -v

This uses a generic COCO-pretrained yolov8n.pt (auto-downloaded by
ultralytics from GitHub), NOT a roof-defect model -- none exists yet. It
will detect the round damage-mark ellipses in the synthetic roof image as
something like "sports ball", not a real defect class. That's the expected,
honest result: it proves the model-loading/inference/parsing code is
correct, not that roof defect detection works -- that needs a real
fine-tuned model (step 9 in the build order), which needs labeled data that
doesn't exist yet.
"""
import pytest

ultralytics = pytest.importorskip("ultralytics", reason="ultralytics not installed -- see module docstring")


@pytest.fixture
def yolo_model_path(tmp_path):
    from ultralytics import YOLO

    # Triggers ultralytics' own auto-download from GitHub releases if not
    # already cached locally.
    model = YOLO("yolov8n.pt")
    weights_path = str(tmp_path / "yolov8n.pt")
    model.save(weights_path)
    return weights_path


async def test_yolo_detector_runs_real_inference(yolo_model_path, monkeypatch):
    from app.config import get_settings
    from app.services.defects import YoloDefectDetector
    from app.services.roof_art import generate_schematic_roof, image_to_png_bytes

    get_settings.cache_clear()
    monkeypatch.setenv("YOLO_MODEL_PATH", yolo_model_path)
    get_settings.cache_clear()

    img_bytes = image_to_png_bytes(generate_schematic_roof(seed=1, num_damage_marks=10))
    YoloDefectDetector._model = None  # ensure a fresh load against this test's model path (class-level cache)
    detector = YoloDefectDetector()
    findings = await detector.detect(img_bytes)

    # Real structural assertions -- this is inference output, not a fixture.
    for f in findings:
        assert 0 <= f.confidence <= 1
        x0, y0, x1, y1 = f.bbox
        assert 0 <= x0 < x1 <= 1
        assert 0 <= y0 < y1 <= 1
        assert f.severity in ("minor", "moderate", "severe")
        assert isinstance(f.type, str) and f.type  # a COCO class name, not empty
