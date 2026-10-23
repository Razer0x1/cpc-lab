"""Overview dashboard aggregation — all metrics computed from the database.

No hardcoded sample numbers: whenever there is no data, zeros with explanatory
empty-state hints are returned instead.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    Artifact, AuditEvent, BenchmarkRun, CompressionMethod, Experiment, ExperimentLog,
    Hypothesis, Metric, ResearchEntry, ResearchProject,
)


def compute_overview(db: Session, workspace_id: str) -> dict:
    exp_completed = db.query(Experiment).filter_by(workspace_id=workspace_id, status="completed").count()
    exp_running = db.query(Experiment).filter_by(workspace_id=workspace_id, status="running").count()
    exp_queued = db.query(Experiment).filter_by(workspace_id=workspace_id, status="queued").count()
    exp_failed = db.query(Experiment).filter_by(workspace_id=workspace_id, status="failed").count()
    hyp_total = db.query(Hypothesis).filter_by(workspace_id=workspace_id).count()
    hyp_validated = (
        db.query(Hypothesis)
        .filter(Hypothesis.workspace_id == workspace_id,
                Hypothesis.evidence_level.in_(["experimentally_tested", "independently_reproduced"]))
        .count()
    )
    hyp_pending = db.query(Hypothesis).filter_by(workspace_id=workspace_id, status="approved").count()

    # averages from MEASURED metrics of completed experiments
    retention_rows = (
        db.query(func.avg(Metric.value)).join(Experiment, Experiment.id == Metric.experiment_id)
        .filter(Metric.workspace_id == workspace_id, Metric.name == "task_retention",
                Metric.stage == "measured", Experiment.status == "completed")
        .scalar()
    )
    ratio_rows = (
        db.query(func.avg(Metric.value)).join(Experiment, Experiment.id == Metric.experiment_id)
        .filter(Metric.workspace_id == workspace_id, Metric.name == "compression_ratio",
                Metric.stage == "measured", Experiment.status == "completed")
        .scalar()
    )
    speedup_rows = (
        db.query(func.avg(Metric.value)).join(Experiment, Experiment.id == Metric.experiment_id)
        .filter(Metric.workspace_id == workspace_id, Metric.name == "latency_speedup_warm",
                Metric.stage == "measured", Experiment.status == "completed")
        .scalar()
    )

    total_artifact_bytes = db.query(func.coalesce(func.sum(Artifact.size_bytes), 0)).filter_by(
        workspace_id=workspace_id).scalar()
    artifact_count = db.query(Artifact).filter_by(workspace_id=workspace_id).count()

    recent_experiments = db.query(Experiment).filter_by(workspace_id=workspace_id).order_by(
        Experiment.created_at.desc()).limit(5).all()
    findings = (
        db.query(Experiment)
        .filter_by(workspace_id=workspace_id, status="completed")
        .order_by(Experiment.finished_at.desc()).limit(4).all()
    )
    pending = (
        db.query(Hypothesis)
        .filter_by(workspace_id=workspace_id)
        .filter(Hypothesis.status.in_(["draft", "approved"]))
        .order_by(Hypothesis.updated_at.desc()).limit(5).all()
    )
    benchmarks = db.query(BenchmarkRun).filter_by(workspace_id=workspace_id).order_by(
        BenchmarkRun.created_at.desc()).limit(6).all()

    timeline = (
        db.query(AuditEvent).filter_by(workspace_id=workspace_id)
        .order_by(AuditEvent.ts.desc()).limit(12).all()
    )

    activity = []
    for e in recent_experiments:
        activity.append({"ts": e.created_at.isoformat(), "kind": "experiment_created", "label": e.name, "status": e.status, "id": e.id})
    for f in findings:
        activity.append({"ts": (f.finished_at or f.created_at).isoformat(), "kind": "experiment_completed",
                          "label": f"Completed: {f.name}", "status": f.success_verdict or f.status, "id": f.id})
    activity.sort(key=lambda x: x["ts"], reverse=True)

    return {
        "totals": {
            "projects": db.query(ResearchProject).filter_by(workspace_id=workspace_id).count(),
            "research_entries": db.query(ResearchEntry).filter_by(workspace_id=workspace_id).count(),
            "experiments_completed": exp_completed,
            "experiments_running": exp_running,
            "experiments_queued": exp_queued,
            "experiments_failed": exp_failed,
            "hypotheses_total": hyp_total,
            "hypotheses_validated": hyp_validated,
            "hypotheses_pending": hyp_pending,
            "methods_available": db.query(CompressionMethod).count(),
            "benchmarks_completed": db.query(BenchmarkRun).filter_by(workspace_id=workspace_id, status="completed").count(),
            "artifacts": artifact_count,
        },
        "averages": {
            "compression_ratio": round(float(ratio_rows), 3) if ratio_rows is not None else None,
            "task_retention": round(float(retention_rows), 3) if retention_rows is not None else None,
            "latency_speedup": round(float(speedup_rows), 3) if speedup_rows is not None else None,
            "note": "averaged over measured metric rows of completed experiments; None means no measured data yet",
        },
        "storage": {
            "artifact_bytes": int(total_artifact_bytes or 0),
            "artifact_count": artifact_count,
        },
        "compute_status": {
            "runner_backend": available_runner_backend(),
            "note": "in-process thread runner for CPU demo jobs; Celery+Redis enabled in docker-compose",
        },
        "recent_experiments": [
            {"id": e.id, "name": e.name, "kind": e.kind, "status": e.status, "verdict": e.success_verdict,
             "created_at": e.created_at.isoformat(), "progress": e.progress} for e in recent_experiments
        ],
        "findings": [
            {"id": e.id, "name": e.name, "verdict": e.success_verdict,
             "retention": (e.result_summary or {}).get("task_retention"),
             "ratio": (e.result_summary or {}).get("compression_ratio_artifact"),
             "finished_at": (e.finished_at.isoformat() if e.finished_at else None)} for e in findings
        ],
        "pending_hypotheses": [
            {"id": h.id, "title": h.title or (h.statement[:90]), "status": h.status, "evidence_level": h.evidence_level}
            for h in pending
        ],
        "benchmarks": [
            {"id": b.id, "task": b.task, "primary_metric": b.primary_metric, "status": b.status,
             "model_id": b.model_id, "value": (b.result or {}).get("value"),
             "created_at": b.created_at.isoformat()} for b in benchmarks
        ],
        "activity": activity[:12],
        "empty_state_hint": _empty_state_hint(db, workspace_id),
    }


def available_runner_backend() -> str:
    from ..config import get_settings
    return get_settings().job_backend


def _empty_state_hint(db: Session, workspace_id: str) -> str:
    if db.query(Experiment).filter_by(workspace_id=workspace_id).count() == 0:
        return ("No experiments yet. Start with the first working demonstration: run 'Teacher→Student "
                "distillation (demo)' in the Experiment Lab — it is CPU-only and finishes in seconds.")
    if db.query(BenchmarkRun).filter_by(workspace_id=workspace_id).count() == 0:
        return ("Experiments exist but no benchmark runs. Execute benchmarks in the Benchmark Center "
                "to build baseline-vs-compressed comparisons and Pareto frontiers.")
    if db.query(Hypothesis).filter_by(workspace_id=workspace_id).count() == 0:
        return ("Add a hypothesis in Hypothesis Studio and link it to an experiment to connect "
                "research intent with measured evidence.")
    return ""
