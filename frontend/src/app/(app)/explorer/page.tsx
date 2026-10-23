"use client";
/** Research Explorer: curated cross-paradigm catalog with filters and hypothesis drafting. */
import { useMemo, useState, type FormEvent } from "react";
import { ChevronDown, ChevronRight, FlaskConical, Plus, Search } from "lucide-react";
import { api, useApi } from "@/lib/api";
import type { ResearchEntry } from "@/lib/types";
import { PageHeader, SectionCard } from "@/components/shared";
import {
  Badge, Button, Card, CardContent, EmptyState, Field, Input, Select, Skeleton, Textarea,
} from "@/components/ui/primitives";

const FIELDS = ["", "compression", "distillation", "quantization", "pruning", "architectures", "multi-paradigm"];
const TECHNIQUES = ["", "knowledge_distillation", "weight_quantization", "structured_pruning", "low_rank", "hybrid"];
const EVIDENCE = ["", "idea", "idea_only", "literature_supported", "implemented", "experimentally_tested", "independently_reproduced"];

export default function ExplorerPage() {
  const [q, setQ] = useState("");
  const [field, setField] = useState("");
  const [technique, setTechnique] = useState("");
  const [evidence, setEvidence] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [creatingHyp, setCreatingHyp] = useState<string | null>(null);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (field) p.set("field", field);
    if (technique) p.set("technique", technique);
    if (evidence) p.set("evidence", evidence);
    if (yearFrom) p.set("year_from", yearFrom);
    const s = p.toString();
    return `/api/v1/research/entries${s ? `?${s}` : ""}`;
  }, [q, field, technique, evidence, yearFrom]);

  const { data, error, loading, refresh } = useApi<ResearchEntry[]>(path, 0);

  return (
    <>
      <PageHeader
        title="Research Explorer"
        subtitle="Curated catalog of cross-paradigm compression research questions — filter, inspect provenance, and draft testable hypotheses."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => setCreating((v) => !v)}>
              <Plus className="h-3.5 w-3.5" /> New entry
            </Button>
          </>
        }
      />

      {creating ? <NewEntryForm onDone={() => { setCreating(false); refresh(); }} /> : null}

      <Card className="mb-5">
        <CardContent className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Search">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-3 h-3.5 w-3.5 text-muted-foreground" />
              <Input className="pl-8" value={q} onChange={(e) => setQ(e.target.value)} placeholder="title, question, shared structure…" />
            </div>
          </Field>
          <Field label="Field">
            <Select value={field} onChange={(e) => setField(e.target.value)}>
              {FIELDS.map((f) => <option key={f} value={f}>{f || "any"}</option>)}
            </Select>
          </Field>
          <Field label="Technique">
            <Select value={technique} onChange={(e) => setTechnique(e.target.value)}>
              {TECHNIQUES.map((t) => <option key={t} value={t}>{t || "any"}</option>)}
            </Select>
          </Field>
          <Field label="Evidence quality">
            <Select value={evidence} onChange={(e) => setEvidence(e.target.value)}>
              {EVIDENCE.map((v) => <option key={v} value={v}>{v || "any"}</option>)}
            </Select>
          </Field>
          <Field label="Published from (year)">
            <Input type="number" min={1990} max={2100} value={yearFrom} onChange={(e) => setYearFrom(e.target.value)} placeholder="e.g. 2015" />
          </Field>
        </CardContent>
      </Card>

      {error ? <p className="mb-4 text-xs text-red-400">Failed to load entries: {error}</p> : null}
      {loading && !data ? (
        <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}</div>
      ) : data && data.length === 0 ? (
        <EmptyState title="No entries match" description="Adjust the filters, or add your own research question with 'New entry'." />
      ) : (
        <div className="space-y-3">
          {(data ?? []).map((e) => (
            <SectionCard
              key={e.id}
              title={e.title || e.question.slice(0, 120)}
              description={`${e.source_paradigm || "?"} → ${e.target_paradigm || "?"}`}
              actions={
                <div className="flex flex-wrap items-center justify-end gap-1.5">
                  <Badge tone={e.evidence_quality === "idea" || e.evidence_quality === "idea_only" ? "amber" : "blue"}>{e.evidence_quality}</Badge>
                  {e.compression_technique ? <Badge tone="violet">{e.compression_technique}</Badge> : null}
                  <Badge tone="neutral">{e.resource_estimate || "resource: n/a"}</Badge>
                </div>
              }
            >
              <div className="px-4 py-3">
                <p className="text-xs text-muted-foreground"><span className="text-foreground">Question:</span> {e.question}</p>
                {expanded !== e.id ? (
                  <button
                    className="mt-2 flex items-center gap-1 text-2xs text-[#18A0FB] hover:underline"
                    onClick={() => setExpanded(e.id)}
                  >
                    <ChevronRight className="h-3 w-3" /> Show full record
                  </button>
                ) : (
                  <div className="mt-3 space-y-3 text-2xs">
                    {e.shared_structure ? <Block label="Shared structure" text={e.shared_structure} /> : null}
                    {e.math_explanation ? <Block label="Mathematical explanation" text={e.math_explanation} /> : null}
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Block label="Computational benefit" text={e.computational_benefit || "—"} />
                      <Block label="Implementation complexity" text={e.implementation_complexity || "—"} />
                    </div>
                    {e.limitations.length > 0 ? <ListBlock label="Limitations" items={e.limitations} /> : null}
                    {e.proposed_experiments.length > 0 ? <ListBlock label="Proposed experiments" items={e.proposed_experiments} /> : null}

                    <div>
                      <p className="mb-1 font-medium text-muted-foreground">Linked publications ({e.publications.length})</p>
                      {e.publications.length === 0 ? (
                        <p className="italic text-muted-foreground">No source links registered yet — provenance is user-verified in the Paper Library.</p>
                      ) : (
                        <ul className="space-y-1">
                          {e.publications.map((p, i) => (
                            <li key={i} className="text-muted-foreground">
                              <span className="text-foreground">{p.title}</span>
                              {p.year ? ` (${p.year})` : ""}{p.doi ? ` — DOI ${p.doi}` : ""}
                              {p.doi || p.url ? (
                                <a className="ml-1 text-[#18A0FB] hover:underline" href={p.doi ? `https://doi.org/${p.doi}` : p.url} target="_blank" rel="noreferrer">open ↗</a>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>

                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button
                        size="sm"
                        disabled={creatingHyp === e.id}
                        onClick={async () => {
                          setCreatingHyp(e.id);
                          try {
                            const res = await api.post<{ id: string }>(`/api/v1/research/entries/${e.id}/hypothesis`, {});
                            refresh();
                            setCreatingHyp(null);
                            window.location.href = `/hypotheses?draft=${res.id}`;
                          } catch (err) {
                            setCreatingHyp(null);
                            alert(err instanceof Error ? err.message : "Failed to draft hypothesis");
                          }
                        }}
                      >
                        <FlaskConical className="h-3.5 w-3.5" /> {creatingHyp === e.id ? "Drafting…" : "Draft hypothesis"}
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => setExpanded(null)}>
                        <ChevronDown className="h-3.5 w-3.5" /> Collapse
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </SectionCard>
          ))}
        </div>
      )}
    </>
  );
}

function Block({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <p className="mb-1 font-medium text-muted-foreground">{label}</p>
      <p className="whitespace-pre-wrap leading-relaxed text-muted-foreground">{text}</p>
    </div>
  );
}

function ListBlock({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <p className="mb-1 font-medium text-muted-foreground">{label}</p>
      <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
        {items.map((it, i) => <li key={i}>{it}</li>)}
      </ul>
    </div>
  );
}

function NewEntryForm({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [title, setTitle] = useState("");
  const [sharedStructure, setSharedStructure] = useState("");
  const [limitations, setLimitations] = useState("");
  const [experiments, setExperiments] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api.post("/api/v1/research/entries", {
        question,
        title,
        shared_structure: sharedStructure,
        limitations: limitations.split("\n").map((s) => s.trim()).filter(Boolean),
        proposed_experiments: experiments.split("\n").map((s) => s.trim()).filter(Boolean),
      });
      onDone();
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Failed to create entry");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-5">
      <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
        <Field label="Research question *">
          <Textarea value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Can quantized students inherit curriculum-gated rational approximations?" className="h-16" />
        </Field>
        <Field label="Title (optional)">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="short descriptive title" />
        </Field>
        <Field label="Shared structure" hint="what is mathematically/structurally shared between paradigms">
          <Textarea value={sharedStructure} onChange={(e) => setSharedStructure(e.target.value)} className="h-20" />
        </Field>
        <div className="grid gap-3">
          <Field label="Limitations (one per line)">
            <Textarea value={limitations} onChange={(e) => setLimitations(e.target.value)} className="h-16" />
          </Field>
          <Field label="Proposed experiments (one per line)">
            <Textarea value={experiments} onChange={(e) => setExperiments(e.target.value)} className="h-16" />
          </Field>
        </div>
        {err ? <p className="text-xs text-red-400 sm:col-span-2">{err}</p> : null}
        <div className="flex gap-2 sm:col-span-2">
          <Button onClick={submit} disabled={busy || question.length < 4}>{busy ? "Saving…" : "Create entry"}</Button>
          <Button variant="outline" onClick={onDone}>Close</Button>
        </div>
      </CardContent>
    </Card>
  );
}
