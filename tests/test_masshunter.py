import os
import shutil
import struct
import tempfile

import numpy as np
import pytest
from lxml import etree

import rainbow as rb
from rainbow.agilent import masshunter

# gold/copper have LZF-compressed MSProfile.bin (real TOF data), so decoding
# them end to end needs python-lzf. The rest of the suite stays lzf-free (the
# magenta/cyan profile fixtures are run-length encoded on purpose), so the
# end-to-end gold/copper tests are skipped when python-lzf is not installed.
try:
    import lzf as _lzf  # noqa: F401
    HAVE_LZF = True
except ImportError:
    HAVE_LZF = False


# The `yellow` fixture is a MassHunter GC-MS acquisition whose AcqData folder
# contains MSScan.xsd, MSScan.bin, and MSTS.xml (but no MSProfile.bin). It
# gives us a ground-truth scan count from MSTS.xml to validate the
# MSTS.xml-independent counting against.
YELLOW_ACQDATA = os.path.join("tests", "inputs", "yellow.D", "AcqData")

# `magenta` and `cyan` are three-scan slices of two real Q-TOF profile
# acquisitions from issue #27, whose MSProfile.bin intensities are run-length
# encoded rather than LZF-compressed. They cover the two format variants we
# have seen:
#   - magenta: older MSScan.xsd (bare type names); UncompressedByteCount > 0.
#   - cyan: newer MSScan.xsd (namespace-prefixed type names, e.g.
#       "mstns:ScanRecordType"); UncompressedByteCount == 0.
# Each slice starts at the scan the reporter exported from Agilent MassHunter
# BioConfirm, so the first scan has a known ground-truth m/z (BIOCONFIRM_APEX_MZ
# below). Neither folder contains MSTS.xml, so they also exercise the
# MSTS-independent scan counting. Both decode without python-lzf installed.
MAGENTA_D = os.path.join("tests", "inputs", "magenta.D")
CYAN_D = os.path.join("tests", "inputs", "cyan.D")

# `amber` is a 500-scan slice of the same real Q-TOF run cyan is a 3-scan slice
# of, but kept long (so per-scan drift accumulates across the run) and windowed in
# m/z to ~823.8-827.2 (each scan's MSProfile.bin segment re-encoded to that
# flight-time range) so the fixture stays small (~0.6 MB). It is the only
# many-scan HRMS fixture and backs the documentation's real-world binning heatmap
# (docs/source/agilent/figures/make_figures.py). Run-length encoded, so no lzf.
AMBER_D = os.path.join("tests", "inputs", "amber.D")

# Apex m/z that BioConfirm reports for each fixture's first scan (its main-peak
# base peak), used to validate the mass calibration against ground truth.
BIOCONFIRM_APEX_MZ = {MAGENTA_D: 734.4836, CYAN_D: 825.4221}

# `gold` and `copper` are trimmed slices of a real Agilent TOF-MS acquisition
# (10 Hz) whose scans store BOTH a profile block (MSProfile.bin) and a centroid
# block (MSPeak.bin). Each ScanRecordType therefore carries two
# SpectrumParamValues blocks - the schema element is maxOccurs="unbounded" -
# which desynced the old fixed-size reader. Neither fixture has MSMassCal.bin,
# so they also exercise the DefaultMassCal.xml calibration fallback.
#   - gold:   3 complete scans; MSScan.bin, MSProfile.bin, MSPeak.bin all agree.
#   - copper: MSScan.bin describes 4 scans but MSProfile.bin was truncated after
#       3 (a deliberately interrupted/incomplete acquisition).
GOLD_D = os.path.join("tests", "inputs", "gold.D")
COPPER_D = os.path.join("tests", "inputs", "copper.D")

# `silver` is an Agilent ICP-MS acquisition; its isotope channels form a
# unit-resolution m/z axis (read through parse_icpmsdata). The Waters `.raw`
# fixtures below carry unit-resolution quadrupole MS m/z axes. Both are used to
# check that display_precision='auto' resolves to whole-number m/z labels for the
# non-HRMS parsers. teal.dx is a UV-only flush with no m/z axis, so the OpenLab
# .dx reader is not covered here (no usable fixture).
SILVER_ACQDATA = os.path.join("tests", "inputs", "silver.D", "AcqData")
# Waters .raw fixtures that actually carry an MS m/z axis (white.raw has none).
WATERS_MS_RAW = [
    os.path.join("tests", "inputs", name)
    for name in ("blue.raw", "indigo.raw", "turquoise.raw", "violet.raw")
]


def _msts_scan_count(acqdata):
    """ Ground-truth scan count: sum of NumOfScans in MSTS.xml. """
    root = etree.parse(os.path.join(acqdata, "MSTS.xml")).getroot()
    return sum(int(seg.find("NumOfScans").text)
               for seg in root.findall("TimeSegment"))


# ---------------------------------------------------------------------------
# Recovering the MS scan count without MSTS.xml.
#
# Agilent OpenLab .rslt/.sirslt result folders omit MSTS.xml, which the
# HRMS parser previously required to learn the number of scans. The count
# is now recovered by reading MSScan.bin to EOF. These tests confirm the
# recovered count exactly matches what MSTS.xml would have provided, and
# that parsing still works when MSTS.xml is absent entirely.
#
# These tests deliberately exercise only parse_scan_xsd / read_scan_records
# so they run without python-lzf (which is needed only to decompress
# MSProfile.bin) installed.
# ---------------------------------------------------------------------------

def test_scan_count_matches_msts():
    """ Counting MSScan.bin records reproduces the MSTS.xml scan count. """
    complextypes = masshunter.parse_scan_xsd(
        os.path.join(YELLOW_ACQDATA, "MSScan.xsd"))
    records = masshunter.read_scan_records(
        os.path.join(YELLOW_ACQDATA, "MSScan.bin"), complextypes)
    assert len(records) == _msts_scan_count(YELLOW_ACQDATA)


def test_read_scan_records_well_formed():
    """ The recovered records are exact and carry sane scan times. """
    complextypes = masshunter.parse_scan_xsd(
        os.path.join(YELLOW_ACQDATA, "MSScan.xsd"))
    records = masshunter.read_scan_records(
        os.path.join(YELLOW_ACQDATA, "MSScan.bin"), complextypes)

    # Each record is a parsed ScanRecordType dict carrying a ScanTime.
    assert all('ScanTime' in r for r in records)
    # Retention time advances monotonically across the run, confirming we
    # parsed real records rather than running off into garbage bytes.
    times = [r['ScanTime'] for r in records]
    assert all(t2 >= t1 for t1, t2 in zip(times, times[1:]))


def test_count_without_msts_xml():
    """ The count is recovered even when MSTS.xml is absent (the
    .rslt/.sirslt case). Copy only the files the new path needs. """
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("MSScan.xsd", "MSScan.bin"):
            shutil.copy(os.path.join(YELLOW_ACQDATA, name), tmp)
        assert not os.path.exists(os.path.join(tmp, "MSTS.xml"))

        complextypes = masshunter.parse_scan_xsd(
            os.path.join(tmp, "MSScan.xsd"))
        records = masshunter.read_scan_records(
            os.path.join(tmp, "MSScan.bin"), complextypes)
        assert len(records) == _msts_scan_count(YELLOW_ACQDATA)


# ---------------------------------------------------------------------------
# Parsing run-length-encoded MSProfile.bin (HRMS) data (issue #27).
#
# Q-TOF profile acquisitions store intensities with a run-length encoding
# instead of LZF compression, which made the parser raise "error in
# compressed data" (and, on newer files, fail to even read MSScan.xsd
# because its type names are namespace-prefixed). These tests parse trimmed
# real fixtures end to end and cross-check the decoded intensities against an
# independent value stored in MSScan.bin.
#
# They run without python-lzf installed, since RLE data does not use it.
# ---------------------------------------------------------------------------

def _profile_records(acqdata):
    complextypes = masshunter.parse_scan_xsd(
        os.path.join(acqdata, "MSScan.xsd"))
    return masshunter.read_scan_records(
        os.path.join(acqdata, "MSScan.bin"), complextypes)


def _assert_decodes(directory):
    """ Parses the fixture and checks each scan's decoded maximum
    intensity against the MaxY field stored independently in MSScan.bin. """
    datafiles = masshunter.parse_allfiles(
        directory, hrms=True, bin_width=0.0001)
    assert len(datafiles) == 1
    datafile = datafiles[0]

    acqdata = os.path.join(directory, "AcqData")
    records = _profile_records(acqdata)
    # One retention time per scan record; MSProfile.bin parsed to a grid.
    assert datafile.data.shape[0] == len(records)
    assert datafile.xlabels.size == len(records)
    assert datafile.data.shape[1] == datafile.ylabels.size

    with open(os.path.join(acqdata, "MSProfile.bin"), 'rb') as f:
        for record in records:
            params = record['SpectrumParamValues']
            f.seek(params['SpectrumOffset'])
            segment = f.read(params['ByteCount'])
            # The segment must be recognized as RLE (not mistaken for LZF).
            assert masshunter.segment_is_rle(segment, params['PointCount'])
            inten = masshunter.decompress_inten_list(
                memoryview(segment)[16:], params['PointCount'])
            assert inten.size == params['PointCount']
            # MaxY is the per-scan maximum intensity, stored separately from
            # the intensity stream - a strong independent decode check.
            assert int(inten.max()) == int(params['MaxY'])


@pytest.mark.parametrize("directory", [MAGENTA_D, CYAN_D], ids=["magenta", "cyan"])
def test_profile_decodes(directory):
    """ RLE profile data (issue #27) parses and decodes for both the
    older-format (magenta) and newer namespace-prefixed XSD (cyan). """
    _assert_decodes(directory)


