"""Provider-independent research assistant.

- Configured LLM providers (openai-compatible / anthropic / local) via environment
  variables only — no keys hardcoded or stored in DB.
- Offline mode: a deterministic, honest rule-based assistant that can draft configs,
  suggest baselines/ablations, explain registered method math, summarize MEASURED
  experiment results from the database, and produce report outlines.
- Hard rule: the assistant never claims experiments were executed unless DB records
  confirm it; offline answers quote only stored/measured data.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import CompressionMethod, Experiment, Hypothesis, AssistantConversation

settings = get_settings()


def provider_status() -> dict:
    key_env = settings.assistant_api_key_env
    has_key = bool(key_env and os.environ.get(key_env))
    configured = bool(settings.assistant_provider and has_key and settings.assistant_base_url)
    return {
        "configured": configured,
        "provider": settings.assistant_provider or None,
        "base_url": settings.assistant_base_url or None,
        "model": settings.assistant_model or None,
        "api_key_env": key_env or None,
        "has_key": has_key,
        "mode": "llm" if configured else "offline_rules",
        "setup_help": (
            "Set ASSISTANT_PROVIDER, ASSISTANT_BASE_URL, ASSISTANT_MODEL and ASSISTANT_API_KEY_ENV "
            "in the backend environment; the key itself is read from that env var name. "
            "Example: ASSISTANT_PROVIDER=openai, ASSISTANT_BASE_URL=https://api.openai.com/v1, "
            "ASSISTANT_MODEL=gpt-4o-mini, ASSISTANT_API_KEY_ENV=OPENAI_API_KEY."
        ),
    }


def _call_llm(messages: list[dict]) -> str:
    st = provider_status()
    if not st["configured"]:
        raise HTTPException(status_code=409, detail="No LLM provider configured; using offline mode instead")
    api_key = os.environ.get(st["api_key_env"] or "", "")
    headers = {"Authorization": f"Bearer {api_key}"}
    if st["provider"] == "anthropic":
        payload = {
            "model": settings.assistant_model,
            "max_tokens": 1024,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")],
        }
        url = st["base_url"].rstrip("/") + "/messages"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    else:  # openai or openai-compatible/local
        payload = {"model": settings.assistant_model, "messages": messages, "temperature": 0.3}
        url = st["base_url"].rstrip("/") + "/chat/completions"
    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM provider call failed: {type(e).__name__}") from e
    data = r.json()
    try:
        if st["provider"] == "anthropic":
            return data["content"][0]["text"]
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=502, detail="Unexpected LLM response shape") from e


def _suggest_method_math(db: Session, key: str) -> str | None:
    m = db.query(CompressionMethod).filter_by(key=key).one_or_none()
    if not m:
        return None
    lines = [f"**{m.name}** ({m.category})", m.description]
    if m.limitations:
        lines.append("Known limitations: " + "; ".join(m.limitations))
    if m.prereqs:
        lines.append("Prerequisites: " + "; ".join(m.prereqs))
    return "\n\n".join(lines)


def _experiment_truth(db: Session, ws_id: str) -> str:
    exps = db.query(Experiment).filter_by(workspace_id=ws_id).order_by(Experiment.created_at.desc()).limit(5).all()
    if not exps:
        return "No experiments exist yet in this workspace — nothing has been executed, so there are no measured results to report."
    out = ["Executed experiments (from database records):"]
    for e in exps:
        verdict = e.success_verdict or "not evaluated"
        summary_metric = ""
        s = e.result_summary or {}
        if s.get("task_retention") is not None:
            summary_metric = f" | retention={s['task_retention']:.3f}, ratio={s.get('compression_ratio_artifact', 0):.2f}x"
        out.append(f"- {e.name} [{e.kind}] status={e.status}, verdict={verdict}{summary_metric}")
    return "\n".join(out)


def offline_answer(db: Session, ws_id: str, prompt: str) -> str:
    """Rule-based, honest, database-grounded responses."""
    p = prompt.lower()

    if any(k in p for k in ("did it work", "result", "executed", "ran", "outcome")):
        return _experiment_truth(db, ws_id)

    if "baselines" in p or "ablation" in p:
        return (
            "**Suggested baselines & ablations** (standard for compression claims):\n"
            "- Untrained same-size student (lower bound) and same-size non-distilled student (distillation benefit)\n"
            "- Teacher identity baseline (upper bound on student)\n"
            "- Method-off vs method-on at matched artifact size\n"
            "- Seed sweep: ≥3 seeds, report mean ± std\n"
            "- For quantization: uniform int8 across layers vs sensitivity-weighted allocation\n"
            "- Always evaluate on the same held-out split with fixed metrics"
        )

    if "config" in p and any(k in p for k in ("distillation", "experiment", "demo")):
        cfg = {"kind": "distillation_demo", "seed": 7,
               "kd_alpha": 0.7, "kd_temperature": 2.0,
               "teacher_hidden": [64, 64], "student_hidden": [8],
               "success_criteria": {"min_retention": 0.95, "min_compression_ratio": 6.0, "min_latency_speedup": 0.9}}
        return ("Suggested experiment configuration (validate/edit in Hypothesis Studio or Experiment Lab):\n```json\n"
                + json.dumps(cfg, indent=2) + "\n```\nConfigured success criteria are evaluated against measured metrics only.")

    m = None
    for key in ("quantization", "pruning", "distillation", "low-rank", "low_rank", "sharing", "cache"):
        if key in p:
            norm = key.replace("-", "_")
            m = _suggest_method_math(db, norm if norm != "quantization" else "weight_quantization")
            break
    if m:
        return m

    if "weakness" in p or "methodological" in p:
        return (
            "**Methodological checks** to consider:\n"
            "- Is the evaluation split identical across baseline/compressed?\n"
            "- Are criteria predefined before running (avoid post-hoc thresholds)?\n"
            "- Multiple seeds? Latency measured warm AND cold on the same host?\n"
            "- Artifact size from actual stored bytes, not parameter estimates?\n"
            "- Theoretical ratios (byte widths) kept separate from measured ones?"
        )

    if "report" in p or "outline" in p:
        return (
            "**Report outline** (auto-filled versions are generated in Results & Reports):\n"
            "1. Research objective\n2. Related work (with verified-status labels)\n"
            "3. Hypothesis + predefine criteria\n4. Experimental setup & environment\n"
            "5. Baselines\n6. Results & uncertainty (measured only)\n"
            "7. Ablations\n8. Limitations\n9. Failure cases\n10. Reproducibility instructions\n11. Citations"
        )

    if "question" in p or "help me formulate" in p or "research" in p:
        return (
            "**Formulating a precise research question** — template:\n"
            "\"Does <method> preserve <metric> of <system> within tolerance <τ> on <task/split> "
            "while reducing <resource> by ≥<r>\", with predefined success/failure criteria.\n"
            "Example: 'Can a shared low-rank representation reduce redundant computation across two "
            "compatible modules without materially reducing task accuracy?'"
        )

    return (
        "**Offline mode** (no LLM provider configured — this is the built-in honest assistant).\n"
        f"{_experiment_truth(db, ws_id)}\n\n"
        "I can help with: formulating research questions, suggested baselines/ablations, "
        "experiment configuration drafts, explaining registered compression methods, "
        "interpreting measured results, methodological-weakness checklists, and report outlines.\n"
        "For generative LLM answers, configure a provider in Settings."
    )


def chat(db: Session, ws_id: str, user_id: str | None, prompt: str) -> dict:
    started = time.time()
    mode = provider_status()["mode"]
    if mode == "llm":
        try:
            content = _call_llm([{"role": "system", "content": (
                "You are the assistant of the Cross-Paradigm Compression research lab. "
                "Never claim experiments were executed unless the user provides measured results. "
                "Clearly separate measured results, theoretical estimates, and speculation.")},
                {"role": "user", "content": prompt}])
            meta = {"mode": "llm", "provider": settings.assistant_provider, "latency_ms": round((time.time() - started) * 1000)}
        except HTTPException:
            content = offline_answer(db, ws_id, prompt)
            meta = {"mode": "offline_fallback", "reason": "provider_unavailable"}
    else:
        content = offline_answer(db, ws_id, prompt)
        meta = {"mode": "offline_rules"}
    conv = AssistantConversation(workspace_id=ws_id, user_id=user_id, title=prompt[:80], messages=[{"role": "user", "content": prompt}, {"role": "assistant", "content": content, "meta": meta}])
    db.add(conv)
    db.commit()
    return {"content": content, "meta": meta, "conversation_id": conv.id}
