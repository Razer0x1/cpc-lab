"use client";
/** Results & Reports: generate Markdown/HTML/PDF reports from completed experiments, download/export. */
import { useState, type FormEvent } from "react";
import { ClipboardList, Download } from "lucide-react";
import { api, useApi, fmtDate } from "@/lib/api";
import type { ExperimentRow, ReportRow } from "@/lib/types";
import { PageHeader, SectionCard, SimpleTable } from "@/components/shared";
import { Badge, Button, EmptyState, Field, Input, Select, Skeleton } from "@/components/ui/primitives";

export default function ReportsPage() {
  const { data: experiments } = useApi<ExperimentRow[]>("/api/v1/experiments", 0);
  const { data: reports, error, loading, refresh } = useApi<ReportRow[]>("/api/v1/reports", 0);
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  async function generate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setLastError(null);
    setLastResult(null);
    const fd = new FormData(e.currentTarget);
    try {
      const body = {
        experiment_id: String(fd.get("experiment_id") ?? ""),
        format: String(fd.get("format") ?? "markdown"),
        title: String(fd.get("title") ?? "") || undefined,
      };
      const res = await api.post<{ id: string; format: string; sha256: string; size_bytes: number }>("/api/v1/reports/generate", body);
      setLastResult(`Report ready (${res.format}, SHA-256 ${res.sha256.slice(0, 10)}…, ${res.size_bytes} bytes)`);
      refresh();
    } catch (err) {
      setLastError(err instanceof Error ? err.message : "Report generation failed");
    } finally {
      setBusy(false);
    }
  }

  const completed = (experiments ?? []).filter((e) => e.status === "completed");

  return (
    <>
      <PageHeader
        title="Results & Reports"
        subtitle="Generate reproducibility-oriented reports (objective, hypothesis, setup, limitations, measured results, references) from experiment runs."
      />

      <div className="grid gap-5 lg:grid-cols-[400px_minmax(0,1fr)]">
        <SectionCard title="Generate report" description="rendered server-side from measured data">
          <form onSubmit={generate} className="space-y-3 p-4">
            <Field label="Experiment *" hint={completed.length === 0 ? "no completed experiments yet — reports are generated from runs" : `${completed.length} completed experiment(s) available`}>
              <Select name="experiment_id" required defaultValue="">
                <option value="" disabled>— select experiment —</option>
                {(experiments ?? []).map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}{e.status === "completed" ? "" : ` (${e.status})`}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Format" hint="PDF requires the optional reportlab extra; markdown/html are always available">
              <Select name="format" defaultValue="markdown">
                <option value="markdown">Markdown (.md)</option>
                <option value="html">HTML (.html)</option>
                <option value="pdf">PDF (.pdf)</option>
              </Select>
            </Field>
            <Field label="Custom title (optional)">
              <Input name="title" placeholder="defaults to 'Research report — <experiment>'" />
            </Field>
            {lastError ? <p className="text-xs text-red-400">{lastError}</p> : null}
            {lastResult ? <p className="text-xs text-emerald-500">{lastResult}</p> : null}
            <Button type="submit" size="sm" disabled={busy}>
              <ClipboardList className="h-3.5 w-3.5" /> {busy ? "Generating…" : "Generate report"}
            </Button>
          </form>
        </SectionCard>

        <SectionCard title={`Generated reports (${reports?.length ?? 0})`}>
          {loading && !reports ? (
            <div className="space-y-2 p-4">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
          ) : error ? (
            <p className="p-4 text-xs text-red-400">{error}</p>
          ) : (reports ?? []).length === 0 ? (
            <div className="p-4">
              <EmptyState title="No reports yet" description="Run an experiment, then generate a report document from its measured results." />
            </div>
          ) : (
            <SimpleTable head={["Title", "Format", "Created", "Actions"]}>
              {(reports ?? []).map((r) => (
                <tr key={r.id} className="hover:bg-muted/40">
                  <td className="max-w-md px-4 py-2">
                    <p className="truncate font-medium">{r.title}</p>
                    <p className="text-2xs text-muted-foreground">
                      experiment <code>{r.experiment_id.slice(0, 8)}…</code>
                    </p>
                  </td>
                  <td className="px-4 py-2"><Badge tone={r.format === "pdf" ? "violet" : "blue"}>{r.format}</Badge></td>
                  <td className="whitespace-nowrap px-4 py-2 text-2xs text-muted-foreground">{fmtDate(r.created_at)}</td>
                  <td className="px-4 py-2">
                    <Button size="sm" variant="outline" onClick={() => {
                      void api.download(`/api/v1/reports/${r.id}/download`, `report.${r.format}`);
                    }}>
                      <Download className="h-3 w-3" /> Download
                    </Button>
                  </td>
                </tr>
              ))}
            </SimpleTable>
          )}
        </SectionCard>
      </div>
    </>
  );
}
