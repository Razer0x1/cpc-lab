"""Knowledge graph assembly from live database objects.

Established edges (user-created source links, applied transformations) are flagged
established=True. Automatically inferred links (e.g. hypothesis -> experiment because
the experiment was submitted against it) are established=False with evidence strings.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import (
    BenchmarkRun, Dataset, Experiment, GraphEdge, Hypothesis, MLModel, Paper,
    ResearchEntry, SourceRef, Transformation,
)

NODE_META = {
    "hypothesis": {"color": "#8b7cf6", "label": "Hypothesis"},
    "experiment": {"color": "#4c7ef3", "label": "Experiment"},
    "paper": {"color": "#5eead4", "label": "Paper"},
    "model": {"color": "#f4bf4f", "label": "Model"},
    "dataset": {"color": "#e09e5e", "label": "Dataset"},
    "method": {"color": "#f472b6", "label": "Compression method"},
    "transformation": {"color": "#94a3b8", "label": "Transformation"},
    "benchmark": {"color": "#a3e635", "label": "Benchmark run"},
    "research_entry": {"color": "#c084fc", "label": "Research question"},
}


def build_graph(db: Session, workspace_id: str) -> dict:
    nodes: dict[str, dict] = {}

    def add_node(kind: str, oid: str, label: str, meta: dict | None = None) -> None:
        key = f"{kind}:{oid}"
        if key not in nodes:
            nodes[key] = {"id": key, "kind": kind, "label": label[:120], "meta": meta or {}, **NODE_META.get(kind, {"color": "#94a3b8"})}

    edges: list[dict] = []

    def add_edge(sk: str, sid: str, dk: str, did: str, relation: str, established: bool, evidence: str = "") -> None:
        edges.append({
            "id": f"{sk}:{sid}->{dk}:{did}:{relation}",
            "source": f"{sk}:{sid}", "target": f"{dk}:{did}",
            "relation": relation, "established": established, "evidence": evidence,
        })

    hypotheses = db.query(Hypothesis).filter_by(workspace_id=workspace_id).all()
    for h in hypotheses:
        add_node("hypothesis", h.id, h.title or (h.statement[:80] + ""), {"status": h.status, "evidence_level": h.evidence_level})
        if h.research_entry_id:
            e = db.get(ResearchEntry, h.research_entry_id)
            if e:
                add_node("research_entry", e.id, e.title or e.question[:80], {})
                add_edge("hypothesis", h.id, "research_entry", e.id, "derived_from", True, "hypothesis.research_entry_id set by user")
        for exp in db.query(Experiment).filter_by(hypothesis_id=h.id).all():
            add_node("experiment", exp.id, exp.name, {"status": exp.status, "verdict": exp.success_verdict})
            add_edge("hypothesis", h.id, "experiment", exp.id, "tested_by",
                     exp.status == "completed", f"experiment submitted against hypothesis (status={exp.status})")

    experiments = db.query(Experiment).filter_by(workspace_id=workspace_id).all()
    for exp in experiments:
        add_node("experiment", exp.id, exp.name, {"status": exp.status, "verdict": exp.success_verdict})
        summary = exp.result_summary or {}
        if summary.get("teacher_model_id"):
            t = db.get(MLModel, summary["teacher_model_id"])
            if t:
                add_node("model", t.id, t.name, {"family": t.family, "role": "teacher"})
                add_edge("experiment", exp.id, "model", t.id, "baseline", True, "experiment result summary links baseline model")
        if summary.get("target_model_id"):
            # reverse-engineering extraction: graph the target -> surrogate provenance
            t2 = db.get(MLModel, summary["target_model_id"])
            if t2:
                add_node("model", t2.id, t2.name, {"family": t2.family, "role": "extraction_target"})
                add_edge("experiment", exp.id, "model", t2.id, "baseline", True,
                         "experiment result summary links extraction target")
            if summary.get("surrogate_model_id"):
                sm = db.get(MLModel, summary["surrogate_model_id"])
                if sm:
                    add_node("model", sm.id, sm.name, {"family": sm.family, "role": "surrogate"})
                    add_edge("model", summary["target_model_id"], "model", sm.id, "extracted_into", True,
                             "black-box surrogate extraction (measured agreement / compression)")
        if summary.get("quantized_model_id"):
            qm = db.get(MLModel, summary["quantized_model_id"])
            if qm:
                add_node("model", qm.id, qm.name, {"family": qm.family, "role": "quantized"})
                if summary.get("source_model_id"):
                    add_edge("model", summary["source_model_id"], "model", qm.id, "quantized_into", True,
                             "measured quantization transformation record")
        if summary.get("student_model_id"):
            s = db.get(MLModel, summary["student_model_id"])
            if s:
                add_node("model", s.id, s.name, {"family": s.family, "role": "student"})
            if summary.get("teacher_model_id"):
                add_edge("model", summary["teacher_model_id"], "model", summary["student_model_id"], "distilled_into", True, "measured transformation record")
        if summary.get("dataset_id"):
            d = db.get(Dataset, summary["dataset_id"])
            if d:
                add_node("dataset", d.id, d.name, {"task_type": d.task_type, "synthetic": d.synthetic})
                add_edge("experiment", exp.id, "dataset", d.id, "evaluated_on", True, "experiment dataset_id")
        for tr in db.query(Transformation).filter_by(experiment_id=exp.id).all():
            add_node("transformation", tr.id, tr.method_key, {"status": tr.status})
            add_edge("experiment", exp.id, "transformation", tr.id, "applies", tr.status == "applied", f"transformation status={tr.status}")
        for br in db.query(BenchmarkRun).filter_by(experiment_id=exp.id).all():
            add_node("benchmark", br.id, f"{br.task} @ {br.primary_metric}", {"status": br.status})
            add_edge("experiment", exp.id, "benchmark", br.id, "benchmarked", br.status == "completed", "benchmark linked from experiment")

    papers = db.query(Paper).filter_by(workspace_id=workspace_id).all()
    for p in papers:
        add_node("paper", p.id, p.title, {"year": p.year, "venue": p.venue, "fulltext_verified": p.fulltext_verified})
    for ref in db.query(SourceRef).filter_by(workspace_id=workspace_id).all():
        add_edge(f"{'hypothesis' if ref.subject_type == 'hypothesis' else ref.subject_type}", ref.subject_id, "paper", ref.paper_id,
                 ref.relation, True, "manual/user source link with provenance")

    methods = db.query(Transformation).filter_by(workspace_id=workspace_id).all()
    for tr in methods:
        if tr.method_key:
            add_node("method", tr.method_key, tr.method_key, {})
            add_edge("method", tr.method_key, "transformation", tr.id, "realized_as", tr.status == "applied", "")

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "legend": NODE_META,
        "note": "established=True edges come from user-created links or recorded transformations; "
                "established=False edges are automatically inferred and unverified.",
    }
