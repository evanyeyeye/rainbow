"""
Round-trip tests: .D + aux -> rainbow objects -> ASM -> rainbow objects.

These build a synthetic sequence from copies of the brown.D UV fixture plus a
synthetic sequence.acaml (instrument + peaks), export it to ASM, read it back
with sequence_from_asm, and check that the data, peaks, and metadata survive
the lap. A few hand-built ASM dicts cover from_asm and the helpers directly.
"""
import json
import os
import shutil

import numpy as np
import pytest

import rainbow as rb
from rainbow import asm


INPUTS = os.path.join(os.path.dirname(__file__), "inputs")
FIXTURE = os.path.join(os.path.dirname(__file__), "inputs", "brown.D")
INJECTION_NAMES = ["008-D1F-A1-sample_01.D", "009-D1F-A2-sample_02.D"]

SEQUENCE_ACAML = """<?xml version="1.0" encoding="utf-8"?>
<ACAML xmlns="urn:schemas-agilent-com:acaml15"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Doc>
    <DocInfo><CreatedByUser>LAB\\runner</CreatedByUser></DocInfo>
    <Content>
      <Resources>
        <Instrument xsi:type="InstrumentType" id="i">
          <Name>1290</Name><Technique>LiquidChromatography</Technique>
          <Module>
            <Name>DAD</Name><Type>Detector</Type>
            <PartNo>G7117B</PartNo><SerialNo>SN-DAD</SerialNo>
            <FirmwareRevision>D.07.35</FirmwareRevision>
          </Module>
          <Module>
            <Name>Quat. Pump</Name><Type>Pump</Type>
            <PartNo>G7104A</PartNo><SerialNo>SN-PUMP</SerialNo>
            <FirmwareRevision>B.07.35</FirmwareRevision>
          </Module>
        </Instrument>
        <Signal xsi:type="SignalType" id="sig-254">
          <BinaryData><DataItem><Data><DataFileReference>
            <Path>008-D1F-A1-sample_01.D\\dad1A.ch</Path>
          </DataFileReference></Data></DataItem></BinaryData>
          <Name>DAD1A</Name><Description>DAD1 A, Sig=254,4</Description>
        </Signal>
      </Resources>
      <Injections>
        <Result xsi:type="InjectionResultType" id="r">
          <SignalResult id="sr">
            <Signal_ID id="sig-254" />
            <Peak id="p1">
              <RetentionTime val="1.0" /><Area val="100.0" />
              <Height val="10.0" /><AreaPercent val="60.0" />
              <BeginTime val="0.9" /><EndTime val="1.1" />
              <Symmetry val="0.95" />
            </Peak>
          </SignalResult>
        </Result>
      </Injections>
    </Content>
  </Doc>
</ACAML>
"""


@pytest.fixture
def original(tmp_path):
    seq = tmp_path / "Seq"
    seq.mkdir()
    for name in INJECTION_NAMES:
        shutil.copytree(FIXTURE, seq / name)
    (seq / "sequence.acaml").write_text(SEQUENCE_ACAML, encoding="utf-8")
    return rb.read_sequence(str(seq), peaks=True)


@pytest.fixture
def reconstructed(original):
    return rb.sequence_from_asm(original.to_asm())


def test_injection_count_survives(original, reconstructed):
    assert len(reconstructed) == len(original)


def test_uv_data_arrays_survive_exactly(original, reconstructed):
    for inj1, inj2 in zip(original, reconstructed):
        by_name = {d.name: d for d in inj2.datafiles}
        assert set(by_name) == {d.name for d in inj1.datafiles}
        for datafile in inj1.datafiles:
            back = by_name[datafile.name]
            np.testing.assert_allclose(back.data, datafile.data,
                                       rtol=1e-9, atol=1e-9)
            np.testing.assert_allclose(back.xlabels, datafile.xlabels,
                                       rtol=1e-9, atol=1e-6)


def test_peaks_survive(original, reconstructed):
    inj1 = original.injections[0]
    inj2 = reconstructed.injections[0]
    peaks1 = inj1.peaks[0]["peaks"]
    peaks2 = inj2.peaks[0]["peaks"]
    assert len(peaks1) == len(peaks2) == 1
    assert inj2.peaks[0]["wavelength"] == 254.0
    p1, p2 = peaks1[0], peaks2[0]
    assert p1["area"] == p2["area"] == 100.0
    assert abs(p1["retention_time"] - p2["retention_time"]) < 1e-9


def test_instrument_survives(original, reconstructed):
    modules1 = original.metadata["instrument"]["modules"]
    modules2 = reconstructed.metadata["instrument"]["modules"]
    assert len(modules1) == len(modules2) == 2
    dad1 = next(m for m in modules1 if m["name"] == "DAD")
    dad2 = next(m for m in modules2 if m["name"] == "DAD")
    assert dad2["part_no"] == dad1["part_no"] == "G7117B"
    assert dad2["serial_no"] == dad1["serial_no"] == "SN-DAD"
    assert dad2["firmware"] == dad1["firmware"] == "D.07.35"


def test_operator_survives(original, reconstructed):
    assert reconstructed.metadata["operator"] == original.metadata["operator"]
    assert all(inj.metadata.get("operator") == "LAB\\runner"
               for inj in reconstructed)


def test_injections_named_by_index_without_a_sample_identifier(reconstructed):
    # brown.D carries no sample identifier, so injections fall back to an index.
    assert [inj.name for inj in reconstructed] == ["injection_1", "injection_2"]


def test_injection_named_from_the_identifier_the_document_carries():
    # The .D folder name IS stored, as the injection document's "injection
    # identifier", so the injection comes back under the name the caller knows
    # rather than its sample identifier ('usp' here), which a set of replicates
    # would share.
    back = rb.sequence_from_asm(rb.read("tests/inputs/red.D").to_asm())
    assert back.injections[0].name == "red.D"


def test_injection_falls_back_to_the_sample_without_an_injection_document():
    # A liquid chromatography run that records no injection volume gets no
    # injection document at all, because the schema requires the volume beside
    # the identifier. Such a run still comes back under its sample identifier.
    datadir = rb.read("tests/inputs/red.D")
    datadir.metadata.pop("injection_volume", None)
    back = rb.sequence_from_asm(datadir.to_asm())
    assert back.injections[0].name == "usp"


def test_envelope_fields_round_trip():
    # red.D carries the envelope fields brown.D lacks; confirm they survive
    # .D -> ASM -> objects.
    from rainbow.asm import _iso_timestamp
    original = rb.read("tests/inputs/red.D")
    back = rb.from_asm(original.to_asm())
    assert back.metadata["sample"] == original.metadata["sample"]
    # The date comes back as the ISO 8601 timestamp ASM requires, not the
    # Chemstation wall-clock string it went out as. Same instant, normalized:
    # the vendor spelling is not a shape any ASM reader could be asked to parse.
    assert back.metadata["date"] == _iso_timestamp(original.metadata["date"])
    assert back.metadata["date"] == "2018-02-27T10:11:50"
    assert str(back.metadata["vialpos"]) == str(original.metadata["vialpos"])
    assert back.metadata["injection_volume"] == \
        original.metadata["injection_volume"]


def test_a_cad_channel_comes_back_as_cad():
    # red.D has a CAD channel (an electric-current cube) alongside its UV
    # channels. It is rebuilt with the detector it was exported from and the
    # unit its cube states, never as a UV trace.
    original = rb.read("tests/inputs/red.D")
    assert any(d.detector == "CAD" for d in original.datafiles)
    back = rb.from_asm(original.to_asm())
    cad = back.get_file("ADC1A.CH")
    assert cad.detector == "CAD"
    # Its unit as red.D records it: published as pA, which the schema needs,
    # with the note that restores it.
    assert cad.metadata["unit"] == "mAu"
    assert cad.metadata["unit"] == original.get_file("ADC1A.CH").metadata[
        "unit"]
    assert cad.metadata["measure"] == "electric current"
    assert cad.data[:, 0].tolist() \
        == original.get_file("ADC1A.CH").data[:, 0].tolist()
    assert {d.detector for d in back.datafiles} == {"UV", "CAD"}


def test_multiple_channels_keep_separate_peak_lists():
    # Two channels with distinct peak lists must not cross-attach.
    datadir = rb.read("tests/inputs/red.D")
    datadir.peaks = [
        {"signal": "DAD1B", "wavelength": 280.0, "description": None,
         "channel_file": "DAD1B.ch",
         "peaks": [{"retention_time": 1.0, "area": 11.0}]},
        {"signal": "DAD1C", "wavelength": 210.0, "description": None,
         "channel_file": "DAD1C.ch",
         "peaks": [{"retention_time": 2.0, "area": 22.0},
                   {"retention_time": 3.0, "area": 33.0}]},
    ]
    document = datadir.to_asm()
    measurements = (document["liquid chromatography aggregate document"]
                    ["liquid chromatography document"][0]
                    ["measurement aggregate document"]["measurement document"])
    by_id = {m["measurement identifier"]: m for m in measurements}

    def peak_areas(measurement):
        return [p["peak area"]["value"] for p in
                (measurement["processed data aggregate document"]
                 ["processed data document"][0]["peak list"]["peak"])]

    assert peak_areas(by_id["DAD1B.ch"]) == [11.0]
    assert peak_areas(by_id["DAD1C.ch"]) == [22.0, 33.0]
    # The DAD spectrum channel had no peaks and must carry no processed data.
    assert "processed data aggregate document" not in by_id["DAD1.UV"]


def test_asm_peak_skips_non_numeric_measure():
    # A malformed val that arrived as a string must not abort the export.
    peak = asm._asm_peak(1, {"retention_time": "bad", "area": 100.0,
                             "height": None})
    assert "retention time" not in peak
    assert "peak height" not in peak
    assert peak["peak area"]["value"] == 100.0


def test_from_asm_skips_measurement_without_a_cube():
    document = {"liquid chromatography aggregate document": {
        "device system document": {
            "device document": [{"device type": "liquid chromatograph"}]},
        "liquid chromatography document": [{
            "analyst": "x", "measurement aggregate document": {
                "measurement document": [{"measurement identifier": "empty"}]}}]}}
    datadir = rb.from_asm(document)
    assert datadir.datafiles == []


# --- direct helper / single-injection tests on hand-built ASM ---

def _minimal_asm():
    return rb.read(os.path.join(os.path.dirname(__file__),
                                "inputs", "brown.D")).to_asm()


def test_from_asm_reconstructs_a_directory():
    document = _minimal_asm()
    original = rb.read(os.path.join(os.path.dirname(__file__),
                                    "inputs", "brown.D"))
    back = rb.from_asm(document, name="brown.D")
    assert back.name == "brown.D"
    assert "UV" in back.detectors
    assert {d.name for d in back.datafiles} == {d.name for d in original.datafiles}
    for datafile in original.datafiles:
        np.testing.assert_allclose(
            back.get_file(datafile.name).data, datafile.data,
            rtol=1e-9, atol=1e-9)


def test_instrument_from_device_system_skips_bare_fallback():
    bare = {"asset management identifier": "unknown",
            "device document": [{"device type": "liquid chromatograph"}]}
    assert asm._instrument_from_device_system(bare) is None


def test_instrument_from_device_system_reads_modules():
    dsd = {"asset management identifier": "1290", "device document": [
        {"device identifier": "DAD", "written name": "DAD",
         "device type": "diode array detector", "model number": "G7117B",
         "equipment serial number": "SN1", "firmware version": "D.07"}]}
    instrument = asm._instrument_from_device_system(dsd)
    assert instrument["name"] == "1290"
    assert instrument["modules"][0]["serial_no"] == "SN1"
    assert instrument["modules"][0]["part_no"] == "G7117B"


def test_peak_from_asm_converts_seconds_back_to_minutes():
    asm_peak = {"retention time": {"value": 120.0, "unit": "s"},
                "peak area": {"value": 50.0, "unit": "mAU.s"}}
    peak = asm._peak_from_asm(asm_peak)
    assert peak["retention_time"] == 2.0
    assert peak["area"] == 50.0


def test_from_asm_reads_external_uv_document():
    # A document rainbow did not write (third-party converter, rich envelope
    # with many extra fields) still reads: the UV chromatogram is reconstructed
    # and the unfamiliar fields are ignored. Fixture is sanitized/synthetic.
    with open(os.path.join(INPUTS, "external_uv.asm.json")) as f:
        document = json.load(f)
    datadir = rb.from_asm(document)

    assert len(datadir.datafiles) == 1
    datafile = datadir.datafiles[0]
    assert datafile.detector == 'UV'
    np.testing.assert_allclose(
        datafile.xlabels, np.array([0.0, 30.0, 60.0]) / 60.0)
    np.testing.assert_allclose(datafile.data[:, 0], [0.1, 5.0, 0.2])
    assert datafile.metadata.get("wavelength") == 254.0
    assert datadir.metadata.get("sample") == "Sample A"


def test_from_asm_skips_mass_chromatogram_keeps_uv():
    # An LC-MS document mixes a mass chromatogram cube (which rainbow does not
    # reconstruct) with a UV chromatogram cube. from_asm keeps the UV trace and
    # skips the MS one rather than crashing.
    with open(os.path.join(INPUTS, "external_lcms.asm.json")) as f:
        document = json.load(f)
    datadir = rb.from_asm(document)

    assert [df.name for df in datadir.datafiles] == ["trace-uv"]
    assert datadir.datafiles[0].detector == 'UV'


def test_masshunter_dad_survives_the_lap():
    """ A MassHunter DAD's signals and spectra come back unchanged. """
    original = rb.read(os.path.join(INPUTS, "bronze.D"))
    reconstructed = rb.from_asm(original.to_asm())

    before = {df.name: df for df in original.datafiles}
    after = {df.name: df for df in reconstructed.datafiles}
    assert before.keys() == after.keys()
    for name, source in before.items():
        target = after[name]
        # The wavelength of a single-signal channel travels as the detector
        # wavelength setting, so it survives rather than coming back blank.
        np.testing.assert_allclose(
            np.asarray(source.ylabels, dtype=float),
            np.asarray(target.ylabels, dtype=float))
        np.testing.assert_allclose(
            source.data.astype(float), target.data.astype(float))
        np.testing.assert_allclose(source.xlabels, target.xlabels)


def test_from_asm_tolerates_a_document_without_measurements():
    """ A third-party document missing the measurement keys is not fatal. """
    document = {
        "liquid chromatography aggregate document": {
            "liquid chromatography document": [{"analyst": "someone"}],
        },
    }
    datadir = rb.from_asm(document)
    assert datadir.datafiles == []
    assert datadir.metadata["operator"] == "someone"


def test_from_asm_accepts_a_lone_measurement_object():
    """ Some writers emit one measurement object where the list is allowed. """
    document = {
        "liquid chromatography aggregate document": {
            "liquid chromatography document": [{
                "measurement aggregate document": {
                    "measurement document": {
                        "measurement identifier": "solo.ch",
                        "chromatogram data cube": {
                            "label": "solo.ch",
                            "cube-structure": {
                                "dimensions": [{"concept": "retention time",
                                                "unit": "s"}],
                                "measures": [{"concept": "absorbance",
                                              "unit": "mAU"}],
                            },
                            "data": {"dimensions": [[0.0, 60.0]],
                                     "measures": [[1.0, 2.0]]},
                        },
                    },
                },
            }],
        },
    }
    datadir = rb.from_asm(document)
    assert [df.name for df in datadir.datafiles] == ["solo.ch"]


def test_documented_idempotence_holds_for_an_absorbance_run():
    """ The recipe in docs/source/asm/roundtrip.rst, kept honest. """
    datadir = rb.read(os.path.join(INPUTS, "brown.D"))
    assert not datadir.detectors - {"UV"}, "fixture must be absorbance-only"
    first = datadir.to_asm()
    again = rb.from_asm(first, name=datadir.name).to_asm()
    assert again == first


def test_a_non_absorbance_channel_survives_re_export():
    """ A CAD cube is read back, so a second export still carries it. """
    datadir = rb.read(os.path.join(INPUTS, "red.D"))
    assert "CAD" in datadir.detectors
    first = datadir.to_asm()
    again = rb.from_asm(first, name=datadir.name).to_asm()

    def labels(document):
        aggregate = document["liquid chromatography aggregate document"]
        return {cube["label"]
                for injection in aggregate["liquid chromatography document"]
                for measurement in (injection["measurement aggregate document"]
                                    ["measurement document"])
                for key, cube in measurement.items() if key.endswith("cube")}

    assert labels(first) == labels(again)


