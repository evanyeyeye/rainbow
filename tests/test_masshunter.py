import os
import shutil
import struct
import tempfile
import unittest

import numpy as np
from lxml import etree

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


class TestMasshunter(unittest.TestCase):
    """
    Tests recovering the MS scan count without MSTS.xml.

    Agilent OpenLab .rslt/.sirslt result folders omit MSTS.xml, which the
    HRMS parser previously required to learn the number of scans. The count
    is now recovered by reading MSScan.bin to EOF. These tests confirm the
    recovered count exactly matches what MSTS.xml would have provided, and
    that parsing still works when MSTS.xml is absent entirely.

    These tests deliberately exercise only parse_scan_xsd / read_scan_records
    so they run without python-lzf (which is needed only to decompress
    MSProfile.bin) installed.

    """
    def _msts_scan_count(self, acqdata):
        """ Ground-truth scan count: sum of NumOfScans in MSTS.xml. """
        root = etree.parse(os.path.join(acqdata, "MSTS.xml")).getroot()
        return sum(int(seg.find("NumOfScans").text)
                   for seg in root.findall("TimeSegment"))

    def test_scan_count_matches_msts(self):
        """ Counting MSScan.bin records reproduces the MSTS.xml scan count. """
        complextypes = masshunter.parse_scan_xsd(
            os.path.join(YELLOW_ACQDATA, "MSScan.xsd"))
        records = masshunter.read_scan_records(
            os.path.join(YELLOW_ACQDATA, "MSScan.bin"), complextypes)
        self.assertEqual(len(records), self._msts_scan_count(YELLOW_ACQDATA))

    def test_read_scan_records_well_formed(self):
        """ The recovered records are exact and carry sane scan times. """
        complextypes = masshunter.parse_scan_xsd(
            os.path.join(YELLOW_ACQDATA, "MSScan.xsd"))
        records = masshunter.read_scan_records(
            os.path.join(YELLOW_ACQDATA, "MSScan.bin"), complextypes)

        # Each record is a parsed ScanRecordType dict carrying a ScanTime.
        self.assertTrue(all('ScanTime' in r for r in records))
        # Retention time advances monotonically across the run, confirming we
        # parsed real records rather than running off into garbage bytes.
        times = [r['ScanTime'] for r in records]
        self.assertTrue(all(t2 >= t1 for t1, t2 in zip(times, times[1:])))

    def test_count_without_msts_xml(self):
        """ The count is recovered even when MSTS.xml is absent (the
        .rslt/.sirslt case). Copy only the files the new path needs. """
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("MSScan.xsd", "MSScan.bin"):
                shutil.copy(os.path.join(YELLOW_ACQDATA, name), tmp)
            self.assertFalse(os.path.exists(os.path.join(tmp, "MSTS.xml")))

            complextypes = masshunter.parse_scan_xsd(
                os.path.join(tmp, "MSScan.xsd"))
            records = masshunter.read_scan_records(
                os.path.join(tmp, "MSScan.bin"), complextypes)
            self.assertEqual(
                len(records), self._msts_scan_count(YELLOW_ACQDATA))


