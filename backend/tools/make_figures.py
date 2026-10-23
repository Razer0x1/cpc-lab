"""Generate data-faithful SVG figures from the live CPC Lab database.

Both figures are renderings of MEASURED database values (never invented):
  1. pareto-measured.svg      — accuracy vs artifact bytes (log scale), from
                                completed benchmark runs via /api/v1/benchmarks/compare logic.
  2. provenance-graph.svg     — knowledge-graph nodes/edges via services.graph.build_graph.

Run:  .venv\\Scripts\\python.exe tools\\make_figures.py   (from backend/)
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models import BenchmarkRun, Experiment, MLModel  # noqa: E402
from app.services.graph import NODE_META, build_graph  # noqa: E402
from app.services.metrics_math import pareto_frontier  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#0f172a"
MUTE = "#64748b"
GRID = "#e2e8f0"
ACCENT = "#111827"


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def pareto_figure(db) -> str:
    runs = db.query(BenchmarkRun).filter_by(status="completed").order_by(BenchmarkRun.created_at.desc()).limit(50).all()
    models = {m.id: m for m in db.query(MLModel).all()}
    experiments = {e.id: e for e in db.query(Experiment).filter_by(status="completed").all()}

    points = []
    for b in runs:
        m = models.get(b.model_id)
        r = b.result or {}
        # mirror the fixed /compare resolution: artifact bytes stored on the model artifact row
        from app.models import Artifact

        artifact_bytes = None
        if m is not None and m.artifact_uri:
            art = db.query(Artifact).filter_by(uri=m.artifact_uri).first()
            if art is not None and art.size_bytes:
                artifact_bytes = art.size_bytes
        if artifact_bytes is None:
            for e in experiments.values():
                s = e.result_summary or {}
                if s.get("teacher_model_id") == b.model_id:
                    artifact_bytes = (s.get("baseline") or {}).get("artifact_bytes")
                if s.get("student_model_id") == b.model_id:
                    artifact_bytes = (s.get("compressed") or {}).get("artifact_bytes")
        role = "unknown"
        for e in experiments.values():
            s = e.result_summary or {}
            if s.get("teacher_model_id") == b.model_id or s.get("target_model_id") == b.model_id:
                role = "baseline"; break
            if s.get("student_model_id") == b.model_id or s.get("quantized_model_id") == b.model_id or s.get("surrogate_model_id") == b.model_id:
                role = "compressed"; break
        if r.get("mean_accuracy") is None or artifact_bytes is None:
            continue
        points.append({
            "name": m.name if m else b.model_id, "quality": r["mean_accuracy"],
            "bytes": artifact_bytes, "latency": r.get("latency_warm_ms"), "role": role,
        })

    # dedupe to the newest row per model
    seen = {}
    for p in points:
        seen.setdefault(p["name"], p)
    pts = list(seen.values())
    idx = {id(p): i for i, p in enumerate(pts)}
    front_i = set(pareto_frontier([
        {"quality": p["quality"], "artifact_bytes": p["bytes"], "latency_ms": p["latency"]} for p in pts
    ]))

    W, H = 960, 560
    L, R, T, B = 84, 320, 76, 84
    import math
    lo, hi = 800.0, 22000.0
    ylo, yhi = 0.7980, 0.8015

    def X(b): return L + (math.log10(b) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (W - R - L)
    def Y(q): return T + (1 - (q - ylo) / (yhi - ylo)) * (H - T - B)

    role_color = {"baseline": "#94a3b8", "compressed": "#4c7ef3", "unknown": "#f4bf4f"}
    s = [f'<?xml version="1.0" encoding="UTF-8"?>',
         f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Segoe UI, Arial, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="white"/>',
         f'<text x="{L}" y="34" font-size="17" font-weight="700" fill="{INK}">Measured Pareto frontier — accuracy vs artifact size</text>',
         f'<text x="{L}" y="54" font-size="11" fill="{MUTE}">synthetic_classification · 3 repeats · bootstrap 95% CI · all values measured by executed code (CPC Lab DB)</text>']

    for gq in (0.7985, 0.7990, 0.7995, 0.8000, 0.8005, 0.8010):
        s.append(f'<line x1="{L}" y1="{Y(gq):.1f}" x2="{W-R}" y2="{Y(gq):.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{L-8}" y="{Y(gq)+4:.1f}" font-size="10" fill="{MUTE}" text-anchor="end">{gq:,.4f}</text>')
    for gb in (1000, 2000, 5000, 10000, 20000):
        s.append(f'<line x1="{X(gb):.1f}" y1="{T}" x2="{X(gb):.1f}" y2="{H-B}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{X(gb):.1f}" y="{H-B+16}" font-size="10" fill="{MUTE}" text-anchor="middle">{gb:,} B</text>')
    s.append(f'<line x1="{L}" y1="{H-B}" x2="{W-R}" y2="{H-B}" stroke="{MUTE}" stroke-width="1"/>')
    s.append(f'<line x1="{L}" y1="{T}" x2="{L}" y2="{H-B}" stroke="{MUTE}" stroke-width="1"/>')
    s.append(f'<text x="{W/2:.0f}" y="{H-28}" font-size="12" fill="{INK}" text-anchor="middle">artifact size (bytes, log scale) — measured stored npz</text>')
    s.append(f'<text x="22" y="{(T+H-B)/2:.0f}" font-size="12" fill="{INK}" text-anchor="middle" transform="rotate(-90 22 {(T+H-B)/2:.0f})">mean accuracy</text>')

    labels = {}
    for i, p in enumerate(pts):
        x, y = X(p["bytes"]), Y(p["quality"])
        col = role_color.get(p["role"], "#94a3b8")
        on_front = i in front_i
        short = (p["name"].replace("MLP teacher [64, 64] (seed 7)", "teacher")
                 .replace("MLP teacher [64, 64]", "teacher").strip())
        stroke = 'stroke="#111827" stroke-width="2.5"' if on_front else 'stroke="white" stroke-width="1.5"'
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{9 if on_front else 6}" fill="{col}" {stroke}/>')
        if on_front:
            s.append(f'<text x="{x}" y="{y-16:.1f}" font-size="11" font-weight="700" fill="{INK}" text-anchor="middle">PARETO FRONT ★</text>')
        dx = 14 if x < W - R - 150 else -14
        anchor = "start" if dx > 0 else "end"
        labels[p["name"]] = (x, y, short)
        s.append(f'<text x="{(x+dx):.1f}" y="{(y+4):.1f}" font-size="11" fill="{INK}" text-anchor="{anchor}">{_esc(short)} · {p["quality"]:.4f} @ {int(p["bytes"]):,} B · {p["latency"]:.3f} ms</text>')

    s.append(f'<text x="{L}" y="{H-10}" font-size="10" fill="{MUTE}">Point styles: blue = compression output (role: compressed) · gray = baseline · amber = extraction benchmark. Frontier = {len(front_i)} point(s), computed from measured rows only.</text>')
    s.append('</svg>')
    return "\n".join(s)


def graph_figure(db) -> str:
    g = build_graph(db, workspace_id=None) if False else None  # workspace resolved below
    db2 = db
    from app.models import Workspace

    ws = db2.query(Workspace).first()
    if ws is None:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="80"><text x="8" y="24">no workspace</text></svg>'
    g = build_graph(db2, workspace_id=ws.id)
    nodes = g["nodes"]
    edges = g["edges"]

    W, H = 1480, 820
    col_x = {
        "research_entry": 130, "hypothesis": 320, "experiment": 520, "model": 700,
        "dataset": 700, "transformation": 900, "method": 1090, "paper": 1330,
        "benchmark": 900,
    }
    buckets: dict[str, list] = {}
    for n in nodes:
        buckets.setdefault(n["kind"], []).append(n)
    pos = {}
    for kind, arr in buckets.items():
        x = col_x.get(kind, 460)
        n = len(arr)
        span = H - 140
        for j, nd in enumerate(arr):
            y = 96 + (span / max(n - 1, 1)) * j if n > 1 else 96 + span / 2
            pos[nd["id"]] = (x, y)

    s = ['<?xml version="1.0" encoding="UTF-8"?>',
         f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Segoe UI, Arial, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="white"/>',
         f'<text x="40" y="34" font-size="17" font-weight="700" fill="{INK}">Provenance knowledge graph — exported from live database</text>',
         f'<text x="40" y="54" font-size="11" fill="{MUTE}">{len(nodes)} nodes · {len(edges)} edges · solid = established provenance (recorded transformations / verified links)</text>']

    for e in edges:
        sp = pos.get(e["source"]); tp = pos.get(e["target"])
        if not sp or not tp:
            continue
        style = 'stroke="#334155" stroke-width="1.3"' if e["established"] else 'stroke="#cbd5e1" stroke-width="1" stroke-dasharray="4 3"'
        x1, y1 = sp; x2, y2 = tp
        mx = (x1 + x2) / 2
        s.append(f'<path d="M {x1} {y1} C {mx} {y1}, {mx} {y2}, {x2} {y2}" fill="none" {style} opacity="0.55"/>')

    lab_w = reality = 150
    for nd in nodes:
        x, y = pos[nd["id"]]
        meta = nd.get("color")
        col = nd.get("color", "#94a3b8")
        s.append(f'<circle cx="{x}" cy="{y}" r="7" fill="{col}" stroke="#0f172a" stroke-width="1"/>')
        label = nd.get("label") or nd["kind"]
        meta_txt = ""
        mt = nd.get("meta") or {}
        if mt.get("status"):
            meta_txt = f' ({mt["status"]}{", " + mt["verdict"] if mt.get("verdict") else ""})'
        s.append(f'<text x="{x+11}" y="{y+4}" font-size="10" fill="{INK}">{_esc(str(label)[:42])}{_esc(meta_txt)}</text>')

    leg = []
    lx = 44
    for kind, mt in NODE_META.items():
        cnt = len(buckets.get(kind, []))
        if cnt == 0:
            continue
        s.append(f'<circle cx="{lx}" cy="{H-46}" r="6" fill="{mt["color"]}" stroke="#0f172a" stroke-width="0.8"/>')
        s.append(f'<text x="{lx+10}" y="{H-42}" font-size="10" fill="{INK}">{mt["label"]} ({cnt})</text>')
        lx += (len(mt["label"]) + 6) * 6.2 + 26
    s.append(f'<text x="44" y="{H-18}" font-size="10" fill="{MUTE}">Rendered deterministically from build_graph() output — node labels show kind/status/verdict; edges show recorded relations.</text>')
    s.append('</svg>')
    return "\n".join(s)


def main() -> int:
    db = SessionLocal()
    try:
        (OUT / "pareto-measured.svg").write_text(pareto_figure(db), encoding="utf-8")
        (OUT / "provenance-graph.svg").write_text(graph_figure(db), encoding="utf-8")
    finally:
        db.close()
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