def test_rid_rides_the_absorbance_cube_and_returns():
    """ RID is documented as NOT export-only, unlike CAD/ELSD/FID. """
    import numpy as np
    from rainbow.datafile import DataFile
    from rainbow.datadirectory import DataDirectory
    rid = DataFile("RID1A.ch", "RID", np.array([0.0, 1.0]), np.array([1.0]),
                   np.array([[10.0], [20.0]]), {})
    reconstructed = rb.from_asm(DataDirectory("/rid.D", [rid], {}).to_asm())
    assert [df.name for df in reconstructed.datafiles] == ["RID1A.ch"]


# ---------------------------------------------------------------------------
# from_asm against documents rainbow did not write. The published cube schema
# does not require the `data` member, and writers differ on whether a
# single-entry list is emitted as a list, so none of these shapes may raise.
# ---------------------------------------------------------------------------

def _lc(*measurements):
    return {"liquid chromatography aggregate document": {
        "liquid chromatography document": [
            {"measurement aggregate document": {
                "measurement document": list(measurements)}}]}}


_STRUCTURE = {"cube-structure": {
    "dimensions": [{"concept": "retention time", "unit": "s"}],
    "measures": [{"concept": "absorbance", "unit": "mAU"}]}}


def _with_cube(**measurement):
    """A measurement carrying a real absorbance cube, plus ``measurement``.

    A measurement with no cube is skipped before its envelope is ever read, so a
    document shape attached to a cubeless measurement tests nothing. Anything
    exercising the envelope (sample document, device control, processed data)
    has to hang off a measurement that actually reconstructs.
    """
    measurement["chromatogram data cube"] = dict(_STRUCTURE, data={
        "dimensions": [[0.0, 60.0]], "measures": [[1.0, 2.0]]})
    return measurement


@pytest.mark.parametrize("document", [
    pytest.param(_lc({"chromatogram data cube": dict(_STRUCTURE)}),
                 id="chromatogram-cube-without-data"),
    pytest.param(_lc({"three-dimensional ultraviolet spectrum data cube":
                      dict(_STRUCTURE)}),
                 id="spectrum-cube-without-data"),
    pytest.param(_lc({"chromatogram data cube": dict(
        _STRUCTURE, data={"dimensions": [[0.0]], "measures": []})}),
        id="cube-with-empty-measures"),
    pytest.param(_lc({"three-dimensional ultraviolet spectrum data cube": dict(
        _STRUCTURE, data={"dimensions": [[0.0]], "measures": [[1.0]]})}),
        id="spectrum-cube-missing-its-second-axis"),
    pytest.param(_lc(_with_cube(**{"device control aggregate document":
                                   {"device control document": []}})),
                 id="empty-device-control-document"),
    pytest.param(_lc(_with_cube(**{"device control aggregate document":
                                   {"device control document":
                                    {"device type": "x"}}})),
                 id="lone-device-control-object"),
    pytest.param(_lc(_with_cube(**{"sample document":
                                   [{"sample identifier": "s"}]})),
                 id="sample-document-as-a-list"),
    pytest.param(_lc(_with_cube(**{"processed data aggregate document":
                                   {"processed data document":
                                    {"peak list": {"peak": []}}}})),
                 id="lone-processed-data-object"),
    # Fields a foreign writer may fill with something other than the declared
    # type. Each hangs off a real cube, so the envelope is genuinely parsed.
    pytest.param(_lc(_with_cube(**{"injection document": "not an object"})),
                 id="injection-document-is-not-an-object"),
    pytest.param(_lc(_with_cube(**{"measurement identifier": ["a", "b"]})),
                 id="measurement-identifier-is-not-a-string"),
    pytest.param(_lc(_with_cube(**{"measurement time": {"value": "now"}})),
                 id="measurement-time-as-a-value-object"),
    pytest.param(_lc(_with_cube(**{"sample document":
                                   {"sample identifier": 7}})),
                 id="sample-identifier-is-not-a-string"),
    pytest.param(_lc(_with_cube(**{"processed data aggregate document":
                                   {"processed data document":
                                    {"peak list": {"peak": ["nope"]}}}})),
                 id="peak-list-entry-is-not-an-object"),
    pytest.param({"liquid chromatography aggregate document": {
        "device system document": "not an object",
        "liquid chromatography document": []}},
        id="device-system-is-not-an-object"),
    pytest.param({"liquid chromatography aggregate document": {
        "device system document": {"device document": None},
        "liquid chromatography document": []}},
        id="device-document-is-not-a-list"),
    pytest.param({"liquid chromatography aggregate document": {
        "device system document": {"device document": ["nope"]},
        "liquid chromatography document": []}},
        id="device-document-entry-is-not-an-object"),
    pytest.param({"liquid chromatography aggregate document": {
        "liquid chromatography document": [{"analyst": {"value": "someone"}}]}},
        id="analyst-as-a-value-object"),
    pytest.param(_lc({"chromatogram data cube": "not an object"}),
                 id="chromatogram-cube-is-not-an-object"),
    pytest.param(_lc({"chromatogram data cube": dict(
        _STRUCTURE, data={"dimensions": [["not a number"]],
                          "measures": [[1.0]]})}),
        id="cube-values-are-not-numbers"),
    pytest.param({"liquid chromatography aggregate document": {
        "liquid chromatography document": {"analyst": "someone"}}},
        id="lone-lc-document-object"),
    pytest.param({"liquid chromatography aggregate document": {
        "liquid chromatography document": ["not a document"]}},
        id="lc-document-is-not-an-object"),
    pytest.param({"liquid chromatography aggregate document": {
        "liquid chromatography document": [
            {"measurement aggregate document": []}]}},
        id="measurement-aggregate-as-a-list"),
    # A time axis numpy converts to the wrong number of axes rather than
    # rejecting. These reach the DataFile constructor, whose own argument check
    # would take down every other channel in the document.
    pytest.param(_lc({"chromatogram data cube": dict(
        _STRUCTURE, data={"dimensions": [7], "measures": [[1.0, 2.0]]})}),
        id="time-axis-is-a-bare-number"),
    pytest.param(_lc({"chromatogram data cube": dict(
        _STRUCTURE, data={"dimensions": [None], "measures": [[1.0, 2.0]]})}),
        id="time-axis-is-null"),
    pytest.param(_lc({"chromatogram data cube": dict(
        _STRUCTURE, data={"dimensions": [[[0.0, 60.0]]],
                          "measures": [[1.0, 2.0]]})}),
        id="time-axis-is-nested-one-level-too-deep"),
    # JSON integer literals are unbounded, so this raises OverflowError on the
    # way to a float rather than the TypeError/ValueError numpy usually gives.
    pytest.param(_lc({"chromatogram data cube": dict(
        _STRUCTURE, data={"dimensions": [[10 ** 400, 60.0]],
                          "measures": [[1.0, 2.0]]})}),
        id="time-axis-value-overflows-a-float"),
    pytest.param(_lc(_with_cube(**{"processed data aggregate document":
                                   {"processed data document":
                                    {"peak list": {"peak": [
                                        {"retention time":
                                         {"value": "1.5", "unit": "s"}}]}}}})),
        id="peak-quantity-is-a-numeric-string"),
    # The same unbounded integer in a peak time, which is divided to minutes on
    # the way in. The cube path above was guarded a round before this one was.
    pytest.param(_lc(_with_cube(**{"processed data aggregate document":
                                   {"processed data document":
                                    {"peak list": {"peak": [
                                        {"retention time": 10 ** 400}]}}}})),
        id="peak-time-overflows-a-float"),
    # With an identifier, so the peak group is joined to the channel and
    # reaches to_asm. Without one it is dropped before the huge area is
    # touched, and the case never exercises the overflow at all.
    pytest.param(_lc(_with_cube(**{
        "measurement identifier": "ch1",
        "processed data aggregate document":
            {"processed data document":
             {"peak list": {"peak": [
                 {"retention time": 1.5,
                  "peak area": {"value": 10 ** 400}}]}}}})),
        id="peak-area-overflows-a-float"),
    pytest.param(_lc(_with_cube(**{"injection document": {
        "autosampler injection volume setting (chromatography)":
            {"value": "lots"}}})),
        id="injection-volume-is-not-a-number"),
    pytest.param(_lc(_with_cube(**{"device control aggregate document": {
        "device control document": [
            {"detector wavelength setting": {"value": {"nested": 1}}}]}})),
        id="wavelength-setting-is-not-a-number"),
])
def test_from_asm_does_not_raise_on_a_foreign_document_shape(document):
    datadir = rb.from_asm(document)
    # Whatever it could not represent is skipped, not fatal.
    assert isinstance(datadir.datafiles, list)
    # The same document read as a sequence takes a different path through the
    # envelope (the device system, the injection naming), so it is read too.
    assert isinstance(rb.sequence_from_asm(document).injections, list)
    # Reading it must not leave behind something that cannot be written back
    # out. A value that survives the read but overflows on the way to seconds
    # would raise here, out of a method the caller has every reason to expect
    # works on anything from_asm returned.
    assert isinstance(datadir.to_asm(), dict)


def test_a_foreign_envelope_shape_does_not_cost_the_channel():
    """ A shape rainbow cannot read must cost only the field it sits in.

    Every one of these hangs off a real absorbance cube: the channel still comes
    back, and only the unreadable field is dropped. Without this the shapes
    above could be attached to cubeless measurements, which are skipped before
    the envelope is ever parsed, and would assert nothing.
    """
    shapes = [
        {"injection document": "not an object"},
        {"measurement identifier": ["a", "b"]},
        {"sample document": {"sample identifier": 7}},
        {"device control aggregate document":
            {"device control document": {"device type": "x"}}},
        {"processed data aggregate document":
            {"processed data document": {"peak list": {"peak": ["nope"]}}}},
    ]
    for shape in shapes:
        datadir = rb.from_asm(_lc(_with_cube(**shape)))
        assert len(datadir.datafiles) == 1, shape
        assert datadir.datafiles[0].data.shape == (2, 1), shape


def test_a_cube_whose_measure_does_not_match_its_time_axis_is_skipped():
    """ A short measure array must cost the channel, not misalign it.

    ``reshape(-1, 1)`` accepts any length, so a measure array one value short
    of its time axis silently pairs every later point with the wrong retention
    time. DataFile checks only ndim, and nothing downstream rechecks, so the
    corruption surfaces far away (an IndexError inside to_csvstr) or not at
    all. Skipping is the honest answer.
    """
    document = _lc({"measurement identifier": "short.ch",
                    "chromatogram data cube": dict(_STRUCTURE, data={
                        "dimensions": [[0.0, 30.0, 60.0]],
                        "measures": [[1.0, 2.0]]})})
    with pytest.warns(UserWarning, match="2 values for 3 retention times"):
        datadir = rb.from_asm(document)
    assert datadir.datafiles == []


def test_a_peak_quantity_that_is_not_a_number_drops_to_none():
    """ A measure spelled as text must not reach the seconds-to-minutes divide.

    Numbers-as-strings are a common foreign-writer habit, and rainbow already
    tolerates them inside a cube because numpy coerces. The export side skips a
    non-numeric measure rather than failing the whole document, so the import
    side has to agree instead of raising TypeError from a division.
    """
    document = _lc(_with_cube(**{"processed data aggregate document": {
        "processed data document": [{"peak list": {"peak": [{
            "retention time": {"value": "1.5", "unit": "s"},
            "peak area": {"value": "100"},
            "peak height": {"value": 12.5}}]}}]}}))
    peaks = rb.from_asm(document).peaks[0]["peaks"]
    assert peaks[0]["retention_time"] is None
    assert peaks[0]["area"] is None
    # A genuine number in the same peak still comes through.
    assert peaks[0]["height"] == 12.5


@pytest.mark.parametrize("document", ["{}", [], None, 3, b"{}"])
def test_from_asm_rejects_a_document_that_is_not_a_dict(document):
    """ Forgetting json.load must say so, not fail deep in the envelope. """
    with pytest.raises(TypeError, match="must be a dict"):
        rb.from_asm(document)
    with pytest.raises(TypeError, match="must be a dict"):
        rb.sequence_from_asm(document)


def test_an_unreadable_channel_is_warned_about_rather_than_dropped_silently():
    """ A document whose channels are all unreadable must not look empty.

    from_asm returning an empty DataDirectory is indistinguishable from a
    document that legitimately carries no UV cube, so a reader that gets
    nothing back has no way to tell a broken file from an export-only one.
    """
    document = _lc({"measurement identifier": "bad.ch",
                    "chromatogram data cube": dict(_STRUCTURE, data={
                        "dimensions": [["not a number"]],
                        "measures": [[1.0]]})})
    with pytest.warns(UserWarning, match="bad.ch"):
        assert rb.from_asm(document).datafiles == []


def test_a_peak_list_that_cannot_be_keyed_to_a_channel_warns():
    """ Peaks read and then discarded on re-export must not go unmentioned. """
    document = _lc(_with_cube(**{
        "measurement identifier": 7,
        "processed data aggregate document": {
            "processed data document": [{"peak list": {"peak": [
                {"retention time": {"value": 90.0, "unit": "s"}}]}}]}}))
    with pytest.warns(UserWarning, match="cannot be joined to a channel"):
        rb.from_asm(document)


def test_from_asm_still_reads_a_lone_measurement_object():
    document = _lc({
        "measurement identifier": "solo.ch",
        "chromatogram data cube": dict(_STRUCTURE, data={
            "dimensions": [[0.0, 60.0]], "measures": [[1.0, 2.0]]})})
    document["liquid chromatography aggregate document"][
        "liquid chromatography document"][0][
        "measurement aggregate document"]["measurement document"] = \
        document["liquid chromatography aggregate document"][
            "liquid chromatography document"][0][
            "measurement aggregate document"]["measurement document"][0]
    assert [df.name for df in rb.from_asm(document).datafiles] == ["solo.ch"]


# The idempotence contract the ASM round-trip documentation states, run as a
# test so the two cannot drift apart. Exact document equality is NOT the
# contract: an export-only channel is absent from the second document, and the
# seconds-to-minutes conversion is not always reversible to the last bit.

def _asm_measurements(document):
    aggregate, = (v for k, v in document.items()
                  if k.endswith("aggregate document"))
    injections, = (v for k, v in aggregate.items()
                   if k.endswith("chromatography document"))
    for injection in injections:
        yield from injection[
            "measurement aggregate document"]["measurement document"]


def _asm_cube(measurement):
    key, = (k for k in measurement if k.endswith("data cube"))
    return measurement[key]["data"]


@pytest.mark.parametrize("fixture", [
    "red.D",          # UV channels beside an export-only CAD channel
    "violet.raw",     # UV channels beside an export-only ELSD channel
    "white.raw",      # all absorbance; retention times drift by ulps
    "teal.dx",
    "bronze.D",
])
def test_a_second_export_reproduces_the_first(fixture):
    import numpy as np
    datadir = rb.read(os.path.join(INPUTS, fixture))
    first = datadir.to_asm()
    again = rb.from_asm(first, name=datadir.name).to_asm()

    rebuilt = {m["measurement identifier"]: m for m in _asm_measurements(again)}
    compared = 0
    for before in _asm_measurements(first):
        after = rebuilt.get(before["measurement identifier"])
        if after is None:
            continue  # export-only (a non-absorbance cube), as documented
        assert _asm_cube(before)["measures"] == _asm_cube(after)["measures"]
        assert np.allclose(_asm_cube(before)["dimensions"][0],
                           _asm_cube(after)["dimensions"][0])
        compared += 1
    assert compared, "no channel was rebuilt, so nothing was compared"


def test_exact_equality_is_not_the_round_trip_contract():
    """ The contract is that the values survive, not that the bytes match.

    The documentation used to assert `again == first`. white.raw falsifies it:
    the seconds-to-minutes conversion is not exactly reversible for these
    retention times, so the second export differs in the last digit.

    What is asserted here is only the real contract, closeness. Pinning the
    inequality instead would enshrine the drift, so making the conversion
    exactly reversible some day, which would be an improvement, would break
    this test.

    white.raw is all absorbance, so every channel must come back. Pairing by
    identifier rather than by position matters: zip would truncate against a
    shorter second export, and a from_asm regression that silently drops
    channels would sail through.
    """
    import numpy as np
    datadir = rb.read(os.path.join(INPUTS, "white.raw"))
    first = datadir.to_asm()
    again = rb.from_asm(first, name=datadir.name).to_asm()

    before = {m["measurement identifier"]: m for m in _asm_measurements(first)}
    after = {m["measurement identifier"]: m for m in _asm_measurements(again)}
    assert len(before) == len(datadir.datafiles)
    assert set(after) == set(before), "a channel was lost on the round trip"
    for name, source in before.items():
        assert np.allclose(_asm_cube(source)["dimensions"][0],
                           _asm_cube(after[name])["dimensions"][0])
        assert _asm_cube(source)["measures"] == \
            _asm_cube(after[name])["measures"]


