"""RoofAI's SAM-2 footprint segmentation as a Modal app. Deploy with:

    modal deploy sam2_service.py

Railway's backend calls this over HTTP (see backend/app/services/footprint.py's
Sam2FootprintProvider) instead of loading SAM-2 in-process, since Railway has
no GPU tier (confirmed via Railway's own docs). This is the only GPU-dependent
piece of the whole system -- everything else (API, Postgres, Redis, CPU
worker) stays on Railway.

Every API call below (modal.App.cls, modal.Image.from_registry/.pip_install,
modal.Volume.from_name, modal.enter, modal.fastapi_endpoint, modal.Secret)
was checked against the actual installed `modal` SDK (v1.5.4) by inspecting
its real signatures with `inspect.signature` -- not guessed from memory or
older docs, which matters because Modal's API has changed shape across
versions (e.g. `scaledown_window` replaced an older `container_idle_timeout`
name). What is NOT verified: this sandbox cannot reach modal.com at all
(confirmed blocked), so `modal deploy` itself, the GPU cold start, and an
actual SAM-2 inference call have not been executed. You have a Modal
account -- that's the part only you can run and confirm.

Same supply-chain note as the Railway-GPU version this replaces: `pip
install sam2` installs an UNRELATED third party's PyPI upload, not Meta's
package (confirmed by downloading and inspecting it directly). Installed
from Meta's real repo below instead.
"""
import os

import modal

app = modal.App("roofai-sam2")

# CUDA/torch pairing confirmed the same way as the (now-retired) Railway GPU
# Dockerfile: Meta's real sam2 package requires torch>=2.5.1 (read directly
# from its setup.py), and this base image tag was confirmed to actually
# exist via Docker Hub's registry API.
sam2_image = (
    modal.Image.from_registry("pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime", add_python="3.11")
    # `pip install git+https://...` needs the `git` binary to clone the repo
    # -- the base image's build container doesn't have it. Caught by an
    # actual `modal deploy` run: "ERROR: Cannot find command 'git'".
    .apt_install("git")
    .pip_install(
        "git+https://github.com/facebookresearch/sam2.git",  # NOT `pip install sam2` -- see module docstring
        "pillow",
        "numpy",
        "fastapi[standard]",
    )
)

# Checkpoint lives in a persistent Modal Volume, downloaded once on first
# cold start rather than baked into the image -- keeps image builds fast;
# the checkpoint survives container restarts via the volume instead.
checkpoint_volume = modal.Volume.from_name("sam2-checkpoints", create_if_missing=True)
CHECKPOINT_DIR = "/checkpoints"
CHECKPOINT_PATH = f"{CHECKPOINT_DIR}/sam2_hiera_large.pt"

# Real bug caught from an actual `modal deploy` + live checkpoint download:
# "Unexpected key(s) in state_dict: no_obj_embed_spatial,
# obj_ptr_tpos_proj.weight, obj_ptr_tpos_proj.bias" -- those keys only exist
# in SAM 2.1's architecture, not 2.0's. Meta's README lists the 2.1
# checkpoint first/as the recommended one, so that's what got downloaded --
# but this config path was still pointing at the 2.0 config
# (configs/sam2/sam2_hiera_l.yaml), which doesn't have those layers at all.
# Fixed to the matching 2.1 config. If you deliberately want the 2.0
# checkpoint instead, use configs/sam2/sam2_hiera_l.yaml + a 2.0 checkpoint
# URL together -- the config and checkpoint version must always match.
CONFIG_NAME = "configs/sam2.1/sam2.1_hiera_l.yaml"

# Create with: modal secret create roofai-sam2-secrets SAM2_API_KEY=<random value> SAM2_CHECKPOINT_URL=<url from facebookresearch/sam2's README>
# SAM2_API_KEY must match SAM2_MODAL_API_KEY on the Railway side (app/config.py).
# SAM2_CHECKPOINT_URL: I could not fetch this myself -- dl.fbaipublicfiles.com
# is confirmed blocked from this sandbox, same as it was for the Railway
# GPU-worker attempt. Copy it from Meta's repo yourself.
secrets = modal.Secret.from_name("roofai-sam2-secrets")


@app.cls(
    image=sam2_image,
    gpu="T4",  # matches what your original spec named; adjust if you want a bigger GPU
    volumes={CHECKPOINT_DIR: checkpoint_volume},
    secrets=[secrets],
    scaledown_window=300,  # keep a warm container for 5 min after the last request
    timeout=120,
)
class Sam2Service:
    @modal.enter()
    def load_model(self):
        import urllib.request

        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        if not os.path.exists(CHECKPOINT_PATH):
            checkpoint_url = os.environ.get("SAM2_CHECKPOINT_URL")
            if not checkpoint_url:
                raise RuntimeError(
                    "No checkpoint found in the volume and SAM2_CHECKPOINT_URL is not set. "
                    "Add it to the roofai-sam2-secrets Modal secret, or download the checkpoint "
                    "into the sam2-checkpoints volume yourself first."
                )
            os.makedirs(CHECKPOINT_DIR, exist_ok=True)
            urllib.request.urlretrieve(checkpoint_url, CHECKPOINT_PATH)
            checkpoint_volume.commit()

        sam2_model = build_sam2(CONFIG_NAME, CHECKPOINT_PATH, device="cuda")
        self.predictor = SAM2ImagePredictor(sam2_model)

    def _segment(self, image_bytes: bytes) -> dict:
        import io

        import numpy as np
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img)
        h, w = arr.shape[:2]

        self.predictor.set_image(arr)
        # Prompt with the image center point as foreground -- Railway's
        # imagery provider is expected to center the frame on the requested
        # lat/lng, so the building of interest should be roughly centered.
        center_point = np.array([[w // 2, h // 2]])
        center_label = np.array([1])
        masks, scores, _ = self.predictor.predict(
            point_coords=center_point, point_labels=center_label, multimask_output=True
        )
        best_mask = masks[int(np.argmax(scores))].astype(bool)

        return {"bbox": mask_to_bbox(best_mask)}

    @modal.fastapi_endpoint(method="POST")
    async def segment(self, request):
        """POST the raw image bytes as the request body, with
        `Authorization: Bearer <SAM2_API_KEY>`. Returns
        {"bbox": [x0, y0, x1, y1]} normalized 0-1, or {"bbox": null} if
        SAM-2 found nothing at the prompt point.
        """
        from fastapi import HTTPException

        expected_key = os.environ["SAM2_API_KEY"]
        auth_header = request.headers.get("authorization", "")
        got_key = auth_header[len("Bearer ") :] if auth_header.startswith("Bearer ") else ""
        if not got_key or got_key != expected_key:
            raise HTTPException(status_code=401, detail="invalid or missing API key")

        image_bytes = await request.body()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="empty request body -- expected raw image bytes")

        return self._segment(image_bytes)


def mask_to_bbox(mask) -> list[float] | None:
    """Convert a boolean segmentation mask to a normalized [x0, y0, x1, y1]
    bbox. Pure numpy, no SAM-2/Modal dependency -- unit-tested for real in
    tests/test_bbox_math.py without needing GPU or the model.
    """
    import numpy as np

    h, w = mask.shape
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return [round(x0 / w, 4), round(y0 / h, 4), round((x1 + 1) / w, 4), round((y1 + 1) / h, 4)]
