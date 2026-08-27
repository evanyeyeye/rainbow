"""
Unit tests for the shared Agilent ACAML reader (rainbow.agilent.acaml).

The fixtures here are synthetic: they mirror the real acq.macaml / da.macaml /
sequence.acaml skeleton (DocInfo header + nested Section/Table/Parameter tree)
but carry invented operators and values, so no real instrument data is needed.
"""
from rainbow.agilent import acaml


# A synthetic acquisition-method ACAML, namespaced exactly like the real files.
# It carries a DocInfo header and a DAD method with a plain parameter section
# and a tabular signal section, the two shapes the reader must handle.
METHOD_ACAML = """<?xml version="1.0" encoding="utf-8"?>
<ACAML xmlns="urn:schemas-agilent-com:acaml15"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Doc>
    <DocID>00000000-0000-0000-0000-000000000001</DocID>
    <DocInfo>
      <Description>Method ACAML</Description>
      <CreatedByUser>LAB\\analyst1</CreatedByUser>
      <CreatedByApplication>
        <AgilentApp>
          <Name>ChemStation</Name>
          <Version>2.200.0.0</Version>
        </AgilentApp>
      </CreatedByApplication>
      <CreationDate>2024-04-25T16:39:46-04:00</CreationDate>
      <ClientName>BENCH1</ClientName>
    </DocInfo>
    <Content>
      <MethodConfiguration>
        <MethodDescription>
          <Name>Method Configuration</Name>
          <ID>Method_Configuration</ID>
          <Section>
            <Name>Acquisition Method</Name>
            <ID>Acquisition_Method</ID>
            <Section>
              <Name>DAD (G7117B)</Name>
              <ID>G7117B</ID>
              <Section>
                <Name>Analog Output</Name>
                <ID>AnalogOutput1</ID>
                <Parameter>
                  <Name>Analog Zero Offset</Name>
                  <ID>AnalogOutput1_AnalogZero</ID>
                  <Unit>%</Unit>
                  <Value>5</Value>
                </Parameter>
              </Section>
              <Section>
                <Name>Signals</Name>
                <ID>Signals</ID>
                <Table>
                  <Name>Signal table</Name>
                  <ID>Signals_Signal</ID>
                  <Row>
                    <Parameter>
                      <Name>Wavelength</Name>
                      <ID>Signal_Wavelength</ID>
                      <Unit>nm</Unit>
                      <Value>254.0</Value>
                    </Parameter>
                  </Row>
                  <Row>
                    <Parameter>
                      <Name>Wavelength</Name>
                      <ID>Signal_Wavelength</ID>
                      <Unit>nm</Unit>
                      <Value>280.0</Value>
                    </Parameter>
                  </Row>
                </Table>
              </Section>
            </Section>
          </Section>
        </MethodDescription>
      </MethodConfiguration>
    </Content>
  </Doc>
</ACAML>
"""


def test_doc_info_reads_header():
    info = acaml.doc_info(METHOD_ACAML)
    assert info["operator"] == "LAB\\analyst1"
    assert info["application"] == "ChemStation"
    assert info["application_version"] == "2.200.0.0"
    assert info["client"] == "BENCH1"
    assert info["created"].startswith("2024-04-25")
    assert info["doc_id"].endswith("0001")
    assert info["description"] == "Method ACAML"


def test_doc_info_omits_absent_fields():
    minimal = ('<ACAML xmlns="urn:schemas-agilent-com:acaml15">'
               '<Doc><DocInfo><CreatedByUser>x</CreatedByUser>'
               '</DocInfo></Doc></ACAML>')
    info = acaml.doc_info(minimal)
    assert info == {"operator": "x"}


def test_sections_nest_under_method_description():
    sections = acaml.sections(METHOD_ACAML)
    assert len(sections) == 1
    acq = sections[0]
    assert acq["name"] == "Acquisition Method"
    assert acq["id"] == "Acquisition_Method"
    # one nested DAD section, which itself holds two sub-sections
    (dad,) = acq["sections"]
    assert dad["name"] == "DAD (G7117B)"
    assert {s["name"] for s in dad["sections"]} == {"Analog Output", "Signals"}


def test_parameter_fields():
    sections = acaml.sections(METHOD_ACAML)
    dad = sections[0]["sections"][0]
    analog = next(s for s in dad["sections"] if s["name"] == "Analog Output")
    (param,) = analog["parameters"]
    assert param == {
        "name": "Analog Zero Offset",
        "id": "AnalogOutput1_AnalogZero",
        "unit": "%",
        "value": "5",
    }


def test_table_rows_are_parsed():
    sections = acaml.sections(METHOD_ACAML)
    dad = sections[0]["sections"][0]
    signals = next(s for s in dad["sections"] if s["name"] == "Signals")
    (table,) = signals["tables"]
    assert table["name"] == "Signal table"
    wavelengths = [row[0]["value"] for row in table["rows"]]
    assert wavelengths == ["254.0", "280.0"]


def test_iter_parameters_is_flat_and_includes_table_rows():
    sections = acaml.sections(METHOD_ACAML)
    params = list(acaml.iter_parameters(sections))
    # one analog parameter + two signal-table rows
    assert len(params) == 3
    assert sum(p["name"] == "Wavelength" for p in params) == 2


def test_index_maps_id_to_parameter():
    sections = acaml.sections(METHOD_ACAML)
    idx = acaml.index(sections)
    assert idx["AnalogOutput1_AnalogZero"]["value"] == "5"
    # duplicate ids (the signal rows) resolve to the last occurrence
    assert idx["Signal_Wavelength"]["value"] == "280.0"


def test_reads_from_a_file_path(tmp_path):
    path = tmp_path / "acq.macaml"
    path.write_text(METHOD_ACAML, encoding="utf-8")
    doc = acaml.read(str(path))
    assert doc["doc_info"]["operator"] == "LAB\\analyst1"
    assert doc["sections"][0]["name"] == "Acquisition Method"


def test_namespace_is_optional():
    # The reader keys on local tag names, so an un-namespaced document (or a
    # future schema version) parses the same way.
    plain = METHOD_ACAML.replace(
        ' xmlns="urn:schemas-agilent-com:acaml15"', "")
    assert acaml.doc_info(plain)["operator"] == "LAB\\analyst1"
    assert acaml.sections(plain)[0]["name"] == "Acquisition Method"