def test_replicate_injections_survive_as_separate_injections(tmp_path):
    """ A sequence of replicates must not collapse on the way back.

    Injections are named after their sample, and replicates share one sample
    identifier, so every rebuilt injection got the same name. DataSequence
    keys by_name with a dict, so all but the last silently vanished from it
    while len() and iteration still reported them all: the loss showed up only
    when someone called get_injection.
    """
    import shutil
    sequence_dir = tmp_path / "Seq"
    sequence_dir.mkdir()
    for name in ("001-A1_01.D", "002-A2_02.D", "003-A3_03.D"):
        shutil.copytree(os.path.join(INPUTS, "red.D"), sequence_dir / name)
    original = rb.read_sequence(str(sequence_dir))
    assert len({inj.metadata.get("sample") for inj in original}) == 1

    back = rb.sequence_from_asm(original.to_asm())
    assert len(back) == len(original) == 3
    assert len(back.by_name) == 3
    assert len(set(inj.name for inj in back)) == 3
    for injection in back:
        assert back.get_injection(injection.name) is not None


def test_replicates_are_kept_apart_when_the_document_names_none_of_them(
        tmp_path):
    # The test above is satisfied by the injection identifier, which is already
    # distinct, so it never reaches the suffixing that keeps replicates apart.
    # Neither model requires an injection document on a liquid chromatography
    # measurement, and rainbow omits it for a run that recorded no injection
    # volume, so a document that names none of its injections is ordinary. Then
    # the sample identifier is all there is, and replicates share it.
    import shutil
    sequence_dir = tmp_path / "Seq"
    sequence_dir.mkdir()
    for name in ("001-A1_01.D", "002-A2_02.D", "003-A3_03.D"):
        shutil.copytree(os.path.join(INPUTS, "red.D"), sequence_dir / name)
    document = rb.read_sequence(str(sequence_dir)).to_asm()
    aggregate = document["liquid chromatography aggregate document"]
    for lc_document in aggregate["liquid chromatography document"]:
        for measurement in (lc_document["measurement aggregate document"]
                            ["measurement document"]):
            measurement.pop("injection document", None)

    back = rb.sequence_from_asm(document)
    assert len(back) == 3
    samples = {inj.metadata.get("sample") for inj in back}
    assert len(samples) == 1  # the collision the suffixing is for
    sample = samples.pop()
    assert [inj.name for inj in back] == [
        sample, f"{sample}_2", f"{sample}_3"]
    for injection in back:
        assert back.get_injection(injection.name) is injection


def test_from_asm_on_a_sequence_document_says_it_is_merging():
    # Every injection's channels land in one directory, where channels sharing
    # a name across injections collapse and get_file returns the last. The
    # docstring points at sequence_from_asm; the warning catches the caller who
    # did not read it.
    from rainbow.datasequence import DataSequence

    one, two = rb.read("tests/inputs/red.D"), rb.read("tests/inputs/red.D")
    document = DataSequence("Seq", [one, two], {}).to_asm()
    with pytest.warns(UserWarning, match="sequence_from_asm"):
        merged = rb.from_asm(document)
    # The warning is earned: two injections of the same run, one set of names.
    assert len(merged.by_name) < len(merged.datafiles)


def test_a_single_injection_document_does_not_warn():
    import warnings as w
    document = rb.read("tests/inputs/red.D").to_asm()
    with w.catch_warnings(record=True) as caught:
        w.simplefilter("always")
        rb.from_asm(document)
    assert not [x for x in caught if "sequence_from_asm" in str(x.message)]


# --- Peak lists a foreign exporter writes -----------------------------------
#
# An Agilent OpenLab / Empower ASM export differs from rainbow's own in three
# ways that all cost peak data: it names each peak's compound, it emits one
# processed data document per result version rather than one per channel, and
# it leaves the device control document without a wavelength setting, naming
# the wavelength in the cube label instead.


def _processed(*peak_lists):
    """A processed data aggregate document, one document per peak list."""
    return {"processed data aggregate document": {
        "processed data document": list(peak_lists)}}


def _peak_list(*peaks, **document):
    document["peak list"] = {"peak": list(peaks)}
    return document


def _rt(seconds):
    return {"retention time": {"value": seconds, "unit": "s"}}


def test_a_peaks_compound_name_is_read():
    """ Without the name a peak list is a set of anonymous retention times.

    The compound a processing method assigned to a peak is the field that makes
    a peak list usable across a study: it is what says which of forty peaks is
    the product. rainbow read every quantity and dropped it.
    """
    document = _lc(_with_cube(**{
        "measurement identifier": "uv",
        **_processed(_peak_list(dict(_rt(90.0),
                                     **{"written name": "Caffeine"}),
                                dict(_rt(120.0))))}))
    peaks = rb.from_asm(document).peaks[0]["peaks"]
    assert [peak["name"] for peak in peaks] == ["Caffeine", None]


def test_a_peaks_compound_name_survives_a_round_trip():
    datadir = rb.read(os.path.join(INPUTS, "red.D"))
    channel = next(d.name for d in datadir.datafiles
                   if d.detector == "UV" and d.data.shape[1] == 1)
    datadir.peaks = [{"signal": channel.split(".")[0].upper(),
                      "wavelength": 254.0, "description": None,
                      "channel_file": channel,
                      "peaks": [{"name": "Caffeine", "retention_time": 1.5,
                                 "area": 100.0}]}]
    document = datadir.to_asm()
    peak = (_measurements(document)[0]["processed data aggregate document"]
            ["processed data document"][0]["peak list"]["peak"][0])
    assert peak["written name"] == "Caffeine"
    assert rb.from_asm(document).peaks[0]["peaks"][0]["name"] == "Caffeine"


def _empower_peak(**fields):
    """A peak shaped the way an Empower export writes one."""
    return dict({"@index": 1,
                 "peak start": {"value": 90.0, "unit": "s"},
                 "peak end": {"value": 120.0, "unit": "s"},
                 "peak baseline start code": "B",
                 "peak baseline end code": "v",
                 "peak value at start": {"value": 0.0, "unit": "mAU"},
                 "peak value at end": {"value": 1.25, "unit": "mAU"},
                 "baseline value at start of peak": {"value": 84.0,
                                                     "unit": "s"},
                 "baseline value at end of peak": {"value": 150.0,
                                                   "unit": "s"}}, **fields)


_BASELINE_KEYS = ("baseline_start_code", "baseline_end_code", "start_height",
                  "end_height", "baseline_start_time", "baseline_end_time")


def test_a_peaks_baseline_is_read():
    """ Without its baseline a peak's area cannot be checked against its trace.

    An Empower export records how the integration drew the line under each
    peak: the type at each edge, how far the trace sits above the line there,
    and where the line under the peak's cluster begins and ends. rainbow read
    the area and dropped everything that says what it was measured from.
    """
    peak = asm._peak_from_asm(_empower_peak())
    assert peak["baseline_start_code"] == "B"
    assert peak["baseline_end_code"] == "v"
    assert peak["start_height"] == 0.0
    assert peak["end_height"] == 1.25
    assert peak["baseline_start_time"] == 1.4
    assert peak["baseline_end_time"] == 2.5


def test_a_peak_without_a_baseline_reads_none():
    peak = asm._peak_from_asm(_rt(90.0))
    assert all(peak[key] is None for key in _BASELINE_KEYS)
    assert peak["retention_time"] == 1.5


def test_a_peaks_heights_and_area_convert_to_mau_by_their_unit():
    """ A height in AU or in Empower's microvolts is the same height in mAU.

    The export labels heights mAU and areas mAU.s, and the edge heights are
    subtracted from a trace in mAU, so a value left in its own unit is a
    thousand times off. Any other unit is kept as written (see below).
    """
    peak = asm._peak_from_asm(_empower_peak(**{
        "peak height": {"value": 0.03, "unit": "AU"},
        "peak area": {"value": 0.5, "unit": "AU.s"},
        "peak value at start": {"value": 0.002, "unit": "AU"},
        "peak value at end": {"value": 1250.0, "unit": "\u00b5V"}}))
    assert peak["height"] == 30.0
    assert peak["area"] == 500.0
    assert peak["start_height"] == 2.0
    assert peak["end_height"] == 1.25

    assert peak["height_unit"] == "mAU"
    assert peak["area_unit"] == "mAU.s"


def test_a_peak_in_another_unit_keeps_its_value_and_unit_as_written():
    """ A fluorescence peak is in RFU, an FID peak in pA: neither is mAU.

    Converting only absorbance and reading every other unit as None lost every
    peak of an Empower study's fluorescence channels, three in four of its
    peaks. Only a value the document gave no unit has none.
    """
    peak = asm._peak_from_asm(_empower_peak(**{
        "peak height": {"value": 3.0, "unit": "RFU"},
        "peak area": {"value": 5.0, "unit": "RFU.s"},
        "peak value at start": {"value": 1.0, "unit": "RFU"},
        "peak value at end": 1.25}))
    assert (peak["height"], peak["height_unit"]) == (3.0, "RFU")
    assert (peak["area"], peak["area_unit"]) == (5.0, "RFU.s")
    assert peak["start_height"] == 1.0
    assert peak["end_height"] == 1.25

    # An absorbance area in a height's unit has no time to convert from.
    peak = asm._peak_from_asm(_empower_peak(**{
        "peak area": {"value": 5.0, "unit": "mAU"}, "peak height": 2.0}))
    assert (peak["area"], peak["area_unit"]) == (None, None)
    assert (peak["height"], peak["height_unit"]) == (2.0, None)

    # An edge height in a unit other than the height's has no unit to be
    # reported in.
    peak = asm._peak_from_asm(_empower_peak(**{
        "peak height": {"value": 3.0, "unit": "RFU"},
        "peak value at start": {"value": 1.0, "unit": "pA"}}))
    assert peak["start_height"] is None


def test_a_microvolt_document_reads_and_exports_in_mau():
    """ An Empower peak list in microvolts reads, and exports, in mAU. """
    document = _lc(_with_cube(**{
        "measurement identifier": "uv",
        **_processed(_peak_list(_empower_peak(**_rt(105.0), **{
            "peak height": {"value": 32572.0, "unit": "\u00b5V"},
            "peak area": {"value": 101951.0, "unit": "\u00b5V.s"},
            "peak value at start": {"value": 0.0, "unit": "\u00b5V"},
            "peak value at end": {"value": 52.5, "unit": "\u00b5V"}})))}))
    datadir = rb.from_asm(document)
    peak = datadir.peaks[0]["peaks"][0]
    assert peak["height"] == pytest.approx(32.572)
    assert peak["area"] == pytest.approx(101.951)
    assert peak["start_height"] == 0.0
    assert peak["end_height"] == pytest.approx(0.0525)

    exported = asm._asm_peak(1, peak)
    assert exported["peak height"] == {"value": peak["height"], "unit": "mAU"}
    assert exported["peak area"] == {"value": peak["area"], "unit": "mAU.s"}
    assert exported["peak value at end"] == {"value": peak["end_height"],
                                             "unit": "mAU"}
    assert asm._peak_from_asm(exported) == peak


def test_a_baseline_time_needs_a_time_unit():
    """ The field's name reads as a signal value; only the unit says time.

    Empower fills it with the time the cluster's baseline starts and ends, in
    seconds. A time in seconds or minutes comes back in minutes, and anything
    else reads as None rather than as a time it may not be.
    """
    peak = asm._peak_from_asm(_empower_peak(**{
        "baseline value at start of peak": {"value": 1.4, "unit": "min"},
        "baseline value at end of peak": {"value": 0.3, "unit": "mAU"}}))
    assert peak["baseline_start_time"] == 1.4
    assert peak["baseline_end_time"] is None

    peak = asm._peak_from_asm(_empower_peak(**{
        "baseline value at start of peak": 84.0,
        "baseline value at end of peak": {"value": 150.0}}))
    assert peak["baseline_start_time"] is None
    assert peak["baseline_end_time"] is None


def test_a_baseline_field_of_the_wrong_type_drops_to_none():
    peak = asm._peak_from_asm(_empower_peak(**{
        "peak baseline start code": 3,
        "peak baseline end code": "  ",
        "peak value at end": {"value": "1.25", "unit": "mAU"},
        "baseline value at start of peak": {"value": "84", "unit": "s"}}))
    assert peak["baseline_start_code"] is None
    assert peak["baseline_end_code"] is None
    assert peak["end_height"] is None
    assert peak["baseline_start_time"] is None
    # The fields beside them still come through.
    assert peak["start_height"] == 0.0
    assert peak["baseline_end_time"] == 2.5


def test_the_baseline_codes_and_times_are_written_as_custom_information():
    """ An export must validate, and the schema defines neither field.

    The schema does define custom information on a peak, so the codes and
    times go there, under the labels Empower uses, and come back from there.
    """
    entry = asm._asm_peak(1, asm._peak_from_asm(_empower_peak()))
    for label in ("peak baseline start code", "peak baseline end code",
                  "baseline value at start of peak",
                  "baseline value at end of peak"):
        assert label not in entry
    custom = (entry["custom information aggregate document"]
              ["custom information document"])
    assert custom == [
        {"@index": 1, "datum label": "peak baseline start code",
         "scalar string datum": "B"},
        {"@index": 2, "datum label": "peak baseline end code",
         "scalar string datum": "v"},
        {"@index": 3, "datum label": "baseline value at start of peak",
         "scalar double datum": 84.0, "unit": "s"},
        {"@index": 4, "datum label": "baseline value at end of peak",
         "scalar double datum": 150.0, "unit": "s"}]
    assert entry["peak value at end"] == {"value": 1.25, "unit": "mAU"}
    peak = asm._peak_from_asm(entry)
    assert peak["baseline_start_code"] == "B"
    assert peak["baseline_end_time"] == 2.5


def test_a_peaks_baseline_survives_a_round_trip():
    datadir = rb.read(os.path.join(INPUTS, "red.D"))
    channel = next(d.name for d in datadir.datafiles
                   if d.detector == "UV" and d.data.shape[1] == 1)
    first = asm._peak_from_asm(_empower_peak(**_rt(105.0), **{
        "peak area": {"value": 50.0, "unit": "mAU.s"},
        "peak value at end": {"value": 1250.0, "unit": "\u00b5V"}}))
    datadir.peaks = [{"signal": channel.split(".")[0].upper(),
                      "wavelength": 254.0, "description": None,
                      "channel_file": channel, "peaks": [first]}]
    document = datadir.to_asm()
    peak = (_measurements(document)[0]["processed data aggregate document"]
            ["processed data document"][0]["peak list"]["peak"][0])
    # Written in mAU, the unit it was converted to on the way in.
    assert peak["peak value at end"] == {"value": 1.25, "unit": "mAU"}
    assert rb.from_asm(document).peaks[0]["peaks"][0] == first


def test_the_edge_heights_of_a_real_empower_export_reproduce_its_areas():
    """ The heights mean what the area was measured from.

    Three touching peaks from an Empower export, a valley-split cluster, with
    the trace under them. Names and identifiers are removed and times shifted
    to start at zero. A line from (start, trace - start height) to (end, trace
    - end height) has to reproduce each peak's area as the file reports it.
    """
    with open(os.path.join(INPUTS, "empower_peaks.asm.json")) as f:
        datadir = rb.from_asm(json.load(f))
    seconds = datadir.datafiles[0].xlabels * 60.0
    trace = datadir.datafiles[0].data[:, 0]
    peaks = datadir.peaks[0]["peaks"]
    assert [peak["baseline_start_code"] + peak["baseline_end_code"]
            for peak in peaks] == ["BV", "VV", "VB"]
    for peak in peaks:
        start, end = peak["start_time"] * 60.0, peak["end_time"] * 60.0
        inside = (seconds > start) & (seconds < end)
        t = np.concatenate([[start], seconds[inside], [end]])
        y = np.interp(t, seconds, trace)
        above = y - np.interp(t, [start, end],
                              [y[0] - peak["start_height"],
                               y[-1] - peak["end_height"]])
        area = np.sum((above[1:] + above[:-1]) / 2 * np.diff(t))
        assert area == pytest.approx(peak["area"], rel=0.01)
        # The cluster's baseline spans the peak.
        assert peak["baseline_start_time"] <= peak["start_time"]
        assert peak["baseline_end_time"] >= peak["end_time"]


