"""
Unit tests for the public ``rainbow.debug`` metadata API: ``inspect`` (faithful
per-file structure) and ``fields`` (one merged canonical run record), plus the
merge policy, provenance map, path validation, and error-isolation behavior.

The assertions deliberately avoid pinning specific identifier *values* (those
live in the fixtures and are vendor data); they pin shapes, types, and invariants
that the API contract guarantees.
"""
import os

import pytest

import rainbow as rb
from rainbow import debug

# red.D carries a rich spread of recognized sidecars (INI, XML, ChemStation
# text/header, RUN.LOG, .REG, methods) and is the main positive fixture.
RICH = os.path.join("tests", "inputs", "red.D")
# An Agilent HRMS run whose only metadata is numeric calibration XML, so it is
# recognized-but-carries-no-identity: fields() should come back empty.
HRMS = os.path.join("tests", "inputs", "amber.D")
# A Waters .raw whose _header.txt is fully synthetic (TEST_SAMPLE_001), so its
# values are safe to assert on. Its instrument has no serial and its sample/
# operator/method fields are blank, exercising the omit-blanks path. Note the
# lowercase _header.txt, which the case-insensitive matcher must still catch.
WATERS = os.path.join("tests", "inputs", "turquoise.raw")
RAW_FIXTURES = ["blue.raw", "indigo.raw", "turquoise.raw", "violet.raw",
                "white.raw"]
# An Agilent OpenLab .dx archive (a "standby flush" run): its GUID-named .CH/.UV
# signal payloads carry ChemStation identity headers. Values come from an Agilent
# installation flush, not a sample, so they are safe to reason about.
DX = os.path.join("tests", "inputs", "teal.dx")
# A sanitized .D holding the ChemStation report/state sidecars (report.txt,
# report00.csv, acq_methhist.txt, scstate.txt) and an MS .tune. Every value is
# fabricated (the real files live only in the untracked data/ corpus), so the
# canonical values are safe to assert on exactly.
NAVY = os.path.join("tests", "inputs", "navy.D")


def test_public_api_surface():
    # The submodule is exported from the package, alongside agilent/waters.
    assert hasattr(rb, "debug")
    assert callable(rb.debug.inspect) and callable(rb.debug.fields)
    assert debug.__all__ == ["inspect", "fields"]


# --- inspect ---------------------------------------------------------------

def test_inspect_returns_per_file_structure():
    out = rb.debug.inspect(RICH)
    assert isinstance(out, dict) and out
    # Keyed by relpath; every value is a parsed dict carrying a 'parser' tag.
    for rel, parsed in out.items():
        assert isinstance(rel, str)
        assert isinstance(parsed, dict)
        assert "parser" in parsed
    # No '_sources' key leaks into the lossless per-file view.
    assert "_sources" not in out
    # A clean fixture parses without any per-file errors.
    assert not any("error" in parsed for parsed in out.values())


def test_inspect_accepts_a_single_file():
    out = rb.debug.inspect(os.path.join(RICH, "RUN.LOG"))
    assert list(out) == ["RUN.LOG"]
    assert out["RUN.LOG"]["parser"] == "chemstation_text"


def test_inspect_skips_unrecognized_files(tmp_path):
    (tmp_path / "notes.txt.unknown").write_text("nothing here")
    assert rb.debug.inspect(str(tmp_path)) == {}


# --- fields ----------------------------------------------------------------

def test_fields_returns_canonical_record_with_sources():
    rec = rb.debug.fields(RICH)
    assert isinstance(rec, dict) and rec
    assert "_sources" in rec
    # Every non-_sources field is provenance-tracked.
    for key in rec:
        if key != "_sources":
            assert key in rec["_sources"]


def test_fields_list_accumulates_scalar_first_wins():
    rec = rb.debug.fields(RICH)
    # 'serials' is a list field: a run legitimately has several.
    assert isinstance(rec["serials"], list) and len(rec["serials"]) >= 1
    assert len(rec["serials"]) == len(set(rec["serials"]))  # de-duplicated
    # 'method' is a scalar field: one value.
    assert isinstance(rec["method"], str)


def test_sources_shape_matches_field_kind():
    rec = rb.debug.fields(RICH)
    src = rec["_sources"]
    # A list field records a list of contributing relpaths (one per value)...
    assert isinstance(src["serials"], list)
    assert len(src["serials"]) == len(rec["serials"])
    # ...a scalar field records the single relpath that supplied it.
    assert isinstance(src["method"], str)


def test_hrms_dir_has_no_identity_fields():
    # Recognized sidecars but no identifiers -> an empty record (and thus no
    # _sources), not a crash.
    assert rb.debug.fields(HRMS) == {}


def test_fields_on_unrecognized_dir_is_empty(tmp_path):
    (tmp_path / "random.dat").write_bytes(b"\x00\x01\x02")
    assert rb.debug.fields(str(tmp_path)) == {}


# --- validation ------------------------------------------------------------

@pytest.mark.parametrize("entry", [debug.inspect, debug.fields])
@pytest.mark.parametrize("bad", [
    os.path.join("tests", "inputs", "does_not_exist"),
    None,
    42,
])
def test_entry_points_reject_bad_paths(entry, bad):
    with pytest.raises(Exception):
        entry(bad)


# --- error isolation -------------------------------------------------------

def test_parse_error_is_reported_not_raised(tmp_path, monkeypatch):
    # A sidecar whose parser blows up must be reported in inspect (not abort the
    # whole walk) and simply skipped by fields.
    (tmp_path / "broken.ini").write_text("[x]\nk=v\n")

    def boom(_path):
        raise ValueError("synthetic parse failure")

    monkeypatch.setattr(debug.ini, "parse", boom)

    out = rb.debug.inspect(str(tmp_path))
    assert out["broken.ini"]["parser"] == "ini"
    assert "error" in out["broken.ini"]

    # fields swallows the failure and, with nothing else to contribute, is empty.
    assert rb.debug.fields(str(tmp_path)) == {}


# --- Waters _HEADER.TXT ----------------------------------------------------

def _write_header(tmp_path, lines):
    """Writes a synthetic Waters _HEADER.TXT from a list of ``Key: Value``
    strings and returns the directory path."""
    body = "".join("$$ %s\r\n" % ln for ln in lines)
    (tmp_path / "_HEADER.TXT").write_text(body)
    return str(tmp_path)


