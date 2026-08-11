# Roofing AI Lead Engine — Backend

Turns storm events into a ranked list of properties likely to have hail/wind
damage, each with an evidence packet (imagery, storm data, damage confidence,
estimated job value) a roofing sales rep can use instead of cold-knocking
doors.

```
Storm ingestion  →  Property resolution  →  Imagery fetch  →  Damage inference  →  Scoring
   (StormEvent)        (Property)          (ImageryAsset)    (DamageAssessment)      (Lead)
```

Every external dependency (storm data, property records, imagery, vision) sits
behind an abstract interface (`app/providers/base.py`) with a **mock
implementation as the default** and a **real implementation stubbed out** for
later. Nothing in `app/pipeline/*` or `app/api/*` needs to change when a real
vendor gets wired in — see "Swapping in a real provider" below.

## Quickstart (zero external services required)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

uvicorn app.main:app --reload
```

On startup the app creates its SQLite schema and seeds one dev tenant, keyed
by `DEV_SEED_TENANT_KEY` in `.env` (defaults to `dev-local-key`). Then, in
another terminal:

```bash
KEY=dev-local-key

# 1. Register a coverage area (a GeoJSON Polygon) for the dev tenant.
curl -s -X POST localhost:8000/territories \
  -H "Content-Type: application/json" -H "X-Tenant-Key: $KEY" \
  -d '{"name":"DFW metro","polygon_geojson":"{\"type\":\"Polygon\",\"coordinates\":[[[-97.3,32.3],[-96.3,32.3],[-96.3,33.3],[-97.3,33.3],[-97.3,32.3]]]}"}'

# 2. Trigger ingestion. This runs the ENTIRE pipeline synchronously (mock
#    providers are instant) and returns once every stage has finished.
curl -s -X POST localhost:8000/storm-events/ingest -H "Content-Type: application/json" -d '{}'

# 3. See the ranked leads.
curl -s localhost:8000/leads -H "X-Tenant-Key: $KEY" | python3 -m json.tool

# 4. Pull the full evidence packet for one lead.
curl -s localhost:8000/leads/<lead_id> -H "X-Tenant-Key: $KEY" | python3 -m json.tool

# 5. Record an outcome (the feedback loop for future scoring tuning).
curl -s -X PATCH localhost:8000/leads/<lead_id> \
  -H "Content-Type: application/json" -H "X-Tenant-Key: $KEY" \
  -d '{"status":"contacted"}'
```

Interactive API docs: `localhost:8000/docs`.

## Deploy to Railway

The repo is set up for a Docker-based Railway deploy: `Dockerfile` builds a
minimal production image (no dev/test dependencies), `railway.toml`
configures the build + health check, and `app/core/db.py` automatically
rewrites Railway's Postgres `DATABASE_URL` (`postgres://...`, sync-driver
format) into the async-driver format SQLAlchemy needs — you don't need to
edit the URL yourself.

1. **Push this repo to GitHub** (already done if you're reading this from the
   `claude/roofing-ai-sales-inspection-7jro12` branch).
2. **Create a Railway project** → *Deploy from GitHub repo* → pick this repo.
3. **Set the service's Root Directory to `backend`** (Settings → Root
   Directory). This repo is a monorepo with the app in a subfolder, so
   Railway needs to know where the Dockerfile lives.
4. **Add a Postgres database**: New → Database → PostgreSQL, in the same
   project. Railway provisions it and exposes a `DATABASE_URL` variable on
   the Postgres service.
