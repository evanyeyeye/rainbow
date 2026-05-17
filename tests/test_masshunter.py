"""
Tests for rainbow.agilent.masshunter — MSPeak.bin support.

Covers:
  - parse_allfiles    : auto-detection of MSProfile.bin vs MSPeak.bin
  - parse_mspeak_data : main public function
  - _parse_msscan_bin : internal scan index reader
  - _parse_mspeak_bin : internal peak data reader
  - DataFile contract : correct xlabels / ylabels / data / metadata shapes
  - Peak encoding     : bpp=8 (float32), bpp=12 (mixed), bpp=16 (float64)
  - Edge cases        : empty scans, zero-peak file, prec rounding,
                        missing files, unknown bpp

Run with:
    python -m unittest test_masshunter.py          (from this directory)
    python -m unittest discover -s tests           (from project root)
"""

import os
import struct
import tempfile
import unittest
import warnings

import numpy as np
from lxml import etree

from rainbow import DataFile
from rainbow.agilent.masshunter import (
    parse_allfiles,
    parse_mspeak_data,
    _parse_msscan_bin,
    _parse_mspeak_bin,
)


# ══════════════════════════════════════════════════════════════════════════════
# Fixture helpers
# ══════════════════════════════════════════════════════════════════════════════

_POINTER_OFFSET = 0x58   # pointer lives here


def _make_scan_record(
    scan_id, scan_time, tic, base_peak_mz, base_peak_value,
    spectrum_offset, byte_count, point_count,
    ms_level=1, scan_type=1, ion_mode=2, ion_polarity=0,
):
    """
    Pack one MSScan.bin record matching the XSD field order.
    read_complextype() reads fields sequentially in XSD definition order:

    ScanRecordType:
      ScanID(i) ScanMethodID(i) TimeSegmentID(i) ScanTime(d)
      MSLevel(i) ScanType(i) TIC(d) BasePeakMZ(d) BasePeakValue(d)
      CycleNumber(i) Status(i) IonMode(i) IonPolarity(i)
      Fragmentor(d) CollisionEnergy(d) MzOfInterest(d)
      SamplingPeriod(d) MeasuredMassRangeMin(d) MeasuredMassRangeMax(d)
      Threshold(d) IsFragmentorDynamic(i) IsCollisionEnergyDynamic(i)
      SpectrumParamValues (SpectrumParamsType):
        SpectrumFormatID(i) SpectrumOffset(l) ByteCount(i) PointCount(i)
        MinY(d) MaxY(d) MinX(d) MaxX(d)
    """
    return struct.pack(
        '<'
        # ScanRecordType fields
        'i'      # ScanID
        'i'      # ScanMethodID
        'i'      # TimeSegmentID
        'd'      # ScanTime
        'i'      # MSLevel
        'i'      # ScanType
        'd'      # TIC
        'd'      # BasePeakMZ
        'd'      # BasePeakValue
        'i'      # CycleNumber
        'i'      # Status
        'i'      # IonMode
        'i'      # IonPolarity
        'd'      # Fragmentor
        'd'      # CollisionEnergy
        'd'      # MzOfInterest
        'd'      # SamplingPeriod
        'd'      # MeasuredMassRangeMin
        'd'      # MeasuredMassRangeMax
        'd'      # Threshold
        'i'      # IsFragmentorDynamic
        'i'      # IsCollisionEnergyDynamic
        # SpectrumParamValues (SpectrumParamsType)
        'i'      # SpectrumFormatID
        'Q'      # SpectrumOffset  (xs:long = uint64)
        'i'      # ByteCount
        'i'      # PointCount
        'd'      # MinY
        'd'      # MaxY
        'd'      # MinX
        'd'      # MaxX
        ,
        # ScanRecordType values
        scan_id, 1, 1,          # ScanID, ScanMethodID, TimeSegmentID
        scan_time,              # ScanTime
        ms_level, scan_type,    # MSLevel, ScanType
        tic,                    # TIC
        base_peak_mz,           # BasePeakMZ
        base_peak_value,        # BasePeakValue
        0, 0,                   # CycleNumber, Status
        ion_mode, ion_polarity, # IonMode, IonPolarity
        0.0, 0.0, 0.0, 0.0,    # Fragmentor, CollisionEnergy, MzOfInterest, SamplingPeriod
        0.0, 0.0, 0.0,          # MeasuredMassRangeMin, MeasuredMassRangeMax, Threshold
        0, 0,                   # IsFragmentorDynamic, IsCollisionEnergyDynamic
        # SpectrumParamValues values
        2,                      # SpectrumFormatID
        spectrum_offset,        # SpectrumOffset
        byte_count,             # ByteCount
        point_count,            # PointCount
        0.0,                    # MinY
        float(base_peak_value), # MaxY
        0.0,                    # MinX
        0.0,                    # MaxX
    )


