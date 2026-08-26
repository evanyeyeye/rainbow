"""
Tests for Allotrope Simple Model (ASM) export.

These assert the structure of the emitted document (the data cubes and the
surrounding envelope). Strict JSON-Schema conformance against the published
liquid-chromatography schema is a separate, later step.

"""
import json
import warnings

import pytest

import rainbow as rb


_SPECTRUM_KEY = "three-dimensional ultraviolet spectrum data cube"
_CHROM_KEY = "chromatogram data cube"


@pytest.fixture
def teal():
    return rb.read("tests/inputs/teal.dx")


def _measurements(document):
    # Works for either technique: a run with an FID channel exports a gas
    # chromatography document, every other run a liquid chromatography one.
    for technique in ("liquid chromatography", "gas chromatography"):
        aggregate = document.get(technique + " aggregate document")
        if aggregate is not None:
            return (aggregate[technique + " document"][0]
                    ["measurement aggregate document"]["measurement document"])
    raise KeyError("document has no chromatography aggregate document")


def _cube(measurement):
    for key in (_CHROM_KEY, _SPECTRUM_KEY):
        if key in measurement:
            return measurement[key]
    raise KeyError("measurement has no data cube")


def _by_label(document):
    # Skips a measurement with no cube this helper knows: a GC-MS run carries
    # mass chromatograms beside the FID, and a caller looking up one channel by
    # name should not have to care about the others.
    labels = {}
    for measurement in _measurements(document):
        try:
            labels[_cube(measurement)["label"]] = measurement
        except KeyError:
            continue
    return labels


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
    # teal has a DAD spectrum and two single-wavelength channels; with the DAD
    # cube on (the default) all three become measurements.
    document = teal.to_asm()
    assert sorted(_by_label(document)) == ["DAD1A.CH", "DAD1H.CH", "DAD1I.UV"]


def test_dad_cube_off_excludes_the_spectrum(teal):
    document = teal.to_asm(export_dad_cube=False)
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


def test_wavelengths_subsets_the_dad_cube(teal):
    document = teal.to_asm(wavelengths=[254, 280])
    cube = _by_label(document)["DAD1I.UV"][_SPECTRUM_KEY]
    rows = teal.get_file("DAD1I.UV").data.shape[0]
    assert cube["data"]["dimensions"][1] == [254.0, 280.0]
    # Two wavelengths per retention point now, not the full grid.
    assert len(cube["data"]["measures"][0]) == rows * 2


def test_wavelengths_select_the_nearest_available(teal):
    # 255 nm is off the 2 nm grid; it snaps to the nearest column, 254 nm.
    cube = _by_label(teal.to_asm(wavelengths=[255]))["DAD1I.UV"][_SPECTRUM_KEY]
    assert cube["data"]["dimensions"][1] == [254.0]
    # A single-wavelength selection stays a valid 2-D cube: one column per row.
    rows = teal.get_file("DAD1I.UV").data.shape[0]
    assert len(cube["data"]["measures"][0]) == rows


def test_unknown_wavelength_warns_and_is_skipped(teal):
    with pytest.warns(UserWarning, match="9999"):
        document = teal.to_asm(wavelengths=[280, 9999])
    cube = _by_label(document)["DAD1I.UV"][_SPECTRUM_KEY]
    assert cube["data"]["dimensions"][1] == [280.0]


def test_no_matching_wavelength_omits_the_dad_cube(teal):
    with pytest.warns(UserWarning):
        document = teal.to_asm(wavelengths=[9999])
    # The spectrum is dropped; the single-wavelength channels still export.
    by_label = _by_label(document)
    assert "DAD1I.UV" not in by_label
    assert "DAD1A.CH" in by_label
    assert all(_SPECTRUM_KEY not in m for m in _measurements(document))


def test_decimal_places_rounds_cube_values(teal):
    cube = (_by_label(teal.to_asm(decimal_places=1, wavelengths=[254]))
            ["DAD1I.UV"][_SPECTRUM_KEY])
    times = cube["data"]["dimensions"][0]
    values = cube["data"]["measures"][0]
    assert times and all(round(t, 1) == t for t in times)
    assert values and all(round(v, 1) == v for v in values)


def test_decimal_places_rounds_peak_metrics():
    from rainbow import asm
    options = asm._Options(decimal_places=2)
    peak = asm._asm_peak(1, {"retention_time": 1.234567, "area": 9.87654},
                         options)
    assert peak["retention time"]["value"] == round(1.234567 * 60, 2)
    assert peak["peak area"]["value"] == 9.88


def test_decimal_places_rounds_injection_volume():
    # The injection volume is a non-cube quantity; it must round too.
    datadir = rb.read("tests/inputs/red.D")
    datadir.metadata["injection_volume"] = {"value": 1.23456, "unit": "uL"}
    volumes = [m["injection document"]
               ["autosampler injection volume setting (chromatography)"]["value"]
               for m in _measurements(datadir.to_asm(decimal_places=2))
               if "injection document" in m]
    assert volumes and all(v == 1.23 for v in volumes)


def test_injection_volume_is_converted_to_the_unit_the_schema_wants():
    # The vendor unit string is passed through verbatim by both upstream
    # readers, so the value cannot be assumed to be in microlitres. Publishing
    # 2 mL as 2 mm^3 is off by a thousand and validates cleanly.
    datadir = rb.read("tests/inputs/red.D")
    for unit, expected in [("uL", 2.0), ("µL", 2.0), ("mm^3", 2.0),
                           ("mL", 2000.0), ("nL", 0.002), ("L", 2000000.0)]:
        datadir.metadata["injection_volume"] = {"value": 2.0, "unit": unit}
        volumes = [m["injection document"]
                   ["autosampler injection volume setting (chromatography)"]
                   for m in _measurements(datadir.to_asm())
                   if "injection document" in m]
        assert volumes, unit
        assert all(v["value"] == expected and v["unit"] == "mm^3"
                   for v in volumes), unit


def test_an_unconvertible_injection_volume_unit_is_omitted_with_a_warning():
    # Omitting the field beats publishing the number under a unit it is not in,
    # because the wrong unit still validates.
    datadir = rb.read("tests/inputs/red.D")
    datadir.metadata["injection_volume"] = {"value": 2.0, "unit": "drops"}
    with pytest.warns(UserWarning, match="cannot convert"):
        document = datadir.to_asm()
    assert not [m for m in _measurements(document) if "injection document" in m]


