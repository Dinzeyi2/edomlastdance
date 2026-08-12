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

Everything is wired end-to-end and testable right now (27 passing tests, no
network calls, no paid API keys). But three pieces are real vendors this repo
can't call without your credentials/infrastructure, and two are heavy ML
models this repo can't run without a trained checkpoint. Being precise about
which is which:

| Piece | Status | Notes |
|---|---|---|
| API gateway, job queue, DB, storage, webhook, scoring, temporal diff | **Real, working** | See "What's genuinely real" below |
| Rule-based defect detector | **Real, working** | Actual OpenCV contour detection, not a random-number stand-in -- see `app/services/defects.py` |
| `IMAGERY_PROVIDER=mock` | **Real, working** | Deterministic synthetic "aerial roof" art (`app/services/roof_art.py`), not a real photo |
| `FOOTPRINT_PROVIDER=center_crop` | **Real, working** | The simple baseline your spec described as the interim step before SAM-2 |
| `FOOTPRINT_PROVIDER=osm` | **Real code, not live-verified** | Real Overpass API client (free, no key) -- this sandbox's network egress policy blocks `overpass-api.de`, so I could not execute a live call. Should work once deployed; smoke-test it |
| `STORAGE_PROVIDER=s3` | **Real code, not live-verified** | Real boto3 client (AWS S3 or R2 via `S3_ENDPOINT`) -- same egress restriction, not live-tested from this sandbox |
| `LLM_PROVIDER=openai` | **Real code, not live-verified** | Real OpenAI call -- same restriction, needs your `OPENAI_API_KEY` |
| Webhook to Lovable | **Real code, not live-verified** | Real signed HTTP POST -- same restriction |
| `IMAGERY_PROVIDER=google_solar` / `nearmap` | **Stub** | Real vendor, real request/response shapes not implemented yet -- needs your API key and, for Google Solar, GeoTIFF handling not in `requirements.txt` |
| `FOOTPRINT_PROVIDER=sam2` | **Stub** | Needs the `sam2` package, a multi-GB checkpoint, and GPU-class compute -- none of which this environment has |
| `DEFECT_PROVIDER=yolo` | **Stub until you provide `YOLO_MODEL_PATH`** | No trained roof-defect model or labeled dataset exists yet -- this is step 9 in the build order, deliberately last |

"Not live-verified" means: implemented against the library/API's documented
behavior, unit-testable logic all passes, but I could not execute the actual
network call from this sandbox (its egress policy allowlists specific hosts
and blocks arbitrary third-party APIs). Worth a smoke test right after your
first deploy, before trusting it in production.

### What's genuinely real (no caveats)

FastAPI gateway with your exact endpoints and auth, the Job/Feedback/
BuildingFootprintCache Postgres (or SQLite) models, the Celery+Redis async
pipeline (verified against a **real Redis broker and a separate worker
process**, not just Celery's inline eager mode), the 3x3 tile splitter, the
deterministic scoring formula, the temporal diff logic, and local-disk
storage.

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

27 tests, no network calls: scoring math, temporal diff logic, deterministic
mock imagery, the rule-based detector's actual contour detection (including a
regression test for an edge-artifact bug the detector caught during
development -- see `app/services/roof_art.py`'s comments), and the full HTTP
API (auth, sync analyze, async analyze + poll, feedback, unknown-job 404).
Async tests run via `CELERY_TASK_ALWAYS_EAGER=true` so they're deterministic
and don't need Redis.

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
   | `LOVABLE_WEBHOOK_URL` / `WEBHOOK_SECRET` | if you want the push-on-completion path in addition to polling |

6. **Verify**: `curl https://<web-service>.up.railway.app/health` ->
   `{"status":"ok"}`. Then run the same `curl` flow from "Local development"
   against that URL. Watch the worker service's logs for `Task
   run_analysis_task[...] received` / `succeeded` to confirm it's actually
   processing jobs.

## Lovable integration

Your `analyzeRoofWithRailway` server function is correct as sketched -- point
`RAILWAY_API_URL` at the web service's Railway URL and `RAILWAY_API_KEY` at
the same secret set in step 5 above. Have `TeslaMap.tsx` call `POST
/api/v1/analyze/async`, then poll `GET /api/v1/jobs/{job_id}` (or receive the
webhook at whatever route you wire up to accept `LOVABLE_WEBHOOK_URL`'s
signed POST -- verify the `X-Webhook-Signature` header as an HMAC-SHA256 of
the raw body using `WEBHOOK_SECRET` before trusting it).

## Swapping in a real provider

Same pattern throughout: implement the interface in the matching
`app/services/*.py` (each stub has a docstring saying exactly what's needed),
add it to that file's `_PROVIDERS` dict, set the matching env var. Nothing in
`app/routes/*` or `app/services/pipeline.py` needs to change.

## What's explicitly out of scope for this pass

- Frontend/dashboard (that's Lovable)
- Real Google Solar / Nearmap imagery integration (stubbed, needs your API key + GeoTIFF handling for Solar API)
- SAM-2 segmentation (stubbed, needs GPU-class compute + a multi-GB checkpoint)
- A trained YOLO defect model (needs a labeled dataset that doesn't exist yet -- `POST /feedback` is the mechanism to start collecting one)
- Rate limiting, request-level caching in Redis beyond the job queue itself
- Alembic migrations (uses `Base.metadata.create_all` -- fine pre-production, promote before this holds data worth preserving)

## Repo layout

```
app/
  config.py       env-driven settings; single source of truth for provider selection
  auth.py         bearer-token check
  db/
    session.py    async engine (API) + sync engine (Celery worker), URL normalization
    models.py     Job, BuildingFootprintCache, Feedback
  schemas/
    analyze.py    Pydantic models matching the API contract above exactly
  services/
    imagery.py    ImageryProvider: mock (real) / google_solar / nearmap (stubs)
    footprint.py  FootprintProvider: center_crop (real) / osm (real, not live-verified) / sam2 (stub)
    defects.py    DefectDetector: rule_based (real CV) / yolo (real, needs a model file)
    scoring.py    deterministic scorer (real) + optional LLM reasoning pass (real, needs a key)
    temporal.py   year-over-year diff logic (real)
    storage.py    StorageService: local (real) / s3 (real, not live-verified)
    webhook.py    signed push to Lovable (real, not live-verified)
    pipeline.py   orchestrates all of the above -- used by both /analyze and the Celery task
  workers/
    celery_app.py Celery instance (Redis broker/backend)
    tasks.py      the task behind /analyze/async
  routes/         analyze.py, jobs.py, feedback.py, health.py
tests/            27 tests, no network calls
Dockerfile        serves both the API and worker (different start commands)
railway.json      repo-root Railway config (see /railway.json, not backend/)
docker-compose.yml  optional local Postgres + Redis
```
