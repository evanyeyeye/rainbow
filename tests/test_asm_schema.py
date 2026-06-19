"""
Opt-in ASM schema-conformance test.

Validates rainbow's emitted ASM document against the published Allotrope
liquid-chromatography JSON schema. This test is opt-in and network-dependent:
it runs only when ``RAINBOW_TEST_ASM_SCHEMA=1`` is set, ``jsonschema`` is
installed (the ``validate`` extra), and the schemas can be fetched. It is
skipped in CI, which does not set the variable, mirroring how the LZF
end-to-end tests are skipped there.

To run it locally::

    pip install -e .[validate]
    RAINBOW_TEST_ASM_SCHEMA=1 pytest tests/test_asm_schema.py

The Allotrope schemas are fetched (not vendored) from a pinned commit and
cached on disk; they are CC-licensed by the Allotrope Foundation.

"""
import json
import os
import tempfile
import urllib.request
from pathlib import Path

import pytest

import rainbow as rb


# A pinned snapshot of Benchling-Open-Source/allotropy, so the schema cannot
# change underneath the test.
_COMMIT = "f8f0bebb03aeaee6edba3781f35770133ea19d22"
_RAW = ("https://raw.githubusercontent.com/Benchling-Open-Source/allotropy/"
        + _COMMIT + "/src/allotropy/allotrope/schemas/")

# The liquid-chromatography schema and its transitive $ref closure (the only
# files needed to resolve every reference while validating).
_ROOT = ("adm/liquid-chromatography/BENCHLING/2023/09/"
         "liquid-chromatography.schema.json")
_SCHEMA_FILES = (
    _ROOT,
    "adm/chromatography/BENCHLING/2024/11/flow-rate-cube-detector.schema.json",
    "adm/chromatography/BENCHLING/2024/11/ph-cube-detector.schema.json",
    "adm/chromatography/BENCHLING/2024/11/pressure-cube-detector.schema.json",
    "adm/chromatography/BENCHLING/2024/11/solvent-cube-detector.schema.json",
    "adm/chromatography/BENCHLING/2024/11/temperature-cube-detector.schema.json",
    "adm/chromatography/REC/2023/09/chromatography-detectors.schema.json",
    "adm/conductivity/REC/2023/09/conductivity-cube-detection.schema.json",
    "adm/core/REC/2023/09/core.schema.json",
    "adm/core/REC/2023/09/cube.schema.json",
    "adm/core/REC/2023/09/hierarchy.schema.json",
    "adm/core/REC/2023/09/manifest.schema.json",
    "adm/fluorescence/BENCHLING/2024/11/fluorescence-cube-detector.schema.json",
    "adm/mass-spectrometry/REC/2023/09/"
    "mass-chromatogram-cube-detection.schema.json",
    "adm/ultraviolet-absorbance/REC/2023/09/"
    "ultraviolet-absorbance-cube-detection.schema.json",
    "adm/ultraviolet-absorbance/REC/2023/09/"
    "ultraviolet-absorbance-spectrum-detection.schema.json",
    "qudt/REC/2023/09/units.schema.json",
)

_CACHE = Path(os.environ.get(
    "RAINBOW_ASM_SCHEMA_CACHE",
    Path(tempfile.gettempdir()) / "rainbow-asm-schemas" / _COMMIT))


pytestmark = pytest.mark.skipif(
    os.environ.get("RAINBOW_TEST_ASM_SCHEMA") != "1",
    reason="set RAINBOW_TEST_ASM_SCHEMA=1 to run the ASM schema test")


def _ensure_schemas():
    """Downloads any not-yet-cached schema files; skips the test on failure."""
    for relpath in _SCHEMA_FILES:
        dest = _CACHE / relpath
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(_RAW + relpath, timeout=30) as response:
                dest.write_bytes(response.read())
        except Exception as error:  # network down, file moved, etc.
            pytest.skip("could not fetch Allotrope schema {}: {}".format(
                relpath, error))


def _registry():
    """A referencing registry of the schemas, keyed by each one's $id."""
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
    resources = []
    for relpath in _SCHEMA_FILES:
        doc = json.loads((_CACHE / relpath).read_text())
        if "$id" in doc:
            resources.append((doc["$id"], Resource.from_contents(
                doc, default_specification=DRAFT202012)))
    return Registry().with_resources(resources)


def test_dx_asm_conforms_to_lc_schema():
    pytest.importorskip("jsonschema", reason="pip install -e .[validate]")
    pytest.importorskip("referencing")
    from jsonschema import Draft202012Validator

    _ensure_schemas()
    root = json.loads((_CACHE / _ROOT).read_text())
    validator = Draft202012Validator(root, registry=_registry())

    document = rb.read("tests/inputs/teal.dx").to_asm()
    errors = sorted(
        validator.iter_errors(document),
        key=lambda e: list(e.absolute_path))
    assert not errors, "\n".join(
        "@ {}: {}".format("/".join(map(str, e.absolute_path)), e.message)
        for e in errors[:10])
