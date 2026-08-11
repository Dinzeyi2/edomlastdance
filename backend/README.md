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

No other changes needed — there's no PostGIS dependency to install.

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