def test_waters_header_registered_and_matches():
    assert debug.waters_header in debug._PARSERS
    assert debug.waters_header.matches("_HEADER.TXT")
    assert debug.waters_header.matches("_header.txt")  # case-insensitive
    assert not debug.waters_header.matches("_FUNCTNS.INF")


def test_waters_raw_yields_canonical_identity():
    # Regression guard for the Waters blind spot: a .raw must no longer be empty.
    rec = rb.debug.fields(WATERS)
    assert rec  # not {}
    # Synthetic values, safe to pin exactly.
    assert rec["instrument"] == "GCMS"
    assert rec["data_file"] == "TEST_SAMPLE_001"
    assert rec["sample_id"] == "TEST_SAMPLE_001"
    assert rec["acquired"] == "01-JAN-2020 12:00:00"  # date + time joined
    assert rec["vialpos"] == "5"
    # Blank header keys (User Name, Sample Description, Instrument w/o '#') must
    # NOT appear as empty canonical fields.
    for absent in ("serials", "operator", "sample"):
        assert absent not in rec
    # turquoise also ships inlet.inf (the GC run-log variant), which supplies the
    # method the _HEADER.TXT lacks. Assert it is surfaced and provenance points at
    # inlet.inf; the value itself is vendor data, so it is not pinned here.
    assert rec.get("method")
    assert rec["_sources"]["method"].lower() == "inlet.inf"
    # Provenance for the header-sourced field points at the (lowercase) header.
    assert rec["_sources"]["instrument"].lower() == "_header.txt"


def test_waters_inspect_tags_the_header():
    out = rb.debug.inspect(WATERS)
    rel = next(r for r in out if r.lower() == "_header.txt")
    parsed = out[rel]
    assert parsed["parser"] == "waters_header"
    # Lossless: blank keys are preserved in parse() even though canonical drops
    # them, and the numeric Cal lines are kept verbatim, not promoted.
    assert parsed["header"]["User Name"] == ""
    assert "Cal MS1 Static" in parsed["header"]


def test_waters_instrument_serial_split(tmp_path):
    d = _write_header(tmp_path, ["Instrument: ACQ-SQD2#ABC1234"])
    rec = rb.debug.fields(d)
    assert rec["instrument"] == "ACQ-SQD2"
    assert rec["serials"] == ["ABC1234"]


def test_waters_notset_serial_is_dropped(tmp_path):
    d = _write_header(tmp_path, ["Instrument: ACQ-QDA#NotSet"])
    rec = rb.debug.fields(d)
    assert rec["instrument"] == "ACQ-QDA"
    assert "serials" not in rec  # NotSet placeholder is not a serial


def test_waters_first_colon_split_preserves_paths(tmp_path):
    # A method path (C:\...) and a clock value must survive the key/value split.
    d = _write_header(tmp_path, [
        r"MS Method: C:\MassLynx\Default.PRO\ACQUDB\8min.EXP",
        "Acquired Time: 00:11:45",
        "Acquired Date: 26-Jan-2024",
    ])
    rec = rb.debug.fields(d)
    assert rec["method"] == r"C:\MassLynx\Default.PRO\ACQUDB\8min.EXP"
    assert rec["acquired"] == "26-Jan-2024 00:11:45"


def test_waters_method_prefers_ms_over_inlet(tmp_path):
    d = _write_header(tmp_path, [
        r"Inlet Method: C:\inlet.exp",
        r"MS Method: C:\ms.exp",
    ])
    assert rb.debug.fields(d)["method"] == r"C:\ms.exp"


def test_waters_header_without_instrument_key(tmp_path):
    # A header missing Instrument must omit instrument/serials, not crash.
    d = _write_header(tmp_path, ["Acquired Name: RUN", "SampleID: S1"])
    rec = rb.debug.fields(d)
    assert "instrument" not in rec and "serials" not in rec
    assert rec["data_file"] == "RUN" and rec["sample_id"] == "S1"


def test_waters_header_utf16(tmp_path):
    # Real .raw headers are frequently UTF-16; decode_text must handle it.
    body = "".join("$$ %s\r\n" % ln for ln in
                   ["Instrument: ACQ-SQD2#ABC1234", "Acquired Name: RUN16"])
    (tmp_path / "_HEADER.TXT").write_bytes(body.encode("utf-16"))
    rec = rb.debug.fields(str(tmp_path))
    assert rec["instrument"] == "ACQ-SQD2"
    assert rec["serials"] == ["ABC1234"]
    assert rec["data_file"] == "RUN16"


@pytest.mark.parametrize("raw", RAW_FIXTURES)
def test_every_raw_fixture_is_nonempty(raw):
    # Shape-only (no values): every committed Waters run now surfaces identity.
    rec = rb.debug.fields(os.path.join("tests", "inputs", raw))
    assert rec and "instrument" in rec
    assert "_sources" in rec


# --- Agilent .drvml (driver results) ---------------------------------------

_DRVML = """<?xml version="1.0"?>
<AnalyticalResultsModuleData xmlns="file://GenericAnalyticalResultData.xsd"
    ModuleId="{mid}" SchemaVersion="1.0.0">
  <ModuleInfo>
    <SerialNumber>{serial}</SerialNumber>
    <PartNumber>{part}</PartNumber>
    <FirmwareRevision>B.07.33 [0003]</FirmwareRevision>
    <Vendor>Agilent</Vendor>
    <DisplayName>{name}</DisplayName>
  </ModuleInfo>
  <DataChannels/>
</AnalyticalResultsModuleData>
"""


def _write_drvml(path, mid, serial, part, name):
    path.write_text(_DRVML.format(mid=mid, serial=serial, part=part, name=name))


def test_drvml_is_matched_by_xml_parser():
    # The extension was the whole gap: parse() always worked, but .drvml was
    # never claimed, so it never reached canonical().
    assert debug.xml.matches("PMP1.AnalyticalResults.drvml")
    assert debug._dispatch("PMP1.AnalyticalResults.drvml") is debug.xml


def test_drvml_canonical_extracts_module(tmp_path):
    f = tmp_path / "PMP1.AnalyticalResults.drvml"
    _write_drvml(f, "PMP1", "DEAA900001", "G7120A", "Binary Pump")
    parsed = debug.xml.parse(str(f))
    assert parsed["root"] == "AnalyticalResultsModuleData"
    out = debug.xml.canonical(parsed)
    assert out["serials"] == ["DEAA900001"]
    assert out["devices"] == [{
        "Name": "Binary Pump",
        "ModelNumber": "G7120A",
        "SerialNumber": "DEAA900001",
        "FirmwareVersion": "B.07.33 [0003]",
        "Vendor": "Agilent",
    }]


