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
