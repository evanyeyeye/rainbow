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
# check that precision='auto' resolves to whole-number m/z labels for the
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
    assert profile.tof.size == k

    for i in range(n):
        mz, inten = profile.scan(i)
        # The per-scan m/z is the exact calibration of the shared flight-time
        # axis (rounded to the reported precision), not a shared rounded grid.
        truth = np.round(
            masshunter.calibrate_mz(
                profile.tof, calib[i],
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
    """ The GC-quadrupole MSPeak.bin m/z axis (already calibrated) matches
    the independent data.ms axis for the same acquisition. """
    centroid = masshunter.parse_mspeakdata(YELLOW_ACQDATA)
    assert centroid.name == "MSPeak.bin"
    assert centroid.detector == "MS"
    assert centroid.data.shape[0] == centroid.xlabels.size
    assert centroid.data.shape[1] == centroid.ylabels.size
    assert (centroid.ylabels[1:] > centroid.ylabels[:-1]).all()

    data_ms = rb.read("tests/inputs/yellow.D").get_file("data.ms")
    np.testing.assert_array_equal(centroid.ylabels, data_ms.ylabels)


def test_gold_centroid_is_calibrated():
    """ A TOF centroid axis is stored as time-of-flight; parsing calibrates
    it to real m/z (within the profile's m/z range, not raw flight time). """
    centroid = masshunter.parse_mspeakdata(os.path.join(GOLD_D, "AcqData"))
    assert centroid.ylabels.min() > 50
    assert centroid.ylabels.max() < 1100
    assert (centroid.ylabels[1:] > centroid.ylabels[:-1]).all()


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


def test_centroid_truncation_is_graceful():
    """ A truncated MSPeak.bin segment is skipped rather than crashing. """
    centroid = masshunter.parse_mspeakdata(os.path.join(COPPER_D, "AcqData"))
    assert centroid.name == "MSPeak.bin"
    assert centroid.data.shape[0] >= 3


# ---------------------------------------------------------------------------
# precision='auto', bin_width, the per-scan default, and the error surface
# (1.3). precision is a label precision (decimals), bin_width is the shared-grid
# bin width in daltons; the two are independent. The HRMS default is per-scan.
# ---------------------------------------------------------------------------

def test_precision_auto_profile_is_four_decimals():
    """ 'auto' precision rounds HRMS profile labels to 4 decimals (not nominal
    mass), on the shared grid. """
    prof = rb.read(MAGENTA_D, hrms=True,
                   bin_width=0.0001).get_file("MSProfile.bin")
    yl = prof.ylabels
    assert np.allclose(yl, np.round(yl, 4))
    assert not np.allclose(yl, np.round(yl))      # genuinely sub-integer


def test_precision_explicit_overrides_auto():
    """ An explicit integer overrides the 'auto' default (labels only; the grid
    is the separate bin_width). """
    prof = rb.read(MAGENTA_D, hrms=True, precision=1,
                   bin_width=0.1).get_file("MSProfile.bin")
    assert np.allclose(prof.ylabels, np.round(prof.ylabels, 1))


def test_precision_auto_gc_centroid_is_integer():
    """ GC-quadrupole centroids (no calibration) auto-resolve to whole numbers,
    matching the unit-resolution data.ms axis. """
    dd = rb.read("tests/inputs/yellow.D", centroid=True)
    cen = dd.get_file("MSPeak.bin")
    assert np.array_equal(cen.ylabels, np.round(cen.ylabels))
    assert np.array_equal(cen.ylabels, dd.get_file("data.ms").ylabels)


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
    fine = rb.read(MAGENTA_D, hrms=True, precision=4,
                   bin_width=0.01).get_file("MSProfile.bin")
    coarse = rb.read(MAGENTA_D, hrms=True, precision=2,
                     bin_width=0.01).get_file("MSProfile.bin")
    assert np.array_equal(fine.data, coarse.data)
    assert np.array_equal(fine.ylabels, coarse.ylabels)


def test_bin_width_decouples_from_precision():
    """ At the same label precision, a coarser bin_width yields fewer columns. """
    fine = rb.read(MAGENTA_D, hrms=True, precision=2,
                   bin_width=0.01).get_file("MSProfile.bin")
    coarse = rb.read(MAGENTA_D, hrms=True, precision=2,
                     bin_width=0.1).get_file("MSProfile.bin")
    assert coarse.ylabels.size < fine.ylabels.size


def test_bin_width_finer_than_labels_warns():
    """ precision and bin_width are independent, so a bin_width finer than the
    labels is allowed; it only WARNS (labels may collide), it does not raise, and
    it still produces a grid. """
    with pytest.warns(UserWarning, match="may collide"):
        out = rb.read(MAGENTA_D, hrms=True, precision=2, bin_width=0.001)
    assert out.get_file("MSProfile.bin").data.shape[1] > 0


def test_bin_width_finer_than_labels_warns_direct():
    """ The warning fires at the direct (non-rb.read) entry point too. """
    acqdata = os.path.join(MAGENTA_D, "AcqData")
    with pytest.warns(UserWarning, match="may collide"):
        masshunter.parse_msdata(acqdata, precision=2, bin_width=0.001)


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
    with pytest.raises(Exception, match="Invalid precision"):
        rb.read(MAGENTA_D, hrms=True, precision=True)


def test_precision_auto_tof_centroid_is_four_decimals():
    """ A TOF-calibrated centroid (gold.D) auto-resolves to 4 decimals, unlike
    the unit-resolution GC centroid that resolves to whole numbers. """
    centroid = masshunter.parse_mspeakdata(os.path.join(GOLD_D, "AcqData"))
    yl = centroid.ylabels
    assert np.allclose(yl, np.round(yl, 4))
    assert not np.array_equal(yl, np.round(yl))   # genuinely sub-integer


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


def test_tof_axis_is_shared_and_monotonic():
    """ tof is the one flight-time axis shared by every scan: it indexes the
    columns and is strictly increasing. """
    profile = rb.read(CYAN_D, hrms=True).get_file("MSProfile.bin")
    assert profile.tof.size == profile.data.shape[1]
    assert (profile.tof[1:] > profile.tof[:-1]).all()


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


# precision='auto' resolves to 0 (whole-number m/z labels) for the
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