def test_drvml_fields_accumulate_across_modules(tmp_path):
    _write_drvml(tmp_path / "PMP1.AnalyticalResults.drvml",
                 "PMP1", "DEAA900001", "G7120A", "Binary Pump")
    _write_drvml(tmp_path / "DAD1.AnalyticalResults.drvml",
                 "DAD1", "DEAA900002", "G7117A", "Diode Array Detector")
    rec = rb.debug.fields(str(tmp_path))
    assert sorted(rec["serials"]) == ["DEAA900001", "DEAA900002"]
    assert len(rec["devices"]) == 2
    # provenance lists one relpath per accumulated serial
    assert len(rec["_sources"]["serials"]) == 2


def test_drvml_placeholder_serial_dropped(tmp_path):
    f = tmp_path / "FID.AnalyticalResults.drvml"
    _write_drvml(f, "FID", "1", "G3431A", "Flame Ionization Detector")
    out = debug.xml.canonical(debug.xml.parse(str(f)))
    assert "serials" not in out          # "1" is a placeholder, not a unit
    assert out["devices"][0]["ModelNumber"] == "G3431A"  # device still recorded


def test_drvml_without_moduleinfo_contributes_nothing(tmp_path):
    # A .drvml with no ModuleInfo must yield {} from canonical, not raise.
    f = tmp_path / "X.AnalyticalResults.drvml"
    f.write_text('<?xml version="1.0"?>\n'
                 '<AnalyticalResultsModuleData xmlns="file://G.xsd">'
                 '<DataChannels/></AnalyticalResultsModuleData>')
    assert debug.xml.canonical(debug.xml.parse(str(f))) == {}


# --- mzXML (open format) ---------------------------------------------------

# A parentFile placed AFTER the first <scan>: parse() reads parentFile elements,
# so if the streaming read did not stop at the first scan this would surface in
# parsed['parent_files']. Its absence is what proves the header-only break works
# (the read never advances past the scan data). A peak sentinel guards the
# weaker claim that scan text is not captured.
_AFTER_SCAN_SENTINEL = "file:///AFTER_SCAN_MUST_NOT_BE_READ.raw"
_PEAK_SENTINEL = "SCANPEAKSMUSTNOTBEREAD"

_MZXML = """<?xml version="1.0" encoding="utf-8"?>
<mzXML xmlns="http://sashimi.sourceforge.net/schema_revision/mzXML_3.2">
  <msRun scanCount="2" startTime="PT0.1S" endTime="PT1.0S">
    <parentFile fileName="{parent}"/>
    <msInstrument msInstrumentID="1">
      <msManufacturer category="msManufacturer" value="Agilent"/>
      <msModel category="msModel" value="6470 QQQ"/>
      <msIonisation category="msIonisation" value="Esi"/>
      <software type="acquisition" name="MassHunter Data Acquisition" version="8.0"/>
    </msInstrument>
    <dataProcessing>
      <software type="conversion" name="ProteoWizard" version="3.0"/>
    </dataProcessing>
    <scan num="1" peaksCount="1">
      <peaks compressionType="none">{peak}</peaks>
    </scan>
    <parentFile fileName="{after}"/>
    <scan num="2" peaksCount="1"><peaks>{peak}</peaks></scan>
  </msRun>
</mzXML>
"""


def _write_mzxml(tmp_path, parent):
    f = tmp_path / "run.mzXML"
    f.write_text(_MZXML.format(parent=parent, peak=_PEAK_SENTINEL,
                               after=_AFTER_SCAN_SENTINEL))
    return str(f)


def test_mzxml_routing_not_to_generic_xml():
    # .mzXML ends with .xml, so the generic xml parser must explicitly decline it
    # (it would otherwise build the whole multi-MB scan tree).
    assert debug.mzxml.matches("run.mzXML")
    assert not debug.xml.matches("run.mzXML")
    assert debug._dispatch("run.mzXML") is debug.mzxml


def test_mzxml_parse_is_header_only(tmp_path):
    f = _write_mzxml(tmp_path, "file:///C:/Data/op/RUN_001.d/AcqData/MSProfile.bin")
    parsed = debug.mzxml.parse(f)
    assert parsed["parser"] == "mzxml"
    assert parsed["msRun"]["scanCount"] == "2"
    assert parsed["instrument"]["msModel"] == "6470 QQQ"
    assert {s["type"] for s in parsed["software"]} == {"acquisition", "conversion"}
    # The streaming read stopped at the first <scan>: the parentFile placed AFTER
    # that scan (which parse() WOULD otherwise capture) is absent. This fails if
    # the `if tag == "scan": break` is removed - the weaker peak-text check below
    # would not.
    assert _AFTER_SCAN_SENTINEL not in parsed["parent_files"]
    assert parsed["parent_files"] == [
        "file:///C:/Data/op/RUN_001.d/AcqData/MSProfile.bin"]
    assert _PEAK_SENTINEL not in repr(parsed)


def test_mzxml_canonical_fields(tmp_path):
    f = _write_mzxml(tmp_path, "file:///C:/Data/op/RUN_001.d/AcqData/MSProfile.bin")
    out = debug.mzxml.canonical(debug.mzxml.parse(f))
    assert out["instrument"] == "6470 QQQ"               # model preferred
    assert out["software_version"] == "MassHunter Data Acquisition 8.0"  # acq preferred
    assert out["data_file"] == "C:/Data/op/RUN_001.d"    # source run, tail trimmed


def test_mzxml_datafile_handles_raw_and_plain(tmp_path):
    # a Waters-style .raw parentFile
    out = debug.mzxml.canonical(debug.mzxml.parse(
        _write_mzxml(tmp_path, "file:///D:/x/SAMPLE.raw/_FUNC001.DAT")))
    assert out["data_file"] == "D:/x/SAMPLE.raw"
    # a parentFile with no .d/.raw component falls back to the bare path
    out2 = debug.mzxml.canonical(debug.mzxml.parse(
        _write_mzxml(tmp_path, "file:///srv/exports/blob.bin")))
    assert out2["data_file"] == "srv/exports/blob.bin"


