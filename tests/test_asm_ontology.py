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
import functools
import json
import os
import urllib.parse
import urllib.request

import pytest

import rainbow as rb


_OLS_BASE = "https://www.ebi.ac.uk/ols4/api"
_OLS_SEARCH = _OLS_BASE + "/search"

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


@functools.lru_cache(maxsize=None)
def _afo_term(term):
    """Returns the AFO class whose label equals ``term``, or None.

    Skips, loudly, when OLS cannot be reached, rather than passing on an
    unanswered question.
    """
    url = (_OLS_SEARCH + "?q=" + urllib.parse.quote(term)
           + "&ontology=afo&rows=15")
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.load(response)
    except Exception as error:
        pytest.skip("could not reach EBI OLS for AFO: {}".format(error))
    for doc in data.get("response", {}).get("docs", []):
        if doc.get("label", "").lower() == term.lower():
            return doc
    return None


def _afo_accession(term):
    """Returns the AFO id whose label equals ``term``, or None; skips offline."""
    doc = _afo_term(term)
    return doc.get("obo_id") if doc else None


def _document_with_all_device_types():
    """An ASM document exercising every module device type rainbow emits.

    The single-file fixtures carry no instrument, so the module device types
    (diode array detector, pump, autosampler, column compartment) would never
    appear in the collected terms. This injects an instrument with one module
    of each kind, the way a sequence read does, so those terms are checked too.

    Every detector class rainbow can name is included, since these labels are
    the only place a made-up term could hide: the JSON schema types device type
    as a free string, so nothing but the ontology checks them.

    Two documents, because a named class is kept only where the document's
    technique agrees with it: the LC modules would be neutralized to a class
    claiming no technique inside a gas chromatography document, and the GC ones
    inside a liquid chromatography document, so neither set can exercise its
    own label from a single document.
    """
    shared = [
        {"name": "Quat. Pump", "type": "Pump", "part_no": "G7104A",
         "serial_no": "s2", "firmware": "f2"},
        {"name": "Multisampler", "type": "Auto sampler",
         "part_no": "G7167B", "serial_no": "s3", "firmware": "f3"},
        {"name": "Column Comp.", "type": "Column compartment",
         "part_no": "G7116B", "serial_no": "s4", "firmware": "f4"},
    ]
    documents = []
    for fixture, technique, modules in (
            ("red.D", "LC", [
                {"name": "DAD", "type": "Detector", "part_no": "G7117B",
                 "serial_no": "s1", "firmware": "f1"},
                {"name": "VWD", "type": "Detector"},
                {"name": "RID1A", "type": "Detector"},
                {"name": "FLD1A", "type": "Detector"},
            ]),
            ("pink.D", "GC", [
                {"name": "TCD Back", "type": "Detector"},
                {"name": "ECD1", "type": "Detector"},
                {"name": "FID1", "type": "Detector"},
                # The same DAD in a GC document, which is where the neutral
                # absorbance class comes from.
                {"name": "DAD", "type": "Detector", "part_no": "G7117B"},
            ])):
        datadir = rb.read("tests/inputs/" + fixture)
        datadir.metadata["instrument"] = {
            "name": "test-instrument", "modules": shared + modules}
        documents.append(datadir.to_asm(technique=technique))
    return documents


def _gc_document_with_a_generic_detector():
    """A gas chromatography document whose detector AFO cannot name.

    The generic fallback follows the document's technique, so this is the only
    document that emits `gas chromatography detector`. Without it that label
    would go unchecked.
    """
    datadir = rb.read("tests/inputs/pink.D")
    datadir.metadata["acq_method"] = "TEST.M"
    datadir.metadata["modules"] = [{"name": "Analog/digital converter",
                                    "type": "Detector"}]
    return datadir.to_asm(technique="GC")


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
    for document in _document_with_all_device_types():
        _collect_terms(document, terms)
    _collect_terms(_gc_document_with_a_generic_detector(), terms)

    # Guard that the key device types and measures are actually present. red.D's
    # CAD and pink.D's FID exercise "electric current"; orange.D's ELSD exercises
    # "intensity"; the faithful detector measures now in use.
    for required in ("diode array detector", "pump", "autosampler",
                     "column compartment", "liquid chromatography detector",
                     "gas chromatography detector", "gas chromatograph",
                     "liquid chromatograph", "ultraviolet detector",
                     "refractive index detector", "fluorescence detector",
                     "thermal conductivity detector",
                     "electron capture detector",
                     "mass spectrometer", "count", "flame ionization detector",
                     "electric current", "intensity",
                     "electronic absorbance detector",
                     "evaporative light scattering detector"):
        assert required in terms, "{} not exercised".format(required)

    resolved = {term: _afo_accession(term) for term in sorted(terms)}
    invalid = [term for term, accession in resolved.items() if accession is None]
    assert not invalid, "not valid AFO classes: {}".format(invalid)


