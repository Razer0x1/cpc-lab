"""Minimal, dependency-light NumPy MLP engine used by CPU-friendly demonstration tasks.

This is real computation (deterministic, seeded), not a simulation. When PyTorch is
installed and enabled, tasks may use the torch engine instead (see requirements-gpu.txt);
results record which engine produced them.
"""
from __future__ import annotations

import io
import time
import tracemalloc
from dataclasses import dataclass

import numpy as np

ACTIVATIONS = {"relu": lambda x: np.maximum(x, 0.0), "tanh": np.tanh}


@dataclass
class MLP:
    """Fully-connected classifier with ReLU hidden layers and a linear head."""

    sizes: list[int]  # e.g. [2, 64, 64, 3]
    activation: str = "relu"
    seed: int = 0

    def __post_init__(self) -> None:
        rng = np.random.default_rng(self.seed)
        self.W: list[np.ndarray] = []
        self.b: list[np.ndarray] = []
        for i, (a, b) in enumerate(zip(self.sizes[:-1], self.sizes[1:])):
            # He initialization for relu, Xavier for tanh
            scale = np.sqrt(2.0 / a) if self.activation == "relu" else np.sqrt(1.0 / a)
            self.W.append((rng.standard_normal((a, b)) * scale).astype(np.float32))
            self.b.append(np.zeros(b, dtype=np.float32))
        self.act = ACTIVATIONS[self.activation]

    @property
    def param_count(self) -> int:
        return int(sum(w.size for w in self.W) + sum(b.size for b in self.b))

    def forward_logits(self, X: np.ndarray) -> np.ndarray:
        h = X
        for i in range(len(self.W) - 1):
            h = self.act(h @ self.W[i] + self.b[i])
        return h @ self.W[-1] + self.b[-1]

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.argmax(self.forward_logits(X), axis=1)

    def loss_and_grads(self, X: np.ndarray, y_onehot: np.ndarray, weights: dict | None = None):
        """Softmax cross-entropy (+ optional KD soft-target term). Returns (loss, grads)."""
        n = X.shape[0]
        acts = [X]
        h = X
        for i in range(len(self.W) - 1):
            h = self.act(h @ self.W[i] + self.b[i])
            acts.append(h)
        logits = h @ self.W[-1] + self.b[-1]

        weights = weights or {"ce": 1.0}
        ce_w = weights.get("ce", 1.0)
        kd_w = weights.get("kd", 0.0)
        T = weights.get("kd_temperature", 1.0)

        if kd_w > 0 and weights.get("teacher_logits") is not None:
            t_logits = weights["teacher_logits"]
            p_soft = _softmax(logits / T)
            q_soft = _softmax(t_logits / T)
            kd_loss = _soft_ce(p_soft, q_soft) * (T * T)
            dlogits_kd = (p_soft - q_soft) / n * (T * T)
        else:
            kd_loss = 0.0
            dlogits_kd = 0.0

        if ce_w > 0:
            p = _softmax(logits)
            ce_loss = _soft_ce(p, y_onehot)
            dlogits_ce = (p - y_onehot) / n
        else:
            ce_loss = 0.0
            dlogits_ce = 0.0

        loss = ce_w * ce_loss + kd_w * kd_loss
        dlogits = ce_w * dlogits_ce + kd_w * dlogits_kd

        grads_W: list[np.ndarray] = [np.zeros_like(w) for w in self.W]
        grads_b: list[np.ndarray] = [np.zeros_like(b) for b in self.b]
        delta = dlogits
        for i in reversed(range(len(self.W))):
            grads_W[i] = acts[i].T @ delta
            grads_b[i] = delta.sum(axis=0)
            if i > 0:
                delta = (delta @ self.W[i].T) * (acts[i] > 0)
        return float(loss), grads_W, grads_b

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        epochs: int,
        lr: float = 0.05,
        batch_size: int = 128,
        teacher: "MLP | None" = None,
        kd_alpha: float = 0.0,
        kd_temperature: float = 2.0,
        seed: int = 0,
        log_every: int = 0,
        log_fn=None,
    ) -> list[float]:
        rng = np.random.default_rng(seed)
        n = X.shape[0]
        num_classes = self.sizes[-1]
        y_onehot = np.eye(num_classes, dtype=np.float32)[y]
        # Adam
        mW = [np.zeros_like(w) for w in self.W]
        vW = [np.zeros_like(w) for w in self.W]
        mb = [np.zeros_like(b) for b in self.b]
        b1, b2, eps = 0.9, 0.999, 1e-8
        t = 0
        losses: list[float] = []
        for epoch in range(epochs):
            order = rng.permutation(n)
            epoch_loss = 0.0
            for start in range(0, n, batch_size):
                idx = order[start : start + batch_size]
                xb, yb = X[idx], y_onehot[idx]
                weights = {"ce": 1.0 - kd_alpha}
                if teacher is not None and kd_alpha > 0:
                    weights["kd"] = kd_alpha
                    weights["kd_temperature"] = kd_temperature
                    weights["teacher_logits"] = teacher.forward_logits(xb)
                loss, gW, gb = self.loss_and_grads(xb, yb, weights)
                epoch_loss += loss * len(idx)
                t += 1
                for i in range(len(self.W)):
                    mW[i] = b1 * mW[i] + (1 - b1) * gW[i]
                    vW[i] = b2 * vW[i] + (1 - b2) * (gW[i] ** 2)
                    mb[i] = b1 * mb[i] + (1 - b1) * gb[i]
                    self.W[i] -= lr * (mW[i] / (1 - b1 ** t)) / (np.sqrt(vW[i] / (1 - b2 ** t)) + eps)
                    self.b[i] -= lr * (mb[i] / (1 - b1 ** t)) / (np.sqrt((mb[i] * mb[i]) / (1 - b2 ** t)) + eps)
            losses.append(epoch_loss / n)
            if log_every and log_fn and (epoch % log_every == 0 or epoch == epochs - 1):
                log_fn(f"epoch {epoch + 1}/{epochs} loss={losses[-1]:.4f}")
        return losses

    def save_npz(self) -> bytes:
        import io

        buf = io.BytesIO()
        arrays: dict[str, np.ndarray] = {}
        for i, (w, b) in enumerate(zip(self.W, self.b)):
            arrays[f"W{i}"] = w
            arrays[f"b{i}"] = b
        np.savez_compressed(buf, **arrays)
        return buf.getvalue()

    @classmethod
    def load_npz(cls, data: bytes, activation: str = "relu") -> "MLP":
        buf = io.BytesIO(data)
        z = np.load(buf)
        if "qW0" in z.files:
            # Quantized artifact schema (see quantization.py): qW{i} = int codes,
            # sW{i} = per-layer fp32 scale, b{i} = fp32 biases. Dequantize with the
            # same math as the quantized forward pass so stored artifacts stay evaluable.
            keys = sorted({k[2:] for k in z.files if k.startswith("qW")}, key=int)
            sizes = [z[f"qW0"].shape[0]] + [z[f"qW{i}"].shape[1] for i in range(len(keys))]
            net = cls(sizes=sizes, activation=activation, seed=0)
            for i in range(len(keys)):
                scale = float(z[f"sW{i}"][0]) if f"sW{i}" in z.files else 1.0
                net.W[i] = z[f"qW{i}"].astype(np.float32) * np.float32(scale)
                net.b[i] = z[f"b{i}"].astype(np.float32)
            return net
        keys = sorted({k[1:] for k in z.files if k.startswith("W")}, key=int)
        sizes = [z[f"W0"].shape[0]] + [z[f"W{i}"].shape[1] for i in range(len(keys))]
        net = cls(sizes=sizes, activation=activation, seed=0)
        for i in range(len(keys)):
            net.W[i] = z[f"W{i}"].astype(np.float32)
            net.b[i] = z[f"b{i}"].astype(np.float32)
        return net


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _soft_ce(p: np.ndarray, target: np.ndarray) -> float:
    return float(-(target * np.log(np.clip(p, 1e-12, None))).sum(axis=1).mean())


