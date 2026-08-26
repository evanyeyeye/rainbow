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


@pytest.mark.parametrize(
    "signal,expected",
    [
        # The 130/30 container holds no FID, so a settings clause in a
        # spelling other than Sig= is still an optical one. Requiring Sig=
        # here typed these as nothing, which is not a milder failure than
        # typing them wrong: a detector of None routes the channel into
        # analog, out of datafiles, out of by_detector, and out of the export.
        ("VWD1A, Wavelength=254 nm", ("UV", "254")),
        ("MWD1A, Wavelength=210.0 nm", ("UV", "210.0")),
        ("Wavelength = 280 nm", ("UV", "280")),
        # A clause rainbow cannot read a number out of still names a UV
        # channel, as it did before, but invents no wavelength for it.
        ("VWD1A, Signal=A", ("UV", "A")),
        # And the detectors that name themselves are unaffected.
        ("ADC1 CHANNEL A", ("ELSD", "")),
        ("DAD1A,Sig=210,4  Ref=off", ("UV", "210")),
        ("RID1A, Refractive Index Signal", (None, "")),
    ],
)
def test_a_uv_only_container_reads_a_wavelength_in_any_spelling(
        signal, expected):
    from rainbow.agilent.chemstation import _detector_from_signal

    metadata = {"signal": signal}
    assert _detector_from_signal(metadata, uv_only=True) == expected
    # The spelled-out wavelength reaches the ASM export the same way the Sig=
    # clause does.
    if "254" in signal:
        assert metadata["wavelength"] == 254.0
    if signal.endswith("Signal=A"):
        assert "wavelength" not in metadata


def test_the_uv_only_reading_is_not_applied_where_fid_lives():
    # The same leniency on the 179/181 container is the bug it was written to
    # fix: there a gain setting would be read as a wavelength, and the run
    # would be published as liquid chromatography measuring absorbance.
    from rainbow.agilent.chemstation import _detector_from_signal

    signal = {"signal": "FID1A, Front Signal (Gain=1)"}
    assert _detector_from_signal(signal, default="FID") == ("FID", "")
    assert _detector_from_signal(signal, default="FID", uv_only=True) \
        == ("UV", "1)")


def test_header_strings_decode_beyond_ascii():
    # Chemstation header slots with a gap of two are UTF-16LE. Reading every
    # other byte agrees with a proper decode only while the text is ASCII; for
    # anything else it produced invalid UTF-8, which the reader swallowed, so
    # the field came back empty rather than wrong.
    import io
    from rainbow.agilent.chemstation import read_string

    for text in ["Front Signal", "Café Münster", "样品-001",
                 "Проба 12"]:
        encoded = text.encode("utf-16-le")
        buf = b"\x00" * 8 + bytes([len(text)]) + encoded
        assert read_string(io.BytesIO(buf), offset=8, gap=2) == text.strip()


def test_an_undecodable_header_slot_still_returns_a_string():
    # A slot that is not valid UTF-16 at all must not raise; the stride remains
    # the fallback so a malformed header degrades rather than breaking the read.
    import io
    from rainbow.agilent.chemstation import read_string

    buf = b"\x00" * 8 + bytes([2]) + b"\xff\xdc\xff\xdc"
    assert isinstance(read_string(io.BytesIO(buf), offset=8, gap=2), str)
