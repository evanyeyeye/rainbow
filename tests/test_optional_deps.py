"""
Tests that rainbow imports and reads without its optional dependencies.

Reading a file needs numpy and nothing else. lxml only makes the XML faster
(rainbow.debug excepted, where its recovering parser is the whole point), and
matplotlib and pandas are needed only by the two calls that use them. These
pin that down by making a module unimportable and exercising the paths.
"""
import builtins
import importlib
import sys

import pytest

import rainbow as rb


class _Blocked:
    """A meta-path finder that makes ``name`` and its submodules unimportable."""

    def __init__(self, name):
        self.name = name

    def find_spec(self, name, path=None, target=None):
        if name == self.name or name.startswith(self.name + "."):
            raise ImportError(f"No module named {name!r}")
        return None


@pytest.fixture
def without_lxml():
    blocked = _Blocked("lxml")
    saved = {k: v for k, v in sys.modules.items() if k.startswith("lxml")}
    for key in saved:
        del sys.modules[key]
    sys.meta_path.insert(0, blocked)
    # Re-import the parsers so they bind the fallback rather than the lxml they
    # already hold.
    from rainbow.agilent import chemstation, masshunter
    importlib.reload(chemstation)
    importlib.reload(masshunter)
    try:
        yield
    finally:
        sys.meta_path.remove(blocked)
        sys.modules.update(saved)
        importlib.reload(chemstation)
        importlib.reload(masshunter)


def test_reading_matches_with_and_without_lxml(without_lxml):
    # The fallback has to parse to the same answer, not merely avoid raising.
    from rainbow.agilent import chemstation
    fallback = chemstation.parse_metadata("tests/inputs/red.D", [])
    assert fallback["vialpos"] == "23"


def test_masshunter_xsd_namespace_without_lxml(without_lxml):
    # This path read the schema namespace with an lxml-only XPath function.
    from rainbow.agilent import masshunter
    types = masshunter.parse_scan_xsd("tests/inputs/gold.D/AcqData/MSScan.xsd")
    assert types


def test_debug_xml_without_lxml_raises_a_useful_error(without_lxml):
    from rainbow.debug import xml as debug_xml
    importlib.reload(debug_xml)
    with pytest.raises(ImportError, match=r"lxml.*rainbow-api\[debug\]"):
        debug_xml.parse("tests/inputs/gold.D/AcqData/DefaultMassCal.xml")
    importlib.reload(debug_xml)


def test_importing_rainbow_does_not_pull_in_matplotlib_or_pandas():
    # Both are imported at the point of use, so a plain import must not load
    # them. They are the two slowest things rainbow depends on.
    code = (
        "import sys, rainbow; "
        "print('matplotlib' in sys.modules, 'pandas' in sys.modules)")
    import subprocess
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        check=True).stdout.strip()
    assert out == "False False"
