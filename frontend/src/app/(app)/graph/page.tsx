"use client";
/** Knowledge Graph: hypotheses ⇄ experiments ⇄ papers ⇄ models ⇄ methods as an interactive graph. */
import { useMemo, useState, type MouseEvent, type ReactNode } from "react";
import {
  Background, Controls, MarkerType, MiniMap, ReactFlow,
  type Edge, type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useApi } from "@/lib/api";
import type { GraphData } from "@/lib/types";
import { PageHeader, SectionCard } from "@/components/shared";
import { Badge, EmptyState, Skeleton } from "@/components/ui/primitives";

const KIND_ORDER = ["hypothesis", "experiment", "paper", "model", "dataset", "method", "transformation", "benchmark", "research_entry"];

const KIND_STYLE: Record<string, { color: string; label: string }> = {
  hypothesis: { color: "#8b7cf6", label: "Hypothesis" },
  experiment: { color: "#4c7ef3", label: "Experiment" },
  paper: { color: "#5eead4", label: "Paper" },
  model: { color: "#f4bf4f", label: "Model" },
  dataset: { color: "#e09e5e", label: "Dataset" },
  method: { color: "#f472b6", label: "Compression method" },
  transformation: { color: "#94a3b8", label: "Transformation" },
  benchmark: { color: "#a3e635", label: "Benchmark run" },
  research_entry: { color: "#c084fc", label: "Research question" },
};

