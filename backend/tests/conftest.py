import numpy as np
import pytest

from corridor.engine.calibration import CorridorLines, solve_corridor_lines
from corridor.engine.vectorizer import MetricScales, fit_scales, vectorize
from corridor.synthetic.generator import SyntheticDataset, generate


@pytest.fixture(scope="session")
def dataset() -> SyntheticDataset:
    return generate(seed=42)


@pytest.fixture(scope="session")
def scales(dataset: SyntheticDataset) -> MetricScales:
    return fit_scales(dataset.raw_matrix())


@pytest.fixture(scope="session")
def vectors(dataset: SyntheticDataset, scales: MetricScales) -> np.ndarray:
    return vectorize(dataset.raw_matrix(), scales)


@pytest.fixture(scope="session")
def lines(dataset: SyntheticDataset, vectors: np.ndarray) -> CorridorLines:
    return solve_corridor_lines(vectors, dataset.raw_matrix(), dataset.npxgd(), dataset.results())