def test_mzxml_fields_via_public_api(tmp_path):
    _write_mzxml(tmp_path, "file:///C:/Data/op/RUN_001.d/AcqData/MSProfile.bin")
    rec = rb.debug.fields(str(tmp_path))
    assert rec["instrument"] == "6470 QQQ"
    assert rec["_sources"]["data_file"] == "run.mzXML"


# --- empty XML (benign placeholders) ---------------------------------------

def test_empty_xml_reported_as_empty_not_malformed(tmp_path):
    # Agilent writes 0-byte TimeStamp.xml files; they must be distinguished from
    # genuinely corrupt XML, not crash, and not pollute fields().
    (tmp_path / "TimeStamp.xml").write_bytes(b"")
    (tmp_path / "whitespace.xml").write_bytes(b"  \r\n\t ")
    out = rb.debug.inspect(str(tmp_path))
    assert out["TimeStamp.xml"] == {"parser": "xml", "error": "empty file"}
    assert out["whitespace.xml"]["error"] == "empty file"
    # A non-empty but malformed doc still reports the distinct malformed error.
    (tmp_path / "bad.xml").write_bytes(b"\x00\x01 not xml <<<")
    out2 = rb.debug.inspect(str(tmp_path))
    assert out2["bad.xml"]["error"] == "unparseable XML"
    # Error entries never reach fields().
    assert rb.debug.fields(str(tmp_path)) == {}


# --- Agilent .dx archive descent ------------------------------------------

def test_dx_inspect_descends_into_archive_members():
    # A .dx is an OPC zip; the walker steps in and reports members as
    # "<archive>!<member>", routing the signal payloads to chemstation_header.
    out = rb.debug.inspect(DX)
    assert out  # not empty - the whole point: a .dx was opaque before
    assert all("teal.dx!" in rel for rel in out)
    headered = [r for r in out if out[r]["parser"] == "chemstation_header"]
    assert headered  # the .CH/.UV payloads were decoded
    assert not any("error" in parsed for parsed in out.values())
    # OPC packaging parts carry no identity and are skipped (not surfaced as
    # boilerplate noise, and not an error surface).
    assert not any(rel.lower().endswith("[content_types].xml") for rel in out)
    assert not any("_rels/" in rel.lower() for rel in out)


def test_dx_does_not_reparse_the_manifest():
    # Anti-duplication guard: injection.acmd is rb.read's territory (it routes
    # the data and supplies sample/method-basename/vialpos). debug must NOT also
    # parse it - debug only mines the per-signal headers rb.read drops.
    out = rb.debug.inspect(DX)
    assert not any(rel.lower().endswith("injection.acmd") for rel in out)


def test_dx_fields_surface_header_identity():
    # The closed gap: fields() now yields the identity from the signal headers.
    rec = rb.debug.fields(DX)
    assert rec
    assert rec["operator"]                      # carried in every .CH/.UV header
    assert "\\" in rec["method"] or "/" in rec["method"]   # a full method path
    assert isinstance(rec["signal_optics"], list) and rec["signal_optics"]
    # provenance points back inside the archive
    assert "teal.dx!" in rec["_sources"]["operator"]


def test_dx_as_member_of_a_scanned_directory(tmp_path):
    # A .dx found during a normal directory walk is descended into too, not
    # treated as one opaque file.
    import shutil
    sub = tmp_path / "run"
    sub.mkdir()
    shutil.copy(DX, sub / "teal.dx")
    out = rb.debug.inspect(str(tmp_path))
    assert any("teal.dx!" in rel for rel in out)


def test_non_dx_zip_is_not_descended(tmp_path):
    # Only .dx archives are containers; an arbitrary .zip is just an unrecognized
    # file, not walked into.
    import zipfile
    z = tmp_path / "bundle.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("_HEADER.TXT", "$$ Instrument: ACQ#ABC1234\r\n")
    assert rb.debug.inspect(str(tmp_path)) == {}


def test_corrupt_dx_does_not_crash(tmp_path):
    # A .dx that is not a valid zip is skipped, not raised.
    bad = tmp_path / "broken.dx"
    bad.write_bytes(b"PK\x03\x04 not really a zip")
    assert rb.debug.inspect(str(tmp_path)) == {}
    assert rb.debug.fields(str(tmp_path)) == {}


# --- Waters _INLET.INF / _extern.inf ---------------------------------------

def test_waters_inf_registered_and_matches():
    assert debug.waters_inf in debug._PARSERS
    assert debug.waters_inf.matches("_INLET.INF")
    assert debug.waters_inf.matches("_extern.inf")
    assert debug.waters_inf.matches("_inlet.inf")  # case-insensitive
    # Must NOT poach _HEADER.TXT (waters_header's) or the numeric INF sidecars.
    assert not debug.waters_inf.matches("_HEADER.TXT")
    assert not debug.waters_inf.matches("_FUNCTNS.INF")
    assert not debug.waters_inf.matches("_HISTORY.INF")


def test_waters_inlet_method_path(tmp_path):
    (tmp_path / "_INLET.INF").write_text(
        "ACE Experimental Record\r\n"
        r"Inlet Method File: c:\masslynx\PROJECT01.pro\acqudb\screen_5min" "\r\n"
        "-- PUMP --\r\nWaters GI Pump\r\n")
    out = debug.waters_inf.canonical(
        debug.waters_inf.parse(str(tmp_path / "_INLET.INF")))
    assert out == {"method": r"c:\masslynx\PROJECT01.pro\acqudb\screen_5min"}


def test_waters_extern_promotes_path_only(tmp_path):
    # A path-like target is promoted...
    f = tmp_path / "_extern.inf"
    f.write_text(r"Parameters for C:\MassLynx\PROJECT02.PRO\ACQUDB\MS_POS.EXP" "\r\n"
                 "Prescan Statistics:\r\n")
    assert debug.waters_inf.canonical(debug.waters_inf.parse(str(f))) == {
        "method": r"C:\MassLynx\PROJECT02.PRO\ACQUDB\MS_POS.EXP"}
    # ...but a bare label is left in the lossless body, not mis-promoted.
    f.write_text("Parameters for test\r\nPolarity\tEI+\r\n")
    parsed = debug.waters_inf.parse(str(f))
    assert debug.waters_inf.canonical(parsed) == {}
    assert "Parameters for test" in parsed["lines"]


