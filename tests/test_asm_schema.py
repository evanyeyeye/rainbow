"""
Opt-in ASM schema-conformance test.

Validates rainbow's emitted ASM documents against the published Allotrope
liquid- and gas-chromatography JSON schemas (revision REC/2026/06, the revision
rainbow's manifests declare). This test is opt-in and network-dependent: it runs
only when ``RAINBOW_TEST_ASM_SCHEMA=1`` is set, ``jsonschema`` is installed (the
``validate`` extra), and the schemas can be fetched. It is skipped in CI, which
does not set the variable, mirroring how the LZF end-to-end tests are skipped
there.

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
                     rb.read("tests/inputs/teal.dx").to_asm(timezone=_TZ))


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
                   "start_time": 1.4, "end_time": 1.6, "symmetry": 0.95}],
    }]
    return datadir.to_asm(timezone=_TZ)


def test_rich_envelope_conforms_to_lc_schema():
    # Instrument modules (device system), injection document, and a processed
    # data peak list all validate against the published schema.
    _assert_conforms(_lc_validator(), _rich_lc_document())


def test_waters_uv_conforms_to_lc_schema():
    # violet.raw's _CHRO UV chromatograms report absorbance in AU, but the LC
    # schema pins the absorbance measure to mAU. The export must normalize AU to
    # mAU (and scale the values), or these measurements fail validation.
    _assert_conforms(_lc_validator(),
                     rb.read("tests/inputs/violet.raw").to_asm(timezone=_TZ))


def test_sim_ms_conforms_to_lc_schema():
    # green.D's single-ion (SIM) MS channels export as mass chromatogram cubes,
    # which the liquid-chromatography ADM admits.
    _assert_conforms(_lc_validator(),
                     rb.read("tests/inputs/green.D").to_asm(timezone=_TZ))


def test_cad_electric_current_conforms_to_lc_schema():
    # red.D's CAD channel now exports as an electric-current (pA) chromatogram,
    # a faithful generic detector cube the LC ADM admits (no longer absorbance).
    _assert_conforms(_lc_validator(),
                     rb.read("tests/inputs/red.D").to_asm(timezone=_TZ))


def test_elsd_intensity_conforms_to_lc_schema():
    # orange.D's ELSD channel exports as an intensity (RLU) chromatogram.
    _assert_conforms(_lc_validator(),
                     rb.read("tests/inputs/orange.D").to_asm(timezone=_TZ))


def test_masshunter_dad_conforms():
    # bronze.D reaches the same cubes through the MassHunter DAD parser rather
    # than the Chemstation one, so it is worth conforming in its own right.
    _assert_conforms(_lc_validator(),
                     rb.read("tests/inputs/bronze.D").to_asm(timezone=_TZ))


def _peaks_on(channel):
    return [{"signal": channel.split(".")[0].upper(), "wavelength": None,
             "description": None, "channel_file": channel,
             "peaks": [{"retention_time": 1.5, "area": 100.0, "height": 10.0,
                        "area_percent": 60.0, "height_percent": 55.0,
                        "start_time": 1.4, "end_time": 1.6, "symmetry": 0.95}]}]


def test_cad_with_peaks_relabels_and_conforms_to_lc_schema():
    # A CAD channel that carries integrated peaks is relabeled to absorbance so
    # the peak list can ride; the result still validates.
    datadir = rb.read("tests/inputs/red.D")
    datadir.peaks = _peaks_on("ADC1A.CH")
    _assert_conforms(_lc_validator(), datadir.to_asm(timezone=_TZ))


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
    return datadir.to_asm(timezone=_TZ, **to_asm_kwargs)


def test_fid_gc_run_conforms_to_gc_schema():
    # pink.D routes to a gas chromatography document (its FID channels export as
    # electric-current chromatograms; its DAD spectrum rides along).
    _assert_conforms(_gc_validator(), _rich_gc_document("tests/inputs/pink.D"))


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


def test_fid_with_peaks_relabels_and_conforms_to_gc_schema():
    # GC-FID peaks are the result of the run, so an FID channel with integrated
    # peaks is relabeled to absorbance to carry them; it still validates as a gas
    # chromatography document.
    datadir = rb.read("tests/inputs/pink.D")
    datadir.metadata["injection_volume"] = {"value": 1.0, "unit": "µL"}
    datadir.peaks = _peaks_on("DAD1A.ch")
    _assert_conforms(_gc_validator(), datadir.to_asm(timezone=_TZ))


# --- Timestamps ---


def test_the_format_checker_actually_rejects_a_bad_timestamp():
    """ The guard that the old suite lacked.

    Without a format checker, jsonschema treats `format` as an annotation and
    every timestamp passes, however malformed. This asserts the checker in use
    really does reject one, so the suite cannot go back to silently validating
    nothing.
    """
    document = rb.read("tests/inputs/red.D").to_asm(timezone=_TZ)
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
    it. A caller who knows where the instrument was passes timezone= (as every
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
        rb.read("tests/inputs/red.D").to_asm(timezone=_TZ)))