@pytest.mark.parametrize("bad", [-1, -3, True, 1.5, "2"])
def test_decimal_places_rejects_a_value_that_would_gut_the_document(bad):
    # round() and np.round() accept a negative precision, so decimal_places=-3
    # rounded every signal value, retention time and peak to zero and still
    # emitted a schema-valid file. read() holds display_precision to this rule.
    datadir = rb.read("tests/inputs/red.D")
    with pytest.raises(ValueError, match="decimal_places"):
        datadir.to_asm(decimal_places=bad)


@pytest.mark.parametrize("ions", [[float("nan")], [float("inf")], [None]])
def test_ions_rejects_a_selection_that_cannot_match(ions):
    # Every comparison against NaN is False, so an unchecked NaN selected index
    # 0 and passed the tolerance check: the caller got the first trace in the
    # file, silently, instead of the ion they asked for.
    datadir = rb.read("tests/inputs/yellow.D")
    with pytest.raises((ValueError, TypeError), match="ions"):
        datadir.to_asm(ions=ions)


def test_a_string_selection_is_rejected_rather_than_read_per_character():
    # wavelengths="254" iterates into [2.0, 5.0, 4.0], drops all three, and the
    # DAD cube silently vanishes.
    datadir = rb.read("tests/inputs/red.D")
    with pytest.raises(TypeError, match="one character at a time"):
        datadir.to_asm(wavelengths="254")


def test_select_wavelengths_tolerance_boundary():
    import numpy as np
    from rainbow import asm
    labels = np.array([254.0, 256.0])
    # Exactly 1.0 nm away is kept (inclusive boundary), nearest column wins.
    assert asm._select_wavelengths(labels, [255.0]) == [0]
    assert asm._select_wavelengths(labels, [255.6]) == [1]
    # More than 1.0 nm from any column is dropped, with a warning.
    with pytest.warns(UserWarning):
        assert asm._select_wavelengths(labels, [300.0]) == []


def test_detector_wavelength_setting(teal):
    by_label = _by_label(teal.to_asm())
    for label, expected in (("DAD1A.CH", 210.0), ("DAD1H.CH", 330.0)):
        control = (by_label[label]["device control aggregate document"]
                   ["device control document"][0])
        assert control["detector wavelength setting"] == {
            "value": expected, "unit": "nm"}


def test_sample_and_time_from_metadata(teal):
    from datetime import datetime
    measurement = _measurements(teal.to_asm())[0]
    # teal is a standby flush, so the sample name is empty -> default.
    assert measurement["sample document"]["sample identifier"] == "unknown"
    # .dx already stores ISO 8601, so the export carries the same instant. The
    # strings are not identical: .NET writes 7 fractional digits and ISO 8601
    # allows at most 6, so the export normalizes to microseconds.
    emitted = datetime.fromisoformat(measurement["measurement time"])
    assert emitted == datetime.fromisoformat(
        teal.metadata["date"][:26] + teal.metadata["date"][27:])
    assert measurement["measurement time"].endswith("-04:00")


def test_export_asm_writes_file(teal, tmp_path):
    out = tmp_path / "teal.asm.json"
    teal.export_asm(str(out))
    assert json.loads(out.read_text()) == teal.to_asm()


def test_export_asm_streams_with_options(teal, tmp_path):
    # The streamed writer applies the same controls as the in-memory document.
    out = tmp_path / "teal.asm.json"
    teal.export_asm(str(out), wavelengths=[254, 280], decimal_places=3)
    assert json.loads(out.read_text()) == \
        teal.to_asm(wavelengths=[254, 280], decimal_places=3)


def test_export_asm_pretty_output_matches_canonical(teal, tmp_path):
    # The streamed pretty-print is byte-identical to a single json.dumps, i.e.
    # the injection documents are correctly indented under the envelope.
    out = tmp_path / "teal.asm.json"
    teal.export_asm(str(out))
    assert out.read_text() == json.dumps(
        teal.to_asm(), indent=2, ensure_ascii=False)


def test_to_asm_on_chemstation_d_directory():
    # The same converter emits ASM for a classic .D directory, not just .dx.
    document = rb.read("tests/inputs/red.D").to_asm()
    by_label = _by_label(document)
    # The UV spectrum and two channels, plus the CAD channel (exported as an
    # electric-current chromatogram, see the ASM detectors docs).
    assert sorted(by_label) == ["ADC1A.CH", "DAD1.UV", "DAD1B.ch", "DAD1C.ch"]
    # Sample name and per-channel wavelength come from the .D metadata.
    channel = by_label["DAD1B.ch"]
    assert channel["sample document"]["sample identifier"] == "usp"
    control = (channel["device control aggregate document"]
               ["device control document"][0])
    assert control["detector wavelength setting"] == {
        "value": 280.0, "unit": "nm"}


def test_cad_exports_as_electric_current_with_truthful_type():
    # red.D's ADC1A.CH is a CAD channel: a charged-aerosol detector measures a
    # current, so it exports faithfully as an electric-current (pA) chromatogram,
    # with the real AFO device type (not "ultraviolet detector") and no
    # wavelength setting.
    cad = _by_label(rb.read("tests/inputs/red.D").to_asm())["ADC1A.CH"]
    assert cad[_CHROM_KEY]["cube-structure"]["measures"][0] == {
        "concept": "electric current", "unit": "pA",
        "@componentDatatype": "double"}
    control = (cad["device control aggregate document"]
               ["device control document"][0])
    assert control["device type"] == "liquid chromatography detector"
    assert "detector wavelength setting" not in control


def test_peaks_on_a_non_absorbance_channel_relabel_to_absorbance_with_a_note():
    # The schema models a peak list only on an absorbance measurement, so a CAD
    # channel (electric current) that carries integrated peaks is relabeled to
    # absorbance to keep the peaks, with a note recording the real quantity and a
    # device type that stays truthful. A relabel happens only when there are
    # peaks: without them the channel keeps its faithful electric-current cube.
    datadir = rb.read("tests/inputs/red.D")
    datadir.peaks = [{
        "signal": "ADC1A", "wavelength": None, "description": None,
        "channel_file": "ADC1A.CH",
        "peaks": [{"retention_time": 1.5, "area": 100.0, "height": 10.0}],
    }]
    cad = _by_label(datadir.to_asm())["ADC1A.CH"]
    # The peak itself survives, on an absorbance cube, device type still truthful.
    peak = (cad["processed data aggregate document"]["processed data document"]
            [0]["peak list"]["peak"][0])
    assert peak["peak area"] == {"value": 100.0, "unit": "mAU.s"}
    assert cad[_CHROM_KEY]["cube-structure"]["measures"][0]["concept"] \
        == "absorbance"
    assert (cad["device control aggregate document"]["device control document"]
            [0]["device type"]) == "liquid chromatography detector"
    # A note records the real quantity.
    note = (cad["custom information aggregate document"]
            ["custom information document"][0])
    assert note["datum label"] == "reported measure"
    assert "electric current" in note["scalar string datum"]


