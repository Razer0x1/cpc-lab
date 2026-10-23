"use client";
/** Settings: compute resources, environment facts, assistant provider status + offline-capable chat. */
import { useState, type FormEvent } from "react";
import { Send } from "lucide-react";
import { api, useApi, fmtDate } from "@/lib/api";
import type { AssistantChat, AssistantStatus, ComputeResourceRow, EnvironmentInfo, MLModel } from "@/lib/types";
import { PageHeader, SectionCard, SimpleTable } from "@/components/shared";
import { Badge, Button, Field, Skeleton, Textarea } from "@/components/ui/primitives";

export default function SettingsPage() {
  const { data: compute, error: compErr } = useApi<ComputeResourceRow[]>("/api/v1/settings/compute", 20000);
  const { data: env, error: envErr } = useApi<EnvironmentInfo>("/api/v1/settings/environment", 0);
  const { data: asst, error: asstErr } = useApi<AssistantStatus>("/api/v1/assistant/status", 0);
  const { data: models } = useApi<MLModel[]>("/api/v1/workbench/models", 0);

  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Deployment facts and integrations. All configuration is environment-driven; no secrets are returned by the API."
      />

      <div className="grid gap-5 lg:grid-cols-2">
        <SectionCard title="Compute resources" description="registered workers/runners for this workspace">
          {compErr ? <p className="p-4 text-xs text-red-400">{compErr}</p> : null}
          {!compute ? (
            <div className="space-y-2 p-4">{Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
          ) : (
            <SimpleTable head={["Name", "Kind", "Status", "Limits", "Updated"]}>
              {compute.map((c) => (
                <tr key={c.id} className="hover:bg-muted/40">
                  <td className="px-4 py-2 font-medium">{c.name}</td>
                  <td className="px-4 py-2 text-muted-foreground">{c.kind}</td>
                  <td className="px-4 py-2"><Badge tone={c.status === "online" ? "green" : "amber"}>{c.status}</Badge></td>
                  <td className="px-4 py-2 text-2xs text-muted-foreground">{JSON.stringify(c.limits)}</td>
                  <td className="whitespace-nowrap px-4 py-2 text-2xs text-muted-foreground">{fmtDate(c.updated_at)}</td>
                </tr>
              ))}
            </SimpleTable>
          )}
        </SectionCard>

        <SectionCard title="Environment" description="non-secret deployment facts">
          {envErr ? <p className="p-4 text-xs text-red-400">{envErr}</p> : null}
          {env ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 p-4 text-xs">
              {([
                ["env", env.env],
                ["database", env.database],
                ["artifact storage", env.storage_backend],
                ["job backend", env.job_backend],
                ["torch engine", env.engine_torch ? "enabled (GPU extras installed)" : "disabled (CPU numpy engine)"],
                ["assistant provider", env.assistant_provider],
                ["rate limit", `${env.rate_limit_per_minute}/min`],
              ] as Array<[string, string]>).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-2xs uppercase tracking-wide text-muted-foreground">{k}</dt>
                  <dd className="mt-0.5">{v}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <div className="p-4"><Skeleton className="h-32 w-full" /></div>
          )}
          <p className="border-t border-border px-4 py-3 text-2xs text-muted-foreground">
            Registered models: {models?.length ?? 0} — models are created by demo runs and stored as SHA-256-verified artifacts.
          </p>
        </SectionCard>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <SectionCard title="Research assistant" description="honesty-first assistant: works fully offline; an LLM provider is optional">
          {asstErr ? <p className="p-4 text-xs text-red-400">{asstErr}</p> : null}
          {asst ? (
            <div className="space-y-3 p-4 text-xs">
              <div className="flex items-center gap-2">
                <Badge tone={asst.configured ? "violet" : "blue"}>
                  {asst.configured ? `LLM: ${asst.provider}/${asst.model}` : "offline rules mode"}
                </Badge>
                {asst.configured ? (
                  <Badge tone={asst.has_key ? "green" : "amber"}>{asst.has_key ? "key present" : "key missing"}</Badge>
                ) : null}
              </div>
              <p className="text-muted-foreground">
                {asst.configured
                  ? "Provider configured via ASSISTANT_PROVIDER / ASSISTANT_BASE_URL / ASSISTANT_MODEL / ASSISTANT_API_KEY_ENV."
                  : "No LLM configured — the assistant answers from workspace rules and recorded facts only, and clearly states when it cannot help. No network calls are made."}
              </p>
              <p className="text-2xs text-muted-foreground">{asst.setup_help}</p>
              <AssistantChatPanel />
            </div>
          ) : (
            <div className="p-4"><Skeleton className="h-24 w-full" /></div>
          )}
        </SectionCard>

        <SectionCard title="Operational notes" description="known behaviors and limits (documented, not hidden)">
          <ul className="ml-4 list-disc space-y-1.5 p-4 text-xs text-muted-foreground">
            <li>Experiment statuses: <code>created</code> (defined, not submitted), <code>queued</code>, <code>running</code>, <code>paused</code>, <code>completed</code>, <code>failed</code>, <code>cancelled</code>.</li>
            <li>Resume of demo tasks restarts the deterministic run from the beginning (documented behavior).</li>
            <li>GPU-heavy experiment kinds require <code>ENGINE_TORCH=true</code> plus optional extras (<code>requirements-gpu.txt</code>); CPU demos run without them.</li>
            <li>Artifacts are content-addressed and SHA-256 verified on download; corruption raises an integrity error instead of returning data.</li>
            <li>OpenAlex/arXiv/Crossref searches are rate-limited and cached (30 min); failures surface as explicit &lsquo;unavailable&rsquo; notes — never as fabricated results.</li>
            <li>SQLite is the default store; point <code>DATABASE_URL</code> at Postgres for multi-process deployments (docker-compose).</li>
          </ul>
        </SectionCard>
      </div>
    </>
  );
}