def _measurements(document):
    """Every measurement carrying a peak list, in document order."""
    return [m for m in document["liquid chromatography aggregate document"]
            ["liquid chromatography document"][0]
            ["measurement aggregate document"]["measurement document"]
            if "processed data aggregate document" in m]


def test_only_the_first_of_several_integrations_is_the_default():
    """ A channel integrated more than once must not lose the extra results.

    An Empower export writes one processed data document per result version, so
    a single channel arrives with the same run integrated up to six times, at
    different times and under different processing methods. rainbow read the
    first and dropped the rest without a word, and the peak lists genuinely
    differ: a reintegration finds or loses whole peaks.
    """
    document = _lc(_with_cube(**{
        "measurement identifier": "uv",
        **_processed(
            _peak_list(dict(_rt(90.0), **{"written name": "first"}),
                       **{"processed data identifier": "1",
                          "data processing time": "2025-09-12T14:20:31-04:00"}),
            _peak_list(dict(_rt(90.0), **{"written name": "second"}),
                       dict(_rt(150.0)),
                       **{"processed data identifier": "2",
                          "data processing time": "2025-10-01T11:17:02-04:00"}))}))
    with pytest.warns(UserWarning, match="2 processed data documents"):
        group = rb.from_asm(document).peaks[0]

    assert [peak["name"] for peak in group["peaks"]] == ["first"]
    assert group["processing"]["identifier"] == "1"
    # The one that was silently thrown away, kept and labelled with the
    # integration that produced it.
    assert len(group["alternates"]) == 1
    alternate = group["alternates"][0]
    assert [peak["name"] for peak in alternate["peaks"]] == ["second", None]
    assert alternate["processing"]["time"] == "2025-10-01T11:17:02-04:00"


def test_a_single_integration_carries_no_alternates_and_no_warning():
    document = _lc(_with_cube(**{
        "measurement identifier": "uv",
        **_processed(_peak_list(_rt(90.0)))}))
    import warnings as w
    with w.catch_warnings(record=True) as caught:
        w.simplefilter("always")
        group = rb.from_asm(document).peaks[0]
    assert group["alternates"] == []
    assert not [x for x in caught if "processed data documents" in str(x.message)]


def test_the_extra_integrations_survive_a_re_export():
    """ Reading every result version is no use if exporting keeps only one. """
    document = _lc(_with_cube(**{
        "measurement identifier": "uv",
        **_processed(
            _peak_list(_rt(90.0), **{"processed data identifier": "1"}),
            _peak_list(_rt(150.0), **{"processed data identifier": "2"}),
            _peak_list(_rt(210.0), **{"processed data identifier": "3"}))}))
    with pytest.warns(UserWarning, match="3 processed data documents"):
        datadir = rb.from_asm(document)
    with pytest.warns(UserWarning, match="3 processed data documents"):
        again = rb.from_asm(datadir.to_asm())

    written = (_measurements(datadir.to_asm())[0]
               ["processed data aggregate document"]["processed data document"])
    assert [d["processed data identifier"] for d in written] == ["1", "2", "3"]
    assert [d["@index"] for d in written] == [1, 2, 3]
    assert len(again.peaks[0]["alternates"]) == 2


# The wavelength is the only thing telling one channel of a multi-signal run
# from another, and a label names up to three of them: the signal, its
# bandwidth, and a reference channel.
@pytest.mark.parametrize("label,expected", [
    ("DAD.0.0, DAD: Signal A, 246.0 nm/Bw:4.0 nm", 246.0),
    ("DAD.0.1, DAD: Signal B, 220.0 nm/Bw:4.0 nm Ref 360.0 nm/Bw:100.0 nm",
     220.0),
    ("DAD1A, Sig=254,4 Ref=off", 254.0),
    ("no wavelength here", None),
])
def test_the_cube_label_supplies_a_missing_wavelength(label, expected):
    """ A channel whose exporter records no wavelength setting still has one.

    Reading only the device control document's setting left every channel of an
    OpenLab export with an empty y-axis label, so a three-signal injection came
    back as three indistinguishable traces.
    """
    measurement = _with_cube(**{"measurement identifier": "uv",
                                **_processed(_peak_list(_rt(90.0)))})
    measurement["chromatogram data cube"]["label"] = label
    datadir = rb.from_asm(_lc(measurement))
    datafile = datadir.datafiles[0]
    if expected is None:
        assert datafile.ylabels.tolist() == [""]
        assert datadir.peaks[0]["wavelength"] is None
    else:
        assert datafile.ylabels.tolist() == [expected]
        assert datafile.metadata["wavelength"] == expected
        assert datadir.peaks[0]["wavelength"] == expected
    # Either way the label itself is kept, so the channel can be identified.
    assert datafile.metadata["description"] == label
    assert datadir.peaks[0]["description"] == label


def test_a_declared_wavelength_setting_still_wins_over_the_label():
    """ The label is a fallback, not a second source of truth. """
    measurement = _with_cube(**{
        "measurement identifier": "uv",
        "device control aggregate document": {"device control document": [
            {"detector wavelength setting": {"value": 254.0, "unit": "nm"}}]},
        **_processed(_peak_list(_rt(90.0)))})
    measurement["chromatogram data cube"]["label"] = "DAD: Signal A, 246.0 nm"
    datadir = rb.from_asm(_lc(measurement))
    assert datadir.datafiles[0].ylabels.tolist() == [254.0]
    assert datadir.peaks[0]["wavelength"] == 254.0


def _sample(**fields):
    """A measurement whose sample document carries ``fields``."""
    return _with_cube(**{"measurement identifier": "uv",
                         "sample document": dict(fields)})


def _custom(*entries):
    """A custom information aggregate document from raw ``entries``."""
    return {"custom information aggregate document": {
        "custom information document": list(entries)}}


def _datum(label, key, value, index=None, **extra):
    entry = {"datum label": label, key: value, **extra}
    if index is not None:
        entry["@index"] = index
    return entry


def _read_custom(*entries):
    return rb.from_asm(_lc(_sample(**{"sample identifier": "s",
                                      **_custom(*entries)})))


def test_a_samples_written_name_is_read_beside_its_identifier():
    """ The identifier keys the sample; the written name is what a human reads.

    rainbow's own writer puts both in the identifier, so reading only that round
    tripped its output. An Empower export names the injection in `written name`
    and keys it in `sample identifier`, and the name was dropped.
    """
    datadir = rb.from_asm(_lc(_sample(**{
        "sample identifier": "133872", "written name": "NB5-P1A11"})))
    assert datadir.metadata["sample"] == "133872"
    assert datadir.metadata["sample_name"] == "NB5-P1A11"


def test_a_sample_with_no_custom_fields_carries_no_key():
    """ Absent is absent: a caller checks the key, not for an empty dict. """
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    assert "sample_custom" not in datadir.metadata
    assert "sample_name" not in datadir.metadata


# --- the four datum types the schema admits ---

@pytest.mark.parametrize("key, written, expected", [
    ("scalar string datum", "Vax-033898", "Vax-033898"),
    ("scalar double datum", 1.5, 1.5),
    ("scalar boolean datum", True, True),
    ("scalar boolean datum", False, False),
])
def test_each_scalar_datum_type_reads_as_its_python_type(key, written,
                                                        expected):
    fields = _read_custom(_datum("f", key, written)).metadata["sample_custom"]
    assert fields == {"f": expected}
    assert type(fields["f"]) is type(expected)


def test_a_timestamp_datum_reads_as_a_datetime_not_a_string():
    """ The datum type is what tells a timestamp from the string it is spelled
    as; losing it means a round trip cannot put it back as a timestamp. """
    import datetime

    fields = _read_custom(
        _datum("When", "scalar timestamp datum",
               "2026-04-28T13:19:56-04:00")).metadata["sample_custom"]
    assert fields["When"] == datetime.datetime(
        2026, 4, 28, 13, 19, 56,
        tzinfo=datetime.timezone(datetime.timedelta(hours=-4)))


def test_an_integer_stays_an_integer_through_a_round_trip():
    """ 3 is not 3.0: the same reason a wavelength of 254 stays 254. """
    datadir = _read_custom(_datum("n", "scalar double datum", 3))
    assert datadir.metadata["sample_custom"] == {"n": 3}
    entry = _custom_entries(datadir.to_asm())[0]
    assert entry["scalar double datum"] == 3
    assert isinstance(entry["scalar double datum"], int)


def test_a_doubles_unit_is_kept_beside_its_value():
    """ The schema lets a double carry a unit, and dropping it changes the
    number's meaning. Read as the {value, unit} shape injection_volume uses. """
    datadir = _read_custom(
        _datum("Weight", "scalar double datum", 1.5, unit="mg"))
    assert datadir.metadata["sample_custom"] == {
        "Weight": {"value": 1.5, "unit": "mg"}}
    entry = _custom_entries(datadir.to_asm())[0]
    assert entry["scalar double datum"] == 1.5 and entry["unit"] == "mg"


def _custom_entries(document):
    """The custom information documents of a built document's first sample."""
    return (document["liquid chromatography aggregate document"]
            ["liquid chromatography document"][0]
            ["measurement aggregate document"]["measurement document"][0]
            ["sample document"]["custom information aggregate document"]
            ["custom information document"])


# --- values rainbow will not guess at ---

def test_a_value_datum_written_as_an_object_is_unwrapped():
    """ tDoubleValue and tStringValue both admit {"@type", "value"}. Reading the
    object itself handed user code a dict where a scalar was promised, and then
    refused to write back a value it had been given correctly. """
    datadir = _read_custom(
        _datum("Weight", "scalar double datum",
               {"@type": "x#Number", "value": 1.5}),
        _datum("Id", "scalar string datum",
               {"@type": "x#String", "value": "Vax-1"}))
    assert datadir.metadata["sample_custom"] == {"Weight": 1.5, "Id": "Vax-1"}


def test_an_integer_too_large_for_a_float_is_dropped_on_read():
    """ JSON integers are unbounded and Python floats are not. Keeping it read
    fine and then raised OverflowError out of the middle of the re-export. """
    entry = json.loads('{"datum label": "Big", "scalar double datum": 1'
                       + "0" * 400 + "}")
    with pytest.warns(UserWarning, match="Big.*cannot read"):
        datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s",
                                             **_custom(entry)})))
    assert "sample_custom" not in datadir.metadata


def test_a_datum_type_rainbow_does_not_read_warns_rather_than_guesses():
    document = _lc(_sample(**{"sample identifier": "s", **_custom(
        _datum("Odd", "scalar float datum", 3))}))
    with pytest.warns(UserWarning, match="Odd.*does not read"):
        datadir = rb.from_asm(document)
    assert "sample_custom" not in datadir.metadata


def test_an_entry_declaring_two_datum_types_is_dropped_not_picked_from():
    """ The schema makes the datum types a oneOf, so two is malformed. Choosing
    between two conflicting values would publish rainbow's own preference. """
    with pytest.warns(UserWarning, match="declares 2 datum types"):
        datadir = _read_custom({"datum label": "x",
                                "scalar string datum": "s",
                                "scalar double datum": 2.0})
    assert "sample_custom" not in datadir.metadata


def test_a_duplicate_label_keeps_the_first_and_says_so():
    """ Legal in the document, impossible in a mapping. """
    with pytest.warns(UserWarning, match="more than once"):
        datadir = _read_custom(_datum("x", "scalar string datum", "one"),
                               _datum("x", "scalar string datum", "two"))
    assert datadir.metadata["sample_custom"] == {"x": "one"}


def test_a_non_finite_custom_value_is_dropped_before_json_sees_it():
    """ json.dumps writes NaN as a bare literal no conforming reader accepts,
    so to_asm looked fine and to_asm_str raised. """
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_custom"] = {"ok": 1.0, "bad": float("nan")}
    with pytest.warns(UserWarning, match="bad.*JSON can carry"):
        document = datadir.to_asm()
    assert [e["datum label"] for e in _custom_entries(document)] == ["ok"]
    with pytest.warns(UserWarning, match="bad"):
        # to_asm_str passes allow_nan=False, so a NaN that reached it would
        # raise rather than emit a literal no conforming reader accepts.
        assert "nan" not in asm.to_asm_str(datadir).lower()


def test_an_unusable_label_is_dropped_with_a_warning():
    """ Every other drop in this reader is announced; this one was silent. """
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_custom"] = {"": "x", "ok": "y"}
    with pytest.warns(UserWarning, match="not a usable datum label"):
        document = datadir.to_asm()
    assert [e["datum label"] for e in _custom_entries(document)] == ["ok"]


def test_a_custom_value_rainbow_cannot_write_is_dropped_not_coerced():
    """ str() on a list would publish it as text and change what it is. """
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_custom"] = {"Kept": "yes", "Odd": [1, 2]}
    with pytest.warns(UserWarning, match="Odd.*cannot write"):
        document = datadir.to_asm()
    assert [e["datum label"] for e in _custom_entries(document)] == ["Kept"]


# --- ordering ---

def test_custom_fields_out_of_index_order_are_sorted_by_index():
    """ @index orders the fields, not their position in the list. """
    datadir = _read_custom(_datum("second", "scalar string datum", "b", index=2),
                           _datum("first", "scalar string datum", "a", index=1))
    assert list(datadir.metadata["sample_custom"]) == ["first", "second"]


def test_a_partly_indexed_document_keeps_its_own_order():
    """ @index is 1-based and sparse; position is 0-based and dense. Sorting a
    mix of the two put the unindexed entry first: 5, 6, (none) came back as
    (none), 5, 6. The schema does not require @index, so rather than mix the
    two namespaces, a document that does not order every entry keeps its own.
    """
    datadir = _read_custom(_datum("a", "scalar string datum", "A", index=5),
                           _datum("b", "scalar string datum", "B", index=6),
                           _datum("c", "scalar string datum", "C"))
    assert list(datadir.metadata["sample_custom"]) == ["a", "b", "c"]


def test_index_is_renumbered_from_one_on_export():
    datadir = _read_custom(_datum("a", "scalar string datum", "A", index=7),
                           _datum("b", "scalar string datum", "B", index=9))
    assert [e["@index"] for e in _custom_entries(datadir.to_asm())] == [1, 2]


# --- the sample document is read as a unit ---

def test_an_identified_sample_document_is_read_without_an_earlier_name():
    """ from_asm merges every injection into one directory. Taking the three
    sample fields one at a time let an identifier from the first injection sit
    beside a name and a MaterialIdentifier from the second -- a join key
    silently attached to the wrong sample, which is worse than none.
    """
    first = _with_cube(**{"measurement identifier": "uv1",
                          "sample document": {"sample identifier": "AAA"}})
    second = _with_cube(**{"measurement identifier": "uv2",
                           "sample document": {
                               "sample identifier": "BBB",
                               "written name": "B-name",
                               **_custom(_datum("MaterialIdentifier",
                                                "scalar string datum",
                                                "Vax-B"))}})
    metadata = rb.from_asm(_lc(first, second)).metadata
    assert metadata["sample"] == "AAA"
    assert "sample_name" not in metadata
    assert "sample_custom" not in metadata


def test_a_later_channel_supplies_the_sample_when_the_first_has_none():
    """ First readable wins, not first measurement. """
    bare = _with_cube(**{"measurement identifier": "uv1",
                         "sample document": {"sample identifier": "unknown"}})
    named = _with_cube(**{"measurement identifier": "uv2",
                          "sample document": {
                              "sample identifier": "BBB",
                              "written name": "B-name"}})
    metadata = rb.from_asm(_lc(bare, named)).metadata
    assert metadata["sample"] == "BBB"
    assert metadata["sample_name"] == "B-name"


