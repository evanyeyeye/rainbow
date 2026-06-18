import unittest

import numpy as np

import tests.datatester
from rainbow.waters import masslynx


def _bin_datapairs_reference(keys, values, pair_counts, prec):
    """Original (pre-optimization) binning, kept as a parity oracle."""
    keys = np.round(keys, prec)
    num_times = pair_counts.size
    ylabels = np.unique(keys)
    ylabels.sort()
    key_indices = np.searchsorted(ylabels, keys)
    data = np.zeros((num_times, ylabels.size), dtype=np.int64)
    cur = 0
    for i in range(num_times):
        stop = cur + pair_counts[i]
        np.add.at(data[i], key_indices[cur:stop], values[cur:stop])
        cur = stop
    return ylabels, data


class TestWatersBinning(unittest.TestCase):
    """
    Unit tests for the vectorized (key, value) binning helper that replaced
    the per-scan np.unique / searchsorted / np.add.at loop in the Waters
    _FUNC .DAT decoders.

    """
    def test_sums_within_scan_and_sorts_ylabels(self):
        # scan 0: m/z 102 twice (5+7) and 100 (3); scan 1: 101 (9) and 100 (4).
        keys = np.array([102., 100., 102., 101., 100.])
        values = np.array([5, 3, 7, 9, 4], dtype=np.int64)
        pair_counts = np.array([3, 2])
        ylabels, data = masslynx._bin_datapairs(keys, values, pair_counts, 0)
        np.testing.assert_array_equal(ylabels, [100., 101., 102.])
        np.testing.assert_array_equal(data, [[3, 0, 12], [4, 9, 0]])

    def test_preserves_key_dtype(self):
        # Calibrated Waters m/z are float32; the ylabels must stay float32.
        keys = np.array([200.4, 200.4, 350.7], dtype=np.float32)
        values = np.array([1, 2, 3], dtype=np.int64)
        ylabels, _ = masslynx._bin_datapairs(keys, values, np.array([3]), 0)
        self.assertEqual(ylabels.dtype, np.float32)

    def test_respects_precision(self):
        # Keys arrive already rounded to `prec` (the decoders round first).
        keys = np.round(np.array([100.14, 100.16, 100.16]), 1)
        values = np.array([1, 2, 4], dtype=np.int64)
        ylabels, data = masslynx._bin_datapairs(keys, values, np.array([3]), 1)
        np.testing.assert_array_equal(ylabels, [100.1, 100.2])
        np.testing.assert_array_equal(data, [[1, 6]])

    def test_matches_reference_on_random_data(self):
        rng = np.random.RandomState(0)
        for prec in (0, 1, 2):
            for _ in range(25):
                num_times = rng.randint(1, 8)
                pair_counts = rng.randint(0, 12, size=num_times)
                n = int(pair_counts.sum())
                if n == 0:
                    continue
                keys = (rng.rand(n) * 900 + 100).astype(np.float32)
                values = rng.randint(-5, 5000, size=n).astype(np.int64)
                y_ref, d_ref = _bin_datapairs_reference(
                    keys.copy(), values.copy(), pair_counts, prec)
                y, d = masslynx._bin_datapairs(
                    np.round(keys, prec), values, pair_counts, prec)
                np.testing.assert_array_equal(y, y_ref)
                np.testing.assert_array_equal(d, d_ref)


class TestWaters(tests.datatester.DataTester):
    """
    Unit tests for parsing Waters .raw directories. 

    """
    def test_blue(self):
        """
        Tests a directory containing:
            - UV spectrum 
            - MS spectrum (8-byte format)
            - CAD channel
        
        """
        self._DataTester__test_data_directory("blue", "raw")

    def test_indigo(self):
        """
        Tests a directory containing:
            - MS trace (2-byte format)
            - 2 analog channels
        
        """
        self._DataTester__test_data_directory("indigo", "raw")

    def test_violet(self):
        """
        Tests a directory containing:
            - UV spectrum 
            - 3 UV channels (analog)
            - 2 MS spectra (6-byte format)
            - ELSD channel

        """
        self._DataTester__test_data_directory("violet", "raw")

    def test_white(self):
        """
        Tests a directory containing:
            - 6 UV spectrum (4-byte format)
            - 2 analog channels

        """
        self._DataTester__test_data_directory("white", "raw")

    def test_turquoise(self):
        """
        Tests a Perkin-Elmer / TurboMass .raw export with
        lowercase filenames and PE _extern.inf polarity format.

        """
        self._DataTester__test_data_directory("turquoise", "raw")

if __name__ == '__main__':
    unittest.main()