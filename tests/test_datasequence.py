"""
Tests for multi-injection sequence reading (rb.read_sequence -> DataSequence).

A synthetic sequence directory is built per-test by copying the small brown.D
UV fixture into injection-named subdirectories, so the real per-injection read
path is exercised without committing any new binary data.
"""
import os
import shutil

import pytest

import rainbow as rb
from rainbow.datadirectory import DataDirectory
from rainbow.datasequence import DataSequence


FIXTURE = os.path.join(os.path.dirname(__file__), "inputs", "brown.D")

# Injection-style names, deliberately out of alphabetical-vs-numeric agreement
# so the sort-by-name ordering is actually tested.
INJECTION_NAMES = [
    "008-D1F-A1-sample_01.D",
    "009-D1F-A2-sample_02.D",
    "010-D1F-A3-sample_03.D",
]


def _make_sequence(tmp_path, names=INJECTION_NAMES, extra_files=()):
    """Builds a synthetic sequence directory of brown.D copies."""
    seq = tmp_path / "Synthetic_Sequence"
    seq.mkdir()
    for name in names:
        shutil.copytree(FIXTURE, seq / name)
    for fname in extra_files:
        (seq / fname).write_text("placeholder", encoding="utf-8")
    return str(seq)


def test_read_sequence_returns_datasequence(tmp_path):
    seq = rb.read_sequence(_make_sequence(tmp_path))
    assert isinstance(seq, DataSequence)
    assert len(seq) == len(INJECTION_NAMES)
    assert all(isinstance(inj, DataDirectory) for inj in seq)


def test_injections_are_in_sorted_acquisition_order(tmp_path):
    seq = rb.read_sequence(_make_sequence(tmp_path))
    assert [inj.name for inj in seq] == sorted(INJECTION_NAMES)


def test_each_injection_is_fully_parsed(tmp_path):
    seq = rb.read_sequence(_make_sequence(tmp_path))
    # brown.D is a UV directory, so every injection should carry UV data.
    for inj in seq:
        assert "UV" in inj.detectors
        assert inj.datafiles


def test_metadata_reports_injection_count(tmp_path):
    seq = rb.read_sequence(_make_sequence(tmp_path))
    assert seq.metadata["injection_count"] == len(INJECTION_NAMES)


def test_get_injection_and_by_name(tmp_path):
    seq = rb.read_sequence(_make_sequence(tmp_path))
    name = sorted(INJECTION_NAMES)[0]
    assert seq.get_injection(name) is seq.by_name[name]
    with pytest.raises(Exception):
        seq.get_injection("does-not-exist.D")


def test_sequence_level_files_are_ignored_for_injection_list(tmp_path):
    # A sequence.acaml / .S sitting alongside the .D dirs must not be counted
    # as an injection.
    seq = rb.read_sequence(
        _make_sequence(tmp_path, extra_files=("sequence.acaml", "run.S")))
    assert len(seq) == len(INJECTION_NAMES)


def test_format_override_is_respected(tmp_path):
    seq = rb.read_sequence(_make_sequence(tmp_path), format="agilent")
    assert len(seq) == len(INJECTION_NAMES)


def test_bad_format_rejected(tmp_path):
    with pytest.raises(Exception):
        rb.read_sequence(_make_sequence(tmp_path), format="nikon")


def test_non_directory_path_rejected(tmp_path):
    missing = str(tmp_path / "nope")
    with pytest.raises(Exception):
        rb.read_sequence(missing)


def test_directory_without_injections_is_not_a_sequence(tmp_path):
    empty = tmp_path / "Empty"
    empty.mkdir()
    with pytest.raises(Exception):
        rb.read_sequence(str(empty))


def test_repr_and_iteration(tmp_path):
    seq = rb.read_sequence(_make_sequence(tmp_path))
    assert "3 injections" in repr(seq)
    assert list(iter(seq)) == seq.injections


def test_datasequence_validates_arguments(tmp_path):
    with pytest.raises(Exception):
        DataSequence("path", "not a list", {})
    with pytest.raises(Exception):
        DataSequence("path", [object()], {})


# A synthetic sequence.acaml header to drop alongside the injections.
SEQUENCE_ACAML = """<?xml version="1.0" encoding="utf-8"?>
<ACAML xmlns="urn:schemas-agilent-com:acaml15"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Doc>
    <DocInfo><CreatedByUser>LAB\\runner</CreatedByUser></DocInfo>
    <Content><Resources>
      <Instrument xsi:type="InstrumentType" id="a">
        <Name>1290</Name>
        <Technique>LiquidChromatography</Technique>
        <Module>
          <Name>DAD</Name><Type>Detector</Type>
          <PartNo>G7117B</PartNo><SerialNo>SN-DAD-001</SerialNo>
          <FirmwareRevision>D.07.35</FirmwareRevision>
        </Module>
      </Instrument>
    </Resources></Content>
  </Doc>
</ACAML>
"""


def _make_sequence_with_acaml(tmp_path):
    seq = _make_sequence(tmp_path)
    with open(os.path.join(seq, "sequence.acaml"), "w", encoding="utf-8") as f:
        f.write(SEQUENCE_ACAML)
    return seq


def test_sequence_acaml_populates_metadata(tmp_path):
    seq = rb.read_sequence(_make_sequence_with_acaml(tmp_path))
    assert seq.metadata["operator"] == "LAB\\runner"
    assert seq.metadata["instrument"]["name"] == "1290"
    assert seq.metadata["instrument"]["modules"][0]["serial_no"] == "SN-DAD-001"


