"""
Opt-in ASM schema-conformance test.

Validates rainbow's emitted ASM documents against the published Allotrope
liquid- and gas-chromatography JSON schemas (revision REC/2026/06, the revision
rainbow's manifests declare). This test is opt-in and network-dependent: it runs
only when ``RAINBOW_TEST_ASM_SCHEMA=1`` is set, ``jsonschema`` is installed (the
``validate`` extra), and the schemas can be fetched. A dedicated CI job sets the
variable and runs it; the ordinary test matrix does not, so it skips there.

To run it locally::

    pip install -e .[validate]
    RAINBOW_TEST_ASM_SCHEMA=1 pytest tests/test_asm_schema.py

The official ``.tabular.embed`` schemas resolve their references internally, so
each is self-contained (no registry of side files needed). They are fetched
(not vendored) from purl.allotrope.org and cached on disk; they are CC-licensed
by the Allotrope Foundation.

"""
import json
import os
import tempfile
import urllib.request
from pathlib import Path

import pytest

import rainbow as rb


# The official self-contained embed schemas for the revision rainbow targets.
_REVISION = "REC/2026/06"
_BASE = "http://purl.allotrope.org/json-schemas/adm/"
_LC_URL = (_BASE + "liquid-chromatography/" + _REVISION +
           "/liquid-chromatography.tabular.embed.schema.json")
_GC_URL = (_BASE + "gas-chromatography/" + _REVISION +
           "/gas-chromatography.tabular.embed.schema.json")

_CACHE = Path(os.environ.get(
    "RAINBOW_ASM_SCHEMA_CACHE",
    Path(tempfile.gettempdir()) / "rainbow-asm-schemas" / "rec-2026-06"))


pytestmark = pytest.mark.skipif(
    os.environ.get("RAINBOW_TEST_ASM_SCHEMA") != "1",
    reason="set RAINBOW_TEST_ASM_SCHEMA=1 to run the ASM schema test")


# Most vendor formats record local wall clock with no UTC offset, and rainbow
# will not invent one (see rainbow.asm._iso_timestamp), so its default output
# carries offset-less timestamps. RFC 3339, which is what the schema's
# `format: date-time` means, requires an offset. These fixtures are therefore
# exported with an explicit offset, which is what a caller who knows where the
# instrument was would do. The default is covered separately below.
_TZ = "+00:00"


def _format_checker():
    """A format checker that actually checks ``date-time``.

    jsonschema treats ``format`` as an annotation unless a checker is supplied,
    and even with one it silently passes any format whose checker is not
    installed. So a bare ``FormatChecker()`` looks like it validates timestamps
    while checking nothing at all, which is how every non-ISO ``measurement
    time`` rainbow used to emit passed this suite. ``date-time`` needs
    rfc3339-validator, which the ``validate`` extra brings.
    """
    from jsonschema import FormatChecker

    checker = FormatChecker()
    if "date-time" not in checker.checkers:
        pytest.skip("date-time format checking needs rfc3339-validator: "
                    "pip install -e .[validate]")
    return checker


def _validator(url):
    """A validator for the embed schema at ``url``, skipping if unavailable."""
    pytest.importorskip("jsonschema", reason="pip install -e .[validate]")
    from jsonschema import Draft202012Validator

    cache = _CACHE / url.rsplit("/", 1)[1]
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                cache.write_bytes(response.read())
        except Exception as error:  # network down, file moved, etc.
            pytest.skip("could not fetch Allotrope schema {}: {}".format(
                url, error))
    return Draft202012Validator(json.loads(cache.read_text()),
                                format_checker=_format_checker())


def _lc_validator():
    return _validator(_LC_URL)


def _gc_validator():
    return _validator(_GC_URL)


def _assert_conforms(validator, document):
    errors = sorted(
        validator.iter_errors(document),
        key=lambda e: list(e.absolute_path))
    assert not errors, "\n".join(
        "@ {}: {}".format("/".join(map(str, e.absolute_path)), e.message)
        for e in errors[:10])


# --- Liquid chromatography ---


def test_dx_conforms_to_lc_schema():
    _assert_conforms(_lc_validator(),
                     rb.read("tests/inputs/teal.dx").to_asm(utc_offset=_TZ))


