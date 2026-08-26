"""
Tests for per-injection method/sample sidecar reading (rainbow.agilent.method).

Fixtures are synthetic .D directories holding a small acq.macaml and SAMPLE.XML
written per-test, with invented operators and method paths, so no real
instrument data is needed and the directory-stripping (PII) behavior is
exercised directly.
"""
import os

from rainbow.agilent import method


# A synthetic acquisition method: instrument-module section headers (name +
# model), plus the specific settings the reader distills.
ACQ_MACAML = """<?xml version="1.0" encoding="utf-8"?>
<ACAML xmlns="urn:schemas-agilent-com:acaml15">
  <Doc>
    <DocInfo><CreatedByUser>LAB\\analyst1</CreatedByUser></DocInfo>
    <Content><MethodConfiguration><MethodDescription>
      <Section>
        <Name>Acquisition Method</Name>
        <ID>Acquisition_Method</ID>
        <Section>
          <Name>DAD (G7117B)</Name><ID>G7117B</ID>
        </Section>
        <Section>
          <Name>Column Comp. (G7116B)</Name><ID>G7116B</ID>
          <Section>
            <Name>Left Temperature Control</Name><ID>LeftTemp</ID>
            <Parameter>
              <Name>Temperature</Name><ID>LeftTemp_T</ID>
              <Unit>&#176;C</Unit><Value>40.0</Value>
            </Parameter>
            <Section>
              <Name>Enable Analysis Left Temperature</Name><ID>x</ID>
              <Parameter>
                <Name>Enable Analysis Left Temperature Value</Name><ID>y</ID>
                <Unit>&#176;C</Unit><Value>0.8</Value>
              </Parameter>
            </Section>
          </Section>
        </Section>
        <Section>
          <Name>Multisampler (G7167B)</Name><ID>G7167B</ID>
          <Section>
            <Name>Injection</Name><ID>Injection</ID>
            <Parameter>
              <Name>Injection Volume</Name><ID>Inj_Vol</ID>
              <Unit>&#181;L</Unit><Value>2.50</Value>
            </Parameter>
          </Section>
        </Section>
        <Section>
          <Name>Quat. Pump (G7104A)</Name><ID>G7104A</ID>
          <Parameter>
            <Name>Flow</Name><ID>Flow</ID>
            <Unit>mL/min</Unit><Value>0.700</Value>
          </Parameter>
          <Section>
            <Name>Stoptime</Name><ID>StopTime</ID>
            <Parameter>
              <Name>Stoptime Mode</Name><ID>Mode</ID><Value>Time set</Value>
            </Parameter>
            <Parameter>
              <Name>Stoptime</Name><ID>Stop</ID>
              <Unit>min</Unit><Value>5.00</Value>
            </Parameter>
          </Section>
        </Section>
      </Section>
    </MethodDescription></MethodConfiguration></Content>
  </Doc>
</ACAML>
"""


def _sample_xml(method_path):
    return (
        '<?xml version="1.0"?>\n'
        "<Sample>\n"
        "  <Name>synthetic_sample</Name>\n"
        "  <Amount>0</Amount>\n"
        "  <Multiplier>1</Multiplier>\n"
        "  <Dilution>2</Dilution>\n"
        f"  <ACQMethodPath>{method_path}</ACQMethodPath>\n"
        "</Sample>\n"
    )


def _make_d(tmp_path, acq=ACQ_MACAML, sample=None, encoding="utf-8"):
    """Builds a synthetic .D directory with the given sidecars."""
    d = tmp_path / "synthetic.D"
    d.mkdir()
    if acq is not None:
        (d / "acq.macaml").write_text(acq, encoding="utf-8")
    if sample is not None:
        (d / "SAMPLE.XML").write_bytes(sample.encode(encoding))
    return str(d)


def test_method_settings_are_distilled():
    md = method.parse_injection_metadata(_make_d_tmp())
    assert md["operator"] == "LAB\\analyst1"
    assert md["injection_volume"] == {"value": 2.5, "unit": "µL"}
    assert md["flow_rate"] == {"value": 0.7, "unit": "mL/min"}
    assert md["column_temperature"] == {"value": 40.0, "unit": "°C"}
    assert md["run_time"] == {"value": 5.0, "unit": "min"}


def test_modules_read_from_section_headers():
    md = method.parse_injection_metadata(_make_d_tmp())
    models = {m["name"]: m["model"] for m in md["modules"]}
    assert models == {
        "DAD": "G7117B",
        "Column Comp.": "G7116B",
        "Multisampler": "G7167B",
        "Quat. Pump": "G7104A",
    }


