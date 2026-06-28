"""
Shared helper for binning (key, value) data pairs into a spectrum matrix.

Several vendor parsers store a scan's spectrum as a flat list of
``(ylabel, value)`` pairs - Waters ``_FUNC.DAT`` (m/z or wavelength) and
Agilent ``.ms`` (m/z) - and need to lay those pairs out as a
``(retention time x ylabel)`` matrix, summing pairs that fall in the same bin
within a scan. This module provides one vectorized implementation of that step.

The bin width is the lossy control: keys closer together than ``bin_width`` are
merged. The bin labels are the bin centres, optionally rounded to a display
precision for presentation, which is purely cosmetic and never merges data.
"""

import numpy as np


def bin_datapairs(keys, values, pair_counts, bin_width,
                  display_precision=None, data_dtype=np.int64):
    """
    Bins (key, value) data pairs into a (retention time x ylabel) matrix.

    Each scan (retention time) contributes ``pair_counts[i]`` consecutive pairs
    from the flat :obj:`keys`/:obj:`values` arrays. Each key is assigned to a bin
    of width :obj:`bin_width`, and pairs landing in the same bin within a scan
    are summed. This binning is the only lossy step: distinct keys closer than
    :obj:`bin_width` are merged, and their values added. The bin labels are the
    bin centres, rounded to :obj:`display_precision` decimals for presentation
    (a cosmetic step that never merges data).

    The keys must be non-negative (m/z or wavelength). The unique bins and each
    pair's column are found with an integer histogram in O(n), not a sort. The
    values are accumulated into a ``data_dtype`` matrix (matching whatever dtype,
    and overflow/truncation behavior, the caller's prior per-scan ``np.add.at``
    loop used).

    Args:
        keys (np.ndarray): Flat ylabels (m/z or wavelength), non-negative.
        values (np.ndarray): Flat values paired with :obj:`keys`.
        pair_counts (np.ndarray): Number of pairs at each retention time.
        bin_width (float): Width of each bin, in the keys' units. The lossy
            control: keys within one bin are summed.
        display_precision (int, optional): Decimals to round the bin-centre
            labels to for display. ``None`` (the default) leaves them unrounded.
        data_dtype (np.dtype, optional): dtype of the output matrix.

    Returns:
        1D numpy array of bin-centre ylabels. 2D ``data_dtype`` numpy array with
            data values (rows are retention times, columns are ylabels).

    """
    if not bin_width > 0:
        raise ValueError(f"bin_width must be positive, got {bin_width!r}.")

    num_times = pair_counts.size

    if keys.size == 0:
        return (np.empty(0, dtype=np.float64),
                np.zeros((num_times, 0), dtype=data_dtype))

    # Assign each key to a bin of width bin_width (this is the lossy step), then
    # densify the bin indices so the unique bins and per-pair columns come from a
    # histogram, not a sort.
    bins = np.rint(np.asarray(keys, dtype=np.float64) / bin_width).astype(
        np.int64)
    base = int(bins.min())
    dense = bins - base

    present = np.zeros(int(dense.max()) + 1, dtype=bool)
    present[dense] = True
    num_ylabels = int(present.sum())

    # Column of each pair = its dense bin's rank among the present bins. Columns
    # increase with the key value, so the ylabels come out sorted.
    columns = (np.cumsum(present) - 1)[dense]

    # The ylabel of each present bin is its centre (bin index * bin_width),
    # rounded only for display. Rounding is cosmetic: the binning above already
    # set which pairs share a column.
    centres = (np.flatnonzero(present) + base) * float(bin_width)
    ylabels = centres if display_precision is None \
        else np.round(centres, display_precision)

    rows = np.repeat(np.arange(num_times), pair_counts)
    flat_indices = rows * num_ylabels + columns

    data = np.zeros(num_times * num_ylabels, dtype=data_dtype)
    np.add.at(data, flat_indices, values)

    return ylabels, data.reshape(num_times, num_ylabels)
