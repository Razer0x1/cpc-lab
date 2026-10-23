"""Paper Library: scholarly search, ingestion into workspace, source-link management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Paper, SourceRef
from ..security import WorkspaceCtx, audit, get_ws_ctx, require_write_access
from ..services import papers as paper_search

router = APIRouter(prefix="/api/v1/papers", tags=["paper library"])


@router.get("/search")
def search(q: str, sources: str | None = None, limit: int = 8):
    srcs = [s.strip() for s in sources.split(",")] if sources else None
    return paper_search.search(q, srcs, limit)


class PaperIn(BaseModel):
    source: str = "manual"
    external_id: str = ""
    title: str
    authors: list[str] = []
    year: int | None = None
    venue: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    concepts: list[str] = []


@router.post("", status_code=201)
def ingest_paper(body: PaperIn, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    existing = (
        db.query(Paper)
        .filter_by(workspace_id=ctx.workspace.id, source=body.source, external_id=body.external_id)
        .one_or_none()
        if body.external_id
        else None
    )
    if existing is not None:
        return {"id": existing.id, "deduplicated": True}
    p = Paper(workspace_id=ctx.workspace.id, **body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    audit(db, "paper.ingest", user=ctx.user, workspace_id=ctx.workspace.id, object_type="paper", object_id=p.id)
    db.commit()
    return {"id": p.id, "deduplicated": False}


@router.get("")
def list_papers(ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    items = db.query(Paper).filter_by(workspace_id=ctx.workspace.id).order_by(Paper.created_at.desc()).all()
    return [
        {"id": p.id, "title": p.title, "authors": p.authors, "year": p.year, "venue": p.venue,
         "doi": p.doi, "url": p.url, "source": p.source, "external_id": p.external_id,
         "abstract": p.abstract[:400], "concepts": p.concepts,
         "fulltext_verified": p.fulltext_verified,
         "note": "bibliographic metadata; not full-text verified" if not p.fulltext_verified else ""}
        for p in items
    ]


class LinkIn(BaseModel):
    subject_type: str  # hypothesis | research_entry | transformation
    subject_id: str
    relation: str = "related"
    note: str = ""


@router.post("/{paper_id}/link", status_code=201)
def link_paper(paper_id: str, body: LinkIn, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    paper = db.get(Paper, paper_id)
    if paper is None or paper.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Paper not found")
    if body.subject_type not in ("hypothesis", "research_entry", "transformation", "experiment", "benchmark_run", "report"):
        raise HTTPException(status_code=422, detail="Unsupported subject_type")
    ref = SourceRef(workspace_id=ctx.workspace.id, subject_type=body.subject_type, subject_id=body.subject_id,
                    paper_id=paper_id, relation=body.relation, note=body.note)
    db.add(ref)
    db.commit()
    return {"id": ref.id, "established": True}


@router.delete("/{paper_id}/link/{ref_id}", status_code=204)
def unlink_paper(paper_id: str, ref_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    ref = db.get(SourceRef, ref_id)
    if ref is None or ref.workspace_id != ctx.workspace.id or ref.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="Link not found")
    db.delete(ref)
    db.commit()
    return None


