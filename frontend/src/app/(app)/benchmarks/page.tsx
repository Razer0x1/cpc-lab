"use client";
/** Benchmark Center: baseline-vs-compressed evaluation with CIs and Pareto analysis. */
import { useState, type FormEvent } from "react";
import { Gauge, Play } from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { api, useApi, fmtNum } from "@/lib/api";
import type { BenchCompare, BenchRunRow, BenchTask, MLModel } from "@/lib/types";
import { PageHeader, SectionCard, SimpleTable } from "@/components/shared";
import {
  Badge, Button, EmptyState, Field, Input, Select, StatusBadge, Skeleton,
} from "@/components/ui/primitives";

export default function BenchmarksPage() {
  const { data: tasks } = useApi<BenchTask[]>("/api/v1/benchmarks/tasks", 0);
  const { data: models } = useApi<MLModel[]>("/api/v1/workbench/models", 0);
  const { data: runs, error, loading, refresh } = useApi<BenchRunRow[]>("/api/v1/benchmarks/runs", 8000);
  const { data: compare } = useApi<BenchCompare>("/api/v1/benchmarks/compare", 10000);
  const [submitErr, setSubmitErr] = useState<string | null>(null);

  const evaluable = (models ?? []).filter((m) => m.artifact_uri);
  const pareto = (compare?.tradeoffs ?? []).filter((t) => t.quality !== null && t.artifact_bytes !== null);

  async function runBenchmark(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitErr(null);
    const form = e.currentTarget;
    const fd = new FormData(form);
    const modelId = String(fd.get("model_id") ?? "");
    const nRepeats = Number(fd.get("n_repeats") ?? 3);
    const seed = Number(fd.get("seed") ?? 11);
    try {
      await api.post("/api/v1/benchmarks/run", { model_id: modelId, n_repeats: nRepeats, seed, task: "synthetic_classification" });
      form.reset();
      refresh();
    } catch (err) {
      setSubmitErr(err instanceof Error ? err.message : "Benchmark failed");
    }
  }

  return (
    <>
      <PageHeader
        title="Benchmark Center"
        subtitle="Baseline-vs-compressed evaluation with bootstrap confidence intervals and Pareto frontier analysis. Available CPU task: synthetic_classification (measured, repeatable)."
      />

      <div className="grid gap-5 lg:grid-cols-[380px_minmax(0,1fr)]">
        <SectionCard title="Run benchmark" description="evaluates a registered model artifact">
          <form onSubmit={runBenchmark} className="space-y-3 p-4">
            <Field label="Model *" hint="models appear here after demo runs have registered artifacts">
              <Select name="model_id" required defaultValue="">
                <option value="" disabled>— select model —</option>
                {evaluable.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </Select>
            </Field>
            <Field label="Task" hint={tasks?.find((t) => t.key === "synthetic_classification")?.note ?? "measured accuracy on the synthetic split"}>
              <Select name="task" defaultValue="synthetic_classification" disabled>
                {(tasks ?? []).map((t) => (
                  <option key={t.key} value={t.key} disabled={t.key !== "synthetic_classification"}>
                    {t.key}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Repeats"><Input name="n_repeats" type="number" min={1} max={10} defaultValue={3} /></Field>
              <Field label="Seed"><Input name="seed" type="number" defaultValue={11} /></Field>
            </div>
            {submitErr ? <p className="text-xs text-red-400">{submitErr}</p> : null}
            {(models ?? []).length === 0 ? (
              <p className="text-2xs text-muted-foreground">No registered models yet — run a distillation demo first.</p>
            ) : null}
            <Button type="submit" size="sm" disabled={evaluable.length === 0}>
              <Play className="h-3.5 w-3.5" /> Run evaluation
            </Button>
          </form>
        </SectionCard>

        <SectionCard title={`Benchmark runs (${runs?.length ?? 0})`} description="mean accuracy with 95% bootstrap CI">
          {loading && !runs ? (
            <div className="space-y-2 p-4">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
          ) : error ? (
            <p className="p-4 text-xs text-red-400">{error}</p>
          ) : (runs ?? []).length === 0 ? (
            <div className="p-4">
              <EmptyState title="No benchmark runs yet" description="Register a model via a demo experiment, then evaluate it here." />
            </div>
          ) : (
            <SimpleTable head={["Model", "Task", "Status", "Accuracy", "95% CI", "Latency (warm)", "Repeats"]}>
              {(runs ?? []).map((r) => (
                <tr key={r.id} className="hover:bg-muted/40">
                  <td className="px-4 py-2 font-medium">{r.model_name ?? r.model_id.slice(0, 8)}</td>
                  <td className="px-4 py-2 text-muted-foreground"><code className="text-2xs">{r.task}</code></td>
                  <td className="px-4 py-2"><StatusBadge status={r.status} /></td>
                  <td className="px-4 py-2 tabular-nums">{r.mean_accuracy === null ? "—" : fmtNum(r.mean_accuracy, 4)}</td>
                  <td className="px-4 py-2 tabular-nums text-muted-foreground">
                    {r.ci95 ? `[${fmtNum(r.ci95[0], 3)}, ${fmtNum(r.ci95[1], 3)}]` : "—"}
                  </td>
                  <td className="px-4 py-2 tabular-nums">{r.latency_warm_ms === null ? "—" : `${fmtNum(r.latency_warm_ms, 2)} ms`}</td>
                  <td className="px-4 py-2 tabular-nums text-muted-foreground">{r.n_repeats ?? "—"}</td>
                </tr>
              ))}
            </SimpleTable>
          )}
        </SectionCard>
      </div>

      <SectionCard
        className="mt-5"
        title="Comparison & trade-offs"
        description="quality vs artifact size; front points lie on the measured Pareto frontier (higher accuracy, smaller artifact)"
      >
        {pareto.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="Not enough benchmark data"
              description="Evaluate both the teacher and the compressed student (from demo artifacts) to populate the trade-off plot and Pareto frontier."
            />
          </div>
        ) : (
          <div className="grid gap-5 p-4 lg:grid-cols-2">
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="artifact_bytes" name="Artifact bytes" type="number" tick={{ fill: "hsl(var(--muted-foreground))" }} scale="log" domain={["auto", "auto"]} />
                  <YAxis dataKey="quality" name="Accuracy" type="number" domain={[0.5, 1]} tick={{ fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip
                    contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
                    formatter={(v: number | string, name: string) => (name === "Accuracy" ? fmtNum(Number(v), 3) : Number(v).toLocaleString())}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Scatter name="On Pareto front" data={pareto.filter((p) => p.on_pareto_front)} fill="#34d399" />
                  <Scatter name="Dominated" data={pareto.filter((p) => !p.on_pareto_front)} fill="#64748b" />
                </ScatterChart>
              </ResponsiveContainer>
              <p className="mt-1 text-2xs text-muted-foreground">log-scale artifact bytes vs measured accuracy (synthetic task)</p>
            </div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pareto} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="model_name" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }} interval={0} angle={-14} dy={8} />
                  <YAxis tick={{ fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="latency_ms" name="Warm latency (ms)" radius={[4, 4, 0, 0]}>
                    {pareto.map((p, i) => (
                      <Cell key={i} fill={p.on_pareto_front ? "#18A0FB" : "#B02FF5"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="mt-1 text-2xs text-muted-foreground">warm latency per model (host-specific — see report limitations)</p>
            </div>
          </div>
        )}
        {compare?.comparisons ? (
          <SimpleTable head={["Model", "Role", "Accuracy", "95% CI", "Cross-entropy", "Latency (warm)"]}>
            {compare.comparisons.map((c) => (
              <tr key={c.id} className="hover:bg-muted/40">
                <td className="px-4 py-1.5 font-medium">{c.model_name}</td>
                <td className="px-4 py-1.5">
                  <Badge tone={c.role === "baseline" ? "blue" : c.role === "compressed" ? "violet" : "neutral"}>{c.role}</Badge>
                </td>
                <td className="px-4 py-1.5 tabular-nums">{c.accuracy === null ? "—" : fmtNum(c.accuracy, 4)}</td>
                <td className="px-4 py-1.5 tabular-nums text-muted-foreground">
                  {c.accuracy_ci95 ? `[${fmtNum(c.accuracy_ci95[0], 3)}, ${fmtNum(c.accuracy_ci95[1], 3)}]` : "—"}
                </td>
                <td className="px-4 py-1.5 tabular-nums text-muted-foreground">{c.cross_entropy === null ? "—" : fmtNum(c.cross_entropy, 4)}</td>
                <td className="px-4 py-1.5 tabular-nums">{c.latency_warm_ms === null ? "—" : `${fmtNum(c.latency_warm_ms, 2)} ms`}</td>
              </tr>
            ))}
          </SimpleTable>
        ) : null}
        {compare?.note ? (
          <p className="px-4 py-3 text-2xs text-muted-foreground">
            <Gauge className="mr-1 inline h-3 w-3" />{compare.note}
          </p>
        ) : null}
      </SectionCard>
    </>
  );
}
