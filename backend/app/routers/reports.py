"""Results & Reports: generate and export scientific reports (Markdown/HTML/PDF)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Artifact, Experiment, Hypothesis, Paper, Report, SourceRef
from ..security import WorkspaceCtx, audit, get_current_user, get_ws_ctx, require_write_access
from ..services import artifacts as artifact_store
from ..services import reports as report_service

router = APIRouter(prefix="/api/v1/reports", tags=["results & reports"])

ENVIRONMENT = {
    "platform": "host CPU (per-node; recorded per run in the future via resource telemetry)",
    "engine": "numpy-mlp (CPU); PyTorch/HF engines are optional GPU extras",
    "precision": "float32 weights and activation math (int8 codes for quantized artifacts)",
}


class ReportIn(BaseModel):
    experiment_id: str | None = None
    title: str | None = None
    format: str = Field(default="markdown", pattern="^(markdown|html|pdf)$")


def _build_context(db: Session, ws_id: str, experiment_id: str) -> dict:
    exp = db.get(Experiment, experiment_id)
    if exp is None or exp.workspace_id != ws_id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    hyp = db.get(Hypothesis, exp.hypothesis_id) if exp.hypothesis_id else None
    refs = []
    related_work = []
    if hyp is not None:
        refs = db.query(SourceRef).filter_by(subject_type="hypothesis", subject_id=hyp.id).all()
        papers = [db.get(Paper, r.paper_id) for r in refs]
        for p in papers:
            if p is not None:
                related_work.append({"title": p.title, "authors": p.authors, "year": p.year, "doi": p.doi, "url": p.url})
    summary = exp.result_summary or {}
    repro_steps = [
        f"Recreate experiment '{exp.name}' (kind={exp.kind}) with seed={exp.seed}",
        f"Use the same versioned config snapshot: {exp.config_json}",
        "Evaluate on the same generated test split (dataset generator cpc_spiral3; seed = run seed + 1)",
        "Compare artifact bytes of teacher.npz vs student.npz stored in Artifacts",
    ]
    return {
        "title": None,  # filled by caller
        "objective": hyp.statement if hyp else (exp.name + ": measure compression vs task quality on the demo benchmark"),
        "hypothesis": {
            "statement": hyp.statement if hyp else None,
            "rationale": hyp.rationale if hyp else None,
            "success_criteria": hyp.success_criteria if hyp else None,
            "failure_criteria": hyp.failure_criteria if hyp else None,
        } if hyp else None,
        "experiment": {
            "id": exp.id, "name": exp.name, "kind": exp.kind, "seed": exp.seed,
            "runner_kind": exp.runner_kind,
            "success_verdict": exp.success_verdict,
            "config_json": exp.config_json,
            "result_summary": summary,
        },
        "related_work": related_work,
        "setup": {
            "environment": ENVIRONMENT,
            "limitations": [
                "Single-host CPU measurements; latency is host-specific and must not be generalized",
                "Warm/cold latency from Python timing loops; production inference benchmarks need dedicated harnesses",
                "Energy consumption not measured in this milestone (requires hardware measurement)",
                "Single seed unless explicitly configured otherwise; multi-seed sweeps are the next milestone",
            ],
            "repro_steps": repro_steps,
        },
    }


@router.post("/generate", status_code=201)
def generate_report(body: ReportIn, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    if not body.experiment_id:
        raise HTTPException(status_code=422, detail="experiment_id is required (reports are generated from runs)")
    data = _build_context(db, ctx.workspace.id, body.experiment_id)
    data["title"] = body.title or f"Research report — {data['experiment']['name']}"
    md = report_service.render_markdown(
        title=data["title"], objective=data["objective"], hypothesis=data["hypothesis"],
        experiment=data["experiment"], related_work=data["related_work"],
        setup=data["setup"], citations=[f"{r['title']} ({r.get('year') or 'n.d.'}) DOI: {r['doi'] or r['url']}" for r in data["related_work"]],
    )
    if body.format == "pdf":
        try:
            blob = report_service.markdown_to_pdf(md, data["title"])
            ext, ctype = "pdf", "application/pdf"
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e))
    elif body.format == "html":
        blob = report_service.markdown_to_html(md, data["title"]).encode()
        ext, ctype = "html", "text/html"
    else:
        blob = md.encode()
        ext, ctype = "md", "text/markdown"
    stored = artifact_store.put_bytes(ctx.workspace.id, "report", f"report.{ext}", blob)
    art = Artifact(
        workspace_id=ctx.workspace.id, experiment_id=body.experiment_id, kind="report",
        filename=f"report.{ext}", meta={"format": body.format}, **stored,
    )
    db.add(art)
    db.commit()
    db.refresh(art)
    rep = Report(workspace_id=ctx.workspace.id, experiment_id=body.experiment_id, title=data["title"],
                 format=body.format, artifact_id=art.id, created_by=ctx.user.id)
    db.add(rep)
    db.commit()
    db.refresh(rep)
    audit(db, "report.generate", user=ctx.user, workspace_id=ctx.workspace.id, object_type="report", object_id=rep.id,
          detail={"format": body.format})
    db.commit()
    return {"id": rep.id, "artifact_id": art.id, "format": body.format, "sha256": art.sha256, "size_bytes": art.size_bytes}


@router.get("")
def list_reports(ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    items = db.query(Report).filter_by(workspace_id=ctx.workspace.id).order_by(Report.created_at.desc()).all()
    return [
        {"id": r.id, "title": r.title, "format": r.format, "experiment_id": r.experiment_id,
         "artifact_id": r.artifact_id, "created_at": r.created_at.isoformat()}
        for r in items
    ]


@router.get("/{report_id}/download")
def download_report(report_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    rep = db.get(Report, report_id)
    if rep is None or rep.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Report not found")
    art = db.get(Artifact, rep.artifact_id)
    if art is None:
        raise HTTPException(status_code=404, detail="Report artifact missing")
    try:
        data = artifact_store.read_bytes(art.uri)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Artifact path invalid")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return Response(
        content=data,
        media_type=art.content_type,
        headers={"Content-Disposition": f"attachment; filename={art.filename or 'report'}",
                  "X-Artifact-SHA256": art.sha256},
    )