def test_column_temperature_picks_setpoint_not_equilibration_tolerance():
    # The 0.8 degC "enable analysis" tolerance must not be mistaken for the
    # 40.0 degC setpoint.
    md = method.parse_injection_metadata(_make_d_tmp())
    assert md["column_temperature"]["value"] == 40.0


def test_sample_xml_fields(tmp_path):
    d = _make_d(tmp_path, acq=None,
                sample=_sample_xml("C:\\Methods\\my_method.M"))
    md = method.parse_injection_metadata(d)
    assert md["dilution"] == 2
    assert md["multiplier"] == 1
    assert md["sample_amount"] == 0
    assert md["acq_method"] == "my_method.M"


def test_acq_method_strips_directory_which_can_carry_a_name(tmp_path):
    # The directory part of the method path may contain a user's name; only the
    # method file name should survive.
    d = _make_d(tmp_path, acq=None,
                sample=_sample_xml("C:\\Users\\Jane Doe\\Methods\\assay.M"))
    md = method.parse_injection_metadata(d)
    assert md["acq_method"] == "assay.M"
    assert "Jane" not in str(md)


def test_sample_xml_reads_utf16(tmp_path):
    # Real SAMPLE.XML files are UTF-16; the reader must handle that encoding.
    d = _make_d(tmp_path, acq=None,
                sample=_sample_xml("C:\\Methods\\m.M"), encoding="utf-16")
    md = method.parse_injection_metadata(d)
    assert md["dilution"] == 2
    assert md["acq_method"] == "m.M"


def test_missing_sidecars_yield_nothing(tmp_path):
    d = tmp_path / "bare.D"
    d.mkdir()
    assert method.parse_injection_metadata(str(d)) == {}


def test_unreadable_acaml_is_ignored(tmp_path):
    d = _make_d(tmp_path, acq="not xml at all <<<")
    assert method.parse_injection_metadata(d) == {}


def _write_acqmeth(directory, mode):
    """Writes a minimal UTF-16 acqmeth.txt declaring the acquisition mode."""
    text = ("                  MS ACQUISITION PARAMETERS\n\n"
            "General Information\n"
            "------------------\n"
            f"Acquisition Mode         : {mode}\n")
    (directory / "acqmeth.txt").write_bytes(text.encode("utf-16"))


def _ms_file(name, num_ions):
    """A synthetic MS DataFile with ``num_ions`` m/z columns."""
    import numpy as np
    from rainbow.datafile import DataFile
    xlabels = np.arange(5, dtype=float)
    ylabels = np.arange(100, 100 + num_ions, dtype=float)
    data = np.ones((5, num_ions), dtype=np.uint32)
    return DataFile(name, "MS", xlabels, ylabels, data, {})


def test_acquisition_modes_reads_simscan(tmp_path):
    d = tmp_path / "x.D"
    d.mkdir()
    _write_acqmeth(d, "SIM/Scan")  # UTF-16, exercises decode_text
    assert method.acquisition_modes(str(d)) == {"SIM", "Scan"}


def test_acquisition_modes_tolerates_comma_separator(tmp_path):
    d = tmp_path / "x.D"
    d.mkdir()
    _write_acqmeth(d, "SIM, Scan")  # comma form must not be read as Scan-only
    assert method.acquisition_modes(str(d)) == {"SIM", "Scan"}


def test_acquisition_modes_reads_spelled_out_sim(tmp_path):
    d = tmp_path / "x.D"
    d.mkdir()
    _write_acqmeth(d, "Selected Ion Monitoring")  # spelled-out form
    assert method.acquisition_modes(str(d)) == {"SIM"}


def test_acquisition_modes_missing_report_is_none(tmp_path):
    d = tmp_path / "x.D"
    d.mkdir()
    assert method.acquisition_modes(str(d)) is None


def test_tag_acquisition_modes_splits_a_simultaneous_run(tmp_path):
    # A SIM/Scan run: the *SIM*.ms file is the monitored ions, the other the
    # full scan. The mode comes from the method, not the column counts.
    d = tmp_path / "x.D"
    d.mkdir()
    _write_acqmeth(d, "SIM/Scan")
    scan = _ms_file("data.ms", 50)
    sim = _ms_file("dataSim.ms", 2)
    method.tag_acquisition_modes(str(d), [scan, sim])
    assert scan.metadata["acquisition_mode"] == "Scan"
    assert sim.metadata["acquisition_mode"] == "SIM"


