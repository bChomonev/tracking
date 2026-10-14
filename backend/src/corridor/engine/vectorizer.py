"""Weighted, direction-aligned, clipped Z-score vectorization → ``halfvec(12)``."""

from dataclasses import dataclass

import numpy as np

from corridor.engine.metrics import DIRECTIONS, METRIC_KEYS, N_DIMS, WEIGHTS, Z_CLIP

_DIR = np.asarray(DIRECTIONS, dtype=np.float64)
_W = np.asarray(WEIGHTS, dtype=np.float64)


@dataclass(frozen=True)
class MetricScales:
    """Per-metric mean/std of the benchmark window, in ``METRIC_KEYS`` order."""

    means: np.ndarray
    stds: np.ndarray

    def to_dicts(self) -> tuple[dict[str, float], dict[str, float]]:
        return (
            {k: float(v) for k, v in zip(METRIC_KEYS, self.means, strict=True)},
            {k: float(v) for k, v in zip(METRIC_KEYS, self.stds, strict=True)},
        )

    @classmethod
    def from_dicts(cls, means: dict[str, float], stds: dict[str, float]) -> "MetricScales":
        return cls(
            means=np.asarray([means[k] for k in METRIC_KEYS], dtype=np.float64),
            stds=np.asarray([stds[k] for k in METRIC_KEYS], dtype=np.float64),
        )


def fit_scales(raw: np.ndarray) -> MetricScales:
    """Fit mean/std per metric over an ``(n, 12)`` matrix. NaNs (missing data) are ignored."""
    raw = np.asarray(raw, dtype=np.float64)
    if raw.ndim != 2 or raw.shape[1] != N_DIMS:
        raise ValueError(f"expected (n, {N_DIMS}) matrix, got {raw.shape}")
    means = np.nanmean(raw, axis=0)
    stds = np.nanstd(raw, axis=0, ddof=1)
    if np.any(~np.isfinite(stds)) or np.any(stds <= 0):
        bad = [k for k, s in zip(METRIC_KEYS, stds, strict=True) if not np.isfinite(s) or s <= 0]
        raise ValueError(f"degenerate std for metrics: {bad}")
    return MetricScales(means=means, stds=stds)


def vectorize(raw: np.ndarray, scales: MetricScales) -> np.ndarray:
    """Map raw rate metrics to weighted Z-score vectors (float16).

    Accepts a single ``(12,)`` row or an ``(n, 12)`` matrix. Missing metrics (NaN) are
    imputed as the benchmark mean (z = 0) so they neither help nor hurt similarity.
    """
    raw = np.asarray(raw, dtype=np.float64)
    z = (raw - scales.means) / scales.stds
    z = np.nan_to_num(z, nan=0.0)
    z = np.clip(_DIR * _W * z, -Z_CLIP, Z_CLIP)
    return z.astype(np.float16)