def _rich_lc_document():
    """An LC document exercising the instrument, injection, and peak envelope.

    The single-file fixtures carry no instrument or peaks, so this injects an
    instrument and a channel peak list onto a real .D the way a sequence read
    does, to validate the richer envelope against the schema.
    """
    datadir = rb.read("tests/inputs/red.D")
    datadir.metadata["instrument"] = {
        "name": "test-instrument",
        "modules": [
            {"name": "DAD", "type": "Detector", "part_no": "G7117B",
             "serial_no": "s1", "firmware": "f1"},
            {"name": "Quat. Pump", "type": "Pump", "part_no": "G7104A",
             "serial_no": "s2", "firmware": "f2"},
        ],
    }
    datadir.metadata["injection_volume"] = {"value": 1.0, "unit": "µL"}
    # Peaks attach to a UV channel: the ADM models a peak list only on an
    # absorbance measurement, not on the generic detector cubes (CAD etc.).
    channel = next(d.name for d in datadir.datafiles
                   if d.detector == "UV" and d.data.shape[1] == 1)
    datadir.peaks = [{
        "signal": channel.split(".")[0].upper(), "wavelength": 254.0,
        "description": None, "channel_file": channel,
        "peaks": [{"retention_time": 1.5, "area": 100.0, "height": 10.0,
                   "area_percent": 60.0, "height_percent": 55.0,
                   "start_time": 1.4, "end_time": 1.6, "symmetry": 0.95,
                   "baseline_start_code": "B", "baseline_end_code": "V",
                   "start_height": 0.0, "end_height": 1.25,
                   "baseline_start_time": 1.4, "baseline_end_time": 1.8}],
    }]
    return datadir.to_asm(utc_offset=_TZ)


def test_rich_envelope_conforms_to_lc_schema():
    # Instrument modules (device system), injection document, and a processed
    # data peak list all validate against the published schema.
    _assert_conforms(_lc_validator(), _rich_lc_document())


def test_a_sample_name_and_every_custom_datum_type_conform_to_lc_schema():
    # The sample document fields rainbow reads back off a foreign (Empower)
    # document and writes out again: `written name` beside the identifier, and
    # arbitrary named values in a custom information aggregate document. Both
    # are optional in the schema, so a wrong shape would pass every other test
    # here and only fail against a real validator.
    import datetime

    datadir = rb.read("tests/inputs/teal.dx")
    datadir.metadata["sample_name"] = "NB5-P1A11"
    # One of each datum type the schema admits, plus the `unit` sibling a double
    # may carry, since each is written under a different key.
    datadir.metadata["sample_custom"] = {
        "MaterialIdentifier": "Vax-033898",              # string
        "SampleWeight": 1.0,                             # double
        "Replicates": 3,                                 # double, written bare
        "Weight": {"value": 1.5, "unit": "mg"},          # double + unit
        "Passed": True,                                  # boolean
        "When": datetime.datetime(                       # timestamp
            2026, 4, 28, 13, 19, 56, tzinfo=datetime.timezone.utc),
    }
    _assert_conforms(_lc_validator(), datadir.to_asm(utc_offset=_TZ))


def test_waters_uv_conforms_to_lc_schema():
    # violet.raw's _CHRO UV chromatograms report absorbance in AU, but the LC
    # schema pins the absorbance measure to mAU. The export must normalize AU to
    # mAU (and scale the values), or these measurements fail validation.
    _assert_conforms(_lc_validator(),
                     rb.read("tests/inputs/violet.raw").to_asm(utc_offset=_TZ))


def test_sim_ms_conforms_to_lc_schema():
    # green.D's single-ion (SIM) MS channels export as mass chromatogram cubes,
    # which the liquid-chromatography ADM admits.
    _assert_conforms(_lc_validator(),
                     rb.read("tests/inputs/green.D").to_asm(utc_offset=_TZ))


def test_cad_electric_current_conforms_to_lc_schema():
    # red.D's CAD channel now exports as an electric-current (pA) chromatogram,
    # a faithful generic detector cube the LC ADM admits (no longer absorbance).
    _assert_conforms(_lc_validator(),
                     rb.read("tests/inputs/red.D").to_asm(utc_offset=_TZ))


