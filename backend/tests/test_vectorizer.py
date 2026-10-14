import numpy as np
import pytest

from corridor.engine.metrics import METRIC_KEYS, N_DIMS, STACK_DIMS, TEAM_METRICS, Z_CLIP
from corridor.engine.vectorizer import MetricScales, fit_scales, vectorize

UNIT = MetricScales(means=np.zeros(N_DIMS), stds=np.ones(N_DIMS))


def test_metric_layout():
    assert N_DIMS == 12
    assert sorted(i for dims in STACK_DIMS.values() for i in dims) == list(range(12))
    assert all(len(dims) == 3 for dims in STACK_DIMS.values())


def test_positive_z_always_means_better():
    row = np.ones(N_DIMS)  # +1 sd on every raw metric
    v = vectorize(row, UNIT).astype(float)
    for m, z in zip(TEAM_METRICS, v, strict=True):
        assert np.sign(z) == m.direction, m.key
        assert z == pytest.approx(m.direction * m.weight, abs=1e-2)


def test_clip_and_dtype():
    v = vectorize(np.full(N_DIMS, 50.0), UNIT)
    assert v.dtype == np.float16
    assert np.all(np.abs(v.astype(float)) <= Z_CLIP)


def test_missing_metrics_impute_to_mean():
    row = np.ones(N_DIMS)
    row[0] = np.nan
    assert vectorize(row, UNIT)[0] == 0.0


def test_fit_scales_ignores_nan_and_rejects_degenerate():
    rng = np.random.default_rng(42)
    raw = rng.normal(5, 2, (500, N_DIMS))
    raw[:100, 0] = np.nan
    s = fit_scales(raw)
    assert s.means[0] == pytest.approx(5, abs=0.3)
    raw[:, 3] = 1.0
    with pytest.raises(ValueError, match=METRIC_KEYS[3]):
        fit_scales(raw)


def test_scales_dict_roundtrip(scales):
    means, stds = scales.to_dicts()
    back = MetricScales.from_dicts(means, stds)
    np.testing.assert_array_equal(back.means, scales.means)