def test_each_injection_in_a_sequence_keeps_its_own_sample():
    """ sequence_from_asm builds a directory per injection, so the fields must
    not travel between them. """
    def injection(identifier, name, material):
        return {"measurement aggregate document": {"measurement document": [
            _with_cube(**{"measurement identifier": "uv-" + identifier,
                          "sample document": {
                              "sample identifier": identifier,
                              "written name": name,
                              **_custom(_datum("MaterialIdentifier",
                                               "scalar string datum",
                                               material))}})]}}

    document = {"liquid chromatography aggregate document": {
        "liquid chromatography document": [injection("1", "one", "Vax-1"),
                                           injection("2", "two", "Vax-2")]}}
    sequence = rb.sequence_from_asm(document)
    got = [(inj.metadata["sample_name"],
            inj.metadata["sample_custom"]["MaterialIdentifier"])
           for inj in sequence.injections]
    assert got == [("one", "Vax-1"), ("two", "Vax-2")]


# --- the whole lap ---

def test_the_sample_name_and_custom_fields_survive_a_round_trip():
    """ The lap an Empower document actually makes: read, then re-export. """
    source = _lc(_sample(**{
        "sample identifier": "133872", "written name": "NB5-P1A11",
        **_custom(_datum("Notebook", "scalar string datum", "NB-23737-0005",
                         index=1),
                  _datum("MaterialIdentifier", "scalar string datum",
                         "Vax-033898", index=2),
                  _datum("SampleWeight", "scalar double datum", 1.0,
                         index=3))}))
    document = rb.from_asm(source).to_asm()
    sample = (document["liquid chromatography aggregate document"]
              ["liquid chromatography document"][0]
              ["measurement aggregate document"]["measurement document"][0]
              ["sample document"])
    assert sample["written name"] == "NB5-P1A11"
    assert sample["custom information aggregate document"] == (
        source["liquid chromatography aggregate document"]
        ["liquid chromatography document"][0]
        ["measurement aggregate document"]["measurement document"][0]
        ["sample document"]["custom information aggregate document"])
    # And a second lap reads back what the first wrote.
    assert rb.from_asm(document).metadata["sample_custom"] == {
        "Notebook": "NB-23737-0005", "MaterialIdentifier": "Vax-033898",
        "SampleWeight": 1.0}


@pytest.mark.parametrize("key, value", [
    ("scalar string datum", "s"),
    ("scalar double datum", 2.5),
    ("scalar boolean datum", False),
    ("scalar timestamp datum", "2026-04-28T13:19:56+00:00"),
])
def test_every_datum_type_returns_the_entry_it_came_from(key, value):
    """ Read then write reproduces the entry, for each of the four types. """
    source = _datum("f", key, value, index=1)
    document = _read_custom(source).to_asm()
    assert _custom_entries(document) == [source]


def test_a_naive_timestamp_takes_the_callers_offset_like_any_other():
    """ The schema's date-time is RFC 3339 and requires an offset. Writing a
    naive datetime's isoformat() direct emitted a value the document then failed
    to validate on; it goes through the same gate as `measurement time`. """
    import datetime

    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_custom"] = {
        "When": datetime.datetime(2026, 4, 28, 13, 19, 56)}
    stamped = _custom_entries(datadir.to_asm(utc_offset="+00:00"))[0]
    assert stamped["scalar timestamp datum"] == "2026-04-28T13:19:56+00:00"


def test_a_naive_timestamp_with_no_offset_warns_rather_than_inventing_one():
    import datetime

    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_custom"] = {
        "When": datetime.datetime(2026, 4, 28, 13, 19, 56)}
    with pytest.warns(UserWarning, match="records no UTC offset"):
        stamped = _custom_entries(datadir.to_asm())[0]
    assert stamped["scalar timestamp datum"] == "2026-04-28T13:19:56"


def test_a_plain_date_is_dropped_because_it_is_not_a_date_time():
    """ `date.isoformat()` is a date, and midnight in an invented zone is the
    guess this reader refuses everywhere else. """
    import datetime

    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_custom"] = {"On": datetime.date(2026, 4, 28)}
    with pytest.warns(UserWarning, match="holds date"):
        document = datadir.to_asm()
    sample = (document["liquid chromatography aggregate document"]
              ["liquid chromatography document"][0]
              ["measurement aggregate document"]["measurement document"][0]
              ["sample document"])
    assert "custom information aggregate document" not in sample


def _two_channel_document():
    """A document with two measurements, so a per-measurement warning repeats."""
    return _lc(
        _with_cube(**{"measurement identifier": "uv1",
                      "sample document": {"sample identifier": "s"}}),
        _with_cube(**{"measurement identifier": "uv2",
                      "sample document": {"sample identifier": "s"}}))


def test_an_integer_too_large_for_a_float_is_dropped_on_write():
    """The read path drops it, so only a caller can put one in -- and
    math.isfinite raises OverflowError on it before the finite check can
    report anything, out of the middle of the export."""
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_custom"] = {"ok": 1.0, "Big": 10 ** 400}
    with pytest.warns(UserWarning, match="Big.*too large"):
        document = datadir.to_asm()       # not OverflowError
    assert [e["datum label"] for e in _custom_entries(document)] == ["ok"]


def test_a_non_bool_under_a_boolean_datum_is_dropped_not_coerced():
    """bool("false") is True, which is the opposite of what was recorded."""
    with pytest.warns(UserWarning, match="Flag.*cannot read"):
        datadir = _read_custom(_datum("Flag", "scalar boolean datum", "false"))
    assert "sample_custom" not in datadir.metadata


def test_an_unindexed_entry_first_still_keeps_document_order():
    """Distinguishes "document order" from "unindexed sorted last": with the
    unindexed entry first, the two disagree."""
    datadir = _read_custom(_datum("c", "scalar string datum", "C"),
                           _datum("a", "scalar string datum", "A", index=5))
    assert list(datadir.metadata["sample_custom"]) == ["c", "a"]


def test_an_index_that_is_not_a_number_does_not_break_the_sort():
    """A string @index beside a real one made sorted() raise TypeError
    comparing int to str."""
    datadir = _read_custom(_datum("a", "scalar string datum", "A", index="2"),
                           _datum("b", "scalar string datum", "B", index=1))
    assert list(datadir.metadata["sample_custom"]) == ["a", "b"]


def test_a_unit_beside_a_non_double_is_reported_on_read():
    """No subschema forbids it, so a conforming document may carry one; only a
    double has anywhere to keep it."""
    with pytest.warns(UserWarning, match="only a double may do"):
        datadir = _read_custom(
            _datum("a", "scalar string datum", "x", unit="mg"))
    assert datadir.metadata["sample_custom"] == {"a": "x"}


def test_a_unit_beside_a_non_double_is_reported_on_write():
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_custom"] = {"a": {"value": "x", "unit": "mg"}}
    with pytest.warns(UserWarning, match="only a double may do"):
        entry = _custom_entries(datadir.to_asm())[0]
    assert entry["scalar string datum"] == "x" and "unit" not in entry


def test_an_entry_with_no_usable_datum_label_is_reported_on_read():
    """`datum label` is required, and a mapping has nowhere to put an
    unlabelled value. The write side already said so for its mirror case."""
    with pytest.warns(UserWarning, match="as its datum label"):
        datadir = _read_custom({"scalar string datum": "x"})
    assert "sample_custom" not in datadir.metadata


def test_a_mapping_with_no_value_member_says_it_was_a_mapping():
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_custom"] = {"L": {"units": "mg"}, "ok": "y"}
    with pytest.warns(UserWarning, match="no usable 'value' member"):
        document = datadir.to_asm()
    assert [e["datum label"] for e in _custom_entries(document)] == ["ok"]


def test_sample_custom_that_is_not_a_mapping_is_reported():
    """Every other unusable input here warns; this one returned quietly."""
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_custom"] = [("a", 1)]
    with pytest.warns(UserWarning, match="not a mapping"):
        document = datadir.to_asm()
    sample = (document["liquid chromatography aggregate document"]
              ["liquid chromatography document"][0]
              ["measurement aggregate document"]["measurement document"][0]
              ["sample document"])
    assert "custom information aggregate document" not in sample


def test_a_write_side_warning_is_said_once_per_document_not_per_channel():
    """One sample_custom mapping is written into every measurement, so warning
    as each was built said the same thing once per channel."""
    datadir = rb.from_asm(_two_channel_document())
    assert len(datadir.datafiles) == 2
    import warnings as w

    datadir.metadata["sample_custom"] = {"bad": [1, 2]}
    with w.catch_warnings(record=True) as caught:
        w.simplefilter("always")
        datadir.to_asm()
    assert len([w for w in caught if "custom field" in str(w.message)]) == 1


def test_the_sample_is_taken_from_the_first_measurement_that_identifies_one():
    """Not merely the first that carries anything: a run whose opening channel
    records a name against an "unknown" identifier otherwise lost the
    identifier a later channel had."""
    named = _with_cube(**{"measurement identifier": "uv1",
                          "sample document": {"sample identifier": "unknown",
                                              "written name": "X"}})
    identified = _with_cube(**{"measurement identifier": "uv2",
                               "sample document": {
                                   "sample identifier": "133872"}})
    metadata = rb.from_asm(_lc(named, identified)).metadata
    assert metadata["sample"] == "133872"
    # And still as a unit: the other document's name does not come along.
    assert "sample_name" not in metadata


def test_sample_fields_are_not_composed_across_channels():
    """The claim the one-pass read exists for, with no identifier anywhere to
    short-circuit it: reading the three fields as each measurement went past put
    one channel's name beside another's MaterialIdentifier -- a join key
    silently attached to the wrong sample, which is worse than none."""
    named = _with_cube(**{"measurement identifier": "uv1",
                          "sample document": {"written name": "X"}})
    with_custom = _with_cube(**{"measurement identifier": "uv2",
                                "sample document": _custom(
                                    _datum("MaterialIdentifier",
                                           "scalar string datum", "Vax-B"))})
    metadata = rb.from_asm(_lc(named, with_custom)).metadata
    assert metadata["sample_name"] == "X"
    assert "sample_custom" not in metadata
    assert "sample" not in metadata


def test_an_unidentified_document_still_supplies_the_sample_fields():
    """The fallback: no measurement names an identifier, so the first that says
    anything at all is read rather than nothing being read."""
    metadata = rb.from_asm(_lc(
        _with_cube(**{"measurement identifier": "uv1",
                      "sample document": {"sample identifier": "unknown"}}),
        _with_cube(**{"measurement identifier": "uv2",
                      "sample document": {"written name": "X"}}))).metadata
    assert metadata["sample_name"] == "X"


@pytest.mark.parametrize("key, written, expected", [
    ("scalar string datum", {"@type": "x#String", "value": "s"}, "s"),
    ("scalar double datum", {"@type": "x#Number", "value": 1.5}, 1.5),
    ("scalar boolean datum", {"@type": "x#Boolean", "value": True}, True),
])
def test_the_object_form_is_unwrapped_for_every_datum_type(key, written,
                                                           expected):
    """tStringValue and tDoubleValue both admit {"@type", "value"}, and the
    object form is a property of the value, not of one datum type."""
    fields = _read_custom(_datum("f", key, written)).metadata["sample_custom"]
    assert fields == {"f": expected}
    assert type(fields["f"]) is type(expected)


def test_the_object_form_is_unwrapped_for_a_timestamp():
    import datetime

    fields = _read_custom(_datum(
        "When", "scalar timestamp datum",
        {"@type": "x#DateTime",
         "value": "2026-04-28T13:19:56+00:00"})).metadata["sample_custom"]
    assert fields["When"] == datetime.datetime(
        2026, 4, 28, 13, 19, 56, tzinfo=datetime.timezone.utc)


def test_a_boolean_is_written_as_a_boolean_not_as_a_number():
    """False == 0 in Python, so comparing the emitted entry by equality cannot
    tell a boolean datum from a double. Only the schema or the type can."""
    entry = _custom_entries(
        _read_custom(_datum("f", "scalar boolean datum", False)).to_asm())[0]
    assert entry["scalar boolean datum"] is False


def test_two_unwritable_fields_are_both_reported():
    """The once-per-document key carries the label and the complaint, so a
    second bad field is not swallowed by the first one's dedupe."""
    import warnings as w

    datadir = rb.from_asm(_two_channel_document())
    datadir.metadata["sample_custom"] = {"one": [1], "two": object()}
    with w.catch_warnings(record=True) as caught:
        w.simplefilter("always")
        datadir.to_asm()
    said = [str(c.message) for c in caught if "custom field" in str(c.message)]
    assert len(said) == 2
    assert {"'one'" in m for m in said} == {"'two'" in m for m in said} == {
        True, False}


def test_a_sample_name_that_is_not_a_string_is_not_written():
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_name"] = None
    sample = (datadir.to_asm()["liquid chromatography aggregate document"]
              ["liquid chromatography document"][0]
              ["measurement aggregate document"]["measurement document"][0]
              ["sample document"])
    assert "written name" not in sample


def test_a_clean_document_round_trips_without_complaint():
    """Nothing above pins SILENCE on the ordinary path, so a reader that warned
    about every well-formed field passed the whole suite. One concrete case: a
    double's unit is consumed where it is used, and failing to consume it made
    every legitimate unit emit the 'only a double may do' complaint.
    """
    import datetime
    import warnings as w

    source = _lc(_sample(**{
        "sample identifier": "133872", "written name": "NB5-P1A11",
        **_custom(_datum("Id", "scalar string datum", "Vax-033898", index=1),
                  _datum("Weight", "scalar double datum", 1.5, index=2,
                         unit="mg"),
                  _datum("Count", "scalar double datum", 3, index=3),
                  _datum("Passed", "scalar boolean datum", True, index=4),
                  _datum("When", "scalar timestamp datum",
                         "2026-04-28T13:19:56+00:00", index=5))}))
    with w.catch_warnings(record=True) as caught:
        w.simplefilter("always")
        datadir = rb.from_asm(source)
        datadir.to_asm()
    assert [str(c.message) for c in caught
            if "custom field" in str(c.message)
            or "datum label" in str(c.message)] == []
    assert datadir.metadata["sample_custom"] == {
        "Id": "Vax-033898", "Weight": {"value": 1.5, "unit": "mg"},
        "Count": 3, "Passed": True,
        "When": datetime.datetime(2026, 4, 28, 13, 19, 56,
                                  tzinfo=datetime.timezone.utc)}


def _injection(*measurements):
    """One liquid chromatography document, i.e. one injection."""
    return {"measurement aggregate document": {
        "measurement document": list(measurements)}}


def _merged(*injections):
    return {"liquid chromatography aggregate document": {
        "liquid chromatography document": list(injections)}}


def test_a_merged_read_reports_the_first_injections_sample():
    """from_asm merges every injection into one directory, so the selection runs
    across all of them. Assigning per injection and keeping whichever came last
    made a merged read report the LAST injection's sample while its vialpos and
    operator still came from the first.
    """
    document = _merged(
        _injection(_with_cube(**{
            "measurement identifier": "uv1",
            "sample document": {"sample identifier": "AAA",
                                "written name": "A-name",
                                "location identifier": "1:A,1"}})),
        _injection(_with_cube(**{
            "measurement identifier": "uv2",
            "sample document": {"sample identifier": "BBB",
                                "written name": "B-name",
                                "location identifier": "9:Z,9"}})))
    metadata = rb.from_asm(document).metadata
    assert metadata["sample"] == "AAA"
    assert metadata["sample_name"] == "A-name"
    # The vial position is part of the same sample document, so it comes from
    # the same one rather than from whichever injection recorded one first.
    assert metadata["vialpos"] == "1:A,1"


def test_an_empty_sample_document_does_not_count_as_the_winner():
    """An injection that supplies nothing is skipped, so an opening injection
    with no readable sample document does not leave the merged read without
    one."""
    document = _merged(
        _injection(_with_cube(**{"measurement identifier": "uv1",
                                 "sample document": {}})),
        _injection(_with_cube(**{
            "measurement identifier": "uv2",
            "sample document": {"sample identifier": "BBB"}})))
    assert rb.from_asm(document).metadata["sample"] == "BBB"


def test_an_identifier_in_a_later_injection_is_not_lost_to_an_earlier_name():
    """The selection runs over every injection the directory will hold, not one
    at a time. Choosing per injection and keeping the first answer lost the
    identifier whenever an earlier injection supplied only a name -- the same
    loss the within-injection rule exists to prevent, one level up."""
    document = _merged(
        _injection(_with_cube(**{
            "measurement identifier": "uv1",
            "sample document": {"sample identifier": "unknown",
                                "written name": "NB5-P1A11"}})),
        _injection(_with_cube(**{
            "measurement identifier": "uv2",
            "sample document": {"sample identifier": "133872",
                                "written name": "NB5-P1A11"}})))
    metadata = rb.from_asm(document).metadata
    assert metadata["sample"] == "133872"
    assert metadata["sample_name"] == "NB5-P1A11"