def test_tag_acquisition_modes_pure_sim_method_tags_multi_ion(tmp_path):
    # A pure-SIM method tags even a multi-column channel SIM, from the method
    # alone (not the single-ion fallback).
    d = tmp_path / "x.D"
    d.mkdir()
    _write_acqmeth(d, "SIM")
    sim = _ms_file("data.ms", 4)
    method.tag_acquisition_modes(str(d), [sim])
    assert sim.metadata["acquisition_mode"] == "SIM"


def test_acquisition_technique_reads_gc_from_sample_inlet(tmp_path):
    # The separation technique is read from the method's "Sample Inlet" line,
    # not inferred from the detectors.
    d = tmp_path / "x.D"
    d.mkdir()
    text = ("              INSTRUMENT CONTROL PARAMETERS:    5977B GCMS\n\n"
            "Sample Inlet             : GC\n"
            "Injection Source         : GC ALS\n")
    (d / "acqmeth.txt").write_bytes(text.encode("utf-16"))
    assert method.acquisition_technique(str(d)) == "GC"


def test_acquisition_technique_reads_lc_from_sample_inlet(tmp_path):
    d = tmp_path / "x.D"
    d.mkdir()
    (d / "acqmeth.txt").write_bytes(
        "Sample Inlet             : LC\n".encode("utf-16"))
    assert method.acquisition_technique(str(d)) == "LC"


def test_acquisition_technique_missing_report_is_none(tmp_path):
    d = tmp_path / "x.D"
    d.mkdir()
    assert method.acquisition_technique(str(d)) is None


def test_acquisition_technique_falls_back_to_gcms_descriptor(tmp_path):
    # With no "Sample Inlet" line, a GC/MS instrument descriptor still marks the
    # run gas chromatography.
    d = tmp_path / "x.D"
    d.mkdir()
    (d / "acqmeth.txt").write_bytes(
        "   INSTRUMENT CONTROL PARAMETERS:  5977B GCMS\n".encode("utf-16"))
    assert method.acquisition_technique(str(d)) == "GC"


def test_acquisition_technique_ignores_gc_in_the_method_path(tmp_path):
    # The fallback reads only the banner line the instrument names itself on.
    # In the real report layout the method path is the fourth line, so a window
    # even a line or two wider takes an LC run filed under a GC-named folder for
    # gas chromatography, which downgrades every UV detector class downstream.
    d = tmp_path / "x.D"
    d.mkdir()
    text = ("                  INSTRUMENT CONTROL PARAMETERS:    1290 Infinity II\n"
            "                  --------------------------------------------\n"
            "\n"
            "   C:\\Chem32\\1\\METHODS\\porting-from-GCMS\\assay.M\n"
            "      Tue Dec 17 10:13:52 2019\n")
    (d / "acqmeth.txt").write_bytes(text.encode("utf-16"))
    assert method.acquisition_technique(str(d)) is None


def test_acquisition_technique_reads_the_banner_in_the_real_layout(tmp_path):
    # The positive case in the same layout: the rule, blank line and path that
    # follow the banner do not stop the instrument's own claim being read.
    d = tmp_path / "x.D"
    d.mkdir()
    text = ("                  INSTRUMENT CONTROL PARAMETERS:    5977B GCMS\n"
            "                  --------------------------------------------\n"
            "\n"
            "   D:\\MassHunter\\Methods\\assay.M\n")
    (d / "acqmeth.txt").write_bytes(text.encode("utf-16"))
    assert method.acquisition_technique(str(d)) == "GC"


def test_tag_acquisition_modes_single_ion_is_sim_without_a_report(tmp_path):
    # With no method report, a single-ion channel is still SIM, but a
    # multi-column grid is left untagged (the exporter then treats it as scan).
    d = tmp_path / "x.D"
    d.mkdir()
    sim = _ms_file("MSD1.MS", 1)
    scan = _ms_file("MSD2.MS", 80)
    method.tag_acquisition_modes(str(d), [sim, scan])
    assert sim.metadata["acquisition_mode"] == "SIM"
    assert "acquisition_mode" not in scan.metadata


# Shared synthetic .D for the read-only tests, built once under a temp dir.
_D_TMP = None


def _make_d_tmp():
    global _D_TMP
    if _D_TMP is None:
        import tempfile
        base = tempfile.mkdtemp()
        d = os.path.join(base, "synthetic.D")
        os.mkdir(d)
        with open(os.path.join(d, "acq.macaml"), "w", encoding="utf-8") as f:
            f.write(ACQ_MACAML)
        with open(os.path.join(d, "SAMPLE.XML"), "wb") as f:
            f.write(_sample_xml("C:\\Methods\\m.M").encode("utf-16"))
        _D_TMP = d
    return _D_TMP
