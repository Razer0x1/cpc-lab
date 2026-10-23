"""Normalized database models. Large binaries live in object storage (artifacts table stores URIs only)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    workspaces: Mapped[list["Workspace"]] = relationship(
        secondary="workspace_members", viewonly=True, lazy="selectin"
    )


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_wsmember"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="member")  # owner | member | viewer


class ResearchProject(TimestampMixin, Base):
    __tablename__ = "research_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    research_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))


class Paper(TimestampMixin, Base):
    __tablename__ = "papers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "source", "external_id", name="uq_paper_source"),
        Index("ix_papers_title", "title"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # openalex | arxiv | crossref | manual
    external_id: Mapped[str] = mapped_column(String(200), default="")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer)
    venue: Mapped[str] = mapped_column(String(300), default="")
    doi: Mapped[str] = mapped_column(String(120), default="")
    url: Mapped[str] = mapped_column(String(600), default="")
    abstract: Mapped[str] = mapped_column(Text, default="")
    concepts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Publication metadata only; full-text verification is a separate, explicit claim.
    fulltext_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    added_by: Mapped[str | None] = mapped_column(String(36))


class SourceRef(Base):
    """Typed link between any workspace object and a paper. Provenance record."""
    __tablename__ = "source_refs"
    __table_args__ = (UniqueConstraint("workspace_id", "subject_type", "subject_id", "paper_id", "relation", name="uq_sourceref"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    subject_type: Mapped[str] = mapped_column(String(40), index=True)  # hypothesis | research_entry | transformation | report
    subject_id: Mapped[str] = mapped_column(String(36), index=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    relation: Mapped[str] = mapped_column(String(40), default="supports")  # supports | related | contradicts | prior_work
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ResearchEntry(TimestampMixin, Base):
    """Curated cross-paradigm research question catalog (Research Explorer)."""
    __tablename__ = "research_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("research_projects.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="")
    source_paradigm: Mapped[str] = mapped_column(String(80), index=True, default="")
    target_paradigm: Mapped[str] = mapped_column(String(80), index=True, default="")
    research_field: Mapped[str] = mapped_column(String(80), index=True, default="")  # compression | representation | reasoning | ...
    architecture: Mapped[str] = mapped_column(String(80), index=True, default="")
    compression_technique: Mapped[str] = mapped_column(String(80), index=True, default="")
    shared_structure: Mapped[str] = mapped_column(Text, default="")
    math_explanation: Mapped[str] = mapped_column(Text, default="")  # LaTeX/algorithmic description
    evidence_quality: Mapped[str] = mapped_column(String(40), index=True, default="theoretical")  # anecdotal|theoretical|replicated|established
    computational_benefit: Mapped[str] = mapped_column(Text, default="")
    implementation_complexity: Mapped[str] = mapped_column(String(40), default="medium")  # low|medium|high
    resource_estimate: Mapped[str] = mapped_column(String(40), default="low")  # low|medium|high
    limitations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    proposed_experiments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    publication_year_from: Mapped[int | None] = mapped_column(Integer)
    provenance: Mapped[str] = mapped_column(String(40), default="curated")  # curated | inferred | user


class Hypothesis(TimestampMixin, Base):
    __tablename__ = "hypotheses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("research_projects.id", ondelete="SET NULL"))
    research_entry_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("research_entries.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), default="")
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="")
    math_formulation: Mapped[str] = mapped_column(Text, default="")
    related_research: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    expected_outcomes: Mapped[str] = mapped_column(Text, default="")
    competing_explanations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_datasets: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_models: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    baselines: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    ablations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    success_criteria: Mapped[str] = mapped_column(Text, default="")  # machine-readable evaluable criteria
    failure_criteria: Mapped[str] = mapped_column(Text, default="")
    compute_requirements: Mapped[str] = mapped_column(Text, default="")
    reproducibility_notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft | approved | rejected
    # Idea only < Literature supported < Implemented < Experimentally tested < Independently reproduced
    evidence_level: Mapped[str] = mapped_column(String(30), default="idea_only", index=True)
    created_by: Mapped[str | None] = mapped_column(String(36))


class MLModel(TimestampMixin, Base):
    __tablename__ = "models"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    family: Mapped[str] = mapped_column(String(80), default="other")  # transformer | mlp | ssm | rnn | symbolic ...
    revision: Mapped[str] = mapped_column(String(100), default="v1")
    source: Mapped[str] = mapped_column(String(30), default="local")  # huggingface | local | synthetic
    params_count: Mapped[int | None] = mapped_column(Integer)
    artifact_uri: Mapped[str] = mapped_column(String(600), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class Dataset(TimestampMixin, Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[str] = mapped_column(String(40), default="classification", index=True)
    num_examples: Mapped[int] = mapped_column(Integer, default=0)
    split_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # train/val/test ratios, seeds
    generator_key: Mapped[str] = mapped_column(String(80), default="")  # reproducible synthetic generator id
    artifact_uri: Mapped[str] = mapped_column(String(600), default="")
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class CompressionMethod(Base):
    """Registry of compression/optimization methods with config schemas."""
    __tablename__ = "compression_methods"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(60), index=True, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    prereqs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    supported_models: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    config_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # JSON-schema-ish field constraints
    limitations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    engine: Mapped[str] = mapped_column(String(40), default="builtin_numpy")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Experiment(TimestampMixin, Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("research_projects.id", ondelete="SET NULL"))
    hypothesis_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("hypotheses.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), default="distillation_demo", index=True)  # runner task key
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    # queued | running | paused | cancelling | cancelled | failed | completed
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # versioned snapshot
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    baseline_model_id: Mapped[str | None] = mapped_column(String(36))
    candidate_model_id: Mapped[str | None] = mapped_column(String(36))
    dataset_id: Mapped[str | None] = mapped_column(String(36))
    budgets: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # max_seconds, max_mb_ram ...
    seed: Mapped[int] = mapped_column(Integer, default=7)
    runner_kind: Mapped[str] = mapped_column(String(20), default="thread")  # thread | celery | simulated
    engine_note: Mapped[str] = mapped_column(String(100), default="")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    result_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    success_verdict: Mapped[str | None] = mapped_column(String(20))  # successful | unsuccessful | inconclusive
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(36))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    experiment_id: Mapped[str] = mapped_column(String(36), ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)  # run number, supports multi-seed
    seed: Mapped[int] = mapped_column(Integer, default=7)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    log_uri: Mapped[str] = mapped_column(String(600), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class ExperimentLog(Base):
    __tablename__ = "experiment_logs"
    __table_args__ = (Index("ix_explogs_exp_seq", "experiment_id", "seq"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    experiment_id: Mapped[str] = mapped_column(String(36), ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)


class Transformation(TimestampMixin, Base):
    """Typed, versioned transformation specification (preconditions/invariants/failure modes)."""
    __tablename__ = "transformations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(String(36))
    spec: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # {type, version, params, ...}
    spec_version: Mapped[int] = mapped_column(Integer, default=1)
    method_key: Mapped[str] = mapped_column(String(60), default="", index=True)
    preconditions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    invariants: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    failure_modes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    compat_checks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # [{name, passed, detail}]
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | compatible | applied | rejected
    input_model_id: Mapped[str | None] = mapped_column(String(36))
    output_model_id: Mapped[str | None] = mapped_column(String(36))


class Metric(TimestampMixin, Base):
    __tablename__ = "metrics"
    __table_args__ = (Index("ix_metrics_owner", "workspace_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("experiment_runs.id", ondelete="CASCADE"), index=True)
    benchmark_run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30), default="")
    stage: Mapped[str] = mapped_column(String(20), default="measured")  # measured | theoretical | simulated | baseline
    seed: Mapped[int | None] = mapped_column(Integer)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class BenchmarkRun(TimestampMixin, Base):
    __tablename__ = "benchmark_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("experiments.id", ondelete="SET NULL"), index=True)
    model_id: Mapped[str] = mapped_column(String(36), nullable=False)
    dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, default=7)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    primary_metric: Mapped[str] = mapped_column(String(40), default="accuracy")
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # value, ci95, per_step, hardware
    error: Mapped[str | None] = mapped_column(Text)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("experiments.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)  # model | dataset | log | report | config | eval
    uri: Mapped[str] = mapped_column(String(600), nullable=False)
    filename: Mapped[str] = mapped_column(String(300), default="")
    sha256: Mapped[str] = mapped_column(String(64), index=True, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class ComputeResource(TimestampMixin, Base):
    __tablename__ = "compute_resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="cpu")  # cpu | gpu | api
    status: Mapped[str] = mapped_column(String(20), default="online")  # online | busy | offline
    limits: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    utilization: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    object_type: Mapped[str] = mapped_column(String(40), default="")
    object_id: Mapped[str | None] = mapped_column(String(36))
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ip: Mapped[str] = mapped_column(String(64), default="")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (UniqueConstraint("workspace_id", "src_type", "src_id", "dst_type", "dst_id", "relation", name="uq_graph_edge"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    src_type: Mapped[str] = mapped_column(String(40), index=True)
    src_id: Mapped[str] = mapped_column(String(36), index=True)
    dst_type: Mapped[str] = mapped_column(String(40), index=True)
    dst_id: Mapped[str] = mapped_column(String(36), index=True)
    relation: Mapped[str] = mapped_column(String(60), default="related_to")
    established: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # True = verified/user-created; False = inferred
    evidence: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(36), index=True)
    benchmark_run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    format: Mapped[str] = mapped_column(String(10), default="markdown")  # markdown | html | pdf
    artifact_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("artifacts.id", ondelete="SET NULL"))
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class AssistantConversation(TimestampMixin, Base):
    __tablename__ = "assistant_conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    messages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # [{role, content, ts, meta}]
