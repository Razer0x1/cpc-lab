/** Shared API response types (mirrors backend routers). */

export type User = { id: string; email: string; display_name: string; is_admin: boolean };
export type Workspace = { id: string; name: string; slug: string; role?: string };
export type Me = { user: User; workspace: Workspace; role: string };
export type LoginResponse = { access_token: string; token_type: string; user: User };

export type Overview = {
  totals: {
    projects: number; research_entries: number;
    experiments_completed: number; experiments_running: number; experiments_queued: number; experiments_failed: number;
    hypotheses_total: number; hypotheses_validated: number; hypotheses_pending: number;
    methods_available: number; benchmarks_completed: number;
    artifacts: number;
  };
  averages: { compression_ratio: number | null; task_retention: number | null; latency_speedup: number | null; note: string };
  storage: { artifact_bytes: number; artifact_count: number };
  compute_status: { runner_backend: string; note: string };
  recent_experiments: Array<{ id: string; name: string; kind: string; status: string; verdict: string | null; created_at: string; progress: number }>;
  findings: Array<{ id: string; name: string; verdict: string | null; retention: number | null; ratio: number | null; finished_at: string | null }>;
  pending_hypotheses: Array<{ id: string; title: string; status: string; evidence_level: string }>;
  benchmarks: Array<{ id: string; task: string; primary_metric: string; status: string; model_id: string; value: number | null; created_at: string }>;
  activity: Array<{ ts: string; kind: string; label: string; status: string; id: string }>;
  empty_state_hint: string;
};

export type ResearchEntry = {
  id: string; title: string; question: string;
  source_paradigm: string; target_paradigm: string;
  research_field: string; architecture: string; compression_technique: string;
  shared_structure: string; math_explanation: string; evidence_quality: string;
  computational_benefit: string; implementation_complexity: string; resource_estimate: string;
  limitations: string[]; proposed_experiments: string[];
  publications: Array<{ title: string; year: number | null; doi: string; url: string; fulltext_verified: boolean }>;
};

export type Hypothesis = {
  id: string; title: string; statement: string; status: string; evidence_level: string;
  evidence_note: string; success_criteria: string; failure_criteria: string;
  rationale: string; math_formulation: string;
  related_research: string[]; baselines: string[]; ablations: string[];
  expected_outcomes: string; required_datasets: string[]; required_models: string[];
  compute_requirements: string; reproducibility_notes: string;
  experiments: Array<{ id: string; name: string; status: string; verdict: string | null }>;
  created_at: string; updated_at: string;
};

export type ExperimentRow = {
  id: string; name: string; kind: string; status: string; progress: number; seed: number;
  hypothesis_id: string | null; verdict: string | null; error: string | null;
  config: Record<string, unknown>; config_version: number; budgets: Record<string, unknown>;
  runner: string; engine_note: string | null; result_summary: Record<string, unknown>;
  created_at: string; started_at: string | null; finished_at: string | null;
};

export type ExperimentDetail = ExperimentRow & {
  runs: Array<{ id: string; seq: number; seed: number; status: string; started_at: string | null; finished_at: string | null }>;
  metrics: Array<{ name: string; value: number; unit: string; stage: string; seed: number; extra: Record<string, unknown> }>;
  artifacts: Array<{ id: string; kind: string; filename: string; sha256: string; size_bytes: number }>;
  log_count: number;
};

export type MetricRow = ExperimentDetail["metrics"][number];

export type Method = {
  id: string; key: string; name: string; category: string; description: string;
  config_schema: Record<string, unknown>; prereqs: string[]; supported_models: string[];
  limitations: string[]; engine: string; runnable_now: boolean; runnable_note: string;
};

export type MLModel = {
  id: string; name: string; family: string; revision: string; source: string;
  params_count: number | null; artifact_uri: string | null; synthetic: boolean; notes: string;
};

export type BenchTask = { key: string; note: string };

export type BenchRunRow = {
  id: string; task: string; status: string; seed: number; model_id: string; model_name: string | null;
  primary_metric: string; value: number | null; ci95: [number, number] | null;
  mean_accuracy: number | null; latency_warm_ms: number | null; n_repeats: number | null; created_at: string;
};

export type BenchCompare = {
  comparisons: Array<{
    id: string; task: string; model_id: string; role: string; model_name: string;
    accuracy: number | null; accuracy_ci95: [number, number] | null; cross_entropy: number | null;
    latency_warm_ms: number | null; n_repeats: number | null;
  }>;
  tradeoffs: Array<{
    benchmark_id: string; model_id: string; model_name: string;
    quality: number | null; artifact_bytes: number | null; latency_ms: number | null;
    role: string; on_pareto_front: boolean;
  }>;
  multi_run_summary: { count: number; mean: number; std: number; min: number; max: number } | null;
  note: string;
};

export type ReportRow = { id: string; title: string; format: string; experiment_id: string; artifact_id: string; created_at: string };

export type Paper = {
  id?: string; source: string; external_id: string; title: string; authors: string[];
  year: number | null; venue: string; doi: string; url: string; abstract: string;
  concepts: string[]; fulltext_verified?: boolean; note?: string;
};

export type GraphData = {
  nodes: Array<{ id: string; kind: string; label: string; meta: Record<string, unknown>; color: string }>;
  edges: Array<{ id: string; source: string; target: string; relation: string; established: string; evidence: string }>;
};

export type AssistantChat = {
  content: string; meta: Record<string, unknown>; conversation_id: string;
};

export type AssistantStatus = {
  configured: boolean;
  provider: string | null;
  base_url: string | null;
  model: string | null;
  api_key_env: string | null;
  has_key: boolean;
  mode: "llm" | "offline_rules";
  setup_help: string;
};

export type ComputeResourceRow = {
  id: string; name: string; kind: string; status: string;
  limits: Record<string, unknown>; utilization: Record<string, unknown>; updated_at: string;
};

export type EnvironmentInfo = {
  env: string; database: string; storage_backend: string; job_backend: string;
  engine_torch: boolean; assistant_provider: string; rate_limit_per_minute: number;
};
