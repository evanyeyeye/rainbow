"""
Unit tests for the shared (key, value) -> (time x ylabel) binning helper that
replaced the per-scan np.unique / searchsorted / np.add.at loops in the Waters
and Agilent spectrum decoders.

bin_datapairs now bins by ``bin_width`` (the lossy control) and labels the bins
at ``display_precision`` (cosmetic). Binning by ``bin_width`` is equivalent to
the old "round to N decimals then sum" with ``bin_width = 10**-N``.
"""
import numpy as np
import pytest

from rainbow._binning import bin_datapairs


def _bin_datapairs_reference(keys, values, pair_counts, precision, data_dtype):
    """Original (pre-optimization) binning, kept as a parity oracle.

    Mirrors the per-scan np.unique / searchsorted / np.add.at loop that the
    Waters _FUNC.DAT and Agilent .ms decoders both used, binning by rounding to
    ``prec`` decimals.
    """
    keys = np.round(keys, precision)
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
    ylabels, data = bin_datapairs(keys, values, pair_counts, 1.0,
                                  display_precision=0)
    np.testing.assert_array_equal(ylabels, [100., 101., 102.])
    np.testing.assert_array_equal(data, [[3, 0, 12], [4, 9, 0]])


def test_labels_are_bin_centres():
    # Raw keys near 200.4 and 350.7 fall in the 200 and 351 nominal-mass bins.
    keys = np.array([200.4, 200.4, 350.7])
    values = np.array([1, 2, 3], dtype=np.int64)
    ylabels, data = bin_datapairs(keys, values, np.array([3]), 1.0,
                                  display_precision=0)
    np.testing.assert_array_equal(ylabels, [200., 351.])
    np.testing.assert_array_equal(data, [[3, 3]])


def test_honors_output_dtype():
    # Agilent .ms accumulates intensities into uint32.
    keys = np.array([100., 100., 200.])
    values = np.array([1, 2, 3], dtype=np.uint32)
    _, data = bin_datapairs(keys, values, np.array([3]), 1.0,
                            display_precision=0, data_dtype=np.uint32)
    assert data.dtype == np.uint32
    np.testing.assert_array_equal(data, [[3, 3]])


def test_bin_width_finer_than_nominal():
    # A 0.1 Da bin_width keeps the 100.1 and 100.2 bins distinct; labels show
    # one decimal.
    keys = np.array([100.14, 100.16, 100.16])
    values = np.array([1, 2, 4], dtype=np.int64)
    ylabels, data = bin_datapairs(keys, values, np.array([3]), 0.1,
                                  display_precision=1)
    np.testing.assert_array_equal(ylabels, [100.1, 100.2])
    np.testing.assert_array_equal(data, [[1, 6]])


def test_empty_input():
    ylabels, data = bin_datapairs(
        np.array([], dtype=np.float64), np.array([], dtype=np.int64),
        np.array([0, 0]), 1.0, display_precision=0)
    assert ylabels.size == 0
    assert data.shape == (2, 0)


@pytest.mark.parametrize("data_dtype", [np.int64, np.uint32])
@pytest.mark.parametrize("prec", [0, 1, 2])
def test_matches_reference_on_random_data(data_dtype, prec):
    # Binning by bin_width = 10**-prec reproduces the old round-to-prec binning.
    rng = np.random.RandomState(0)
    for _ in range(20):
        num_times = rng.randint(1, 8)
        pair_counts = rng.randint(0, 12, size=num_times)
        n = int(pair_counts.sum())
        if n == 0:
            continue
        keys = (rng.rand(n) * 900 + 100).astype(np.float64)
        values = rng.randint(0, 5000, size=n).astype(data_dtype)
        y_ref, d_ref = _bin_datapairs_reference(
            keys.copy(), values.copy(), pair_counts, prec, data_dtype)
        y, d = bin_datapairs(
            keys.copy(), values, pair_counts, 10.0 ** -prec,
            display_precision=prec, data_dtype=data_dtype)
        np.testing.assert_allclose(y, y_ref)
        np.testing.assert_array_equal(d, d_ref)
        assert d.dtype == d_ref.dtype


def test_no_floor_warning_for_tof_centroids():
    """ A calibrated TOF centroid resolves far below the quadrupole floor. """
    import warnings
    import rainbow as rb
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        rb.read("tests/inputs/gold.D", centroid=True, bin_width=0.01)
    assert not [w for w in caught if "finer than" in str(w.message)]


def test_unit_resolution_data_still_warns():
    """ The floor still applies where it is true: quadrupole .ms is 0.1 Da. """
    import warnings
    import rainbow as rb
    with pytest.warns(UserWarning, match="finer than"):
        rb.read("tests/inputs/orange.D", bin_width=0.001)
