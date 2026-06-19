"""
Tests for Allotrope Simple Model (ASM) export.

These assert the structure of the emitted document (the data cubes and the
surrounding envelope). Strict JSON-Schema conformance against the published
liquid-chromatography schema is a separate, later step.

"""
import json

import pytest

import rainbow as rb


_SPECTRUM_KEY = "three-dimensional ultraviolet spectrum data cube"
_CHROM_KEY = "chromatogram data cube"


@pytest.fixture
def teal():
    return rb.read("tests/inputs/teal.dx")


def _measurements(document):
    return (document["liquid chromatography aggregate document"]
            ["liquid chromatography document"][0]
            ["measurement aggregate document"]["measurement document"])


def _cube(measurement):
    for key in (_CHROM_KEY, _SPECTRUM_KEY):
        if key in measurement:
            return measurement[key]
    raise KeyError("measurement has no data cube")


def _by_label(document):
    return {_cube(m)["label"]: m for m in _measurements(document)}


def test_to_asm_is_json_serializable(teal):
    document = teal.to_asm()
    # Round-trips through JSON (no numpy scalars or arrays left behind).
    assert json.loads(json.dumps(document)) == document


def test_to_asm_top_level(teal):
    document = teal.to_asm()
    assert "$asm.manifest" in document
    aggregate = document["liquid chromatography aggregate document"]
    assert "device system document" in aggregate
    lc_documents = aggregate["liquid chromatography document"]
    assert len(lc_documents) == 1
    assert lc_documents[0]["analyst"] == "SYSTEM (SYSTEM)"


def test_measurements_cover_all_uv_files(teal):
    # teal has a DAD spectrum and two single-wavelength channels; with spectra
    # on (the default) all three become measurements.
    document = teal.to_asm()
    assert sorted(_by_label(document)) == ["DAD1A.CH", "DAD1H.CH", "DAD1I.UV"]


def test_spectra_off_excludes_the_spectrum(teal):
    document = teal.to_asm(spectra=False)
    labels = _by_label(document)
    assert sorted(labels) == ["DAD1A.CH", "DAD1H.CH"]
    assert all(_SPECTRUM_KEY not in m for m in _measurements(document))


def test_chromatogram_cube_structure_and_data(teal):
    document = teal.to_asm()
    measurement = _by_label(document)["DAD1A.CH"]
    datafile = teal.get_file("DAD1A.CH")

    cube = measurement[_CHROM_KEY]
    structure = cube["cube-structure"]
    assert structure["dimensions"] == [
        {"concept": "retention time", "unit": "s", "@componentDatatype": "double"}]
    assert structure["measures"][0]["concept"] == "absorbance"

    times = cube["data"]["dimensions"][0]
    absorbance = cube["data"]["measures"][0]
    assert len(times) == datafile.xlabels.size
    assert len(absorbance) == datafile.data.shape[0]
    # Retention time is converted from minutes to seconds.
    assert times[0] == pytest.approx(float(datafile.xlabels[0]) * 60.0)
    assert absorbance[0] == pytest.approx(float(datafile.data[0, 0]))


def test_spectrum_cube_structure_and_data(teal):
    document = teal.to_asm()
    measurement = _by_label(document)["DAD1I.UV"]
    datafile = teal.get_file("DAD1I.UV")
    rows, cols = datafile.data.shape

    cube = measurement[_SPECTRUM_KEY]
    dims = cube["cube-structure"]["dimensions"]
    assert [d["concept"] for d in dims] == ["retention time", "wavelength"]
    assert [d["unit"] for d in dims] == ["s", "nm"]
    assert cube["cube-structure"]["measures"][0]["concept"] == "absorbance"

    data = cube["data"]
    # Two dimension arrays (times, wavelengths) and one flattened measure grid.
    assert len(data["dimensions"][0]) == rows
    assert len(data["dimensions"][1]) == cols
    assert data["dimensions"][1] == datafile.ylabels.astype(float).tolist()
    flat = data["measures"][0]
    assert len(flat) == rows * cols
    # Flattened with wavelength varying fastest (C order): index r*cols + c.
    assert flat[0] == pytest.approx(float(datafile.data[0, 0]))
    assert flat[1] == pytest.approx(float(datafile.data[0, 1]))
    assert flat[cols] == pytest.approx(float(datafile.data[1, 0]))


def test_detector_wavelength_setting(teal):
    by_label = _by_label(teal.to_asm())
    for label, expected in (("DAD1A.CH", 210.0), ("DAD1H.CH", 330.0)):
        control = (by_label[label]["device control aggregate document"]
                   ["device control document"][0])
        assert control["detector wavelength setting"] == {
            "value": expected, "unit": "nm"}


def test_sample_and_time_from_metadata(teal):
    measurement = _measurements(teal.to_asm())[0]
    # teal is a standby flush, so the sample name is empty -> default.
    assert measurement["sample document"]["sample identifier"] == "unknown"
    assert measurement["measurement time"] == teal.metadata["date"]


def test_export_asm_writes_file(teal, tmp_path):
    out = tmp_path / "teal.asm.json"
    teal.export_asm(str(out))
    assert json.loads(out.read_text()) == teal.to_asm()


def test_to_asm_on_chemstation_d_directory():
    # The same converter emits ASM for a classic .D directory, not just .dx.
    document = rb.read("tests/inputs/red.D").to_asm()
    by_label = _by_label(document)
    # The CAD channel is excluded; the UV spectrum and two channels remain.
    assert sorted(by_label) == ["DAD1.UV", "DAD1B.ch", "DAD1C.ch"]
    # Sample name and per-channel wavelength come from the .D metadata.
    channel = by_label["DAD1B.ch"]
    assert channel["sample document"]["sample identifier"] == "usp"
    control = (channel["device control aggregate document"]
               ["device control document"][0])
    assert control["detector wavelength setting"] == {
        "value": 280.0, "unit": "nm"}
