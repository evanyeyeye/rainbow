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


def test_labels_stay_distinct_below_the_vendor_display_precision():
    """ A sub-unit bin_width must not round neighbouring bins onto one label.

    Chemstation and Waters resolve an 'auto' display_precision to 0 decimals,
    which is coarser than any bin_width below 1 - including the widths
    rb.mz_resolution reports as the practical ceiling for those files. Rounding
    is documented as cosmetic, so it has to stay fine enough for the labels to
    name the columns one to one. When they collided, extract_traces returned
    whichever column the duplicate label found first (a fraction of the signal
    at that m/z) and to_csvstr repeated the header.
    """
    import warnings
    import rainbow as rb
    for path, bin_width in (("tests/inputs/orange.D", 0.1),
                            ("tests/inputs/turquoise.raw", 0.05)):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            datadir = rb.read(path, bin_width=bin_width)
        for datafile in datadir.datafiles:
            if datafile.detector != 'MS':
                continue
            labels = np.asarray(datafile.ylabels, dtype=float)
            assert np.unique(labels).size == labels.size, (
                "{} {} labels {} bins".format(
                    path, np.unique(labels).size, labels.size))
            # The whole signal at a label is reachable through that label.
            total = float(np.asarray(datafile.data).sum())
            traced = float(np.asarray(
                datafile.extract_traces(list(labels))).sum())
            assert traced == pytest.approx(total)


def test_label_precision_only_raises_what_the_grid_needs():
    from rainbow._binning import label_precision

    assert label_precision(0, 1.0) == 0        # unit bins, unit labels
    assert label_precision(0, 0.1) == 1
    assert label_precision(0, 0.05) == 2
    assert label_precision(4, 1e-6) == 6
    assert label_precision(8, 0.1) == 8        # never lowers a fine request
    assert label_precision(None, 0.1) is None  # unrounded stays unrounded


def test_a_bin_width_far_below_the_grid_does_not_allocate_the_whole_span():
    """ The dense layout allocates over the span, not the occupied bins.

    A bin_width far below the vendor grid makes that span enormous while the
    occupied bins stay few, so past a cap the bins are laid out by sorting.
    Without it the allocation reached gigabytes and the process was killed
    before the too-fine-bin_width warning, which runs after the parse, could be
    printed.
    """
    import warnings
    import rainbow as rb
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        coarse = rb.read("tests/inputs/orange.D", bin_width=0.1)
        fine = rb.read("tests/inputs/orange.D", bin_width=1e-8)
    fine_ms = [f for f in fine.datafiles if f.detector == 'MS'][0]
    coarse_ms = [f for f in coarse.datafiles if f.detector == 'MS'][0]
    # Every occupied bin survives, and no empty ones were invented.
    assert fine_ms.ylabels.size == coarse_ms.ylabels.size
    assert np.unique(fine_ms.ylabels).size == fine_ms.ylabels.size
    assert float(np.asarray(fine_ms.data).sum()) == pytest.approx(
        float(np.asarray(coarse_ms.data).sum()))


def test_a_bin_width_that_overflows_the_bin_index_is_refused():
    """ Silently collapsing every key into one bin is worse than refusing.

    Below about 1e-17 the key/bin_width division overflows, every bin index
    casts to the same int64, and the run came back as a single column labelled
    0.0 holding the total signal - while the warning said the width was too
    fine to resolve anything.
    """
    import rainbow as rb
    with pytest.raises(ValueError, match="overflows"):
        rb.read("tests/inputs/turquoise.raw", bin_width=1e-300)


def test_a_binned_sibling_does_not_overwrite_a_per_scan_resolution():
    """ The probe read must not clobber an answer the first read got right.

    mz_resolution measures per-scan channels from their own scans, then
    re-reads on a fine probe grid for the channels that need it. The probe
    passes a bin_width, which is what turns a per-scan channel into a binned
    one, so an HRMS profile came back from the probe looking binned and
    replaced its own measurement with the probe's grid.

    Checked against ground truth rather than against the code's own rule: the
    profile's m/z axis is one scan's calibrated flight-time axis, so its
    spacing is computable here without asking rainbow how it would measure it.
    """
    import warnings
    import rainbow as rb
    path = "tests/inputs/amber.D"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        profile = rb.read(path, hrms=True).get_file("MSProfile.bin")
        axis = np.unique(np.asarray(profile.mass_labels(0), dtype=float))
        truth = round(float(np.min(np.diff(axis))), 7)
        got = rb.mz_resolution(path, hrms=True)["MSProfile.bin"]
    assert got == truth
    # A real spacing, not the 1e-3 grid the probe reads on.
    assert truth > 1e-3
    assert got != 1e-3