def test_rle_not_confused_with_lzf():
    """ segment_is_rle only fires on the real signature. """
    records = _profile_records(os.path.join(MAGENTA_D, "AcqData"))
    params = records[0]['SpectrumParamValues']
    num_mz = params['PointCount']
    with open(os.path.join(MAGENTA_D, "AcqData", "MSProfile.bin"), 'rb') as f:
        f.seek(params['SpectrumOffset'])
        segment = f.read(params['ByteCount'])
    assert masshunter.segment_is_rle(segment, num_mz)
    # Wrong point count -> not RLE (the embedded length must match).
    assert not masshunter.segment_is_rle(segment, num_mz + 1)
    # Arbitrary/LZF-like bytes lack the 0x90 marker word -> not RLE.
    assert not masshunter.segment_is_rle(b"\x00" * 32, num_mz)


def test_mass_calibration_in_range():
    """ The calibrated mz axis spans a sensible HRMS range. """
    datafile = masshunter.parse_allfiles(
        CYAN_D, hrms=True, bin_width=0.0001)[0]
    assert datafile.ylabels.min() > 100
    assert datafile.ylabels.max() < 5000
    assert (datafile.ylabels[1:] > datafile.ylabels[:-1]).all()


def _scan_axis(directory, scan_index, use_polynomial=True):
    """ Decoded intensities and calibrated mz for one scan of a fixture. """
    acqdata = os.path.join(directory, "AcqData")
    records = _profile_records(acqdata)
    record = records[scan_index]
    params = record['SpectrumParamValues']
    num_mz = params['PointCount']
    with open(os.path.join(acqdata, "MSProfile.bin"), 'rb') as f:
        f.seek(params['SpectrumOffset'])
        segment = f.read(params['ByteCount'])
    start_mz, delta_mz = struct.unpack('<dd', segment[:16])
    inten = masshunter.decompress_inten_list(
        memoryview(segment)[16:], num_mz)

    with open(os.path.join(acqdata, "MSMassCal.bin"), 'rb') as cal_file:
        cal_bytes = cal_file.read()
    calib = np.ndarray((len(records), 10), '<d', cal_bytes[0x4c:], 0, (84, 8))
    flags = masshunter.parse_default_masscal(
        os.path.join(acqdata, "DefaultMassCal.xml"))
    use_flags = flags.get(record.get('CalibrationID')) if use_polynomial \
        else None
    tof = np.arange(
        start_mz, start_mz + delta_mz * (num_mz - 1) + 1e-3, delta_mz)
    mzs = masshunter.calibrate_mz(tof[:num_mz], calib[scan_index], use_flags)
    return inten, mzs


@pytest.mark.parametrize(
    "directory, truth",
    list(BIOCONFIRM_APEX_MZ.items()),
    ids=["magenta", "cyan"],
)
def test_polynomial_calibration_matches_bioconfirm(directory, truth):
    """ The polynomial calibration reproduces the m/z Agilent reports, and
    is meaningfully more accurate than the traditional calibration alone. """
    inten, mzs = _scan_axis(directory, 0)
    apex = mzs[int(np.argmax(inten))]
    assert round(apex - truth, 3) == 0
    # The polynomial term is actually applied (primary differs and
    # is further from the truth).
    _, mzs_primary = _scan_axis(directory, 0, use_polynomial=False)
    apex_primary = mzs_primary[int(np.argmax(inten))]
    assert round(apex_primary - apex, 5) != 0
    assert abs(apex - truth) < abs(apex_primary - truth)


def _rle_segment(num_mz, leading_zeros, tokens):
    """ Build a MSProfile.bin RLE segment body (the bytes after the 16-byte mz
    header): the 4-byte point-count word, the negated leading-zero count, then
    the already-packed `tokens` stream (which opens at 4-byte width). """
    return (struct.pack('<I', num_mz | (0x90 << 24))
            + struct.pack('<i', -leading_zeros) + tokens)


def test_profile_stream_opens_at_four_byte_width():
    """ Issue #27 follow-up: the token stream opens at 4-byte width, so a scan
    whose first stored intensity is a literal (a high-signal scan, with no
    leading width-switch control) decodes correctly. The previous reader read a
    separate "width flag" field that did not exist, which decoded identically
    whenever the first token was a width switch (the common case) but raised
    "Malformed MSProfile.bin RLE segment" on a literal-first scan. """
    tokens = (
        struct.pack('<i', 70000)    # 4-byte literal             -> inten[1]
        + struct.pack('<i', 80000)  # 4-byte literal             -> inten[2]
        + struct.pack('<i', -1)     # control @4B: 0 zeros, -> 1-byte width
        + struct.pack('<b', 5)      # 1-byte literal             -> inten[3]
        + struct.pack('<b', -2)     # control @1B: 0 zeros, -> 2-byte width
        + struct.pack('<h', 1000)   # 2-byte literal             -> inten[4]
    )
    body = _rle_segment(8, leading_zeros=1, tokens=tokens)
    expected = [0, 70000, 80000, 5, 1000, 0, 0, 0]

    out = masshunter.decompress_inten_list(memoryview(body), 8)
    assert out.tolist() == expected
    assert out.dtype == np.uint32
    # The compiled accelerator must decode the literal opening identically.
    if masshunter._msprofile_fast is not None:
        fast = masshunter._msprofile_fast.decompress_inten_list(
            memoryview(body), 8)
        assert fast.tolist() == expected


def test_malformed_rle_raises_valueerror():
    """ A corrupt RLE stream raises a clear ValueError, not a cryptic
    KeyError/struct.error/silent wraparound. """
    # A control token whose remainder is 0 is a zero-width switch -> invalid.
    # Opening at 4-byte width, -4 -> divmod(4, 4) = (1 zero, width flag 0).
    bad_width = _rle_segment(5, 0, struct.pack('<i', -4))
    with pytest.raises(ValueError):
        masshunter.decompress_inten_list(memoryview(bad_width), 5)

    # A positive initial zero-repeat would start the write index negative.
    neg_index = _rle_segment(5, -3, b"")
    with pytest.raises(ValueError):
        masshunter.decompress_inten_list(memoryview(neg_index), 5)

    # More literals than the point count must not overflow silently: switch to
    # 1-byte width, then emit more 1-byte literals than there are points.
    too_many = _rle_segment(5, 0, struct.pack('<i', -1) + struct.pack('<b', 7) * 9)
    with pytest.raises(ValueError):
        masshunter.decompress_inten_list(memoryview(too_many), 5)


# ---------------------------------------------------------------------------
# Per-scan profile representation (parse_msdata with no bin_width).
#
# An HRMS profile has a per-scan m/z axis: every scan shares the flight-time
# grid but the calibration drifts, so the m/z of a point depends on the scan
# too. With no bin_width, parse_msdata returns ProfileDataFile objects that keep
# the raw intensities and expose the per-scan m/z via scan(i)/mass_labels(i),
# instead of projecting onto one shared grid (which inserts zeros). See the
# "HRMS profile data model" docs page.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "directory", [MAGENTA_D, CYAN_D], ids=["magenta", "cyan"])
def test_per_scan_profile_is_faithful(directory):
    """ The per-scan form keeps raw intensities and exact per-scan m/z. """
    acqdata = os.path.join(directory, "AcqData")
    profiles = masshunter.parse_msdata(acqdata)
    assert isinstance(profiles, list) and len(profiles) >= 1

    records = _profile_records(acqdata)
    calib, flags = masshunter._load_calibration(
        acqdata, [r.get('CalibrationID') for r in records])

    profile = profiles[0]
    assert isinstance(profile, masshunter.ProfileDataFile)
    n, k = profile.data.shape           # rows are scans, columns flight-time bins
    assert profile.xlabels.size == n
    assert profile.flight_times.size == k

    for i in range(n):
        mz, inten = profile.scan(i)
        # The per-scan m/z is the exact calibration of the shared flight-time
        # axis (rounded to the reported precision), not a shared rounded grid.
        truth = np.round(
            masshunter.calibrate_mz(
                profile.flight_times, calib[i],
                flags.get(records[i].get('CalibrationID'))),
            profile.mz_decimals)
        np.testing.assert_array_equal(mz, truth)
        # Intensities are the raw decoded values: the per-scan maximum matches
        # the MaxY stored independently in MSScan.bin.
        assert int(inten.max()) == int(
            records[i]['SpectrumParamValues']['MaxY'])


def test_per_scan_profile_has_no_shared_ylabels():
    """ A profile has no single m/z axis, so ylabels raises with guidance
    rather than returning a silently-approximate array. """
    profile = masshunter.parse_msdata(
        os.path.join(MAGENTA_D, "AcqData"))[0]
    with pytest.raises(AttributeError, match="mass_labels"):
        profile.ylabels


def test_default_is_per_scan():
    """ With no bin_width the public rb.read API gives the per-scan
    representation; passing a bin_width opts into the shared grid. """
    datadir = rb.read(MAGENTA_D, hrms=True)
    profiles = [f for f in datadir.datafiles
                if isinstance(f, masshunter.ProfileDataFile)]
    assert len(profiles) >= 1
    mz, inten = profiles[0].scan(0)
    assert mz.shape == inten.shape == (profiles[0].data.shape[1],)
    # Opt in to the shared grid: a single non-profile DataFile with ylabels.
    binned = rb.read(MAGENTA_D, hrms=True, bin_width=0.01)
    profile_files = [f for f in binned.datafiles
                     if f.name.startswith("MSProfile")]
    assert len(profile_files) == 1
    assert not isinstance(profile_files[0], masshunter.ProfileDataFile)


