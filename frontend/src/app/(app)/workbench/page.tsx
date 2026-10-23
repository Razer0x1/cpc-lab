"use client";
/** Compression Workbench: method registry → validated config → run creation. */
import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { CheckCircle2, CircleDashed, Play, Wrench } from "lucide-react";
import { api, useApi } from "@/lib/api";
import type { Hypothesis, Method, MLModel } from "@/lib/types";
import { PageHeader, SectionCard, SimpleTable } from "@/components/shared";
import {
  Badge, Button, Card, CardContent, Field, Input, Select, Skeleton, Textarea,
} from "@/components/ui/primitives";

export default function WorkbenchPage() {
  const { data: methods, error, loading, refresh } = useApi<Method[]>("/api/v1/workbench/methods", 0);
  const { data: models, refresh: refreshModels } = useApi<MLModel[]>("/api/v1/workbench/models", 0);
  const { data: hypotheses } = useApi<Hypothesis[]>("/api/v1/hypotheses", 0);
  const [selected, setSelected] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<{ id: string; status: string } | null>(null);

  const method = useMemo(
    () => (methods ?? []).find((m) => m.key === selected) ?? (methods ?? [])[0] ?? null,
    [methods, selected]
  );

  const sampleConfig = useMemo(() => {
    if (!method) return "{}";
    const samples: Record<string, object> = {
      knowledge_distillation: { learning_rate: 0.05, epochs: 0, temperature: 2.0, alpha: 0.5, student_hidden: [8, 8], max_seconds: 300 },
      weight_quantization: { bits: 8, per_channel: false, symmetric: true },
      hybrid_combination: { learning_rate: 0.05, temperature: 2.0, alpha: 0.5, student_hidden: [8, 4], max_seconds: 300 },
      reverse_engineering: {
        surrogate_hidden: [8], temperature: 2.0, soft_weight: 0.9,
        query_budget: 3000, query_range: 1.2, surrogate_epochs: 120,
      },
    };
    if (samples[method.key]) return JSON.stringify(samples[method.key], null, 2);
    return method.config_schema && Object.keys(method.config_schema).length > 0
      ? JSON.stringify(demoOfSchema(method.config_schema), null, 2)
      : "{}";
  }, [method]);

  return (
    <>
      <PageHeader
        title="Compression Workbench"
        subtitle="Method registry with validated configuration. Methods marked 'engine ready' execute real CPU demo runs; planned engines validate configs but do not fake results."
        actions={
          <Button variant="outline" size="sm" onClick={() => { refresh(); refreshModels(); }}>
            Refresh registry
          </Button>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <SectionCard title="Compression methods" description="click a method to configure">
            {loading && !methods ? (
              <div className="space-y-2 p-4">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
            ) : error ? (
              <p className="p-4 text-xs text-red-400">Failed to load methods: {error}</p>
            ) : (
              <CheckboxList items={methods ?? []} onSelect={(k) => setSelected(k)} />
            )}
          </SectionCard>

          {models && models.length > 0 ? (
            <SectionCard title="Registered models" description="targets for quantization / evaluation (populated by demo runs)">
              <SimpleTable head={["Model", "Family", "Source", "Params", "Artifact", "Synthetic"]}>
                {models.map((m) => (
                  <tr key={m.id} className="hover:bg-muted/40">
                    <td className="px-4 py-2 font-medium">{m.name}</td>
                    <td className="px-4 py-2 text-muted-foreground">{m.family}</td>
                    <td className="px-4 py-2 text-muted-foreground">{m.source}</td>
                    <td className="px-4 py-2 tabular-nums">{m.params_count ?? "—"}</td>
                    <td className="px-4 py-2 text-muted-foreground">{m.artifact_uri ? "stored" : "—"}</td>
                    <td className="px-4 py-2">{m.synthetic ? <Badge tone="neutral">synthetic</Badge> : <Badge tone="blue">real</Badge>}</td>
                  </tr>
                ))}
              </SimpleTable>
            </SectionCard>
          ) : null}
        </div>

        <div className="space-y-5">
          {method ? (
            <SectionCard title={method.name} description={method.category}>
              <div className="space-y-4 p-4 text-2xs">
                <div className="flex items-center gap-2">
                  {method.runnable_now ? (
                    <Badge tone="green"><CheckCircle2 className="h-3 w-3" /> engine ready (CPU demo)</Badge>
                  ) : (
                    <Badge tone="amber"><CircleDashed className="h-3 w-3" /> planned — config validated only</Badge>
                  )}
                  <Badge tone="neutral">engine: {method.engine}</Badge>
                </div>
                <p className="leading-relaxed text-muted-foreground">{method.description}</p>
                <div>
                  <p className="mb-1 font-medium uppercase tracking-wide text-muted-foreground">Prerequisites</p>
                  <ul className="ml-4 list-disc text-muted-foreground">{method.prereqs.length ? method.prereqs.map((p, i) => <li key={i}>{p}</li>) : <li>none documented</li>}</ul>
                </div>
                <div>
                  <p className="mb-1 font-medium uppercase tracking-wide text-muted-foreground">Documented limitations</p>
                  <ul className="ml-4 list-disc text-muted-foreground">{method.limitations.length ? method.limitations.map((p, i) => <li key={i}>{p}</li>) : <li>none documented</li>}</ul>
                </div>
                <RunMethodForm
                  key={method.key}
                  method={method}
                  models={models ?? []}
                  hypotheses={hypotheses ?? []}
                  sampleConfig={sampleConfig}
                  onCreated={(run) => setLastRun(run)}
                />
              </div>
            </SectionCard>
          ) : null}

          {lastRun ? (
            <Card className="border-emerald-500/40 bg-emerald-500/5">
              <CardContent className="flex flex-col gap-2 p-4 text-xs">
                <p className="font-medium">Run created: <Link href={`/experiments/${lastRun.id}`} className="text-[#18A0FB] hover:underline">{lastRun.id.slice(0, 8)}…</Link></p>
                {lastRun.status === "queued" ? "Queued in the runner; observe progress in the Experiment Lab." : "Status 'created' — start it from the Experiment Lab (Run or Run synchronously)."}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </>
  );
}

function CheckboxList({ items, onSelect }: {
  items: Method[]; onSelect: (key: string) => void;
}) {
  return (
    <ul className="divide-y divide-border">
      {items.map((m) => (
        <li key={m.key}>
          <button
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-xs hover:bg-muted/50"
            onClick={() => onSelect(m.key)}
          >
            <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-medium">{m.name}</span>
            <Badge tone={m.category === "paradigm" ? "blue" : m.category === "combination" ? "violet" : "neutral"}>{m.category}</Badge>
            {m.runnable_now ? <Badge tone="green">runnable</Badge> : <Badge tone="amber">planned</Badge>}
            <span className="ml-auto truncate text-2xs text-muted-foreground">{m.runnable_note}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function demoOfSchema(schema: Record<string, unknown>): Record<string, unknown> {
  if (schema && typeof schema === "object" && "properties" in schema) {
    const props = (schema as { properties: Record<string, unknown> }).properties;
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(props)) {
      const spec = v as { default?: unknown; example?: unknown };
      out[k] = spec.default ?? spec.example ?? null;
    }
    return out;
  }
  return {};
}

function RunMethodForm({ method, models, hypotheses, sampleConfig, onCreated }: {
  method: Method; models: MLModel[]; hypotheses: Hypothesis[]; sampleConfig: string;
  onCreated: (run: { id: string; status: string }) => void;
}) {
  const defaultName = `${method.key}-run-${new Date().toISOString().slice(5, 16).replace("T", "-")}`;
  const [name, setName] = useState(defaultName);
  const [config, setConfig] = useState(sampleConfig);
  const [modelId, setModelId] = useState("");
  const [hypothesisId, setHypothesisId] = useState("");
  const [seed, setSeed] = useState("7");
  const [runNow, setRunNow] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const needsModel = method.key === "weight_quantization" || method.key === "reverse_engineering";
  const modelHint = method.key === "reverse_engineering"
    ? "extraction queries a registered model artifact through its forward function"
    : "quantization compresses a registered model artifact";

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
      const res = await api.post<{ id: string; kind: string; status: string }>("/api/v1/workbench/runs", {
        method_key: method.key,
        name: name.trim(),
        config: parsed,
        model_id: modelId || undefined,
        hypothesis_id: hypothesisId || undefined,
        seed: Number(seed) || 7,
        run_immediately: runNow,
      });
      onCreated({ id: res.id, status: res.status });
      setName(`${method.key}-run-${new Date().toISOString().slice(5, 16).replace("T", "-")}`);
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Run creation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 border-t border-border pt-4">
      <p className="font-medium uppercase tracking-wide text-muted-foreground">Create run</p>
      <Field label="Experiment name">
        <Input value={name} onChange={(e) => setName(e.target.value)} minLength={3} required />
      </Field>
      <Field label="Config (JSON)">
        <Textarea className="font-mono text-[11px]" value={config} onChange={(e) => setConfig(e.target.value)} rows={6} spellCheck={false} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Seed"><Input type="number" value={seed} onChange={(e) => setSeed(e.target.value)} min={0} /></Field>
        <Field label="Link hypothesis (optional)">
          <Select value={hypothesisId} onChange={(e) => setHypothesisId(e.target.value)}>
            <option value="">— none —</option>
            {hypotheses.map((h) => <option key={h.id} value={h.id}>{h.title || h.statement.slice(0, 60)}</option>)}
          </Select>
        </Field>
      </div>
      {needsModel ? (
        <Field label="Target model *" hint={modelHint}>
          <Select value={modelId} onChange={(e) => setModelId(e.target.value)} required>
            <option value="">— select model —</option>
            {models.filter((m) => m.artifact_uri).map((m) => (
              <option key={m.id} value={m.id}>{m.name}{m.artifact_uri ? " (artifact stored)" : ""}</option>
            ))}
          </Select>
        </Field>
      ) : null}
      <label className="flex items-center gap-2 text-2xs text-muted-foreground">
        <input type="checkbox" checked={runNow} onChange={(e) => setRunNow(e.target.checked)} className="accent-[#18A0FB]" />
        Queue immediately (otherwise create as &lsquo;created&rsquo; and start from the Experiment Lab)
      </label>
      {err ? <p className="text-xs text-red-400">{err}</p> : null}
      <Button type="submit" size="sm" disabled={busy || !method.runnable_now}>
        <Play className="h-3.5 w-3.5" /> {busy ? "Submitting…" : "Start compression run"}
      </Button>
    </form>
  );
}