def test_a_centroid_resolution_is_measured_over_the_whole_run():
    """ A centroid's peaks are not a grid, so one scan cannot measure it.

    Each scan holds only the peaks that were picked, so the gaps inside a scan
    are peak separations: yellow.D's first scan holds two peaks, 130.99 and
    202.0, and measuring it reported 71 Da as the finest grid of a run that
    quantizes to 0.09. What the file quantizes to shows up only over the run.
    An HRMS profile is the opposite case, and is covered above: it samples
    every scan on one flight-time grid, so pooling scans would measure the
    calibration drift between them instead.
    """
    import warnings
    import rainbow as rb
    path = "tests/inputs/yellow.D"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        centroid = rb.read(path, centroid=True).get_file("MSPeak.bin")
        pooled = np.unique(np.concatenate([
            np.asarray(centroid.mass_labels(i), dtype=float)
            for i in range(len(centroid.xlabels))]))
        truth = round(float(np.min(np.diff(pooled))), 7)
        got = rb.mz_resolution(path, centroid=True)["MSPeak.bin"]
    assert got == truth
    # The fixture really does have the shape that made scan 0 misleading, so
    # this is not vacuously true.
    assert centroid.mass_labels(0).size == 2
    scan0 = np.unique(np.asarray(centroid.mass_labels(0), dtype=float))
    assert float(np.min(np.diff(scan0))) > 70          # the old answer
    assert truth < 0.1                                 # the real grid


def test_the_probe_reaches_a_channel_the_first_read_could_not_measure(tmp_path):
    """ A binned channel beside a per-scan one must still be measured.

    mz_resolution measures per-scan channels on the first read and everything
    else on a second, finer probe read. The probe used to run only when a
    binned MS channel was present, which named a channel type rather than
    asking what was still missing.

    No bundled fixture pairs an HRMS profile with a binned channel, so one is
    built here: without it the probe never runs and this asserts nothing, which
    is exactly how the previous version of this test passed while the bug it
    was named for was reintroduced.
    """
    import shutil
    import rainbow as rb
    mixed = tmp_path / "mixed.D"
    shutil.copytree("tests/inputs/amber.D", mixed)
    shutil.copy("tests/inputs/orange.D/MSD1.MS", mixed / "MSD1.MS")

    alone = rb.mz_resolution("tests/inputs/amber.D", hrms=True)
    together = rb.mz_resolution(str(mixed), hrms=True)
    # The profile keeps its own measurement, taken from one scan's axis...
    assert together["MSProfile.bin"] == alone["MSProfile.bin"] > 1e-3
    # ...and the binned sibling is measured too, on the probe grid.
    assert together["MSD1.MS"] == 0.1
    # Not the probe's own 1e-3 constant, which is what overwriting produced.
    assert together["MSProfile.bin"] != 1e-3


def test_bin_width_does_not_touch_a_waters_uv_function():
    """ bin_width is an m/z control, so a UV function's wavelengths are exempt.

    parse_function binned before it decided whether the function was MS or UV,
    so an m/z width re-binned DAD wavelengths: at bin_width=5.0 a 190-wavelength
    trace came back as 39 columns, five nanometres to a column. Nothing warned,
    because the too-fine-bin_width check only looks at MS files.
    """
    import warnings
    import rainbow as rb
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        default = rb.read("tests/inputs/violet.raw")
        coarse = rb.read("tests/inputs/violet.raw", bin_width=5.0)
    for before, after in zip(default.datafiles, coarse.datafiles):
        if before.detector != 'UV':
            continue
        np.testing.assert_array_equal(after.ylabels, before.ylabels)
        np.testing.assert_array_equal(after.data, before.data)
    # The MS functions in the same run do respond to it, so this is not
    # passing because bin_width was ignored everywhere.
    ms = [(b, a) for b, a in zip(default.datafiles, coarse.datafiles)
          if b.detector == 'MS']
    assert ms and all(a.ylabels.size < b.ylabels.size for b, a in ms)


