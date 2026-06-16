"""
Tests for the optional compiled .uv accelerator.

These verify the contract that matters for the optional extension: when the
compiled accelerator (:mod:`rainbow.agilent._uvdelta`) is present, it produces
output bit-identical to the pure-Python fallback, and it fails safely on
truncated input rather than reading out of bounds. The tests skip themselves
when the extension was not built.
"""
import unittest
from pathlib import Path

import numpy as np

from rainbow.agilent import chemstation as cs

# Every fixture .D directory that contains a .uv file, covering all decode
# paths: delta (brown=v31, red=v131), partial (green), and array/OL (pink).
UV_FIXTURES = ["brown", "red", "green", "pink"]


def _uv_path(color):
    directory = Path("tests") / "inputs" / (color + ".D")
    for entry in directory.iterdir():
        if entry.suffix.lower() == ".uv":
            return str(entry)
    return None


@unittest.skipIf(cs._uvdelta_fast is None, "compiled accelerator not built")
class TestUVAccelerator(unittest.TestCase):

    def _parse_pure_python(self, path):
        """Parse with the accelerator temporarily disabled."""
        saved = cs._uvdelta_fast
        cs._uvdelta_fast = None
        try:
            return cs.parse_uv(path)
        finally:
            cs._uvdelta_fast = saved

    def test_fast_matches_pure_python(self):
        """Compiled output is bit-identical to the pure-Python reference."""
        for color in UV_FIXTURES:
            path = _uv_path(color)
            self.assertIsNotNone(path, f"no .uv fixture for {color}")
            with self.subTest(fixture=color):
                fast = cs.parse_uv(path)
                slow = self._parse_pure_python(path)
                np.testing.assert_array_equal(fast.data, slow.data)
                np.testing.assert_array_equal(fast.xlabels, slow.xlabels)
                np.testing.assert_array_equal(fast.ylabels, slow.ylabels)

    def test_truncated_input_raises(self):
        """A stream that ends mid-record raises instead of crashing."""
        truncated = b"\x00" * 64
        with self.assertRaises(ValueError):
            cs._uvdelta_fast.decode_uv_delta(truncated, 0, 100, 106)


if __name__ == "__main__":
    unittest.main()