# ---------------------------------------------------------------------------
# Parsing MassHunter profile data whose scans also store centroids.
#
# When an acquisition writes MSPeak.bin alongside MSProfile.bin, each
# ScanRecordType holds a profile block *and* a centroid block. The reader must
# step over the extra block at the true record stride (rather than mis-parsing
# it as the next scan), recover the m/z calibration from DefaultMassCal.xml
# when the per-scan MSMassCal.bin is absent, and keep the complete scans of an
# interrupted acquisition whose trailing MSProfile.bin segments were never
# written.
# ---------------------------------------------------------------------------

def _acqdata(directory):
    return os.path.join(directory, "AcqData")


def _complextypes(directory):
    return masshunter.parse_scan_xsd(
        os.path.join(_acqdata(directory), "MSScan.xsd"))


def test_type_size_matches_reader():
    """ type_size predicts the bytes read_complextype consumes, which is
    what lets read_scan_records reason about the record stride. """
    ctd = _complextypes(GOLD_D)
    # SpectrumParamsType is the 64-byte block that repeats per scan.
    assert masshunter.type_size(ctd, "SpectrumParamsType") == 64

    path = os.path.join(_acqdata(GOLD_D), "MSScan.bin")
    with open(path, 'rb') as f:
        f.seek(0x58)
        f.seek(struct.unpack('<I', f.read(4))[0])
        start = f.tell()
        masshunter.read_complextype(f, ctd, "ScanRecordType")
        consumed = f.tell() - start
    assert consumed == masshunter.type_size(ctd, "ScanRecordType")


def test_fixtures_lack_msmasscal():
    """ These fixtures intentionally have no per-scan MSMassCal.bin, so they
    exercise the DefaultMassCal.xml fallback. """
    for directory in (GOLD_D, COPPER_D):
        assert not os.path.exists(
            os.path.join(_acqdata(directory), "MSMassCal.bin"))


def test_two_block_records_read_at_correct_stride():
    """ Two-block records are read one per scan, not mis-split into extra
    single-block records, and carry monotonic scan times. """
    acqdata = _acqdata(GOLD_D)
    records = masshunter.read_scan_records(
        os.path.join(acqdata, "MSScan.bin"),
        _complextypes(GOLD_D), masshunter.count_scans(acqdata))
    assert len(records) == 3
    times = [r['ScanTime'] for r in records]
    assert all(t2 >= t1 for t1, t2 in zip(times, times[1:]))


def test_stride_inferred_without_msts():
    """ The two-block stride is recovered from the record geometry alone -
    i.e. parsing still finds all four records if MSTS.xml is unavailable. """
    acqdata = _acqdata(COPPER_D)
    records = masshunter.read_scan_records(
        os.path.join(acqdata, "MSScan.bin"),
        _complextypes(COPPER_D), None)
    assert len(records) == 4


@pytest.mark.skipif(
    not HAVE_LZF, reason="python-lzf required to decode LZF MSProfile.bin")
def test_gold_parses_with_default_masscal():
    """ gold parses end to end to a profile grid with a sensible TOF m/z
    axis, calibrated from DefaultMassCal.xml (no MSMassCal.bin). """
    datafile = masshunter.parse_allfiles(
        GOLD_D, hrms=True, bin_width=0.0001)[0]
    assert datafile.data.shape[0] == 3               # 3 scans
    assert datafile.xlabels.size == 3
    assert datafile.data.shape[1] == datafile.ylabels.size
    assert datafile.ylabels.min() > 50
    assert datafile.ylabels.max() < 2000
    assert (datafile.ylabels[1:] > datafile.ylabels[:-1]).all()


def test_default_masscal_row_matches_msmasscal():
    """ A DefaultMassCal.xml row reproduces the per-scan MSMassCal.bin row a
    fixture with both stores, confirming it is a faithful stand-in. """
    acqdata = os.path.join(MAGENTA_D, "AcqData")
    rows = masshunter.read_default_masscal_rows(
        os.path.join(acqdata, "DefaultMassCal.xml"))
    records = masshunter.read_scan_records(
        os.path.join(acqdata, "MSScan.bin"),
        masshunter.parse_scan_xsd(os.path.join(acqdata, "MSScan.xsd")))
    with open(os.path.join(acqdata, "MSMassCal.bin"), 'rb') as f:
        per_scan = np.ndarray(
            (len(records), 10), '<d', f.read()[0x4c:], 0, (84, 8))
    calib_id = records[0].get('CalibrationID')
    # The per-scan refinement is sub-ppm; everything else matches exactly.
    np.testing.assert_allclose(
        rows[calib_id], per_scan[0], rtol=0, atol=1e-6)


@pytest.mark.skipif(
    not HAVE_LZF, reason="python-lzf required to decode LZF MSProfile.bin")
def test_incomplete_acquisition_keeps_complete_scans():
    """ copper's MSScan.bin describes four scans but MSProfile.bin holds
    only three; parsing keeps the three complete scans rather than failing
    on the truncated segment. """
    datafile = masshunter.parse_allfiles(
        COPPER_D, hrms=True, bin_width=0.0001)[0]
    assert datafile.data.shape[0] == 3
    assert datafile.xlabels.size == 3


# ---------------------------------------------------------------------------
# Parsing centroided MS data from MSPeak.bin - the opt-in counterpart to
# the MSProfile.bin profile spectrum (centroid=True).
#
# MSPeak.bin is uncompressed, so these run without python-lzf. They cover a
# GC-quadrupole acquisition whose MSPeak.bin already stores m/z (yellow), a
# Q-TOF acquisition whose centroid axis is time-of-flight and is calibrated
# like the profile (gold), the centroid=True flag, and the discoverability
# metadata note.
# ---------------------------------------------------------------------------

def test_select_centroid_block():
    """ On a scan that stores both, the centroid (fixed-width peak) block is
    chosen over the compressed profile block. """
    acqdata = os.path.join(GOLD_D, "AcqData")
    complextypes = masshunter.parse_scan_xsd(
        os.path.join(acqdata, "MSScan.xsd"))
    records = masshunter.read_scan_records(
        os.path.join(acqdata, "MSScan.bin"), complextypes,
        masshunter.count_scans(acqdata))
    blocks = records[0]['SpectrumParamsBlocks']
    assert len(blocks) == 2  # profile block + centroid block
    chosen = masshunter._select_centroid_block(blocks)
    assert chosen is not None
    assert chosen['ByteCount'] // chosen['PointCount'] in (8, 12, 16)


def test_yellow_centroid_axis_matches_data_ms():
    """ The GC-quadrupole MSPeak.bin m/z axis, binned to nominal mass, matches
    the independent data.ms axis for the same acquisition. """
    centroid = masshunter.parse_mspeakdata(YELLOW_ACQDATA, bin_width=1.0)
    assert centroid.name == "MSPeak.bin"
    assert centroid.detector == "MS"
    assert centroid.data.shape[0] == centroid.xlabels.size
    assert centroid.data.shape[1] == centroid.ylabels.size
    assert (centroid.ylabels[1:] > centroid.ylabels[:-1]).all()

    data_ms = rb.read("tests/inputs/yellow.D").get_file("data.ms")
    np.testing.assert_array_equal(centroid.ylabels, data_ms.ylabels)


def test_gold_centroid_is_calibrated():
    """ A TOF centroid axis is stored as time-of-flight; parsing calibrates each
    scan's peaks to real m/z (within the profile's m/z range, not raw flight
    time). """
    centroid = masshunter.parse_mspeakdata(os.path.join(GOLD_D, "AcqData"))
    assert isinstance(centroid, masshunter.CentroidDataFile)
    mz, _ = centroid.scan(0)
    assert mz.size > 0
    assert mz.min() > 50 and mz.max() < 1100


def test_centroid_bin_width_toggles_binning():
    """ Centroids mirror the profile: per-scan by default, a shared-grid
    DataFile when a bin_width is given. """
    acqdata = os.path.join(GOLD_D, "AcqData")
    per_scan = masshunter.parse_mspeakdata(acqdata)
    assert isinstance(per_scan, masshunter.CentroidDataFile)
    with pytest.raises(AttributeError):
        per_scan.ylabels
    grid = masshunter.parse_mspeakdata(acqdata, bin_width=0.01)
    assert isinstance(grid, masshunter.DataFile)
    assert not isinstance(grid, masshunter.CentroidDataFile)
    assert grid.ylabels.size > 0


def test_centroid_flag_end_to_end():
    """ centroid=True adds the MSPeak.bin DataFile; by default it is not
    parsed but a metadata note advertises that it is available. """
    default = rb.read("tests/inputs/yellow.D")
    assert "MSPeak.bin" not in [df.name for df in default.datafiles]
    assert default.metadata.get("centroid_available")

    with_centroid = rb.read("tests/inputs/yellow.D", centroid=True)
    assert "MSPeak.bin" in [df.name for df in with_centroid.datafiles]
    # data.ms is untouched - centroid is additive, not a replacement.
    assert "data.ms" in [df.name for df in with_centroid.datafiles]
    assert "centroid_available" not in with_centroid.metadata