def test_the_vendor_floor_never_contradicts_a_measured_grid():
    """ mz_resolution must not report a width that read() then calls too fine.

    One floor per vendor is a lower bound, not a measurement: Waters stores
    each m/z with its own exponent, so the grid varies by run. A floor above a
    real file's grid made the two APIs disagree, one reporting 0.036 as the
    achievable width and the other warning that using it was pointless.
    """
    import warnings
    import rainbow as rb
    for name in ("blue.raw", "turquoise.raw", "violet.raw", "orange.D"):
        path = "tests/inputs/" + name
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for width in rb.mz_resolution(path).values():
                rb.read(path, bin_width=width)
        assert not [w for w in caught if "finer than" in str(w.message)], name


def test_a_selected_ion_channel_reports_no_grid():
    """ Monitored ions are the method's choice, not a lattice.

    A SIM channel records only the m/z the method asked the instrument to
    watch, so the gap between them says nothing about what the binary can
    resolve. yellow.D watches 131 and 202, and reporting 71 Da as "the finest
    m/z spacing the binary actually stores" sent a caller to a bin_width 700
    times too coarse - while rb.read warned, correctly, that anything below
    0.1 Da on that run was too fine. The two APIs contradicted each other.
    """
    import rainbow as rb
    sim = rb.read("tests/inputs/yellow.D").get_file("dataSim.ms")
    assert sim.metadata["acquisition_mode"] == "SIM"
    assert list(sim.ylabels) == [131.0, 202.0]      # the shape that misled it
    answer = rb.mz_resolution("tests/inputs/yellow.D")
    assert "dataSim.ms" not in answer
    # The scan channel beside it is still measured.
    assert answer["data.ms"] == 0.1
    # A run whose MS is all selected-ion reports nothing rather than nonsense.
    assert rb.mz_resolution("tests/inputs/green.D") == {}


def test_labels_only_returns_the_same_labels_without_the_grid():
    # The grid is num_times x num_ylabels, which at a bin width far below the
    # vendor lattice dwarfs the data it came from. A caller measuring the grid
    # a run records reads nothing but the labels, so it must be able to skip
    # building it, and must get exactly the labels it would have got.
    import numpy as np
    from rainbow._binning import bin_datapairs

    keys = np.array([100.0, 100.02, 250.5, 250.5, 400.25])
    values = np.array([1, 2, 3, 4, 5], dtype=np.int64)
    pair_counts = np.array([3, 2], dtype=np.int64)

    full_labels, full_data = bin_datapairs(
        keys, values, pair_counts, 0.01, display_precision=4)
    lean_labels, lean_data = bin_datapairs(
        keys, values, pair_counts, 0.01, display_precision=4, labels_only=True)

    assert np.array_equal(full_labels, lean_labels)
    # Still a 2D array of the right height, so a DataFile can hold it.
    assert lean_data.shape == (pair_counts.size, 0)
    assert full_data.shape == (pair_counts.size, full_labels.size)


def test_labels_only_on_the_sparse_path():
    # The sparse fallback (past _MAX_DENSE_BINS) must skip the grid too.
    import numpy as np
    from rainbow._binning import bin_datapairs, _MAX_DENSE_BINS

    keys = np.array([1.0, 2.0 + _MAX_DENSE_BINS])
    values = np.array([1, 1], dtype=np.int64)
    pair_counts = np.array([2], dtype=np.int64)
    labels, data = bin_datapairs(keys, values, pair_counts, 1.0,
                                 labels_only=True)
    assert labels.size == 2 and data.shape == (1, 0)


def test_labels_only_on_empty_input():
    import numpy as np
    from rainbow._binning import bin_datapairs

    labels, data = bin_datapairs(
        np.array([]), np.array([]), np.array([0, 0]), 1.0, labels_only=True)
    assert labels.size == 0 and data.shape == (2, 0)
