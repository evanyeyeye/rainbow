"""
Tests for sequence.acaml header reading (rainbow.agilent.sequence).

The fixture is a synthetic sequence.acaml: a DocInfo operator plus one
instrument with two modules, namespaced like the real document but with
invented serials. The heavy result section is omitted, which is exactly the
part parse_header is designed to skip.
"""
import os

from rainbow.agilent import sequence


SEQUENCE_ACAML = """<?xml version="1.0" encoding="utf-8"?>
<ACAML xmlns="urn:schemas-agilent-com:acaml15"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Doc>
    <DocID>00000000-0000-0000-0000-0000000000ff</DocID>
    <DocInfo>
      <CreatedByUser>LAB\\runner</CreatedByUser>
      <CreationDate>2024-04-25T15:55:01-04:00</CreationDate>
    </DocInfo>
    <Content>
      <Resources>
        <Instrument xsi:type="InstrumentType" id="aaaa">
          <Name>1290</Name>
          <Technique>LiquidChromatography</Technique>
          <Module>
            <Name>DAD</Name>
            <Type>Detector</Type>
            <PartNo>G7117B</PartNo>
            <SerialNo>SN-DAD-001</SerialNo>
            <FirmwareRevision>D.07.35</FirmwareRevision>
          </Module>
          <Module>
            <Name>Quat. Pump</Name>
            <Type>Pump</Type>
            <PartNo>G7104A</PartNo>
            <SerialNo>SN-PUMP-002</SerialNo>
            <FirmwareRevision>B.07.35</FirmwareRevision>
          </Module>
        </Instrument>
      </Resources>
    </Content>
  </Doc>
</ACAML>
"""


