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


def test_emitted_terms_are_afo_classes():
    terms = set()
    # A .D and a .dx together exercise both the chromatogram and spectrum cubes.
    for path in ("tests/inputs/red.D", "tests/inputs/teal.dx"):
        _collect_terms(rb.read(path).to_asm(), terms)
    assert terms, "no ontology terms found in the ASM output"

    resolved = {term: _afo_accession(term) for term in sorted(terms)}
    invalid = [term for term, accession in resolved.items() if accession is None]
    assert not invalid, "not valid AFO classes: {}".format(invalid)