5. **Wire the Postgres URL into the web service**: in the web service's
   Variables tab, add `DATABASE_URL` with the value `${{Postgres.DATABASE_URL}}`
   (Railway's variable-reference syntax — click "Add Reference" in the
   Railway UI instead of typing it if you'd rather not type it by hand).
   Without this the app falls back to an on-container SQLite file, which
   works but is wiped on every redeploy — fine for a first smoke test, not
   for anything you want to keep.
6. **Add your API keys as variables** on the web service. At minimum:

   | Variable | Value |
   |---|---|
   | `VISION_PROVIDER` | `stub` to start free, or `claude` once you're ready to spend real API calls |
   | `ANTHROPIC_API_KEY` | your key (only read when `VISION_PROVIDER=claude`) |
   | `DEV_SEED_TENANT_KEY` | **set this to your own random secret** — it's the API key the seeded dev tenant uses to call the API; the code default (`dev-local-key`) is fine for local dev, not for a public deployment |

   Leave `STORM_PROVIDER` / `PROPERTY_PROVIDER` / `IMAGERY_PROVIDER` as
   `mock` until you wire up a real one (see "Swapping in a real provider").
7. **Deploy.** Railway builds the Dockerfile and starts the container; the
   `/health` check in `railway.toml` gates traffic until the app (and its
   retrying DB connection — see `init_db_with_retry` in `app/core/db.py`,
   which handles the web service and Postgres both booting at once) is ready.
8. **Verify**: `curl https://<your-service>.up.railway.app/health` should
   return `{"status":"ok"}`. Then run the same `curl` flow from the
   Quickstart section against that URL instead of `localhost:8000`.

Optional: the standalone job worker (`python -m app.jobs.worker`) isn't
required — the ingest route drains the queue synchronously — but if you later
want ingestion off the request path, add it as a second Railway service
pointed at the same repo/Dockerfile with `startCommand` overridden to
`python -m app.jobs.worker`.

## Tests

```bash
pytest
```

No network calls, no external services — everything runs against mock
providers and a scratch SQLite file. Covers: scoring math, geo point-in-polygon,
each mock provider's determinism, a full pipeline drain asserting ranked leads
come out the other end (and that tenants outside a storm's territory correctly
see nothing), and the HTTP API end to end (auth, ingest, list/detail/patch).

## Architecture notes / deviations from a "textbook" version

- **No PostGIS.** Storm/territory polygons are stored as GeoJSON text;
  point-in-polygon filtering happens in application code via Shapely
  (`app/pipeline/geo.py`), not a DB-side `ST_Within`. This keeps the app
  running against plain SQLite *or* Postgres with zero GIS extension setup.
  It scales less gracefully than an indexed spatial query — fine at the lead
  volumes this product deals in (thousands of properties per territory, not
  millions); revisit if that changes.
- **No Redis/Celery.** Jobs live in a plain DB table (`app/models/job.py`)
  with a claim-one-pending helper (`SELECT ... FOR UPDATE SKIP LOCKED` on
  Postgres) in `app/jobs/queue.py`. The ingest API route drains the queue
  synchronously in-request (`app/jobs/runner.py`) so a single `POST
  /storm-events/ingest` call demonstrates the whole pipeline without a
  second process running. `python -m app.jobs.worker` is also provided as a
  standalone poller for a more production-shaped deployment (real vendor
  APIs are not instant, and you won't want ingestion blocking the request).
- **`Base.metadata.create_all` instead of Alembic migrations.** Fine for a v1
  scaffold with no production data yet; promote to real Alembic migrations
  before this touches a persistent database with data worth preserving.
- **Vision defaults to a free, deterministic stub** (`VISION_PROVIDER=stub`)
  that doesn't look at the image at all — it derives a plausible confidence
  from storm severity + roof attributes, so the whole pipeline runs at zero
  API cost. `VISION_PROVIDER=claude` is fully implemented
  (`app/providers/vision/claude.py`) and sends the image to a Claude vision
  model with a structured prompt; it's not the default because it costs real
  API calls per image and mock imagery is schematic placeholder art, not a
  real roof.

## Swapping in a real provider

1. Implement the interface in `app/providers/base.py` (e.g. fill in
   `app/providers/storm/noaa.py` against the NOAA NCEI Storm Events API).
2. Add it to the lookup dict in `app/providers/__init__.py`.
3. Set the matching env var (e.g. `STORM_PROVIDER=noaa`).

Nothing in `app/pipeline/*` or `app/api/*` changes.

## Try the real vision path without a real imagery vendor

```bash
# .env
VISION_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
```

Re-run the ingest flow above — inference now sends the bundled schematic
fixture images (`fixtures/sample_roofs/`, see `scripts/generate_fixtures.py`)
to Claude and stores its structured damage assessment. This proves the
integration path even before a real imagery vendor is wired up. Since the
fixtures are schematic placeholders (not real aerial photos), don't read
much into the actual damage_confidence values it returns — the point is that
the call, parsing, and storage all work.

## Using Postgres instead of SQLite

```bash
docker compose up -d
# .env
DATABASE_URL=postgresql+asyncpg://roofing:roofing@localhost:5432/roofing
```

No other changes needed — there's no PostGIS dependency to install. Plain
`postgres://...` or `postgresql://...` URLs (what Railway and most managed
Postgres providers hand out) work too — `app/core/db.py` rewrites the scheme
to the async driver automatically, see `normalize_database_url`.

## What's explicitly out of scope for this pass

- Frontend/dashboard UI
- Real NOAA/Regrid/Nearmap integrations (interfaces + stubs only, see
  `app/providers/*/noaa.py`, `regrid.py`, `nearmap.py`)
- Billing/usage metering
- Full auth (OAuth/JWT, roles) — a single hashed API key per tenant only
- A trained custom roof-damage CV model — vision is an LLM call or a stub

## Repo layout

```
app/
  core/       config, DB engine/session, dev tenant seeding
  models/     SQLAlchemy tables
  schemas/    Pydantic request/response models
  providers/  base interfaces + mock/real implementations per data source
  pipeline/   one function per pipeline stage, plus scoring + geo helpers
  jobs/       DB-backed job queue, drain loop, standalone worker
  api/routes/ FastAPI routers
tests/        pytest, all against mock providers, no network calls
fixtures/     schematic placeholder "aerial roof" images for mock imagery
scripts/      one-off fixture generator (needs Pillow, not an app dependency)
```
