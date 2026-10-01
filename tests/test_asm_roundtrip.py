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
    ("DAD1A, Sig=254,4 Ref=off", None),
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
        _datum("Odd", "scalar integer datum", 3))}))
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

    bad = _custom(_datum("Odd", "scalar integer datum", 3))
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