def test_custom_fields_in_a_later_injection_are_not_lost_either():
    document = _merged(
        _injection(_with_cube(**{
            "measurement identifier": "uv1",
            "sample document": {"written name": "NAME-1"}})),
        _injection(_with_cube(**{
            "measurement identifier": "uv2",
            "sample document": dict(
                {"sample identifier": "133872"},
                **_custom(_datum("MaterialIdentifier", "scalar string datum",
                                 "Vax-B")))})))
    metadata = rb.from_asm(document).metadata
    assert metadata["sample"] == "133872"
    assert metadata["sample_custom"] == {"MaterialIdentifier": "Vax-B"}
    # Still one document's worth: the other injection's name does not come along.
    assert "sample_name" not in metadata


def test_a_date_with_no_time_of_day_is_not_promoted_to_midnight():
    """ASM types every timestamp as a full date-time. Parsing a bare date gave
    midnight -- a value the document never carried -- and re-exporting it
    published that invention. The write side refuses a Python `date` for the
    same reason, so reading one in was the two directions contradicting."""
    with pytest.warns(UserWarning, match="On.*cannot read"):
        datadir = _read_custom(_datum("On", "scalar timestamp datum",
                                      "2026-04-28"))
    assert "sample_custom" not in datadir.metadata


@pytest.mark.parametrize("text", ["20260428", "2026-W18-2"])
def test_other_date_only_spellings_are_refused_too(text):
    with pytest.warns(UserWarning, match="cannot read"):
        datadir = _read_custom(_datum("On", "scalar timestamp datum", text))
    assert "sample_custom" not in datadir.metadata


def test_decimal_places_reaches_a_custom_double():
    """Every other emitted number honours the option; this one wrote raw, so a
    cube rounded to two places sat beside a custom field that was not."""
    datadir = _read_custom(_datum("w", "scalar double datum", 1.23456789))
    entry = _custom_entries(datadir.to_asm(decimal_places=2))[0]
    assert entry["scalar double datum"] == 1.23


def test_a_read_side_complaint_is_said_once_for_one_sample_document():
    """The same sample document is repeated in every measurement, so a complaint
    about it was made once per candidate channel."""
    import warnings as w

    bad = _custom(_datum("Odd", "scalar float datum", 3))
    document = _lc(*[_with_cube(**{"measurement identifier": "uv%d" % n,
                                   "sample document": dict(bad)})
                     for n in range(4)])
    with w.catch_warnings(record=True) as caught:
        w.simplefilter("always")
        rb.from_asm(document)
    assert len([c for c in caught if "custom field" in str(c.message)]) == 1


@pytest.mark.parametrize("name", [None, "", 5])
def test_an_unusable_sample_name_is_not_written(name):
    """An empty `written name` validates but says nothing, and a reader would
    take it for a sample called the empty string."""
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_name"] = name
    sample = (datadir.to_asm()["liquid chromatography aggregate document"]
              ["liquid chromatography document"][0]
              ["measurement aggregate document"]["measurement document"][0]
              ["sample document"])
    assert "written name" not in sample


@pytest.mark.parametrize("text, expected_hour", [
    ("2026-04-28T13:19:56+00:00", 13),
    # RFC 3339 permits a lowercase separator, the suite's own format checker
    # accepts one, and _parse_iso already tolerates a lowercase `z`. Refusing it
    # dropped a conforming date-time and said rainbow could not read it.
    ("2026-04-28t13:19:56+00:00", 13),
    # No offset, but still a date-time: read, and warned about on export.
    ("2026-04-28T00:30:00", 0),
    # A space is not the schema's separator, but _parse_iso reads it and the
    # re-export writes it back as `T`, so taking it in normalizes it.
    ("2026-04-28 13:19:56+00:00", 13),
])
def test_every_date_time_separator_is_read(text, expected_hour):
    fields = _read_custom(
        _datum("When", "scalar timestamp datum", text)).metadata["sample_custom"]
    assert fields["When"].hour == expected_hour


@pytest.mark.parametrize("text", [
    "2026", "2026-04", "2026-04-28",
    # Padded. These are why the pattern anchors on the digits either side: a
    # separator can be present without a time of day following it, and
    # _parse_iso strips before parsing, so both would come back as midnight.
    "2026-04-28 ", " 2026-04-28",
])
def test_a_date_without_a_time_is_refused_whatever_its_precision(text):
    """A pattern matching the separator alone would admit the padded ones."""
    with pytest.warns(UserWarning, match="cannot read"):
        datadir = _read_custom(_datum("On", "scalar timestamp datum", text))
    assert "sample_custom" not in datadir.metadata


def test_the_vial_position_comes_from_the_chosen_sample_document():
    """It is a field of the sample document like any other, and it is what a
    plate map is looked up by, so taking it first-wins per measurement put the
    wrong well against the right sample."""
    metadata = rb.from_asm(_lc(
        _with_cube(**{"measurement identifier": "uv1",
                      "sample document": {"sample identifier": "unknown",
                                          "written name": "WRONG-A",
                                          "location identifier": "1:A,1"}}),
        _with_cube(**{"measurement identifier": "uv2",
                      "sample document": {"sample identifier": "133872",
                                          "written name": "RIGHT-B",
                                          "location identifier": "9:Z,9"}}),
    )).metadata
    assert metadata["sample"] == "133872"
    assert metadata["sample_name"] == "RIGHT-B"
    assert metadata["vialpos"] == "9:Z,9"


def test_a_vial_position_survives_when_nothing_identifies_the_sample():
    """No document supplies an identity, so none is chosen -- but the position is
    still worth having."""
    metadata = rb.from_asm(_lc(_with_cube(**{
        "measurement identifier": "uv",
        "sample document": {"location identifier": "3:C,7"}}))).metadata
    assert metadata["vialpos"] == "3:C,7"
    assert "sample" not in metadata


def test_each_unlabelled_custom_field_is_reported_separately():
    """The message cannot carry a label, so without the position the dedupe
    reported one warning however many fields were dropped."""
    import warnings as w

    document = _lc(_sample(**{"sample identifier": "s", **_custom(
        {"scalar string datum": "a"},
        {"scalar string datum": "b"},
        {"scalar string datum": "c"})}))
    with w.catch_warnings(record=True) as caught:
        w.simplefilter("always")
        rb.from_asm(document)
    assert len([c for c in caught if "datum label" in str(c.message)]) == 3


# --- Every measurement is read: peaks, detectors, optics, envelope ---


def _cube(concept, unit, label=None, data=True):
    """A chromatogram cube measuring ``concept`` in ``unit``."""
    cube = {"cube-structure": {
        "dimensions": [{"concept": "retention time", "unit": "s"}],
        "measures": [{"concept": concept, "unit": unit}]}}
    if label is not None:
        cube["label"] = label
    if data:
        cube["data"] = {"dimensions": [[0.0, 60.0]],
                        "measures": [[1.0, 2.0]]}
    return cube


def _control(**settings):
    return {"device control aggregate document": {
        "device control document": [dict({"@index": 1}, **settings)]}}


def _fluorescence(data=True, **measurement):
    """An Empower fluorescence measurement with one RFU peak."""
    return dict({
        "measurement identifier": "128288",
        "chromatogram data cube": _cube(
            "fluorescence", "RFU", "ACQUITY FLR ChA Ex280,Em340 nm", data),
        **_control(**{"device type": "fluorescence detector",
                      "device acquisition method": "V175 Long SEC Method"}),
        **_processed(_peak_list(
            _empower_peak(**_rt(105.0), **{
                "peak height": {"value": 3.0, "unit": "RFU"},
                "peak area": {"value": 50.0, "unit": "RFU.s"},
                "peak value at start": {"value": 0.0, "unit": "RFU"},
                "peak value at end": {"value": 0.5, "unit": "RFU"}}),
            **{"processed data identifier": "247109",
               "group identifier": "246987",
               "processed data description": "FLR ChA Ex280,Em340 nm"}))},
        **measurement)


def test_a_fluorescence_channel_is_rebuilt_as_fld_with_its_wavelengths():
    datadir = rb.from_asm(_lc(_fluorescence()))
    datafile = datadir.get_file("128288")
    assert datafile.detector == "FLD"
    assert datafile.metadata["unit"] == "RFU"
    assert datafile.metadata["measure"] == "fluorescence"
    assert datafile.metadata["excitation_wavelength"] == 280.0
    assert datafile.metadata["emission_wavelength"] == 340.0
    # Not an absorbance wavelength: the label's last "340 nm" is the emission.
    assert "wavelength" not in datafile.metadata
    assert datafile.ylabels.tolist() == [340.0]
    assert datafile.metadata["device_type"] == "fluorescence detector"
    assert datafile.metadata["acq_method"] == "V175 Long SEC Method"


def test_a_fluorescence_channels_peaks_are_read_in_rfu():
    group = rb.from_asm(_lc(_fluorescence())).peaks[0]
    assert group["detector"] == "FLD"
    assert group["wavelength"] is None
    assert group["metadata"]["emission_wavelength"] == 340.0
    peak = group["peaks"][0]
    assert (peak["area"], peak["area_unit"]) == (50.0, "RFU.s")
    assert (peak["height"], peak["height_unit"]) == (3.0, "RFU")
    assert peak["end_height"] == 0.5


def test_peaks_are_read_from_a_cube_with_no_values():
    """ An index document carries a cube's structure and none of its data.

    The trace cannot be rebuilt, but the integration is the measurement's,
    and it used to be read only beside a rebuilt trace.
    """
    datadir = rb.from_asm(_lc(_fluorescence(data=False)))
    assert datadir.datafiles == [] and datadir.analog == []
    group = datadir.peaks[0]
    assert group["channel_file"] == "128288"
    assert group["detector"] == "FLD"
    assert group["peaks"][0]["retention_time"] == 1.75


def test_peaks_are_read_on_a_channel_rainbow_has_no_detector_for():
    measurement = {
        "measurement identifier": "1779",
        "chromatogram data cube": _cube("electric conductance", "S", "CD_1"),
        **_control(**{"device type": "electric conductivity detector"}),
        **_processed(_peak_list(_rt(90.0), **{
            "processed data identifier": "1"}))}
    datadir = rb.from_asm(_lc(measurement))
    # No rainbow detector name, so the trace is one of the analog ones.
    assert datadir.datafiles == []
    trace, = datadir.analog
    assert trace.detector is None
    assert trace.metadata["unit"] == "S"
    assert trace.metadata["measure"] == "electric conductance"
    assert datadir.peaks[0]["peaks"][0]["retention_time"] == 1.5


@pytest.mark.parametrize("measurement,detector", [
    ({"chromatogram data cube": _cube("electric current", "pA",
                                      "GC.0.0, Front Signal"),
      **_control(**{"device type": "Flame Ionization Detector"})}, "FID"),
    ({"chromatogram data cube": _cube("electric current", "pA", "ADC1A.CH"),
      **_control(**{"device type": "liquid chromatography detector"})},
     "CAD"),
    # The identifier is a key, not a claim: a GUID segment is not a detector.
    ({"chromatogram data cube": _cube("electric current", "pA"),
      "measurement identifier": "9e1f-adc4-77b2"}, None),
    ({"chromatogram data cube": _cube("intensity", "RLU"),
      **_control(**{"device type": "evaporative light scattering detector"})},
     "ELSD"),
    ({"chromatogram data cube": _cube("absorbance", "mAU"),
      **_control(**{"device type": "refractive index detector"})}, "RID"),
    # rainbow's own relabel of a channel's measure leaves its device type
    # truthful, so the device type, not the measure, names the detector.
    ({"chromatogram data cube": _cube("absorbance", "mAU"),
      **_control(**{"device type": "flame ionization detector"})}, "FID"),
    ({"chromatogram data cube": _cube("absorbance", "mAU")}, "UV"),
    ({"chromatogram data cube": _cube("electric current", "pA")}, None),
])
def test_the_device_type_names_the_detector(measurement, detector):
    measurement.setdefault("measurement identifier", "channel")
    datafile, = rb.from_asm(_lc(measurement)).by_name.values()
    assert datafile.detector == detector
    assert datafile.metadata["unit"] == \
        measurement["chromatogram data cube"]["cube-structure"][
            "measures"][0]["unit"]


@pytest.mark.parametrize("label,expected", [
    ("DAD.0.0, DAD: Signal A, 210.0 nm/Bw:4.0 nm Ref 380.0 nm/Bw:100.0 nm",
     {"wavelength": 210.0, "bandwidth": 4.0, "reference_wavelength": 380.0,
      "reference_bandwidth": 100.0}),
    ("DAD1A,Sig=254,4  Ref=off",
     {"wavelength": 254.0, "bandwidth": 4.0, "reference_wavelength": None}),
    ("DAD1A,Sig=210.0,4.0  Ref=360.0,100.0",
     {"wavelength": 210.0, "bandwidth": 4.0, "reference_wavelength": 360.0,
      "reference_bandwidth": 100.0}),
    ("PDA Ch1 280nm@4.8nm", {"wavelength": 280.0, "bandwidth": 4.8}),
    ("ACQUITY TUV ChA 214nm", {"wavelength": 214.0}),
    ("VWD.0.0, VWD: Signal A, 233 nm", {"wavelength": 233.0}),
    ("ACQUITY FLR ChA Ex280,Em340 nm",
     {"excitation_wavelength": 280.0, "emission_wavelength": 340.0}),
    ("CD_1", {}),
])
def test_a_cube_label_names_the_channels_optics(label, expected):
    assert asm._optics_from_label(label) == expected


def test_a_device_control_setting_outranks_the_label():
    measurement = _with_cube(**{
        "measurement identifier": "uv",
        **_control(**{
            "detector wavelength setting": {"value": 254.0, "unit": "nm"},
            "detector bandwidth setting": {"value": 8.0, "unit": "nm"},
            "electronic absorbance reference wavelength setting":
                {"value": 360.0, "unit": "nm"}})})
    measurement["chromatogram data cube"]["label"] = \
        "DAD1A,Sig=210,4  Ref=off"
    metadata = rb.from_asm(_lc(measurement)).datafiles[0].metadata
    assert metadata["wavelength"] == 254.0
    assert metadata["bandwidth"] == 8.0
    assert metadata["reference_wavelength"] == 360.0


def test_the_signal_description_names_a_channel_its_label_does_not():
    measurement = _with_cube(**{
        "measurement identifier": "uv",
        **_processed(_peak_list(_rt(90.0), **{
            "processed data description":
                "DAD: Signal A, 246.0 nm/Bw:4.0 nm"}))})
    datadir = rb.from_asm(_lc(measurement))
    assert datadir.datafiles[0].metadata["wavelength"] == 246.0
    assert datadir.peaks[0]["wavelength"] == 246.0


def test_the_injection_and_sample_fields_are_read():
    measurement = _fluorescence(**{
        "measurement time": "2026-04-10T18:46:20-04:00",
        "injection document": {
            "injection identifier": "128283",
            "injection time": "2026-04-10T18:46:25-04:00"},
        "sample document": {
            "sample identifier": "128282",
            "sample role type": "standard sample role",
            "well plate identifier": "Plate23",
            "location identifier": "1:A,1"}})
    metadata = rb.from_asm(_lc(measurement)).metadata
    assert metadata["injection_time"] == "2026-04-10T18:46:25-04:00"
    assert metadata["date"] == "2026-04-10T18:46:20-04:00"
    assert metadata["sample_role"] == "standard sample role"
    assert metadata["well_plate_id"] == "Plate23"
    assert metadata["vialpos"] == "1:A,1"
    assert metadata["acq_method"] == "V175 Long SEC Method"


def test_the_sample_fields_are_written_back():
    metadata = {"sample": "s", "sample_role": "blank role",
                "well_plate_id": "Plate23"}
    datadir = rb.from_asm(_lc(_sample(**{
        "sample identifier": "s", "sample role type": "blank role",
        "well plate identifier": "Plate23"})))
    assert {key: datadir.metadata[key] for key in metadata} == metadata
    sample = next(_asm_measurements(datadir.to_asm()))["sample document"]
    assert sample["sample role type"] == "blank role"
    # Not a sample document property in REC/2026/06: custom information.
    assert "well plate identifier" not in sample
    entries = (sample["custom information aggregate document"]
               ["custom information document"])
    assert {"datum label": "well plate identifier",
            "scalar string datum": "Plate23"}.items() <= entries[-1].items()
    again = rb.from_asm(datadir.to_asm())
    assert again.metadata["well_plate_id"] == "Plate23"
    assert "sample_custom" not in again.metadata


