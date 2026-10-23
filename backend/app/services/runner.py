"""Experiment task registry + shared task context.

Tasks are pure functions of (context) -> TaskResult. The JobManager executes them
either in an in-process thread pool (default, CPU demo jobs) or via Celery workers
(production). User-provided code is never executed; only registered task kinds run.
"""
from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Artifact, Experiment, ExperimentLog, ExperimentRun, Metric, Workspace
from ..services import artifacts as artifact_store


class JobCancelled(Exception):
    pass


class JobPaused(Exception):
    pass


@dataclass
class TaskContext:
    db: Session
    experiment_id: str
    workspace_id: str
    seed: int
    config: dict[str, Any]
    budgets: dict[str, Any]
    _log_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _cancelled: set = field(default_factory=set, repr=False)
    _paused: set = field(default_factory=set, repr=False)

    def log(self, message: str, level: str = "info") -> None:
        with self._log_lock:
            seq = (
                self.db.query(ExperimentLog)
                .filter(ExperimentLog.experiment_id == self.experiment_id)
                .order_by(ExperimentLog.seq.desc())
                .first()
            )
            next_seq = (seq.seq + 1) if seq else 0
            self.db.add(
                ExperimentLog(experiment_id=self.experiment_id, seq=next_seq, level=level, message=message)
            )
            self.db.commit()

    def progress(self, fraction: float, message: str | None = None) -> None:
        exp = self.db.get(Experiment, self.experiment_id)
        if exp is not None:
            exp.progress = max(0.0, min(1.0, fraction))
            self.db.commit()
        if message:
            self.log(message)

    def check_point(self) -> None:
        """Cooperative cancellation/pause checkpoint. Tasks call this between stages."""
        if self.experiment_id in self._cancelled:
            raise JobCancelled()
        if self.experiment_id in self._paused:
            raise JobPaused()

    def save_artifact(self, kind: str, filename: str, data: bytes, meta: dict | None = None) -> Artifact:
        stored = artifact_store.put_bytes(self.workspace_id, kind, filename, data)
        art = Artifact(
            workspace_id=self.workspace_id,
            experiment_id=self.experiment_id,
            kind=kind,
            filename=filename,
            meta=meta or {},
            **stored,
        )
        self.db.add(art)
        self.db.commit()
        self.db.refresh(art)
        return art


@dataclass
class TaskResult:
    summary: dict[str, Any] = field(default_factory=dict)
    metrics: list[dict[str, Any]] = field(default_factory=list)  # {name,value,unit,stage,seed,extra}
    artifacts: list[dict[str, Any]] = field(default_factory=list)  # {kind, filename, data(bytes), meta}
    verdict: str | None = None  # successful | unsuccessful | inconclusive
    verdict_reason: str = ""
    engine_note: str = ""


TaskFunc = Callable[[TaskContext], TaskResult]

_REGISTRY: dict[str, TaskFunc] = {}


def register_task(kind: str) -> Callable[[TaskFunc], TaskFunc]:
    def deco(fn: TaskFunc) -> TaskFunc:
        _REGISTRY[kind] = fn
        return fn
    return deco


def get_task(kind: str) -> TaskFunc:
    if kind not in _REGISTRY:
        raise KeyError(f"Unknown experiment kind: {kind}")
    return _REGISTRY[kind]


def known_kinds() -> list[str]:
    return sorted(_REGISTRY)


def _store_task_artifacts(ctx: TaskContext, result: TaskResult) -> list[Artifact]:
    created: list[Artifact] = []
    for spec in result.artifacts:
        art = ctx.save_artifact(spec["kind"], spec["filename"], spec["data"], spec.get("meta"))
        created.append(art)
    return created


def snapshot_effective_config(ctx: TaskContext, effective: dict) -> None:
    """Persist the fully resolved config (kind defaults + user overrides) on the
    experiment. Reports must reproduce what actually ran, not just the submitted
    override dict; config_version is bumped to mark the resolution step."""
    exp = ctx.db.get(Experiment, ctx.experiment_id)
    if exp is None:
        return
    exp.config_json = dict(effective)
    exp.config_version = int(exp.config_version or 1) + 1
    ctx.db.commit()