function AssistantChatPanel() {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant"; content: string; mode?: string }>>([]);
  const [err, setErr] = useState<string | null>(null);
  const [convId, setConvId] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setBusy(true);
    setErr(null);
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    try {
      const res = await api.post<AssistantChat>("/api/v1/assistant/chat", {
        message: text,
        conversation_id: convId ?? undefined,
      });
      setConvId(res.conversation_id ?? null);
      const mode = res.meta && typeof res.meta.mode === "string" ? res.meta.mode : undefined;
      setMessages((m) => [...m, { role: "assistant", content: res.content, mode }]);
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Assistant request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="max-h-64 space-y-2 overflow-y-auto rounded-md bg-muted/40 p-3 scrollbar-thin">
        {messages.length === 0 ? (
          <p className="text-2xs text-muted-foreground">
            Try: &lsquo;which methods can run right now?&rsquo; or &lsquo;summarize my latest finding&rsquo; — offline answers cite workspace facts only.
          </p>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : ""}>
              <span
                className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-2xs ${
                  m.role === "user" ? "bg-[#18A0FB]/15 text-foreground" : "bg-card text-foreground ring-1 ring-border"
                }`}
              >
                {m.content}
                {m.mode ? <span className="mt-1 block text-[10px] text-muted-foreground">mode: {m.mode}</span> : null}
              </span>
            </div>
          ))
        )}
        {busy ? <p className="text-2xs text-muted-foreground">thinking…</p> : null}
      </div>
      {err ? <p className="text-2xs text-red-400">{err}</p> : null}
      <form onSubmit={send} className="flex items-end gap-2">
        <Field label="Ask the assistant">
          <Textarea
            className="min-h-[44px]"
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. what compression evidence exists so far?"
          />
        </Field>
        <Button type="submit" size="sm" disabled={busy || !input.trim()}>
          <Send className="h-3.5 w-3.5" />
        </Button>
      </form>
    </div>
  );
}
