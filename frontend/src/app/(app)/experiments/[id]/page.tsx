"use client";
/** Experiment detail: measured metrics, artifacts (SHA-256), logs stream, peer comparison. */
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Ban, Download, Pause, Play, RotateCcw, Timer } from "lucide-react";
import { api, useApi, fmtBytes, fmtDate, fmtNum } from "@/lib/api";
import type { ExperimentDetail } from "@/lib/types";
import { SectionCard, SimpleTable } from "@/components/shared";
import {
  Badge, Button, Spinner, StatusBadge, Progress,
} from "@/components/ui/primitives";

type LogLine = { seq: number; ts: string; level: string; message: string };

type PeerRow = {
  id: string; name: string; kind: string; verdict: string | null;
  retention: number | null; ratio: number | null;
  accuracy_baseline: number | null; accuracy_compressed: number | null;
  latency_speedup: number | null; is_current: boolean;
};

export default function ExperimentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const { data: peers } = useApi<{ comparison: PeerRow[] }>(
    id ? `/api/v1/experiments/${id}/compare` : null, 15000
  );
  const { data, error, loading, refresh } = useApi<ExperimentDetail>(
    id ? `/api/v1/experiments/${id}` : null,
    3000
  );

  const [busy, setBusy] = useState(false);
  const [actionErr, setActionErr] = useState<string | null>(null);

  if (!id || (!data && loading)) {
    return <div className="flex items-center gap-2 p-10 text-sm text-muted-foreground"><Spinner /> Loading experiment…</div>;
  }
  if (error || !data) {
    return (
      <SectionCard title="Experiment">
        <p className="p-4 text-xs text-red-400">{error ?? "Not found"}</p>
        <div className="p-4 pt-0">
          <Button variant="outline" size="sm" onClick={refresh}>Retry load</Button>
        </div>
      </SectionCard>
    );
  }

  const active = ["queued", "running"].includes(data.status);

  async function action(path: string) {
    setBusy(true);
    setActionErr(null);
    try {
      await api.post(`/api/v1/experiments/${id}/${path}`);
      refresh();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  const summary = data.result_summary ?? {};

  return (
    <>
      <div className="mb-5">
        <Link href="/experiments" className="text-2xs text-muted-foreground hover:text-foreground">&larr; Experiment Lab</Link>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="text-lg font-semibold tracking-tight">{data.name}</h1>
          <StatusBadge status={data.status} />
          {data.verdict ? <StatusBadge status={data.verdict} /> : null}
          <Badge tone="neutral"><code className="text-2xs">{data.kind}</code></Badge>
          <Badge tone="neutral">runner: {data.runner}</Badge>
          <Badge tone="neutral">seed {data.seed}</Badge>
        </div>
        <p className="mt-1 text-2xs text-muted-foreground">
          created {fmtDate(data.created_at)}
          {data.started_at ? ` · started ${fmtDate(data.started_at)}` : ""}
          {data.finished_at ? ` · finished ${fmtDate(data.finished_at)}` : ""}
        </p>
      </div>

      {active ? <Progress value={data.progress ?? 0} className="mb-4" /> : null}
      {data.error ? (
        <p className="mb-4 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          <span className="font-medium">Error:</span> {data.error}
        </p>
      ) : null}
      {actionErr ? (
        <p className="mb-4 text-xs text-red-400">{actionErr}</p>
      ) : null}

      <div className="mb-5 flex flex-wrap gap-2">
        {data.status === "created" ? (
          <>
            <Button size="sm" disabled={busy} onClick={() => action("run")}><Play className="h-3.5 w-3.5" /> Queue</Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => action("run_sync")}><Timer className="h-3.5 w-3.5" /> Run synchronously</Button>
          </>
        ) : null}
        {active ? (
          <>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => action("pause")}><Pause className="h-3.5 w-3.5" /> Pause</Button>
            <Button size="sm" variant="ghost" className="text-red-400" disabled={busy} onClick={() => action("cancel")}><Ban className="h-3.5 w-3.5" /> Cancel</Button>
          </>
        ) : null}
        {data.status === "paused" ? (
          <Button size="sm" disabled={busy} onClick={() => action("resume")}><Play className="h-3.5 w-3.5" /> Resume</Button>
        ) : null}
        {["failed", "cancelled", "paused"].includes(data.status) ? (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => action("retry")}>
            <RotateCcw className="h-3.5 w-3.5" /> Reset for re-run
          </Button>
        ) : null}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <SectionCard title="Config snapshot" description={`version ${data.config_version} · immutable during runs`}>
          <pre className="overflow-x-auto p-4 text-[11px] leading-relaxed text-muted-foreground scrollbar-thin">
            {JSON.stringify({ config: data.config, budgets: data.budgets }, null, 2)}
          </pre>
        </SectionCard>

        <SectionCard title="Result summary" description="measured-only (no fabricated values)">
          {Object.keys(summary).length === 0 ? (
            <p className="p-4 text-xs text-muted-foreground">No results yet — the run has not completed.</p>
          ) : (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 p-4 text-xs">
              {Object.entries(summary as Record<string, unknown>).map(([k, v]) => (
                <div key={k} className="min-w-0">
                  <dt className="truncate text-2xs uppercase tracking-wide text-muted-foreground">{k.replace(/_/g, " ")}</dt>
                  <dd className="truncate font-medium tabular-nums">
                    {fmtAnyValue(k, v)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </SectionCard>

        <SectionCard title={`Metrics (${data.metrics.length})` } description="name : stage — measured rows come from real computation">
          {data.metrics.length === 0 ? (
            <p className="p-4 text-xs text-muted-foreground">No metrics recorded.</p>
          ) : (
            <SimpleTable head={["Metric", "Stage", "Value", "Unit", "Seed"]}>
              {data.metrics.map((m, i) => (
                <tr key={`${m.name}:${m.stage}:${i}`} className="hover:bg-muted/40">
                  <td className="px-4 py-1.5 font-mono text-2xs">{m.name}</td>
                  <td className="px-4 py-1.5"><Badge tone={m.stage === "measured" ? "green" : "neutral"}>{m.stage}</Badge></td>
                  <td className="px-4 py-1.5 tabular-nums">{fmtNum(m.value, 5)}</td>
                  <td className="px-4 py-1.5 text-muted-foreground">{m.unit || "—"}</td>
                  <td className="px-4 py-1.5 tabular-nums text-muted-foreground">{m.seed}</td>
                </tr>
              ))}
            </SimpleTable>
          )}
        </SectionCard>

        <SectionCard title={`Artifacts (${data.artifacts.length})`} description="SHA-256 verified integrity">
          {data.artifacts.length === 0 ? (
            <p className="p-4 text-xs text-muted-foreground">No artifacts produced.</p>
          ) : (
            <div className="divide-y divide-border">
              {data.artifacts.map((a) => (
                <div key={a.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-xs">
                  <div className="min-w-0">
                    <p className="font-medium">{a.filename}</p>
                    <p className="truncate text-2xs text-muted-foreground">
                      {a.kind} · {fmtBytes(a.size_bytes)} · <code>{a.sha256.slice(0, 12)}…</code>
                    </p>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => {
                    void api.download(`/api/v1/artifacts/${a.id}/download`, a.filename || "artifact.npz");
                  }}>
                    <Download className="h-3 w-3" /> Download
                  </Button>
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        <LogsCard id={id} logCount={data.log_count} />

        <SectionCard title="Peer comparison" description="all completed experiments in the workspace">
          {peers && peers.comparison ? (
            <SimpleTable head={["Name", "Kind", "Verdict", "Retention", "Ratio", "Latency speedup"]}>
              {peers.comparison.map((p) => (
                <tr key={p.id} className={p.is_current ? "bg-primary/5" : "hover:bg-muted/40"}>
                  <td className="px-4 py-1.5">
                    {p.is_current ? <span className="font-medium">{p.name}</span> : (
                      <Link href={`/experiments/${p.id}`} className="text-[#18A0FB] hover:underline">{p.name}</Link>
                    )}
                  </td>
                  <td className="px-4 py-1.5 text-muted-foreground">{p.kind}</td>
                  <td className="px-4 py-1.5">{p.verdict ? <StatusBadge status={p.verdict} /> : <span className="text-muted-foreground">—</span>}</td>
                  <td className="px-4 py-1.5 tabular-nums">{fmtNum(p.retention, 3)}</td>
                  <td className="px-4 py-1.5 tabular-nums">{fmtNum(p.ratio, 2)}</td>
                  <td className="px-4 py-1.5 tabular-nums">{fmtNum(p.latency_speedup, 2)}</td>
                </tr>
              ))}
            </SimpleTable>
          ) : (
            <p className="p-4 text-xs text-muted-foreground">No completed peers yet.</p>
          )}
        </SectionCard>
      </div>
    </>
  );
}

function LogsCard({ id, logCount }: { id: string; logCount: number }) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [following, setFollowing] = useState(true);
  const boxRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef(-1);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const res = await api.get<{ logs: LogLine[]; next_seq: number; experiment_status: string }>(
          `/api/v1/experiments/${id}/logs?after_seq=${cursorRef.current}`
        );
        if (!alive) return;
        if (res.logs.length > 0) setLines((prev) => [...prev, ...res.logs].slice(-500));
        cursorRef.current = res.next_seq;
        if (["completed", "failed", "cancelled"].includes(res.experiment_status)) return; // done
      } catch {
        /* transient */
      }
      if (alive) timer = setTimeout(tick, 1600);
    };
    void tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [id]);

  useEffect(() => {
    if (following && boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [lines, following]);

  return (
    <SectionCard
      title={`Run log (${lines.length || logCount} lines)`}
      description="cursor-polling stream — survives retries and restarts"
      actions={
        <label className="flex items-center gap-1.5 text-2xs text-muted-foreground">
          <input type="checkbox" checked={following} onChange={(e) => setFollowing(e.target.checked)} className="accent-[#18A0FB]" />
          follow
        </label>
      }
    >
      <div ref={boxRef} className="h-64 overflow-y-auto rounded-b-xl bg-black/40 p-4 font-mono text-[11px] leading-relaxed text-slate-300 scrollbar-thin">
        {lines.length === 0 ? (
          <span className="text-slate-500">no log lines received yet…</span>
        ) : (
          lines.map((l) => (
            <div key={l.seq} className="flex gap-2">
              <span className="shrink-0 select-none text-slate-500">{String(l.seq).padStart(3, "0")}</span>
              <span className={`shrink-0 ${l.level === "error" ? "text-red-400" : l.level === "warning" ? "text-amber-400" : "text-sky-600"}`}>{l.level}</span>
              <span className="whitespace-pre-wrap">{l.message}</span>
            </div>
          ))
        )}
      </div>
    </SectionCard>
  );
}

function fmtAnyValue(key: string, v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (key.includes("bytes")) return fmtBytes(v);
    if (Math.abs(v) >= 100) return v.toFixed(1);
    return fmtNum(v, 4);
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "object") return JSON.stringify(v).slice(0, 120);
  return String(v).slice(0, 140);
}
