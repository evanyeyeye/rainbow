"""
Tests for sequence-level ASM export (DataSequence.to_asm) and the envelope
enrichment shared with single-injection export.

The sequence fixtures copy the small brown.D UV fixture into injection
subdirectories and drop a synthetic sequence.acaml (instrument modules + a peak
list) beside them, so the join from peaks to channels runs end to end without
any real instrument data.
"""
import json
import os
import shutil

import pytest

import rainbow as rb
from rainbow import asm


FIXTURE = os.path.join(os.path.dirname(__file__), "inputs", "brown.D")
INJECTION_NAMES = ["008-D1F-A1-sample_01.D", "009-D1F-A2-sample_02.D"]

# A sequence.acaml with an instrument (two modules) and peaks for the first
# injection's DAD1A channel.
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
def sequence(tmp_path):
    seq = tmp_path / "Seq"
    seq.mkdir()
    for name in INJECTION_NAMES:
        shutil.copytree(FIXTURE, seq / name)
    (seq / "sequence.acaml").write_text(SEQUENCE_ACAML, encoding="utf-8")
    return rb.read_sequence(str(seq), peaks=True)


def _aggregate(document):
    return document["liquid chromatography aggregate document"]


def test_top_level_has_one_lc_document_per_injection(sequence):
    document = sequence.to_asm()
    assert document["$asm.manifest"]
    lc = _aggregate(document)["liquid chromatography document"]
    assert len(lc) == len(INJECTION_NAMES)
    assert all(d["analyst"] == "LAB\\runner" for d in lc)


def test_device_system_from_instrument_modules(sequence):
    dsd = _aggregate(sequence.to_asm())["device system document"]
    assert dsd["asset management identifier"] == "1290"
    devices = dsd["device document"]
    types = [d.get("device type") for d in devices]
    assert "diode array detector" in types
    assert "pump" in types
    dad = next(d for d in devices if d["device type"] == "diode array detector")
    assert dad["model number"] == "G7117B"
    assert dad["equipment serial number"] == "SN-DAD"
    assert dad["firmware version"] == "D.07.35"


def test_peaks_become_processed_data_on_the_right_channel(sequence):
    document = sequence.to_asm()
    first = _aggregate(document)["liquid chromatography document"][0]
    measurements = first["measurement aggregate document"]["measurement document"]
    # The DAD1A channel measurement should carry the peak list.
    dad1a = next(m for m in measurements
                 if m["measurement identifier"].upper().startswith("DAD1A"))
    peaks = (dad1a["processed data aggregate document"]
             ["processed data document"][0]["peak list"]["peak"])
    assert len(peaks) == 1
    peak = peaks[0]
    # retention time minutes -> seconds
    assert peak["retention time"] == {"value": 60.0, "unit": "s"}
    assert peak["peak area"]["value"] == 100.0
    assert peak["relative peak area"] == {"value": 60.0, "unit": "%"}


def test_channels_without_peaks_have_no_processed_data(sequence):
    document = sequence.to_asm()
    second = _aggregate(document)["liquid chromatography document"][1]
    measurements = second["measurement aggregate document"]["measurement document"]
    # The second injection had no peaks in the synthetic document.
    assert all("processed data aggregate document" not in m
               for m in measurements)


def test_sequence_asm_is_json_serializable(sequence):
    document = sequence.to_asm()
    assert json.loads(json.dumps(document)) == document


def test_export_asm_writes_a_file(sequence, tmp_path):
    out = tmp_path / "sequence.asm.json"
    sequence.export_asm(str(out))
    written = json.loads(out.read_text())
    assert (written["liquid chromatography aggregate document"]
            ["device system document"]["asset management identifier"] == "1290")


def test_export_asm_per_injection_writes_one_file_each(sequence, tmp_path):
    out = tmp_path / "per_injection"
    paths = sequence.export_asm(str(out), per_injection=True)
    # One standalone document per injection, named for the injection.
    assert [os.path.basename(p) for p in paths] == [
        "008-D1F-A1-sample_01.asm.json", "009-D1F-A2-sample_02.asm.json"]
    for path in paths:
        document = json.loads(open(path).read())
        aggregate = document["liquid chromatography aggregate document"]
        # Each file is complete: manifest, the shared device system, and exactly
        # one injection's chromatography document.
        assert "$asm.manifest" in document
        assert (aggregate["device system document"]
                ["asset management identifier"] == "1290")
        assert len(aggregate["liquid chromatography document"]) == 1


