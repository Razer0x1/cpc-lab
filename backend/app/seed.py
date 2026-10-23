"""Idempotent database seeding: admin user, workspace, compression methods,
curated cross-paradigm research entries, bibliographic references, compute resources.

Seed data is CURATED knowledge (provenance='curated'), clearly separated from anything
the experiments produce. No fabricated metrics are ever seeded.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    CompressionMethod, ComputeResource, Paper, ResearchEntry, ResearchProject,
    SourceRef, User, Workspace, WorkspaceMember,
)
from .security import hash_password

settings = get_settings()


METHODS: list[dict] = [
    {
        "key": "weight_quantization", "name": "Weight Quantization", "category": "quantization",
        "description": "Reduce weight precision (e.g. float32 -> int8/int4) with per-tensor or per-channel scales. Post-training or quantization-aware.",
        "config_schema": {"bits": {"type": "enum", "options": [2, 4, 8], "default": 8},
                           "granularity": {"type": "enum", "options": ["per_tensor", "per_channel"], "default": "per_tensor"}},
        "prereqs": ["Target model registered with a stored artifact (float32 preferred)"],
        "supported_models": ["mlp", "transformer (engine planned)", "cnn (engine planned)"],
        "limitations": ["May reduce accuracy, especially with heavy outlier activations",
                         "Measured 'compression ratio' counts fp32-scale metadata; byte-width ratios are theoretical",
                         "Real int8 kernel speedups need ONNX Runtime or native kernels; dequantize-on-load may not speed up small models"],
        "engine": "builtin_numpy",
    },
    {
        "key": "pruning_unstructured", "name": "Unstructured Magnitude Pruning", "category": "pruning_unstructured",
        "description": "Remove individual weights by magnitude threshold; sparse storage required to realize size/compute savings.",
        "config_schema": {"sparsity": {"type": "range", "min": 0.0, "max": 0.95, "default": 0.5}},
        "prereqs": ["Trained model artifact", "Sparse-aware runtime for actual speedup"],
        "supported_models": ["mlp (engine planned)", "transformer (engine planned)"],
        "limitations": ["Unstructured sparsity rarely accelerates dense hardware without specialized kernels",
                         "Requires fine-tuning to recover accuracy at high sparsity"],
        "engine": "planned_documented",
    },
    {
        "key": "pruning_structured", "name": "Structured Pruning (channels/heads)", "category": "pruning_structured",
        "description": "Remove whole channels, attention heads, or layers so the pruned model runs on dense kernels.",
        "config_schema": {"sparsity": {"type": "range", "min": 0.0, "max": 0.9, "default": 0.3},
                           "unit": {"type": "enum", "options": ["channel", "head", "layer"], "default": "channel"}},
        "prereqs": ["Architectural simulator for the target family"],
        "supported_models": ["mlp (engine planned)", "transformer (engine planned)"],
        "limitations": ["Structure choice interacts with accuracy in non-obvious ways", "May need retraining"],
        "engine": "planned_documented",
    },
    {
        "key": "knowledge_distillation", "name": "Knowledge Distillation", "category": "distillation",
        "description": "Train a smaller student to match a larger teacher's soft outputs (temperature-scaled KL) plus the hard label loss.",
        "config_schema": {"kd_alpha": {"type": "range", "min": 0, "max": 1, "default": 0.7},
                           "kd_temperature": {"type": "range", "min": 0.5, "max": 10, "default": 2.0},
                           "student_hidden": {"type": "list_int", "default": [8]}},
        "prereqs": ["Teacher model (or demo trains an internal teacher)", "Shared labeled evaluation split"],
        "supported_models": ["mlp (engine builtin_numpy)", "transformer (HF engine: optional GPU extras)"],
        "limitations": ["Student accuracy is bounded by teacher quality and capacity gap",
                         "Self-distillation and task shift can change which temperature helps",
                         "Results are per-model-per-device; no universal guarantee"],
        "engine": "builtin_numpy",
    },
    {
        "key": "low_rank_factorization", "name": "Low-Rank Factorization", "category": "low_rank_factorization",
        "description": "Approximate dense weight matrices as products of skinny matrices (SVD/LoRA-style), shrinking parameters and FLOPs.",
        "config_schema": {"student_hidden": {"type": "list_int", "default": [16]},
                           "rank": {"type": "range", "min": 1, "max": 256, "default": 16}},
        "prereqs": ["Weight matrix access", "Rank selection or tuning budget"],
        "supported_models": ["mlp (engine planned)", "transformer (engine planned)"],
        "limitations": ["Rank too low damages accuracy; energy retention in weights is task-dependent",
                         "Speedup depends on hardware batching behavior"],
        "engine": "planned_documented",
    },
    {
        "key": "parameter_sharing", "name": "Parameter Sharing (incl. ALBERT-style)", "category": "parameter_sharing",
        "description": "Reuse the same weights across layers or modules; reduces parameters without changing depth.",
        "config_schema": {"share": {"type": "enum", "options": ["layers", "towers"], "default": "layers"}},
        "prereqs": ["Repetitive or homogeneous structure analysis"],
        "supported_models": ["transformer (engine planned)", "rnn (engine planned)"],
        "limitations": ["Compute is NOT reduced when depth stays constant", "Quality depends on representation compatibility across layers"],
        "engine": "planned_documented",
    },
    {
        "key": "activation_cache_optimization", "name": "Activation/Cache Optimization", "category": "activation_cache_optimization",
        "description": "Compress KV caches, activations, or retrieval memories (quantized/moving-average/eviction) for inference efficiency.",
        "config_schema": {"cache_bits": {"type": "enum", "options": [4, 8, 16], "default": 8},
                           "strategy": {"type": "enum", "options": ["quantize", "evict_lru", "low_rank"], "default": "quantize"}},
        "prereqs": ["Sequence-length workload analysis", "Memory profiling harness"],
        "supported_models": ["transformer (engine planned)", "ssm (engine planned)"],
        "limitations": ["Long-context quality loss from aggressive cache compression", "No FLOP savings, memory-bandwidth bounded"],
        "engine": "planned_documented",
    },
    {
        "key": "architecture_simplification", "name": "Architecture Simplification", "category": "architecture_simplification",
        "description": "Replace expensive blocks with cheaper equivalents (gating, linear attention, fusing ops) validated against behavior thresholds.",
        "config_schema": {"target": {"type": "enum", "options": ["layer_fuse", "gating", "kernel_replace"], "default": "layer_fuse"}},
        "prereqs": ["Behavioral equivalence tolerance must be predefined"],
        "supported_models": ["transformer (engine planned)", "mlp (engine planned)"],
        "limitations": ["Equivalence must be tested per model; shape-similarity is NOT behavioral interchangeability"],
        "engine": "planned_documented",
    },
    {
        "key": "reverse_engineering", "name": "Reverse Engineering (black-box surrogate)", "category": "reverse_engineering",
        "description": "Reconstruct a compact surrogate from a trained model's behavior alone: query the target's forward function (documented domain), fit a small student on the responses, and measure held-out agreement plus compression.",
        "config_schema": {
            "surrogate_hidden": {"type": "list_int", "default": [8]},
            "temperature": {"type": "range", "min": 0.5, "max": 10, "default": 2.0},
            "soft_weight": {"type": "range", "min": 0, "max": 1, "default": 0.9},
            "query_budget": {"type": "range", "min": 200, "max": 50000, "default": 3000},
            "query_range": {"type": "range", "min": 0.5, "max": 4.0, "default": 1.2},
        },
        "prereqs": ["Forward-query access to the target artifact's predictions",
                     "Documented input domain (query distribution must be stated)"],
        "supported_models": ["mlp (engine builtin_numpy)", "transformer (engine planned)"],
        "limitations": [
            "Agreement guarantees are restricted to the queried domain; extrapolation is unmeasured risk",
            "Surrogate fidelity is bounded by query coverage, student capacity and target smoothness",
            "Ethics/legality: extracting hosted third-party models may violate ToS; this engine documents access as black-box and is intended for locally owned artifacts",
            "Soft-response training uses teacher forward outputs — hard-label truth is never required"
        ],
        "engine": "builtin_numpy",
    },
    {
        "key": "hybrid_combination", "name": "Hybrid Combination", "category": "hybrid",
        "description": "Chain compatible methods (e.g. distill then quantize) respecting order and tolerance budgets.",
        "config_schema": {"chain": {"type": "list_str", "default": ["knowledge_distillation", "weight_quantization"]}},
        "prereqs": ["Every chained method's own prerequisites"],
        "supported_models": ["mlp (via chained engines)"],
        "limitations": ["Errors compound across the chain; each stage needs its own evaluation gate"],
        "engine": "builtin_numpy",
    },
]


PAPERS: list[dict] = [
    {"source": "manual", "external_id": "arXiv:1706.03762", "title": "Attention Is All You Need",
     "authors": ["A. Vaswani", "N. Shazeer", "N. Parmar", "J. Uszkoreit", "L. Jones", "A. Gomez", "L. Kaiser", "I. Polosukhin"],
     "year": 2017, "venue": "NeurIPS", "doi": "10.48550/arXiv.1706.03762", "url": "https://arxiv.org/abs/1706.03762",
     "concepts": ["transformer", "attention"]},
    {"source": "manual", "external_id": "arXiv:2312.00752", "title": "Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
     "authors": ["A. Gu", "T. Dao"], "year": 2023, "venue": "arXiv", "doi": "10.48550/arXiv.2312.00752",
     "url": "https://arxiv.org/abs/2312.00752", "concepts": ["state_space_models", "sequence_modeling"]},
    {"source": "manual", "external_id": "arXiv:2106.09685", "title": "LoRA: Low-Rank Adaptation of Large Language Models",
     "authors": ["E. Hu", "Y. Shen", "P. Wallis", "Z. Allen-Zhu", "Y. Li", "S. Wang", "L. Wang", "W. Chen"],
     "year": 2021, "venue": "ICLR", "doi": "10.48550/arXiv.2106.09685", "url": "https://arxiv.org/abs/2106.09685",
     "concepts": ["low_rank", "parameter_efficient_adaptation"]},
    {"source": "manual", "external_id": "arXiv:1503.02531", "title": "Distilling the Knowledge in a Neural Network",
     "authors": ["G. Hinton", "O. Vinyals", "J. Dean"], "year": 2015, "venue": "NeurIPS Deep Learning Workshop",
     "doi": "10.48550/arXiv.1503.02531", "url": "https://arxiv.org/abs/1503.02531",
     "concepts": ["knowledge_distillation", "compression"]},
    {"source": "manual", "external_id": "arXiv:1803.03635", "title": "The Lottery Ticket Hypothesis: Finding Sparse, Trainable Neural Networks",
     "authors": ["J. Frankle", "M. Carbin"], "year": 2019, "venue": "ICLR", "doi": "10.48550/arXiv.1803.03635",
     "url": "https://arxiv.org/abs/1803.03635", "concepts": ["pruning", "sparsity"]},
    {"source": "manual", "external_id": "arXiv:2404.19756", "title": "KAN: Kolmogorov-Arnold Networks",
     "authors": ["Z. Liu", "Y. Wang", "S. Vaidya", "F. Ruehle", "J. Halverson", "M. Soljačić", "T. Hou", "M. Tegmark"],
     "year": 2024, "venue": "arXiv", "doi": "10.48550/arXiv.2404.19756", "url": "https://arxiv.org/abs/2404.19756",
     "concepts": ["learnable_activation", "symbolic", "interpretability"]},
    {"source": "manual", "external_id": "arXiv:2006.11239", "title": "Denoising Diffusion Probabilistic Models",
     "authors": ["J. Ho", "A. Jain", "P. Abbeel"], "year": 2020, "venue": "NeurIPS", "doi": "10.48550/arXiv.2006.11239",
     "url": "https://arxiv.org/abs/2006.11239", "concepts": ["diffusion", "variational_inference"]},
    {"source": "manual", "external_id": "arXiv:1911.00172", "title": "Generalization through Memorization: Nearest Neighbor Language Models",
     "authors": ["U. Khandelwal", "O. Levy", "D. Jurafsky", "L. Zettlemoyer", "M. Lewis"], "year": 2020, "venue": "ICLR",
     "doi": "10.48550/arXiv.1911.00172", "url": "https://arxiv.org/abs/1911.00172",
     "concepts": ["retrieval_augmentation", "external_memory"]},
    {"source": "manual", "external_id": "arXiv:1503.02406", "title": "Deep Learning and the Information Bottleneck Principle",
     "authors": ["N. Tishby", "N. Zaslavsky"], "year": 2015, "venue": "IEEE Information Theory Workshop",
     "doi": "10.48550/arXiv.1503.02406", "url": "https://arxiv.org/abs/1503.02406",
     "concepts": ["information_bottleneck", "representation_learning"]},
    {"source": "manual", "external_id": "arXiv:2205.14135", "title": "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness",
     "authors": ["T. Dao", "D. Fu", "S. Ermon", "A. Rudra", "C. Ré"], "year": 2022, "venue": "NeurIPS",
     "doi": "10.48550/arXiv.2205.14135", "url": "https://arxiv.org/abs/2205.14135",
     "concepts": ["attention", "memory_efficiency", "kernels"]},
    {"source": "manual", "external_id": "arXiv:2001.08361", "title": "Scaling Laws for Neural Language Models",
     "authors": ["J. Kaplan", "S. McCandlish", "T. Henighan", "T. Brown", "et al."], "year": 2020, "venue": "arXiv",
     "doi": "10.48550/arXiv.2001.08361", "url": "https://arxiv.org/abs/2001.08361",
     "concepts": ["scaling", "compute_budgets"]},
]

ENTRIES: list[dict] = [
    {
        "title": "Linear attention as a (selective) recurrent network",
        "question": "Can transformer attention over context length L be re-expressed as a recurrent state update with state size d, so that inference cost becomes O(Ld) instead of O(L^2) while reproducing the same outputs within tolerance?",
        "source_paradigm": "transformers (quadratic attention)",
        "target_paradigm": "recurrent / state-space models",
        "research_field": "representation", "architecture": "transformer", "compression_technique": "architecture_simplification",
        "shared_structure": "Attention with linear scoring is equivalent to reading a growing sum of outer products — i.e. an RNN whose hidden state accumulates key-value information. Selective decay/state gating generalizes to SSM form.",
        "math_explanation": "softmax-free attention: out_t = sum_{s<=t} q_t k_s^T v_s = q_t · S_t with S_t = S_{t-1} + k_t v_t^T (recurrent form, O(d^2) per step). softmax attention cannot be reduced exactly without approximation, so transformed models must be validated behaviorally rather than assumed equivalent.",
        "evidence_quality": "established",
        "computational_benefit": "O(L^2 d) -> O(L d^2) inference; constant-memory streaming generation",
        "implementation_complexity": "high", "resource_estimate": "medium",
        "limitations": ["Softmax normalization is lost in exact linearization", "Autoregressive quality often degrades on long copying tasks", "Equivalence only under specific scoring assumptions"],
        "proposed_experiments": ["Distill a softmax transformer into a linear-attention student and measure task retention vs O(L) speedup", "Compare KV-cache memory growth curve vs SSD state memory across L"],
        "papers": ["Attention Is All You Need", "Mamba: Linear-Time Sequence Modeling with Selective State Spaces"],
    },
    {
        "title": "Low-rank updates and shared subspaces across modules",
        "question": "Do two neural modules trained on the same task develop low-rank weight subspaces that are redundant with each other, such that one shared factorized subspace preserves accuracy while reducing parameters?",
        "source_paradigm": "information theory / matrix approximation",
        "target_paradigm": "parameter sharing",
        "research_field": "compression", "architecture": "transformer", "compression_technique": "low_rank_factorization",
        "shared_structure": "A weight matrix ΔW of rank r embeds a rank-d shared subspace; several modules may reuse the same basis U with small private diagonal factors.",
        "math_explanation": "ΔW = B·A with A ∈ R^{r×n}, B ∈ R^{m×r}. Sharing basis across modules: A_i D_i B_i where D_i is per-module. Information-theoretic view: I(ΔW; task) concentrated in top singular directions (cf. bottleneck principle).",
        "evidence_quality": "replicated",
        "computational_benefit": "parameters mn -> r(m+n) per shared pair; FLOPs cut for large m,n",
        "implementation_complexity": "medium", "resource_estimate": "medium",
        "limitations": ["Sharing basis across modules can couple gradients harmfully", "Edge singular values may carry task-specific signal"],
        "proposed_experiments": ["SVD-shared two-tower experiment on the distillation demo", "Ablate shared vs private basis at matched parameter budget"],
        "papers": ["LoRA: Low-Rank Adaptation of Large Language Models", "Deep Learning and the Information Bottleneck Principle"],
    },
    {
        "title": "Distillation as mutual-information-preserving compression",
        "question": "Does distillation loss correspond to retaining the student-relevant bits of the teacher's output distribution, and can the required student capacity be predicted from output-distribution entropy rather than trial runs?",
        "source_paradigm": "knowledge distillation",
        "target_paradigm": "information theory",
        "research_field": "compression", "architecture": "any", "compression_technique": "distillation",
        "shared_structure": "Teacher soft targets compress class-conditional structure (dark knowledge). Capacity needed ≈ MI(class; teacher logits) rather than teacher parameter count.",
        "math_explanation": "KD loss: L = α T² KL(softmax(z_s/T) || softmax(z_t/T)) + (1-α) CE(y, z_s). Effective classes ≈ exp(H(softmax(z_t))) (perplexity of teacher outputs) predicts student width.",
        "evidence_quality": "literature_supported",
        "computational_benefit": "Chooses minimal student capacity before training; avoids over-parameterized student sweeps",
        "implementation_complexity": "low", "resource_estimate": "low",
        "limitations": ["Entropy estimates on few classes are noisy", "Distillation also transfers teacher errors"],
        "proposed_experiments": ["Relate teacher output entropy to student width on synthetic benchmark", "Test retention frontier at fixed α, sweeping T"],
        "papers": ["Distilling the Knowledge in a Neural Network", "Deep Learning and the Information Bottleneck Principle"],
    },
    {
        "title": "Retrieval as compressed external memory",
        "question": "At what point does a compressed parametric memory (quantized/shrunken model) become preferable to an uncompressed retrieval index over raw data, and how does the trade-off scale with corpus size?",
        "source_paradigm": "retrieval-augmented generation",
        "target_paradigm": "compressed memory / quantization",
        "research_field": "compression", "architecture": "transformer", "compression_technique": "activation_cache_optimization",
        "shared_structure": "Both store key-value traces of experience; kNN-LM mixes retrievals into next-token distribution, a cache quantization compresses them into weights.",
        "math_explanation": "p(y|x) = λ p_retrieval(y|x) + (1-λ) p_lm(y|x) (kNN-LM) vs p_q(y|x) from quantized weights: information moves from index (addressable, exact-ish) into weights (amortized, lossy).",
        "evidence_quality": "literature_supported",
        "computational_benefit": "Small model + tiny index may dominate huge parametric model at equal quality (Pareto analysis needed)",
        "implementation_complexity": "high", "resource_estimate": "high",
        "limitations": ["Retrieval needs the corpus at inference (storage + latency)", "Index and model formats are not interchangeable"],
        "proposed_experiments": ["Pareto plot: corpus size vs model size at fixed accuracy on synthetic lookup tasks", "Measure end-to-end latency including index access"],
        "papers": ["Generalization through Memorization: Nearest Neighbor Language Models", "Scaling Laws for Neural Language Models"],
    },
    {
        "title": "Pruning subnetworks as hypothesis selection",
        "question": "Do magnitude-surviving subnetworks identified without training (early-level heuristics) transfer across architectures sharing computational motifs, enabling pruning with one-tenth the search compute?",
        "source_paradigm": "pruning / sparsity",
        "target_paradigm": "architecture search / symbolic structure",
        "research_field": "compression", "architecture": "cnn", "compression_technique": "pruning_unstructured",
        "shared_structure": "Winner-take-all subsets of parameters as discrete hypotheses; graph motif matching to transfer masks.",
        "math_explanation": "Mask s ∈ {0,1}^n minimizes L(θ⊙s) under ‖s‖₀ ≤ k. Transfer: motifs matched subgraph-isomorphism between architectures.",
        "evidence_quality": "replicated",
        "computational_benefit": "Lower pruning search cost; interpretable surviving-structure reports",
        "implementation_complexity": "medium", "resource_estimate": "medium",
        "limitations": ["Lottery-ticket re-init is expensive", "Mask transfer fidelity varies by task family"],
        "proposed_experiments": ["Transfer masks across MLP widths on the synthetic benchmark", "Compare one-shot vs iterative magnitude pruning at fixed sparsity"],
        "papers": ["The Lottery Ticket Hypothesis: Finding Sparse, Trainable Neural Networks"],
    },
    {
        "title": "Quantization as rate-distortion allocation",
        "question": "Given an inference accuracy tolerance, what is the optimal bits-allocation across layers that minimizes total artifact size, possible to compute from weight statistics alone before any retraining?",
        "source_paradigm": "quantization",
        "target_paradigm": "information theory (rate-distortion)",
        "research_field": "compression", "architecture": "any", "compression_technique": "weight_quantization",
        "shared_structure": "Layers are sources with differing sensitivity (distortion curves); allocation is a knapsack over rate.",
        "math_explanation": "minimize Σ_mode R_m(b_m) subject to D(b) ≤ ε, with distortion sensitivities κ_m from curvature/fisher proxies.",
        "evidence_quality": "theoretical",
        "computational_benefit": "Skip retraining sweeps; explain quality loss from sensitivity",
        "implementation_complexity": "medium", "resource_estimate": "low",
        "limitations": ["Fisher estimates need data; zero-data variants are heuristic", "Per-device kernels constrain achievable bit-widths"],
        "proposed_experiments": ["Measure per-layer sensitivity on the quantization demo task", "Validate allocation-vs-uniform at matched size"],
        "papers": ["Deep Learning and the Information Bottleneck Principle", "Scaling Laws for Neural Language Models"],
    },
    {
        "title": "Diffusion as amortized symbolic dynamics",
        "question": "Can the deterministic denoising trajectory of a diffusion model be expressed as a shorter symbolic program (fewer learned parameters) when the target distribution has known low-dimensional manifold structure?",
        "source_paradigm": "diffusion / generative modeling",
        "target_paradigm": "program synthesis",
        "research_field": "representation", "architecture": "diffusion", "compression_technique": "architecture_simplification",
        "shared_structure": "Score function ∇log p_t as vector field; on low-dim manifolds it factors into geometric + dynamic parts, where the geometric part is program-expressible.",
        "math_explanation": "score s(x,t) = ∇_x log p_t(x); symbolic ansatz s = s_geom(x; c) + s_learn(x,t) with c discretized constants from data.",
        "evidence_quality": "theoretical",
        "computational_benefit": "Fewer sampling steps; smaller network for the learnable residual",
        "implementation_complexity": "high", "resource_estimate": "high",
        "limitations": ["Symbolic extraction fails on complex manifolds", "Provable compression bounds are open"],
        "proposed_experiments": ["Fit score fields on synthetic 2D manifolds and extract residuals", "Compare sample quality vs parameter count"],
        "papers": ["Denoising Diffusion Probabilistic Models", "KAN: Kolmogorov-Arnold Networks"],
    },
    {
        "title": "Graph message passing as belief propagation",
        "question": "When do GNN message-passing rounds reproduce mean-field BP on the factor graph, enabling compression by pruning redundant propagation rounds at matched accuracy?",
        "source_paradigm": "graph neural networks",
        "target_paradigm": "probabilistic graphical models",
        "research_field": "representation", "architecture": "gnn", "compression_technique": "architecture_simplification",
        "shared_structure": "Message m_{i→j} updates identical modulo nonlinearity choice; calibration conditions overlap.",
        "math_explanation": "BP: m^{t+1}_{i→j}(x_j) ∝ Σ_{x_i} φ_i(x_i) ψ_{ij}(x_i,x_j) Π_{k≠j} m^t_{k→i}(x_i); GNN similar with learned ψ and normalization.",
        "evidence_quality": "theoretical",
        "computational_benefit": "Fewer rounds = fewer FLOPs; explains over-smoothing failures via BP convergence",
        "implementation_complexity": "high", "resource_estimate": "medium",
        "limitations": ["Equivalence requires specific activation/normalization families", "Loopy BP non-convergence carries over"],
        "proposed_experiments": ["Replay judge equivalence on small factor graphs", "Ablate rounds vs accuracy at fixed parameter budget"],
        "papers": ["Attention Is All You Need"],
    },
    {
        "title": "Sparse mixture routing as symbolic branch selection",
        "question": "Can router gate decisions in a small MoE be replaced by a symbolic rule extracted offline, preserving accuracy on the routing distribution while eliminating the gating network at inference?",
        "source_paradigm": "mixture-of-experts / gating",
        "target_paradigm": "program synthesis / decision trees",
        "research_field": "compression", "architecture": "transformer", "compression_technique": "architecture_simplification",
        "shared_structure": "Routing policy as decision tree over input statistics; gates are discrete functions amenable to symbolic distillation.",
        "math_explanation": "g(x) = argmax_k gate_k(x) → decision tree τ with accuracy_acc(g→τ) on held routing data; accept if agreement ≥ 1-δ.",
        "evidence_quality": "theoretical",
        "computational_benefit": "Remove gating compute and memory; interpretable, auditable routes",
        "implementation_complexity": "medium", "resource_estimate": "low",
        "limitations": ["Distribution shift breaks extracted rules", "Accuracy of rule bounded by gate quality"],
        "proposed_experiments": ["Extract tree from the distillation demo's gates", "Evaluate agreement + end-task accuracy drop δ"],
        "papers": ["KAN: Kolmogorov-Arnold Networks", "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness"],
    },
    {
        "title": "KV-cache compression vs SSM state compression",
        "question": "Is there a task-independent equivalence between KV-cache quantization/eviction budgets in transformers and fixed state sizes in selective SSMs, expressible as a memory-quality frontier per sequence length?",
        "source_paradigm": "transformers (KV cache)",
        "target_paradigm": "state-space models (SSM)",
        "research_field": "compression", "architecture": "transformer", "compression_technique": "activation_cache_optimization",
        "shared_structure": "Both maintain a fixed-size summary of history; trade quality vs summary bytes.",
        "math_explanation": "cache budget b bytes ↔ SSM state size s: both approximate retrieval from O(L) history with O(b/s) state; frontier M(L, b) mapping quality.",
        "evidence_quality": "theoretical",
        "computational_benefit": "Memory-bounded long-context serving planning",
        "implementation_complexity": "high", "resource_estimate": "high",
        "limitations": ["Retrieval fidelity differs fundamentally (exact keys vs lossy state)", "Needs matched-quality protocol"],
        "proposed_experiments": ["Frontier sweep on synthetic long-copy tasks", "Measure peak memory scaling with L at matched quality"],
        "papers": ["Mamba: Linear-Time Sequence Modeling with Selective State Spaces", "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness"],
    },
]


def seed_db(db: Session) -> None:
    """Idempotent seed. Runs on API startup and via `python -m app.seed`."""
    admin = db.query(User).filter_by(email=settings.admin_email).one_or_none()
    if admin is None:
        admin = User(
            email=settings.admin_email,
            hashed_password=hash_password(settings.admin_password),
            display_name="Lab Admin",
            is_admin=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

    ws = db.query(Workspace).filter_by(slug="main").one_or_none()
    if ws is None:
        ws = Workspace(name="Main Workspace", slug="main")
        db.add(ws)
        db.commit()
        db.refresh(ws)
    if not db.query(WorkspaceMember).filter_by(workspace_id=ws.id, user_id=admin.id).one_or_none():
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=admin.id, role="owner"))
        db.commit()

    if db.query(CompressionMethod).count() == 0:
        for m in METHODS:
            db.add(CompressionMethod(**m))
        db.commit()
    else:
        # Idempotent additions: registry entries added in later milestones
        # must appear on pre-existing installations too (keyed upsert, no churn).
        existing_keys = {k for (k,) in db.query(CompressionMethod.key).all()}
        for m in METHODS:
            if m["key"] not in existing_keys:
                db.add(CompressionMethod(**m))
        db.commit()

    if db.query(ComputeResource).filter_by(workspace_id=ws.id, name="local-cpu").one_or_none() is None:
        import os
        cpu_count = os.cpu_count() or 1
        db.add(
            ComputeResource(
                workspace_id=ws.id, name="local-cpu", kind="cpu", status="online",
                limits={"max_cpu_threads": max(1, cpu_count - 1), "max_ram_mb": 2048, "gpu": False},
                utilization={"threads_in_use": 0},
            )
        )
        db.commit()

    if db.query(ResearchEntry).count() == 0:
        paper_by_title: dict[str, Paper] = {}
        for p in PAPERS:
            paper = Paper(workspace_id=ws.id, **p)
            db.add(paper)
            db.flush()
            paper_by_title[p["title"]] = paper
        for e in ENTRIES:
            refs = e.pop("papers", [])
            entry = ResearchEntry(workspace_id=ws.id, provenance="curated", **e)
            db.add(entry)
            db.flush()
            for r in refs:
                paper = paper_by_title.get(r)
                if paper:
                    db.add(SourceRef(workspace_id=ws.id, subject_type="research_entry",
                                     subject_id=entry.id, paper_id=paper.id, relation="supports"))
        db.commit()

    if db.query(ResearchProject).filter_by(workspace_id=ws.id).count() == 0:
        db.add(
            ResearchProject(
                workspace_id=ws.id,
                name="Cross-Paradigm Compression — kickoff project",
                description=("Investigate shared structure between paradigms and validate compression "
                              "transformations with measured, reproducible experiments."),
                research_fields=["compression", "representation", "distillation", "quantization"],
                created_by=admin.id,
            )
        )
        db.commit()
