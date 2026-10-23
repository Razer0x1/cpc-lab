"use client";
/** Experiment Lab: create experiments, control lifecycle (queue/run/cancel/retry), observe status. */
import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { Ban, Play, RotateCcw, Rocket, Timer } from "lucide-react";
import { api, useApi, fmtDate } from "@/lib/api";
import type { Hypothesis, ExperimentRow } from "@/lib/types";
import { PageHeader, SectionCard, SimpleTable } from "@/components/shared";
import {
  Badge, Button, Card, CardContent, EmptyState, Field, Input, Select, Skeleton, StatusBadge, Textarea,
} from "@/components/ui/primitives";

const KIND_INFO: Record<string, string> = {
  distillation_demo: "Real CPU demo: teacher→student knowledge distillation on synthetic cpc_spiral3 (numpy).",
  quantization_int8_eval: "Real CPU demo: int8 codebook quantization + evaluation of a registered model artifact.",
};

export default function ExperimentsPage() {
  const { data, error, loading, refresh } = useApi<ExperimentRow[]>("/api/v1/experiments", 4000);
  const { data: kinds } = useApi<{ key: string }[]>("/api/v1/experiments/kinds", 0);
  const { data: hypotheses } = useApi<Hypothesis[]>("/api/v1/hypotheses", 0);
  const [creating, setCreating] = useState(false);

  const busy = useMemo(
    () => (data ?? []).filter((e) => ["queued", "running"].includes(e.status)),
    [data]
  );

  return (
    <>
      <PageHeader
        title="Experiment Lab"
        subtitle="Asynchronous experiment manager: queue, run synchronously, cancel, retry. Status 'created' means defined but not yet submitted."
        actions={
          <>
            {busy.length > 0 ? <Badge tone="blue">{busy.length} active</Badge> : null}
            <Button size="sm" onClick={() => setCreating((v) => !v)}>
              <Rocket className="h-3.5 w-3.5" /> New experiment
            </Button>
          </>
        }
      />

      {creating ? <CreateForm onDone={() => { setCreating(false); refresh(); }} kinds={(kinds ?? []).map((k) => k.key)} hypotheses={hypotheses ?? []} /> : null}

      <SectionCard title="All experiments" description={`polling every 4s · ${data?.length ?? 0} total`} >
        <div className="p-2">
          <Button variant="outline" size="sm" onClick={refresh}>Refresh now</Button>
        </div>
        {loading && !data ? (
          <div className="space-y-2 p-4">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
        ) : error ? (
          <p className="p-4 text-xs text-red-400">Failed to load experiments: {error}</p>
        ) : data && data.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No experiments yet"
              description="Create the flagship distillation demo — it is CPU-only, deterministic, and finishes in seconds."
            />
          </div>
        ) : (
          <SimpleTable head={["Name", "Kind", "Status", "Verdict", "Progress", "Seed", "Created", "Actions"]}>
            {(data ?? []).map((e) => (
              <tr key={e.id} className="hover:bg-muted/40">
                <td className="px-4 py-2">
                  <Link href={`/experiments/${e.id}`} className="font-medium text-[#18A0FB] hover:underline">{e.name}</Link>
                </td>
                <td className="px-4 py-2 text-muted-foreground"><code className="rounded bg-muted px-1.5 py-0.5">{e.kind}</code></td>
                <td className="px-4 py-2"><StatusBadge status={e.status} /></td>
                <td className="px-4 py-2">{e.verdict ? <StatusBadge status={e.verdict} /> : <span className="text-muted-foreground">—</span>}</td>
                <td className="px-4 py-2 tabular-nums text-muted-foreground">{Math.round((e.progress ?? 0) * 100)}%</td>
                <td className="px-4 py-2 tabular-nums text-muted-foreground">{e.seed}</td>
                <td className="whitespace-nowrap px-4 py-2 text-2xs text-muted-foreground">{fmtDate(e.created_at)}</td>
                <td className="px-4 py-2">
                  <RowActions e={e} onDone={refresh} />
                </td>
              </tr>
            ))}
          </SimpleTable>
        )}
      </SectionCard>
    </>
  );
}

