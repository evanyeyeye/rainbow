"""
Unit tests for the shared (key, value) -> (time x ylabel) binning helper that
replaced the per-scan np.unique / searchsorted / np.add.at loops in the Waters
and Agilent spectrum decoders.
"""
import numpy as np
import pytest

from rainbow._binning import bin_datapairs


def _bin_datapairs_reference(keys, values, pair_counts, prec, data_dtype):
    """Original (pre-optimization) binning, kept as a parity oracle.

    Mirrors the per-scan np.unique / searchsorted / np.add.at loop that the
    Waters _FUNC.DAT and Agilent .ms decoders both used before bin_datapairs.
    """
    keys = np.round(keys, prec)
    num_times = pair_counts.size
    ylabels = np.unique(keys)
    ylabels.sort()
    key_indices = np.searchsorted(ylabels, keys)
    data = np.zeros((num_times, ylabels.size), dtype=data_dtype)
    cur = 0
    for i in range(num_times):
        stop = cur + int(pair_counts[i])
        np.add.at(data[i], key_indices[cur:stop], values[cur:stop])
        cur = stop
    return ylabels, data


def test_sums_within_scan_and_sorts_ylabels():
    # scan 0: m/z 102 twice (5+7) and 100 (3); scan 1: 101 (9) and 100 (4).
    keys = np.array([102., 100., 102., 101., 100.])
    values = np.array([5, 3, 7, 9, 4], dtype=np.int64)
    pair_counts = np.array([3, 2])
    ylabels, data = bin_datapairs(keys, values, pair_counts, 0)
    np.testing.assert_array_equal(ylabels, [100., 101., 102.])
    np.testing.assert_array_equal(data, [[3, 0, 12], [4, 9, 0]])


def test_preserves_key_dtype():
    # Calibrated Waters m/z are float32; the ylabels must stay float32.
    keys = np.array([200.4, 200.4, 350.7], dtype=np.float32)
    values = np.array([1, 2, 3], dtype=np.int64)
    ylabels, _ = bin_datapairs(keys, values, np.array([3]), 0)
    assert ylabels.dtype == np.float32


def test_honors_output_dtype():
    # Agilent .ms accumulates intensities into uint32.
    keys = np.array([100., 100., 200.])
    values = np.array([1, 2, 3], dtype=np.uint32)
    _, data = bin_datapairs(keys, values, np.array([3]), 0, data_dtype=np.uint32)
    assert data.dtype == np.uint32
    np.testing.assert_array_equal(data, [[3, 3]])


def test_respects_precision():
    # Keys arrive already rounded to `prec` (the decoders round first).
    keys = np.round(np.array([100.14, 100.16, 100.16]), 1)
    values = np.array([1, 2, 4], dtype=np.int64)
    ylabels, data = bin_datapairs(keys, values, np.array([3]), 1)
    np.testing.assert_array_equal(ylabels, [100.1, 100.2])
    np.testing.assert_array_equal(data, [[1, 6]])


def test_empty_input():
    ylabels, data = bin_datapairs(
        np.array([], dtype=np.float64), np.array([], dtype=np.int64),
        np.array([0, 0]), 0)
    assert ylabels.size == 0
    assert data.shape == (2, 0)


@pytest.mark.parametrize("data_dtype", [np.int64, np.uint32])
@pytest.mark.parametrize("prec", [0, 1, 2])
def test_matches_reference_on_random_data(data_dtype, prec):
    rng = np.random.RandomState(0)
    for _ in range(20):
        num_times = rng.randint(1, 8)
        pair_counts = rng.randint(0, 12, size=num_times)
        n = int(pair_counts.sum())
        if n == 0:
            continue
        keys = (rng.rand(n) * 900 + 100).astype(np.float32)
        values = rng.randint(0, 5000, size=n).astype(data_dtype)
        y_ref, d_ref = _bin_datapairs_reference(
            keys.copy(), values.copy(), pair_counts, prec, data_dtype)
        y, d = bin_datapairs(
            np.round(keys, prec), values, pair_counts, prec,
            data_dtype=data_dtype)
        np.testing.assert_array_equal(y, y_ref)
        np.testing.assert_array_equal(d, d_ref)
        assert d.dtype == d_ref.dtype
