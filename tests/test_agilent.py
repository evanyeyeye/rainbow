"""
Unit tests for parsing Agilent .D directories.

"""
import pytest

import rainbow as rb
from tests.datatester import assert_data_directory


# Each case is (color, ext, telemetry). The docstrings of the former methods
# describe the contents of each fixture:
#   - red:    UV spectrum, 2 UV channels, CAD channel
#   - orange: ELSD channel, MS spectrum (LC format)
#   - yellow: FID channel, MS spectrum (GC format), MS SIM (GC format)
#   - green:  partial UV spectrum, 4 partial MS traces (LC format)
#   - brown:  31-version UV spectrum, 4 30-version MS traces (LC format)
#   - pink:   UV spectrum (131 OL format), 6 MS channels (179 OL format)
#   - silver: Agilent 8900 ICP-MS spectrum (MassHunter MSProfile.bin,
#             uncompressed); parsed with hrms=True to route through the
#             MassHunter parser (issue #25).
#   - teal:   Agilent OpenLab CDS .dx archive (DAD spectrum + 2 DAD signals +
#             2 instrument telemetry traces); parsed with telemetry=True so the
#             .IT analog traces are included.
@pytest.mark.parametrize(
    "color, ext, hrms, telemetry",
    [
        ("red", "D", False, False),
        ("orange", "D", False, False),
        ("yellow", "D", False, False),
        ("green", "D", False, False),
        ("brown", "D", False, False),
        ("pink", "D", False, False),
        ("silver", "D", True, False),
        ("teal", "dx", False, True),
    ],
    ids=["red", "orange", "yellow", "green", "brown", "pink", "silver", "teal"],
)
def test_agilent(color, ext, hrms, telemetry):
    assert_data_directory(color, ext, hrms=hrms, telemetry=telemetry)


def test_teal_telemetry_off():
    """
    Tests that .dx telemetry (.IT) is skipped unless requested.

    """
    path = "tests/inputs/teal.dx"

    # By default the telemetry traces are not parsed.
    datadir = rb.read(path)
    assert datadir.analog == []
    assert all(df.detector == 'UV' for df in datadir.datafiles)

    # The telemetry flag includes them as analog data.
    datadir = rb.read(path, telemetry=True)
    assert sorted(df.name for df in datadir.analog) == sorted(
        ["WPS1A.IT", "PMP1B.IT"])

    # An explicitly requested telemetry trace is parsed even when the flag
    # is off.
    datadir = rb.read(path, requested_files=["PMP1B.IT"])
    assert sorted(df.name for df in datadir.analog) == sorted(["PMP1B.IT"])


@pytest.mark.parametrize(
    "signal,expected",
    [
        # A wavelength clause, and only a wavelength clause, makes a channel UV.
        ("DAD1A,Sig=210,4  Ref=off", ("UV", "210")),
        ("DAD1B, Sig=280.0,4.0  Ref=off", ("UV", "280.0")),
        # An "=" belonging to something else does not. These read as FID
        # because that is what the 179/181 container defaults to, and a wrong
        # answer here retypes the run's whole document: a gain setting taken
        # for a wavelength publishes picoamps as milli-absorbance in a liquid
        # chromatography document.
        ("FID1A, Front Signal (Gain=1)", ("FID", "")),
        ("Front Signal", ("FID", "")),
        ("=", ("FID", "")),
        # The ADC channels keep their own naming, unaffected by either.
        ("ADC1 CHANNEL A", ("ELSD", "")),
        ("ADC1", ("CAD", "")),
    ],
)
def test_detector_is_read_from_the_wavelength_clause(signal, expected):
    from rainbow.agilent.chemstation import _detector_from_signal

    metadata = {"signal": signal}
    assert _detector_from_signal(metadata, default="FID") == expected
    # A channel typed UV always carries the wavelength the ASM export needs for
    # its detector wavelength setting; nothing else invents one.
    assert ("wavelength" in metadata) == (expected[0] == "UV")
