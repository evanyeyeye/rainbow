"""
Shared helper for binning (key, value) data pairs into a spectrum matrix.

Several vendor parsers store a scan's spectrum as a flat list of
``(ylabel, value)`` pairs - Waters ``_FUNC.DAT`` (m/z or wavelength) and
Agilent ``.ms`` (m/z) - and need to lay those pairs out as a
``(retention time x ylabel)`` matrix, summing pairs that share a ylabel within
a scan. This module provides one vectorized implementation of that step.
"""

import numpy as np


def bin_datapairs(keys, values, pair_counts, prec, data_dtype=np.int64):
    """
    Bins (key, value) data pairs into a (retention time x ylabel) matrix.

    Each scan (retention time) contributes ``pair_counts[i]`` consecutive pairs
    from the flat :obj:`keys`/:obj:`values` arrays. Pairs that share a ylabel
    within the same scan are summed.

    The keys must already be rounded to :obj:`prec` decimals and be
    non-negative (m/z or wavelength), so the unique ylabels and each pair's
    column are found with an integer histogram in O(n) instead of sorting every
    pair with ``np.unique``/``np.searchsorted``. The values are accumulated into
    a ``data_dtype`` matrix (matching whatever dtype - and overflow/truncation
    behavior - the caller's prior per-scan ``np.add.at`` loop used).

    Args:
        keys (np.ndarray): Flat ylabels, rounded to :obj:`prec`, non-negative.
        values (np.ndarray): Flat values paired with :obj:`keys`.
        pair_counts (np.ndarray): Number of pairs at each retention time.
        prec (int): Number of decimals the keys were rounded to.
        data_dtype (np.dtype, optional): dtype of the output matrix.

    Returns:
        1D numpy array with ylabels (in the keys' dtype). 2D ``data_dtype``
            numpy array with data values (rows are retention times, columns are
            ylabels).

    """
    num_times = pair_counts.size

    if keys.size == 0:
        return (np.empty(0, dtype=keys.dtype),
                np.zeros((num_times, 0), dtype=data_dtype))

    # Map each rounded key onto a non-negative integer bin so the unique
    # ylabels and per-pair columns come from a histogram, not a sort.
    scale = 10 ** prec if prec > 0 else 1
    int_keys = np.rint(keys * scale).astype(np.int64)
    int_keys -= int_keys.min()

    present = np.zeros(int(int_keys.max()) + 1, dtype=bool)
    present[int_keys] = True
    num_ylabels = int(present.sum())

    # Column of each pair = its dense bin's rank among the present bins.
    # Columns increase with the key value, so scattering the (already rounded)
    # keys yields the sorted unique ylabels - in the keys' own dtype, matching
    # the previous np.unique(keys) (e.g. float32 for calibrated Waters m/z).
    columns = (np.cumsum(present) - 1)[int_keys]
    ylabels = np.empty(num_ylabels, dtype=keys.dtype)
    ylabels[columns] = keys

    rows = np.repeat(np.arange(num_times), pair_counts)
    flat_indices = rows * num_ylabels + columns

    data = np.zeros(num_times * num_ylabels, dtype=data_dtype)
    np.add.at(data, flat_indices, values)

    return ylabels, data.reshape(num_times, num_ylabels)