def test_elsd_intensity_conforms_to_lc_schema():
    # orange.D's ELSD channel exports as an intensity (RLU) chromatogram.
    _assert_conforms(_lc_validator(),
                     rb.read("tests/inputs/orange.D").to_asm(utc_offset=_TZ))


def test_masshunter_dad_conforms():
    # bronze.D reaches the same cubes through the MassHunter DAD parser rather
    # than the Chemstation one, so it is worth conforming in its own right.
    _assert_conforms(_lc_validator(),
                     rb.read("tests/inputs/bronze.D").to_asm(utc_offset=_TZ))


def _peaks_on(channel):
    return [{"signal": channel.split(".")[0].upper(), "wavelength": None,
             "description": None, "channel_file": channel,
             "peaks": [{"retention_time": 1.5, "area": 100.0, "height": 10.0,
                        "area_percent": 60.0, "height_percent": 55.0,
                        "start_time": 1.4, "end_time": 1.6, "symmetry": 0.95}]}]


def test_cad_with_peaks_conforms_to_lc_schema():
    # A CAD channel that carries integrated peaks keeps its electric-current
    # cube, and its peak list in pA.s and pA is the one the schema's
    # picoampere detector defines.
    datadir = rb.read("tests/inputs/red.D")
    datadir.peaks = _peaks_on("ADC1A.CH")
    _assert_conforms(_lc_validator(), datadir.to_asm(utc_offset=_TZ))


def test_a_current_in_na_with_peaks_relabels_and_conforms_to_lc_schema():
    # nA has no peak list in the schema, so that channel alone is relabeled to
    # absorbance to carry its peaks, and the result still validates.
    datadir = rb.read("tests/inputs/red.D")
    datadir.get_file("ADC1A.CH").metadata["unit"] = "nA"
    datadir.peaks = _peaks_on("ADC1A.CH")
    _assert_conforms(_lc_validator(), datadir.to_asm(utc_offset=_TZ))


def test_a_relabeled_channel_re_exports_to_a_valid_document():
    # Export, read, export: the relabel note restores the channel's real unit,
    # and the second document validates.
    datadir = rb.read("tests/inputs/red.D")
    datadir.get_file("ADC1A.CH").metadata["unit"] = "nA"
    datadir.peaks = _peaks_on("ADC1A.CH")
    first = datadir.to_asm(utc_offset=_TZ)
    _assert_conforms(_lc_validator(), first)
    again = rb.from_asm(first, name=datadir.name).to_asm(utc_offset=_TZ)
    _assert_conforms(_lc_validator(), again)


def test_a_1_5_4_relabeled_channel_re_exports_to_a_valid_document():
    # 1.5.4 relabeled a CAD channel in pA and recorded the real measure only
    # as a sentence. Read back, it is a pA channel again, its peaks in pA.s.
    datadir = rb.read("tests/inputs/red.D")
    datadir.peaks = _peaks_on("ADC1A.CH")
    document = datadir.to_asm(utc_offset=_TZ)
    measurements = (document["liquid chromatography aggregate document"]
                    ["liquid chromatography document"][0]
                    ["measurement aggregate document"]["measurement document"])
    cad = next(m for m in measurements
               if m["measurement identifier"] == "ADC1A.CH")
    cad["chromatogram data cube"]["cube-structure"]["measures"][0].update(
        concept="absorbance", unit="mAU")
    for peak in (cad["processed data aggregate document"]
                 ["processed data document"][0]["peak list"]["peak"]):
        peak["peak area"]["unit"] = "mAU.s"
        peak["peak height"]["unit"] = "mAU"
    cad["custom information aggregate document"] = {
        "custom information document": [{
            "datum label": "reported measure",
            "scalar string datum": (
                "This channel measures electric current (in pA); its values "
                "are reported as absorbance in mAU so the integrated peak "
                "list can be carried, which the schema models only on an "
                "absorbance measurement.")}]}
    again = rb.from_asm(document, name=datadir.name).to_asm(utc_offset=_TZ)
    _assert_conforms(_lc_validator(), again)


def test_a_read_back_sample_role_and_plate_conform_to_lc_schema():
    # The sample role is a sample document property; the plate is not, so it
    # is written as custom information, and the document validates.
    datadir = rb.read("tests/inputs/red.D")
    datadir.metadata["sample_role"] = "standard sample role"
    datadir.metadata["well_plate_id"] = "Plate23"
    _assert_conforms(_lc_validator(), datadir.to_asm(utc_offset=_TZ))


