# Runtime image for Railway (or any container host). Deliberately minimal --
# every runtime dependency (fastapi, sqlalchemy, asyncpg, shapely, anthropic,
# httpx) ships a prebuilt Linux wheel, so no compiler toolchain is needed.
FROM python:3.11-slim

WORKDIR /app

# Copy only what's needed to install dependencies first, so dependency layers
# cache across rebuilds that only touch application code.
COPY pyproject.toml ./
COPY app ./app
COPY fixtures ./fixtures

RUN pip install --no-cache-dir .

EXPOSE 8000

# Railway injects $PORT at runtime; default to 8000 for `docker run` locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