def _make_msscan_bin(scan_specs):
    """
    Build a synthetic MSScan.bin byte string.
    Writes a uint32 pointer at 0x58 pointing to where records start,
    matching the real file format and parse_msdata() / _parse_msscan_bin()
    framing.
    """
    records_start = _POINTER_OFFSET + 4   # records start at byte 92
    buf = bytearray(_POINTER_OFFSET)      # pad to 0x58
    buf += struct.pack('<I', records_start)
    for s in scan_specs:
        buf += _make_scan_record(**s)
    return bytes(buf)


def _make_mspeak_bin_f64(peak_lists):
    """
    Build a synthetic MSPeak.bin with the split-block bpp=16 format.

    Layout per scan:
      n × float64  nominal m/z    (first half)
      n × float64  intensity      (second half)

    Args:
        peak_lists: list of lists of (mz, intensity) tuples, one per scan.

    Returns:
        (bytes, list_of_offsets)
    """
    buf     = bytearray()
    offsets = []
    for peaks in peak_lists:
        offsets.append(len(buf))
        # first block: all m/z values
        for mz, _ in peaks:
            buf += struct.pack('<d', mz)
        # second block: all intensities
        for _, intensity in peaks:
            buf += struct.pack('<d', intensity)
    return bytes(buf), offsets


def _make_mspeak_bin_f32(peak_lists):
    """
    Build MSPeak.bin with float32 mz + float32 intensity (bpp=8).
    """
    buf     = bytearray()
    offsets = []
    for peaks in peak_lists:
        offsets.append(len(buf))
        for mz, intensity in peaks:
            buf += struct.pack('<ff', mz, intensity)
    return bytes(buf), offsets


def _make_mspeak_bin_mixed(peak_lists):
    """
    Build MSPeak.bin with float64 mz + float32 intensity (bpp=12).
    """
    buf     = bytearray()
    offsets = []
    for peaks in peak_lists:
        offsets.append(len(buf))
        for mz, intensity in peaks:
            buf += struct.pack('<df', mz, intensity)
    return bytes(buf), offsets


MSTS_XML_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<TimeSegments>
  <TimeSegment TimeSegmentID="1">
    <StartTime>0</StartTime>
    <EndTime>10</EndTime>
    <NumOfScans>{num_scans}</NumOfScans>
    <FixedCycleLength>0</FixedCycleLength>
  </TimeSegment>
</TimeSegments>
"""

MSSCAN_XSD = """\
<?xml version="1.0" encoding="utf-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="ScanRecord" type="ScanRecordType"/>
  <xs:complexType name="ScanRecordType">
    <xs:sequence>
      <xs:element name="ScanID" type="xs:int"/>
      <xs:element name="ScanMethodID" type="xs:int"/>
      <xs:element name="TimeSegmentID" type="xs:int"/>
      <xs:element name="ScanTime" type="xs:double"/>
      <xs:element name="MSLevel" type="xs:int"/>
      <xs:element name="ScanType" type="xs:int"/>
      <xs:element name="TIC" type="xs:double"/>
      <xs:element name="BasePeakMZ" type="xs:double"/>
      <xs:element name="BasePeakValue" type="xs:double"/>
      <xs:element name="CycleNumber" type="xs:int"/>
      <xs:element name="Status" type="xs:int"/>
      <xs:element name="IonMode" type="xs:int"/>
      <xs:element name="IonPolarity" type="xs:int"/>
      <xs:element name="Fragmentor" type="xs:double"/>
      <xs:element name="CollisionEnergy" type="xs:double"/>
      <xs:element name="MzOfInterest" type="xs:double"/>
      <xs:element name="SamplingPeriod" type="xs:double"/>
      <xs:element name="MeasuredMassRangeMin" type="xs:double"/>
      <xs:element name="MeasuredMassRangeMax" type="xs:double"/>
      <xs:element name="Threshold" type="xs:double"/>
      <xs:element name="IsFragmentorDynamic" type="xs:int"/>
      <xs:element name="IsCollisionEnergyDynamic" type="xs:int"/>
      <xs:element name="SpectrumParamValues" type="SpectrumParamsType"/>
    </xs:sequence>
  </xs:complexType>
  <xs:complexType name="SpectrumParamsType">
    <xs:sequence>
      <xs:element name="SpectrumFormatID" type="xs:int"/>
      <xs:element name="SpectrumOffset" type="xs:long"/>
      <xs:element name="ByteCount" type="xs:int"/>
      <xs:element name="PointCount" type="xs:int"/>
      <xs:element name="MinY" type="xs:double"/>
      <xs:element name="MaxY" type="xs:double"/>
      <xs:element name="MinX" type="xs:double"/>
      <xs:element name="MaxX" type="xs:double"/>
    </xs:sequence>
  </xs:complexType>