def _property_names(schema, key, root=None):
    """Every property name the schema declares for objects under ``key``.

    A definition reached by a ``$ref`` ("#/$defs/electronicProjectRecord") is
    followed, by its last path segment, so a record declared once and
    referenced is still checked. Definitions are looked up in ``root``, the
    whole schema, when ``schema`` is a part of it.
    """
    names = set()
    definitions = {}

    def index(node):
        if isinstance(node, dict):
            for name, value in (node.get("$defs") or {}).items():
                definitions.setdefault(name.rsplit("/", 1)[-1], value)
            for value in node.values():
                index(value)
        elif isinstance(node, list):
            for value in node:
                index(value)

    index(root if root is not None else schema)
    followed = set()

    def collect(node):
        if not isinstance(node, dict):
            return
        names.update((node.get("properties") or {}).keys())
        for combinator in ("allOf", "anyOf", "oneOf"):
            for part in node.get(combinator) or []:
                collect(part)
        collect(node.get("items"))
        reference = node.get("$ref")
        if isinstance(reference, str) and "/$defs/" in reference:
            target = reference.rsplit("/", 1)[-1]
            if target not in followed and target in definitions:
                followed.add(target)
                collect(definitions[target])

    walked = set()

    def walk(node):
        if isinstance(node, dict):
            for name, value in node.items():
                if name == key:
                    collect(value)
                walk(value)
            # A part of the schema reaches its documents through references
            # too, so they are walked into when the whole schema is not.
            reference = node.get("$ref")
            if root is not None and isinstance(reference, str) \
                    and "/$defs/" in reference:
                target = reference.rsplit("/", 1)[-1]
                if target not in walked and target in definitions:
                    walked.add(target)
                    walk(definitions[target])
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return names


def test_processed_data_carries_only_names_the_schema_declares():
    # The embed schemas are not closed, so a property they do not declare
    # still validates. Each name rainbow writes in a processed data document,
    # or in its data processing document, is checked against the schema's
    # own list instead.
    schema = _lc_validator().schema
    allowed = {key: _property_names(schema, key) for key in (
        "processed data document", "data processing document")}
    assert "peak list" in allowed["processed data document"]
    # Without an offset: it takes utc_offset like every other timestamp, so
    # the dateTimeStamp the data processing document needs has one.
    processing = {"identifier": "1", "group_identifier": "g",
                  "time": "2025-09-18T11:42:38", "method_name": "m",
                  "method_version": "1", "type": "integration",
                  "description": "DAD: Signal A, 246.0 nm"}
    datadir = rb.read("tests/inputs/red.D")
    datadir.peaks = [dict(_peaks_on("DAD1B.ch")[0], processing=processing)]
    document = datadir.to_asm(utc_offset=_TZ)

    def documents(node):
        if isinstance(node, dict):
            for name, value in node.items():
                if name == "processed data document":
                    yield from (value if isinstance(value, list) else [value])
                yield from documents(value)
        elif isinstance(node, list):
            for value in node:
                yield from documents(value)

    written = list(documents(document))
    assert written
    for processed in written:
        names = {name for name in processed if not name.startswith("@")}
        assert names <= allowed["processed data document"], names
        method = processed["data processing document"]
        assert set(method) <= allowed["data processing document"], method
    _assert_conforms(_lc_validator(), document)


def test_a_document_rainbow_1_5_4_wrote_re_exports_to_a_valid_document():
    # tests/inputs/rainbow_1_5_4.asm.json was written by rainbow 1.5.4
    # (ff716a7) from red.D, with its CAD channel relabeled to carry peaks.
    with open("tests/inputs/rainbow_1_5_4.asm.json") as f:
        document = json.load(f)
    again = rb.from_asm(document, name="red.D").to_asm(utc_offset=_TZ)
    _assert_conforms(_lc_validator(), again)


