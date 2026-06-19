"""
Tests for Allotrope Simple Model (ASM) export.

These assert the structure of the emitted document (the data cubes and the
surrounding envelope). Strict JSON-Schema conformance against the published
liquid-chromatography schema is a separate, later step.

"""
import json

import pytest

import rainbow as rb
from rainbow import asm


@pytest.fixture
def teal():
    return rb.read("tests/inputs/teal.dx")


def test_to_asm_is_json_serializable(teal):
    document = teal.to_asm()
    # Round-trips through JSON without error (no numpy scalars left behind).
    assert json.loads(json.dumps(document)) == document


def test_to_asm_top_level(teal):
    document = teal.to_asm()
    assert "$asm.manifest" in document
    aggregate = document["liquid chromatography aggregate document"]
    assert "device system document" in aggregate
    lc_documents = aggregate["liquid chromatography document"]
    assert len(lc_documents) == 1
    # analyst comes from the manifest operator.
    assert lc_documents[0]["analyst"] == "SYSTEM (SYSTEM)"


def test_one_measurement_per_single_wavelength_channel(teal):
    document = teal.to_asm()
    measurements = (document["liquid chromatography aggregate document"]
                    ["liquid chromatography document"][0]
                    ["measurement aggregate document"]["measurement document"])
    # teal has a DAD spectrum (excluded) and two single-wavelength channels.
    labels = sorted(m["chromatogram data cube"]["label"] for m in measurements)
    assert labels == ["DAD1A.CH", "DAD1H.CH"]


def test_chromatogram_cube_structure_and_data(teal):
    document = teal.to_asm()
    measurements = (document["liquid chromatography aggregate document"]
                    ["liquid chromatography document"][0]
                    ["measurement aggregate document"]["measurement document"])
    by_label = {m["chromatogram data cube"]["label"]: m for m in measurements}

    measurement = by_label["DAD1A.CH"]
    datafile = teal.get_file("DAD1A.CH")

    cube = measurement["chromatogram data cube"]
    structure = cube["cube-structure"]
    assert structure["dimensions"][0]["concept"] == "retention time"
    assert structure["dimensions"][0]["unit"] == "s"
    assert structure["measures"][0]["concept"] == "absorbance"

    times, absorbance = cube["data"]["dimensions"][0], cube["data"]["measures"][0]
    assert len(times) == datafile.xlabels.size
    assert len(absorbance) == datafile.data.shape[0]
    # Retention time is converted from minutes to seconds.
    assert times[0] == pytest.approx(float(datafile.xlabels[0]) * 60.0)
    assert absorbance[0] == pytest.approx(float(datafile.data[0, 0]))


def test_detector_wavelength_setting(teal):
    document = teal.to_asm()
    measurements = (document["liquid chromatography aggregate document"]
                    ["liquid chromatography document"][0]
                    ["measurement aggregate document"]["measurement document"])
    by_label = {m["chromatogram data cube"]["label"]: m for m in measurements}

    control = (by_label["DAD1A.CH"]["device control aggregate document"]
               ["device control document"][0])
    assert control["detector wavelength setting"] == {"value": 210.0, "unit": "nm"}
    assert by_label["DAD1H.CH"]["device control aggregate document"][
        "device control document"][0]["detector wavelength setting"] == {
        "value": 330.0, "unit": "nm"}


def test_sample_and_time_from_metadata(teal):
    document = teal.to_asm()
    measurement = (document["liquid chromatography aggregate document"]
                   ["liquid chromatography document"][0]
                   ["measurement aggregate document"]
                   ["measurement document"][0])
    # teal is a standby flush, so the sample name is empty -> default.
    assert measurement["sample document"]["sample identifier"] == "unknown"
    assert measurement["measurement time"] == teal.metadata["date"]


def test_export_asm_writes_file(teal, tmp_path):
    out = tmp_path / "teal.asm.json"
    teal.export_asm(str(out))
    written = json.loads(out.read_text())
    assert written == teal.to_asm()
