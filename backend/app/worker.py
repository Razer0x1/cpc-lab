"""Celery application for production (Redis-backed) asynchronous experiments.

The default dev mode runs the in-process thread runner. In docker-compose, the
`worker` service runs this module; only registered task kinds execute (never
user-provided code). Resource isolation comes from the container environment.
"""
from __future__ import annotations

from celery import Celery

from .config import get_settings

settings = get_settings()

celery_app = Celery(
    "cpc-lab",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker"],
)
from .services import tasks as _register_tasks  # noqa: E402,F401  (registers experiment runners)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_time_limit=3600,
    task_soft_time_limit=3300,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)


@celery_app.task(name="cpc.run_experiment", bind=True, max_retries=0)
def run_experiment(self, experiment_id: str):  # noqa: ANN001
    """Execute an experiment synchronously inside the worker container."""
    from .services.runner import execute_experiment_sync

    execute_experiment_sync(experiment_id)
    return {"experiment_id": experiment_id, "status": "processed"}