def test_read_metadata_locates_masshunter_datafiles():
    """ read_metadata routes a MassHunter .D to its AcqData binaries instead of
    returning an empty datafile list (the Chemstation .uv/.ch/.ms scan never
    finds them). It reports the bin names plus the flags needed to read them,
    without parsing the binaries. """
    # gold.D carries both a profile spectrum and a peak-picked centroid list.
    both = rb.read_metadata(GOLD_D)
    assert both["datafiles"] == ["MSProfile.bin", "MSPeak.bin"]
    assert both["metadata"].get("hrms_available")
    assert both["metadata"].get("centroid_available")

    # amber.D has only MSProfile.bin, so no centroid is advertised.
    profile_only = rb.read_metadata(AMBER_D)
    assert profile_only["datafiles"] == ["MSProfile.bin"]
    assert profile_only["metadata"].get("hrms_available")
    assert "centroid_available" not in profile_only["metadata"]


def test_read_metadata_reports_dad_files():
    """ A DAD run's files are reported too. read() returns them with no flag
    set, so a run holding them must not come back as MS-only - nor, when it has
    no MS data at all, as nothing. """
    dad_only = rb.read_metadata(BRONZE_D)
    assert dad_only["datafiles"] == ["DAD1.cg", "DAD1.sp"]
    assert "hrms_available" not in dad_only["metadata"]

    with tempfile.TemporaryDirectory() as tmp:
        # Give a MassHunter MS run a DAD alongside it: both must be reported.
        combined = os.path.join(tmp, "combined.D")
        shutil.copytree(GOLD_D, combined)
        for name in ("DAD1.cd", "DAD1.cg", "DAD1.sd", "DAD1.sp"):
            shutil.copy(os.path.join(BRONZE_ACQDATA, name),
                        os.path.join(combined, "AcqData", name))
        both = rb.read_metadata(combined)
        assert both["datafiles"] == [
            "DAD1.cg", "DAD1.sp", "MSProfile.bin", "MSPeak.bin"]
        assert both["metadata"].get("centroid_available")


def test_hrms_flag_advertises_profile():
    """ hrms=True adds the MSProfile.bin DataFile; by default it is not parsed
    but a metadata note advertises that profile/HRMS data is available (mirrors
    centroid_available). amber.D is run-length encoded, so no python-lzf. """
    default = rb.read(AMBER_D)
    assert "MSProfile.bin" not in [df.name for df in default.datafiles]
    assert default.metadata.get("hrms_available")

    with_hrms = rb.read(AMBER_D, hrms=True)
    assert "MSProfile.bin" in [df.name for df in with_hrms.datafiles]
    assert "hrms_available" not in with_hrms.metadata


def test_centroid_truncation_is_graceful():
    """ A truncated MSPeak.bin segment is skipped rather than crashing. """
    centroid = masshunter.parse_mspeakdata(os.path.join(COPPER_D, "AcqData"))
    assert centroid.name == "MSPeak.bin"
    assert centroid.xlabels.size >= 3


# ---------------------------------------------------------------------------
# display_precision='auto', bin_width, the per-scan default, and the error surface
# (1.3). precision is a label precision (decimals), bin_width is the shared-grid
# bin width in daltons; the two are independent. The HRMS default is per-scan.
# ---------------------------------------------------------------------------

def test_precision_auto_profile_is_four_decimals():
    """ 'auto' display_precision rounds HRMS profile labels to 4 decimals (not
    nominal mass), on the shared grid. """
    prof = rb.read(MAGENTA_D, hrms=True,
                   bin_width=0.0001).get_file("MSProfile.bin")
    yl = prof.ylabels
    assert np.allclose(yl, np.round(yl, 4))
    assert not np.allclose(yl, np.round(yl))      # genuinely sub-integer


def test_precision_explicit_overrides_auto():
    """ An explicit integer overrides the 'auto' default (labels only; the grid
    is the separate bin_width). """
    prof = rb.read(MAGENTA_D, hrms=True, display_precision=1,
                   bin_width=0.1).get_file("MSProfile.bin")
    assert np.allclose(prof.ylabels, np.round(prof.ylabels, 1))


def test_precision_auto_gc_centroid_is_integer():
    """ GC-quadrupole centroids (no calibration) auto-resolve to whole numbers
    on each scan's per-scan m/z axis. """
    dd = rb.read("tests/inputs/yellow.D", centroid=True)
    cen = dd.get_file("MSPeak.bin")
    mz = cen.mass_labels(0)
    assert mz.size > 0
    assert np.array_equal(mz, np.round(mz))


def test_bin_width_presence_toggles_binning():
    """ bin_width is the only binning switch: omit it for the per-scan list,
    pass a width for the single shared-grid DataFile. """
    acqdata = os.path.join(MAGENTA_D, "AcqData")
    per_scan = masshunter.parse_msdata(acqdata)
    assert isinstance(per_scan, list)
    assert all(isinstance(p, masshunter.ProfileDataFile) for p in per_scan)
    grid = masshunter.parse_msdata(acqdata, bin_width=0.01)
    assert isinstance(grid, masshunter.DataFile)
    assert not isinstance(grid, masshunter.ProfileDataFile)


def test_precision_does_not_affect_the_grid():
    """ At a fixed bin_width, precision changes only the label rounding, never
    which scans share a column: the data and (here) the labels are identical. """
    fine = rb.read(MAGENTA_D, hrms=True, display_precision=4,
                   bin_width=0.01).get_file("MSProfile.bin")
    coarse = rb.read(MAGENTA_D, hrms=True, display_precision=2,
                     bin_width=0.01).get_file("MSProfile.bin")
    assert np.array_equal(fine.data, coarse.data)
    assert np.array_equal(fine.ylabels, coarse.ylabels)


def test_bin_width_decouples_from_precision():
    """ At the same label precision, a coarser bin_width yields fewer columns. """
    fine = rb.read(MAGENTA_D, hrms=True, display_precision=2,
                   bin_width=0.01).get_file("MSProfile.bin")
    coarse = rb.read(MAGENTA_D, hrms=True, display_precision=2,
                     bin_width=0.1).get_file("MSProfile.bin")
    assert coarse.ylabels.size < fine.ylabels.size


def test_bin_width_finer_than_labels_still_labels_every_bin():
    """ display_precision and bin_width are independent, so a bin_width finer
    than the labels is allowed. Display rounding is documented as cosmetic, so
    it is raised to the decimals the grid needs rather than rounding
    neighbouring bins onto one label: a label that named several columns would
    make extract_traces return part of the signal at that m/z and to_csvstr
    repeat a header. """
    out = rb.read(MAGENTA_D, hrms=True, display_precision=2, bin_width=0.001)
    labels = out.get_file("MSProfile.bin").ylabels
    assert labels.size > 0
    assert np.unique(labels).size == labels.size


def test_bin_width_finer_than_labels_still_labels_every_bin_direct():
    """ The same holds at the direct (non-rb.read) entry point. """
    acqdata = os.path.join(MAGENTA_D, "AcqData")
    out = masshunter.parse_msdata(acqdata, display_precision=2, bin_width=0.001)
    assert np.unique(out.ylabels).size == out.ylabels.size


def test_bin_width_invalid_value_rejected():
    with pytest.raises(Exception, match="Invalid bin_width"):
        rb.read(MAGENTA_D, hrms=True, bin_width=0)


def test_profile_shared_axis_ops_raise_with_pointer():
    """ The per-scan profile has no shared m/z axis, so ylabels and the DataFile
    operations that need one raise, pointing at scan(i)/mass_labels(i) and the
    documentation. """
    prof = rb.read(MAGENTA_D, hrms=True).get_file("MSProfile.bin")
    assert isinstance(prof, masshunter.ProfileDataFile)
    ops = [lambda: prof.ylabels,
           lambda: prof.extract_traces(),
           lambda: prof.to_csvstr(),
           lambda: prof.export_csv("unused.csv"),
           lambda: prof.plot(100.0)]
    for op in ops:
        with pytest.raises(AttributeError, match="readthedocs"):
            op()


def test_precision_rejects_bool():
    """ bool is not a valid precision even though it is an int subclass. """
    with pytest.raises(Exception, match="Invalid display_precision"):
        rb.read(MAGENTA_D, hrms=True, display_precision=True)


def test_precision_auto_tof_centroid_is_four_decimals():
    """ A TOF-calibrated centroid (gold.D) auto-resolves to 4 decimals, unlike
    the unit-resolution GC centroid that resolves to whole numbers. """
    centroid = masshunter.parse_mspeakdata(os.path.join(GOLD_D, "AcqData"))
    mz = centroid.mass_labels(0)
    assert mz.size > 0
    assert np.allclose(mz, np.round(mz, 4))
    assert not np.array_equal(mz, np.round(mz))   # genuinely sub-integer


def test_mass_labels_are_per_scan_and_drift():
    """ Each scan's m/z is its own: mass_labels(i) is exactly scan(i)'s axis, and
    the same column j carries a different m/z in different scans (drift). """
    profile = rb.read(CYAN_D, hrms=True).get_file("MSProfile.bin")
    num_scans, k = profile.data.shape
    for i in (0, num_scans - 1):
        mz, _ = profile.scan(i)
        np.testing.assert_array_equal(profile.mass_labels(i), mz)
    j = k // 2
    first = profile.mass_labels(0)[j]
    last = profile.mass_labels(num_scans - 1)[j]
    assert first != last                          # the column drifts across scans


def test_flight_times_axis_is_shared_and_monotonic():
    """ tof is the one flight-time axis shared by every scan: it indexes the
    columns and is strictly increasing. """
    profile = rb.read(CYAN_D, hrms=True).get_file("MSProfile.bin")
    assert profile.flight_times.size == profile.data.shape[1]
    assert (profile.flight_times[1:] > profile.flight_times[:-1]).all()