class TestMasshunterProfile(unittest.TestCase):
    """
    Tests parsing run-length-encoded MSProfile.bin (HRMS) data (issue #27).

    Q-TOF profile acquisitions store intensities with a run-length encoding
    instead of LZF compression, which made the parser raise "error in
    compressed data" (and, on newer files, fail to even read MSScan.xsd
    because its type names are namespace-prefixed). These tests parse trimmed
    real fixtures end to end and cross-check the decoded intensities against an
    independent value stored in MSScan.bin.

    They run without python-lzf installed, since RLE data does not use it.

    """
    def _records(self, acqdata):
        complextypes = masshunter.parse_scan_xsd(
            os.path.join(acqdata, "MSScan.xsd"))
        return masshunter.read_scan_records(
            os.path.join(acqdata, "MSScan.bin"), complextypes)

    def _assert_decodes(self, directory):
        """ Parses the fixture and checks each scan's decoded maximum
        intensity against the MaxY field stored independently in MSScan.bin. """
        datafiles = masshunter.parse_allfiles(directory)
        self.assertEqual(len(datafiles), 1)
        datafile = datafiles[0]

        acqdata = os.path.join(directory, "AcqData")
        records = self._records(acqdata)
        # One retention time per scan record; MSProfile.bin parsed to a grid.
        self.assertEqual(datafile.data.shape[0], len(records))
        self.assertEqual(datafile.xlabels.size, len(records))
        self.assertEqual(datafile.data.shape[1], datafile.ylabels.size)

        with open(os.path.join(acqdata, "MSProfile.bin"), 'rb') as f:
            for record in records:
                params = record['SpectrumParamValues']
                f.seek(params['SpectrumOffset'])
                segment = f.read(params['ByteCount'])
                # The segment must be recognized as RLE (not mistaken for LZF).
                self.assertTrue(
                    masshunter.segment_is_rle(segment, params['PointCount']))
                inten = masshunter.decompress_inten_list(
                    memoryview(segment)[16:], params['PointCount'])
                self.assertEqual(inten.size, params['PointCount'])
                # MaxY is the per-scan maximum intensity, stored separately from
                # the intensity stream - a strong independent decode check.
                self.assertEqual(int(inten.max()), int(params['MaxY']))

    def test_magenta_profile_decodes(self):
        """ Older-format RLE profile data (issue #27) parses and decodes. """
        self._assert_decodes(MAGENTA_D)

    def test_cyan_profile_decodes(self):
        """ Newer-format (namespace-prefixed XSD) RLE profile data parses. """
        self._assert_decodes(CYAN_D)

    def test_rle_not_confused_with_lzf(self):
        """ segment_is_rle only fires on the real signature. """
        records = self._records(os.path.join(MAGENTA_D, "AcqData"))
        params = records[0]['SpectrumParamValues']
        num_mz = params['PointCount']
        with open(os.path.join(MAGENTA_D, "AcqData", "MSProfile.bin"), 'rb') as f:
            f.seek(params['SpectrumOffset'])
            segment = f.read(params['ByteCount'])
        self.assertTrue(masshunter.segment_is_rle(segment, num_mz))
        # Wrong point count -> not RLE (the embedded length must match).
        self.assertFalse(masshunter.segment_is_rle(segment, num_mz + 1))
        # Arbitrary/LZF-like bytes lack the 0x90 marker word -> not RLE.
        self.assertFalse(masshunter.segment_is_rle(b"\x00" * 32, num_mz))

    def test_mass_calibration_in_range(self):
        """ The calibrated mz axis spans a sensible HRMS range. """
        datafile = masshunter.parse_allfiles(CYAN_D)[0]
        self.assertGreater(datafile.ylabels.min(), 100)
        self.assertLess(datafile.ylabels.max(), 5000)
        self.assertTrue((datafile.ylabels[1:] > datafile.ylabels[:-1]).all())

    def _scan_axis(self, directory, scan_index, use_polynomial=True):
        """ Decoded intensities and calibrated mz for one scan of a fixture. """
        acqdata = os.path.join(directory, "AcqData")
        records = self._records(acqdata)
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

    def test_polynomial_calibration_matches_bioconfirm(self):
        """ The polynomial calibration reproduces the m/z Agilent reports, and
        is meaningfully more accurate than the traditional calibration alone. """
        for directory, truth in BIOCONFIRM_APEX_MZ.items():
            with self.subTest(fixture=directory):
                inten, mzs = self._scan_axis(directory, 0)
                apex = mzs[int(np.argmax(inten))]
                self.assertAlmostEqual(apex, truth, places=3)
                # The polynomial term is actually applied (primary differs and
                # is further from the truth).
                _, mzs_primary = self._scan_axis(
                    directory, 0, use_polynomial=False)
                apex_primary = mzs_primary[int(np.argmax(inten))]
                self.assertNotAlmostEqual(apex_primary, apex, places=5)
                self.assertLess(abs(apex - truth), abs(apex_primary - truth))

    def test_malformed_rle_raises_valueerror(self):
        """ A corrupt RLE stream raises a clear ValueError, not a cryptic
        KeyError/struct.error/silent wraparound. """
        # 4-byte point-count word, then negated (init_zero_repeat, width_flag).
        def stream(init_zero_repeat, width_flag, tail):
            return (struct.pack('<I', 5 | (0x90 << 24))
                    + struct.pack('<ii', -init_zero_repeat, -width_flag) + tail)

        # Token -4 -> divmod(4, 4) = (1, 0): a zero-width switch is invalid.
        bad_width = stream(0, 1, struct.pack('<b', -4))
        with self.assertRaises(ValueError):
            masshunter.decompress_inten_list(memoryview(bad_width)[0:], 5)

        # A positive initial zero-repeat would start the write index negative.
        neg_index = stream(-3, 1, b"")
        with self.assertRaises(ValueError):
            masshunter.decompress_inten_list(memoryview(neg_index)[0:], 5)

        # More literals than the point count must not overflow silently.
        too_many = stream(0, 1, struct.pack('<b', 7) * 9)
        with self.assertRaises(ValueError):
            masshunter.decompress_inten_list(memoryview(too_many)[0:], 5)


