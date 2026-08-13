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
pip install -r requirements.txt   # modal + fastapi (fastapi is needed locally
                                   # too -- `modal deploy` imports sam2_service.py
                                   # on your machine before shipping it)
modal setup   # opens a browser to link your existing Modal account
```

## Step 2: Get the real SAM-2 checkpoint URL

Go to **https://github.com/facebookresearch/sam2**, find "Model
Checkpoints", copy the download URL for the **large** checkpoint.

**Important, caught from an actual failed deploy**: Meta ships two model
generations, SAM 2.0 and SAM 2.1, with different checkpoint files
(`sam2_hiera_large.pt` vs `sam2.1_hiera_large.pt`) that are NOT
interchangeable with each other's config. `sam2_service.py`'s `CONFIG_NAME`
is set to the **2.1** config (`configs/sam2.1/sam2.1_hiera_l.yaml`) since
that's the version Meta's README lists first/recommends now. Make sure the
checkpoint URL you copy is the **2.1** one -- if you deliberately want the
older 2.0 checkpoint instead, you must also change `CONFIG_NAME` in
`sam2_service.py` to `configs/sam2/sam2_hiera_l.yaml` to match, or you'll
hit `RuntimeError: Error(s) in loading state_dict for SAM2Base: Unexpected
key(s)...` — exactly the error this note exists because of.

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

1. **Checkpoint/config version mismatch** — this actually happened on the
   first real deploy: `RuntimeError: Error(s) in loading state_dict for
   SAM2Base: Unexpected key(s)...`. Means the checkpoint you downloaded
   (2.0 vs 2.1) doesn't match `CONFIG_NAME` in `sam2_service.py`. See Step 2.
2. **Checkpoint download fails inside the container** — `SAM2_CHECKPOINT_URL`
   wrong, expired, or requires auth Modal's container doesn't have. Check
   `modal app logs roofai-sam2` for the `urllib.request.urlretrieve` error.
3. **Cold start timeout** — first request after a scale-to-zero has to
   download/load a multi-GB model; if it's slower than the 120s function
   timeout in `sam2_service.py`, raise `timeout=` there and redeploy.

If a container keeps failing repeatedly right after deploy (Modal's
dashboard shows "crash-looping" on the Containers tab), that's this list,
not a networking/curl issue on your end -- check `modal app logs
<app-name>` for the real Python traceback before doing anything else.

4. **Every call returns `422 Unprocessable Entity`, even correct ones** --
   this actually happened after fixing the checkpoint/config issue above:
   containers came up fine (no more crash-looping), but every request --
   including ones with a correct body and a correct `Authorization` header
   -- came back 422. Root cause: `segment(self, request)`'s `request`
   parameter had no type annotation, so FastAPI (which Modal uses
   internally to build the endpoint) couldn't tell it was meant to receive
   the raw request object, and instead treated it as a required *query
   string* parameter -- which no client was ever sending, hence "field
   required" on every call. Fixed by annotating it as `fastapi.Request`
   (`from fastapi import Request` at the top of `sam2_service.py`, then
   `async def segment(self, request: Request):`). If you're editing this
   file yourself and add more endpoint parameters, the same rule applies to
   those too -- FastAPI infers each parameter's source (path/query/body)
   from its type annotation, so an unannotated one won't behave the way
   you expect.
