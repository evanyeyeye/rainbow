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


if __name__ == '__main__':
    unittest.main()