function RowActions({ e, onDone }: { e: ExperimentRow; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const call = async (path: string) => {
    setBusy(true);
    setErr(null);
    try {
      await api.post(`/api/v1/experiments/${e.id}/${path}`);
      onDone();
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const canRun = e.status === "created";
  const canCancel = e.status === "queued" || e.status === "running" || e.status === "created";
  const canRetry = e.status === "failed" || e.status === "cancelled" || e.status === "paused";

  return (
    <div className="flex flex-col items-start gap-1">
      <div className="flex flex-wrap gap-1">
        {canRun ? (
          <>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => call("run")}>
              <Play className="h-3 w-3" /> Queue
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => call("run_sync")}>
              <Timer className="h-3 w-3" /> Run sync
            </Button>
          </>
        ) : null}
        {canRetry ? (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => call("retry")}>
            <RotateCcw className="h-3 w-3" /> Reset
          </Button>
        ) : null}
        {canCancel ? (
          <Button size="sm" variant="ghost" className="text-red-400" disabled={busy} onClick={() => call("cancel")}>
            <Ban className="h-3 w-3" /> Cancel
          </Button>
        ) : null}
      </div>
      {err ? <span className="text-2xs text-red-400">{err}</span> : null}
    </div>
  );
}

function CreateForm({ onDone, kinds, hypotheses }: { onDone: () => void; kinds: string[]; hypotheses: Hypothesis[] }) {
  const kindDefault = kinds.includes("distillation_demo") ? "distillation_demo" : (kinds[0] ?? "");
  const [name, setName] = useState("");
  const [kind, setKind] = useState(kindDefault);
  const [config, setConfig] = useState("{}");
  const [hypothesisId, setHypothesisId] = useState("");
  const [seed, setSeed] = useState("7");
  const [runNow, setRunNow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [created, setCreated] = useState<{ id: string; status: string } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    let parsed: object = {};
    try {
      parsed = JSON.parse(config || "{}");
    } catch {
      setErr("Config is not valid JSON");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post<{ id: string; status: string }>("/api/v1/experiments", {
        name: name.trim(),
        kind,
        config: parsed,
        hypothesis_id: hypothesisId || undefined,
        seed: Number(seed) || 7,
        budgets: { max_seconds: 60, max_ram_mb: 512 },
        run_now: runNow,
      });
      setCreated(res);
      setName("");
      refreshMini();
      onDone();
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  function refreshMini() { /* the list polls automatically */ }

  return (
    <Card className="mb-5">
      <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} minLength={3} required placeholder="e.g. kd-spiral-seed7" /></Field>
        <Field label="Kind" hint={KIND_INFO[kind] ?? "requires ENGINE_TORCH=true (optional GPU extras)"}>
          <Select value={kind} onChange={(e) => setKind(e.target.value)}>
            {(kinds.length ? kinds : ["distillation_demo", "quantization_int8_eval"]).map((k) => (
              <option key={k} value={k}>{k}</option>
            ))}
          </Select>
        </Field>
        <Field label="Config JSON">
          <Textarea className="font-mono text-[11px]" value={config} onChange={(e) => setConfig(e.target.value)} rows={4} spellCheck={false} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Seed"><Input type="number" value={seed} onChange={(e) => setSeed(e.target.value)} min={0} /></Field>
          <Field label="Hypothesis (optional)">
            <Select value={hypothesisId} onChange={(e) => setHypothesisId(e.target.value)}>
              <option value="">— none —</option>
              {hypotheses.map((h) => <option key={h.id} value={h.id}>{h.title || h.statement.slice(0, 60)}</option>)}
            </Select>
          </Field>
        </div>
        <label className="flex items-center gap-2 text-2xs text-muted-foreground sm:col-span-2">
          <input type="checkbox" checked={runNow} onChange={(e) => setRunNow(e.target.checked)} className="accent-[#18A0FB]" />
          Submit to runner immediately (otherwise stays &lsquo;created&rsquo;)
        </label>
        {err ? <p className="text-xs text-red-400 sm:col-span-2">{err}</p> : null}
        {created ? (
          <p className="text-xs text-emerald-500 sm:col-span-2">
            Created <Link href={`/experiments/${created.id}`} className="underline">{created.id.slice(0, 8)}…</Link> ({created.status})
          </p>
        ) : null}
        <div className="flex gap-2 sm:col-span-2">
          <Button onClick={submit} disabled={busy || name.length < 3 || !kind}>
            {busy ? "Creating…" : "Create experiment"}
          </Button>
          <Button variant="outline" onClick={onDone}>Close</Button>
        </div>
      </CardContent>
    </Card>
  );
}
