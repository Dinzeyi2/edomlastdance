# RoofAI Analysis Backend

The ML backend behind a Lovable-built roofing app: Lovable sends a lat/lng,
this service downloads aerial imagery, isolates the building footprint, runs
defect detection, compares against prior-year imagery, scores the roof 0-100,
uploads the evidence, and returns (or polls back) a structured report.

```
Lovable map click
    -> POST /api/v1/analyze/async {lat, lng, user_id, compare_year, ...}
    -> Railway returns {job_id, status: "queued"}
    -> Celery worker (separate process, via Redis):
         imagery fetch -> footprint mask -> 3x3 tile split -> defect detection
         -> (temporal diff, if compare_year given) -> scoring -> S3 upload
    -> Lovable polls GET /jobs/{id} (or receives a signed webhook)
    -> job.result matches the AnalysisResult shape below
```

## What's real vs. what's a stub

Everything is wired end-to-end and testable right now (46 tests: 45 passing
+ 1 that auto-skips unless you install `ultralytics`, no network calls in the
normal suite, no paid API keys required). This sandbox's network egress is
policy-restricted to a host allowlist I don't control and was told not to
route around -- some real vendor calls could be implemented and unit-tested
here, some could be reached at the domain level but not tested end-to-end
without your credentials, and a few hosts are hard-blocked regardless of
credentials. Being precise about which is which:

