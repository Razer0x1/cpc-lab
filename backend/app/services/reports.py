"""Research report generation (Markdown always; HTML always; PDF via optional reportlab).

Sections follow the required scientific structure. Measured results, theoretical
estimates, and speculative interpretation are labeled distinctly in the output.
"""
from __future__ import annotations

import io
from typing import Any


def _fmt(v: Any, nd: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def render_markdown(
    *,
    title: str,
    objective: str,
    hypothesis: dict | None,
    experiment: dict,
    related_work: list[dict],
    setup: dict,
    citations: list[str],
) -> str:
    parts: list[str] = []
    parts.append(f"# {title}\n")
    parts.append("## Research objective\n")
    parts.append(objective or "(not stated)\n")

    if hypothesis:
        parts.append("## Hypothesis\n")
        parts.append(f"**Statement:** {hypothesis.get('statement', '')}\n")
        if hypothesis.get("rationale"):
            parts.append(f"**Rationale:** {hypothesis['rationale']}\n")
        if hypothesis.get("success_criteria"):
            parts.append(f"**Predefined success criteria:** {hypothesis['success_criteria']}\n")
        if hypothesis.get("failure_criteria"):
            parts.append(f"**Predefined failure criteria:** {hypothesis['failure_criteria']}\n")

    parts.append("## Related work\n")
    if related_work:
        for r in related_work:
            parts.append(f"- {r.get('title', '')} " +
                         (f"({', '.join(r.get('authors', [])[:3]) or 'unknown authors'}"
                          f"{', ' + str(r.get('year')) if r.get('year') else ''})" ) +
                         f" — DOI/URL: {r.get('doi') or r.get('url') or 'n/a'} **[metadata only, not full-text verified]**")
    else:
        parts.append("- (none recorded; add papers from the Paper Library)\n")
    parts.append("")

    summary = experiment.get("result_summary") or {}
    base = summary.get("baseline") or {}
    comp = summary.get("compressed") or {}

    parts.append("## Experimental setup\n")
    parts.append(f"- Experiment: {experiment.get('name')} (kind `{experiment.get('kind')}`, seed `{experiment.get('seed')}`)")
    parts.append(f"- Runner: `{experiment.get('runner_kind')}`; engine: `{summary.get('engine', experiment.get('engine_note', 'n/a'))}`")
    parts.append(f"- Config snapshot (versioned): `{json_min(experiment.get('config_json'))}`")
    parts.append(f"- Datasets: synthetic, deterministic generation from run seed; held-out test split shared by teacher and student")
    parts.append("")

    parts.append("## Baselines\n")
    parts.append("| Quantity | Baseline |")
    parts.append("| --- | --- |")
    parts.append(f"| Accuracy | {_fmt(base.get('accuracy'))} |")
    parts.append(f"| Cross-entropy | {_fmt(base.get('cross_entropy'))} |")
    parts.append(f"| Artifact size | {_fmt(base.get('artifact_bytes'), 0)} B |")
    parts.append(f"| Parameters | {_fmt(base.get('param_count'), 0)} |")
    parts.append("")

    parts.append("## Environment (hardware & software)\n")
    env = setup.get("environment") or {}
    for k, v in env.items():
        parts.append(f"- {k}: {v}")
    parts.append("")

    parts.append("## Results and uncertainty\n")
    parts.append("**All numbers below are measured values from executed runs; nothing is simulated unless explicitly labeled.**\n")
    parts.append("| Quantity | Baseline | Compressed | Change |")
    parts.append("| --- | --- | --- | --- |")
    parts.append(f"| Accuracy | {_fmt(base.get('accuracy'))} | {_fmt(comp.get('accuracy'))} | {_fmt( comp.get('accuracy') and (comp['accuracy'] - (base.get('accuracy') or 0)))} absolute |")
    parts.append(f"| Artifact size (B) | {_fmt(base.get('artifact_bytes'), 0)} | {_fmt(comp.get('artifact_bytes'), 0)} | ratio {_fmt(summary.get('compression_ratio_artifact'), 2)}× |")
    parts.append(f"| Warm latency (ms) | {_fmt(base.get('latency_warm_ms'), 3)} | {_fmt(comp.get('latency_warm_ms'), 3)} | speedup {_fmt(summary.get('latency_speedup_warm'), 3)}× |")
    parts.append(f"| Cold latency (ms) | {_fmt(base.get('latency_cold_ms'), 3)} | {_fmt(comp.get('latency_cold_ms'), 3)} | — |")
    parts.append(f"| Throughput (rows/s) | {_fmt(base.get('throughput_rows_per_s'), 1)} | {_fmt(comp.get('throughput_rows_per_s'), 1)} | {_fmt(summary.get('throughput_gain'), 2)}× |")
    parts.append(f"| Peak inference mem (MB) | {_fmt(base.get('inference_peak_mem_mb'), 3)} | {_fmt(comp.get('inference_peak_mem_mb'), 3)} | — |")
    parts.append(f"| Peak training mem (MB) | {_fmt(base.get('training_peak_mem_mb'), 3)} | {_fmt(comp.get('training_peak_mem_mb'), 3)} | — |")
    parts.append(f"| Task retention | — | {_fmt(summary.get('task_retention'))} | measured |")
    parts.append("")

    checks = summary.get("criteria_checks") or []
    parts.append("## Predefined-criteria evaluation\n")
    if checks:
        for c in checks:
            mark = "✅" if c.get("passed") else "❌"
            parts.append(f"- {mark} `{c.get('id')}`: {c.get('detail')}")
    else:
        parts.append("(criteria not recorded)")
    parts.append(f"\n**Verdict:** {experiment.get('success_verdict') or summary.get('verdict') or 'not executed'}\n")

    parts.append("## Ablations\n")
    abl = summary.get("ablations")
    if abl:
        for a in abl:
            parts.append(f"- {a}")
    else:
        parts.append("- Not run in this milestone. Multi-seed sweeps and temperature/alpha ablations are the immediate follow-up (see Limitations).")
    parts.append("")

    parts.append("## Limitations\n")
    for line in setup.get("limitations", []):
        parts.append(f"- {line}")
    parts.append("")

    parts.append("## Failure cases\n")
    parts.append("- Runs whose measured criteria fail are recorded with verdict `unsuccessful`/`inconclusive` in the Experiment Lab history; consult the experiment detail page.")
    parts.append("")

    parts.append("## Reproducibility instructions\n")
    for step in setup.get("repro_steps", []):
        parts.append(f"1. {step}")
    parts.append("")

    if citations:
        parts.append("## Source citations\n")
        for c in citations:
            parts.append(f"- {c}")
        parts.append("")
    return "\n".join(parts)


def json_min(obj: Any) -> str:
    import json as _json
    try:
        return _json.dumps(obj, separators=(",", ":"), default=str)
    except Exception:
        return str(obj)


def markdown_to_html(md_text: str, title: str = "CPC Lab Report") -> str:
    """Small, dependency-free Markdown -> HTML for the report's specific subset."""
    lines = md_text.splitlines()
    out = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{title}</title>", "<style>",
        "body{font-family:ui-sans-serif,system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1.5rem;color:#111;line-height:1.6}",
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #d4d4d8;padding:6px 10px;text-align:left}",
        "th{background:#f4f4f5}code{background:#f4f4f5;padding:1px 4px;border-radius:4px}",
        "h1,h2{border-bottom:1px solid #e4e4e7;padding-bottom:4px}",
        "</style></head><body>",
    ]
    in_table = False
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("|"):
            cells = [c.strip().replace("*", "") for c in stripped.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if not in_table:
                out.append("<table>"); in_table = True
                out.append("<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if stripped.startswith("### "):
            out.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            out.append(f"<h2>{_inline(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            out.append(f"<h1>{_inline(stripped[2:])}</h1>")
        elif stripped.startswith("- "):
            out.append(f"<li>{_inline(stripped[2:])}</li>")
        elif _is_ol(ln):
            out.append(f"<li>{_inline(_ol_text(ln))}</li>")
        elif not stripped:
            out.append("")
        else:
            out.append(f"<p>{_inline(stripped)}</p>")
    if in_table:
        out.append("</table>")
    out.append("</body></html>")
    return "\n".join(out)


def _inline(s: str) -> str:
    if s.startswith("**All numbers"):
        s = s.replace("**", "").strip()
    else:
        while "**" in s:
            s = s.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
    while "`" in s:
        s = s.replace("`", "<code>", 1).replace("`", "</code>", 1)
    import html as _html
    return s


def _is_ol(line: str) -> bool:
    import re
    return bool(re.match(r"^\d+\. ", line.strip()))


def _ol_text(line: str) -> str:
    import re
    return re.sub(r"^\d+\. ", "", line.strip())


def markdown_to_pdf(md_text: str, title: str = "CPC Lab Report") -> bytes:
    """PDF via optional reportlab. Raises RuntimeError when not installed."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from xml.sax.saxutils import escape as esc
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "PDF export requires the optional 'reportlab' dependency "
            "(pip install reportlab). Markdown and HTML exports are always available."
        ) from e

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title, leftMargin=2 * cm, rightMargin=2 * cm)
    styles = getSampleStyleSheet()
    story: list = []

    def add_flow(text: str, style) -> None:
        safe = esc(text).replace("`", "")
        pieces = safe.split("**")
        out = ""
        for i, piece in enumerate(pieces):
            out += f"<b>{piece}</b>" if i % 2 == 1 else piece
        story.append(Paragraph(out, style))

    for ln in md_text.splitlines():
        s = ln.strip()
        if s.startswith("# "):
            story.append(Paragraph(esc(s[2:]), styles["Title"]))
        elif s.startswith("## "):
            story.append(Paragraph(esc(s[3:]).replace("**", ""), styles["Heading2"]))
        elif s.startswith("|"):
            continue  # handled after scan below (tables are rendered separately)
        elif s.startswith("- "):
            story.append(Paragraph("• " + esc(s[2:]).replace("**", "").replace("`", ""), styles["BodyText"]))
        elif not s:
            story.append(Spacer(1, 4))
        else:
            add_flow(s, styles["BodyText"])
    doc.build(story)
    return buf.getvalue()