def test_uv_channel_with_peaks_is_not_relabeled():
    # A UV channel is already absorbance, so peaks attach with no relabel and no
    # "reported measure" note (the relabel is only for non-absorbance detectors).
    datadir = rb.read("tests/inputs/red.D")
    datadir.peaks = [{
        "signal": "DAD1B", "wavelength": 280.0, "description": None,
        "channel_file": "DAD1B.ch",
        "peaks": [{"retention_time": 1.5, "area": 100.0, "height": 10.0}],
    }]
    uv = _by_label(datadir.to_asm())["DAD1B.ch"]
    assert "processed data aggregate document" in uv
    assert "custom information aggregate document" not in uv


def test_fid_with_peaks_relabels_with_an_electric_current_note():
    # A GC-FID channel with integrated peaks (the common GC case) relabels to
    # absorbance, keeping the peaks, with a note naming the real quantity and a
    # device type that stays the flame ionization detector.
    datadir = rb.read("tests/inputs/yellow.D")
    datadir.peaks = [{
        "signal": "FID1A", "wavelength": None, "description": None,
        "channel_file": "FID1A.ch",
        "peaks": [{"retention_time": 1.5, "area": 100.0, "height": 10.0}],
    }]
    fid = _by_label(datadir.to_asm())["FID1A.ch"]
    assert "processed data aggregate document" in fid
    control = (fid["device control aggregate document"]
               ["device control document"][0])
    assert control["device type"] == "flame ionization detector"
    note = (fid["custom information aggregate document"]
            ["custom information document"][0]["scalar string datum"])
    assert "electric current" in note


def test_non_absorbance_channel_without_peaks_stays_faithful():
    # No peaks, no relabel: the CAD channel keeps its electric-current cube.
    cad = _by_label(rb.read("tests/inputs/red.D").to_asm())["ADC1A.CH"]
    assert cad[_CHROM_KEY]["cube-structure"]["measures"][0]["concept"] \
        == "electric current"
    assert "custom information aggregate document" not in cad


def test_elsd_exports_as_intensity_with_truthful_type():
    # orange.D's ADC1A.CH is an ELSD channel: it exports faithfully as a light
    # intensity (RLU) chromatogram, with the real ELSD AFO device type.
    measurement = _by_label(rb.read("tests/inputs/orange.D").to_asm())["ADC1A.CH"]
    assert measurement[_CHROM_KEY]["cube-structure"]["measures"][0] == {
        "concept": "intensity", "unit": "RLU", "@componentDatatype": "double"}
    control = (measurement["device control aggregate document"]
               ["device control document"][0])
    assert control["device type"] == "evaporative light scattering detector"
    assert "detector wavelength setting" not in control


_MASS_CHROM_KEY = "mass chromatogram data cube"


def test_sim_ms_exports_as_mass_chromatogram():
    # green.D has four single-ion (SIM) MS channels, each a 1D trace at one m/z.
    # Each becomes a mass chromatogram data cube (ion count over retention time),
    # with the monitored m/z recorded in the label.
    document = rb.read("tests/inputs/green.D").to_asm()
    measurements = _measurements(document)
    ms = [m for m in measurements if _MASS_CHROM_KEY in m]
    assert len(ms) == 4

    cube = ms[0][_MASS_CHROM_KEY]
    assert cube["cube-structure"]["dimensions"] == [
        {"concept": "retention time", "unit": "s", "@componentDatatype": "double"}]
    assert cube["cube-structure"]["measures"][0] == {
        "concept": "count", "unit": "Counts", "@componentDatatype": "double"}
    # The m/z appears in the label (a mass chromatogram has no m/z dimension).
    assert "m/z" in cube["label"]
    control = (ms[0]["device control aggregate document"]
               ["device control document"][0])
    assert control["device type"] == "mass spectrometer"


def test_full_scan_ms_exports_only_requested_ions():
    # orange.D's MS is a 2D retention-by-m/z scan grid, which the published
    # schema cannot hold faithfully. By default none of it is exported (no mass
    # cube), but the ELSD channel still is, so the document is not trivially
    # empty. When the caller names ions, each is pulled from the grid as its own
    # mass chromatogram.
    datadir = rb.read("tests/inputs/orange.D")
    measurements = _measurements(datadir.to_asm())
    assert all(_MASS_CHROM_KEY not in m for m in measurements)
    assert any(_CHROM_KEY in m for m in measurements)   # the ELSD measurement

    ms = [m for m in _measurements(datadir.to_asm(ions=[150, 200]))
          if _MASS_CHROM_KEY in m]
    assert len(ms) == 2
    assert all("m/z" in m[_MASS_CHROM_KEY]["label"] for m in ms)

    # A single m/z (not a list) is accepted too.
    ms = [m for m in _measurements(datadir.to_asm(ions=150))
          if _MASS_CHROM_KEY in m]
    assert len(ms) == 1


def test_requested_ion_not_in_scan_warns_and_is_skipped():
    # An ion the scan does not cover is skipped with a warning, not exported and
    # not an error.
    datadir = rb.read("tests/inputs/orange.D")
    with pytest.warns(UserWarning, match="No m/z within 0.5 of 9999"):
        document = datadir.to_asm(ions=[9999])
    assert all(_MASS_CHROM_KEY not in m for m in _measurements(document))


def test_ions_does_not_affect_sim_channels():
    # ions= selects from full scans only; a SIM channel always exports all of
    # its monitored ions regardless of (non-matching) requested ions.
    document = rb.read("tests/inputs/green.D").to_asm(ions=[999])
    ms = [m for m in _measurements(document) if _MASS_CHROM_KEY in m]
    assert len(ms) == 4