_RECORDS = {
    "data system document": {
        "ASM converter name": "Agilent OpenLab ECM Allotrope Export",
        "ASM converter version": "1.2.1.203",
        "software name": "Empower 3 Software"},
    "analysis sequence document": {
        "written name": "NB_23737_0005_10APR2026", "identifier": "128268",
        "start time": "2026-04-10T18:11:45-04:00"},
    "electronic project record": {
        "written name": "VPD_WP\\MRL_MultiRes", "description": "3rd Level"},
}


def test_the_once_per_file_records_are_read_as_written():
    document = _lc(_fluorescence())
    document["liquid chromatography aggregate document"].update(_RECORDS)
    for read in (rb.from_asm, rb.sequence_from_asm):
        metadata = read(document).metadata
        assert metadata["data_system"] == _RECORDS["data system document"]
        assert metadata["analysis_sequence"] \
            == _RECORDS["analysis sequence document"]
        assert metadata["project"] == _RECORDS["electronic project record"]


def test_a_record_keeps_a_quantitys_unit_and_drops_nested_documents():
    assert asm._record({"run time": {"value": 900.0, "unit": "s"},
                        "name": {"value": "x"},
                        "nested": {"a": 1}, "items": [1, 2]}) \
        == {"run time": {"value": 900.0, "unit": "s"}, "name": "x"}
    assert asm._record({}) is None


def test_a_scalar_integer_datum_reads_as_an_int():
    datadir = _read_custom(_datum("Injections", "scalar integer datum", 3),
                           _datum("Vial", "scalar integer datum", 4.0))
    assert datadir.metadata["sample_custom"] == {"Injections": 3, "Vial": 4}
    assert isinstance(datadir.metadata["sample_custom"]["Vial"], int)


def test_a_scalar_integer_datum_that_is_not_whole_is_dropped():
    with pytest.warns(UserWarning, match="Half.*cannot read"):
        datadir = _read_custom(_datum("Half", "scalar integer datum", 2.5))
    assert "sample_custom" not in datadir.metadata


def test_every_integration_is_read_in_order_with_its_provenance():
    measurement = _fluorescence()
    documents = measurement["processed data aggregate document"][
        "processed data document"]
    documents.append(_peak_list(_rt(95.0), _rt(110.0), **{
        "processed data identifier": "250001",
        "group identifier": "246987",
        "processed data description": "FLR ChA Ex280,Em340 nm",
        "data processing time": "2026-04-12T09:00:00-04:00"}))
    with pytest.warns(UserWarning, match="2 processed data documents"):
        group = rb.from_asm(_lc(measurement)).peaks[0]
    assert group["processing"]["identifier"] == "247109"
    assert group["processing"]["group_identifier"] == "246987"
    assert group["processing"]["description"] == "FLR ChA Ex280,Em340 nm"
    alternate, = group["alternates"]
    assert alternate["processing"]["identifier"] == "250001"
    assert [p["retention_time"] for p in alternate["peaks"]] \
        == pytest.approx([95.0 / 60, 110.0 / 60])


def test_a_peaks_identifier_and_index_are_read():
    peak = asm._peak_from_asm(dict(_rt(90.0), **{
        "@index": 7, "identifier": "d5c1-peak"}))
    assert peak["index"] == 7
    assert peak["identifier"] == "d5c1-peak"
    assert asm._asm_peak(1, peak)["identifier"] == "d5c1-peak"


def test_peaks_from_asm_reads_one_measurement():
    measurement = _fluorescence(data=False)
    group = asm.peaks_from_asm(measurement)
    assert group == rb.from_asm(_lc(_fluorescence(data=False))).peaks[0]
    assert asm.peaks_from_asm({"measurement identifier": "x"}) is None
    with pytest.raises(TypeError, match="measurement must be a dict"):
        asm.peaks_from_asm([measurement])


def test_a_fluorescence_channel_round_trips_with_its_peaks():
    first = rb.from_asm(_lc(_fluorescence()), name="run")
    document = first.to_asm()
    measurement, = _measurements(document)
    cube = measurement["chromatogram data cube"]
    assert cube["cube-structure"]["measures"][0]["concept"] == "fluorescence"
    assert cube["cube-structure"]["measures"][0]["unit"] == "RFU"
    control = (measurement["device control aggregate document"]
               ["device control document"][0])
    assert control["device type"] == "fluorescence detector"
    assert control["excitation wavelength setting"]["value"] == 280.0
    assert control["detector wavelength setting"]["value"] == 340.0
    document_peaks = (measurement["processed data aggregate document"]
                      ["processed data document"][0])
    # REC/2026/06's name for what 2025/03 called processed data description.
    assert "processed data description" not in document_peaks
    assert document_peaks["description"] == "FLR ChA Ex280,Em340 nm"
    peak = document_peaks["peak list"]["peak"][0]
    assert peak["peak area"] == {"value": 50.0, "unit": "RFU.s"}
    assert peak["peak height"] == {"value": 3.0, "unit": "RFU"}
    again = rb.from_asm(document, name="run")
    assert again.peaks[0]["peaks"] == first.peaks[0]["peaks"]
    assert again.get_file("128288").detector == "FLD"


# --- A relabeled channel comes back in its real unit ---


def _relabeled_cad():
    """red.D with peaks on its CAD channel, recorded in nA (relabeled)."""
    datadir = rb.read(os.path.join(INPUTS, "red.D"))
    datadir.get_file("ADC1A.CH").metadata["unit"] = "nA"
    datadir.peaks = [{"signal": "ADC1A", "channel_file": "ADC1A.CH",
                      "peaks": [{"retention_time": 1.5, "area": 100.0,
                                 "height": 10.0}]}]
    return datadir


def _cad_measurement(document):
    return next(m for m in _asm_measurements(document)
                if m["measurement identifier"] == "ADC1A.CH")


def test_a_relabeled_channel_reads_back_in_its_real_unit():
    back = rb.from_asm(_relabeled_cad().to_asm(), name="red.D")
    cad = back.get_file("ADC1A.CH")
    assert cad.detector == "CAD"
    assert (cad.metadata["measure"], cad.metadata["unit"]) \
        == ("electric current", "nA")
    group = next(g for g in back.peaks if g["channel_file"] == "ADC1A.CH")
    peak = group["peaks"][0]
    assert (peak["area_unit"], peak["height_unit"]) == ("nA.s", "nA")


def test_a_relabeled_channel_re_exports_relabeled_again():
    again = rb.from_asm(_relabeled_cad().to_asm(), name="red.D").to_asm()
    measurement = _cad_measurement(again)
    cube = measurement["chromatogram data cube"]["cube-structure"]
    assert cube["measures"][0]["unit"] == "mAU"
    peak = (measurement["processed data aggregate document"]
            ["processed data document"][0]["peak list"]["peak"][0])
    assert peak["peak area"]["unit"] == "mAU.s"
    labels = {entry["datum label"]: entry["scalar string datum"]
              for entry in measurement["custom information aggregate document"]
              ["custom information document"]}
    assert labels["reported measure unit"] == "nA"


def _old_relabel_document():
    """A CAD channel the way 1.5.4 relabeled it: absorbance, a sentence."""
    measurement = {
        "measurement identifier": "ADC1A.CH",
        "chromatogram data cube": _cube("absorbance", "mAU", "ADC1A.CH"),
        **_control(**{"device type": "liquid chromatography detector"}),
        "custom information aggregate document": {
            "custom information document": [{
                "datum label": "reported measure",
                "scalar string datum": (
                    "This channel measures electric current (in pA); its "
                    "values are reported as absorbance in mAU so the "
                    "integrated peak list can be carried, which the schema "
                    "models only on an absorbance measurement.")}]},
        **_processed(_peak_list(dict(_rt(30.0), **{
            "peak area": {"value": 5.0, "unit": "mAU.s"},
            "peak height": {"value": 2.0, "unit": "mAU"}})))}
    return _lc(measurement)


def test_a_1_5_4_relabel_reads_back_from_its_sentence():
    back = rb.from_asm(_old_relabel_document())
    cad = back.get_file("ADC1A.CH")
    assert cad.detector == "CAD"
    assert cad.metadata["unit"] == "pA"
    peak = back.peaks[0]["peaks"][0]
    assert (peak["area"], peak["area_unit"]) == (5.0, "pA.s")
    measurement = _cad_measurement(back.to_asm())
    assert measurement["chromatogram data cube"]["cube-structure"][
        "measures"][0] == {"concept": "electric current", "unit": "pA",
                           "@componentDatatype": "double"}
    peak = (measurement["processed data aggregate document"]
            ["processed data document"][0]["peak list"]["peak"][0])
    assert peak["peak area"] == {"value": 5.0, "unit": "pA.s"}
    assert peak["peak height"] == {"value": 2.0, "unit": "pA"}


def test_a_peak_in_another_unit_is_written_in_the_cubes_and_said():
    import warnings as w
    options = asm._Options()
    with w.catch_warnings(record=True) as caught:
        w.simplefilter("always")
        entry = asm._asm_peak(1, {"area": 1.0, "area_unit": "RFU.s",
                                  "height": 1.0, "height_unit": "RFU"},
                              options, "pA")
    assert entry["peak area"]["unit"] == "pA.s"
    assert entry["peak height"]["unit"] == "pA"
    assert any("relabeled and not converted" in str(c.message)
               for c in caught)


def test_peaks_no_exported_channel_carries_are_warned_about():
    # An index document's peaks have no rebuilt trace to ride on.
    datadir = rb.from_asm(_lc(_fluorescence(data=False),
                              _with_cube(**{"measurement identifier": "uv"})))
    with pytest.warns(UserWarning, match="1 peaks on 128288 .* are not in"):
        datadir.to_asm()


def test_an_fld_channel_read_from_asm_exports_without_a_relabel_warning():
    import warnings as w
    datadir = rb.from_asm(_lc(_fluorescence()))
    with w.catch_warnings(record=True) as caught:
        w.simplefilter("always")
        datadir.to_asm(utc_offset="+00:00")
    assert not [c for c in caught if "relabeled" in str(c.message)]


# --- Review round 2 ---


def test_an_elsd_peak_in_microvolts_stays_in_microvolts():
    """ Empower's microvolt is a microabsorbance unit only on a UV channel.

    On an ELSD channel the trace is in µV, and converting its peaks to mAU
    put them a thousand times below the trace they were integrated on.
    """
    measurement = {
        "measurement identifier": "elsd",
        "chromatogram data cube": _cube("intensity", "\u00b5V"),
        **_control(**{"device type": "evaporative light scattering detector"}),
        **_processed(_peak_list(_empower_peak(**_rt(105.0), **{
            "peak height": {"value": 3000.0, "unit": "\u00b5V"},
            "peak area": {"value": 9000.0, "unit": "\u00b5V.s"},
            "peak value at start": {"value": 0.0, "unit": "\u00b5V"},
            "peak value at end": {"value": 50.0, "unit": "\u00b5V"}})))}
    peak = rb.from_asm(_lc(measurement)).peaks[0]["peaks"][0]
    assert (peak["height"], peak["height_unit"]) == (3000.0, "\u00b5V")
    assert (peak["area"], peak["area_unit"]) == (9000.0, "\u00b5V.s")
    assert peak["end_height"] == 50.0


def test_agilents_fluorescence_label_is_read():
    assert asm._optics_from_label("FLD1 A, Ex=230, Em=310") == {
        "excitation_wavelength": 230.0, "emission_wavelength": 310.0}


def test_a_fluorescence_setting_outranks_its_label():
    measurement = _fluorescence(**_control(**{
        "device type": "fluorescence detector",
        "detector wavelength setting": {"value": 350.0, "unit": "nm"},
        "excitation wavelength setting": {"value": 285.0, "unit": "nm"}}))
    metadata = rb.from_asm(_lc(measurement)).get_file("128288").metadata
    assert metadata["emission_wavelength"] == 350.0
    assert metadata["excitation_wavelength"] == 285.0
    assert "wavelength" not in metadata


def test_a_relabeled_channel_re_exports_without_peak_unit_warnings():
    import warnings as w
    first = rb.from_asm(_relabeled_cad().to_asm(utc_offset="+00:00"),
                        name="red.D")
    with w.catch_warnings(record=True) as caught:
        w.simplefilter("always")
        first.to_asm(utc_offset="+00:00")
    assert not [c for c in caught if "a peak read in" in str(c.message)]


def test_only_measures_rainbow_exports_are_listed_as_carrying_peaks():
    # The schema gives conductance a peak list too, but no rainbow detector
    # exports one, so the exporter does not claim it.
    assert not asm._admits_peaks({asm._CHROMATOGRAM_CUBE: {"cube-structure": {
        "measures": [{"concept": "electric conductance", "unit": "S"}]}}})


# --- Review round 3 ---


def test_the_processing_time_is_written_where_the_schema_puts_it():
    processing = {"identifier": "1", "time": "2026-04-12T09:00:00-04:00",
                  "method_name": "m", "description": "Signal A"}
    document = asm._asm_processed_data(1, processing, [{"area": 1.0}],
                                       asm._Options())
    assert "data processing time" not in document
    assert document["data processing document"]["data processing time"] \
        == "2026-04-12T09:00:00-04:00"
    # And it reads back, with the description, from where it was written.
    assert asm._processing_document(document) == dict(
        processing, group_identifier=None, method_version=None, type=None)


def test_an_absorbance_trace_in_au_is_rebuilt_in_mau():
    """ The peaks convert to mAU, so the trace has to as well, or the trace
    minus an edge height is a thousand times off. """
    measurement = {
        "measurement identifier": "uv",
        "chromatogram data cube": _cube("absorbance", "AU"),
        **_processed(_peak_list(_empower_peak(**_rt(30.0), **{
            "peak height": {"value": 0.0015, "unit": "AU"},
            "peak value at start": {"value": 0.0005, "unit": "AU"}})))}
    datadir = rb.from_asm(_lc(measurement))
    datafile = datadir.datafiles[0]
    assert datafile.metadata["unit"] == "mAU"
    assert datafile.data[:, 0].tolist() == [1000.0, 2000.0]
    peak = datadir.peaks[0]["peaks"][0]
    assert peak["height"] == pytest.approx(1.5)
    assert peak["start_height"] == pytest.approx(0.5)


def test_a_trace_in_another_measure_keeps_its_unit():
    measurement = {"measurement identifier": "elsd",
                   "chromatogram data cube": _cube("intensity", "\u00b5V")}
    datafile, = rb.from_asm(_lc(measurement)).by_name.values()
    assert datafile.metadata["unit"] == "\u00b5V"
    assert datafile.data[:, 0].tolist() == [1.0, 2.0]


@pytest.mark.parametrize("unit,area", [
    ("mAU", "mAU.s"), ("pA", "pA.s"), ("RFU", "RFU.s"), ("nA", "nA.s")])
def test_a_peak_area_takes_the_unit_its_schema_names(unit, area):
    entry = asm._asm_peak(1, {"area": 1.0, "height": 1.0}, None, unit)
    assert entry["peak area"]["unit"] == area
    assert entry["peak height"]["unit"] == unit


def test_the_peak_unit_warning_names_its_channel():
    with pytest.warns(UserWarning, match="^ADC1A: a peak read in 'RFU.s'"):
        asm._asm_peak(1, {"area": 1.0, "area_unit": "RFU.s"},
                      asm._Options(), "pA", channel="ADC1A")


# --- Review round 4 ---


def test_a_processing_time_without_an_offset_takes_the_callers():
    processing = {"time": "2025-09-18T11:42:38", "method_name": "m"}
    stamped = asm._asm_processed_data(
        1, processing, [{"area": 1.0}], asm._Options(utc_offset="+00:00"))
    assert stamped["data processing document"]["data processing time"] \
        == "2025-09-18T11:42:38+00:00"
    assert "custom information aggregate document" not in stamped