</xs:schema>
"""


def _write_acqdata(tmpdir, scan_specs, peak_bytes, extra_files=None):
    """
    Write a minimal AcqData directory for testing.

    Args:
        tmpdir:     path to a temporary directory (the .D folder)
        scan_specs: list of scan spec dicts (passed to _make_msscan_bin)
        peak_bytes: raw bytes for MSPeak.bin
        extra_files: dict of {filename: bytes} for additional files
    """
    acq = os.path.join(tmpdir, "AcqData")
    os.makedirs(acq, exist_ok=True)

    # MSTS.xml
    with open(os.path.join(acq, "MSTS.xml"), 'w') as f:
        f.write(MSTS_XML_TEMPLATE.format(num_scans=len(scan_specs)))

    # MSScan.xsd
    with open(os.path.join(acq, "MSScan.xsd"), 'w') as f:
        f.write(MSSCAN_XSD)

    # MSScan.bin
    with open(os.path.join(acq, "MSScan.bin"), 'wb') as f:
        f.write(_make_msscan_bin(scan_specs))

    # MSPeak.bin
    with open(os.path.join(acq, "MSPeak.bin"), 'wb') as f:
        f.write(peak_bytes)

    # any extra files requested
    if extra_files:
        for name, data in extra_files.items():
            with open(os.path.join(acq, name), 'wb') as f:
                f.write(data)

    return acq


def _make_standard_fixture(tmpdir, n_scans=3, bpp=16):
    """
    Build a complete test .D directory with n_scans scans and the given bpp.

    Returns (dot_d_path, expected_scan_times, expected_peaks_per_scan)
    where expected_peaks_per_scan is a list of [(mz, intensity), ...].
    """
    peak_lists = [
        [(100.0 + i * 10, 500.0 - i * 50), (200.0 + i * 5, 300.0 + i * 20)]
        for i in range(n_scans)
    ]

    if bpp == 16:
        peak_bytes, offsets = _make_mspeak_bin_f64(peak_lists)
    elif bpp == 8:
        peak_bytes, offsets = _make_mspeak_bin_f32(peak_lists)
    elif bpp == 12:
        peak_bytes, offsets = _make_mspeak_bin_mixed(peak_lists)

    scan_times = [0.5 * (i + 1) for i in range(n_scans)]
    scan_specs = []
    for i in range(n_scans):
        peaks  = peak_lists[i]
        n_pts  = len(peaks)
        b_cnt  = n_pts * bpp
        bp_mz  = max(peaks, key=lambda p: p[1])[0]
        bp_val = max(peaks, key=lambda p: p[1])[1]
        scan_specs.append(dict(
            scan_id        = i + 1,
            scan_time      = scan_times[i],
            tic            = sum(p[1] for p in peaks),
            base_peak_mz   = bp_mz,
            base_peak_value= bp_val,
            spectrum_offset= offsets[i],
            byte_count     = b_cnt,
            point_count    = n_pts,
        ))

    _write_acqdata(tmpdir, scan_specs, peak_bytes)
    return tmpdir, scan_times, peak_lists


# ══════════════════════════════════════════════════════════════════════════════
# Test classes
# ══════════════════════════════════════════════════════════════════════════════

class TestRecordFormat(unittest.TestCase):
    """Sanity checks on the XSD-driven record parsing."""

    def setUp(self):
        acq           = _write_acqdata(tempfile.mkdtemp(), [], b'')
        xsd_path      = os.path.join(acq, "MSScan.xsd")
        tree          = etree.parse(xsd_path)
        root          = tree.getroot()
        namespace     = tree.xpath('namespace-uri(.)')
        self.names    = [ct.get('name') for ct in
                         root.findall(f"{{{namespace}}}complexType")]
        self.all_names = {el.get('name')
                          for el in root.iter()
                          if el.get('name') and el.get('type')}

    def test_xsd_contains_required_types(self):
        """MSScan.xsd must define ScanRecordType and SpectrumParamsType."""
        self.assertIn('ScanRecordType',     self.names)
        self.assertIn('SpectrumParamsType', self.names)

    def test_xsd_scanrecord_contains_required_fields(self):
        """ScanRecordType must define the fields we rely on."""
        required = {
            'ScanTime', 'TIC', 'BasePeakMZ', 'BasePeakValue',
            'MSLevel', 'IonMode', 'IonPolarity',
            'SpectrumOffset', 'ByteCount', 'PointCount',
        }
        self.assertTrue(required.issubset(self.all_names),
                        f"Missing fields: {required - self.all_names}")

    def test_xsd_spectrumparams_contains_required_fields(self):
        """SpectrumParamsType must define the spectrum pointer fields."""
        required = {
            'SpectrumFormatID', 'SpectrumOffset',
            'ByteCount', 'PointCount',
            'MinY', 'MaxY', 'MinX', 'MaxX',
        }
        self.assertTrue(required.issubset(self.all_names),
                        f"Missing fields: {required - self.all_names}")
                    

class TestParseMsscanBin(unittest.TestCase):
    """Tests for _parse_msscan_bin."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _write_scan_bin(self, scan_specs):
        """Write a full AcqData directory and return the MSScan.bin path."""
        # _write_acqdata writes MSScan.bin + MSScan.xsd — both needed now
        acq = _write_acqdata(self.tmpdir, scan_specs, b'')
        return acq   # return acqdata path, not just MSScan.bin

    def _parse(self, acq_path, n):
        """Helper: parse MSScan.bin using XSD from the same AcqData folder."""
        return _parse_msscan_bin(
            os.path.join(acq_path, "MSScan.bin"),
            n,
            os.path.join(acq_path, "MSScan.xsd"),
        )

    def test_correct_number_of_records(self):
        specs = [
            dict(scan_id=i, scan_time=float(i), tic=100.0,
                 base_peak_mz=100.0, base_peak_value=50.0,
                 spectrum_offset=0, byte_count=0, point_count=0)
            for i in range(5)
        ]
        acq     = self._write_scan_bin(specs)
        records = self._parse(acq, 5)
        self.assertEqual(len(records), 5)

    def test_scan_time_values(self):
        times = [0.5, 1.0, 2.5]
        specs = [
            dict(scan_id=i+1, scan_time=t, tic=0.0,
                 base_peak_mz=0.0, base_peak_value=0.0,
                 spectrum_offset=0, byte_count=0, point_count=0)
            for i, t in enumerate(times)
        ]
        acq     = self._write_scan_bin(specs)
        records = self._parse(acq, 3)
        for rec, expected_t in zip(records, times):
            self.assertAlmostEqual(rec['scan_time'], expected_t, places=6)

    def test_tic_values(self):
        tics = [100.0, 2500.5, 0.0]
        specs = [
            dict(scan_id=i+1, scan_time=float(i), tic=t,
                 base_peak_mz=0.0, base_peak_value=0.0,
                 spectrum_offset=0, byte_count=0, point_count=0)
            for i, t in enumerate(tics)
        ]
        acq     = self._write_scan_bin(specs)
        records = self._parse(acq, 3)
        for rec, expected_tic in zip(records, tics):
            self.assertAlmostEqual(rec['tic'], expected_tic, places=3)

    def test_spectrum_offset_and_point_count(self):
        spec = dict(scan_id=1, scan_time=1.0, tic=500.0,
                    base_peak_mz=135.0, base_peak_value=400.0,
                    spectrum_offset=6404, byte_count=64, point_count=4)
        acq     = self._write_scan_bin([spec])
        records = self._parse(acq, 1)
        self.assertEqual(records[0]['spectrum_offset'], 6404)
        self.assertEqual(records[0]['byte_count'],      64)
        self.assertEqual(records[0]['point_count'],     4)

    def test_base_peak_fields(self):
        spec = dict(scan_id=1, scan_time=1.0, tic=500.0,
                    base_peak_mz=135.0, base_peak_value=400.0,
                    spectrum_offset=0, byte_count=0, point_count=0)
        acq     = self._write_scan_bin([spec])
        records = self._parse(acq, 1)
        self.assertAlmostEqual(records[0]['base_peak_mz'],    135.0, places=4)
        self.assertAlmostEqual(records[0]['base_peak_value'], 400.0, places=4)

    def test_partial_file_truncated_gracefully(self):
        """If the file has fewer records than expected, return what was read."""
        spec = dict(scan_id=1, scan_time=1.0, tic=0.0,
                    base_peak_mz=0.0, base_peak_value=0.0,
                    spectrum_offset=0, byte_count=0, point_count=0)
        acq     = self._write_scan_bin([spec])
        records = self._parse(acq, 5)  # ask for 5, only 1 exists
        self.assertEqual(len(records), 1)