def test_amber_is_a_long_windowed_run():
    """ amber.D is the many-scan fixture: 500 scans over a narrow m/z window, with
    per-scan drift accumulating across the run (more than a fine bin). """
    profile = rb.read(AMBER_D, hrms=True).get_file("MSProfile.bin")
    n, k = profile.data.shape
    assert n == 500
    mz0 = profile.mass_labels(0)
    assert 823 < mz0.min() and mz0.max() < 828        # windowed in m/z
    drift = float(np.median(np.abs(profile.mass_labels(n - 1) - mz0)))
    assert drift > 0.002                               # drifts across the run
    # It bins like any profile: a fine grid leaves zeros, a coarse grid does not.
    fine = rb.read(AMBER_D, hrms=True, bin_width=0.005).get_file("MSProfile.bin")
    coarse = rb.read(AMBER_D, hrms=True, bin_width=0.5).get_file("MSProfile.bin")
    assert (fine.data == 0).mean() > 0.3
    assert (coarse.data == 0).mean() == 0


@pytest.mark.parametrize("bin_width", [0.0001, 0.01])
def test_binned_grid_has_no_all_zero_columns(bin_width):
    """ Every column of the shared grid is a bin some scan actually filled, so no
    column is all zeros. This holds on a fine grid (the sparse code path, which
    must drop bins that hold only zero-intensity points) and on a coarser grid
    (the dense path). """
    binned = rb.read(CYAN_D, hrms=True, bin_width=bin_width)
    data = binned.get_file("MSProfile.bin").data
    assert data.shape[1] > 0
    assert (data.sum(axis=0) == 0).sum() == 0


# display_precision='auto' resolves to 0 (whole-number m/z labels) for the
# unit-resolution, non-HRMS parsers. Each test reads with the default precision
# and checks the per-array mass labels equal their rounded-to-integer values.

def test_icpms_auto_precision_is_whole_numbers():
    """ ICP-MS isotope channels are unit-resolution, so the default precision
    yields whole-number m/z labels. """
    datafile = masshunter.parse_icpmsdata(SILVER_ACQDATA)
    ylabels = datafile.ylabels
    assert ylabels.size > 0
    np.testing.assert_array_equal(ylabels, np.round(ylabels))


@pytest.mark.parametrize(
    "path", WATERS_MS_RAW,
    ids=[os.path.basename(p) for p in WATERS_MS_RAW])
def test_waters_auto_precision_is_whole_numbers(path):
    """ Waters quadrupole MS m/z axes are unit-resolution, so the default
    precision yields whole-number m/z labels. """
    datadir = rb.read(path)
    ms_files = [datafile for datafile in datadir.datafiles
                if datafile.detector == 'MS']
    assert ms_files
    for datafile in ms_files:
        ylabels = datafile.ylabels
        assert ylabels.size > 0
        np.testing.assert_array_equal(ylabels, np.round(ylabels))


# ---------------------------------------------------------------------------
# MassHunter DAD (.cd/.cg/.sd/.sp).
#
# A MassHunter DAD writes the same two views the Chemstation format splits into
# .ch and .uv files, but in its own binary family: a descriptor indexing a data
# file, twice over. `bronze` is a four-retention-time slice of a real QQQ+DAD
# acquisition, keeping all five absorbance signals, the three telemetry traces,
# and the full 190-550 nm axis. Its telemetry traces deliberately keep a
# different point count (8) from its absorbance signals (4), as they do on the
# instrument, so the per-signal geometry is exercised rather than assumed.
# ---------------------------------------------------------------------------

BRONZE_D = os.path.join("tests", "inputs", "bronze.D")
BRONZE_ACQDATA = os.path.join(BRONZE_D, "AcqData")


def test_dad_signals_are_described():
    """ The .cd descriptor names every signal and locates its data in the .cg. """
    signals = masshunter.read_dad_signals(
        os.path.join(BRONZE_ACQDATA, "DAD1.cd"))
    assert len(signals) == 8
    assert [s['letter'] for s in signals] == list("ABCDEIJK")

    absorbance = [s for s in signals if s['description'].startswith('Sig=')]
    assert len(absorbance) == 5
    assert all(s['unit'] == 'mAU' for s in absorbance)
    assert absorbance[0]['description'].startswith('Sig=254.0')

    # The telemetry traces carry their own units - which are UTF-8, not ASCII -
    # and are sampled at their own rate.
    telemetry = [s for s in signals if not s['description'].startswith('Sig=')]
    assert [s['description'] for s in telemetry] == [
        "Board Temperature", "Optical Unit Temperature", "UV Lamp Anode Voltage"]
    assert [s['unit'] for s in telemetry] == ["\N{DEGREE SIGN}C",
                                              "\N{DEGREE SIGN}C", "V"]
    assert {s['num_times'] for s in telemetry} != {
        s['num_times'] for s in absorbance}


def test_dad_chromatograms_are_named_per_signal():
    """ Each signal becomes its own DataFile, named the Chemstation way. """
    datadir = rb.read(BRONZE_D)
    names = [df.name for df in datadir.datafiles]
    assert names[:5] == ["DAD1A.cg", "DAD1B.cg", "DAD1C.cg",
                         "DAD1D.cg", "DAD1E.cg"]
    for name, wavelength in zip(names, (254, 210, 280, 400, 260)):
        datafile = datadir.get_file(name)
        assert datafile.detector == 'UV'
        assert datafile.data.shape == (4, 1)
        assert datafile.ylabels[0] == wavelength


def test_dad_spectra_form_one_grid():
    """ The .sp spectra land on the single wavelength axis the .sd describes. """
    datadir = rb.read(BRONZE_D)
    spectra = datadir.get_file("DAD1.sp")
    assert spectra.detector == 'UV'
    assert spectra.data.shape == (4, 181)
    assert spectra.ylabels[0] == 190
    assert spectra.ylabels[-1] == 550
    np.testing.assert_allclose(np.diff(spectra.ylabels), 2)
    # Retention times are minutes, ascending, and shared with the chromatograms.
    assert (spectra.xlabels[1:] > spectra.xlabels[:-1]).all()
    np.testing.assert_allclose(
        spectra.xlabels, datadir.get_file("DAD1A.cg").xlabels)


def test_dad_spectra_agree_with_chromatograms():
    """ The two views encode the same measurement, so a signal's chromatogram
    is reproduced by the spectra over that signal's band.

    A signal is a centre wavelength and a bandwidth ("Sig=400.0,4.0" is 400 nm
    over 4 nm), so the comparison averages the spectra across the band rather
    than reading a single column.

    400 nm is the case this can be asserted on: it is the one signal acquired
    Ref=off, so its chromatogram is the band alone. The others subtract a
    reference band, and reproducing Agilent's exact weighting is out of scope
    here - averaging the reference band accounts for most of the difference but
    not all of it, so those signals are only checked for the shared time axis
    and a plausible absorbance scale. """
    datadir = rb.read(BRONZE_D)
    spectra = datadir.get_file("DAD1.sp")
    wavelengths = np.asarray(spectra.ylabels, dtype=float)

    def band(centre, width=4.0):
        columns = np.abs(wavelengths - centre) <= width / 2
        return spectra.data[:, columns].mean(axis=1)

    unreferenced = datadir.get_file("DAD1D.cg")     # Sig=400.0, Ref=off
    np.testing.assert_allclose(unreferenced.data[:, 0], band(400), atol=5e-3)

    for name, centre in (("DAD1A.cg", 254), ("DAD1B.cg", 210)):
        chromatogram = datadir.get_file(name).data[:, 0]
        assert chromatogram.shape == (4,)
        # Same units and order of magnitude as the band it is drawn from.
        assert np.abs(chromatogram - band(centre)).max() < 1.0


def test_dad_telemetry_is_opt_in_and_analog():
    """ The detector's telemetry traces are parsed only on request, and land in
    `analog` rather than among the detector signals. """
    default = rb.read(BRONZE_D)
    assert default.analog == []
    assert len(default.datafiles) == 6

    with_telemetry = rb.read(BRONZE_D, telemetry=True)
    assert len(with_telemetry.datafiles) == 6      # unchanged: additive
    assert [df.name for df in with_telemetry.analog] == [
        "DAD1I.cg", "DAD1J.cg", "DAD1K.cg"]
    for datafile in with_telemetry.analog:
        assert datafile.detector is None
        # Sampled at their own rate, not the absorbance signals'.
        assert datafile.data.shape == (8, 1)


def test_dad_fixture_keeps_the_real_signal_kinds():
    """ A .cd record marks a signal 1 for absorbance and 2 for telemetry. The
    parser separates the two by unit instead, so nothing here reads the field -
    but the fixture is only useful as evidence if it still says what the
    instrument said. """
    with open(os.path.join(BRONZE_ACQDATA, "DAD1.cd"), 'rb') as f:
        raw = f.read()
    absorbance = [0x71, 0xde, 0x14b, 0x1b0, 0x21d]
    telemetry = [0x27e, 0x2e6, 0x34b]
    for offset in absorbance:
        assert struct.unpack_from('<I', raw, offset)[0] == 1
    for offset in telemetry:
        assert struct.unpack_from('<I', raw, offset)[0] == 2


def test_dad_parses_without_the_ms_flags():
    """ DAD data is parsed unconditionally, as the Chemstation UV formats are -
    a .d holding only DAD data still reads as UV with no flags set. """
    datadir = rb.read(BRONZE_D)
    assert datadir.detectors == {'UV'}
    assert len(datadir.by_detector['UV']) == 6


def test_dad_rejects_a_foreign_file():
    """ The type tag in the shared header identifies which member a file is, so
    a mismatched one is declined rather than misread. """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = os.path.join(tmp, "fake.D", "AcqData")
        os.makedirs(acqdata)
        # The .sp content under a .cd name: right family, wrong member.
        shutil.copy(os.path.join(BRONZE_ACQDATA, "DAD1.sp"),
                    os.path.join(acqdata, "DAD1.cd"))
        assert masshunter.read_dad_signals(
            os.path.join(acqdata, "DAD1.cd")) == []