def test_ms_channel_with_no_shared_axis_is_skipped():
    # A per-scan profile (e.g. HRMS) has no single shared m/z axis: reading
    # ylabels raises. The exporter must skip it cleanly, not crash.
    from rainbow import asm

    class _NoSharedAxis:
        name = "profile.bin"
        detector = "MS"
        metadata = {}

        @property
        def ylabels(self):
            raise AttributeError("per-scan profile has no shared m/z axis")

    assert asm._mass_chromatogram_measurements(_NoSharedAxis(), {}, None) == []


def test_multi_ion_sim_exports_every_ion():
    # yellow.D is a simultaneous SIM/Scan run: dataSim.ms holds two monitored
    # (SIM) ions and data.ms is the full scan. Every SIM ion is exported by
    # default; the scan is left out unless its ions are requested.
    datadir = rb.read("tests/inputs/yellow.D")
    ms = [m for m in _measurements(datadir.to_asm()) if _MASS_CHROM_KEY in m]
    # Two mass chromatograms, both from the SIM channel, none from the scan.
    assert len(ms) == 2
    assert all(m["measurement identifier"].startswith("dataSim.ms") for m in ms)
    labels = sorted(m[_MASS_CHROM_KEY]["label"] for m in ms)
    assert labels == ["dataSim.ms (m/z 131)", "dataSim.ms (m/z 202)"]


def test_acquisition_mode_tags_sim_and_scan():
    # The acquisition mode is read from the method (acqmeth.txt), not guessed:
    # yellow.D's scan and SIM channels are tagged distinctly.
    datadir = rb.read("tests/inputs/yellow.D")
    modes = {df.name: df.metadata.get("acquisition_mode")
             for df in datadir.datafiles if df.detector == "MS"}
    assert modes == {"data.ms": "Scan", "dataSim.ms": "SIM"}


def test_module_device_type_falls_back_for_unmapped_module():
    # device type is schema-required. A module whose type rainbow cannot map
    # still gets a valid device document entry, with the generic AFO "device"
    # class, while a recognizable module keeps its specific type.
    from rainbow import asm
    unknown = asm._module_device(1, {"name": "Mystery Box", "type": "Widget"})
    assert unknown["device type"] == "device"
    pump = asm._module_device(2, {"name": "Quat. Pump", "type": "Pump"})
    assert pump["device type"] == "pump"


# --- FID and gas-chromatography routing ---


def _aggregate_key(document):
    return next(k for k in document if k.endswith("aggregate document"))


def test_non_fid_run_is_liquid_chromatography(teal):
    # A run with no FID channel stays a liquid chromatography document, on the
    # liquid-chromatography manifest.
    document = teal.to_asm()
    assert _aggregate_key(document) == "liquid chromatography aggregate document"
    assert "liquid-chromatography" in document["$asm.manifest"]
    assert "REC/2026/06" in document["$asm.manifest"]


def test_fid_run_routes_to_gas_chromatography():
    # An FID channel makes the whole run a gas chromatography document on the
    # gas-chromatography manifest. yellow.D's method also declares GC, so the
    # declaration is dropped here to leave the detector as the only evidence.
    datadir = rb.read("tests/inputs/yellow.D")
    del datadir.metadata["technique"]
    document = datadir.to_asm()
    assert _aggregate_key(document) == "gas chromatography aggregate document"
    manifest = document["$asm.manifest"]
    assert "gas-chromatography" in manifest and "REC/2026/06" in manifest


def test_fid_exports_as_electric_current_chromatogram():
    # An FID channel is a 1D chromatogram whose measure is electric current in
    # pA (the FID's real quantity, faithfully), with a truthful device type and
    # detection type.
    document = rb.read("tests/inputs/yellow.D").to_asm()
    fid = _by_label(document)["FID1A.ch"]
    cube = fid[_CHROM_KEY]
    assert cube["cube-structure"]["measures"][0] == {
        "concept": "electric current", "unit": "pA",
        "@componentDatatype": "double"}
    control = (fid["device control aggregate document"]
               ["device control document"][0])
    assert control["device type"] == "flame ionization detector"
    assert control["detection type"] == "flame ionization"


def test_gc_run_keeps_its_ms_channels():
    # yellow.D is a GC-MS run (an FID channel plus SIM/scan MS). Routing to a
    # gas chromatography document does not drop the MS: the SIM ions still
    # export as mass chromatograms (the 2026/06 GC ADM admits that cube), and
    # the FID rides alongside as an electric-current chromatogram.
    document = rb.read("tests/inputs/yellow.D").to_asm()
    assert _aggregate_key(document) == "gas chromatography aggregate document"
    measurements = _measurements(document)
    assert sum(_MASS_CHROM_KEY in m for m in measurements) == 2   # the SIM ions
    fid = [m for m in measurements if _CHROM_KEY in m]
    assert len(fid) == 1
    assert (fid[0]["device control aggregate document"]
            ["device control document"][0]["device type"]
            == "flame ionization detector")


def test_gc_injection_document_uses_microlitres():
    # The gas-chromatography injection document carries the volume in uL (the
    # Greek mu the schema pins), unlike the liquid-chromatography mm^3.
    datadir = rb.read("tests/inputs/yellow.D")
    datadir.metadata["injection_volume"] = {"value": 1.5, "unit": "µL"}
    measurement = _measurements(datadir.to_asm())[0]
    volume = measurement["injection document"]["injection volume setting"]
    assert volume == {"value": 1.5, "unit": "μL"}


def test_gc_document_carries_a_device_method_identifier():
    # A gas chromatography document requires a device method identifier; absent
    # method metadata it falls back rather than being omitted.
    datadir = rb.read("tests/inputs/yellow.D")
    assert not datadir.metadata.get("method")
    document = datadir.to_asm()
    gc_document = (document["gas chromatography aggregate document"]
                   ["gas chromatography document"][0])
    assert gc_document["device method identifier"] == "unknown"


# --- technique resolution: override > method > FID-presence fallback ---


def test_technique_override_forces_gc_on_a_non_fid_run(teal):
    # An explicit technique= forces the document even with no FID channel.
    assert _aggregate_key(teal.to_asm(technique="GC")) \
        == "gas chromatography aggregate document"


def test_technique_override_beats_the_fid_fallback():
    # With the method declaration removed, an FID channel is the only evidence
    # and the run falls back to GC; an explicit technique="LC" overrides that.
    datadir = rb.read("tests/inputs/yellow.D")
    del datadir.metadata["technique"]
    document = datadir.to_asm(technique="LC")
    assert _aggregate_key(document) == "liquid chromatography aggregate document"