class TestParseMspeakBin(unittest.TestCase):
    """Tests for _parse_mspeak_bin — all three peak encodings."""

    def _make_scan_record_minimal(self, spectrum_offset, byte_count,
                                   point_count, scan_time=1.0):
        return {
            'scan_time'      : scan_time,
            'spectrum_offset': spectrum_offset,
            'byte_count'     : byte_count,
            'point_count'    : point_count,
        }

    def test_bpp16_float64_pairs(self):
        peaks      = [(135.0, 500.0), (77.0, 300.0), (51.0, 100.0)]
        peak_bytes, offsets = _make_mspeak_bin_f64([peaks])
        rec        = self._make_scan_record_minimal(offsets[0],
                                                    len(peaks) * 16,
                                                    len(peaks))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(peak_bytes); fname = f.name
        try:
            spectra = _parse_mspeak_bin(fname, [rec])
            rt, mz_arr, int_arr = spectra[0]
            self.assertEqual(len(mz_arr), 3)
            np.testing.assert_allclose(sorted(mz_arr), [51.0, 77.0, 135.0])
            # intensities match (order may differ from sort)
            self.assertAlmostEqual(int_arr[np.argmin(np.abs(mz_arr - 135.0))],
                                   500.0, places=3)
        finally:
            os.unlink(fname)

    def test_bpp8_float32_pairs(self):
        peaks      = [(100.0, 200.0), (150.0, 400.0)]
        peak_bytes, offsets = _make_mspeak_bin_f32([peaks])
        rec        = self._make_scan_record_minimal(offsets[0],
                                                    len(peaks) * 8,
                                                    len(peaks))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(peak_bytes); fname = f.name
        try:
            spectra = _parse_mspeak_bin(fname, [rec])
            rt, mz_arr, int_arr = spectra[0]
            self.assertEqual(len(mz_arr), 2)
            np.testing.assert_allclose(sorted(mz_arr), [100.0, 150.0],
                                       rtol=1e-5)
        finally:
            os.unlink(fname)

    def test_bpp12_mixed_encoding(self):
        peaks      = [(200.0, 600.0), (250.5, 800.0)]
        peak_bytes, offsets = _make_mspeak_bin_mixed([peaks])
        rec        = self._make_scan_record_minimal(offsets[0],
                                                    len(peaks) * 12,
                                                    len(peaks))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(peak_bytes); fname = f.name
        try:
            spectra = _parse_mspeak_bin(fname, [rec])
            rt, mz_arr, int_arr = spectra[0]
            self.assertEqual(len(mz_arr), 2)
            np.testing.assert_allclose(sorted(mz_arr), [200.0, 250.5],
                                       rtol=1e-5)
        finally:
            os.unlink(fname)

    def test_empty_scan_returns_empty_arrays(self):
        rec = self._make_scan_record_minimal(0, 0, 0)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b''); fname = f.name
        try:
            spectra = _parse_mspeak_bin(fname, [rec])
            rt, mz_arr, int_arr = spectra[0]
            self.assertEqual(len(mz_arr), 0)
            self.assertEqual(len(int_arr), 0)
        finally:
            os.unlink(fname)

    def test_unknown_bpp_emits_warning_and_empty(self):
        # 10 bytes/peak is not a known format
        peak_bytes = b'\x00' * 20
        rec = self._make_scan_record_minimal(0, 20, 2)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(peak_bytes); fname = f.name
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                spectra = _parse_mspeak_bin(fname, [rec])
            self.assertTrue(any(issubclass(x.category, RuntimeWarning)
                                for x in w))
            rt, mz_arr, int_arr = spectra[0]
            self.assertEqual(len(mz_arr), 0)
        finally:
            os.unlink(fname)

    def test_multiple_scans_correct_offsets(self):
        peak_lists = [
            [(100.0, 200.0)],
            [(300.0, 400.0), (350.0, 500.0)],
            [(50.0, 100.0), (60.0, 110.0), (70.0, 120.0)],
        ]
        peak_bytes, offsets = _make_mspeak_bin_f64(peak_lists)
        recs = [
            self._make_scan_record_minimal(offsets[i],
                                           len(peak_lists[i]) * 16,
                                           len(peak_lists[i]),
                                           scan_time=float(i+1))
            for i in range(3)
        ]
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(peak_bytes); fname = f.name
        try:
            spectra = _parse_mspeak_bin(fname, recs)
            self.assertEqual(len(spectra[0][1]), 1)
            self.assertEqual(len(spectra[1][1]), 2)
            self.assertEqual(len(spectra[2][1]), 3)
        finally:
            os.unlink(fname)

    def test_retention_times_propagated(self):
        peaks = [(100.0, 200.0)]
        peak_bytes, offsets = _make_mspeak_bin_f64([peaks])
        rec = self._make_scan_record_minimal(offsets[0], 16, 1, scan_time=3.14)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(peak_bytes); fname = f.name
        try:
            spectra = _parse_mspeak_bin(fname, [rec])
            self.assertAlmostEqual(spectra[0][0], 3.14, places=5)
        finally:
            os.unlink(fname)