def test_records_injection_time_and_role_written_back_conform():
    datadir = rb.read("tests/inputs/red.D")
    datadir.metadata.update({
        "injection_time": "2018-02-27T10:11:50",
        "sample_role": "not a role the schema has",
        "data_system": {"ASM file identifier": "A.JSON",
                        "data system instance identifier": "DB ID: 1",
                        "database primary key": "1",
                        "software name": "Empower 3 Software",
                        "Odd Field": "kept"},
        "analysis_sequence": {"written name": "SET_1",
                              "start time": "2026-04-10T18:11:45-04:00"},
        "project": {"written name": "P", "description": "d"}})
    _assert_conforms(_lc_validator(), datadir.to_asm(utc_offset=_TZ))


def _written(node, key):
    """Every object written under ``key`` anywhere in ``node``."""
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key:
                yield from (value if isinstance(value, list) else [value])
            yield from _written(value, key)
    elif isinstance(node, list):
        for value in node:
            yield from _written(value, key)


@pytest.mark.parametrize("url,run", [
    (_LC_URL, "tests/inputs/red.D"), (_LC_URL, "tests/inputs/brown.D"),
    (_LC_URL, "tests/inputs/blue.raw"), (_LC_URL, "tests/inputs/teal.dx"),
    (_GC_URL, "tests/inputs/yellow.D")])
def test_the_envelope_carries_only_names_the_schema_declares(url, run):
    # Like the processed data check above, for the sample, device control,
    # injection and once-per-file record documents rainbow writes. The
    # records, the role, the plate and the method are set as from_asm would
    # read them, so every write path is exercised.
    schema = _validator(url).schema
    datadir = rb.read(run)
    datadir.metadata.update({
        "injection_volume": {"value": 1.0, "unit": "uL"},
        "injection_time": "2018-02-27T10:11:50",
        "sample_name": "n", "sample_role": "blank role",
        "well_plate_id": "Plate23", "acq_method": "TEST.M",
        "data_system": {"data system instance identifier": "DB ID: 1",
                        "database primary key": "1",
                        "software name": "Empower 3 Software"},
        "analysis_sequence": {"written name": "SET_1",
                              "start time": "2026-04-10T18:11:45"},
        "project": {"written name": "P", "description": "d"}})
    document = datadir.to_asm(utc_offset=_TZ)
    for key in ("sample document", "device control document",
                "injection document", "data system document",
                "analysis sequence document", "electronic project record"):
        allowed = _property_names(schema, key)
        written = list(_written(document, key))
        assert written, key
        for item in written:
            names = {name for name in item if not name.startswith("@")}
            assert names <= allowed, (key, names - allowed)


