"""Research Explorer: curated cross-paradigm catalog + filters + scholarly linking."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Paper, ResearchEntry, ResearchProject, SourceRef
from ..security import WorkspaceCtx, audit, get_ws_ctx, require_write_access 

router = APIRouter(prefix="/api/v1/research", tags=["research"])


@router.get("/entries")
def list_entries(
    field: str | None = None,
    architecture: str | None = None,
    technique: str | None = None,
    evidence: str | None = None,
    resource: str | None = None,
    year_from: int | None = None,
    q: str | None = None,
    ctx: WorkspaceCtx = Depends(get_ws_ctx),
    db: Session = Depends(get_db),
):
    query = db.query(ResearchEntry).filter_by(workspace_id=ctx.workspace.id)
    if field:
        query = query.filter(ResearchEntry.research_field == field)
    if architecture:
        query = query.filter(ResearchEntry.architecture == architecture)
    if technique:
        query = query.filter(ResearchEntry.compression_technique == technique)
    if evidence:
        query = query.filter(ResearchEntry.evidence_quality == evidence)
    if resource:
        query = query.filter(ResearchEntry.resource_estimate == resource)
    if year_from:
        query = query.filter(ResearchEntry.publication_year_from >= year_from)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            (func.lower(ResearchEntry.title)).like(like)
            | (func.lower(ResearchEntry.question)).like(like)
            | (func.lower(ResearchEntry.shared_structure)).like(like)
        )
    entries = query.order_by(ResearchEntry.created_at.desc()).all()
    papers = {p.id: p for p in db.query(Paper).filter_by(workspace_id=ctx.workspace.id).all()}
    refs = db.query(SourceRef).filter_by(workspace_id=ctx.workspace.id, subject_type="research_entry").all()
    refs_by_entry: dict[str, list[str]] = {}
    for r in refs:
        refs_by_entry.setdefault(r.subject_id, []).append(r.paper_id)
    return [
        {
            "id": e.id, "title": e.title, "question": e.question,
            "source_paradigm": e.source_paradigm, "target_paradigm": e.target_paradigm,
            "research_field": e.research_field, "architecture": e.architecture,
            "compression_technique": e.compression_technique,
            "shared_structure": e.shared_structure, "math_explanation": e.math_explanation,
            "evidence_quality": e.evidence_quality,
            "computational_benefit": e.computational_benefit,
            "implementation_complexity": e.implementation_complexity,
            "resource_estimate": e.resource_estimate,
            "limitations": e.limitations, "proposed_experiments": e.proposed_experiments,
            "publications": [
                {"title": papers[pid].title, "year": papers[pid].year, "doi": papers[pid].doi,
                 "url": papers[pid].url, "fulltext_verified": papers[pid].fulltext_verified}
                for pid in refs_by_entry.get(e.id, []) if pid in papers
            ],
        }
        for e in entries
    ]


class EntryCreate(BaseModel):
    question: str
    title: str = ""
    source_paradigm: str = ""
    target_paradigm: str = ""
    research_field: str = "compression"
    shared_structure: str = ""
    math_explanation: str = ""
    evidence_quality: str = "idea"
    limitations: list[str] = []
    proposed_experiments: list[str] = []


@router.post("/entries", status_code=201)
def create_entry(body: EntryCreate, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    entry = ResearchEntry(workspace_id=ctx.workspace.id, provenance="user", **body.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    audit(db, "research_entry.create", user=ctx.user, workspace_id=ctx.workspace.id, object_type="research_entry", object_id=entry.id)
    db.commit()
    return {"id": entry.id}


class HypothesisFromEntry(BaseModel):
    project_id: str | None = None


@router.post("/entries/{entry_id}/hypothesis", status_code=201)
def entry_to_hypothesis(
    entry_id: str,
    body: HypothesisFromEntry,
    ctx: WorkspaceCtx = Depends(get_ws_ctx),
    db: Session = Depends(get_db),
):
    from ..models import Hypothesis as HypothesisModel

    require_write_access(ctx.user)
    entry = db.get(ResearchEntry, entry_id)
    if entry is None or entry.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry_paper_titles = [
        p.title
        for p in db.query(Paper).join(SourceRef, SourceRef.paper_id == Paper.id)
        .filter(SourceRef.subject_type == "research_entry", SourceRef.subject_id == entry.id)
        .all()
    ]
    h = HypothesisModel(
        workspace_id=ctx.workspace.id,
        project_id=body.project_id,
        research_entry_id=entry.id,
        title=entry.title,
        statement=entry.question,
        rationale=entry.shared_structure,
        related_research=entry_paper_titles,
        success_criteria="Task retention >= 0.95 on the shared test split; measured artifact size ratio >= 2.0",
        failure_criteria="Retention < 0.90 or instability across seeds",
        compute_requirements="CPU demo (numpy) or GPU per engine selection",
        reproducibility_notes="Fixed seed; deterministic synthetic dataset; config snapshot stored with the run",
        status="draft",
        evidence_level="idea_only",
        created_by=ctx.user.id,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    audit(db, "hypothesis.draft_from_entry", user=ctx.user, workspace_id=ctx.workspace.id, object_type="hypothesis", object_id=h.id)
    db.commit()
    return {"id": h.id, "posted_at": datetime.now().isoformat()}