def test_technique_override_beats_the_method_declaration():
    # yellow.D's method declares GC (metadata['technique'] == 'GC'); the override
    # still wins.
    datadir = rb.read("tests/inputs/yellow.D")
    assert datadir.metadata.get("technique") == "GC"
    assert _aggregate_key(datadir.to_asm(technique="LC")) \
        == "liquid chromatography aggregate document"


def test_method_declaration_beats_the_fid_fallback():
    # When the method records the technique, it wins over detector evidence: a
    # declared LC run with an FID channel stays liquid chromatography.
    datadir = rb.read("tests/inputs/yellow.D")
    datadir.metadata["technique"] = "LC"
    assert _aggregate_key(datadir.to_asm()) \
        == "liquid chromatography aggregate document"


def test_method_declared_gc_routes_without_an_fid_channel():
    # The method alone (no FID) routes a run to gas chromatography.
    datadir = rb.read("tests/inputs/teal.dx")
    datadir.metadata["technique"] = "GC"
    assert _aggregate_key(datadir.to_asm()) \
        == "gas chromatography aggregate document"


def test_bad_technique_override_raises():
    with pytest.raises(ValueError, match="GC.*LC|technique"):
        rb.read("tests/inputs/teal.dx").to_asm(technique="GCMS")


def test_sequence_routes_by_an_injection_technique():
    # A sequence is routed by its injections' technique: one GC/FID injection
    # makes the whole aggregate a gas chromatography document.
    from rainbow.datasequence import DataSequence
    gc_injection = rb.read("tests/inputs/yellow.D")
    sequence = DataSequence("seq", [gc_injection], {})
    document = sequence.to_asm()
    assert _aggregate_key(document) == "gas chromatography aggregate document"
    # And the sequence-level override still wins.
    assert _aggregate_key(sequence.to_asm(technique="LC")) \
        == "liquid chromatography aggregate document"


# ---------------------------------------------------------------------------
# Agilent MassHunter DAD (.cd/.cg/.sd/.sp).
#
# The exporter routes on the detector, not the file format, so a MassHunter
# DAD's channels export the same way a Chemstation .ch and .uv pair does: one
# chromatogram cube per single-wavelength signal, one spectrum cube for the
# wavelength grid. These pin that down, since the two formats reach it by
# different parsers.
# ---------------------------------------------------------------------------

@pytest.fixture
def bronze():
    return rb.read("tests/inputs/bronze.D")


def test_masshunter_dad_exports_every_signal_and_the_spectrum(bronze):
    by_label = _by_label(bronze.to_asm())
    assert sorted(by_label) == [
        "DAD1.sp", "DAD1A.cg", "DAD1B.cg", "DAD1C.cg", "DAD1D.cg", "DAD1E.cg"]
    assert _SPECTRUM_KEY in by_label["DAD1.sp"]
    for letter in "ABCDE":
        assert _CHROM_KEY in by_label[f"DAD1{letter}.cg"]


def test_masshunter_dad_carries_the_detector_wavelength_setting(bronze):
    # The signal descriptions follow the Chemstation convention, so each
    # channel's optics reach the document the same way a .ch channel's do.
    by_label = _by_label(bronze.to_asm())
    for label, expected in (("DAD1A.cg", 254.0), ("DAD1B.cg", 210.0),
                            ("DAD1C.cg", 280.0), ("DAD1D.cg", 400.0),
                            ("DAD1E.cg", 260.0)):
        control = (by_label[label]["device control aggregate document"]
                   ["device control document"][0])
        assert control["detector wavelength setting"] == {
            "value": expected, "unit": "nm"}


def test_masshunter_dad_cube_off_keeps_the_signals(bronze):
    by_label = _by_label(bronze.to_asm(export_dad_cube=False))
    assert "DAD1.sp" not in by_label
    assert len(by_label) == 5


def test_masshunter_dad_wavelengths_subset_the_spectrum(bronze):
    cube = _by_label(bronze.to_asm(wavelengths=[254, 280]))["DAD1.sp"]
    assert cube[_SPECTRUM_KEY]["data"]["dimensions"][1] == [254.0, 280.0]


def test_masshunter_dad_telemetry_is_not_exported(bronze):
    # Telemetry is analog data, not a detector channel, so it stays out of the
    # document even when parsed. It also carries a different point count from
    # the absorbance signals, so a leak would not go unnoticed.
    with_telemetry = rb.read("tests/inputs/bronze.D", telemetry=True)
    assert with_telemetry.analog
    assert _by_label(with_telemetry.to_asm()).keys() \
        == _by_label(bronze.to_asm()).keys()


def test_non_uv_modules_are_not_reported_as_ultraviolet():
    # The inventory has to agree with the cube: a module that is plainly an FID
    # or an RID must not be filed under the generic ultraviolet fallback.
    from rainbow.asm import _module_device_type
    assert _module_device_type({"name": "FID1", "type": "detector"}) \
        == "flame ionization detector"
    assert _module_device_type({"name": "RID1A", "type": ""}) \
        == "refractive index detector"
    assert _module_device_type({"name": "", "type": "evaporative light "
                                                    "scattering detector"}) \
        == "evaporative light scattering detector"
    assert _module_device_type({"name": "Charged Aerosol Detector"}) \
        == "liquid chromatography detector"
    assert _module_device_type({"name": "RI Detector", "type": ""}) \
        == "refractive index detector"
    assert _module_device_type({"name": "2424 ELS Detector", "type": ""}) \
        == "evaporative light scattering detector"
    assert _module_device_type({"name": "MSD1", "type": "Detector"}) \
        == "mass spectrometer"
    # A genuine UV module still maps the way it did.
    assert _module_device_type({"name": "DAD1", "type": "detector"}) \
        == "diode array detector"
    assert _module_device_type({"name": "VWD1", "type": "detector"}) \
        == "ultraviolet detector"


def test_detector_acronyms_are_matched_as_whole_words():
    # "rid" and "cad" sit inside ordinary words, so a substring match would
    # mislabel an unrelated module.
    from rainbow.asm import _module_device_type
    assert _module_device_type({"name": "Hybrid Column Compartment"}) \
        == "column compartment"
    assert _module_device_type({"name": "Cascade Pump"}) == "pump"
    assert _module_device_type({"name": "Ride Control"}) is None
    assert _module_device_type({"name": "Cadmium Trap"}) is None