def _write(tmp_path, text=SEQUENCE_ACAML, name="sequence.acaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_parse_header_reads_operator(tmp_path):
    header = sequence.parse_header(_write(tmp_path))
    assert header["operator"] == "LAB\\runner"


def test_parse_header_reads_instrument_and_modules(tmp_path):
    instrument = sequence.parse_header(_write(tmp_path))["instrument"]
    assert instrument["name"] == "1290"
    assert instrument["technique"] == "LiquidChromatography"
    assert len(instrument["modules"]) == 2
    dad = instrument["modules"][0]
    assert dad == {
        "name": "DAD",
        "type": "Detector",
        "part_no": "G7117B",
        "serial_no": "SN-DAD-001",
        "firmware": "D.07.35",
    }


def test_find_locates_sequence_acaml(tmp_path):
    _write(tmp_path)
    assert sequence.find(str(tmp_path)).endswith("sequence.acaml")


def test_find_is_case_insensitive(tmp_path):
    _write(tmp_path, name="Sequence.acaml")
    assert sequence.find(str(tmp_path)) is not None


def test_find_returns_none_without_sequence_file(tmp_path):
    assert sequence.find(str(tmp_path)) is None


def test_parse_header_tolerates_malformed_xml(tmp_path):
    bad = _write(tmp_path, text="<ACAML><Doc>truncated")
    assert sequence.parse_header(bad) == {}


# A synthetic result graph: two signals (254, 280) for one injection plus a
# signal for an off-disk blank, with peaks under SignalResults (and one empty
# SignalResult that must be skipped).
def _signal(signal_id, d_name, channel, description):
    return f"""
      <Signal xsi:type="SignalType" id="{signal_id}">
        <BinaryData><DataItem><Data><DataFileReference>
          <Path>{d_name}\\{channel}</Path>
        </DataFileReference></Data></DataItem></BinaryData>
        <Name>{channel.split('.')[0]}</Name>
        <Description>{description}</Description>
      </Signal>"""


PEAKS_ACAML = f"""<?xml version="1.0" encoding="utf-8"?>
<ACAML xmlns="urn:schemas-agilent-com:acaml15"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Doc><Content>
    <Resources>
      {_signal("sig-254", "008-D1F-A1-sample_01.D", "DAD1A.CH",
               "DAD1 A, Sig=254,4 Ref=360,100")}
      {_signal("sig-280", "008-D1F-A1-sample_01.D", "DAD1G.CH",
               "DAD1 G, Sig=280,4 Ref=off")}
      {_signal("sig-blank", "001-NV-Blank.D", "DAD1A.CH", "Sig=254,4")}
    </Resources>
    <Injections>
      <Result xsi:type="InjectionResultType" id="res-1">
        <SignalResult id="sr-254">
          <Signal_ID id="sig-254" />
          <Peak id="p1">
            <RetentionTime val="1.5" /><Area val="100.0" />
            <AreaPercent val="60.0" /><Height val="10.0" />
            <HeightPercent val="55.0" /><BeginTime val="1.4" />
            <EndTime val="1.6" /><Symmetry val="0.9" />
          </Peak>
          <Peak id="p2"><RetentionTime val="2.5" /><Area val="40.0" /></Peak>
        </SignalResult>
        <SignalResult id="sr-280">
          <Signal_ID id="sig-280" />
          <Peak id="p3"><RetentionTime val="1.5" /><Area val="80.0" /></Peak>
        </SignalResult>
        <SignalResult id="sr-empty"><Signal_ID id="sig-254" /></SignalResult>
      </Result>
      <Result xsi:type="InjectionResultType" id="res-blank">
        <SignalResult id="sr-b">
          <Signal_ID id="sig-blank" />
          <Peak id="pb"><RetentionTime val="0.5" /><Area val="2.0" /></Peak>
        </SignalResult>
      </Result>
    </Injections>
  </Content></Doc>
</ACAML>
"""


def test_parse_peaks_groups_by_injection_and_signal(tmp_path):
    by_injection = sequence.parse_peaks(_write(tmp_path, PEAKS_ACAML))
    assert set(by_injection) == {"008-D1F-A1-sample_01.D", "001-NV-Blank.D"}
    groups = by_injection["008-D1F-A1-sample_01.D"]
    assert len(groups) == 2
    by_signal = {g["signal"]: g for g in groups}
    assert by_signal["DAD1A"]["wavelength"] == 254.0
    assert by_signal["DAD1G"]["wavelength"] == 280.0
    assert len(by_signal["DAD1A"]["peaks"]) == 2
    assert len(by_signal["DAD1G"]["peaks"]) == 1


def test_parse_peaks_reads_measures_and_channel(tmp_path):
    groups = sequence.parse_peaks(
        _write(tmp_path, PEAKS_ACAML))["008-D1F-A1-sample_01.D"]
    dad1a = next(g for g in groups if g["signal"] == "DAD1A")
    assert dad1a["channel_file"] == "DAD1A.CH"
    peak = dad1a["peaks"][0]
    assert peak["retention_time"] == 1.5
    assert peak["area"] == 100.0
    assert peak["area_percent"] == 60.0
    assert peak["height"] == 10.0
    assert peak["symmetry"] == 0.9
    assert peak["start_time"] == 1.4 and peak["end_time"] == 1.6


def test_parse_peaks_skips_empty_signal_results(tmp_path):
    # The sr-empty SignalResult (no peaks) must not add a group.
    groups = sequence.parse_peaks(
        _write(tmp_path, PEAKS_ACAML))["008-D1F-A1-sample_01.D"]
    assert len(groups) == 2


ODD_MEASURES_ACAML = f"""<?xml version="1.0" encoding="utf-8"?>
<ACAML xmlns="urn:schemas-agilent-com:acaml15"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Doc><Content>
    <Resources>
      {_signal("s", "008-D1F-A1-sample_01.D", "DAD1A.CH", "Sig=254,4")}
    </Resources>
    <Injections>
      <Result xsi:type="InjectionResultType" id="r">
        <SignalResult id="sr">
          <Signal_ID id="s" />
          <Peak id="p">
            <RetentionTime>1.5</RetentionTime>
            <Area val="bad" />
            <Height val="9.0" />
          </Peak>
        </SignalResult>
      </Result>
    </Injections>
  </Content></Doc>
</ACAML>
"""


def test_parse_peaks_tolerates_text_and_malformed_measures(tmp_path):
    # A measure given as element text (no val attribute) or a non-numeric val
    # falls back to the raw value instead of crashing the parse.
    groups = sequence.parse_peaks(
        _write(tmp_path, ODD_MEASURES_ACAML))["008-D1F-A1-sample_01.D"]
    peak = groups[0]["peaks"][0]
    assert peak["retention_time"] == "1.5"   # element text fallback
    assert peak["area"] == "bad"             # non-numeric val fallback
    assert peak["height"] == 9.0             # well-formed val still numeric


def test_etree_fallback_matches_lxml_for_peaks(tmp_path, monkeypatch):
    # Forcing _lxml to None exercises the xml.etree fallback; it must produce
    # the same result as the default backend. (A no-op when lxml is absent.)
    path = _write(tmp_path, PEAKS_ACAML)
    expected = sequence.parse_peaks(path)
    monkeypatch.setattr(sequence, "_lxml", None)
    assert sequence.parse_peaks(path) == expected


def test_etree_fallback_matches_lxml_for_header(tmp_path, monkeypatch):
    path = _write(tmp_path)
    expected = sequence.parse_header(path)
    monkeypatch.setattr(sequence, "_lxml", None)
    assert sequence.parse_header(path) == expected


# A document that puts the Signal inside the SignalResult that references it,
# after the children that SignalResult is read for. Agilent's own exports keep
# signals in Resources, but the reader is pointed at documents rainbow did not
# write, and the streaming parser must not destroy a subtree it is still
# building.
NESTED_SIGNAL_ACAML = f"""<?xml version="1.0" encoding="utf-8"?>
<ACAML xmlns="urn:schemas-agilent-com:acaml15"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Doc><Content>
    <Injections>
      <Result xsi:type="InjectionResultType" id="r">
        <SignalResult id="sr">
          <Signal_ID id="s" />
          <Peak id="p">
            <RetentionTime val="1.5" />
            <Area val="5.0" />
          </Peak>
          {_signal("s", "008-D1F-A1-sample_01.D", "DAD1A.CH", "Sig=254,4")}
        </SignalResult>
      </Result>
    </Injections>
  </Content></Doc>
</ACAML>
"""


def test_a_signal_nested_in_its_own_result_keeps_the_peaks(tmp_path):
    # The pruning that keeps the tree from accumulating deletes earlier
    # siblings. Here those siblings are the Signal_ID and Peak the enclosing
    # SignalResult has not been read for yet, so pruning at the inner Signal
    # loses the peaks entirely and the injection disappears.
    by_injection = sequence.parse_peaks(
        _write(tmp_path, NESTED_SIGNAL_ACAML))
    groups = by_injection["008-D1F-A1-sample_01.D"]
    assert len(groups) == 1
    assert groups[0]["signal"] == "DAD1A"
    assert [p["area"] for p in groups[0]["peaks"]] == [5.0]


def test_etree_fallback_matches_lxml_on_a_nested_signal(tmp_path, monkeypatch):
    # The two backends are documented to yield the same elements, which is a
    # claim about the awkward shapes rather than the easy ones.
    path = _write(tmp_path, NESTED_SIGNAL_ACAML)
    expected = sequence.parse_peaks(path)
    monkeypatch.setattr(sequence, "_lxml", None)
    assert sequence.parse_peaks(path) == expected
    assert expected  # both empty would satisfy the equality above