def test_waters_extern_utf16(tmp_path):
    # _extern.inf is sometimes UTF-16 (the parse relies on decode_text); lock in
    # that a UTF-16 method path still decodes and promotes.
    f = tmp_path / "_extern.inf"
    body = (r"Parameters for C:\MassLynx\PROJECT02.PRO\ACQUDB\MS_POS.EXP" "\r\n"
            "Tune method name:\tDefault\r\n")
    f.write_bytes(body.encode("utf-16"))
    out = debug.waters_inf.canonical(debug.waters_inf.parse(str(f)))
    assert out == {"method": r"C:\MassLynx\PROJECT02.PRO\ACQUDB\MS_POS.EXP"}


def test_waters_inf_numbered_copy_matched(tmp_path):
    # MassLynx writes _extern(1).inf / _inlet(2).inf when a .raw is re-acquired
    # in place; the copy carries the same method identity and must be claimed.
    assert debug.waters_inf.matches("_extern(1).inf")
    assert debug.waters_inf.matches("_INLET(2).INF")  # case-insensitive
    assert debug._dispatch("_extern(1).inf") is debug.waters_inf
    # The (N) must sit right before .inf; a stray paren elsewhere is not a copy.
    assert not debug.waters_inf.matches("_extern(1).txt")
    assert not debug.waters_inf.matches("_functns(1).inf")
    f = tmp_path / "_extern(1).inf"
    f.write_text(r"Parameters for C:\MassLynx\PROJECT02.PRO\ACQUDB\MS_POS.EXP" "\r\n"
                 "Prescan Statistics:\r\n")
    parsed = debug.waters_inf.parse(str(f))
    assert parsed["kind"] == "extern"
    assert debug.waters_inf.canonical(parsed) == {
        "method": r"C:\MassLynx\PROJECT02.PRO\ACQUDB\MS_POS.EXP"}


def test_waters_inf_lossless_keeps_body(tmp_path):
    f = tmp_path / "_INLET.INF"
    f.write_text(r"Inlet Method File: c:\x.m" "\r\n-- PUMP --\r\n"
                 " Solvent A Name: Acetonitrile\r\n")
    parsed = debug.waters_inf.parse(str(f))
    assert parsed["kind"] == "inlet"
    assert " Solvent A Name: Acetonitrile".strip() in [l.strip()
                                                        for l in parsed["lines"]]


def test_waters_inf_real_fixtures_carry_method():
    # blue.raw (_INLET.INF) and indigo.raw (_extern.inf) both name a project path.
    for raw, needle in [("blue.raw", "inlet"), ("indigo.raw", "extern")]:
        out = rb.debug.inspect(os.path.join("tests", "inputs", raw))
        inf = {r: v for r, v in out.items() if v["parser"] == "waters_inf"}
        assert inf, raw
        assert any(v["kind"] == needle for v in inf.values())


# --- ChemStation Audit.txt / method.txt ------------------------------------

_METHOD_M = os.path.join(
    "tests", "inputs", "yellow.D", "AcqData",
    "HP-5MS_HTAchiral_da_100-300_simscan.M")


def test_audit_txt_is_inspect_only_with_events():
    f = os.path.join(_METHOD_M, "Audit.txt")
    parsed = debug.chemstation_text.parse(f)
    assert parsed["kind"] == "audit"
    assert parsed["events"]  # the save-event records were captured
    first = parsed["events"][0]
    assert set(first) <= {"modified", "event", "message", "why", "severity"}
    # Forensic-only: no clean canonical identifier is promoted.
    assert debug.chemstation_text.canonical(parsed) == {}
    # ...but the trail is now visible in inspect(), where it was opaque before.
    out = rb.debug.inspect(os.path.join("tests", "inputs", "yellow.D"))
    assert any(r.endswith("Audit.txt") for r in out)


def test_method_txt_promotes_method_path():
    f = os.path.join(_METHOD_M, "method.txt")
    parsed = debug.chemstation_text.parse(f)
    assert parsed["kind"] == "method_info"
    out = debug.chemstation_text.canonical(parsed)
    assert out["method"].lower().endswith(".m")


def test_audit_and_method_txt_matched():
    assert debug.chemstation_text.matches("Audit.txt")
    assert debug.chemstation_text.matches("method.txt")
    assert debug._dispatch("Audit.txt") is debug.chemstation_text


def test_audit_record_boundary(tmp_path):
    # Two records: a new event begins at each "Modified"; fields stay grouped.
    (tmp_path / "Audit.txt").write_text(
        "D:\\m\\default.m\\Audit.txt\r\n"
        "Created Tue Sep 20 19:17:52 2016\r\n"
        " Modified : Tue Sep 20 19:17:52 2016\r\n"
        " Event    : Save Method\r\n"
        " Message  : Save Method to D:\\m\\INCH\\IC_Default.m\r\n"
        " Why      : Reason : free-text with a spaced colon\r\n"
        " Modified : Tue Sep 20 19:26:56 2016\r\n"
        " Event    : Edit Method\r\n")
    parsed = debug.chemstation_text.parse(str(tmp_path / "Audit.txt"))
    assert parsed["created"] == "Tue Sep 20 19:17:52 2016"
    assert len(parsed["events"]) == 2
    assert parsed["events"][0]["event"] == "Save Method"
    assert parsed["events"][1]["event"] == "Edit Method"
    # The message path with embedded colons (drive colon, no following space)
    # survives the key/value split...
    assert parsed["events"][0]["message"].endswith("IC_Default.m")
    # ...and a value that itself contains " : " keeps its remainder (the key is
    # split at the first ": " only).
    assert parsed["events"][0]["why"] == "Reason : free-text with a spaced colon"


# --- ChemStation MSPARMS.txt ------------------------------------------------

# Synthetic MSD parameter report: a labeled identity header over a numeric body.
# Values are fake (no real operator/host) so they are safe to assert on.
_MSPARMS = (
    "This data was acquired in Method&Run Control.\r\n"
    "\r\n"
    "File                     :   C:\\Chem32\\1\\DATA\\DEMO\\002-0101.D\r\n"
    "Operator                 :   Alex Sampleton\r\n"
    "Date acquired            :   Thu Nov 14 15:11:33 2019\r\n"
    "Instrument               :   LCMS_0-001A\r\n"
    "Tune File                :   C:\\Chem32\\1\\6140ATUN\\atunes.tun\r\n"
    "\r\n"
    "Sample information\r\n"
    "----------------------------------\r\n"
    "Sample name              :   blank\r\n"
    "\r\n"
    "MS parameters - Positive\r\n"
    "----------------------------------\r\n"
    "Skim1                    :    35 V\r\n"
    "                            118.09       :   -247\r\n")