def _apply_result(ctx: TaskContext, exp: Experiment, result: TaskResult) -> None:
    run = ExperimentRun(
        experiment_id=exp.id, seq=1, seed=exp.seed, status="completed",
        started_at=exp.started_at, finished_at=datetime.now(timezone.utc),
        metrics={"summary": result.summary},
    )
    ctx.db.add(run)
    ctx.db.flush()
    for m in result.metrics:
        ctx.db.add(
            Metric(
                workspace_id=exp.workspace_id,
                experiment_id=exp.id,
                run_id=run.id,
                name=m["name"],
                value=m.get("value"),
                unit=m.get("unit", ""),
                stage=m.get("stage", "measured"),
                seed=m.get("seed", exp.seed),
                extra=m.get("extra", {}),
            )
        )
    exp.result_summary = result.summary
    exp.success_verdict = result.verdict
    exp.engine_note = result.engine_note or exp.engine_note
    exp.progress = 1.0
    exp.status = "completed"
    exp.finished_at = datetime.now(timezone.utc)
    ctx.db.commit()


def execute_experiment_sync(experiment_id: str) -> None:
    """Run an experiment to completion in the calling thread (used by tests and Celery)."""
    db = SessionLocal()
    ctx: TaskContext | None = None
    try:
        exp = db.get(Experiment, experiment_id)
        if exp is None:
            raise ValueError(f"Experiment {experiment_id} not found")
        task = get_task(exp.kind)
        ws = db.get(Workspace, exp.workspace_id)
        ctx = TaskContext(
            db=db, experiment_id=exp.id, workspace_id=exp.workspace_id,
            seed=exp.seed, config=dict(exp.config_json or {}), budgets=dict(exp.budgets or {}),
        )
        exp.status = "running"
        exp.started_at = datetime.now(timezone.utc)
        exp.error = None
        db.commit()
        ctx.log(f"Experiment started (kind={exp.kind}, seed={exp.seed}, runner={exp.runner_kind})")
        result = task(ctx)
        _store_task_artifacts(ctx, result)
        _apply_result(ctx, exp, result)
        verdict_line = f"Verdict: {result.verdict}" + (f" — {result.verdict_reason}" if result.verdict_reason else "")
        ctx.log(verdict_line, level="info" if result.verdict == "successful" else "warn")
        ctx.log("Experiment completed")
    except JobCancelled:
        e = db.get(Experiment, experiment_id)
        if e is not None:
            e.status = "cancelled"
            e.finished_at = datetime.now(timezone.utc)
            db.commit()
    except JobPaused:
        e = db.get(Experiment, experiment_id)
        if e is not None:
            e.status = "paused"
            db.commit()
    except Exception:
        db.rollback()
        e = db.get(Experiment, experiment_id)
        err = traceback.format_exc(limit=8)
        if e is not None:
            e.status = "failed"
            e.error = err[-4000:]
            e.finished_at = datetime.now(timezone.utc)
            db.commit()
            if ctx is not None:
                ctx.log(f"Experiment failed: {err.splitlines()[-1]}", level="error")
    finally:
        db.close()


class JobManager:
    """In-process thread executor with cooperative cancellation. Celery backend optional."""

    def __init__(self) -> None:
        self._executor: ThreadPoolExecutorLike | None = None
        self._cancelled: set[str] = set()
        self._paused: set[str] = set()
        self._lock = threading.Lock()

    def _pool(self):
        from concurrent.futures import ThreadPoolExecutor

        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cpc-exp")
        return self._executor

    def submit(self, experiment_id: str, *, paused: bool = False) -> None:
        with self._lock:
            self._cancelled.discard(experiment_id)
            if paused:
                self._paused.add(experiment_id)
            else:
                self._paused.discard(experiment_id)
        self._pool().submit(self._wrap, experiment_id)

    def _wrap(self, experiment_id: str) -> None:
        db = SessionLocal()
        try:
            exp = db.get(Experiment, experiment_id)
            paused = experiment_id in self._paused
        finally:
            db.close()
        if paused:
            execute_experiment_sync_paused(experiment_id)
        else:
            execute_experiment_sync(experiment_id)

    def cancel(self, experiment_id: str) -> bool:
        with self._lock:
            self._cancelled.add(experiment_id)
        return True

    def pause(self, experiment_id: str) -> bool:
        with self._lock:
            self._paused.add(experiment_id)
        return True

    def resume(self, experiment_id: str) -> None:
        self.submit(experiment_id, paused=False)


class ThreadPoolExecutorLike:
    pass


def execute_experiment_sync_paused(experiment_id: str) -> None:
    """Execute with the paused set installed so the first checkpoint pauses the job."""
    db = SessionLocal()
    try:
        exp = db.get(Experiment, experiment_id)
        if exp is None:
            return
        # Re-run with pause flag: simplest correct behavior is to mark paused before any work.
        exp.status = "paused"
        db.commit()
    finally:
        db.close()


job_manager = JobManager()