def cross_entropy(net: MLP, X: np.ndarray, y: np.ndarray) -> float:
    logits = net.forward_logits(X)
    onehot = np.eye(net.sizes[-1], dtype=np.float32)[y]
    return _soft_ce(_softmax(logits), onehot)


def accuracy(net: MLP, X: np.ndarray, y: np.ndarray) -> float:
    return float((net.predict(X) == y).mean())


def make_spiral3(n_per_class: int, seed: int, noise: float = 0.22, classes: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic 3-class 2D spiral classification benchmark (synthetic, documented)."""
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for c in range(classes):
        t = np.linspace(0.35, 1.05, n_per_class) * 3.6 + c * (2 * np.pi / classes)
        r = np.linspace(0.05, 1.0, n_per_class)
        x = r * np.sin(t + c * 2 * np.pi / classes) + rng.normal(0, noise, n_per_class)
        yy = r * np.cos(t + c * 2 * np.pi / classes) + rng.normal(0, noise, n_per_class)
        xs.append(np.stack([x, yy], axis=1))
        ys.append(np.full(n_per_class, c))
    X = np.concatenate(xs).astype(np.float32)
    y = np.concatenate(ys).astype(np.int64)
    perm = rng.permutation(X.shape[0])
    return X[perm], y[perm]


def measure_latency(net: MLP, X: np.ndarray, *, warmup: int = 5, repeats: int = 30) -> dict:
    """Warm/cold latency and throughput on a fixed batch. Measured on the host CPU."""
    batch = X[: min(256, X.shape[0])]
    # cold: first-ever forward pass in a fresh tracemalloc-clean state
    cold_t0 = time.perf_counter()
    net.forward_logits(batch.copy())
    cold_ms = (time.perf_counter() - cold_t0) * 1000
    for _ in range(warmup):
        net.forward_logits(batch)
    t0 = time.perf_counter()
    for _ in range(repeats):
        net.forward_logits(batch)
    warm_ms = (time.perf_counter() - t0) * 1000 / repeats
    return {
        "latency_warm_ms": warm_ms,
        "latency_cold_ms": cold_ms,
        "throughput_rows_per_s": batch.shape[0] / (warm_ms / 1000),
        "batch_rows": int(batch.shape[0]),
    }


def measure_peak_memory_train(fn, *args, **kwargs) -> tuple[float, any]:
    """Run fn and return (peak_mb, fn result) using tracemalloc (process-local, documented)."""
    tracemalloc.start()
    out = fn(*args, **kwargs)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / (1024 * 1024), out