def test_msparms_registered_and_matched():
    assert debug.chemstation_text.matches("MSPARMS.txt")
    assert debug.chemstation_text.matches("msparms.txt")  # case-insensitive
    assert debug._dispatch("MSPARMS.txt") is debug.chemstation_text


def test_msparms_canonical_header_fields(tmp_path):
    f = tmp_path / "MSPARMS.txt"
    f.write_text(_MSPARMS)
    parsed = debug.chemstation_text.parse(str(f))
    assert parsed["kind"] == "msparms"
    out = debug.chemstation_text.canonical(parsed)
    assert out == {
        "data_file": r"C:\Chem32\1\DATA\DEMO\002-0101.D",
        "operator": "Alex Sampleton",
        "acquired": "Thu Nov 14 15:11:33 2019",
        "instrument": "LCMS_0-001A",
        "sample": "blank",
    }


def test_msparms_numeric_body_is_lossless_not_mined(tmp_path):
    # The MS-parameter body is kept verbatim for inspect, but its numeric
    # key:value lines (Tune File, Skim1, mass rows) are NOT promoted to canonical.
    f = tmp_path / "MSPARMS.txt"
    f.write_text(_MSPARMS)
    parsed = debug.chemstation_text.parse(str(f))
    assert any(l.startswith("Skim1") for l in parsed["lines"])
    assert any("118.09" in l for l in parsed["lines"])
    out = debug.chemstation_text.canonical(parsed)
    # Tune File is a path but a fixed instrument reference; never promoted.
    assert "atunes.tun" not in str(out)
    assert set(out) == {"data_file", "operator", "acquired", "instrument", "sample"}


def test_msparms_real_fixture_surfaces_operator():
    # orange.D ships a real MSPARMS.txt; assert the parser surfaces the operator
    # FIELD (a personal-name slot the LC/MS runstart lacks). The value is real
    # vendor PII, so only the key's presence is asserted, never the string.
    out = rb.debug.inspect(os.path.join("tests", "inputs", "orange.D"))
    msp = [v for v in out.values()
           if v.get("parser") == "chemstation_text" and v.get("kind") == "msparms"]
    assert msp, "MSPARMS.txt was not surfaced"
    assert "operator" in debug.chemstation_text.canonical(msp[0])


# --- Waters inlet.inf (GC run-log variant, no leading underscore) -----------

def test_waters_inlet_no_underscore_matched():
    # Both spellings are claimed; the GC run-log drops the leading underscore.
    assert debug.waters_inf.matches("inlet.inf")
    assert debug.waters_inf.matches("extern.inf")
    assert debug._dispatch("inlet.inf") is debug.waters_inf


def test_waters_inlet_bare_method_name(tmp_path):
    # The GC layout names the method with "Method File: <name>" (a bare name,
    # not a path); it is identity and taken as-is.
    f = tmp_path / "inlet.inf"
    f.write_text("GC Run Log\r\nInstrument: GCMS\r\n"
                 "Method File: DEMO_METHOD_SLOW\r\n"
                 "Last Saved : 11/10/2025 7:03:36 PM\r\n"
                 "Inj A: SSL\t300 deg C\r\n")
    parsed = debug.waters_inf.parse(str(f))
    assert parsed["kind"] == "inlet"
    assert debug.waters_inf.canonical(parsed) == {"method": "DEMO_METHOD_SLOW"}
    # The GC parameter body stays in the lossless lines.
    assert any(l.startswith("Inj A") for l in parsed["lines"])


def test_waters_inlet_underscore_path_layout_still_works(tmp_path):
    # Regression: adding the "Method File:" prefix must not disturb the original
    # "Inlet Method File: <path>" layout.
    f = tmp_path / "_INLET.INF"
    f.write_text("ACE Experimental Record\r\n"
                 r"Inlet Method File: c:\masslynx\PROJECT01.pro\acqudb\screen" "\r\n")
    out = debug.waters_inf.canonical(debug.waters_inf.parse(str(f)))
    assert out == {"method": r"c:\masslynx\PROJECT01.pro\acqudb\screen"}


def test_waters_inlet_real_fixture_turquoise():
    # turquoise.raw ships inlet.inf (no underscore); assert it is surfaced as a
    # waters_inf inlet record that carries a method. Value is vendor data, so
    # only the key's presence is asserted.
    out = rb.debug.inspect(WATERS)
    inlet = [v for v in out.values()
             if v.get("parser") == "waters_inf" and v.get("kind") == "inlet"]
    assert inlet, "inlet.inf was not surfaced"
    assert "method" in debug.waters_inf.canonical(inlet[0])


def test_waters_extern_no_underscore_canonical(tmp_path):
    # The bare `extern.inf` spelling must go through the same path-vs-label gate
    # as `_extern.inf`, not just be matched by name.
    f = tmp_path / "extern.inf"
    f.write_text(r"Parameters for C:\MassLynx\PROJECT02.PRO\ACQUDB\MS_POS.EXP" "\r\n")
    assert debug._dispatch("extern.inf") is debug.waters_inf
    assert debug.waters_inf.canonical(debug.waters_inf.parse(str(f))) == {
        "method": r"C:\MassLynx\PROJECT02.PRO\ACQUDB\MS_POS.EXP"}
    # ...and a bare label is still left unpromoted under the no-underscore spelling.
    f.write_text("Parameters for test\r\n")
    assert debug.waters_inf.canonical(debug.waters_inf.parse(str(f))) == {}


def test_waters_inlet_empty_method_file_not_promoted(tmp_path):
    # "Method File:" with nothing after it must yield {}, not {"method": ""}.
    f = tmp_path / "inlet.inf"
    f.write_text("GC Run Log\r\nMethod File:\r\nInj A: SSL\t300 deg C\r\n")
    assert debug.waters_inf.canonical(debug.waters_inf.parse(str(f))) == {}


def test_msparms_first_value_wins_blank_skipped(tmp_path):
    # A blank "Operator :" line carries no value (the key:value matcher needs a
    # non-space after the colon), so it is skipped; the first real value then wins
    # via setdefault and a later differing value does not override it.
    f = tmp_path / "MSPARMS.txt"
    f.write_text("Operator                 :   \r\n"
                 "Operator                 :   Alex Sampleton\r\n"
                 "Operator                 :   Someone Else\r\n")
    out = debug.chemstation_text.canonical(debug.chemstation_text.parse(str(f)))
    assert out == {"operator": "Alex Sampleton"}