| Piece | Status | Notes |
|---|---|---|
| API gateway, job queue, DB, storage, webhook, scoring, temporal diff, footprint cache, imagery cache, rate limiting | **Real, working** | See "What's genuinely real" below |
| Rule-based defect detector | **Real, working** | Actual OpenCV contour detection, not a random-number stand-in -- see `app/services/defects.py` |
| `IMAGERY_PROVIDER=mock` | **Real, working** | Deterministic synthetic "aerial roof" art (`app/services/roof_art.py`), not a real photo |
| `FOOTPRINT_PROVIDER=center_crop` | **Real, working** | The simple baseline your spec described as the interim step before SAM-2 |
| Diff heatmap (temporal comparison) | **Real, working** | Actual per-pixel diff + JET colormap, not just a text summary -- `app/services/temporal.py` |
| `DEFECT_PROVIDER=yolo` | **Real, verified working** (given a model) | I actually ran this against a real downloaded YOLOv8 model and confirmed the load/inference/parsing code is correct -- see `tests/test_yolo_detector_optional.py`. It has no roof-specific classes to detect until you provide a fine-tuned `YOLO_MODEL_PATH`; no such model or labeled dataset exists yet (your own step 9, deliberately last) |
| `IMAGERY_PROVIDER=google_solar` | **Real implementation, not live-verified** | Real HTTP calls to Google's documented Solar API + real GeoTIFF decoding (tested against real GeoTIFF bytes I constructed, confirmed byte-accurate). `solar.googleapis.com` is reachable from this sandbox (confirmed), but I don't have a Google Cloud API key to make an actual successful call -- give me one and I can verify/fix it here |
| `STORAGE_PROVIDER=s3` | **Real code, not live-verified** | Real boto3 client. `s3.amazonaws.com` is reachable from this sandbox (confirmed) -- give me a real AWS bucket + credentials and I can verify this here too. Cloudflare R2's endpoint is separately confirmed **blocked**, so R2 specifically cannot be tested from this sandbox even with credentials |
| `FOOTPRINT_PROVIDER=osm` | **Real code, not live-verified, host confirmed blocked** | Real Overpass API client (free, no key) -- `overpass-api.de` returns a 403 from this sandbox's egress proxy regardless of credentials |
| `LLM_PROVIDER=openai` | **Real code, not live-verified, host confirmed blocked** | `api.openai.com` returns a 403 from this sandbox's egress proxy regardless of credentials |
| Webhook to Lovable | **Real code, not live-verified** | Depends on your Lovable app's URL, which isn't reachable from here either way |
| `FOOTPRINT_PROVIDER=sam2` | **Real HTTP client here; real model code on Modal, not live-verified** | Railway has no GPU tier (confirmed via Railway's own docs), so SAM-2 runs on Modal instead -- see `/modal-service` at the repo root. This provider is just an HTTP client (tested with a mocked call). **Caught a real supply-chain issue while building the Modal side**: `pip install sam2` is NOT Meta's package -- I downloaded and inspected it directly; it's an unrelated third party's PyPI upload. Fixed to install from `github.com/facebookresearch/sam2` instead, confirmed the config-path convention by reading that package's actual `build_sam.py` source, and verified every Modal SDK call used (`App.cls`, `Image.from_registry`, `Volume.from_name`, etc.) against the real installed `modal` package's signatures. Not verified: `modal deploy` itself and actual inference, since `modal.com` is confirmed blocked from this sandbox and I have no GPU here regardless -- see `/modal-service/README.md` |
| Nearmap | **Stub, host confirmed blocked** | `api.nearmap.com` returns a 403 regardless of credentials, and its API is behind an enterprise sales process with no public documented shape to implement against anyway |

"Confirmed blocked" / "confirmed reachable" means I actually tested the
connection (`curl` through the sandbox's egress proxy) rather than assumed --
see the git history for the raw results. "Not live-verified" past that means:
implemented correctly against documented behavior, but I could not execute an
actual successful call, either because I lack credentials or because the host
itself is blocked. Worth a smoke test right after your first deploy.

### What's genuinely real (no caveats)

FastAPI gateway with your exact endpoints and auth, the Job/Feedback/
BuildingFootprintCache Postgres (or SQLite) models -- including the
footprint cache actually being read/written now (it existed as an unused
table in an earlier pass; caught on review and wired in, with tests proving
a second request for the same coordinates skips re-running the footprint
provider), the Celery+Redis async pipeline (verified against a **real Redis
broker and a separate worker process**, not just Celery's inline eager
mode), Redis-backed imagery tile caching (proven with tests against a real
Redis server -- a second fetch for the same coordinates doesn't hit the
underlying provider again), Redis-backed rate limiting (same -- proven
against real Redis, including that a 429 actually fires past the configured
limit), the 3x3 tile splitter, the deterministic scoring formula, the
temporal diff logic plus the diff heatmap image, and local-disk storage.

Both Redis-backed features (imagery cache, rate limiter) **fail open** if
Redis itself is unreachable -- they log a warning and let the request
through rather than 500ing the whole API. Caught by actually testing the
no-Redis case: the first version of this made Redis a hard dependency of
every `/analyze` call, which silently broke the "zero infra" local dev setup
below. Fixed, with a test proving each one degrades gracefully.

## Local development (zero infra)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # CELERY_TASK_ALWAYS_EAGER=true by default -- no Redis needed

uvicorn app.main:app --reload
```

```bash
KEY=dev-local-key   # matches RAILWAY_API_KEY in .env.example

curl -s -X POST localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" -H "Authorization: Bearer $KEY" \
  -d '{"lat":40.7128,"lng":-74.0060,"compare_year":2023}' | python3 -m json.tool

# or the async path:
JOB=$(curl -s -X POST localhost:8000/api/v1/analyze/async \
  -H "Content-Type: application/json" -H "Authorization: Bearer $KEY" \
  -d '{"lat":40.7128,"lng":-74.0060}')
echo "$JOB"
curl -s localhost:8000/api/v1/jobs/<job_id> -H "Authorization: Bearer $KEY" | python3 -m json.tool
```

Interactive docs: `localhost:8000/docs`.

### With a real Postgres + Redis + separate worker process

```bash
docker compose up -d   # postgres + redis
# .env
DATABASE_URL=postgresql://roofai:roofai@localhost:5432/roofai
CELERY_TASK_ALWAYS_EAGER=false

# terminal 1
uvicorn app.main:app --reload
# terminal 2
celery -A app.workers.celery_app worker --loglevel=info
```

This is what was actually run and verified while building this (real Redis
broker, a genuinely separate worker process, `POST /analyze/async` returning
immediately while the worker completes the job in the background) -- not
just the eager-mode shortcut.

## Tests

```bash
pytest
```

45 tests pass, 1 auto-skips (see below). Every test spins up a **real**
Redis server on a scratch port (conftest.py) -- not mocked out -- since the
imagery cache and rate limiter need to be proven against real Redis, not
just import cleanly. Covers: scoring math, temporal diff logic + heatmap
generation, deterministic mock imagery, the rule-based detector's actual
contour detection (including a regression test for an edge-artifact bug the
detector caught during development -- see `app/services/roof_art.py`'s
comments), the footprint cache actually persisting and being reused, the
imagery cache actually skipping a re-fetch on a repeat request, the rate
limiter actually returning 429 past its configured limit, real GeoTIFF
decoding for the Google Solar provider (constructed test GeoTIFFs with known
pixel values, confirmed byte-accurate output), and the full HTTP API (auth,
sync analyze, async analyze + poll, feedback, unknown-job 404).
`CELERY_TASK_ALWAYS_EAGER=true` keeps job execution deterministic without
needing a separate worker process for tests.

`tests/test_yolo_detector_optional.py` auto-skips unless you `pip install
ultralytics` -- it's deliberately not a base dependency (adds torch, a
multi-GB dependency, for a code path with no trained model to load yet). Run
it manually to see real YOLO inference actually execute:
```bash
pip install ultralytics
pytest tests/test_yolo_detector_optional.py -v
```

## API reference

All `/api/v1/*` routes require `Authorization: Bearer <RAILWAY_API_KEY>`.

**`POST /api/v1/analyze`** -- runs the full pipeline inline, returns the
result directly. Fine for testing; for real traffic prefer the async path so
the caller isn't holding a request open for 30-120s.

**`POST /api/v1/analyze/async`**
```json
{"lat": 40.7128, "lng": -74.0060, "address": "123 Main St", "user_id": "uuid", "compare_year": 2023, "resolution_cm": 10, "include_raw_tiles": true}
```
->
```json
{"job_id": "job_abc123", "status": "queued", "estimated_seconds": 60}
```

**`GET /api/v1/jobs/{job_id}`**
```json
{"job_id": "job_abc123", "status": "processing", "progress": 0.45, "stage": "defect_detection", "result": null, "error": null}
```
When `status: "completed"`, `result` matches:
```json
{
  "building_id": "bld_...", "score": 67, "condition": "aging", "confidence": 0.82,
  "resolution_cm": 10, "footprint_masked": true, "imagery_date": "2026-06-15",
  "findings": [{"type": "staining", "severity": "moderate", "bbox": [0.34,0.21,0.52,0.38], "tile_index": [1,2], "confidence": 0.91}],
  "temporal": {"previous_score": 43, "score_delta": 24, "change_summary": "New staining visible since prior imagery."},
  "image_urls": {"full": "...", "masked": "...", "tiles": ["...", "..."]}
}
```

**`POST /api/v1/feedback`** -- roofer corrections, saved to Postgres as
future training data for a real defect model.

**`GET /health`** -- no auth, used by Railway's health check.

## Deploy to Railway

Two services in one Railway project, from this same repo:

1. **Web service.** Deploy from GitHub as usual -- the repo-root
   `railway.json` auto-configures the Docker build (`backend/Dockerfile`) and
   health check with zero manual "Root Directory" setting.
2. **Worker service.** Add a second service from the *same* repo/branch. In
   its Settings, override **Start Command** to:
   ```
   celery -A app.workers.celery_app worker --loglevel=info --concurrency=2
   ```
   Same image, different process -- this is the background worker that
   actually runs the pipeline.
3. **Add Postgres and Redis** (New -> Database, twice) to the project.
4. **On both services**, add `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
   and `REDIS_URL` = `${{Redis.REDIS_URL}}` (Railway variable references --
   use "Add Reference" in the UI). Both services must share the same
   database and broker.
5. **On both services**, set:

   | Variable | Value |
   |---|---|
   | `RAILWAY_API_KEY` | your own random secret -- this is what Lovable's server function sends as the bearer token |
   | `CELERY_TASK_ALWAYS_EAGER` | `false` (or just omit it -- default is already false) |
   | `STORAGE_PROVIDER` | `s3` once you have a bucket, otherwise leave `local` (ephemeral, fine for a first smoke test only) |
   | `S3_ENDPOINT` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET` | your R2/S3 credentials, if `STORAGE_PROVIDER=s3` |
   | `IMAGERY_PROVIDER`, `FOOTPRINT_PROVIDER`, `DEFECT_PROVIDER`, `LLM_PROVIDER` | leave at their real-and-free defaults (`mock`, `center_crop`, `rule_based`, `none`) until you wire up a real vendor -- see the table above |
   | `GOOGLE_SOLAR_API_KEY` | set this + `IMAGERY_PROVIDER=google_solar` once you have a Google Cloud key with the Solar API enabled -- this is the one real vendor integration most likely to just work once keyed, since I confirmed `solar.googleapis.com` is reachable |
   | `SAM2_MODAL_ENDPOINT_URL` / `SAM2_MODAL_API_KEY` | set these + `FOOTPRINT_PROVIDER=sam2` once you've deployed `/modal-service` (separate deploy, not a Railway service -- see its README) |
   | `LOVABLE_WEBHOOK_URL` / `WEBHOOK_SECRET` | if you want the push-on-completion path in addition to polling |
   | `RATE_LIMIT_PER_MINUTE` | defaults to 30; set to `0` to disable |

6. **Verify**: `curl https://<web-service>.up.railway.app/health` ->
   `{"status":"ok"}`. Then run the same `curl` flow from "Local development"
   against that URL. Watch the worker service's logs for `Task
   run_analysis_task[...] received` / `succeeded` to confirm it's actually
   processing jobs.

## Lovable integration

See `/lovable-integration` at the repo root -- the server function, the
polling hook, and a webhook receiver, written against this backend's actual
API contract, ready to copy into your Lovable project. Its README says
plainly which files are high-confidence (the server function, the polling
hook) vs. a sketch to adapt (the webhook route's exact framework wiring --
I don't have your Lovable codebase to verify against).

One open question from your original spec I did NOT resolve on my own:
section 2A lists `POST /webhooks/lovable` as something *Railway* exposes
(i.e. Lovable calls it), but section 4's concrete example shows the opposite
-- Railway calling out to a Lovable-hosted URL. I built the outbound
direction (matches the concrete example), not an inbound route, since I
couldn't find a plausible payload/purpose for Lovable calling *into* Railway
under that name without guessing. If you did mean an inbound route, tell me
what it's for and I'll add it.

## Swapping in a real provider

Same pattern throughout: implement the interface in the matching
`app/services/*.py` (each stub has a docstring saying exactly what's needed),
add it to that file's `_PROVIDERS` dict, set the matching env var. Nothing in
`app/routes/*` or `app/services/pipeline.py` needs to change.

## What's explicitly out of scope for this pass

- Frontend/dashboard (that's Lovable)
- Nearmap imagery integration (its API has no public self-serve key or documented shape to implement against, and the host is confirmed blocked from this sandbox regardless)
- Actually running SAM-2 (the code is real on both sides -- Railway's HTTP client and the Modal service -- but `modal deploy` and a live inference call need your Modal account, which this sandbox can't reach; see `/modal-service/README.md`)
- A trained YOLO defect model (needs a labeled dataset that doesn't exist yet -- `POST /feedback` is the mechanism to start collecting one; the inference code path itself is verified working, see Tests)
- Image registration/alignment for temporal comparison (not needed against synthetic imagery, which is always pixel-aligned by construction; would matter with real imagery that has perspective/zoom variance between captures)
- An inbound `/webhooks/lovable` route -- see the open question under "Lovable integration"
- Alembic migrations (uses `Base.metadata.create_all` -- fine pre-production, promote before this holds data worth preserving)

## Repo layout

```
app/
  config.py            env-driven settings; single source of truth for provider selection
  auth.py              bearer-token check
  rate_limit.py         Redis-backed rate limiter (real, tested against real Redis)
  db/
    session.py          async engine (API) + sync engine (Celery worker), URL normalization
    models.py            Job, BuildingFootprintCache, Feedback
  schemas/
    analyze.py            Pydantic models matching the API contract above exactly
  services/
    imagery.py             ImageryProvider: mock (real) / google_solar (real, not live-verified) / nearmap (stub)
    imagery_cache.py        Redis tile cache wrapper (real, tested against real Redis)
    footprint.py             FootprintProvider: center_crop (real) / osm (real, host confirmed blocked) / sam2 (real HTTP client -- the model itself runs on Modal, see /modal-service)
    footprint_cache.py        Postgres footprint cache (real, tested)
    defects.py                  DefectDetector: rule_based (real CV) / yolo (real, verified against a real model, needs YOLO_MODEL_PATH)
    scoring.py                   deterministic scorer (real) + optional LLM reasoning pass (real, host confirmed blocked)
    temporal.py                   year-over-year diff logic + diff heatmap (both real)
    storage.py                     StorageService: local (real) / s3 (real, not live-verified)
    webhook.py                      signed push to Lovable (real, not live-verified)
    redis_client.py                  shared per-event-loop Redis client
    pipeline.py                       orchestrates all of the above -- used by both /analyze and the Celery task
  workers/
    celery_app.py       Celery instance (Redis broker/backend)
    tasks.py              the task behind /analyze/async
  routes/                analyze.py, jobs.py, feedback.py, health.py
tests/                   45 tests pass, 1 auto-skips without ultralytics, real Redis, no other network calls
Dockerfile               serves the API + default CPU worker (different start commands)
railway.json             repo-root Railway config (see /railway.json, not backend/)
docker-compose.yml       optional local Postgres + Redis
../lovable-integration/  Lovable-side server function, polling hook, webhook receiver sketch
../modal-service/        SAM-2 on Modal (the one GPU-dependent piece -- Railway has no GPU tier)
```