class TestParseMspeakData(unittest.TestCase):
    """Tests for parse_mspeak_data — the main public function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_returns_datafile(self):
        _make_standard_fixture(self.tmpdir)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        self.assertIsInstance(result, DataFile)

    def test_datafile_name_is_mspeak_bin(self):
        _make_standard_fixture(self.tmpdir)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        self.assertEqual(result.name, "MSPeak.bin")

    def test_detector_is_ms(self):
        _make_standard_fixture(self.tmpdir)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        self.assertEqual(result.detector, 'MS')

    def test_xlabels_shape_and_values(self):
        n = 4
        _make_standard_fixture(self.tmpdir, n_scans=n)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        self.assertEqual(result.xlabels.ndim, 1)
        self.assertEqual(result.xlabels.size, n)
        # retention times should be strictly increasing
        self.assertTrue(np.all(np.diff(result.xlabels) > 0))

    def test_ylabels_are_sorted_unique_mz(self):
        _make_standard_fixture(self.tmpdir)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        self.assertEqual(result.ylabels.ndim, 1)
        self.assertTrue(np.all(np.diff(result.ylabels) > 0),
                        "ylabels must be strictly increasing")
        self.assertEqual(result.ylabels.size,
                         np.unique(result.ylabels).size,
                         "ylabels must be unique")

    def test_data_shape(self):
        n = 3
        _make_standard_fixture(self.tmpdir, n_scans=n)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        self.assertEqual(result.data.ndim, 2)
        self.assertEqual(result.data.shape[0], n)
        self.assertEqual(result.data.shape[1], result.ylabels.size)

    def test_data_intensities_non_negative(self):
        _make_standard_fixture(self.tmpdir)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        self.assertTrue(np.all(result.data >= 0))

    def test_tic_in_metadata(self):
        n = 3
        _make_standard_fixture(self.tmpdir, n_scans=n)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        self.assertIn('tic', result.metadata)
        self.assertEqual(result.metadata['tic'].size, n)
        self.assertTrue(np.all(result.metadata['tic'] >= 0))

    def test_metadata_keys_present(self):
        _make_standard_fixture(self.tmpdir)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        for key in ('tic', 'base_peak_mz', 'base_peak_value',
                    'ms_level', 'scan_type', 'ion_mode', 'ion_polarity'):
            self.assertIn(key, result.metadata, f"Missing metadata key: {key}")

    def test_specific_peak_is_placed_correctly(self):
        """A single scan with one peak — intensity must land in the right cell."""
        peak_bytes, offsets = _make_mspeak_bin_f64([[(135.0, 500.0)]])
        scan_specs = [dict(scan_id=1, scan_time=1.0, tic=500.0,
                           base_peak_mz=135.0, base_peak_value=500.0,
                           spectrum_offset=offsets[0],
                           byte_count=16, point_count=1)]
        acq = _write_acqdata(self.tmpdir, scan_specs, peak_bytes)
        result = parse_mspeak_data(acq)

        idx_mz  = np.searchsorted(result.ylabels, 135.0)
        self.assertAlmostEqual(result.data[0, idx_mz], 500.0, places=2)

    def test_prec_rounding_merges_close_mz(self):
        """With prec=0, m/z 135.1 and 135.4 should both map to 135."""
        peaks = [(135.1, 100.0), (135.4, 200.0)]
        peak_bytes, offsets = _make_mspeak_bin_f64([peaks])
        scan_specs = [dict(scan_id=1, scan_time=1.0, tic=300.0,
                           base_peak_mz=135.4, base_peak_value=200.0,
                           spectrum_offset=offsets[0],
                           byte_count=32, point_count=2)]
        acq = _write_acqdata(self.tmpdir, scan_specs, peak_bytes)
        result = parse_mspeak_data(acq, prec=0)
        # Both should round to 135 and be summed
        self.assertIn(135.0, result.ylabels)
        idx = np.searchsorted(result.ylabels, 135.0)
        self.assertAlmostEqual(result.data[0, idx], 300.0, places=1)

    def test_prec_rounding_keeps_distinct_mz(self):
        """With prec=2, m/z 135.10 and 135.50 stay separate."""
        peaks = [(135.10, 100.0), (135.50, 200.0)]
        peak_bytes, offsets = _make_mspeak_bin_f64([peaks])
        scan_specs = [dict(scan_id=1, scan_time=1.0, tic=300.0,
                           base_peak_mz=135.5, base_peak_value=200.0,
                           spectrum_offset=offsets[0],
                           byte_count=32, point_count=2)]
        acq = _write_acqdata(self.tmpdir, scan_specs, peak_bytes)
        result = parse_mspeak_data(acq, prec=2)
        self.assertIn(135.10, result.ylabels)
        self.assertIn(135.50, result.ylabels)

    def test_all_empty_scans_returns_empty_datafile(self):
        """File where every scan has zero peaks."""
        scan_specs = [
            dict(scan_id=i+1, scan_time=float(i), tic=0.0,
                 base_peak_mz=0.0, base_peak_value=0.0,
                 spectrum_offset=0, byte_count=0, point_count=0)
            for i in range(3)
        ]
        acq = _write_acqdata(self.tmpdir, scan_specs, b'')
        result = parse_mspeak_data(acq)
        self.assertIsInstance(result, DataFile)
        self.assertEqual(result.ylabels.size, 0)
        self.assertEqual(result.data.shape, (3, 0))

    def test_bpp8_encoding_parsed_correctly(self):
        _make_standard_fixture(self.tmpdir, bpp=8)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        self.assertGreater(result.ylabels.size, 0)
        self.assertGreater(result.data.sum(), 0)

    def test_bpp12_encoding_parsed_correctly(self):
        _make_standard_fixture(self.tmpdir, bpp=12)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        self.assertGreater(result.ylabels.size, 0)
        self.assertGreater(result.data.sum(), 0)

    def test_bpp16_encoding_parsed_correctly(self):
        _make_standard_fixture(self.tmpdir, bpp=16)
        result = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        self.assertGreater(result.ylabels.size, 0)
        self.assertGreater(result.data.sum(), 0)

    def test_extract_traces_works_on_result(self):
        """DataFile.extract_traces should work on the returned object."""
        _make_standard_fixture(self.tmpdir)
        result  = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        label   = result.ylabels[0]
        traces  = result.extract_traces(label)
        self.assertEqual(traces.shape, (1, result.xlabels.size))

    def test_export_csv_produces_output(self):
        _make_standard_fixture(self.tmpdir)
        result   = parse_mspeak_data(os.path.join(self.tmpdir, "AcqData"))
        csv_path = os.path.join(self.tmpdir, "out.csv")
        result.export_csv(csv_path)
        self.assertTrue(os.path.exists(csv_path))
        self.assertGreater(os.path.getsize(csv_path), 0)


class TestParseAllfiles(unittest.TestCase):
    """Tests for parse_allfiles — auto-detection of format."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_mspeak_bin_detected(self):
        """parse_allfiles should return a DataFile when MSPeak.bin is present."""
        _make_standard_fixture(self.tmpdir)
        results = parse_allfiles(self.tmpdir)
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], DataFile)
        self.assertEqual(results[0].name, "MSPeak.bin")

    def test_no_acqdata_returns_empty_list(self):
        empty_dir = tempfile.mkdtemp()
        self.assertEqual(parse_allfiles(empty_dir), [])

    def test_missing_required_files_returns_empty_list(self):
        """AcqData exists but is missing MSScan.bin — should return []."""
        acq = os.path.join(self.tmpdir, "AcqData")
        os.makedirs(acq)
        # Write only MSTS.xml, no MSScan.bin or MSPeak.bin
        with open(os.path.join(acq, "MSTS.xml"), 'w') as f:
            f.write(MSTS_XML_TEMPLATE.format(num_scans=1))
        self.assertEqual(parse_allfiles(self.tmpdir), [])

    def test_neither_profile_nor_peak_returns_empty(self):
        """MSScan.bin present but neither MSProfile nor MSPeak — return []."""
        acq = os.path.join(self.tmpdir, "AcqData")
        os.makedirs(acq)
        with open(os.path.join(acq, "MSTS.xml"),   'w') as f:
            f.write(MSTS_XML_TEMPLATE.format(num_scans=0))
        with open(os.path.join(acq, "MSScan.xsd"), 'w') as f:
            f.write(MSSCAN_XSD)
        with open(os.path.join(acq, "MSScan.bin"), 'wb') as f:
            f.write(b'\x00' * _POINTER_OFFSET)
        self.assertEqual(parse_allfiles(self.tmpdir), [])

    def test_mspeak_preferred_over_nothing(self):
        """When only MSPeak.bin (not MSProfile.bin) exists, it is parsed."""
        _make_standard_fixture(self.tmpdir)
        results = parse_allfiles(self.tmpdir)
        self.assertEqual(results[0].name, "MSPeak.bin")


