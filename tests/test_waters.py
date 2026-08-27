"""
Unit tests for parsing Waters .raw directories.

"""
import pytest

import rainbow as rb
from tests.datatester import assert_data_directory


# Each case is (color, ext). The docstrings of the former methods describe the
# contents of each fixture:
#   - blue:      UV spectrum, MS spectrum (8-byte format), CAD channel
#   - indigo:    MS trace (2-byte format), 2 analog channels
#   - violet:    UV spectrum, 3 UV channels (analog), 2 MS spectra (6-byte
#                format), ELSD channel
#   - white:     6 UV spectrum (4-byte format), 2 analog channels
#   - turquoise: Perkin-Elmer / TurboMass .raw export with lowercase filenames
#                and PE _extern.inf polarity format
@pytest.mark.parametrize(
    "color, ext",
    [
        ("blue", "raw"),
        ("indigo", "raw"),
        ("violet", "raw"),
        ("white", "raw"),
        ("turquoise", "raw"),
    ],
    ids=["blue", "indigo", "violet", "white", "turquoise"],
)
def test_waters(color, ext):
    assert_data_directory(color, ext)


def test_acquisition_mode_tagged_from_function_type():
    # The MS acquisition mode is read from the function type in _FUNCTNS.INF,
    # not guessed: indigo is a SIR (Waters' SIM) acquisition, turquoise a full
    # scan. (SIR is the low-5-bit type code 1; an MS scan is 0.)
    def ms_modes(color):
        datadir = rb.read(f"tests/inputs/{color}.raw")
        return {df.name: df.metadata.get("acquisition_mode")
                for df in datadir.datafiles if df.detector == "MS"}

    assert ms_modes("indigo") == {"_FUNC001.DAT": "SIM"}
    assert ms_modes("turquoise") == {"_func001.dat": "Scan"}


def test_function_type_helpers_degrade_and_map():
    # The function-type helpers must not crash on a missing/short sidecar, and
    # the type-code mapping is scan (0), SIR=SIM (1), and untagged otherwise.
    from rainbow.waters import masslynx
    assert masslynx._function_types("/tmp/does-not-exist.inf", 3) == []
    assert masslynx._acquisition_mode(0) == "Scan"
    assert masslynx._acquisition_mode(1) == "SIM"
    assert masslynx._acquisition_mode(12) is None  # diode array: not an MS mode


def test_a_diode_array_axis_ignores_the_m_z_bin_width():
    """The DAD wavelength axis is in nanometres on a 1 nm step, whatever
    bin_width the caller passed for the MS channels in the same run."""
    import numpy as np
    for bin_width in (1.0, 0.05):
        datadir = rb.read("tests/inputs/violet.raw", bin_width=bin_width)
        labels = np.asarray(
            datadir.get_file("_FUNC003.DAT").ylabels, dtype=float)
        assert np.allclose(np.diff(labels), 1.0), bin_width
        # The MS channels in the same run do follow bin_width.
        ms = np.asarray(datadir.get_file("_FUNC001.DAT").ylabels, dtype=float)
        assert np.min(np.diff(ms)) <= bin_width


def test_the_uv_wavelength_step_is_not_the_ms_bin_width():
    from rainbow.waters.masslynx import (
        _UV_WAVELENGTH_STEP, _FUNC_TYPE_DIODE_ARRAY)

    assert _UV_WAVELENGTH_STEP == 1.0
    assert _FUNC_TYPE_DIODE_ARRAY == 12


# NOT COVERED, and no bundled fixture can cover it: reading the axis from the
# declared function type rather than from the guessed detector only changes an
# answer for a function that is (a) not type 12, (b) typed UV by the polarity
# fallback, and (c) in the 6/8 format, which is the only one that bins rather
# than taking its labels from _FUNCTNS.INF. white.raw is (a) and (b) but is in
# the 2/4 format, so reverting the change leaves every bundled fixture
# byte-identical. Covering it needs a fixture that does not exist yet.


@pytest.mark.parametrize("func_type,detector,expected", [
    # A function the file calls a diode array is a wavelength axis whatever the
    # polarity metadata says.
    (12, 'UV', True),
    (12, 'MS', True),
    # Any other recorded type is m/z, and must stay subject to bin_width. This
    # is the MRM-without-polarity case: the polarity alone would call it UV and
    # silently exempt an m/z axis from the caller's binning.
    (0, 'UV', False),
    (6, 'UV', False),
    (6, 'MS', False),
    # With no recorded type there is nothing better than the polarity.
    (None, 'UV', True),
    (None, 'MS', False),
])
def test_the_wavelength_axis_rule(func_type, detector, expected):
    from rainbow.waters.masslynx import _is_wavelength_axis

    assert _is_wavelength_axis(func_type, detector) is expected


def test_a_diode_array_function_ignores_bin_width():
    # The rule's whole point: an m/z bin width must not merge DAD channels.
    # blue.raw's UV function is a real diode array, so a coarse bin_width must
    # leave its wavelength axis alone.
    import numpy as np
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plain = rb.read("tests/inputs/blue.raw")
        coarse = rb.read("tests/inputs/blue.raw", bin_width=5.0)

    for a, b in zip(plain.datafiles, coarse.datafiles):
        if a.detector != 'UV':
            continue
        np.testing.assert_array_equal(np.asarray(a.ylabels, dtype=float),
                                      np.asarray(b.ylabels, dtype=float))
