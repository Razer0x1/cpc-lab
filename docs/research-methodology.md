# Research Methodology (evidence & honesty policy)

## 1. Evidence classification

Hypotheses carry an `evidence_level` that may only be advanced by actual runs:

```
idea_only → literature_supported → implemented → experimentally_tested → independently_reproduced
```

- `literature_supported` may be set only by a **user-verified** literature link (Paper Library /
  Hypothesis Studio link action). Search results themselves never raise evidence levels —
  absence/presence of papers is not proof.
- `implemented` requires an experiment to have been **executed** on the hypothesis.
- `experimentally_tested` requires a completed run with a measured verdict; the UI shows the
  generic reminder for `idea_only` items: *"Evidence level propagates only from actual runs,
  never from paper searches."*

## 2. Verdicts are computed against declared criteria

Experiments reach one of three verdicts (`successful`, `unsuccessful`, `inconclusive`) by
comparing **measured** metrics against the configured success criteria in
`services/tasks/*.py`. No verdict is ever invented; unfinished/cancelled runs have no verdict.

## 3. Measured metrics in this milestone

| Metric | How it is measured |
|---|---|
| `accuracy` (baseline / compressed) | generated test split (seed = run seed + 1), argmax vs labels — real forward passes through NumPy MLPs |
| `cross_entropy` | teacher vs student, same split |
| `compression_ratio_artifact` | byte-length ratio of stored NPZ artifacts (intended = parameter struct ratio for reference) |
| `task_retention` | compressed / baseline accuracy |
| `latency_warm` / `latency_cold` | Python timer loops; **warm** = repeated calls, **cold** = fresh interpreter overhead model documented in limitations |
| `throughput` | samples/second from the same loop |
| `peak_memory` | `tracemalloc` peak of the inference/quantization code paths |

The overview dashboard averages only `stage=measured` rows from `completed` experiments and
shows `—` (never a fake number) when nothing is measured yet.

## 4. Reproducibility contract

- Deterministic NumPy engines with fixed seeds (dataset generated from the run's seed).
- Config + budgets are snapshotted (`config_version`) and immutable during runs.
- Logs are append-only with sequence numbers; the volatile trace is served through
  `"logs"`-polling or SSE, and the DB log is the durable record.
- Reports embed the exact config snapshot, seed, environment note, explicit limitation list,
  and reproducibility steps — anyone can re-run and land on the same numbers.

## 5. Documented limitations (also emitted into every report)

- Host-specific single-node latency; do not generalize.
- No energy measurements (requires hardware instrumentation — future milestone).
- Synthetic benchmark `cpc_spiral3` is a controlled task, not ImageNet-scale evidence.
- Single seed by default; multi-seed sweeps are next.
- Availability: Planned engines (pruning / low-rank / 4-bit / LTT evaluation / torch+HF tasks)
  are **documented but not executed**; attempting to run them fails loudly instead of producing
  plausible-looking numbers.

## 6. Provenance rules for papers

- Scholarly search returns **bibliographic metadata only**; `fulltext_verified` stays `false`
  until a verified-ingestion pass runs.
- Ingestion is deduplicated by (`source`, `external_id`).
- The Knowledge Graph separates **verified** links (explicit user link actions, animated solid
  edges) from structural relations (created models/used datasets).
