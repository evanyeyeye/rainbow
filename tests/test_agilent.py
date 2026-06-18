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
#   - teal:   Agilent OpenLab CDS .dx archive (DAD spectrum + 2 DAD signals +
#             2 instrument telemetry traces); parsed with telemetry=True so the
#             .IT analog traces are included.
@pytest.mark.parametrize(
    "color, ext, telemetry",
    [
        ("red", "D", False),
        ("orange", "D", False),
        ("yellow", "D", False),
        ("green", "D", False),
        ("brown", "D", False),
        ("pink", "D", False),
        ("teal", "dx", True),
    ],
    ids=["red", "orange", "yellow", "green", "brown", "pink", "teal"],
)
def test_agilent(color, ext, telemetry):
    assert_data_directory(color, ext, telemetry=telemetry)


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
