"""Celery app instance. Broker + result backend are both Redis (REDIS_URL) --
matches the spec's "Celery/RQ with Redis" choice. CELERY_TASK_ALWAYS_EAGER
runs tasks inline in the caller's process instead of dispatching to a worker
over Redis; set it for local dev/tests when you don't want a Redis server and
a separate `celery worker` process running. Do NOT set it on Railway -- that
would make POST /analyze/async block for the full pipeline, defeating the
point of the async endpoint.
"""
from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery("roofai", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)

# Registers app.workers.tasks' @celery_app.task-decorated functions.
import app.workers.tasks  # noqa: E402,F401
