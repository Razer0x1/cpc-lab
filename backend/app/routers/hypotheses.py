"""Hypothesis Studio: full-lifecycle hypothesis management with evidence classification."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Experiment, Hypothesis, SourceRef
from ..security import WorkspaceCtx, audit, get_ws_ctx, require_write_access

router = APIRouter(prefix="/api/v1/hypotheses", tags=["hypotheses"])

EVIDENCE_LEVELS = ["idea_only", "literature_supported", "implemented", "experimentally_tested", "independently_reproduced"]


class HypothesisIn(BaseModel):
    title: str = ""
    statement: str = Field(min_length=8)
    rationale: str = ""
    math_formulation: str = ""
    related_research: list[str] = []
    expected_outcomes: str = ""
    competing_explanations: list[str] = []
    required_datasets: list[str] = []
    required_models: list[str] = []
    baselines: list[str] = []
    ablations: list[str] = []
    success_criteria: str = ""
    failure_criteria: str = ""
    compute_requirements: str = ""
    reproducibility_notes: str = ""
    project_id: str | None = None


class HypothesisPatch(BaseModel):
    title: str | None = None
    statement: str | None = None
    rationale: str | None = None
    math_formulation: str | None = None
    expected_outcomes: str | None = None
    baselines: list[str] | None = None
    ablations: list[str] | None = None
    success_criteria: str | None = None
    failure_criteria: str | None = None
    status: str | None = None  # draft | approved | rejected
    evidence_level: str | None = None


@router.get("")
def list_hypotheses(ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    items = db.query(Hypothesis).filter_by(workspace_id=ctx.workspace.id).order_by(Hypothesis.updated_at.desc()).all()
    exp_by_hyp: dict[str, list[dict]] = {}
    for e in db.query(Experiment).filter(Experiment.hypothesis_id != None, Experiment.workspace_id == ctx.workspace.id).all():  # noqa: E711
        exp_by_hyp.setdefault(e.hypothesis_id, []).append(
            {"id": e.id, "name": e.name, "status": e.status, "verdict": e.success_verdict}
        )
    return [
        {
            "id": h.id, "title": h.title, "statement": h.statement, "status": h.status,
            "evidence_level": h.evidence_level, "evidence_note": (
                "Evidence level propagates only from actual runs, never from search absence of papers."
                if h.evidence_level == "idea_only" else ""
            ),
            "success_criteria": h.success_criteria, "failure_criteria": h.failure_criteria,
            "rationale": h.rationale, "math_formulation": h.math_formulation,
            "related_research": h.related_research, "baselines": h.baselines, "ablations": h.ablations,
            "expected_outcomes": h.expected_outcomes,
            "required_datasets": h.required_datasets, "required_models": h.required_models,
            "compute_requirements": h.compute_requirements,
            "reproducibility_notes": h.reproducibility_notes,
            "experiments": exp_by_hyp.get(h.id, []),
            "created_at": h.created_at.isoformat(), "updated_at": h.updated_at.isoformat(),
        }
        for h in items
    ]


@router.post("", status_code=201)
def create_hypothesis(body: HypothesisIn, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    h = Hypothesis(workspace_id=ctx.workspace.id, status="draft", evidence_level="idea_only", created_by=ctx.user.id, **body.model_dump())
    db.add(h)
    db.commit()
    db.refresh(h)
    audit(db, "hypothesis.create", user=ctx.user, workspace_id=ctx.workspace.id, object_type="hypothesis", object_id=h.id)
    db.commit()
    return {"id": h.id}


@router.get("/{hypothesis_id}")
def get_hypothesis(hypothesis_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    h = db.get(Hypothesis, hypothesis_id)
    if h is None or h.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    refs = (
        db.query(SourceRef).filter_by(workspace_id=ctx.workspace.id, subject_type="hypothesis", subject_id=h.id).all()
    )
    return {
        "id": h.id, "title": h.title, "statement": h.statement, "status": h.status,
        "evidence_level": h.evidence_level, "paper_links": [
            {"id": r.id, "paper_id": r.paper_id, "relation": r.relation} for r in refs
        ],
    }


@router.patch("/{hypothesis_id}")
def patch_hypothesis(hypothesis_id: str, body: HypothesisPatch, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    h = db.get(Hypothesis, hypothesis_id)
    if h is None or h.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in ("draft", "approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be draft|approved|rejected")
    if "evidence_level" in data and data["evidence_level"] not in EVIDENCE_LEVELS:
        raise HTTPException(status_code=422, detail=f"evidence_level must be one of {EVIDENCE_LEVELS}")
    for k, v in data.items():
        setattr(h, k, v)
    db.commit()
    audit(db, "hypothesis.update", user=ctx.user, workspace_id=ctx.workspace.id, object_type="hypothesis", object_id=h.id, detail=data)
    db.commit()
    return {"ok": True, "id": h.id}


@router.post("/{hypothesis_id}/link-paper", status_code=201)
def link_paper(hypothesis_id: str, paper_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    """Manual literature link — an explicit, user-verified provenance action."""
    require_write_access(ctx.user)
    h = db.get(Hypothesis, hypothesis_id)
    if h is None or h.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    ref = SourceRef(workspace_id=ctx.workspace.id, subject_type="hypothesis", subject_id=h.id, paper_id=paper_id, relation="supports")
    db.add(ref)
    db.commit()
    return {"id": ref.id}


