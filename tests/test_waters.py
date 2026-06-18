"""
Unit tests for parsing Waters .raw directories.

"""
import pytest

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