def test_dad_varying_wavelength_axis_is_declined():
    """ Spectra that do not share one wavelength axis cannot form a dense grid,
    so they are declined with a warning instead of being reshaped. """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = os.path.join(tmp, "AcqData")
        shutil.copytree(BRONZE_ACQDATA, acqdata)
        desc_path = os.path.join(acqdata, "DAD1.sd")
        with open(desc_path, 'rb') as descriptor:
            desc = bytearray(descriptor.read())
        data_offset = struct.unpack_from('<I', desc, 0x4c)[0]
        # Give the second spectrum a different wavelength count.
        struct.pack_into('<I', desc, data_offset + 80 + 44, 180)
        with open(desc_path, 'wb') as descriptor:
            descriptor.write(bytes(desc))

        with pytest.warns(UserWarning, match="wavelength axis changes"):
            spectra = masshunter.parse_dadspectra(
                os.path.join(acqdata, "DAD1.sp"), desc_path)
        assert spectra is None


def test_dad_honors_requested_files():
    """ requested_files narrows the DAD parse as it does the Chemstation one -
    by the per-signal name, or by the file the signals share. """
    one_signal = rb.read(BRONZE_D, requested_files=["DAD1B.cg"])
    assert [df.name for df in one_signal.datafiles] == ["DAD1B.cg"]

    spectra_only = rb.read(BRONZE_D, requested_files=["DAD1.sp"])
    assert [df.name for df in spectra_only.datafiles] == ["DAD1.sp"]

    # The shared filename selects every signal it holds, but not the spectra.
    every_signal = rb.read(BRONZE_D, requested_files=["DAD1.cg"])
    assert [df.name for df in every_signal.datafiles] == [
        "DAD1A.cg", "DAD1B.cg", "DAD1C.cg", "DAD1D.cg", "DAD1E.cg"]

    assert rb.read(BRONZE_D, requested_files=["nothing.cg"]).datafiles == []
    # A name that merely resembles a real one is not a request for it: there is
    # no DAD1A.sp, so asking for one yields nothing.
    assert rb.read(BRONZE_D, requested_files=["DAD1A.sp"]).datafiles == []
    assert rb.read(BRONZE_D, requested_files=["DAD1.sd"]).datafiles == []


def test_dad_telemetry_can_be_requested_by_name():
    """ Naming a telemetry trace parses it whether or not the flag is set, as
    it does for .dx telemetry. """
    datadir = rb.read(BRONZE_D, requested_files=["DAD1I.cg"])
    assert [df.name for df in datadir.analog] == ["DAD1I.cg"]
    assert datadir.datafiles == []


def _bronze_copy(tmp):
    """ A writable copy of the bronze AcqData, for corrupting. """
    acqdata = os.path.join(tmp, "AcqData")
    shutil.copytree(BRONZE_ACQDATA, acqdata)
    return acqdata


def _patch(path, offset, value, fmt='<I'):
    with open(path, 'rb') as f:
        raw = bytearray(f.read())
    struct.pack_into(fmt, raw, offset, value)
    with open(path, 'wb') as f:
        f.write(bytes(raw))


def test_dad_short_descriptor_is_declined():
    """ A truncated .cd yields no signals rather than a partial parse. """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = _bronze_copy(tmp)
        path = os.path.join(acqdata, "DAD1.cd")
        with open(path, 'rb') as f:
            head = f.read(0x50)
        with open(path, 'wb') as f:
            f.write(head)
        with pytest.warns(UserWarning, match="too short to hold"):
            assert masshunter.read_dad_signals(path) == []


def test_dad_missing_signals_are_reported():
    """ Reading fewer signals than the descriptor declares is warned about,
    not returned silently as a short list. """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = _bronze_copy(tmp)
        path = os.path.join(acqdata, "DAD1.cd")
        _patch(path, 0x4c, 9)          # claim one more signal than exists
        with pytest.warns(UserWarning, match="describes 9 signals but only 8"):
            signals = masshunter.read_dad_signals(path)
        assert len(signals) == 8


def _synthetic_cd(acqdata, signals):
    """ Writes a minimal .cd/.cg pair, one record per (letter, description,
    unit, num_times), and returns the .cg's size. The real fixture carries its
    only one-letter unit in its last record, where nothing can be lost behind
    it. """
    descriptor = bytearray(80)
    struct.pack_into('<H', descriptor, 0, 0x0200)
    struct.pack_into('<I', descriptor, 0x4c, len(signals))

    chromatograms = bytearray(68)
    offsets = []
    for _, _, _, num_times in signals:
        offsets.append(len(chromatograms))
        chromatograms += struct.pack('<dd', 0.0, 0.01) + b'\x00' * num_times * 8

    def pascal(text):
        encoded = text.encode('utf-8')
        return bytes([len(encoded)]) + encoded

    for (letter, description, unit, num_times), offset in zip(signals, offsets):
        descriptor += pascal(letter) + pascal(description)
        descriptor += struct.pack('<IIII', 1, offset, 0, num_times)
        descriptor += b'\x00' * 8 + pascal(unit)

    with open(os.path.join(acqdata, "DAD1.cd"), 'wb') as f:
        f.write(descriptor)
    with open(os.path.join(acqdata, "DAD1.cg"), 'wb') as f:
        f.write(chromatograms)
    return len(chromatograms)


def test_dad_one_letter_unit_does_not_split_a_record():
    """ A single-uppercase-letter unit ("V") has the same byte shape as a
    record's leading letter. Put one on a middle record, where mistaking it for
    a boundary would cost the record behind it. """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = os.path.join(tmp, "synthetic.D", "AcqData")
        os.makedirs(acqdata)
        size = _synthetic_cd(acqdata, [
            ("A", "Sig=254.0,4.0  Ref=360.0,100.0", "mAU", 10),
            ("B", " UV Lamp Anode Voltage", "V", 40),
            ("C", "Sig=210.0,4.0  Ref=360.0,100.0", "mAU", 10)])
        signals = masshunter.read_dad_signals(
            os.path.join(acqdata, "DAD1.cd"), size)

    assert [s['letter'] for s in signals] == ["A", "B", "C"]
    assert [s['unit'] for s in signals] == ["mAU", "V", "mAU"]
    assert [s['num_times'] for s in signals] == [10, 40, 10]


def test_dad_records_are_bounded_by_the_chromatogram_file():
    """ Every record indexes data inside the .cg, so requiring it to fit rules
    out a coincidental byte pattern: text read as a field gives implausibly
    large numbers. """
    record = (b"\x01A\x1eSig=254.0,4.0  Ref=360.0,100.0"
              + struct.pack('<IIII', 1, 68, 0, 10))
    assert masshunter._read_record_header(record, 0, 68 + 16 + 10 * 8)
    assert masshunter._read_record_header(record, 0, 100) is None
    # The bound leaves the real fixture untouched.
    signals = masshunter.read_dad_signals(
        os.path.join(BRONZE_ACQDATA, "DAD1.cd"),
        os.path.getsize(os.path.join(BRONZE_ACQDATA, "DAD1.cg")))
    assert [s['letter'] for s in signals] == list("ABCDEIJK")
    assert signals[-1]['unit'] == "V"


def test_dad_descriptor_pointing_outside_the_file_is_declined():
    """ A spectrum offset past the end of the .sp is refused, not read. """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = _bronze_copy(tmp)
        desc_path = os.path.join(acqdata, "DAD1.sd")
        data_offset = 164
        _patch(desc_path, data_offset + 32, 10 ** 7)    # first spectrum offset
        with pytest.warns(UserWarning, match="outside the file"):
            assert masshunter.parse_dadspectra(
                os.path.join(acqdata, "DAD1.sp"), desc_path) is None


def test_dad_zero_wavelengths_is_declined():
    """ A descriptor reporting no wavelengths is refused with a warning. """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = _bronze_copy(tmp)
        desc_path = os.path.join(acqdata, "DAD1.sd")
        for i in range(4):
            _patch(desc_path, 164 + i * 80 + 44, 0)
        with pytest.warns(UserWarning, match="0 wavelengths"):
            assert masshunter.parse_dadspectra(
                os.path.join(acqdata, "DAD1.sp"), desc_path) is None


def test_dad_axis_disagreement_is_declined():
    """ The wavelength axis is stated in both the .sp and the .sd, so the two
    are checked against each other. """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = _bronze_copy(tmp)
        spectra_path = os.path.join(acqdata, "DAD1.sp")
        # Move every spectrum's start together, so the axes still agree with
        # each other and only the descriptor is left contradicting them.
        for i in range(4):
            _patch(spectra_path, 68 + i * 1464, 900.0, '<d')
        with pytest.warns(UserWarning, match="but its descriptor says"):
            assert masshunter.parse_dadspectra(
                spectra_path, os.path.join(acqdata, "DAD1.sd")) is None


def test_dad_axis_changing_mid_run_is_declined():
    """ Each spectrum states its own axis, so a run that changes it partway
    yields rows that share no grid. Every spectrum is checked, not just the
    first. """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = _bronze_copy(tmp)
        spectra_path = os.path.join(acqdata, "DAD1.sp")
        _patch(spectra_path, 68 + 2 * 1464, 400.0, '<d')    # the third one
        with pytest.warns(UserWarning, match="share one wavelength axis"):
            assert masshunter.parse_dadspectra(
                spectra_path, os.path.join(acqdata, "DAD1.sd")) is None


