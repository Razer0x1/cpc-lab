"use client";
/** Paper Library: scholarly search (OpenAlex/arXiv/Crossref), ingestion, and provenance linking. */
import { useState, type FormEvent } from "react";
import { ExternalLink, FilePlus2, Link2, Search } from "lucide-react";
import { api, useApi } from "@/lib/api";
import type { ExperimentRow, Hypothesis, Paper, ResearchEntry } from "@/lib/types";
import { PageHeader, SectionCard, SimpleTable } from "@/components/shared";
import {
  Badge, Button, Card, CardContent, EmptyState, Field, Input, Select, Skeleton, Textarea,
} from "@/components/ui/primitives";

type SearchResult = Paper & { note?: string };

export default function PapersPage() {
  const [q, setQ] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searchNote, setSearchNote] = useState<string | null>(null);
  const [ingesting, setIngesting] = useState<string | null>(null);
  const [linkFor, setLinkFor] = useState<Paper | null>(null);

  const { data: library, error, loading, refresh } = useApi<Paper[]>("/api/v1/papers", 20000);
  const { data: hypotheses } = useApi<Hypothesis[]>("/api/v1/hypotheses", 20000);
  const { data: entries } = useApi<ResearchEntry[]>("/api/v1/research/entries", 20000);
  const { data: experiments } = useApi<ExperimentRow[]>("/api/v1/experiments", 20000);

  async function runSearch(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setSearching(true);
    setSearchNote(null);
    try {
      const data = await api.get<{ query: string; results: SearchResult[]; errors?: Record<string, string>; note?: string }>(
        `/api/v1/papers/search?q=${encodeURIComponent(q.trim())}&limit=10`
      );
      setResults(data.results ?? []);
      const parts: string[] = [];
      if (data.errors && Object.keys(data.errors).length > 0) {
        parts.push(Object.entries(data.errors).map(([k, v]) => `${k}: ${v}`).join(" · "));
      }
      if (data.note) parts.push(data.note);
      if ((data.results ?? []).length === 0) parts.push("No results returned — you can ingest manually using the search metadata.");
      setSearchNote(parts.join(" — ") || null);
    } catch (err) {
      setResults([]);
      setSearchNote(err instanceof Error ? `Search failed: ${err.message}` : "Search failed (offline uses only local library)");
    } finally {
      setSearching(false);
    }
  }

  async function ingest(p: Paper) {
    const key = `${p.source}:${p.external_id}:${p.title}`;
    setIngesting(key);
    try {
      await api.post("/api/v1/papers", {
        source: p.source || "manual",
        external_id: p.external_id || "",
        title: p.title,
        authors: p.authors ?? [],
        year: p.year ?? null,
        venue: p.venue ?? "",
        doi: p.doi ?? "",
        url: p.url ?? "",
        abstract: (p.abstract ?? "").slice(0, 4000),
        concepts: p.concepts ?? [],
      });
      refresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Ingest failed");
    } finally {
      setIngesting(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Paper Library"
        subtitle="Search OpenAlex, arXiv, and Crossref; ingest metadata into the workspace; link papers to hypotheses, entries, and experiments — provenance links are user-verified actions."
      />

      <Card className="mb-5">
        <CardContent className="p-4">
          <form onSubmit={runSearch} className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-3 h-3.5 w-3.5 text-muted-foreground" />
              <Input className="pl-8" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. curriculum learning distillation quantization" />
            </div>
            <Button type="submit" disabled={searching || !q.trim()}>
              {searching ? "Searching…" : "Search scholarly sources"}
            </Button>
          </form>
          {searching ? <Skeleton className="mt-3 h-12 w-full" /> : null}
          {searchNote ? <p className="mt-3 text-2xs text-muted-foreground">{searchNote}</p> : null}
          {results && results.length > 0 ? (
            <div className="mt-4 divide-y divide-border rounded-lg border border-border">
              {results.map((p, i) => (
                <div key={`${p.source}-${p.external_id}-${i}`} className="flex flex-col gap-1 p-3 sm:flex-row sm:items-start">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={p.source === "openalex" ? "blue" : p.source === "arxiv" ? "violet" : "cyan"}>{p.source}</Badge>
                      {p.year ? <span className="text-2xs text-muted-foreground">{p.year}</span> : null}
                      {p.venue ? <span className="truncate text-2xs text-muted-foreground">{p.venue}</span> : null}
                    </div>
                    <p className="mt-1 text-xs font-medium">{p.title}</p>
                    <p className="truncate text-2xs text-muted-foreground">{(p.authors ?? []).slice(0, 5).join(", ")}</p>
                    {p.note ? <p className="mt-1 text-2xs text-amber-500">{p.note}</p> : null}
                  </div>
                  <div className="flex shrink-0 gap-1.5 pt-2 sm:pt-0">
                    {p.doi && p.doi !== p.url ? (
                      <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer" className="rounded-md border border-border px-2 py-1 text-2xs text-muted-foreground hover:text-foreground">
                        <ExternalLink className="mr-1 inline h-3 w-3" />DOI
                      </a>
                    ) : p.url ? (
                      <a href={p.url} target="_blank" rel="noreferrer" className="rounded-md border border-border px-2 py-1 text-2xs text-muted-foreground hover:text-foreground">
                        <ExternalLink className="mr-1 inline h-3 w-3" />open
                      </a>
                    ) : null}
                    <Button size="sm" variant="outline" onClick={() => ingest(p)} disabled={ingesting === `${p.source}:${p.external_id}:${p.title}`}>
                      <FilePlus2 className="h-3 w-3" /> {ingesting === `${p.source}:${p.external_id}:${p.title}` ? "…" : "Ingest"}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {linkFor ? <LinkDialog paper={linkFor} hypotheses={hypotheses ?? []} entries={entries ?? []} experiments={experiments ?? []} onClose={() => setLinkFor(null)} onLink={() => setLinkFor(null)} /> : null}

      <SectionCard title={`Workspace library (${library?.length ?? 0})`} description="ingested bibliographic records (metadata only — claims require verified full text)">
        {loading && !library ? (
          <div className="space-y-2 p-4">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
        ) : error ? (
          <p className="p-4 text-xs text-red-400">{error}</p>
        ) : (library ?? []).length === 0 ? (
          <div className="p-4">
            <EmptyState title="Library is empty" description="Search above and ingest relevant papers, or they arrive pre-seeded with the curated catalog." />
          </div>
        ) : (
          <SimpleTable head={["Title", "Source", "Year", "Venue", "Verification", "Actions"]}>
            {(library ?? []).map((p) => (
              <tr key={p.id ?? p.title} className="align-top hover:bg-muted/40">
                <td className="max-w-md px-4 py-2">
                  <p className="font-medium">{p.title}</p>
                  <p className="truncate text-2xs text-muted-foreground">{(p.authors ?? []).slice(0, 4).join(", ")}</p>
                  {p.abstract ? <p className="mt-1 line-clamp-2 text-2xs text-muted-foreground">{p.abstract}</p> : null}
                </td>
                <td className="px-4 py-2"><Badge tone="blue">{p.source}</Badge></td>
                <td className="px-4 py-2 text-muted-foreground">{p.year ?? "—"}</td>
                <td className="max-w-40 truncate px-4 py-2 text-muted-foreground">{p.venue || "—"}</td>
                <td className="px-4 py-2">
                  <Badge tone={p.fulltext_verified ? "green" : "amber"}>{p.fulltext_verified ? "metadata verified" : "metadata only"}</Badge>
                </td>
                <td className="px-4 py-2">
                  <Button size="sm" variant="outline" onClick={() => setLinkFor(p)}>
                    <Link2 className="h-3 w-3" /> Link
                  </Button>
                </td>
              </tr>
            ))}
          </SimpleTable>
        )}
      </SectionCard>
    </>
  );
}

function LinkDialog({ paper, hypotheses, entries, experiments, onClose, onLink }: {
  paper: Paper;
  hypotheses: Hypothesis[]; entries: ResearchEntry[]; experiments: ExperimentRow[];
  onClose: () => void; onLink: () => void;
}) {
  const [subjectType, setSubjectType] = useState("hypothesis");
  const [subjectId, setSubjectId] = useState("");
  const [relation, setRelation] = useState("supports");
  const [note, setNote] = useState("user-verified link");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const pools: Record<string, Array<{ id: string; label: string }>> = {
    hypothesis: hypotheses.map((h) => ({ id: h.id, label: h.title || h.statement.slice(0, 70) })),
    research_entry: entries.map((e) => ({ id: e.id, label: e.title || e.question.slice(0, 70) })),
    experiment: experiments.map((e) => ({ id: e.id, label: e.name })),
  };
  const pool = pools[subjectType] ?? [];

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!subjectId) {
      setErr("Select a subject to link to");
      return;
    }
    setBusy(true);
    try {
      await api.post(`/api/v1/papers/${paper.id}/link`, { subject_type: subjectType, subject_id: subjectId, relation, note });
      onLink();
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Link failed — refresh the library and retry");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-5 border-[#18A0FB]/40">
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 p-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <p className="text-xs font-medium">Link paper: <span className="text-muted-foreground">{paper.title}</span></p>
            <p className="text-2xs text-muted-foreground">Established provenance — the graph marks this relation as verified.</p>
          </div>
          <Field label="Subject type">
            <Select value={subjectType} onChange={(e) => { setSubjectType(e.target.value); setSubjectId(""); }}>
              <option value="hypothesis">hypothesis</option>
              <option value="research_entry">research entry</option>
              <option value="experiment">experiment</option>
            </Select>
          </Field>
          <Field label="Subject">
            <Select value={subjectId} onChange={(e) => setSubjectId(e.target.value)} required>
              <option value="">— select —</option>
              {pool.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </Select>
          </Field>
          <Field label="Relation">
            <Select value={relation} onChange={(e) => setRelation(e.target.value)}>
              {["supports", "contradicts", "related", "reproduces"].map((r) => <option key={r} value={r}>{r}</option>)}
            </Select>
          </Field>
          <Field label="Note"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          {err ? <p className="text-xs text-red-400 sm:col-span-2">{err}</p> : null}
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" size="sm" disabled={busy}>{busy ? "Linking…" : "Establish link"}</Button>
            <Button type="button" variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