def test_an_unnameable_detector_is_generic_not_ultraviolet():
    # A detector whose name does not identify it must not be guessed as
    # ultraviolet. This is the shape red.D's charged-aerosol channel arrives
    # in: an analog input the vendor does not model as a detector kind.
    from rainbow.asm import _module_device_type
    for name in ("Analog/digital converter", "CAD", "Detector"):
        assert _module_device_type({"name": name, "type": "Detector"}) \
            == "liquid chromatography detector", name


def test_a_nameable_detector_gets_its_exact_afo_class():
    # TCD, ECD, and FLD are AFO classes of their own (AFE_0000316, AFE_0000534,
    # AFE_0000567); typing them generically threw away what the name said.
    from rainbow.asm import _module_device_type
    exact = {
        "TCD Back": "thermal conductivity detector",
        "ECD1": "electron capture detector",
        "FLD1A": "fluorescence detector",
        "Variable Wavelength Detector": "ultraviolet detector",
        "PDA": "diode array detector",
    }
    for name, device_type in exact.items():
        assert _module_device_type({"name": name, "type": "Detector"}) \
            == device_type, name


def test_the_generic_detector_follows_the_documents_technique():
    # `liquid chromatography detector` and `gas chromatography detector` are
    # disjoint AFO siblings, so a fixed fallback contradicted every GC document
    # that carried a detector AFO cannot name.
    from rainbow.asm import _GC, _LC, _module_device_type
    module = {"name": "Analog/digital converter", "type": "Detector"}
    assert _module_device_type(module, _LC) == "liquid chromatography detector"
    assert _module_device_type(module, _GC) == "gas chromatography detector"


def test_a_named_class_yields_to_the_documents_technique():
    """ AFO's named detector classes are not technique-neutral.

    `ultraviolet detector` and `diode array detector` have `liquid
    chromatography detector` as an asserted parent, defined as a component of
    an LC system; FID, TCD and ECD sit under the gas chromatography sibling,
    and the two are disjoint. So keeping the exact class in a document of the
    other technique makes the document contradict itself. The nearest class
    claiming no technique is used instead.
    """
    from rainbow.asm import _module_device_type, _LC, _GC
    absorbance = "electronic absorbance detector"
    for name, lc_type, gc_type in (
            ("DAD1A", "diode array detector", absorbance),
            ("VWD", "ultraviolet detector", absorbance),
            ("RID1A", "refractive index detector", "chromatographic detector"),
            ("FLD1A", "fluorescence detector", "chromatographic detector"),
            ("FID1", "chromatographic detector", "flame ionization detector"),
            ("TCD Back", "chromatographic detector",
             "thermal conductivity detector"),
            ("ECD1", "chromatographic detector", "electron capture detector"),
            # Neither class claims a technique, so neither is ever neutralized.
            ("ELSD", "evaporative light scattering detector",
             "evaporative light scattering detector"),
            ("MSD", "mass spectrometer", "mass spectrometer")):
        module = {"name": name, "type": "Detector"}
        assert _module_device_type(module, _LC) == lc_type, name
        assert _module_device_type(module, _GC) == gc_type, name
        # An unknown technique contradicts nothing, so the class is kept.
        assert _module_device_type(module, None) == \
            (gc_type if lc_type == "chromatographic detector" else lc_type), name


def test_rainbow_can_read_back_every_detector_label_it_writes():
    """ A label rainbow emits and cannot re-read degrades on every round trip.

    `ultraviolet detector` is AFO's own label and rainbow's own output, but
    \\buv\\b does not match inside "ultraviolet", so it used to come back as
    the generic class. The neutral absorbance class has the same hazard: the
    word "absorbance" would otherwise re-specialize it to UV.
    """
    from rainbow.asm import (_DETECTOR_RULES, _module_device_type,
                             _DETECTOR_TECHNIQUES, _LC, _GC)
    for _, _, device_type in _DETECTOR_RULES:
        claimed = _DETECTOR_TECHNIQUES.get(device_type)
        technique = claimed[0] if claimed else _LC
        assert _module_device_type({"name": device_type}, technique) == \
            device_type, device_type


def test_a_gas_chromatography_document_claims_no_liquid_chromatography_parts():
    """ No part of a GC document may claim a liquid chromatography detector.

    pink.D is a diode-array run, so forcing it to GC puts real absorbance
    channels inside a gas chromatography document: they must come back as the
    technique-neutral parent class rather than as a UV or diode array detector,
    both of which the document would contradict.
    """
    document = rb.read("tests/inputs/pink.D").to_asm(technique="GC")
    aggregate = document["gas chromatography aggregate document"]
    types = {device.get("device type") for device
             in aggregate["device system document"]["device document"]}
    for gc_document in aggregate["gas chromatography document"]:
        for measurement in gc_document["measurement aggregate document"][
                "measurement document"]:
            for control in measurement["device control aggregate document"][
                    "device control document"]:
                types.add(control.get("device type"))
    assert "ultraviolet detector" not in types
    assert "diode array detector" not in types
    assert "electronic absorbance detector" in types


def test_module_names_survive_any_separator():
    # An underscore is a word character, so \b saw no boundary in "FID_2".
    from rainbow.asm import _module_device_type
    for name in ("FID_2", "FID-2", "FID 2", "FID2", "fid"):
        assert _module_device_type({"name": name}) \
            == "flame ionization detector", name


def test_the_real_cad_instrument_inventory_agrees_with_its_cube():
    # End to end on the fixture the inventory used to contradict: red.D's
    # CAD channel exports an electric-current cube, so its module must not be
    # inventoried as an ultraviolet detector.
    from rainbow.agilent import sequence
    header = sequence.parse_header("tests/inputs/red.D/sequence.acam_")
    modules = header["instrument"]["modules"]
    from rainbow.asm import _module_device_type
    types = {m["name"]: _module_device_type(m) for m in modules}
    assert types["Analog/digital converter"] == "liquid chromatography detector"
    assert "ultraviolet detector" not in \
        {v for k, v in types.items() if k != "DAD"}


# ASM types every timestamp as ISO 8601, but the vendors write wall clock in
# their own formats. These are the shapes rainbow's parsers actually hand back.

