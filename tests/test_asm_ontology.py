"""
Opt-in AFO ontology-conformance test.

Verifies that the controlled-vocabulary terms rainbow emits in ASM (data-cube
``concept`` values and ``device type`` values) are real classes in the
Allotrope Foundation Ontology (AFO). The JSON schema leaves these fields
free-form, so the ontology is the layer that catches a made-up term; this test
is what stops a typo or an invented label from slipping through.

Like the schema test, it is opt-in and network-dependent: it runs only when
``RAINBOW_TEST_ASM_SCHEMA=1`` is set and AFO is reachable, otherwise it skips.
It needs no extra dependency, querying the EBI Ontology Lookup Service (which
hosts AFO) over plain HTTP.

    RAINBOW_TEST_ASM_SCHEMA=1 pytest tests/test_asm_ontology.py

"""
import json
import os
import urllib.parse
import urllib.request

import pytest

import rainbow as rb


_OLS_SEARCH = "https://www.ebi.ac.uk/ols4/api/search"

# Fields in the ASM document whose values are AFO ontology classes (as opposed
# to free text or QUDT units, which the schema validates separately).
_ONTOLOGY_KEYS = ("device type", "concept")


pytestmark = pytest.mark.skipif(
    os.environ.get("RAINBOW_TEST_ASM_SCHEMA") != "1",
    reason="set RAINBOW_TEST_ASM_SCHEMA=1 to run the AFO ontology test")


def _collect_terms(node, out):
    """Gathers every ontology-class value used in an ASM document."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _ONTOLOGY_KEYS and isinstance(value, str):
                out.add(value)
            _collect_terms(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_terms(value, out)


def _afo_accession(term):
    """Returns the AFO id whose label equals ``term``, or None; skips offline."""
    url = (_OLS_SEARCH + "?q=" + urllib.parse.quote(term)
           + "&ontology=afo&rows=15")
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.load(response)
    except Exception as error:
        pytest.skip("could not reach EBI OLS for AFO: {}".format(error))
    for doc in data.get("response", {}).get("docs", []):
        if doc.get("label", "").lower() == term.lower():
            return doc.get("obo_id")
    return None


def _document_with_all_device_types():
    """An ASM document exercising every module device type rainbow emits.

    The single-file fixtures carry no instrument, so the module device types
    (diode array detector, pump, autosampler, column compartment) would never
    appear in the collected terms. This injects an instrument with one module
    of each kind, the way a sequence read does, so those terms are checked too.
    """
    datadir = rb.read("tests/inputs/red.D")
    datadir.metadata["instrument"] = {
        "name": "test-instrument",
        "modules": [
            {"name": "DAD", "type": "Detector", "part_no": "G7117B",
             "serial_no": "s1", "firmware": "f1"},
            {"name": "Quat. Pump", "type": "Pump", "part_no": "G7104A",
             "serial_no": "s2", "firmware": "f2"},
            {"name": "Multisampler", "type": "Auto sampler",
             "part_no": "G7167B", "serial_no": "s3", "firmware": "f3"},
            {"name": "Column Comp.", "type": "Column compartment",
             "part_no": "G7116B", "serial_no": "s4", "firmware": "f4"},
        ],
    }
    return datadir.to_asm()


def test_emitted_terms_are_afo_classes():
    terms = set()
    # A .D and a .dx together exercise both the chromatogram and spectrum cubes;
    # red.D adds a non-UV (CAD) detector, green.D adds the SIM MS mass
    # chromatogram (mass spectrometer device type, count measure), pink.D adds
    # the FID (flame ionization detector device type, electric current measure)
    # in a gas chromatography document; the instrument document adds every
    # module device type.
    for path in ("tests/inputs/red.D", "tests/inputs/teal.dx",
                 "tests/inputs/green.D", "tests/inputs/pink.D",
                 "tests/inputs/orange.D", "tests/inputs/bronze.D"):
        _collect_terms(rb.read(path).to_asm(), terms)
    _collect_terms(_document_with_all_device_types(), terms)

    # Guard that the key device types and measures are actually present. red.D's
    # CAD and pink.D's FID exercise "electric current"; orange.D's ELSD exercises
    # "intensity"; the faithful detector measures now in use.
    for required in ("diode array detector", "pump", "autosampler",
                     "column compartment", "liquid chromatography detector",
                     "mass spectrometer", "count", "flame ionization detector",
                     "electric current", "intensity",
                     "evaporative light scattering detector"):
        assert required in terms, "{} not exercised".format(required)

    resolved = {term: _afo_accession(term) for term in sorted(terms)}
    invalid = [term for term, accession in resolved.items() if accession is None]
    assert not invalid, "not valid AFO classes: {}".format(invalid)