def test_export_asm_per_injection_uniquifies_duplicate_names(tmp_path):
    # Re-injected blanks/standards commonly share a name; the per-injection
    # files must not collide and silently overwrite each other.
    from rainbow.datasequence import DataSequence
    one = rb.read(FIXTURE)            # name "brown.D"
    two = rb.read(FIXTURE)            # same name -> same base filename
    seq = DataSequence(str(tmp_path / "Seq"), [one, two], {})
    paths = seq.export_asm(str(tmp_path / "per_injection"), per_injection=True)
    assert len(paths) == 2 and len(set(paths)) == 2
    assert all(os.path.exists(p) for p in paths)
    assert sorted(os.path.basename(p) for p in paths) == [
        "brown.asm.json", "brown_2.asm.json"]


def test_each_per_injection_document_carries_its_own_warnings(tmp_path):
    # A warning said "once per run" was keyed to the _Options object, which
    # sequence_export_asm_per_injection reuses for every file it writes. One
    # warning then stood for N standalone documents and named an injection that
    # was not in most of them, while the rest were written silently invalid.
    import warnings
    from rainbow.datasequence import DataSequence

    injections = []
    for name in ("001-A1-std.D", "002-A2-std.D", "003-A3-std.D"):
        injection = rb.read("tests/inputs/yellow.D")
        injection.name = name
        injections.append(injection)
    seq = DataSequence(str(tmp_path / "Seq"), injections, {})

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        paths = seq.export_asm(str(tmp_path / "per_injection"),
                               per_injection=True)
    volume = [str(w.message) for w in caught
              if "records no injection volume" in str(w.message)]
    # One per document written, each naming the injection it is about.
    assert len(paths) == 3
    assert len(volume) == 3
    assert {p.split()[0] for p in volume} == {
        "001-A1-std.D", "002-A2-std.D", "003-A3-std.D"}


def test_sequence_export_asm_streams_equal_to_in_memory(sequence, tmp_path):
    out = tmp_path / "seq.asm.json"
    sequence.export_asm(str(out))
    assert json.loads(out.read_text()) == sequence.to_asm()


def test_sequence_export_asm_streams_with_options_and_compact(sequence, tmp_path):
    # Exercise the indent=0 separator branch and option threading.
    out = tmp_path / "seq.asm.json"
    sequence.export_asm(str(out), decimal_places=3, indent=0)
    assert json.loads(out.read_text()) == sequence.to_asm(decimal_places=3)


def test_sequence_export_asm_pretty_output_matches_canonical(sequence, tmp_path):
    # Streamed injection documents are indented under the aggregate document,
    # so the output is byte-identical to a single json.dumps(indent=2).
    out = tmp_path / "seq.asm.json"
    sequence.export_asm(str(out))
    assert out.read_text() == json.dumps(
        sequence.to_asm(), indent=2, ensure_ascii=False)


# --- helper-level unit tests (no fixtures) ---

def test_device_system_falls_back_without_modules():
    dsd = asm._device_system({"sample": "x"})
    assert dsd["device document"] == [{"device type": "liquid chromatograph"}]
    assert dsd["asset management identifier"] == "unknown"


def test_device_system_from_per_injection_modules():
    metadata = {"modules": [{"name": "DAD", "model": "G7117B"}]}
    dsd = asm._device_system(metadata)
    device = dsd["device document"][0]
    assert device["device type"] == "diode array detector"
    assert device["model number"] == "G7117B"
    assert "equipment serial number" not in device


def test_module_device_type_mapping():
    assert asm._module_device_type({"name": "DAD", "type": "Detector"}) == \
        "diode array detector"
    assert asm._module_device_type({"name": "x", "type": "Pump"}) == "pump"
    assert asm._module_device_type(
        {"name": "x", "type": "Auto sampler"}) == "autosampler"
    # an unmapped type yields no device type rather than a guess
    assert asm._module_device_type({"name": "x", "type": "Mystery"}) is None


def test_module_device_type_inferred_from_name_without_type():
    # The per-injection modules carry a name but no type, so the device type is
    # inferred from the name (every result is a checked AFO class).
    assert asm._module_device_type({"name": "Quat. Pump"}) == "pump"
    assert asm._module_device_type({"name": "Multisampler"}) == "autosampler"
    assert asm._module_device_type({"name": "Column Comp."}) == \
        "column compartment"
    assert asm._module_device_type({"name": "VWD"}) == "ultraviolet detector"


