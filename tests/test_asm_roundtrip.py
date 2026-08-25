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
    original = rb.read("tests/inputs/red.D")
    back = rb.from_asm(original.to_asm())
    assert back.metadata["sample"] == original.metadata["sample"]
    assert back.metadata["date"] == original.metadata["date"]
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
