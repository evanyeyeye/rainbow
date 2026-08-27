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


# Finest meaningful m/z bin width per vendor (the m/z grid the binary records;
# see the per-vendor MS docs). A bin_width below this only inserts empty bins.
# These describe unit-resolution data, the default assumption for a channel
# whose parser does not record a floor of its own.
#
# One number per vendor is a floor, not a measurement. Waters stores each m/z
# with its own exponent, so the grid depends on the run: the fixtures here
# record 0.036, 0.065 and 0.069. The constant sits below all of them, because
# warning that a width is too fine when the file resolves finer would be a
# false claim, while staying quiet about a width that is merely finer than one
# particular run costs nothing. rainbow.mz_resolution answers per file.
MZ_FLOORS = {'agilent': 0.1, 'waters': 0.03}

# Calibrated MassHunter (TOF/Q-TOF) data, profile or centroid, resolves far
# below any vendor floor, so its parsers record this one instead.
HRMS_MZ_FLOOR = 1e-6

# Where the search below stops. Beyond this many decimals a float64 m/z label
# carries no more information, so a denormal bin_width would otherwise loop
# forever raising a precision that cannot rise. It bounds the search, not the
# caller's display_precision: rb.read holds that to its own limit, and this is
# the floor under a bin_width the search is chasing.
_MAX_LABEL_DECIMALS = 17

# Above this many bins in the span, lay the bins out by sorting rather than by
# allocating an array over the whole span. Matches the cap the MassHunter grid
# builder uses. At about 9 bytes a bin the dense path costs ~450 MB here, and
# the spans that exceed it are almost entirely empty bins.
_MAX_DENSE_BINS = 50_000_000


def label_precision(display_precision, bin_width):
    """
    ``display_precision``, raised if it is too coarse to label every bin.

    Rounding bin centres for display is meant to be cosmetic. It stops being
    cosmetic once it is coarser than the bins themselves: adjacent centres round
    to the same number, and the labels no longer name the columns one to one.
    A caller then cannot address a column at all, and the ones that silently
    lose are the columns that share a label with an earlier one, so
    ``extract_traces`` returns part of the signal at that m/z and a CSV export
    repeats the header.

    Bin centres are multiples of ``bin_width``, so adjacent labels differ by
    exactly ``bin_width`` and stay distinct as long as the rounding step is no
    larger than that. The vendor default is 0 decimals (unit-resolution data),
    which collides for every ``bin_width`` below 1, including the sub-unit
    widths :func:`rainbow.mz_resolution` recommends.

    """
    if display_precision is None or bin_width is None or not bin_width > 0:
        return display_precision
    decimals = display_precision
    while decimals < _MAX_LABEL_DECIMALS and 10.0 ** -decimals > bin_width:
        decimals += 1
    return decimals


def bin_datapairs(keys, values, pair_counts, bin_width,
                  display_precision=None, data_dtype=np.int64,
                  labels_only=False):
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
        labels_only (bool, optional): Return the bin labels and an empty
            ``(num_times, 0)`` matrix, skipping the accumulation. The matrix is
            ``num_times x num_ylabels``, which at a bin width far below the
            vendor grid dwarfs the input: a caller that only wants to know what
            grid the run records (:func:`rainbow.mz_resolution`) would otherwise
            build tens of gigabytes to read one number off the labels.

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

    # Assign each key to a bin of width bin_width (this is the lossy step).
    # A bin_width small enough to send a key past the float64 range, or past
    # what an int64 bin index can hold, would silently wrap: every key would
    # cast to the same index and the whole run would collapse into one column
    # holding the total signal. Refuse instead of returning that.
    scaled = np.asarray(keys, dtype=np.float64) / bin_width
    if not np.isfinite(scaled).all() or np.abs(scaled).max() >= 2.0 ** 62:
        raise ValueError(
            f"bin_width={bin_width!r} is too small for keys up to "
            f"{float(np.max(keys)):g}: the bin index overflows.")
    bins = np.rint(scaled).astype(np.int64)
    base = int(bins.min())
    span = int(bins.max()) - base + 1

    # Densifying the bin indices gets the unique bins and per-pair columns from
    # a histogram rather than a sort, but it allocates over the whole span, not
    # just the bins that occur. A bin_width far below the vendor grid makes that
    # span enormous while the number of occupied bins stays small (a 1e-8 width
    # over a few hundred daltons is tens of billions of bins, most of them
    # empty), so past a cap it sorts instead. Without the cap the allocation
    # reaches gigabytes and the process is killed before the too-fine-bin_width
    # warning, which runs after the parse, can be printed.
    if span <= _MAX_DENSE_BINS:
        dense = bins - base
        present = np.zeros(span, dtype=bool)
        present[dense] = True
        num_ylabels = int(present.sum())
        # Column of each pair = its dense bin's rank among the present bins.
        # Columns increase with the key value, so the ylabels come out sorted.
        columns = (np.cumsum(present) - 1)[dense]
        occupied = np.flatnonzero(present) + base
    else:
        occupied = np.unique(bins)
        num_ylabels = occupied.size
        columns = np.searchsorted(occupied, bins)

    # The ylabel of each present bin is its centre (bin index * bin_width),
    # rounded only for display. Rounding is cosmetic: the binning above already
    # set which pairs share a column. It is held to a precision fine enough to
    # keep every centre distinct, so that it stays cosmetic and the labels go on
    # naming the columns one to one.
    centres = occupied * float(bin_width)
    ylabels = centres if display_precision is None \
        else np.round(centres, label_precision(display_precision, bin_width))

    if labels_only:
        return ylabels, np.zeros((num_times, 0), dtype=data_dtype)

    rows = np.repeat(np.arange(num_times), pair_counts)
    flat_indices = rows * num_ylabels + columns

    data = np.zeros(num_times * num_ylabels, dtype=data_dtype)
    np.add.at(data, flat_indices, values)

    return ylabels, data.reshape(num_times, num_ylabels)