@functools.lru_cache(maxsize=None)
def _afo_ancestors(term):
    """The labels of every ancestor of the AFO class labelled ``term``.

    Returns None when ``term`` is not an AFO class at all, so a caller can
    tell "no ancestors" apart from "no such class". Skips offline.
    """
    doc = _afo_term(term)
    if doc is None:
        return None
    # The IRI has to come from the search response. Rebuilding it from the OBO
    # id does not work: the id is shaped AFO:equipment#AFE_0000711, so any
    # naive substitution yields a URL OLS answers with 200 and no terms, and
    # every ancestor query silently returns nothing.
    url = (_OLS_BASE + "/ontologies/afo/terms/"
           + urllib.parse.quote(urllib.parse.quote(doc["iri"], safe=""))
           + "/hierarchicalAncestors?size=200")
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.load(response)
    except Exception as error:
        pytest.skip("could not reach EBI OLS for AFO: {}".format(error))
    return frozenset(entry.get("label") for entry
                     in data.get("_embedded", {}).get("terms", []))


def test_the_ancestor_lookup_actually_returns_ancestors():
    """ A canary for the contradiction guard below.

    That guard passes when it finds no offending ancestor, so a lookup that
    silently returns nothing makes it vacuous, and a vacuous version of it
    shipped once already. This pins known-true facts about the AFO hierarchy,
    so the guard cannot go quiet without a test going red.
    """
    ultraviolet = _afo_ancestors("ultraviolet detector")
    assert ultraviolet is not None
    assert "liquid chromatography detector" in ultraviolet
    assert "electronic absorbance detector" in ultraviolet
    assert "gas chromatography detector" not in ultraviolet

    fid = _afo_ancestors("flame ionization detector")
    assert "gas chromatography detector" in fid
    assert "liquid chromatography detector" not in fid

    # The two classes rainbow substitutes must really claim no technique.
    for neutral in ("electronic absorbance detector", "chromatographic detector"):
        ancestors = _afo_ancestors(neutral)
        assert ancestors, neutral
        assert not ancestors & {"liquid chromatography detector",
                                "gas chromatography detector"}, neutral

    assert _afo_ancestors("not an afo class at all") is None


@pytest.mark.parametrize("fixture,technique,aggregate", [
    ("pink.D", None, "gas chromatography aggregate document"),
    ("red.D", "GC", "gas chromatography aggregate document"),
    ("teal.dx", "GC", "gas chromatography aggregate document"),
    ("red.D", None, "liquid chromatography aggregate document"),
    ("pink.D", "LC", "liquid chromatography aggregate document"),
])
def test_no_device_type_contradicts_its_documents_technique(
        fixture, technique, aggregate):
    """ A document must not assert a detector belongs to the other technique.

    AFO makes `liquid chromatography detector` and `gas chromatography
    detector` disjoint, and asserts one of them as a parent of most named
    detector classes: `ultraviolet detector` is defined as a component of an LC
    system, `flame ionization detector` of a GC system. So a UV channel riding
    along in a gas chromatography document cannot keep its own class without
    the document contradicting itself.

    Nothing else catches this. The schema types `device type` as a free string,
    and the label check above only asks whether a term exists, never where it
    sits. This walks the real hierarchy.
    """
    document = rb.read("tests/inputs/" + fixture).to_asm(technique=technique)
    assert aggregate in document, fixture
    terms = set()
    _collect_terms(document, terms)

    contradicted = "liquid chromatography detector" if "gas" in aggregate \
        else "gas chromatography detector"
    offenders, checked = {}, 0
    for term in sorted(terms):
        ancestors = _afo_ancestors(term)
        if ancestors is None:
            continue                       # not an AFO class, e.g. a unit
        checked += 1
        if contradicted in ancestors or term == contradicted:
            offenders[term] = sorted(ancestors & {
                "liquid chromatography detector",
                "gas chromatography detector"}) or [term]
    assert not offenders, (
        "{} ({}) asserts {}: {}".format(
            fixture, aggregate, contradicted, offenders))
    # Guard the guard: a document whose terms all failed to resolve would
    # otherwise pass while checking nothing.
    assert checked, "no term resolved to an AFO class, so nothing was checked"
