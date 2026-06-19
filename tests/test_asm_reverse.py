"""
Tests for the reverse ASM conversion (from_asm): an ASM document back into
rainbow DataDirectory/DataFile objects, round-tripping with to_asm.

"""
import json

import numpy as np
import pytest

import rainbow as rb
from rainbow import asm


@pytest.fixture(params=["tests/inputs/teal.dx", "tests/inputs/red.D"])
def original(request):
    return rb.read(request.param)


def test_from_asm_reconstructs_uv_datafiles(original):
    rebuilt = rb.from_asm(original.to_asm())

    # to_asm emits exactly the UV files; from_asm reconstructs the same set.
    uv = {df.name: df for df in original.datafiles if df.detector == 'UV'}
    rebuilt_files = {df.name: df for df in rebuilt.datafiles}
    assert set(rebuilt_files) == set(uv)

    for name, source in uv.items():
        copy = rebuilt_files[name]
        assert copy.detector == 'UV'
        assert copy.data.shape == source.data.shape
        # Retention time survives the minutes -> seconds -> minutes round-trip.
        np.testing.assert_allclose(
            copy.xlabels, source.xlabels, rtol=1e-9, atol=1e-9)
        # The decoded values survive exactly (no lossy step in between).
        np.testing.assert_allclose(
            copy.data, source.data, rtol=1e-9, atol=1e-9)


def test_from_asm_unflattens_the_spectrum_grid():
    original = rb.read("tests/inputs/teal.dx")
    rebuilt = rb.from_asm(original.to_asm())
    source = original.get_file("DAD1I.UV")
    copy = {df.name: df for df in rebuilt.datafiles}["DAD1I.UV"]

    assert copy.data.shape == source.data.shape
    np.testing.assert_allclose(copy.ylabels, source.ylabels, rtol=1e-9)
    np.testing.assert_allclose(copy.data, source.data, rtol=1e-9, atol=1e-9)


def test_from_asm_reconstructs_directory_metadata():
    original = rb.read("tests/inputs/red.D")
    rebuilt = rb.from_asm(original.to_asm())
    # red.D carries a sample name and date but no operator.
    assert rebuilt.metadata.get("sample") == "usp"
    assert rebuilt.metadata.get("date") == original.metadata["date"]
    assert "operator" not in rebuilt.metadata


def test_chromatogram_channel_recovers_wavelength():
    original = rb.read("tests/inputs/red.D")
    rebuilt = rb.from_asm(original.to_asm())
    channel = {df.name: df for df in rebuilt.datafiles}["DAD1B.ch"]
    assert channel.metadata["wavelength"] == 280.0
    assert channel.ylabels.tolist() == [280.0]


def test_to_asm_from_asm_to_asm_is_stable():
    # The ASM document is the canonical form: re-deriving it through from_asm
    # reproduces it (numbers compared with tolerance via JSON round-trip).
    original = rb.read("tests/inputs/teal.dx")
    document = original.to_asm()
    redone = rb.from_asm(document).to_asm()

    # Structure and strings identical; numeric arrays within tolerance.
    assert _strip_numbers(redone) == _strip_numbers(document)
    np.testing.assert_allclose(
        _all_numbers(redone), _all_numbers(document), rtol=1e-9, atol=1e-9)


def _strip_numbers(node):
    """A copy of the structure with all floats/ints replaced by a placeholder."""
    if isinstance(node, dict):
        return {k: _strip_numbers(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_numbers(v) for v in node]
    if isinstance(node, bool):
        return node
    if isinstance(node, (int, float)):
        return "#"
    return node


def _all_numbers(node):
    """Every numeric leaf, in document order."""
    out = []
    def walk(n):
        if isinstance(n, dict):
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
        elif isinstance(n, bool):
            pass
        elif isinstance(n, (int, float)):
            out.append(n)
    walk(node)
    return out