# --- ChemStation .D report / state family (report.txt, report*.csv, ----------
# --- acq_methhist.txt, scstate.txt) and the .tune XML. All synthetic: these
# --- formats live only in the untracked data/ corpus, so there is no committed
# --- fixture; the values below are fabricated.

_REPORT_TEXT = (
    "Data File C:\\Chem32\\1\\Data\\DEMO\\023-sample-23.D\r\n"
    "Sample Name: DEMO-SAMPLE-23\r\n"
    "1290UHPLC 1/26/2024 7:42:22 PM SYSTEM\r\n"
    "=====================================================================\r\n"
    "Acq. Operator   : Alex Sampleton                  Seq. Line :  23\r\n"
    "Acq. Instrument : 1290UHPLC                         Location :   D3F-B11\r\n"
    "Injection Date  : 1/26/2024 7:36:13 PM                  Inj :   1\r\n"
    "=====================================================================\r\n"
    "                         Area Percent Report\r\n"
    "   1   0.708  1  BV    178.19504   20.53072   1.0227\r\n")


def test_report_text_registered_and_matched():
    assert debug.chemstation_text.matches("report.txt")
    assert debug._dispatch("report.txt") is debug.chemstation_text


def test_report_text_two_column_header(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text(_REPORT_TEXT)
    parsed = debug.chemstation_text.parse(str(f))
    assert parsed["kind"] == "report_text"
    out = debug.chemstation_text.canonical(parsed)
    # Each two-column value must stop at the column gap, not swallow the second
    # column (operator must be "Alex Sampleton", not "...  Seq. Line : 23").
    assert out == {
        "data_file": r"C:\Chem32\1\Data\DEMO\023-sample-23.D",
        "sample": "DEMO-SAMPLE-23",
        "operator": "Alex Sampleton",
        "instrument": "1290UHPLC",
        "acquired": "1/26/2024 7:36:13 PM",
        "vialpos": "D3F-B11",
    }


def test_report_text_peak_table_not_mined(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text(_REPORT_TEXT)
    parsed = debug.chemstation_text.parse(str(f))
    # The numeric peak row is kept verbatim but never promoted.
    assert any("178.19504" in l for l in parsed["lines"])
    assert "178.19504" not in str(debug.chemstation_text.canonical(parsed))


_REPORT_CSV = (
    '"Sample Name","DEMO HTE Screen 89",""\r\n'
    '"Data File","C:\\Chem32\\1\\Data\\DEMO\\",\r\n'
    '"Acq. Instrument","LCMS",""\r\n'
    '"Acq. Method","4min FFP MS.M",""\r\n'
    '"Acq. Operator","Alex Sampleton",""\r\n'
    '"Injection Date","23-Jun-23, 03:57:09",""\r\n'
    '"Location",7.38264e+008,""\r\n')


def test_report_csv_matched_by_prefix():
    assert debug.chemstation_text.matches("report00.csv")
    assert debug.chemstation_text.matches("report03.csv")
    assert debug._dispatch("report01.csv") is debug.chemstation_text
    # A non-report/non-tic CSV (e.g. rainbow's own export) is not claimed.
    assert not debug.chemstation_text.matches("results.csv")


def test_report_csv_canonical_and_bom(tmp_path):
    f = tmp_path / "report00.csv"
    f.write_text("﻿" + _REPORT_CSV)  # leading BOM must not break the first key
    parsed = debug.chemstation_text.parse(str(f))
    assert parsed["kind"] == "report_csv"
    out = debug.chemstation_text.canonical(parsed)
    assert out == {
        "sample": "DEMO HTE Screen 89",
        "data_file": "C:\\Chem32\\1\\Data\\DEMO\\",
        "instrument": "LCMS",
        "method": "4min FFP MS.M",
        "operator": "Alex Sampleton",
        "acquired": "23-Jun-23, 03:57:09",
    }
    # The numeric Location row is preserved but not promoted.
    assert "vialpos" not in out


_METHHIST = (
    "Data File  : C:\\Chem32\\1\\DATA\\DEMO\\013-x.D\r\n"
    "Acq. Method: DEMO-long-005.M\r\n"
    "The Acq. Method's Audit Trail at the end of the Run : \r\n"
    "Operator   : SYSTEM\r\n"
    "Date       : 2/3/2025 7:52:10 AM\r\n"
    "Change Info: created based on method 'C:\\Chem32\\Methods\\DEMO-006.M'\r\n")


def test_methhist_matched_and_canonical(tmp_path):
    assert debug._dispatch("acq_methhist.txt") is debug.chemstation_text
    f = tmp_path / "acq_methhist.txt"
    f.write_text(_METHHIST)
    parsed = debug.chemstation_text.parse(str(f))
    assert parsed["kind"] == "methhist"
    assert debug.chemstation_text.canonical(parsed) == {
        "data_file": r"C:\Chem32\1\DATA\DEMO\013-x.D",
        "method": "DEMO-long-005.M",
    }
    # The audit trail is kept verbatim, not promoted.
    assert any(l.startswith("Change Info") for l in parsed["lines"])


_SCSTATE = (
    "                          SC State Report (Rev. 2.01)\r\n"
    "Instrument Configuration:\r\n"
    "  Instrument Model          = G6120B\r\n"
    "  Serial Number             = DEMO00001\r\n"
    "  Mass Range Low/High[Res]  = 0.15 / 3276.00 [0.050]\r\n"
    "Smartcard Configuration:\r\n"
    "  Smartcard Model           = SC3B\r\n"
    "  Serial Number             = DEMO00002\r\n")


def test_scstate_matched_and_serials(tmp_path):
    assert debug._dispatch("scstate.txt") is debug.chemstation_text
    f = tmp_path / "scstate.txt"
    f.write_text(_SCSTATE)
    parsed = debug.chemstation_text.parse(str(f))
    assert parsed["kind"] == "scstate"
    out = debug.chemstation_text.canonical(parsed)
    # Every distinct Serial Number is collected, in order; the first pairs with
    # the Instrument Model. The Smartcard Model is NOT the instrument.
    assert out["serials"] == ["DEMO00001", "DEMO00002"]
    assert out["instrument"] == "G6120B"
    assert out["devices"] == [{"Name": "G6120B", "SerialNumber": "DEMO00001"}]
    # Numeric config lines are kept but not promoted.
    assert any("Mass Range" in l for l in parsed["lines"])


_TUNE = (
    '<Root version="3.0"><HashValue>abc</HashValue>'
    '<TuneContent><ExternalModel>G6465B</ExternalModel>'
    '<InternalModel>G6465B</InternalModel>'
    '<SerialNumber>DEMO00009</SerialNumber></TuneContent></Root>')


def test_tune_matched_by_xml_parser():
    assert debug.xml.matches("tunefilexml_1.tune")
    assert debug._dispatch("x.tune") is debug.xml


def test_tune_utf16le_no_bom_serial(tmp_path):
    # .tune is UTF-16LE with no BOM and no declaration; the xml parser must fall
    # back to a decode-based parse, then extract the serial + model.
    f = tmp_path / "tunefilexml_1.tune"
    f.write_bytes(_TUNE.encode("utf-16-le"))
    parsed = debug.xml.parse(str(f))
    assert parsed.get("error") is None
    assert parsed["root"] == "Root"
    out = debug.xml.canonical(parsed)
    assert out["serials"] == ["DEMO00009"]
    assert out["instrument"] == "G6465B"
    assert out["devices"][0] == {"Name": "G6465B", "SerialNumber": "DEMO00009"}


def test_tune_root_without_serial_is_empty(tmp_path):
    # A generic <Root> document with no SerialNumber must fall through to {}.
    f = tmp_path / "other.tune"
    f.write_bytes(b'<Root><Other>x</Other></Root>')
    parsed = debug.xml.parse(str(f))
    assert parsed["root"] == "Root"
    assert debug.xml.canonical(parsed) == {}


def test_navy_inspect_surfaces_report_family():
    # All five sanitized report/state sidecars are surfaced in a real dir walk.
    out = rb.debug.inspect(NAVY)
    kinds = {v.get("kind") or v.get("root") for v in out.values()}
    for kind in ("report_text", "report_csv", "methhist", "scstate"):
        assert kind in kinds, kind
    assert "Root" in kinds  # the UTF-16LE .tune, via the xml parser


def test_navy_fields_merge_report_family():
    rec = rb.debug.fields(NAVY)
    # Identity merged across the report/state files (sanitized values).
    assert rec["operator"] == "Alex Sampleton"
    assert rec["sample"] == "DEMO-SAMPLE-23"
    assert rec["instrument"] == "1290UHPLC"   # report.txt sorts before scstate
    assert rec["vialpos"] == "D3F-B11"        # report.txt Location column
    assert rec["method"] == "DEMO-long-005.M"  # acq_methhist.txt sorts first
    assert rec["data_file"].endswith("DEMO-SAMPLE-12.D")
    # serials accumulate across scstate.txt and the .tune.
    assert "DEAA900001" in rec["serials"]      # scstate Serial Number
    assert "DEAA900002" in rec["serials"]      # .tune SerialNumber
    # provenance is recorded for the merged fields.
    assert {"operator", "serials", "sample", "method"} <= set(rec["_sources"])


# --- review follow-ups: edge cases for the .D report/state + .tune fills -----

def test_report_csv_extension_restricted_to_csv():
    # report* is claimed only as .csv (comma-delimited reader); a .tsv is not.
    assert debug.chemstation_text.matches("report.csv")        # digit-optional
    assert not debug.chemstation_text.matches("report00.tsv")  # not tab


def test_report_text_datafile_colon_variant(tmp_path):
    # The data-file line also appears as "Data File : <path>" (with a colon).
    f = tmp_path / "report.txt"
    f.write_text("Data File : C:\\Chem32\\1\\Data\\DEMO\\x.D\r\nSample Name: S\r\n")
    out = debug.chemstation_text.canonical(debug.chemstation_text.parse(str(f)))
    assert out["data_file"] == r"C:\Chem32\1\Data\DEMO\x.D"


def test_report_labels_case_insensitive(tmp_path):
    # The header labels are lowercased before lookup, so upper-case still maps.
    f = tmp_path / "report.txt"
    f.write_text("ACQ. OPERATOR   : Alex Sampleton                  Seq. Line : 1\r\n")
    out = debug.chemstation_text.canonical(debug.chemstation_text.parse(str(f)))
    assert out == {"operator": "Alex Sampleton"}


def test_scstate_model_without_serial(tmp_path):
    # Instrument Model present, no Serial Number: instrument only, no serials.
    f = tmp_path / "scstate.txt"
    f.write_text("Instrument Configuration:\r\n  Instrument Model          = G1\r\n")
    out = debug.chemstation_text.canonical(debug.chemstation_text.parse(str(f)))
    assert out == {"instrument": "G1"}


def test_tune_model_without_serial_is_empty(tmp_path):
    # A <Root> with a model tag but no SerialNumber is not a tune file: {}.
    f = tmp_path / "x.tune"
    f.write_bytes(
        "<Root><TuneContent><ExternalModel>G6465B</ExternalModel>"
        "</TuneContent></Root>".encode("utf-16-le"))
    parsed = debug.xml.parse(str(f))
    assert parsed["root"] == "Root"
    assert debug.xml.canonical(parsed) == {}


def test_tune_multi_serial_dedup(tmp_path):
    # Distinct SerialNumbers accumulate (a repeat is dropped); the first pairs
    # with the model in devices.
    f = tmp_path / "x.tune"
    body = ("<Root><A><SerialNumber>S1</SerialNumber></A>"
            "<B><SerialNumber>S1</SerialNumber></B>"
            "<C><SerialNumber>S2</SerialNumber>"
            "<InternalModel>M1</InternalModel></C></Root>")
    f.write_bytes(body.encode("utf-16-le"))
    out = debug.xml.canonical(debug.xml.parse(str(f)))
    assert out["serials"] == ["S1", "S2"]
    assert out["instrument"] == "M1"
    assert out["devices"][0] == {"Name": "M1", "SerialNumber": "S1"}


def test_tune_undecodable_does_not_raise(tmp_path):
    # A non-XML .tune must error cleanly (not raise), contributing nothing.
    f = tmp_path / "x.tune"
    f.write_bytes(b"\x00\x01\x02 this is not xml \xff")
    parsed = debug.xml.parse(str(f))  # must not raise
    assert isinstance(parsed, dict)
    assert debug.xml.canonical(parsed) == {}