def test_dad_padded_spectrum_records_are_read():
    """ A descriptor may give a record length longer than the values it holds,
    which only means the record is padded. Reading is driven by the wavelength
    count, so such a file parses rather than being declined. """
    reference = rb.read(BRONZE_D).get_file("DAD1.sp")
    pad = 8
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = _bronze_copy(tmp)
        spectra_path = os.path.join(acqdata, "DAD1.sp")
        desc_path = os.path.join(acqdata, "DAD1.sd")

        with open(spectra_path, 'rb') as f:
            raw = f.read()
        stride = 1464
        rebuilt = bytearray(raw[:68])
        for i in range(4):
            rebuilt += raw[68 + i * stride:68 + (i + 1) * stride] + b'\x00' * pad
        with open(spectra_path, 'wb') as f:
            f.write(rebuilt)
        for i in range(4):
            _patch(desc_path, 164 + i * 80 + 32, 68 + i * (stride + pad))
            _patch(desc_path, 164 + i * 80 + 40, stride + pad)

        parsed = masshunter.parse_dadspectra(spectra_path, desc_path)
        assert parsed is not None
        assert np.array_equal(parsed.data, reference.data)


def test_dad_short_spectrum_records_are_declined():
    """ A record shorter than its wavelength count would be read past its end,
    so it is refused rather than trusted. """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = _bronze_copy(tmp)
        desc_path = os.path.join(acqdata, "DAD1.sd")
        for i in range(4):
            _patch(desc_path, 164 + i * 80 + 40, 1000)
        with pytest.warns(UserWarning, match="shorter than"):
            assert masshunter.parse_dadspectra(
                os.path.join(acqdata, "DAD1.sp"), desc_path) is None


def test_dad_single_spectrum_is_writeable():
    """ One spectrum needs no restriding, so the returned array must still be a
    copy rather than a view onto the read-only file buffer. """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = _bronze_copy(tmp)
        _patch(os.path.join(acqdata, "DAD1.sd"), 0x50, 1)   # one record
        parsed = masshunter.parse_dadspectra(
            os.path.join(acqdata, "DAD1.sp"), os.path.join(acqdata, "DAD1.sd"))
        assert parsed.data.shape == (1, 181)
        parsed.data[0, 0] = 1.0


def test_dad_non_contiguous_spectra_are_read():
    """ Spectra are located through the descriptor, so they need not be evenly
    spaced in the .sp. Rebuild one with a gap between every spectrum. """
    reference = rb.read(BRONZE_D).get_file("DAD1.sp")
    gap = 7
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = _bronze_copy(tmp)
        spectra_path = os.path.join(acqdata, "DAD1.sp")
        desc_path = os.path.join(acqdata, "DAD1.sd")

        with open(spectra_path, 'rb') as f:
            raw = f.read()
        stride = 16 + 181 * 8
        spread = bytearray(raw[:68])
        offsets = []
        for i in range(4):
            offsets.append(68 + len(spread) - 68)
            spread += raw[68 + i * stride: 68 + (i + 1) * stride]
            spread += b"\x00" * gap
        with open(spectra_path, 'wb') as f:
            f.write(bytes(spread))
        for i, offset in enumerate(offsets):
            _patch(desc_path, 164 + i * 80 + 32, offset)

        spectra = masshunter.parse_dadspectra(spectra_path, desc_path)
        assert spectra is not None
        np.testing.assert_array_equal(spectra.data, reference.data)
        np.testing.assert_array_equal(spectra.ylabels, reference.ylabels)


def test_dad_accepts_other_detector_stems():
    """ A multi- or variable-wavelength detector writes the same family under
    its own name, so the parse is not tied to "DAD". """
    with tempfile.TemporaryDirectory() as tmp:
        acqdata = os.path.join(tmp, "AcqData")
        os.makedirs(acqdata)
        for ext in (".cd", ".cg", ".sd", ".sp"):
            shutil.copy(os.path.join(BRONZE_ACQDATA, "DAD1" + ext),
                        os.path.join(acqdata, "MWD1" + ext))
        datafiles = masshunter.parse_dadfiles(acqdata)
        assert [df.name for df in datafiles] == [
            "MWD1A.cg", "MWD1B.cg", "MWD1C.cg", "MWD1D.cg", "MWD1E.cg",
            "MWD1.sp"]
# mz_resolution inspects the m/z grid the binary records, independent of
# the nominal-mass default, so a user can tell how fine a bin_width is worth it.

def test_mz_resolution_agilent_quadrupole_is_tenth_dalton():
    """ Agilent quadrupole .ms records m/z on a 0.1 Da grid. """
    res = rb.mz_resolution("tests/inputs/orange.D")
    assert res
    assert all(abs(r - 0.1) < 1e-3 for r in res.values())


def test_mz_resolution_waters_is_subnominal():
    """ Waters MS m/z is calibrated to finer than nominal mass. """
    res = rb.mz_resolution("tests/inputs/turquoise.raw")
    assert res
    assert all(0 < r < 0.2 for r in res.values())


def test_mz_resolution_hrms_is_subnominal():
    """ The HRMS profile resolves far finer than nominal, measured per scan. """
    res = rb.mz_resolution(CYAN_D, hrms=True)
    assert res
    assert all(0 < r < 0.1 for r in res.values())


def test_mz_resolution_sim_returns_empty():
    """ A single-ion (SIM) channel has one m/z, so there is no spacing. """
    assert rb.mz_resolution("tests/inputs/green.D") == {}


# The per-vendor floor warning: a bin_width finer than the binary's grid only
# inserts empty bins, so rainbow warns (and the HRMS message names the profile).

def test_floor_warning_agilent_and_waters():
    with pytest.warns(UserWarning, match="only inserts empty bins"):
        rb.read("tests/inputs/orange.D", bin_width=0.01)     # below 0.1 Da
    with pytest.warns(UserWarning, match="only inserts empty bins"):
        rb.read("tests/inputs/turquoise.raw", bin_width=0.01)  # below 0.05 Da


def test_floor_warning_hrms_names_the_profile():
    with pytest.warns(UserWarning, match="MSProfile.bin"):
        rb.read(MAGENTA_D, hrms=True, bin_width=1e-8)          # below 1e-6 Da


def test_no_floor_warning_at_the_grid():
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        rb.read("tests/inputs/orange.D", bin_width=0.1)        # at the floor
    assert not any("empty bins" in str(w.message) for w in caught)


def test_centroid_flag_does_not_silence_other_channels():
    """ The floor belongs to the channel parsed, not to the flags requested.

    A blanket centroid carve-out silenced the warning for every channel in the
    run, including ordinary quadrupole and Waters data that has a real floor.
    """
    with pytest.warns(UserWarning, match="MSD1.MS"):
        rb.read("tests/inputs/orange.D", centroid=True, bin_width=0.001)
    with pytest.warns(UserWarning, match="_func001.dat"):
        # centroid is an Agilent flag; it must not reach a Waters read at all.
        rb.read("tests/inputs/turquoise.raw", centroid=True, bin_width=0.001)


def test_a_centroid_floor_follows_the_rounding_the_parse_applied():
    """ The centroid parse rounds m/z into the data, so that is the grid.

    Unlike the profile path, parse_mspeakdata rounds each peak to
    display_precision before binning, so however finely the instrument
    resolved, the channel records 10**-display_precision. An uncalibrated
    centroid defaults to 0 decimals, which is a floor of 1 Da and not the 0.1
    Da a quadrupole .ms channel records.
    """
    # Calibrated (TOF), 4 decimals by default: the real grid is 1e-4, so a
    # 1e-5 bin only inserts empty bins even though the instrument resolves
    # further. Reported as 0.0001, not the 1e-6 the calibration alone implies.
    with pytest.warns(UserWarning, match=r"MSPeak\.bin \(about 0\.0001 Da\)"):
        rb.read("tests/inputs/gold.D", centroid=True, bin_width=1e-5)
    # Uncalibrated (GC quadrupole), 0 decimals: nominal m/z, a floor of 1 Da.
    with pytest.warns(UserWarning, match=r"MSPeak\.bin \(about 1\.0 Da\)"):
        rb.read("tests/inputs/yellow.D", centroid=True, bin_width=0.5)


def test_the_floor_warning_quotes_each_grid_not_just_the_coarsest():
    """ One number for every channel would be orders of magnitude wrong.

    yellow.D holds a centroid peak list on a 1 Da grid beside two Chemstation
    .ms channels on a 0.1 Da one. Naming them all against a single figure
    would misreport one group by a factor of ten.
    """
    with pytest.warns(UserWarning) as caught:
        rb.read("tests/inputs/yellow.D", centroid=True, bin_width=0.05)
    message = str(next(w.message for w in caught
                       if "empty bins" in str(w.message)))
    assert "MSPeak.bin (about 1.0 Da)" in message
    assert "data.ms, dataSim.ms (about 0.1 Da)" in message


def test_icpms_has_no_floor_because_it_is_never_binned():
    """ An ICP-MS run is fixed isotope channels, and ignores bin_width.

    Falling back to the Agilent vendor floor would warn that a fine bin_width
    inserts empty bins into a channel that is not binned at all.
    """
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        datadir = rb.read("tests/inputs/silver.D", hrms=True, bin_width=0.001)
    assert not any("empty bins" in str(w.message) for w in caught)
    # The claim above: bin_width genuinely does nothing to this parser.
    unbinned = rb.read("tests/inputs/silver.D", hrms=True)
    assert (datadir.get_file("MSProfile.bin").ylabels
            == unbinned.get_file("MSProfile.bin").ylabels).all()


