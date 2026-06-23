"""
Tests for the optional compiled accelerators.

These verify the contract that matters for the optional extensions: when a
compiled accelerator (:mod:`rainbow.agilent._uvdelta` for .uv decoding,
:mod:`rainbow.agilent._msprofile` for MassHunter MSProfile.bin) is present, it
produces output bit-identical to the pure-Python fallback, and it fails safely
on malformed input rather than reading out of bounds. The tests skip themselves
when an extension was not built.
"""
from pathlib import Path

import numpy as np
import pytest

from rainbow.agilent import chemstation as cs
from rainbow.agilent import masshunter as mh

# Every fixture .D directory that contains a .uv file, covering all decode
# paths: delta (brown=v31, red=v131), partial (green), and array/OL (pink).
UV_FIXTURES = ["brown", "red", "green", "pink"]


def _uv_path(color):
    directory = Path("tests") / "inputs" / (color + ".D")
    for entry in directory.iterdir():
        if entry.suffix.lower() == ".uv":
            return str(entry)
    return None


def _parse_pure_python(path):
    """Parse with the accelerator temporarily disabled."""
    saved = cs._uvdelta_fast
    cs._uvdelta_fast = None
    try:
        return cs.parse_uv(path)
    finally:
        cs._uvdelta_fast = saved


@pytest.mark.skipif(
    cs._uvdelta_fast is None, reason="compiled accelerator not built")
@pytest.mark.parametrize("color", UV_FIXTURES)
def test_uv_fast_matches_pure_python(color):
    """Compiled output is bit-identical to the pure-Python reference."""
    path = _uv_path(color)
    assert path is not None, f"no .uv fixture for {color}"
    fast = cs.parse_uv(path)
    slow = _parse_pure_python(path)
    np.testing.assert_array_equal(fast.data, slow.data)
    np.testing.assert_array_equal(fast.xlabels, slow.xlabels)
    np.testing.assert_array_equal(fast.ylabels, slow.ylabels)


@pytest.mark.skipif(
    cs._uvdelta_fast is None, reason="compiled accelerator not built")
def test_uv_truncated_input_raises():
    """A stream that ends mid-record raises instead of crashing."""
    truncated = b"\x00" * 64
    with pytest.raises(ValueError):
        cs._uvdelta_fast.decode_uv_delta(truncated, 0, 100, 106)


# Fixtures whose .ch channel files (CAD/ELSD/UV, format 130/30) exercise the
# _chdelta accelerator: brown=v30 UV, orange=v130 ELSD, red=v130 CAD + UV.
CH_FIXTURES = ["brown", "orange", "red"]


def _ch_paths(color):
    directory = Path("tests") / "inputs" / (color + ".D")
    return [str(entry) for entry in sorted(directory.iterdir())
            if entry.suffix.lower() == ".ch"]


def _parse_ch_pure_python(path):
    """Parse with the accelerator temporarily disabled."""
    saved = cs._chdelta_fast
    cs._chdelta_fast = None
    try:
        return cs.parse_ch(path)
    finally:
        cs._chdelta_fast = saved


@pytest.mark.skipif(
    cs._chdelta_fast is None, reason="compiled accelerator not built")
@pytest.mark.parametrize("color", CH_FIXTURES)
def test_ch_fast_matches_pure_python(color):
    """Compiled output is bit-identical to the pure-Python reference."""
    for path in _ch_paths(color):
        fast = cs.parse_ch(path)
        if fast is None or fast.detector == 'FID':
            continue  # FID uses a different (non-_chdelta) decoder
        slow = _parse_ch_pure_python(path)
        np.testing.assert_array_equal(fast.data, slow.data)
        np.testing.assert_array_equal(fast.xlabels, slow.xlabels)
        np.testing.assert_array_equal(fast.ylabels, slow.ylabels)
        assert fast.detector == slow.detector


@pytest.mark.skipif(
    cs._chdelta_fast is None, reason="compiled accelerator not built")
def test_ch_decode_delta_matches_reference():
    """The decode matches a hand-rolled reference, incl. the sentinel."""
    import struct
    # Two segments; the second sample uses the -0x8000 absolute sentinel.
    body = (struct.pack('>BB', 0x10, 3)
            + struct.pack('>h', 5) + struct.pack('>h', 10)
            + struct.pack('>h', -0x8000) + struct.pack('>i', 1000)
            + struct.pack('>BB', 0x10, 1) + struct.pack('>h', -4)
            + b'\x00')  # non-0x10 terminator
    out = cs._chdelta_fast.decode_delta(body, 0)
    # acc: 5, 15, then absolute 1000, then 1000-4 = 996.
    np.testing.assert_array_equal(out, [5, 15, 1000, 996])
    assert out.dtype == np.int64


@pytest.mark.skipif(
    cs._chdelta_fast is None, reason="compiled accelerator not built")
def test_ch_truncated_input_is_safe():
    """A stream that ends mid-record stops instead of reading OOB."""
    import struct
    # Header promises 4 samples but only one delta follows.
    truncated = struct.pack('>BB', 0x10, 4) + struct.pack('>h', 7)
    out = cs._chdelta_fast.decode_delta(truncated, 0)
    np.testing.assert_array_equal(out, [7])


# MassHunter Q-TOF profile fixtures whose run-length-encoded MSProfile.bin
# exercises the _msprofile accelerator.
MSPROFILE_FIXTURES = ["magenta.D", "cyan.D"]


def _msprofile_segments(fixture):
    """Yield (segment_body, num_mz) for every scan of a fixture."""
    acqdata = Path("tests") / "inputs" / fixture / "AcqData"
    complextypes = mh.parse_scan_xsd(str(acqdata / "MSScan.xsd"))
    records = mh.read_scan_records(str(acqdata / "MSScan.bin"), complextypes)
    with open(acqdata / "MSProfile.bin", 'rb') as f:
        for record in records:
            params = record['SpectrumParamValues']
            f.seek(params['SpectrumOffset'])
            segment = f.read(params['ByteCount'])
            yield memoryview(segment)[16:], params['PointCount']


@pytest.mark.skipif(
    mh._msprofile_fast is None, reason="compiled accelerator not built")
@pytest.mark.parametrize("fixture", MSPROFILE_FIXTURES)
def test_msprofile_fast_matches_pure_python(fixture):
    """Compiled RLE output is bit-identical to the pure-Python reference."""
    for body, num_mz in _msprofile_segments(fixture):
        fast = mh._msprofile_fast.decompress_inten_list(body, num_mz)
        slow = mh.decompress_inten_list(body, num_mz)
        np.testing.assert_array_equal(fast, slow)


@pytest.mark.skipif(
    mh._msprofile_fast is None, reason="compiled accelerator not built")
def test_msprofile_malformed_input_raises():
    """A bad width flag raises ValueError, like the pure-Python path."""
    import struct
    # Point-count word, negated leading-zero count, then a token stream that
    # opens at 4-byte width. A control with remainder 0 (-4 -> width flag 0) is
    # an invalid zero-width switch.
    bad = (struct.pack('<I', 5 | (0x90 << 24))
           + struct.pack('<i', 0) + struct.pack('<i', -4))
    with pytest.raises(ValueError):
        mh._msprofile_fast.decompress_inten_list(memoryview(bad), 5)