def _measurement_variants(schema):
    """The measurement document's common part and its detector variants.

    The schema's measurement document is a common part, allOf'd with an
    anyOf over one definition per detector kind. Returns ``(common,
    [(reference, variant), ...])``.
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            for name, value in node.items():
                items = value.get("items") if isinstance(value, dict) else None
                if name == "measurement document" and isinstance(items, dict) \
                        and any("anyOf" in part
                                for part in items.get("allOf", [])):
                    found.append(items)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    items, = found
    common = [part for part in items["allOf"] if "anyOf" not in part]
    variants = []
    for part in items["allOf"]:
        for branch in part.get("anyOf", []):
            base, fragment = branch["$ref"].split("#")
            name = fragment.rsplit("/", 1)[-1]
            variants.append((branch["$ref"],
                             schema["$defs"][base]["$defs"][name]))
    return {"allOf": common}, variants


# The detector schema each measure has its own variant in, beside the
# chromatography-detectors definitions matched by their cube's measure.
_VARIANT_SCHEMAS = {
    ("chromatogram data cube", "absorbance"): "absorbance-cube-detector",
    ("three-dimensional ultraviolet spectrum data cube", "absorbance"):
        "absorbance-spectrum-detector",
    ("chromatogram data cube", "fluorescence"): "fluorescence-cube-detector",
    ("mass chromatogram data cube", "count"): "mass-chromatogram-cube",
}


def _matching_variants(variants, measurement):
    """The variants a written measurement is one of, by its cube."""
    import re
    key, = (name for name in measurement if name.endswith("data cube"))
    measure = measurement[key]["cube-structure"]["measures"][0]
    pattern = re.compile(
        r'"concept": \{"const": "%s"\}, "unit": \{"const": "%s"\}' % (
            re.escape(measure["concept"]), re.escape(measure["unit"])))
    dedicated = _VARIANT_SCHEMAS.get((key, measure["concept"]))
    return [variant for reference, variant in variants
            if (dedicated and dedicated in reference)
            or (key in variant.get("properties", {}) and pattern.search(
                json.dumps(variant["properties"][key])))]


@pytest.mark.parametrize("url,run", [
    (_LC_URL, "tests/inputs/red.D"), (_LC_URL, "tests/inputs/brown.D"),
    (_LC_URL, "tests/inputs/blue.raw"), (_LC_URL, "tests/inputs/teal.dx"),
    (_GC_URL, "tests/inputs/yellow.D")])
def test_each_device_control_matches_its_own_detector_variant(url, run):
    # Not against the union of every detector's names: a fluorescence
    # setting on an absorbance channel validates against the open schema all
    # the same, so each device control is checked against the common part
    # and the variant its own cube makes it. An FLD channel rides along.
    import numpy as np
    from rainbow.datafile import DataFile

    import copy

    schema = _validator(url).schema
    _, variants = _measurement_variants(schema)
    # What every measurement may carry: the schema's names with every
    # detector variant taken out.
    common = copy.deepcopy(schema)
    for reference, _ in variants:
        base, fragment = reference.split("#")
        common["$defs"][base]["$defs"].pop(fragment.rsplit("/", 1)[-1], None)
    datadir = rb.read(run)
    datadir.datafiles.append(DataFile(
        "FLD1A", "FLD", np.array([0.0, 1.0]), np.array([310.0]),
        np.array([[1.0], [2.0]]),
        {"unit": "RFU", "excitation_wavelength": 230.0,
         "excitation_bandwidth": 10.0, "emission_wavelength": 310.0,
         "bandwidth": 20.0}))
    # An FLD read out in mV is a voltage cube, whose variant declares no
    # excitation setting.
    datadir.datafiles.append(DataFile(
        "FLD1B", "FLD", np.array([0.0, 1.0]), np.array([310.0]),
        np.array([[1.0], [2.0]]),
        {"unit": "mV", "excitation_wavelength": 230.0,
         "excitation_bandwidth": 10.0, "emission_wavelength": 310.0}))
    document = datadir.to_asm(utc_offset=_TZ, ions=[131])
    measurements = list(_written(document, "measurement document"))
    assert any(m["measurement identifier"] == "FLD1A" for m in measurements)
    for measurement in measurements:
        matched = _matching_variants(variants, measurement)
        assert matched, measurement["measurement identifier"]
        allowed = _property_names(common, "device control document")
        for variant in matched:
            allowed |= _property_names(variant, "device control document",
                                       schema)
        for control in _written(measurement, "device control document"):
            names = {name for name in control if not name.startswith("@")}
            assert names <= allowed, (
                measurement["measurement identifier"], names - allowed)


def test_a_fluorescence_channel_read_from_asm_conforms_to_lc_schema():
    # An FLD channel rebuilt by from_asm exports as a fluorescence cube in RFU
    # with its peaks in RFU.s and RFU, the schema's fluorescence detector.
    import numpy as np
    from rainbow.datadirectory import DataDirectory
    from rainbow.datafile import DataFile

    fld = DataFile("FLR ChA", "FLD", np.array([0.0, 1.0, 2.0]),
                   np.array([340.0]), np.array([[0.0], [5.0], [0.0]]),
                   {"unit": "RFU", "excitation_wavelength": 280.0,
                    "emission_wavelength": 340.0})
    datadir = DataDirectory("run", [fld], {"date": "2026-04-10T18:46:25"})
    datadir.peaks = [{"signal": "FLR CHA", "channel_file": "FLR ChA",
                      "peaks": [{"retention_time": 1.0, "area": 50.0,
                                 "area_unit": "RFU.s", "height": 5.0,
                                 "height_unit": "RFU", "start_height": 0.0,
                                 "start_time": 0.5, "end_time": 1.5}]}]
    _assert_conforms(_lc_validator(), datadir.to_asm(utc_offset=_TZ))


# --- Gas chromatography (FID routing) ---


def _rich_gc_document(fixture, ** to_asm_kwargs):
    """A GC document with the injection metadata the GC schema requires.

    The gas-chromatography ADM requires an injection document (with a volume)
    on every measurement, which the bare fixtures do not record, so inject one
    the way a real method-rich run carries it.
    """
    datadir = rb.read(fixture)
    datadir.metadata["injection_volume"] = {"value": 1.0, "unit": "µL"}
    datadir.metadata["acq_method"] = "TEST.M"
    return datadir.to_asm(utc_offset=_TZ, **to_asm_kwargs)


def test_fid_gc_run_conforms_to_gc_schema():
    # yellow.D routes to a gas chromatography document: its FID channel exports
    # as an electric-current chromatogram.
    _assert_conforms(_gc_validator(), _rich_gc_document("tests/inputs/yellow.D"))


def test_gc_ms_run_conforms_to_gc_schema():
    # yellow.D is a GC-MS run: an FID channel plus SIM MS. The 2026/06 gas
    # chromatography ADM admits both the electric-current and mass chromatogram
    # cubes, so the whole run validates as one gas chromatography document.
    _assert_conforms(_gc_validator(),
                     _rich_gc_document("tests/inputs/yellow.D"))


def test_gc_scan_ion_extraction_conforms_to_gc_schema():
    # Naming ions of a GC-MS full scan pulls each as a mass chromatogram, still
    # within the gas chromatography document.
    _assert_conforms(
        _gc_validator(),
        _rich_gc_document("tests/inputs/yellow.D", ions=[131, 202]))


def test_cad_inside_a_gc_document_conforms():
    # A CAD channel forced into a gas chromatography document (electric-current
    # chromatogram) validates against the GC schema too.
    _assert_conforms(
        _gc_validator(),
        _rich_gc_document("tests/inputs/red.D", technique="GC"))


def test_elsd_inside_a_gc_document_conforms():
    _assert_conforms(
        _gc_validator(),
        _rich_gc_document("tests/inputs/orange.D", technique="GC"))


def test_fid_with_peaks_conforms_to_gc_schema():
    # GC-FID peaks are the result of the run. An FID channel with integrated
    # peaks keeps its electric-current cube and writes them in pA.s and pA,
    # which the gas chromatography document admits.
    datadir = rb.read("tests/inputs/yellow.D")
    datadir.metadata["injection_volume"] = {"value": 1.0, "unit": "µL"}
    datadir.peaks = _peaks_on("FID1A.ch")
    _assert_conforms(_gc_validator(), datadir.to_asm(utc_offset=_TZ))


# --- Timestamps ---


def test_the_format_checker_actually_rejects_a_bad_timestamp():
    """ The guard that the old suite lacked.

    Without a format checker, jsonschema treats `format` as an annotation and
    every timestamp passes, however malformed. This asserts the checker in use
    really does reject one, so the suite cannot go back to silently validating
    nothing.
    """
    document = rb.read("tests/inputs/red.D").to_asm(utc_offset=_TZ)
    measurements = (document["liquid chromatography aggregate document"]
                    ["liquid chromatography document"][0]
                    ["measurement aggregate document"]["measurement document"])
    measurements[0]["measurement time"] = "27-Feb-18, 10:11:50"
    errors = list(_lc_validator().iter_errors(document))
    assert errors, "a vendor-format timestamp must not validate"
    assert any("measurement time" in "/".join(map(str, e.absolute_path))
               for e in errors)


def test_the_default_export_is_iso_but_carries_no_invented_offset():
    """ rainbow will not fabricate a UTC offset the instrument never recorded.

    Chemstation records local wall clock with no zone, so the default export is
    ISO 8601 without an offset. That is deliberately not strict RFC 3339, which
    is what `format: date-time` means, so a strict validator flags it, and only
    it. A caller who knows where the instrument was passes utc_offset= (as every
    other test here does) and gets a fully conforming document.
    """
    document = rb.read("tests/inputs/red.D").to_asm()
    errors = list(_lc_validator().iter_errors(document))
    flagged = {"/".join(map(str, e.absolute_path)).rsplit("/", 1)[-1]
               for e in errors}
    # The timestamps, and nothing else: the offset is the only thing missing.
    assert flagged, "the offset-less default should be flagged"
    assert flagged <= {"measurement time", "injection time"}, flagged
    # Supplying the offset makes the same run fully conforming.
    assert not list(_lc_validator().iter_errors(
        rb.read("tests/inputs/red.D").to_asm(utc_offset=_TZ)))
