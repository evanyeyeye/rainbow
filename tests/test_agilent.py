"""
Unit tests for parsing Agilent .D directories.

"""
import struct

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


@pytest.mark.parametrize("path,name", [
    ("tests/inputs/pink.D", "DAD1A.ch"),      # Chemstation 130/30
    ("tests/inputs/red.D", "DAD1B.ch"),       # Chemstation, one decimal
    ("tests/inputs/teal.dx", "DAD1H.CH"),     # OpenLab .dx
    ("tests/inputs/bronze.D", "DAD1A.cg"),    # MassHunter, float all along
])
def test_a_single_wavelength_ylabel_is_a_number(path, name):
    # The label is the axis, and an axis is looked up by value. It arrived as
    # text out of the signal string, so extract_traces(254.0) raised on a
    # Chemstation channel and worked on the MassHunter channel beside it, and
    # the spelling followed the vendor's own ("210" against "210.0").
    import warnings

    import numpy as np

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        datafile = rb.read(path).get_file(name)

    assert datafile.ylabels.dtype.kind == "f"
    wavelength = float(datafile.ylabels[0])
    assert wavelength == datafile.metadata["wavelength"]
    # The lookup the axis exists for.
    traces = datafile.extract_traces(wavelength)
    assert np.asarray(traces).shape[-1] == datafile.data.shape[0]


@pytest.mark.parametrize("path,name", [
    ("tests/inputs/yellow.D", "FID1A.ch"),
    ("tests/inputs/red.D", "ADC1A.CH"),
    ("tests/inputs/orange.D", "ADC1A.CH"),
])
def test_a_channel_with_no_wavelength_keeps_its_empty_label(path, name):
    # FID, CAD and a bare analog input have no wavelength to report, so there
    # is no number to give and the label stays as it always was.
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        datafile = rb.read(path).get_file(name)

    assert list(datafile.ylabels) == [""]


# --- Scan sizes across the uint16 multiply (issue #75) ---------------------
#
# parse_ms held each scan's pair count in a numpy uint16 array. Read back out,
# pair_count * 4 was uint16 arithmetic and wrapped at 65536, so a scan of more
# than 16383 pairs read a fraction of its own bytes and the reader resumed
# inside it. The collected bytes then stopped matching the counts describing
# them, which surfaced as numpy refusing the short buffer: "strides is
# incompatible with shape of requested array". numpy 1 widened the multiply to
# int64 and hid it; numpy 2 keeps the uint16.


def _synthesize_ms(raw, pair_counts):
    """Build an LC .ms file with scans of the given sizes, reusing a real
    file's header so everything outside the scan records stays valid.

    A record is 18 bytes of header, then the mz-intensity pairs, then a 10 byte
    trailer, and it opens with its own length in 16-bit words.

    Args:
        raw (bytes): Contents of a "MSD Spectral File" .ms file, for its header.
        pair_counts (list): Number of pairs to write for each scan.

    """
    start = struct.unpack_from('>H', raw, 0x10A)[0] * 2 - 2
    out = bytearray(raw[:start])
    struct.pack_into('>I', out, 0x116, len(pair_counts))
    for i, count in enumerate(pair_counts):
        record = bytearray(18 + count * 4 + 10)
        struct.pack_into('>H', record, 0, len(record) // 2)
        struct.pack_into('>I', record, 2, (i + 1) * 60000)   # one minute apart
        struct.pack_into('>H', record, 12, count)
        for j in range(count):
            # m/z is stored twentyfold in a uint16, so it has to stay under
            # 3276 Da. Cycling keeps a big scan inside that without changing
            # what the row sums to. Every intensity is an unscaled 1.
            struct.pack_into('>H', record, 18 + j * 4, (100 + j % 2000) * 20)
            struct.pack_into('>H', record, 20 + j * 4, 1)
        out += record
    return bytes(out)


@pytest.mark.parametrize("count", [
    16383,   # the largest scan the uint16 multiply survived
    16384,   # the first it did not
    25201,   # the largest scan in the file reported in issue #75
])
def test_a_scan_larger_than_a_uint16_multiply_reads_whole(tmp_path, count):
    raw = open("tests/inputs/orange.D/MSD1.MS", "rb").read()
    path = tmp_path / "MSD1.MS"
    path.write_bytes(_synthesize_ms(raw, [count, count]))

    from rainbow.agilent.chemstation import parse_ms
    parsed = parse_ms(str(path))

    assert parsed.data.shape[0] == 2
    # Every pair carries an intensity of 1, so a scan has to total its own pair
    # count. A short read leaves the row summing to less.
    assert parsed.data.sum(axis=1).tolist() == [count, count]


def test_scan_sizes_either_side_of_the_wrap_read_the_same_way(tmp_path):
    # The wrap was harmless for small scans and fatal for large ones in the
    # same file, which is why it read as large files being the problem. Sizes
    # spanning the wrap have to behave alike.
    raw = open("tests/inputs/orange.D/MSD1.MS", "rb").read()
    counts = [3, 16383, 7, 16384, 20000, 11]
    path = tmp_path / "MSD1.MS"
    path.write_bytes(_synthesize_ms(raw, counts))

    from rainbow.agilent.chemstation import parse_ms
    parsed = parse_ms(str(path))

    assert parsed.data.shape[0] == len(counts)
    assert parsed.data.sum(axis=1).tolist() == counts