def test_sequence_device_system_borrows_injection_modules():
    # With no sequence-level instrument, the device system falls back to an
    # injection's per-injection modules (name + model, the P3 shape).
    from rainbow.datasequence import DataSequence
    injection = rb.read("tests/inputs/red.D")
    injection.metadata["modules"] = [
        {"name": "DAD", "model": "G7117B"},
        {"name": "Quat. Pump", "model": "G7104A"},
    ]
    seq = DataSequence("seq", [injection], {"injection_count": 1})
    dsd = seq.to_asm()["liquid chromatography aggregate document"][
        "device system document"]
    models = {d.get("model number") for d in dsd["device document"]}
    assert {"G7117B", "G7104A"} <= models
    types = {d.get("device type") for d in dsd["device document"]}
    assert "diode array detector" in types and "pump" in types


def test_asm_peak_converts_times_to_seconds():
    peak = asm._asm_peak(1, {"retention_time": 2.0, "start_time": 1.5,
                             "end_time": 2.5, "area": 50.0})
    assert peak["retention time"] == {"value": 120.0, "unit": "s"}
    assert peak["peak start"] == {"value": 90.0, "unit": "s"}
    assert peak["peak end"] == {"value": 150.0, "unit": "s"}
    assert peak["peak area"] == {"value": 50.0, "unit": "mAU.s"}


def test_a_round_trip_restores_the_injection_names(tmp_path):
    # The document already carries an "injection identifier" per injection, the
    # .D folder name it was exported under. Reading it back off the sample
    # identifier instead collapsed a set of replicates (which share a sample)
    # into name, name_2, name_3, so get_injection could not find any of them
    # under the name the caller knows.
    from rainbow.datasequence import DataSequence

    names = ["001-A1_01.D", "002-A2_02.D", "003-A3_03.D"]
    injections = []
    for name in names:
        injection = rb.read(FIXTURE)
        injection.name = name
        injection.metadata["sample"] = "usp"   # replicates share a sample
        # The LC schema requires the volume in the same injection document that
        # carries the identifier, so a run that records no volume has nowhere
        # to put its name; see sequence_from_asm.
        injection.metadata["injection_volume"] = {"value": 5.0, "unit": "uL"}
        injections.append(injection)
    seq = DataSequence(str(tmp_path / "Seq"), injections, {})

    back = rb.sequence_from_asm(seq.to_asm())
    assert [i.name for i in back.injections] == names
    for name in names:
        assert name in back
        assert back.get_injection(name).name == name


def test_sequence_membership_and_indexing(sequence):
    first = sequence.injections[0]
    # Without __contains__, this fell back to iterating and comparing each
    # injection object against a string, so it answered False for a name that
    # is present: a membership test that quietly says no.
    assert first.name in sequence
    assert "not-an-injection.D" not in sequence
    # Indexing by position, by slice, and by name.
    assert sequence[0] is first
    assert sequence[0:1] == [first]
    assert sequence[first.name] is first


def test_an_unknown_injection_name_says_what_is_there(sequence):
    with pytest.raises(KeyError) as excinfo:
        sequence.get_injection("nope.D")
    assert sequence.injections[0].name in str(excinfo.value)


@pytest.mark.parametrize("indent", [2, 0, None, 4, "  ", "\t", ""])
def test_the_streamed_writer_takes_every_indent_json_takes(sequence, tmp_path,
                                                           indent):
    # json.dumps accepts a string indent as well as a number, and to_asm_str
    # passes one straight through, so the streamed writers must too. A string
    # used to raise "unsupported operand type(s) for +: 'int' and 'str'".
    out = tmp_path / "seq.asm.json"
    sequence.export_asm(str(out), indent=indent)
    written = out.read_text()
    assert json.loads(written) == sequence.to_asm()

    # And it is laid out the way json.dumps lays it out. Parsing back does not
    # catch a layout bug: the injection documents were indented by a count of
    # leading spaces, so a tab indent counted zero and every injection sat at
    # the top level, and indent=0 and indent=None each differed from json's own
    # spelling. All of it stayed valid JSON and none of it was the file
    # to_asm_str would have written.
    expected = json.dumps(sequence.to_asm(), indent=indent, ensure_ascii=False)
    # Compared as a boolean: these documents run to tens of megabytes, and
    # letting the assertion rewriter diff two of them takes longer than the
    # rest of the suite put together.
    assert (written == expected) is True, _where_they_differ(written, expected)


def _where_they_differ(written, expected):
    """A short report of the first difference between two long strings."""
    for index, (a, b) in enumerate(zip(written, expected)):
        if a != b:
            window = slice(max(0, index - 60), index + 60)
            return "at {}: wrote {!r}, json.dumps writes {!r}".format(
                index, written[window], expected[window])
    return "identical for {} characters, then lengths differ: {} and {}".format(
        min(len(written), len(expected)), len(written), len(expected))
