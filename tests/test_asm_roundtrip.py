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


def test_injection_named_from_sample_identifier_when_present():
    # red.D has sample 'usp'; the reconstructed injection takes that name,
    # since the .D folder name is not stored in ASM.
    back = rb.sequence_from_asm(rb.read("tests/inputs/red.D").to_asm())
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


def test_only_absorbance_channels_are_reconstructed():
    # red.D has a CAD channel (an electric-current cube, export-only) alongside
    # its UV channels. from_asm reconstructs only the absorbance (UV) cubes, so
    # the CAD channel is dropped rather than mislabeled back into a UV trace.
    original = rb.read("tests/inputs/red.D")
    assert any(d.detector == "CAD" for d in original.datafiles)
    back = rb.from_asm(original.to_asm())
    assert all(d.detector == "UV" for d in back.datafiles)
    assert not any(d.name == "ADC1A.CH" for d in back.datafiles)


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


def test_a_non_absorbance_channel_is_export_only():
    """ The documented exception: a CAD cube does not survive re-export. """
    datadir = rb.read(os.path.join(INPUTS, "red.D"))
    assert "CAD" in datadir.detectors
    first = datadir.to_asm()
    again = rb.from_asm(first, name=datadir.name).to_asm()
    assert again != first

    def labels(document):
        aggregate = document["liquid chromatography aggregate document"]
        return {cube["label"]
                for injection in aggregate["liquid chromatography document"]
                for measurement in (injection["measurement aggregate document"]
                                    ["measurement document"])
                for key, cube in measurement.items() if key.endswith("cube")}

    dropped = labels(first) - labels(again)
    assert dropped == {"ADC1A.CH"}


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