@pytest.mark.parametrize("vendor,expected", [
    ("27-Feb-18, 10:11:50", "2018-02-27T10:11:50"),      # Chemstation .ch/.uv
    ("14-Nov-19, 15:08:08", "2019-11-14T15:08:08"),
    ("06-Aug-2021 10:52:20", "2021-08-06T10:52:20"),     # Waters _HEADER.TXT
    ("17 Dec 19  10:04 am", "2019-12-17T10:04:00"),      # Agilent sequence
    ("3 Feb 22  11:22 am -0500",                         # ... with an offset
     "2022-02-03T11:22:00-05:00"),
    ("2025-06-19T20:30:07.2297248-04:00",                # OpenLab .dx, already
     "2025-06-19T20:30:07.229724-04:00"),                # ISO (.NET's 7 digits)
])
def test_vendor_timestamps_become_iso_8601(vendor, expected):
    from rainbow.asm import _iso_timestamp
    assert _iso_timestamp(vendor) == expected


def test_an_unreadable_timestamp_is_dropped_not_passed_through():
    # Emitting the vendor string would put a value in the document that no ASM
    # reader can parse; the field is optional, so it is omitted instead.
    from rainbow.asm import _iso_timestamp
    for value in ("not a date", "", None, 17, "99-Zzz-99"):
        assert _iso_timestamp(value) is None


@pytest.mark.parametrize("locale_name", ["fr_FR.UTF-8", "de_DE.UTF-8",
                                         "ja_JP.UTF-8"])
def test_vendor_timestamps_parse_under_a_non_english_locale(locale_name):
    """ A month name must not be read through the process locale.

    rainbow is a library; the application embedding it may well have called
    setlocale(LC_ALL, ''), which is enough to make strptime's %b and %p reject
    every vendor spelling. That would silently drop the acquisition time on a
    non-English workstation while passing on the developer's machine.
    """
    import locale
    from rainbow.asm import _iso_timestamp
    previous = locale.setlocale(locale.LC_TIME)
    try:
        try:
            locale.setlocale(locale.LC_TIME, locale_name)
        except locale.Error:
            pytest.skip(locale_name + " is not installed")
        assert _iso_timestamp("27-Feb-18, 10:11:50") == "2018-02-27T10:11:50"
        assert _iso_timestamp("17 Dec 19  10:04 am") == "2019-12-17T10:04:00"
        assert _iso_timestamp("3 Feb 22  11:22 am -0500") == \
            "2022-02-03T11:22:00-05:00"
    finally:
        locale.setlocale(locale.LC_TIME, previous)


@pytest.mark.parametrize("value,expected", [
    # .NET writes 7 fractional digits and trims trailing zeros, so the same
    # .dx can arrive with any width. Pythons before 3.11 accept only 3 or 6.
    ("2025-06-19T20:30:07.2297248-04:00", "2025-06-19T20:30:07.229724-04:00"),
    ("2025-06-19T20:30:07.2297-04:00", "2025-06-19T20:30:07.229700-04:00"),
    ("2025-06-19T20:30:07.22-04:00", "2025-06-19T20:30:07.220000-04:00"),
    ("2025-06-19T20:30:07.229724-04:00", "2025-06-19T20:30:07.229724-04:00"),
])
def test_a_fractional_second_of_any_width_is_read(value, expected):
    from rainbow.asm import _iso_timestamp
    assert _iso_timestamp(value) == expected


@pytest.mark.parametrize("value", [
    "02/03/2022 11:22:00",          # numeric: day and month indistinguishable
    "31-Feb-18, 10:11:50",          # a day the calendar does not have
    "3 Feb 22  13:22 pm",           # a 12-hour clock reading 13
    "3 Feb 22  11:22 am +053045",   # ISO 8601 allows seconds, RFC 3339 does not
])
def test_a_timestamp_that_could_be_misread_is_refused(value):
    """ A timestamp read into the wrong instant is worse than one refused. """
    from rainbow.asm import _iso_timestamp
    assert _iso_timestamp(value) is None


@pytest.mark.parametrize("value", [
    # An offset of 24 hours or more raises out of datetime.timezone rather than
    # failing to parse, which would take down a whole export.
    "3 Feb 22  11:22 am +2500",
    "3 Feb 22  11:22 am -2400",
    "3 Feb 22  11:22 am +9999",
    # Minutes of 60 or more would roll over into a different instant.
    "3 Feb 22  11:22 am +0060",
    "3 Feb 22  11:22 am +0099",
    # A 12-hour clock runs 1 to 12; hour 0 read as noon is a 12-hour error.
    "3 Feb 22  00:22 pm",
    # A truncated year would read as a timestamp eighteen centuries off.
    "9-Feb-218 10:11:50",
])
def test_a_vendor_timestamp_rainbow_cannot_trust_returns_none(value):
    """ Never raise, and never guess: the contract is a value or None. """
    from rainbow.asm import _iso_timestamp
    assert _iso_timestamp(value) is None


def test_an_offset_the_run_recorded_is_validated_like_the_callers():
    """ A vendor file is not a more trustworthy source than a keyword.

    The offset harvested from a sibling file is concatenated onto every
    timestamp in the document exactly as the caller's is, so hardening only
    the `timezone` argument would leave a second unguarded way in.
    """
    from rainbow.asm import _Options
    options = _Options()
    for bad in ("+99:99", "garbage", "+05:60", "+24:00"):
        with pytest.warns(UserWarning, match="is not one"):
            stamped = options.timestamp(
                "27-Feb-18, 10:11:50", recorded_offset=bad)
        assert stamped == "2018-02-27T10:11:50", bad
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert options.timestamp("27-Feb-18, 10:11:50",
                                 recorded_offset="-05:00") == \
            "2018-02-27T10:11:50-05:00"


def test_a_required_timestamp_is_written_through_rather_than_dropped():
    """ Dropping a required field breaks structure, not just format.

    injection time is required by both ADMs, and the injection document itself
    is required for gas chromatography. Omitting an unreadable one turns a
    format violation into a required-property violation and throws away the
    only copy of the acquisition time, so it is written through with a warning.
    """
    from rainbow.asm import _Options
    options = _Options()
    with pytest.warns(UserWarning, match="omitting the field"):
        assert options.timestamp("no idea") is None
    with pytest.warns(UserWarning, match="schema requires the field"):
        assert options.timestamp("no idea", required=True) == "no idea"
    # A value that reads cleanly is unaffected, and says nothing.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert options.timestamp("27-Feb-18, 10:11:50", required=True) == \
            "2018-02-27T10:11:50"


