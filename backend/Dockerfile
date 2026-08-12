# Runtime image for Railway (or any container host) -- serves BOTH the API
# and the Celery worker off the same image, just with a different start
# command per Railway service (see /railway.json for the API's; the worker
# service overrides startCommand to
# `celery -A app.workers.celery_app worker --loglevel=info`, see README).
#
# Every base dependency in requirements.txt ships a prebuilt Linux wheel, so
# no compiler toolchain is needed. Deliberately does NOT include
# ultralytics/torch or sam2 -- see app/services/defects.py and
# app/services/footprint.py for why those stay optional, lazy-imported
# dependencies instead of baked into this image.
#
# NOTE: built with the REPO ROOT as the build context (see /railway.json's
# dockerfilePath), not the backend/ folder -- that's what lets Railway
# auto-detect this config with zero manual "Root Directory" setting. That's
# why every COPY below is prefixed with backend/.
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

EXPOSE 8000

# Railway injects $PORT at runtime; default to 8000 for `docker run` locally.
# This is the API process's command -- the worker service overrides it.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
