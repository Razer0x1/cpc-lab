"use client";
/** Hypothesis Studio: lifecycle management with evidence classification. */
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Plus, ChevronsUpDown } from "lucide-react";
import { api, useApi } from "@/lib/api";
import type { Hypothesis } from "@/lib/types";
import { PageHeader, SectionCard } from "@/components/shared";
import {
  Badge, Button, Card, CardContent, EmptyState, Field, Input, Select, Skeleton, Textarea,
} from "@/components/ui/primitives";

const EVIDENCE_LEVELS = [
  "idea_only", "literature_supported", "implemented", "experimentally_tested", "independently_reproduced",
];

export default function HypothesesPage() {
  const { data, error, loading, refresh } = useApi<Hypothesis[]>("/api/v1/hypotheses", 15000);
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  return (
    <>
      <PageHeader
        title="Hypothesis Studio"
        subtitle="Every hypothesis is classified by evidence level — 'idea_only' means not yet tested, and evidence level never rises from paper searches alone."
        actions={
          <Button size="sm" onClick={() => setCreating((v) => !v)}>
            <Plus className="h-3.5 w-3.5" /> New hypothesis
          </Button>
        }
      />

      {creating ? <NewHypothesisForm onDone={() => { setCreating(false); refresh(); }} /> : null}

      {error ? <p className="mb-4 text-xs text-red-400">Failed to load hypotheses: {error}</p> : null}

      {loading && !data ? (
        <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}</div>
      ) : data && data.length === 0 ? (
        <EmptyState
          title="No hypotheses yet"
          description="Draft one here, or open a curated entry in the Research Explorer and use 'Draft hypothesis' to prefill the record."
          action={<Link href="/explorer" className="text-xs text-[#18A0FB] hover:underline">Browse Research Explorer →</Link>}
        />
      ) : (
        <div className="space-y-3">
          {(data ?? []).map((h) => (
            <SectionCard
              key={h.id}
              title={h.title || h.statement.slice(0, 110)}
              description={`updated ${new Date(h.updated_at).toLocaleDateString()}`}
              actions={
                <div className="flex flex-wrap items-center justify-end gap-1.5">
                  <Badge tone={h.status === "approved" ? "green" : h.status === "rejected" ? "red" : "neutral"}>{h.status}</Badge>
                  <Badge tone={h.evidence_level === "idea_only" ? "amber" : h.evidence_level === "independently_reproduced" ? "green" : "blue"}>
                    {h.evidence_level}
                  </Badge>
                </div>
              }
            >
              <div className="px-4 py-3">
                <p className="text-xs text-muted-foreground"><span className="text-foreground">Statement:</span> {h.statement}</p>

                {h.experiments.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {h.experiments.map((x) => (
                      <Link
                        key={x.id}
                        href={`/experiments/${x.id}`}
                        className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-2xs hover:border-[#18A0FB]/60"
                      >
                        {x.name}
                        <Badge tone={x.verdict === "successful" ? "green" : x.verdict === "unsuccessful" ? "red" : x.verdict === "inconclusive" ? "amber" : "neutral"}>
                          {x.verdict ?? x.status}
                        </Badge>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-2xs italic text-muted-foreground">No experiments linked to this hypothesis yet.</p>
                )}

                {h.evidence_note ? <p className="mt-2 text-2xs text-muted-foreground">{h.evidence_note}</p> : null}

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <LifecycleActions id={h.id} status={h.status} evidence={h.evidence_level} onDone={refresh} />
                  <button
                    className="ml-auto flex items-center gap-1 text-2xs text-[#18A0FB] hover:underline"
                    onClick={() => setOpen(open === h.id ? null : h.id)}
                  >
                    <ChevronsUpDown className="h-3 w-3" /> {open === h.id ? "Hide details" : "Full record"}
                  </button>
                </div>

                {open === h.id ? <DetailGrid h={h} /> : null}
              </div>
            </SectionCard>
          ))}
        </div>
      )}
    </>
  );
}

function DetailGrid({ h }: { h: Hypothesis }) {
  const rows: Array<[string, string | string[]]> = [
    ["Rationale", h.rationale || "—"],
    ["Math formulation", h.math_formulation || "—"],
    ["Expected outcomes", h.expected_outcomes || "—"],
    ["Success criteria", h.success_criteria || "—"],
    ["Failure criteria", h.failure_criteria || "—"],
    ["Related research", h.related_research],
    ["Baselines", h.baselines],
    ["Ablations", h.ablations],
    ["Required datasets", h.required_datasets],
    ["Required models", h.required_models],
    ["Compute requirements", h.compute_requirements || "—"],
    ["Reproducibility notes", h.reproducibility_notes || "—"],
  ];
  return (
    <dl className="mt-4 grid gap-3 rounded-lg bg-muted/40 p-4 text-2xs sm:grid-cols-2">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt className="font-medium uppercase tracking-wide text-muted-foreground">{k}</dt>
          <dd className="mt-0.5 whitespace-pre-wrap text-foreground">
            {Array.isArray(v) ? (v.length ? v.join("; ") : "—") : v}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function LifecycleActions({ id, status, evidence, onDone }: {
  id: string; status: string; evidence: string; onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex items-center gap-1.5">
      <Select
        className="h-8 w-40 text-2xs"
        value={evidence}
        onChange={async (e) => {
          setBusy(true);
          try {
            await api.patch(`/api/v1/hypotheses/${id}`, { evidence_level: e.target.value });
            onDone();
          } catch (err) {
            alert(err instanceof Error ? err.message : "Update failed");
          } finally {
            setBusy(false);
          }
        }}
      >
        {EVIDENCE_LEVELS.map((lv) => <option key={lv} value={lv}>{lv}</option>)}
      </Select>
      <Button variant="outline" size="sm" disabled={busy || status !== "draft"} onClick={async () => {
        setBusy(true);
        try {
          await api.patch(`/api/v1/hypotheses/${id}`, { status: "approved" });
          onDone();
        } catch (err) {
          alert(err instanceof Error ? err.message : "Update failed");
        } finally {
          setBusy(false);
        }
      }}>
        Approve
      </Button>
      <Button variant="outline" size="sm" disabled={busy || status !== "draft"} onClick={async () => {
        setBusy(true);
        try {
          await api.patch(`/api/v1/hypotheses/${id}`, { status: "rejected" });
          onDone();
        } catch (err) {
          alert(err instanceof Error ? err.message : "Update failed");
        } finally {
          setBusy(false);
        }
      }}>
        Reject
      </Button>
    </div>
  );
}

function NewHypothesisForm({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [f, setF] = useState({
    title: "", statement: "", rationale: "", math_formulation: "", expected_outcomes: "",
    success_criteria: "", failure_criteria: "",
  });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api.post("/api/v1/hypotheses", {
        ...f,
        related_research: [], baselines: [], ablations: [],
      });
      onDone();
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-5">
      <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
        <Field label="Title"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label="Statement *" hint="min 8 characters; must be falsifiable to be approved">
          <Textarea value={f.statement} onChange={(e) => setF({ ...f, statement: e.target.value })} className="h-20" />
        </Field>
        <Field label="Rationale"><Textarea value={f.rationale} onChange={(e) => setF({ ...f, rationale: e.target.value })} className="h-20" /></Field>
        <Field label="Mathematical formulation"><Textarea value={f.math_formulation} onChange={(e) => setF({ ...f, math_formulation: e.target.value })} className="h-20" /></Field>
        <Field label="Expected outcomes"><Textarea value={f.expected_outcomes} onChange={(e) => setF({ ...f, expected_outcomes: e.target.value })} className="h-16" /></Field>
        <Field label="Success criteria"><Textarea value={f.success_criteria} onChange={(e) => setF({ ...f, success_criteria: e.target.value })} className="h-16" /></Field>
        <Field label="Failure criteria"><Textarea value={f.failure_criteria} onChange={(e) => setF({ ...f, failure_criteria: e.target.value })} className="h-16" /></Field>
        {err ? <p className="text-xs text-red-400 sm:col-span-2">{err}</p> : null}
        <div className="flex gap-2 sm:col-span-2">
          <Button onClick={submit} disabled={busy || f.statement.length < 8}>{busy ? "Saving…" : "Create hypothesis (draft, idea_only)"}</Button>
          <Button variant="outline" onClick={onDone}>Close</Button>
        </div>
      </CardContent>
    </Card>
  );
}