export default function GraphPage() {
  const { data, error, loading, refresh } = useApi<GraphData>("/api/v1/graph", 20000);
  const [enabled, setEnabled] = useState<Record<string, boolean>>(
    () => Object.fromEntries(KIND_ORDER.map((k) => [k, true]))
  );
  const [selected, setSelected] = useState<GraphData["nodes"][number] | null>(null);

  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [] as Node[], edges: [] as Edge[] };
    const activeKinds = new Set(KIND_ORDER.filter((k) => enabled[k]));
    const kept = data.nodes.filter((n) => activeKinds.has(n.kind));
    const keptIds = new Set(kept.map((n) => n.id));

    // column layout: one column per kind present
    const presentKinds = KIND_ORDER.filter((k) => kept.some((n) => n.kind === k));
    const colX = new Map(presentKinds.map((k, i) => [k, i * 280]));
    const perKindIndex = new Map<string, number>();
    const rfNodes: Node[] = kept.map((n) => {
      const idx = perKindIndex.get(n.kind) ?? 0;
      perKindIndex.set(n.kind, idx + 1);
      return {
        id: n.id,
        type: "default",
        position: { x: colX.get(n.kind) ?? 0, y: idx * 92 },
        data: { label: n.label.slice(0, 60) },
        style: {
          background: "hsl(var(--card))",
          color: "hsl(var(--foreground))",
          fontSize: 11,
          width: 220,
          borderRadius: 8,
          border: `1.5px solid ${KIND_STYLE[n.kind]?.color ?? n.color}`,
        },
      };
    });
    const rfEdges: Edge[] = data.edges
      .filter((e) => keptIds.has(e.source) && keptIds.has(e.target))
      .map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: `${e.relation}${e.established === "verified" ? " ✓" : ""}`,
        labelStyle: { fontSize: 9, fill: "hsl(var(--muted-foreground))" },
        labelBgStyle: { fill: "hsl(var(--card))" },
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 4,
        animated: e.established === "verified",
        style: {
          stroke: e.established === "verified" ? "#18A0FB" : "hsl(var(--muted-foreground))",
          strokeWidth: 1.2,
        },
        markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: e.established === "verified" ? "#18A0FB" : "hsl(var(--muted-foreground))" },
      }));
    return { nodes: rfNodes, edges: rfEdges };
  }, [data, enabled]);

  function onNodeClick(_e: MouseEvent, node: Node) {
    const n = (data?.nodes ?? []).find((x) => x.id === node.id);
    setSelected(n ?? null);
  }

  const anyEnabled = Object.values(enabled).some(Boolean);

  return (
    <>
      <PageHeader
        title="Knowledge Graph"
        subtitle="Provenance graph across the workspace: solid animated edges are user-verified links, muted edges are structural relations."
        actions={
          <button onClick={() => refresh()} className="text-xs text-[#18A0FB] hover:underline">Reload graph</button>
        }
      />

      <div className="mb-4 flex flex-wrap gap-1.5">
        {KIND_ORDER.map((k) => (
          <button
            key={k}
            onClick={() => setEnabled((prev) => ({ ...prev, [k]: !prev[k] }))}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-2xs transition-colors ${
              enabled[k] ? "border-transparent text-foreground" : "border-border text-muted-foreground opacity-60"
            }`}
            style={enabled[k] ? { background: `${KIND_STYLE[k]?.color}22`, borderColor: `${KIND_STYLE[k]?.color}66` } : undefined}
          >
            <span className="h-2 w-2 rounded-full" style={{ background: KIND_STYLE[k]?.color }} />
            {KIND_STYLE[k]?.label ?? k}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-border bg-card/40">
        {loading && !data ? (
          <div className="h-[560px] p-6"><Skeleton className="h-full w-full" /></div>
        ) : error ? (
          <p className="p-6 text-xs text-red-400">{error}</p>
        ) : !data || data.nodes.length === 0 || !anyEnabled ? (
          <div className="h-[560px] grid place-items-center p-6">
            <EmptyState
              title="Graph is empty"
              description="Create hypotheses, run experiments, and link papers — the graph connects them automatically."
            />
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={onNodeClick}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.1}
            proOptions={{ hideAttribution: false }}
          >
            <Background color="hsl(var(--border))" gap={18} />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              style={{ background: "hsl(var(--card))" }}
              maskColor="hsl(var(--background) / 0.6)"
              nodeColor={(n) => KIND_STYLE[(n as { id: string }).id.split(":")[0]]?.color ?? "#94a3b8"}
            />
          </ReactFlow>
        )}
      </div>

      {selected ? (
        <SectionCard className="mt-5" title={selected.label} description={`kind: ${KIND_STYLE[selected.kind]?.label ?? selected.kind}`}>
          <div className="p-4 text-xs">
            {Object.keys(selected.meta).length === 0 ? (
              <p className="text-muted-foreground">No additional metadata on this node.</p>
            ) : (
              <dl className="grid gap-2 sm:grid-cols-2">
                {Object.entries(selected.meta).map(([k, v]) => (
                  <div key={k} className="min-w-0">
                    <dt className="text-2xs uppercase tracking-wide text-muted-foreground">{k.replace(/_/g, " ")}</dt>
                    <dd className="truncate">{typeof v === "object" ? JSON.stringify(v).slice(0, 120) : String(v).slice(0, 160)}</dd>
                  </div>
                ))}
              </dl>
            )}
            <p className="mt-3 text-2xs text-muted-foreground">Node id: <code>{selected.id}</code> {selected.kind === "experiment" ? (
              <a href={`/experiments/${selected.id.split(":")[1]}`} className="text-[#18A0FB] hover:underline">open →</a>
            ) : selected.kind === "hypothesis" ? (
              <a href="/hypotheses" className="text-[#18A0FB] hover:underline">open studio →</a>
            ) : selected.kind === "paper" ? (
              <a href="/papers" className="text-[#18A0FB] hover:underline">open library →</a>
            ) : null}
            </p>
          </div>
        </SectionCard>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-2 text-2xs text-muted-foreground">
        <LegendDot color="#18A0FB" label="verified link (user-established provenance)" />
        <LegendDot color="hsl(var(--muted-foreground))" label="structural relation" />
      </div>
    </>
  );
}

function LegendDot({ color, label }: { color: string; label: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-full" style={{ background: color, color: "hsl(var(--muted-foreground))" }} />
      <Badge tone="neutral">{label}</Badge>
    </span>
  );
}
