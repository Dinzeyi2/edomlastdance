# Runtime image for Railway (or any container host). Deliberately minimal --
# every runtime dependency (fastapi, sqlalchemy, asyncpg, shapely, anthropic,
# httpx) ships a prebuilt Linux wheel, so no compiler toolchain is needed.
#
# NOTE: this Dockerfile is built with the REPO ROOT as the build context (see
# /railway.json's dockerfilePath), not the backend/ folder -- that's what
# lets Railway auto-detect this config without any manual "Root Directory"
# setting. That's why every COPY below is prefixed with backend/.
FROM python:3.11-slim

WORKDIR /app

# Copy only what's needed to install dependencies first, so dependency layers
# cache across rebuilds that only touch application code.
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/fixtures ./fixtures

RUN pip install --no-cache-dir .

EXPOSE 8000

# Railway injects $PORT at runtime; default to 8000 for `docker run` locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
