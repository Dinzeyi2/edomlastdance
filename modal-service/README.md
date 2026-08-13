# RoofAI SAM-2 — Modal deployment

The one GPU-dependent piece of the system, split out from Railway (which
[has no GPU tier](https://docs.railway.com/guides/ai-api-hosted-inference))
onto Modal. Everything else (API, Postgres, Redis, CPU worker) stays on
Railway and calls this over HTTP.

## What's verified vs. not

I checked every Modal API this code uses (`App.cls`, `Image.from_registry`,
`Image.pip_install`, `Volume.from_name`, `modal.enter`, `modal.method`,
`modal.fastapi_endpoint`, `Secret.from_name`) against the actual installed
`modal` SDK by inspecting its real signatures directly — not from memory or
docs that might be stale, since Modal's API has changed shape across
versions. `sam2_service.py` imports cleanly against that real SDK. What I
could **not** verify: this sandbox cannot reach `modal.com` at all
(confirmed blocked), so `modal deploy`, an actual GPU cold start, and a real
SAM-2 inference call have not been executed anywhere. That's the part your
Modal account makes possible and this sandbox can't.

## Step 1: Install the CLI and authenticate

```bash
pip install modal
modal setup   # opens a browser to link your existing Modal account
```

## Step 2: Get the real SAM-2 checkpoint URL

Same requirement as before: go to
**https://github.com/facebookresearch/sam2**, find "Model Checkpoints", copy
the download URL for `sam2_hiera_large.pt`. I could not fetch this myself —
`dl.fbaipublicfiles.com` is confirmed blocked from this sandbox.

## Step 3: Create the Modal secret

```bash
modal secret create roofai-sam2-secrets \
  SAM2_API_KEY=<generate a random string yourself, e.g. `openssl rand -hex 32`> \
  SAM2_CHECKPOINT_URL=<the URL from Step 2>
```

`SAM2_API_KEY` is what protects this endpoint from being called by anyone
who finds the URL — Modal web endpoints are public HTTPS URLs by default.
Keep this value, you'll need it again in Step 5.

## Step 4: Deploy

```bash
cd modal-service
modal deploy sam2_service.py
```

First deploy will be slow — it's building an image on top of a multi-GB
CUDA base image. Modal prints the deployed web endpoint's URL when this
finishes, something like:

```
https://<your-workspace>--roofai-sam2-sam2service-segment.modal.run
```

Copy that exact URL.

## Step 5: Point Railway at it

On your Railway **API service** and **CPU worker service** (not a new
service this time — there's no Railway GPU service anymore), set:

| Variable | Value |
|---|---|
| `FOOTPRINT_PROVIDER` | `sam2` |
| `SAM2_MODAL_ENDPOINT_URL` | the URL from Step 4 |
| `SAM2_MODAL_API_KEY` | the same `SAM2_API_KEY` value from Step 3 |

Redeploy those services so the new env vars take effect.

## Step 6: Verify

```bash
# Should get a 401 -- proves auth is enforced
curl -X POST https://<your-endpoint-url> --data-binary @some-test-image.png

# Should get {"bbox": [...]} or {"bbox": null} -- proves it actually works
curl -X POST https://<your-endpoint-url> \
  -H "Authorization: Bearer <SAM2_API_KEY>" \
  --data-binary @some-test-image.png
```

Then trigger a real analysis from Railway (`POST /api/v1/analyze/async`
with `FOOTPRINT_PROVIDER=sam2` set) and check both Railway's worker logs
and Modal's dashboard logs (`modal app logs roofai-sam2`) for the request.

## If it fails, most likely first

1. **Checkpoint download fails inside the container** — `SAM2_CHECKPOINT_URL`
   wrong, expired, or requires auth Modal's container doesn't have. Check
   `modal app logs roofai-sam2` for the `urllib.request.urlretrieve` error.
2. **Cold start timeout** — first request after a scale-to-zero has to
   download/load a multi-GB model; if it's slower than the 120s function
   timeout in `sam2_service.py`, raise `timeout=` there and redeploy.
3. **Config path mismatch** — only relevant if you change `CONFIG_NAME` in
   `sam2_service.py` to a different model size than `sam2_hiera_large.pt`;
   the default is confirmed correct for the large model (verified against
   the real `build_sam.py` source, not guessed).

None of these three are things I can pre-verify from this sandbox.
