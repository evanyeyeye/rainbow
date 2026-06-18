import os
import shutil
import tempfile
import unittest

import rainbow as rb


class TestVendorDetection(unittest.TestCase):
    """
    Unit tests for rb.read's vendor dispatch: extension first, content sniffing
    for unsuffixed directories, and the explicit ``format`` override.

    """
    WATERS_FIXTURE = os.path.join("tests", "inputs", "blue.raw")
    AGILENT_FIXTURE = os.path.join("tests", "inputs", "brown.D")

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _copy_without_suffix(self, fixture, new_name):
        """Copy a .raw/.D fixture to a folder whose name has no vendor suffix."""
        dest = os.path.join(self.tmp, new_name)
        shutil.copytree(fixture, dest)
        return dest

    def test_extension_still_dispatches(self):
        # The conventional suffixes must keep working exactly as before.
        self.assertEqual(rb.read(self.WATERS_FIXTURE).metadata["vendor"],
                         "Waters")
        self.assertIn("Agilent",
                      rb.read(self.AGILENT_FIXTURE).metadata["vendor"])

    def test_sniffs_waters_without_suffix(self):
        path = self._copy_without_suffix(self.WATERS_FIXTURE, "Noscapine 3")
        self.assertEqual(rb.read(path).metadata["vendor"], "Waters")

    def test_sniffs_agilent_without_suffix(self):
        path = self._copy_without_suffix(self.AGILENT_FIXTURE, "renamed_run")
        self.assertIn("Agilent", rb.read(path).metadata["vendor"])

    def test_format_override(self):
        path = self._copy_without_suffix(self.WATERS_FIXTURE, "anything")
        self.assertEqual(rb.read(path, format="waters").metadata["vendor"],
                         "Waters")

    def test_invalid_format_raises(self):
        self.assertRaises(
            Exception, rb.read, self.WATERS_FIXTURE, format="thermo")

    def test_unknown_directory_raises(self):
        empty = os.path.join(self.tmp, "not_a_dataset")
        os.makedirs(empty)
        open(os.path.join(empty, "readme.txt"), "w").close()
        self.assertRaises(Exception, rb.read, empty)

    def test_detect_vendor_helpers(self):
        waters = self._copy_without_suffix(self.WATERS_FIXTURE, "w")
        agilent = self._copy_without_suffix(self.AGILENT_FIXTURE, "a")
        self.assertEqual(rb._detect_vendor(waters), "waters")
        self.assertEqual(rb._detect_vendor(agilent), "agilent")
        self.assertIsNone(rb._detect_vendor(self.tmp))
        # Extension takes precedence over (and short-circuits) content.
        self.assertEqual(rb._detect_vendor(self.WATERS_FIXTURE), "waters")
        self.assertEqual(rb._detect_vendor(self.AGILENT_FIXTURE), "agilent")

    def test_read_metadata_sniffs(self):
        path = self._copy_without_suffix(self.WATERS_FIXTURE, "md_test")
        self.assertEqual(
            rb.read_metadata(path)["metadata"]["vendor"], "Waters")


if __name__ == "__main__":
    unittest.main()
