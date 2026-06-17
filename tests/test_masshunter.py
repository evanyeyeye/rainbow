import os
import shutil
import tempfile
import unittest
from lxml import etree

from rainbow.agilent import masshunter


# The `yellow` fixture is a MassHunter GC-MS acquisition whose AcqData folder
# contains MSScan.xsd, MSScan.bin, and MSTS.xml (but no MSProfile.bin). It
# gives us a ground-truth scan count from MSTS.xml to validate the
# MSTS.xml-independent counting against.
YELLOW_ACQDATA = os.path.join("tests", "inputs", "yellow.D", "AcqData")

# `magenta` and `cyan` are the first three scans of two real Q-TOF profile
# acquisitions from issue #27, whose MSProfile.bin intensities are run-length
# encoded rather than LZF-compressed. They cover the two format variants we
# have seen:
#   - magenta: older MSScan.xsd (bare type names); UncompressedByteCount > 0.
#   - cyan: newer MSScan.xsd (namespace-prefixed type names, e.g.
#       "mstns:ScanRecordType"); UncompressedByteCount == 0.
# Neither folder contains MSTS.xml, so they also exercise the MSTS-independent
# scan counting. Both decode without python-lzf installed.
MAGENTA_D = os.path.join("tests", "inputs", "magenta.D")
CYAN_D = os.path.join("tests", "inputs", "cyan.D")


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


if __name__ == '__main__':
    unittest.main()