def test_a_processing_time_with_no_offset_at_all_is_custom_information():
    processing = {"time": "2025-09-18T11:42:38", "method_name": "m"}
    with pytest.warns(UserWarning, match="no UTC offset"):
        document = asm._asm_processed_data(
            1, processing, [{"area": 1.0}], asm._Options())
    assert "data processing time" not in document["data processing document"]
    entry, = (document["custom information aggregate document"]
              ["custom information document"])
    assert entry["datum label"] == "data processing time"
    assert asm._processing_document(document)["time"] \
        == "2025-09-18T11:42:38"


@pytest.mark.parametrize("unit", ["mV", "pA"])
def test_an_fld_channel_in_another_unit_keeps_its_emission(unit):
    import numpy as np
    from rainbow.datadirectory import DataDirectory
    from rainbow.datafile import DataFile

    fld = DataFile("FLD1A", "FLD", np.array([0.0, 1.0]), np.array([310.0]),
                   np.array([[1.0], [2.0]]),
                   {"unit": unit, "excitation_wavelength": 230.0,
                    "emission_wavelength": 310.0})
    back = rb.from_asm(DataDirectory("run", [fld], {}).to_asm())
    metadata = back.get_file("FLD1A").metadata
    assert back.get_file("FLD1A").detector == "FLD"
    assert metadata["emission_wavelength"] == 310.0
    assert metadata["excitation_wavelength"] == 230.0
    assert "wavelength" not in metadata


_PEAK_KEYS = {"identifier", "index", "area_unit", "height_unit"}


def test_an_asm_peak_and_a_vendor_peak_have_the_same_keys():
    vendor = rb.read(os.path.join(INPUTS, "red.D"), peaks=True)
    vendor_group = vendor.peaks[0]
    vendor_peak = vendor_group["peaks"][0]
    assert all(vendor_peak[key] is None for key in _PEAK_KEYS)
    asm_group = rb.from_asm(vendor.to_asm()).peaks[0]
    assert set(asm_group["peaks"][0]) == set(vendor_peak)
    assert set(asm_group) == set(vendor_group)
    assert vendor_group["alternates"] == []
    # And one read from an Empower export, with every key it can carry.
    empower = rb.from_asm(_lc(_fluorescence())).peaks[0]
    assert set(empower["peaks"][0]) == set(vendor_peak)
    assert set(empower) == set(vendor_group)


def test_a_sample_role_outside_the_schema_is_custom_information():
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["sample_role"] = "system suitability"
    sample = next(_asm_measurements(datadir.to_asm()))["sample document"]
    assert "sample role type" not in sample
    entries = (sample["custom information aggregate document"]
               ["custom information document"])
    assert entries[-1]["datum label"] == "sample role type"
    back = rb.from_asm(datadir.to_asm())
    assert back.metadata["sample_role"] == "system suitability"
    assert "sample_custom" not in back.metadata


def test_the_injection_time_and_records_are_written_back():
    measurement = _fluorescence(**{
        "measurement time": "2026-04-10T18:46:20-04:00",
        "injection document": {
            "injection identifier": "128283",
            "injection time": "2026-04-10T18:46:25-04:00"}})
    document = _lc(measurement)
    records = {
        "data system document": {
            "ASM file identifier": "A.JSON",
            "data system instance identifier": "DB ID: 1",
            "database primary key": "1",
            "software name": "Empower 3 Software",
            "Odd Field": "kept"},
        "analysis sequence document": {"written name": "SET_1"},
        "electronic project record": {"written name": "P"}}
    document["liquid chromatography aggregate document"].update(records)
    again = rb.from_asm(document).to_asm()
    aggregate = again["liquid chromatography aggregate document"]
    # No injection volume, so no LC injection document: the time rides the
    # measurement's custom information, and reads back.
    measurement = next(_asm_measurements(again))
    assert "injection document" not in measurement
    assert rb.from_asm(again).metadata["injection_time"] \
        == "2026-04-10T18:46:25-04:00"
    data_system = aggregate["data system document"]
    assert data_system["software name"] == "Empower 3 Software"
    assert "Odd Field" not in data_system
    labels = [entry["datum label"] for entry
              in data_system["custom information aggregate document"]
              ["custom information document"]]
    assert "Odd Field" in labels and "source ASM file identifier" in labels
    assert data_system["ASM converter name"] == "rainbow-api"
    assert aggregate["analysis sequence document"] == {"written name": "SET_1"}
    assert aggregate["electronic project record"] == {"written name": "P"}
    assert rb.from_asm(again).metadata["data_system"]["software name"] \
        == "Empower 3 Software"


def test_a_record_missing_a_required_field_is_not_written():
    datadir = rb.from_asm(_lc(_sample(**{"sample identifier": "s"})))
    datadir.metadata["data_system"] = {"software name": "x"}
    with pytest.warns(UserWarning, match="data system instance identifier"):
        document = datadir.to_asm()
    assert "data system document" not in \
        document["liquid chromatography aggregate document"]


_RAINBOW_1_5_4 = os.path.join(INPUTS, "rainbow_1_5_4.asm.json")


def test_a_document_rainbow_1_5_4_wrote_reads_back_in_real_units():
    """ Written by rainbow 1.5.4 (ff716a7) from red.D: its CAD channel was
    relabeled to absorbance to carry peaks, with only the sentence to say
    so. """
    with open(_RAINBOW_1_5_4) as f:
        document = json.load(f)
    back = rb.from_asm(document, name="red.D")
    cad = back.get_file("ADC1A.CH")
    assert cad.detector == "CAD"
    assert (cad.metadata["measure"], cad.metadata["unit"]) \
        == ("electric current", "pA")
    group = next(g for g in back.peaks if g["channel_file"] == "ADC1A.CH")
    assert group["peaks"][0]["area_unit"] == "pA.s"
    again = _cad_measurement(back.to_asm())
    assert again["chromatogram data cube"]["cube-structure"]["measures"][0][
        "unit"] == "pA"
    peak = (again["processed data aggregate document"]
            ["processed data document"][0]["peak list"]["peak"][0])
    assert peak["peak area"]["unit"] == "pA.s"


def test_an_injection_time_with_a_volume_goes_in_the_injection_document():
    datadir = rb.from_asm(_lc(_fluorescence(**{
        "measurement time": "2026-04-10T18:46:20-04:00",
        "injection document": {
            "injection identifier": "128283",
            "injection time": "2026-04-10T18:46:25-04:00",
            "autosampler injection volume setting (chromatography)":
                {"value": 5.0, "unit": "mm^3"}}})))
    injection = next(_asm_measurements(datadir.to_asm()))["injection document"]
    assert injection["injection time"] == "2026-04-10T18:46:25-04:00"


# --- Review round 5 ---


def _records_document():
    document = _lc(_fluorescence())
    document["liquid chromatography aggregate document"].update({
        "data system document": {
            "ASM converter name": "Agilent OpenLab ECM Allotrope Export",
            "ASM converter version": "1.2.1.203",
            "ASM conversion time": "2026-04-11T17:55:39-04:00",
            "ASM file identifier": "SOURCE.JSON",
            "data system instance identifier": "DB ID: 508927282",
            "database primary key": "128283",
            "software name": "Empower 3 Software",
            "software version": "Build 3471"},
        "analysis sequence document": {
            "written name": "SET_1", "start time": "2026-04-10T18:11:45"}})
    return document


def test_a_re_exported_data_system_names_rainbow_and_keeps_its_source():
    from datetime import datetime
    datadir = rb.from_asm(_records_document(), name="NB5-P2A1")
    data_system = datadir.to_asm(utc_offset="+00:00")[
        "liquid chromatography aggregate document"]["data system document"]
    assert data_system["ASM converter name"] == "rainbow-api"
    assert data_system["ASM converter version"] == asm._rainbow_version()
    assert data_system["ASM file identifier"] == "NB5-P2A1.asm.json"
    assert datetime.fromisoformat(
        data_system["ASM conversion time"]).tzinfo is not None
    # Where the data came from is kept.
    assert data_system["software name"] == "Empower 3 Software"
    assert data_system["data system instance identifier"] \
        == "DB ID: 508927282"
    assert data_system["database primary key"] == "128283"
    source = {entry["datum label"]: entry.get(
        "scalar string datum", entry.get("scalar timestamp datum"))
              for entry in data_system["custom information aggregate document"]
              ["custom information document"]}
    assert source["source ASM conversion time"] == "2026-04-11T17:55:39-04:00"
    assert source["source ASM converter name"] \
        == "Agilent OpenLab ECM Allotrope Export"
    assert source["source ASM file identifier"] == "SOURCE.JSON"


def test_each_per_injection_file_is_its_own_file_identifier(tmp_path):
    sequence = rb.sequence_from_asm(_records_document())
    paths = asm.sequence_export_asm_per_injection(
        sequence, str(tmp_path), utc_offset="+00:00")
    for path in paths:
        with open(path) as f:
            data_system = json.load(f)[
                "liquid chromatography aggregate document"][
                    "data system document"]
        assert data_system["ASM file identifier"] == os.path.basename(path)


def test_a_records_times_take_the_callers_offset():
    datadir = rb.from_asm(_records_document())
    sequence = datadir.to_asm(utc_offset="+00:00")[
        "liquid chromatography aggregate document"][
            "analysis sequence document"]
    assert sequence["start time"] == "2026-04-10T18:11:45+00:00"


def test_the_description_is_read_from_every_place_it_has_been_written():
    for document in ({"description": "A"},
                     {"processed data description": "A"},
                     {"custom information aggregate document": {
                         "custom information document": [{
                             "datum label": "processed data description",
                             "scalar string datum": "A"}]}}):
        assert asm._processing_document(document)["description"] == "A"


def test_a_waters_fluorescence_channel_is_fld(tmp_path):
    from rainbow.waters import masslynx
    path = tmp_path / "_CHRO001.DAT"
    path.write_bytes(b"\x00" * 0x80 + b"\x00" * 8 * 4)
    datafile = masslynx.parse_chrodat(
        str(path), "ACQUITY FLR ChA Ex280,Em340 nm", "EU")
    assert datafile.detector == "FLD"
    assert datafile.ylabels.tolist() == [340.0]
    assert datafile.metadata["excitation_wavelength"] == 280.0
    assert datafile.metadata["emission_wavelength"] == 340.0


def test_one_parser_reads_every_fluorescence_spelling():
    from rainbow import _optics
    from rainbow.agilent import chemstation
    for text in ("FLD1 A, Ex=230, Em=310", "ACQUITY FLR ChA Ex230,Em310 nm",
                 "Ex: 230 nm / Em: 310"):
        assert _optics.excitation_emission(text) == (230.0, 310.0)
        assert chemstation.parse_optics(text)["emission_wavelength"] == 310.0
        assert asm._optics_from_label(text)["excitation_wavelength"] == 230.0


# --- Review round 6 ---


@pytest.mark.parametrize("run", ["red.D", "blue.raw"])
def test_rainbows_own_cad_reads_back_as_cad_and_re_exports(run):
    original = rb.read(os.path.join(INPUTS, run))
    assert "CAD" in original.detectors
    first = original.to_asm()
    back = rb.from_asm(first, name=original.name)
    assert "CAD" in back.detectors
    cads = [d for d in back.datafiles if d.detector == "CAD"]
    assert cads and all(not d.name.endswith(".ms") for d in cads)

    def labels(document):
        return {m["measurement identifier"]
                for m in _asm_measurements(document)}

    assert labels(back.to_asm()) == labels(first)


def test_an_lc_acquisition_method_is_written_back():
    datadir = rb.from_asm(_lc(_fluorescence()))
    assert datadir.metadata["acq_method"] == "V175 Long SEC Method"
    again = rb.from_asm(datadir.to_asm())
    assert again.metadata["acq_method"] == "V175 Long SEC Method"
    assert again.get_file("128288").metadata["acq_method"] \
        == "V175 Long SEC Method"


def test_the_electronic_absorbance_wavelength_setting_is_read():
    measurement = _with_cube(**{
        "measurement identifier": "uv",
        **_control(**{"electronic absorbance wavelength setting":
                      {"value": 254.0, "unit": "nm"}})})
    datafile = rb.from_asm(_lc(measurement)).datafiles[0]
    assert datafile.metadata["wavelength"] == 254.0


@pytest.mark.parametrize("run", ["red.D", "brown.D", "teal.dx"])
def test_a_uv_channels_optics_survive_a_round_trip(run):
    keys = ("wavelength", "bandwidth", "reference_wavelength",
            "reference_bandwidth")
    original = rb.read(os.path.join(INPUTS, run))
    back = rb.from_asm(original.to_asm(), name=original.name)
    checked = 0
    for datafile in original.datafiles:
        if datafile.detector != "UV" or datafile.data.shape[1] != 1:
            continue
        optics = {key: datafile.metadata[key] for key in keys
                  if key in datafile.metadata}
        rebuilt = back.get_file(datafile.name).metadata
        assert {key: rebuilt[key] for key in optics
                if key in rebuilt} == optics, datafile.name
        checked += 1
    assert checked


def test_a_vendor_peak_group_names_its_channels_detector():
    datadir = rb.read(os.path.join(INPUTS, "red.D"), peaks=True)
    by_channel = {g["channel_file"].upper(): g for g in datadir.peaks}
    assert by_channel["ADC1A.CH"]["detector"] == "CAD"
    assert by_channel["ADC1A.CH"]["metadata"]["unit"] \
        == datadir.get_file("ADC1A.CH").metadata["unit"]
    uv = [g for g in datadir.peaks if g["detector"] == "UV"]
    assert uv


# --- Review round 7 ---


def test_a_channel_published_in_another_unit_reads_back_with_its_peaks():
    datadir = rb.read(os.path.join(INPUTS, "red.D"))
    assert datadir.get_file("ADC1A.CH").metadata["unit"] == "mAu"
    datadir.peaks = [{"signal": "ADC1A", "channel_file": "ADC1A.CH",
                      "peaks": [{"retention_time": 1.5, "area": 100.0,
                                 "height": 10.0}]}]
    back = rb.from_asm(datadir.to_asm(), name="red.D")
    assert back.get_file("ADC1A.CH").metadata["unit"] == "mAu"
    peak = next(g for g in back.peaks
                if g["channel_file"] == "ADC1A.CH")["peaks"][0]
    assert (peak["area_unit"], peak["height_unit"]) == ("mAu.s", "mAu")
    # And a second lap publishes it the same way, under its note.
    again = rb.from_asm(back.to_asm(), name="red.D")
    assert again.get_file("ADC1A.CH").metadata["unit"] == "mAu"


def test_peaks_from_asm_refuses_a_whole_document():
    with pytest.raises(ValueError, match="whole ASM document"):
        asm.peaks_from_asm(_lc(_fluorescence()))


def test_the_version_an_export_names_is_pyprojects():
    import re
    pyproject = os.path.join(os.path.dirname(__file__), "..",
                             "pyproject.toml")
    with open(pyproject) as f:
        declared = re.search(r'^version\s*=\s*"([^"]+)"', f.read(),
                             re.MULTILINE).group(1)
    assert rb.__version__ == declared
    assert asm._rainbow_version() == declared


@pytest.mark.parametrize("unit,absorbance,expected", [
    ("mAU.min", True, (6.0, "mAU.s")),
    ("RFU.min", False, (6.0, "RFU.s")),
    ("mAU.s", True, (0.1, "mAU.s")),
    ("mAU.h", True, (None, None))])
def test_an_area_per_minute_is_converted_and_an_unknown_time_is_none(
        unit, absorbance, expected):
    value, read_unit = asm._peak_measure({"value": 0.1, "unit": unit}, ".s",
                                         absorbance)
    assert read_unit == expected[1]
    assert value == pytest.approx(expected[0]) if expected[0] is not None \
        else value is None


def test_a_records_source_survives_a_second_round_trip():
    first = rb.from_asm(_records_document()).to_asm(utc_offset="+00:00")
    second = rb.from_asm(first).to_asm(utc_offset="+00:00")
    data_system = second["liquid chromatography aggregate document"][
        "data system document"]
    entries = {entry["datum label"]: entry for entry
               in data_system["custom information aggregate document"]
               ["custom information document"]}
    assert entries["source ASM converter name"]["scalar string datum"] \
        == "Agilent OpenLab ECM Allotrope Export"
    assert entries["source ASM file identifier"]["scalar string datum"] \
        == "SOURCE.JSON"
    assert entries["source ASM conversion time"]["scalar timestamp datum"] \
        == "2026-04-11T17:55:39-04:00"
