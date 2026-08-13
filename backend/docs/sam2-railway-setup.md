# Deploying SAM-2 as a GPU worker on Railway

Step-by-step. Where I could verify something from this sandbox, I say so.
Where I couldn't (mainly: anything requiring a live download or GPU), I say
that too, plus exactly what to check on your end.

## What you're building

A **third Railway service** (alongside the API and the existing CPU worker):
a GPU-enabled Celery worker that loads SAM-2 once and segments roof
footprints for real. It shares the same Postgres + Redis as the other two
services. `FOOTPRINT_PROVIDER=sam2` only needs to be set on *this* worker —
leave the API and the CPU worker on `center_crop` (or `osm`) so they don't
try to load a GPU model they don't have.

## Step 1: Check GPU availability on your Railway plan

Not every Railway plan/region has GPU instances. In the Railway dashboard:
**Account/Team Settings → Usage & Billing** (or the "New Service" GPU option
if your team has it enabled) — look for GPU as a resource type when creating
a service. If you don't see it, you'll need to either upgrade your plan or
contact Railway support to enable GPU access. This is a Railway account
setting I have no visibility into from here — check it before doing anything
else, since everything below assumes it's available.

## Step 2: Get the real SAM-2 checkpoint URL

Go to **https://github.com/facebookresearch/sam2** and find the "Model
Checkpoints" section of their README. Copy the download URL for
`sam2_hiera_large.pt` (or whichever size you want — large is what your spec
named).

I could not fetch or verify this exact URL myself — this sandbox's network
policy blocks `dl.fbaipublicfiles.com` (confirmed with a direct connectivity
test). Get the current, correct URL directly from their repo, not from me.

**Also important**: do NOT `pip install sam2`. I downloaded and inspected
that PyPI package directly — it is not Meta's official package (its
`setup.py` lists an unrelated GitHub URL and an individual author, not
`facebookresearch`). `requirements-gpu.txt` and `Dockerfile.worker` already
install from Meta's real repo instead
(`git+https://github.com/facebookresearch/sam2.git`) -- just flagging this
so you don't "fix" it back to the PyPI name later without realizing why.

## Step 3: SAM-2 config name (already confirmed, not a guess)

`app/config.py`'s default is
`SAM2_CONFIG_NAME=configs/sam2/sam2_hiera_l.yaml`. I confirmed this is
correct by downloading Meta's actual `build_sam.py` source (via the -- yes,
fraudulent, but source-identical for this file -- PyPI copy, whose code
matches Meta's public repo verbatim including copyright headers) and reading
its `HF_MODEL_ID_TO_FILENAMES` table directly, which maps
`facebook/sam2-hiera-large` → `configs/sam2/sam2_hiera_l.yaml` +
`sam2_hiera_large.pt`. A bare top-level `sam2_hiera_l.yaml` (no `configs/`
prefix) also exists in the package but is a legacy/unused location — the
default is already correct for the checkpoint your spec named, no action
needed on this step unless you pick a different model size (in which case,
swap `sam2_hiera_l` for `sam2_hiera_t`/`s`/`b+` consistently in both the
config path and checkpoint filename).

## Step 4: Build the GPU worker image

From the repo root:

```bash
docker build -f backend/Dockerfile.worker \
  --build-arg SAM2_CHECKPOINT_URL="<the URL from Step 2>" \
  -t roofai-gpu-worker .
```

This bakes the checkpoint into the image at build time (simpler than
downloading it at container startup every time). The image will be large
(base CUDA/PyTorch image + checkpoint, likely several GB) — expect a slow
first build/push.

If you'd rather not bake a multi-GB checkpoint into your image, an
alternative is downloading it to a Railway volume at container startup
instead and pointing `SAM2_CHECKPOINT_PATH` at the volume path — not set up
here, but a reasonable follow-up if image size becomes a problem.

## Step 5: Push the image somewhere Railway can pull it

Railway can build from a Dockerfile in your repo directly, OR you can push a
pre-built image to a registry (Docker Hub, GHCR) and point Railway at it.
Given this image needs a build arg (the checkpoint URL) that you probably
don't want sitting in your repo's `railway.json` in plaintext, **pushing a
pre-built image is the cleaner option here**:

```bash
docker tag roofai-gpu-worker <your-registry>/roofai-gpu-worker:latest
docker push <your-registry>/roofai-gpu-worker:latest
```

## Step 6: Create the Railway service

In your Railway project: **New → Empty Service** (not "Deploy from GitHub
repo" this time, since you're pointing at a pre-built image) → in that
service's Settings, set the **Source** to your pushed image
(`<your-registry>/roofai-gpu-worker:latest`).

Under **Settings → Deploy**, set the resource type to **GPU** and pick an
instance size (an NVIDIA T4 is the one your original spec named, and is
Railway's typical entry-level GPU option — confirm current GPU SKUs in their
dashboard, this changes over time).

## Step 7: Environment variables on this service

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` — same reference as your other two services |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` — same reference |
| `FOOTPRINT_PROVIDER` | `sam2` |
| `SAM2_CONFIG_NAME` | leave unset to use the confirmed-correct default (`configs/sam2/sam2_hiera_l.yaml`), unless you picked a different model size in Step 2 |
| `SAM2_DEVICE` | `cuda` |

`SAM2_CHECKPOINT_PATH` is already set by the Dockerfile (`/models/sam2_checkpoint.pt`) — no need to set it again unless you changed where it lives.

Do **NOT** set `FOOTPRINT_PROVIDER=sam2` on the API service or your existing
CPU worker — only this GPU service should try to load SAM-2.

## Step 8: Route jobs to the right worker

Celery routes tasks by queue name, and right now everything uses the
default `celery` queue — meaning your CPU worker and this GPU worker would
both try to pull the same tasks, and the CPU one (with `FOOTPRINT_PROVIDER`
left at `center_crop`) would run some analyses without SAM-2 nondeterministically. Two ways to handle this, pick one:

- **Simplest**: only run this GPU worker, retire the CPU worker (`docker`
  wise, stop that Railway service). One worker, one footprint provider,
  no queue routing needed.
- **Correct long-term**: add Celery queue routing so `run_analysis_task`
  goes to a queue only the GPU worker consumes, and the CPU worker consumes
  a different queue (or none). This isn't set up yet — flag it back to me if
  you want both workers running simultaneously and I'll add the routing
  config to `app/workers/celery_app.py`.

## Step 9: Deploy and verify

Watch this service's Railway logs for the model load on first task (it'll
be slow — multi-second to load a GPU model). Trigger an analysis
(`POST /api/v1/analyze/async`) and check the GPU worker's logs for the
`Task run_analysis_task[...] received` / `succeeded` lines, same pattern as
the CPU worker.

If it fails, the most likely first errors, in order of likelihood:
1. **Checkpoint file corrupted/incomplete** — the build-time download
   failed partway silently (Dockerfile.worker's download step doesn't
   verify a checksum). Check the file size in the built image against what
   Meta's README lists as the expected checkpoint size for
   `sam2_hiera_large.pt`.
2. **CUDA driver/toolkit mismatch** — the base image's bundled CUDA 12.1
   runtime doesn't match Railway's GPU instance's driver. Check
   `nvidia-smi` in the container against what CUDA version it reports.
3. **Config file not found** — least likely of the three, since the config
   path is confirmed correct against the real source (Step 3), but worth
   ruling out if you picked a non-default model size and mistyped the path.

None of these are things I can pre-verify from this sandbox — the actual
model download, GPU driver matching, and inference run are the genuine
unknowns of this deploy that need a real GPU to test.