class TestMasshunterMultiBlock(unittest.TestCase):
    """
    Tests parsing MassHunter profile data whose scans also store centroids.

    When an acquisition writes MSPeak.bin alongside MSProfile.bin, each
    ScanRecordType holds a profile block *and* a centroid block. The reader must
    step over the extra block at the true record stride (rather than mis-parsing
    it as the next scan), recover the m/z calibration from DefaultMassCal.xml
    when the per-scan MSMassCal.bin is absent, and keep the complete scans of an
    interrupted acquisition whose trailing MSProfile.bin segments were never
    written.
    """
    def _acqdata(self, directory):
        return os.path.join(directory, "AcqData")

    def _complextypes(self, directory):
        return masshunter.parse_scan_xsd(
            os.path.join(self._acqdata(directory), "MSScan.xsd"))

    def test_type_size_matches_reader(self):
        """ type_size predicts the bytes read_complextype consumes, which is
        what lets read_scan_records reason about the record stride. """
        ctd = self._complextypes(GOLD_D)
        # SpectrumParamsType is the 64-byte block that repeats per scan.
        self.assertEqual(masshunter.type_size(ctd, "SpectrumParamsType"), 64)

        path = os.path.join(self._acqdata(GOLD_D), "MSScan.bin")
        with open(path, 'rb') as f:
            f.seek(0x58)
            f.seek(struct.unpack('<I', f.read(4))[0])
            start = f.tell()
            masshunter.read_complextype(f, ctd, "ScanRecordType")
            consumed = f.tell() - start
        self.assertEqual(consumed, masshunter.type_size(ctd, "ScanRecordType"))

    def test_fixtures_lack_msmasscal(self):
        """ These fixtures intentionally have no per-scan MSMassCal.bin, so they
        exercise the DefaultMassCal.xml fallback. """
        for directory in (GOLD_D, COPPER_D):
            self.assertFalse(os.path.exists(
                os.path.join(self._acqdata(directory), "MSMassCal.bin")))

    def test_two_block_records_read_at_correct_stride(self):
        """ Two-block records are read one per scan, not mis-split into extra
        single-block records, and carry monotonic scan times. """
        acqdata = self._acqdata(GOLD_D)
        records = masshunter.read_scan_records(
            os.path.join(acqdata, "MSScan.bin"),
            self._complextypes(GOLD_D), masshunter.count_scans(acqdata))
        self.assertEqual(len(records), 3)
        times = [r['ScanTime'] for r in records]
        self.assertTrue(all(t2 >= t1 for t1, t2 in zip(times, times[1:])))

    def test_stride_inferred_without_msts(self):
        """ The two-block stride is recovered from the record geometry alone -
        i.e. parsing still finds all four records if MSTS.xml is unavailable. """
        acqdata = self._acqdata(COPPER_D)
        records = masshunter.read_scan_records(
            os.path.join(acqdata, "MSScan.bin"),
            self._complextypes(COPPER_D), None)
        self.assertEqual(len(records), 4)

    @unittest.skipUnless(HAVE_LZF, "python-lzf required to decode LZF MSProfile.bin")
    def test_gold_parses_with_default_masscal(self):
        """ gold parses end to end to a profile grid with a sensible TOF m/z
        axis, calibrated from DefaultMassCal.xml (no MSMassCal.bin). """
        datafile = masshunter.parse_allfiles(GOLD_D)[0]
        self.assertEqual(datafile.data.shape[0], 3)               # 3 scans
        self.assertEqual(datafile.xlabels.size, 3)
        self.assertEqual(datafile.data.shape[1], datafile.ylabels.size)
        self.assertGreater(datafile.ylabels.min(), 50)
        self.assertLess(datafile.ylabels.max(), 2000)
        self.assertTrue((datafile.ylabels[1:] > datafile.ylabels[:-1]).all())

    def test_default_masscal_row_matches_msmasscal(self):
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

    @unittest.skipUnless(HAVE_LZF, "python-lzf required to decode LZF MSProfile.bin")
    def test_incomplete_acquisition_keeps_complete_scans(self):
        """ copper's MSScan.bin describes four scans but MSProfile.bin holds
        only three; parsing keeps the three complete scans rather than failing
        on the truncated segment. """
        datafile = masshunter.parse_allfiles(COPPER_D)[0]
        self.assertEqual(datafile.data.shape[0], 3)
        self.assertEqual(datafile.xlabels.size, 3)


if __name__ == '__main__':
    unittest.main()