def test_mz_resolution_measures_icpms_which_hrms_gates_but_does_not_bin():
    """ A channel behind a flag, yet on a shared axis, needs both reads.

    ICP-MS is parsed only under hrms=True, but it comes back on a shared m/z
    axis rather than per scan. Measuring only the per-scan channels of the
    flagged read skips it, and a probe read that does not forward the flag
    never parses it, so it fell through both and the run looked like it had
    no MS at all.
    """
    assert rb.mz_resolution("tests/inputs/silver.D", hrms=True) == \
        {"MSProfile.bin": 1.0}
    assert rb.mz_resolution("tests/inputs/silver.D", hrms=True,
                            centroid=True) == {"MSProfile.bin": 1.0}


def test_read_sequence_rejects_bad_bin_width():
    # read_sequence shares read's bin_width guard (a regression let bin_width=0
    # through to a divide-by-zero).
    from rainbow import _validate_bin_width
    with pytest.raises(Exception, match="Invalid bin_width"):
        _validate_bin_width(0)
    with pytest.raises(Exception, match="Invalid bin_width"):
        _validate_bin_width(-1)


# Centroids mirror the profile: per-scan by default (ragged peak lists), a
# shared-grid DataFile only with a bin_width. Test both TOF and GC.

@pytest.mark.parametrize(
    "acqdata",
    [os.path.join(GOLD_D, "AcqData"), YELLOW_ACQDATA],
    ids=["gold-tof", "yellow-gc"])
def test_centroid_per_scan_or_binned(acqdata):
    per_scan = masshunter.parse_mspeakdata(acqdata)
    assert isinstance(per_scan, masshunter.CentroidDataFile)
    grid = masshunter.parse_mspeakdata(acqdata, bin_width=1.0)
    assert isinstance(grid, masshunter.DataFile)
    assert not isinstance(grid, masshunter.CentroidDataFile)
    assert grid.ylabels.size > 0


def test_centroid_is_ragged():
    """ A centroid's defining property: a different number of peaks per scan. """
    centroid = masshunter.parse_mspeakdata(os.path.join(GOLD_D, "AcqData"))
    counts = {centroid.mass_labels(i).size
              for i in range(centroid.xlabels.size)}
    assert len(counts) > 1                       # genuinely ragged
    for i in range(centroid.xlabels.size):
        mz, inten = centroid.scan(i)
        assert mz.size == inten.size             # matched pairs


def test_centroid_shared_axis_ops_raise():
    """ The per-scan centroid refuses every shared-axis operation. """
    centroid = masshunter.parse_mspeakdata(os.path.join(GOLD_D, "AcqData"))
    for op in (lambda c: c.ylabels,
               lambda c: c.data,
               lambda c: c.extract_traces(),
               lambda c: c.to_csvstr(),
               lambda c: c.plot("x")):
        with pytest.raises(AttributeError, match="per-scan m/z axis"):
            op(centroid)


# --- bin_to_grid / _scatter_sum exactness ----------------------------------
# The grid scatter-add uses np.bincount (float64 reduction) for speed, guarded
# to fall back to an exact uint64 np.add.at above float64's 53-bit integer
# range. These tests pin that the fast path is bit-for-bit identical to an exact
# reference, and that the fallback triggers and stays exact past 2**53.

def _reference_scatter(idx, intensities, size):
    """An unambiguous exact uint64 scatter-add to compare against."""
    grid = np.zeros(size, dtype=np.uint64)
    np.add.at(grid, idx, intensities)
    return grid


def test_scatter_sum_matches_exact_reference():
    rng = np.random.default_rng(0)
    size = 500
    idx = rng.integers(0, size, size=20000)
    intensities = rng.integers(0, 10_000, size=20000).astype(np.uint64)
    got = masshunter._scatter_sum(idx, intensities, size)
    assert got.dtype == np.uint64
    np.testing.assert_array_equal(got, _reference_scatter(idx, intensities, size))


def test_scatter_sum_fallback_is_exact_past_2_53():
    # Two points whose summed intensity exceeds 2**53: the float64 bincount path
    # would lose the low bit, so the guard must take the exact uint64 fallback.
    big = np.uint64(2 ** 53)
    idx = np.array([3, 3], dtype=np.int64)
    intensities = np.array([big, np.uint64(1)], dtype=np.uint64)
    assert int(intensities.sum()) >= masshunter._FLOAT64_EXACT_INT  # fallback path
    got = masshunter._scatter_sum(idx, intensities, 8)
    assert int(got[3]) == 2 ** 53 + 1  # exact, not rounded to 2**53


def test_scatter_sum_guard_boundary_is_exact_both_sides():
    # Exactly at the 2**53 boundary takes the exact fallback (strict <); just
    # below stays on the fast bincount path. Both must be exact.
    at = np.array([np.uint64(2 ** 53)], dtype=np.uint64)         # fallback
    below = np.array([np.uint64(2 ** 53 - 1)], dtype=np.uint64)  # fast path
    assert int(masshunter._scatter_sum(np.array([0]), at, 1)[0]) == 2 ** 53
    assert int(masshunter._scatter_sum(np.array([0]), below, 1)[0]) == 2 ** 53 - 1


def test_bin_to_grid_dense_matches_reference():
    # Three scans of unit-resolution points; small m/z span -> dense path.
    mz = np.array([100.0, 101.0, 100.0, 102.0, 101.0, 101.0])
    intensity = np.array([5, 7, 3, 9, 4, 6], dtype=np.uint64)
    rows = np.array([0, 0, 1, 1, 2, 2])
    ylabels, grid = masshunter.bin_to_grid(mz, intensity, rows, 3, display_precision=0)
    assert grid.dtype == np.uint64
    # Expected: columns 100/101/102 summed per scan row.
    np.testing.assert_array_equal(ylabels, [100.0, 101.0, 102.0])
    np.testing.assert_array_equal(grid, np.array([[5, 7, 0],
                                                  [3, 0, 9],
                                                  [0, 10, 0]], dtype=np.uint64))


def test_bin_to_grid_sparse_path_matches_dense(monkeypatch):
    # Force the sparse branch (np.unique/searchsorted) by shrinking the dense
    # threshold, and include a zero-intensity point at an m/z no other scan fills
    # (114.0): the sparse path must drop that phantom all-zero column to match the
    # dense path's grid.any() filter. Same input -> same expected grid.
    monkeypatch.setattr(masshunter, "_MAX_DENSE_BINS", 4)
    mz = np.array([100.0, 101.0, 100.0, 102.0, 101.0, 101.0, 114.0])
    intensity = np.array([5, 7, 3, 9, 4, 6, 0], dtype=np.uint64)
    rows = np.array([0, 0, 1, 1, 2, 2, 2])
    ylabels, grid = masshunter.bin_to_grid(mz, intensity, rows, 3, display_precision=0)
    assert grid.dtype == np.uint64
    np.testing.assert_array_equal(ylabels, [100.0, 101.0, 102.0])
    np.testing.assert_array_equal(grid, np.array([[5, 7, 0],
                                                  [3, 0, 9],
                                                  [0, 10, 0]], dtype=np.uint64))


def test_dad_signals_carry_their_optics():
    """ A DAD signal surfaces the optics its description encodes. """
    datafiles = masshunter.parse_dadfiles(BRONZE_ACQDATA)
    by_name = {df.name: df for df in datafiles}
    signal = by_name["DAD1A.cg"]
    assert signal.metadata["wavelength"] == 254.0
    assert signal.metadata["bandwidth"] == 4.0
    assert signal.metadata["reference_wavelength"] == 360.0
    # "Ref=off" means there is no reference band to record.
    assert "reference_wavelength" not in by_name["DAD1D.cg"].metadata


def test_dad_telemetry_has_no_optics():
    """ A telemetry trace has no Sig= clause, so it gains no optics. """
    datafiles = masshunter.parse_dadfiles(BRONZE_ACQDATA, telemetry=True)
    telemetry = [df for df in datafiles if df.detector is None]
    assert telemetry
    for datafile in telemetry:
        assert "wavelength" not in datafile.metadata


def test_mz_resolution_sees_centroid_data():
    """ Without the flag a centroid run looks like one with no MS at all. """
    assert rb.mz_resolution(GOLD_D) == {}
    resolved = rb.mz_resolution(GOLD_D, centroid=True)
    assert "MSPeak.bin" in resolved
    assert 0 < resolved["MSPeak.bin"] < 2


def test_mz_resolution_centroid_flag_leaves_binned_channels_alone():
    """ The centroid flag must not change what a binned MS channel reports.

    yellow.D holds a Chemstation data.ms beside a MassHunter MSPeak.bin. The
    centroid read is unbinned (the peak lists are per scan), which binned
    data.ms at the default nominal width, so it reported that default instead
    of the 0.1 Da grid the binary records.
    """
    yellow = os.path.join("tests", "inputs", "yellow.D")
    binned = rb.mz_resolution(yellow)
    assert binned["data.ms"] == 0.1
    with_centroid = rb.mz_resolution(yellow, centroid=True)
    assert with_centroid["data.ms"] == binned["data.ms"]
    assert with_centroid["dataSim.ms"] == binned["dataSim.ms"]
    # The centroid channel is still measured per scan, not on the probe grid.
    assert with_centroid["MSPeak.bin"] > 1e-3


def test_list_analog_handles_masshunter_telemetry(capsys):
    """ MassHunter keys a trace's description 'signal', not 'description'. """
    rb.read(BRONZE_D, telemetry=True).list_analog()
    printed = capsys.readouterr().out
    assert "Board Temperature" in printed
    assert "UV Lamp Anode Voltage" in printed