class TestDataFileContract(unittest.TestCase):
    """Verify the returned DataFile satisfies rainbow's DataFile contract."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _make_standard_fixture(self.tmpdir, n_scans=5, bpp=16)
        self.result = parse_mspeak_data(
            os.path.join(self.tmpdir, "AcqData")
        )

    def test_xlabels_is_1d_numpy_array(self):
        self.assertIsInstance(self.result.xlabels, np.ndarray)
        self.assertEqual(self.result.xlabels.ndim, 1)

    def test_ylabels_is_1d_numpy_array(self):
        self.assertIsInstance(self.result.ylabels, np.ndarray)
        self.assertEqual(self.result.ylabels.ndim, 1)

    def test_data_is_2d_numpy_array(self):
        self.assertIsInstance(self.result.data, np.ndarray)
        self.assertEqual(self.result.data.ndim, 2)

    def test_data_rows_match_xlabels(self):
        self.assertEqual(self.result.data.shape[0],
                         self.result.xlabels.size)

    def test_data_cols_match_ylabels(self):
        self.assertEqual(self.result.data.shape[1],
                         self.result.ylabels.size)

    def test_metadata_is_dict(self):
        self.assertIsInstance(self.result.metadata, dict)

    def test_get_info_returns_string(self):
        self.assertIsInstance(self.result.get_info(), str)

    def test_extract_traces_all_labels(self):
        traces = self.result.extract_traces()
        self.assertEqual(traces.shape,
                         (self.result.ylabels.size,
                          self.result.xlabels.size))

    def test_extract_traces_single_label(self):
        label  = self.result.ylabels[0]
        traces = self.result.extract_traces(label)
        self.assertEqual(traces.shape[0], 1)
        self.assertEqual(traces.shape[1], self.result.xlabels.size)

    def test_extract_traces_label_list(self):
        labels = list(self.result.ylabels[:2])
        traces = self.result.extract_traces(labels)
        self.assertEqual(traces.shape[0], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