def test_timezone_fills_in_a_missing_offset_but_never_overrides_one():
    from rainbow.asm import _iso_timestamp
    # The source recorded no zone, so the caller's offset is used.
    assert _iso_timestamp("27-Feb-18, 10:11:50", "-05:00") == \
        "2018-02-27T10:11:50-05:00"
    # The source recorded one, so it wins: it is what the instrument said.
    assert _iso_timestamp("3 Feb 22  11:22 am -0500", "+09:00") == \
        "2022-02-03T11:22:00-05:00"


def test_an_offset_a_sibling_file_recorded_outranks_the_callers():
    """ timezone= must fill in a missing zone, never overwrite a recorded one.

    A ChemStation run spells the same instant differently per detector, and
    only the MS spelling carries a UTC offset. Which spelling wins the
    directory-level vote comes down to how many channels the run happened to
    have, so without this a caller passing timezone= would silently move
    orange.D's timestamps five hours while the right offset sat in a sibling.
    """
    datadir = rb.read("tests/inputs/orange.D")
    # The vote is unchanged: the .ch spelling is the more precise one.
    assert datadir.metadata["date"] == "14-Nov-19, 15:08:08"
    assert datadir.metadata["utc_offset"] == "-05:00"
    lc = datadir.to_asm(timezone="+00:00")[
        "liquid chromatography aggregate document"][
        "liquid chromatography document"][0]
    for measurement in lc["measurement aggregate document"][
            "measurement document"]:
        assert measurement["measurement time"] == "2019-11-14T15:08:08-05:00"


def test_timezone_option_is_validated():
    from rainbow.asm import _utc_offset
    assert _utc_offset(None) is None
    assert _utc_offset("Z") == "+00:00"
    assert _utc_offset("-0500") == "-05:00"
    assert _utc_offset("+09:00") == "+09:00"
    assert _utc_offset("+14:00") == "+14:00"          # the largest real offset
    # Whitespace survives a config read or a shell capture, and the offset is
    # concatenated onto every timestamp, so it is stripped rather than carried.
    assert _utc_offset("+05:00\n") == "+05:00"
    assert _utc_offset("  -05:00  ") == "-05:00"
    for bad in ("EST", "5", "+5:00", 3, "-25:00 extra", "",
                # Shape alone is not enough: these all match [+-]dd:?dd but no
                # RFC 3339 reader accepts the timestamps they would produce.
                "+24:00", "+99:99", "+05:60", "+14:01",
                # \d is Unicode-aware, so digits need pinning to ASCII.
                "+٠٥:٣٠"):
        with pytest.raises(Exception, match="timezone must be"):
            _utc_offset(bad)


def test_export_emits_iso_timestamps_for_every_vendor():
    # The end-to-end result: no fixture exports a vendor-format timestamp.
    import json
    import re
    for fixture in ("red.D", "green.D", "pink.D", "teal.dx", "violet.raw",
                    "yellow.D", "orange.D"):
        document = json.dumps(rb.read("tests/inputs/" + fixture).to_asm())
        stamps = re.findall(r'"(?:measurement|injection) time": "([^"]*)"',
                            document)
        assert stamps, fixture
        for stamp in stamps:
            assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", stamp), \
                (fixture, stamp)


# --- the arithmetic that turns a vendor timestamp into an instant ---
#
# These pin the three calculations a wrong answer would slip through
# silently: they produce a plausible timestamp, not an error. Mutation
# testing found all three unguarded.


@pytest.mark.parametrize("vendor,expected", [
    # Noon and midnight are the two hours the % 12 exists for, and the two it
    # gets wrong if dropped: 12 pm is 12:00, not 24:00 (which raises, so the
    # timestamp silently disappears), and 12 am is 00:00, not 12:00.
    ("3 Feb 22  12:22 pm", "2022-02-03T12:22:00"),
    ("3 Feb 22  12:22 am", "2022-02-03T00:22:00"),
    ("3 Feb 22  12:00 am", "2022-02-03T00:00:00"),
    ("3 Feb 22  11:22 am", "2022-02-03T11:22:00"),
    ("3 Feb 22  11:22 pm", "2022-02-03T23:22:00"),
    ("3 Feb 22  1:22 pm", "2022-02-03T13:22:00"),
])
def test_the_meridiem_hour_converts_at_noon_and_midnight(vendor, expected):
    from rainbow.asm import _iso_timestamp
    assert _iso_timestamp(vendor) == expected


@pytest.mark.parametrize("vendor,expected", [
    # The pivot strptime's %y uses. Either side of it is a plausible date, so
    # getting it wrong moves a run by a century without complaint.
    ("3 Feb 68  10:11:50", "2068-02-03T10:11:50"),
    ("3 Feb 69  10:11:50", "1969-02-03T10:11:50"),
    ("3 Feb 99  10:11:50", "1999-02-03T10:11:50"),
    ("3 Feb 00  10:11:50", "2000-02-03T10:11:50"),
])
def test_the_two_digit_year_pivots_where_strptime_does(vendor, expected):
    from rainbow.asm import _iso_timestamp
    assert _iso_timestamp(vendor) == expected


def test_absorbance_in_au_is_scaled_to_the_milli_absorbance_the_schema_pins():
    """ The LC schema pins absorbance to mAU, and Waters records AU.

    A missing or wrong factor exports the signal a thousand times too small,
    which validates cleanly and is wrong by three orders of magnitude. Only
    the network-dependent schema suite covered this, and it skips by default.
    """
    import numpy as np
    from rainbow.datafile import DataFile
    from rainbow.datadirectory import DataDirectory

    channel = DataFile("UV1.dat", "UV",
                       np.array([0.0, 1.0]), np.array([254.0]),
                       np.array([[-1.6], [2.5]]), {"unit": "AU"})
    document = DataDirectory("run", [channel], {}).to_asm()
    measurement = _by_label(document)["UV1.dat"]
    cube = measurement[_CHROM_KEY]
    assert cube["cube-structure"]["measures"][0]["unit"] == "mAU"
    assert cube["data"]["measures"][0] == [-1600.0, 2500.0]

    # A channel already in mAU is passed through unscaled.
    channel.metadata["unit"] = "mAU"
    again = _by_label(DataDirectory("run", [channel], {}).to_asm())["UV1.dat"]
    assert again[_CHROM_KEY]["data"]["measures"][0] == [-1.6, 2.5]
