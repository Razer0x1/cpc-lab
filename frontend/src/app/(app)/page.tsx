"use client";
import Link from "next/link";
import { useApi } from "@/lib/api";
import type { Overview } from "@/lib/types";
import { fmtBytes, fmtNum } from "@/lib/api";
import { PageHeader, StatCard, StatCardSkeleton, SectionCard, SimpleTable } from "@/components/shared";
import { StatusBadge, Badge, EmptyState } from "@/components/ui/primitives";

export default function OverviewPage() {
  const { data, error, loading, refresh } = useApi<Overview>("/api/v1/overview", 10000);

  if (loading && !data) {
    return (
      <>
        <PageHeader title="Overview" subtitle="Workspace health at a glance (database-backed; no sample numbers)." />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => <StatCardSkeleton key={i} />)}
        </div>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <PageHeader title="Overview" />
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          Failed to load overview: {error ?? "unknown error"}
        </p>
        <button onClick={refresh} className="mt-2 text-xs underline">retry</button>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="All numbers below are computed from the workspace database — averages use only measured metric rows of completed experiments."
      />

      {data.empty_state_hint ? (
        <div className="mb-5 rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-3 text-xs text-sky-300">
          {data.empty_state_hint}
        </div>
      ) : null}

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Experiments completed" value={data.totals.experiments_completed} hint={`${data.totals.experiments_running} running · ${data.totals.experiments_queued} queued · ${data.totals.experiments_failed} failed`} />
        <StatCard label="Hypotheses" value={data.totals.hypotheses_total} hint={`${data.totals.hypotheses_validated} experimentally evidenced · ${data.totals.hypotheses_pending} awaiting runs`} tone="violet" />
        <StatCard label="Research entries" value={data.totals.research_entries} hint={`${data.totals.projects} active projects`} tone="amber" />
        <StatCard label="Methods available" value={data.totals.methods_available} hint="compression method registry" tone="green" />
        <StatCard label="Avg task retention" value={data.averages.task_retention === null ? "—" : fmtNum(data.averages.task_retention)} hint={data.averages.task_retention === null ? "no measured data yet" : "measured metric rows only"} />
        <StatCard label="Avg compression ratio" value={data.averages.compression_ratio === null ? "—" : fmtNum(data.averages.compression_ratio, 2)} hint={data.averages.compression_ratio === null ? "no measured data yet" : "artifacts measured in bytes"} />
        <StatCard label="Avg latency speedup" value={data.averages.latency_speedup === null ? "—" : fmtNum(data.averages.latency_speedup, 2)} hint="host-specific; see limitations" />
        <StatCard label="Benchmarks completed" value={data.totals.benchmarks_completed} hint={`${data.totals.artifacts} artifacts · ${fmtBytes(data.storage.artifact_bytes)} stored`} tone="violet" />
      </section>

      {data.compute_status.note ? (
        <p className="mt-4 text-2xs text-muted-foreground">
          Compute: <span className="text-foreground">{data.compute_status.runner_backend}</span> — {data.compute_status.note}
          &nbsp;·&nbsp; {data.averages.note}
        </p>
      ) : null}

      <section className="mt-6 grid gap-5 lg:grid-cols-2">
        <SectionCard title="Recent experiments" description="newest first">
          {data.recent_experiments.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title="No experiments yet"
                description="Run the flagship CPU demo: teacher→student knowledge distillation on the synthetic benchmark. It completes in seconds."
                action={<Link href="/experiments" className="text-xs text-[#18A0FB] hover:underline">Open Experiment Lab →</Link>}
              />
            </div>
          ) : (
            <SimpleTable head={["Name", "Kind", "Status", "Verdict", "Progress"]}>
              {data.recent_experiments.map((e) => (
                <tr key={e.id} className="hover:bg-muted/40">
                  <td className="px-4 py-2">
                    <Link href={`/experiments/${e.id}`} className="text-[#18A0FB] hover:underline">{e.name}</Link>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">{e.kind}</td>
                  <td className="px-4 py-2"><StatusBadge status={e.status} /></td>
                  <td className="px-4 py-2">{e.verdict ? <StatusBadge status={e.verdict} /> : <span className="text-muted-foreground">—</span>}</td>
                  <td className="px-4 py-2 tabular-nums text-muted-foreground">{Math.round((e.progress ?? 0) * 100)}%</td>
                </tr>
              ))}
            </SimpleTable>
          )}
        </SectionCard>

        <SectionCard title="Findings" description="completed runs with measured outcome">
          {data.findings.length === 0 ? (
            <div className="p-4 text-xs text-muted-foreground">No completed experiments yet.</div>
          ) : (
            <div className="divide-y divide-border">
              {data.findings.map((f) => (
                <div key={f.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <Link href={`/experiments/${f.id}`} className="truncate text-xs font-medium hover:text-[#18A0FB]">{f.name}</Link>
                    <p className="text-2xs text-muted-foreground">
                      retention {f.retention === null ? "—" : fmtNum(f.retention, 2)} · ratio {f.ratio === null ? "—" : fmtNum(f.ratio, 1)}×
                    </p>
                  </div>
                  {f.verdict ? <StatusBadge status={f.verdict} /> : null}
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard title="Pending hypotheses" description="drafts and approved-but-untested ideas">
          {data.pending_hypotheses.length === 0 ? (
            <div className="p-4 text-xs text-muted-foreground">
              Nothing pending. <Link href="/hypotheses" className="text-[#18A0FB] hover:underline">Draft a hypothesis →</Link>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {data.pending_hypotheses.map((h) => (
                <div key={h.id} className="flex items-center justify-between gap-2 px-4 py-3">
                  <span className="truncate text-xs">{h.title}</span>
                  <span className="flex shrink-0 gap-1.5">
                    <Badge tone="neutral">{h.status}</Badge>
                    <Badge tone={h.evidence_level === "idea_only" ? "amber" : "blue"}>{h.evidence_level}</Badge>
                  </span>
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard title="Workspace activity" description="audit trail (latest 12 events)">
          {data.activity.length === 0 ? (
            <div className="p-4 text-xs text-muted-foreground">No activity recorded yet.</div>
          ) : (
            <ol className="relative space-y-3 px-4 py-3">
              {data.activity.map((a, i) => (
                <li key={`${a.ts}-${a.kind}-${i}`} className="relative pl-4 before:absolute before:left-1 before:top-1.5 before:h-1.5 before:w-1.5 before:rounded-full before:bg-[#18A0FB]">
                  <p className="text-xs">{a.label}</p>
                  <p className="text-2xs text-muted-foreground">
                    {new Date(a.ts).toLocaleString()} · {a.kind === "experiment_created" ? "created" : a.kind.replace("experiment_", "")} · <StatusBadgeFire status={a.status} />
                  </p>
                </li>
              ))}
            </ol>
          )}
        </SectionCard>
      </section>
    </>
  );
}

function StatusBadgeFire({ status }: { status: string }) {
  const safe = ["completed", "failed", "cancelled", "successful", "unsuccessful", "inconclusive", "queued", "running", "created", "paused"].includes(status);
  return safe ? <StatusBadge status={status} /> : <Badge tone="neutral">{status}</Badge>;
}