def test_operator_backfills_onto_injections(tmp_path):
    seq = rb.read_sequence(_make_sequence_with_acaml(tmp_path))
    # brown.D carries no operator of its own, so the run-wide operator fills in.
    for injection in seq:
        assert injection.metadata["operator"] == "LAB\\runner"


def test_no_sequence_acaml_leaves_minimal_metadata(tmp_path):
    seq = rb.read_sequence(_make_sequence(tmp_path))
    assert seq.metadata == {"injection_count": len(INJECTION_NAMES)}
    assert "operator" not in seq.metadata


# A sequence.acaml carrying peaks for the first injection only.
PEAKS_ACAML = """<?xml version="1.0" encoding="utf-8"?>
<ACAML xmlns="urn:schemas-agilent-com:acaml15"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Doc><Content>
    <Resources>
      <Signal xsi:type="SignalType" id="sig-254">
        <BinaryData><DataItem><Data><DataFileReference>
          <Path>008-D1F-A1-sample_01.D\\DAD1A.CH</Path>
        </DataFileReference></Data></DataItem></BinaryData>
        <Name>DAD1A</Name><Description>DAD1 A, Sig=254,4</Description>
      </Signal>
    </Resources>
    <Injections>
      <Result xsi:type="InjectionResultType" id="r1">
        <SignalResult id="sr1">
          <Signal_ID id="sig-254" />
          <Peak id="p1"><RetentionTime val="1.5" /><Area val="100.0" /></Peak>
        </SignalResult>
      </Result>
    </Injections>
  </Content></Doc>
</ACAML>
"""


def _make_sequence_with_peaks(tmp_path):
    seq = _make_sequence(tmp_path)
    with open(os.path.join(seq, "sequence.acaml"), "w", encoding="utf-8") as f:
        f.write(PEAKS_ACAML)
    return seq


def test_peaks_flag_attaches_peaks_to_matching_injection(tmp_path):
    seq = rb.read_sequence(_make_sequence_with_peaks(tmp_path), peaks=True)
    assert seq.metadata["peaks_read"] is True
    first = seq.get_injection("008-D1F-A1-sample_01.D")
    assert len(first.peaks) == 1
    assert first.peaks[0]["wavelength"] == 254.0
    assert first.peaks[0]["peaks"][0]["area"] == 100.0


def test_peaks_flag_leaves_unmatched_injections_empty(tmp_path):
    seq = rb.read_sequence(_make_sequence_with_peaks(tmp_path), peaks=True)
    others = [inj for inj in seq if inj.name != "008-D1F-A1-sample_01.D"]
    assert others and all(inj.peaks == [] for inj in others)


def test_peaks_off_by_default(tmp_path):
    seq = rb.read_sequence(_make_sequence_with_peaks(tmp_path))
    assert "peaks_read" not in seq.metadata
    assert not hasattr(seq.injections[0], "peaks")


def test_bad_peaks_flag_rejected(tmp_path):
    with pytest.raises(Exception):
        rb.read_sequence(_make_sequence(tmp_path), peaks="yes")


def _injection_acam(d_name):
    """A per-injection result document (sequence.acam_) for one injection."""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ACAML xmlns="urn:schemas-agilent-com:acaml15"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Doc><Content>
    <Resources>
      <Signal xsi:type="SignalType" id="s">
        <BinaryData><DataItem><Data><DataFileReference>
          <Path>{d_name}\\dad1A.ch</Path>
        </DataFileReference></Data></DataItem></BinaryData>
        <Name>DAD1A</Name><Description>DAD1 A, Sig=254,4</Description>
      </Signal>
    </Resources>
    <Injections>
      <Result xsi:type="InjectionResultType" id="r">
        <SignalResult id="sr">
          <Signal_ID id="s" />
          <Peak id="p"><RetentionTime val="2.0" /><Area val="50.0" /></Peak>
        </SignalResult>
      </Result>
    </Injections>
  </Content></Doc>
</ACAML>
"""


def test_peaks_fall_back_to_per_injection_acam(tmp_path):
    # A sequence with NO top-level sequence.acaml, but each .D carries its own
    # sequence.acam_ (the no-top-level-acaml layout). Peaks must still attach.
    seq_dir = _make_sequence(tmp_path)
    for name in INJECTION_NAMES:
        with open(os.path.join(seq_dir, name, "sequence.acam_"),
                  "w", encoding="utf-8") as f:
            f.write(_injection_acam(name))

    seq = rb.read_sequence(seq_dir, peaks=True)
    assert all(inj.peaks for inj in seq)
    first = seq.injections[0]
    assert first.peaks[0]["wavelength"] == 254.0
    assert first.peaks[0]["peaks"][0]["area"] == 50.0


def test_per_injection_acam_adopted_despite_name_mismatch(tmp_path):
    # When a per-injection sequence.acam_ names a .D that differs from the
    # folder (its single result still belongs to this injection), it is still
    # adopted. This is why _injection_peaks falls back to the sole entry.
    seq_dir = _make_sequence(tmp_path)
    for name in INJECTION_NAMES:
        with open(os.path.join(seq_dir, name, "sequence.acam_"),
                  "w", encoding="utf-8") as f:
            f.write(_injection_acam("UNRELATED-NAME.D"))

    seq = rb.read_sequence(seq_dir, peaks=True)
    assert all(inj.peaks for inj in seq)
    assert seq.injections[0].peaks[0]["peaks"][0]["area"] == 50.0
