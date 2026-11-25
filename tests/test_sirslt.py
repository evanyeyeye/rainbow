"""
Tests for Agilent OpenLab CDS .sirslt result folders.

A .sirslt holds a .dx archive, a .acaml result-set document, and for an MS run
the MSScan.bin/MSPeak.bin binaries beside the archive (their schema,
MSScan.xsd, inside it). The folders here are assembled from the repository's
own fixtures: teal.dx for the detector signals, yellow.D's AcqData for the MS
binaries, so each part can be checked against reading its source directly.

Three real, anonymised folders are read as well (see
tests/inputs/README_sirslt.md): olive.sirslt, a UHPLC single-quadrupole LC/MS
run (DAD spectrum, one DAD signal, MS centroids); plum.sirslt, an HPLC run
whose DAD spectrum carries the HPLC scale factor; and lime.sirslt, an HPLC run
with one DAD signal.

Set RAINBOW_SIRSLT_EXAMPLES to a directory of real .sirslt folders to also run
:func:`test_real_sirslt_folders` against them.

"""
import glob
import os
import shutil
import struct
import tempfile
import warnings
import zipfile

import numpy as np
import pytest

import rainbow as rb
from rainbow.agilent import masshunter, openlab, sirslt

INPUTS = os.path.join("tests", "inputs")
TEAL = os.path.join(INPUTS, "teal.dx")
YELLOW_ACQDATA = os.path.join(INPUTS, "yellow.D", "AcqData")

_MS_SIGNAL = (
    '<Signal>'
    '<Encoding>Agilent.OpenLab.Rawdata/MSData</Encoding>'
    '<TraceId>00000000-0000-4000-8000-000000000001</TraceId>'
    '<DeviceName /><Description>Mass Spec Data</Description>'
    '<ScaleFactor>0</ScaleFactor><Units />'
    '<ExternalElementPaths>{stem}.MSPeak.bin,{stem}.MSScan.bin'
    '</ExternalElementPaths>'
    '</Signal>')


def _acaml(technique="LiquidChromatography", name="LC1"):
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<ACAML xmlns="urn:schemas-agilent-com:acaml21"><Doc>'
        '<DocInfo><CreatedByUser>analyst</CreatedByUser></DocInfo>'
        '<Content><Resources><Instrument id="i">'
        '<Name>' + name + '</Name>'
        '<Technique>' + technique + '</Technique>'
        '<Module><Name>DAD</Name><Type>Detector</Type></Module>'
        '</Instrument></Resources></Content></Doc></ACAML>')


def _make_dx(dest, source=TEAL, acmd=None, extra=None, drop_payloads=False):
    """Copies ``source`` to ``dest``, optionally rewriting its manifest and
    adding members (``extra`` maps member name -> bytes)."""
    with zipfile.ZipFile(source) as src, \
            zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as out:
        for member in src.namelist():
            if member == 'injection.acmd' and acmd is not None:
                out.writestr(member, acmd(src.read(member).decode('utf-8-sig')))
                continue
            if drop_payloads and os.path.splitext(member)[1].lower() in (
                    '.uv', '.ch', '.it'):
                continue
            out.writestr(member, src.read(member))
        for name, data in (extra or {}).items():
            out.writestr(name, data)


def _make_sirslt(tmp_path, name="run", acaml=True, ms=False, suffix=".sirslt",
                 **dx_kwargs):
    folder = tmp_path / (name + suffix)
    folder.mkdir()
    if ms:
        extra = {}
        for member in ("MSScan.xsd", "Contents.xml", "Devices.xml",
                       "MSTS.xml"):
            with open(os.path.join(YELLOW_ACQDATA, member), 'rb') as f:
                extra["MSData/" + member] = f.read()
        dx_kwargs['extra'] = extra
        previous = dx_kwargs.get('acmd')

        def acmd(text):
            if previous is not None:
                text = previous(text)
            return text.replace(
                '</Signals>', _MS_SIGNAL.format(stem=name) + '</Signals>')
        dx_kwargs['acmd'] = acmd
        for member in ("MSScan.bin", "MSPeak.bin"):
            shutil.copyfile(os.path.join(YELLOW_ACQDATA, member),
                            str(folder / "{}.{}".format(name, member)))
    _make_dx(str(folder / (name + ".dx")), **dx_kwargs)
    if acaml:
        text = acaml if isinstance(acaml, str) else _acaml()
        (folder / (name + ".acaml")).write_text(text, encoding="utf-8")
    return str(folder)


# --- detector signals --------------------------------------------------------

def test_reads_the_archive_signals(tmp_path):
    path = _make_sirslt(tmp_path)
    datadir = rb.read(path)
    reference = rb.read(TEAL)
    assert datadir.name == "run.sirslt"
    assert sorted(df.name for df in datadir.datafiles) == \
        sorted(df.name for df in reference.datafiles)
    for datafile in reference.datafiles:
        ours = datadir.get_file(datafile.name)
        assert ours.detector == datafile.detector
        np.testing.assert_array_equal(ours.xlabels, datafile.xlabels)
        np.testing.assert_array_equal(ours.data, datafile.data)
    for key, value in reference.metadata.items():
        assert datadir.metadata[key] == value
    assert datadir.metadata['technique'] == 'LC'
    assert datadir.metadata['instrument']['name'] == 'LC1'
    assert not datadir.analog


def test_telemetry_is_opt_in(tmp_path):
    path = _make_sirslt(tmp_path)
    assert rb.read(path).analog == []
    assert len(rb.read(path, telemetry=True).analog) == \
        len(rb.read(TEAL, telemetry=True).analog)


def test_a_folder_without_its_suffix_is_recognized(tmp_path):
    path = _make_sirslt(tmp_path, suffix="")
    assert rb.sniff_vendor(path) == 'agilent'
    assert sirslt.is_sirslt(path)
    assert rb.read(path).metadata['technique'] == 'LC'


def test_a_run_with_no_detector_signal_keeps_its_metadata(tmp_path):
    # A column flush records instrument telemetry only. The .dx reader has
    # nothing to return for it, but the run is real and its metadata is not.
    path = _make_sirslt(tmp_path, drop_payloads=True)
    datadir = rb.read(path)
    assert datadir.datafiles == []
    assert datadir.metadata['vendor'] == 'Agilent'
    assert datadir.metadata['technique'] == 'LC'


def test_read_metadata(tmp_path):
    path = _make_sirslt(tmp_path, ms=True)
    listing = rb.read_metadata(path)
    assert 'MSPeak.bin' in listing['datafiles']
    assert listing['metadata']['centroid_available'] is True
    assert listing['metadata']['technique'] == 'LC'


def test_peaks_are_not_read_and_say_so(tmp_path):
    path = _make_sirslt(tmp_path)
    with pytest.warns(UserWarning, match="sirslt"):
        datadir = rb.read(path, peaks=True)
    assert datadir.peaks == []


# --- the spectrum's scale factor ---------------------------------------------

def test_the_spectrum_is_scaled_by_its_manifest_factor(tmp_path):
    # An HPLC DAD records 1000 * 2**-21 where a UHPLC DAD records
    # 1000 * 2**-27; the factor is the manifest's, not a constant.
    reference = rb.read(TEAL).get_file("DAD1I.UV")

    def rescale(text):
        return text.replace('<ScaleFactor>7.4505805969238281E-06',
                            '<ScaleFactor>0.000476837158203125')
    dest = str(tmp_path / "hplc.dx")
    _make_dx(dest, acmd=rescale)
    rescaled = rb.read(dest).get_file("DAD1I.UV")
    np.testing.assert_allclose(rescaled.data, reference.data * 64)


def test_the_manifest_carries_scale_factor_and_external_files(tmp_path):
    dest = str(tmp_path / "ms.dx")
    _make_dx(dest, acmd=lambda text: text.replace(
        '</Signals>', _MS_SIGNAL.format(stem="run") + '</Signals>'))
    with zipfile.ZipFile(dest) as archive:
        _, signals = openlab._parse_manifest(archive)
    spectra = [s for s in signals.values()
               if s['encoding'].endswith('Spectra131')]
    assert spectra[0]['scale_factor'] == 1000 * 2 ** -27
    ms = [s for s in signals.values() if s['encoding'].endswith('/MSData')]
    assert ms[0]['external'] == ["run.MSPeak.bin", "run.MSScan.bin"]


# --- MS beside the archive ---------------------------------------------------

def test_ms_beside_the_archive_reads_like_the_d(tmp_path):
    path = _make_sirslt(tmp_path, ms=True)
    ours = rb.read(path, centroid=True).get_file("MSPeak.bin")
    reference = rb.read(os.path.join(INPUTS, "yellow.D"),
                        centroid=True).get_file("MSPeak.bin")
    np.testing.assert_array_equal(ours.xlabels, reference.xlabels)
    for i in range(len(reference.xlabels)):
        for mine, theirs in zip(ours.scan(i), reference.scan(i)):
            np.testing.assert_array_equal(mine, theirs)
    datadir = rb.read(path, centroid=True)
    assert 'MS' in datadir.detectors
    assert datadir.metadata['ms_devices']
    assert 'centroid_available' not in datadir.metadata


def test_ms_is_flagged_when_not_asked_for(tmp_path):
    path = _make_sirslt(tmp_path, ms=True)
    datadir = rb.read(path)
    assert 'MS' not in datadir.detectors
    assert datadir.metadata['centroid_available'] is True


def test_ms_with_a_bin_width_is_binned(tmp_path):
    path = _make_sirslt(tmp_path, ms=True)
    ours = rb.read(path, centroid=True, bin_width=1.0).get_file("MSPeak.bin")
    reference = rb.read(os.path.join(INPUTS, "yellow.D"), centroid=True,
                        bin_width=1.0).get_file("MSPeak.bin")
    np.testing.assert_array_equal(ours.ylabels, reference.ylabels)
    np.testing.assert_array_equal(ours.data, reference.data)


def test_no_temporary_folder_is_left_behind(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(scratch))
    rb.read(_make_sirslt(tmp_path, ms=True), centroid=True)
    assert list(scratch.iterdir()) == []


# --- LC or GC ----------------------------------------------------------------

def test_technique_from_the_result_document(tmp_path):
    gc = _make_sirslt(tmp_path, name="gc",
                      acaml=_acaml("GasChromatography", "GC1"))
    assert sirslt.technique(gc) == 'GC'
    assert rb.read(gc).metadata['technique'] == 'GC'


def test_technique_from_the_ms_contents_without_a_result_document(tmp_path):
    # yellow.D is a GC/MS run: its Contents.xml says SeparationTechnique 2.
    path = _make_sirslt(tmp_path, acaml=False, ms=True)
    assert sirslt.technique(path) == 'GC'


def test_technique_from_a_gc_injection_source(tmp_path):
    def gc_injector(text):
        return text.replace(
            '<InjectionInfo>',
            '<InjectionInfo><InjectionSource>GC Injector</InjectionSource>', 1)
    path = _make_sirslt(tmp_path, acaml=False, acmd=gc_injector)
    assert sirslt.technique(path) == 'GC'


def test_technique_unknown_without_evidence(tmp_path):
    path = _make_sirslt(tmp_path, acaml=False)
    assert sirslt.technique(path) is None
    assert 'technique' not in rb.read(path).metadata


# --- the MassHunter pieces the folder relies on -------------------------------

def test_scan_xsd_skips_an_untyped_padding_element(tmp_path):
    xsd = tmp_path / "MSScan.xsd"
    xsd.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<xs:schema targetNamespace="http://tempuri.org/XMLSchema.xsd" '
        'xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'xmlns="http://tempuri.org/XMLSchema.xsd">'
        '<xs:complexType name="ScanRecordType"><xs:sequence>'
        '<xs:element name="ScanID" type="xs:int" />'
        '<xs:element name="Padding" minOccurs="0"><xs:complexType>'
        '<xs:sequence><xs:element name="PadBytes" type="xs:byte" '
        'minOccurs="0" maxOccurs="unbounded" /></xs:sequence>'
        '</xs:complexType></xs:element>'
        '</xs:sequence></xs:complexType></xs:schema>', encoding="utf-8")
    types = masshunter.parse_scan_xsd(str(xsd))
    assert types["ScanRecordType"] == [("ScanID", "xs:int")]
    assert masshunter.type_size(types, "ScanRecordType") == 4


def test_fractional_intensities_are_summed_as_floats():
    grid = masshunter._scatter_sum(
        np.array([0, 0, 2]), np.array([1.25, 2.5, 0.75]), 3)
    np.testing.assert_allclose(grid, [3.75, 0.0, 0.75])


def test_fractional_centroid_intensities_are_not_truncated():
    # yellow.D's MSPeak.bin stores abundances such as 10242.948; a cast to an
    # integer dropped the fraction.
    centroid = rb.read(os.path.join(INPUTS, "yellow.D"),
                       centroid=True).get_file("MSPeak.bin")
    intensities = centroid.scan(0)[1]
    assert intensities.dtype == np.float64
    assert np.any(intensities != np.floor(intensities))


# --- a synthetic single-quadrupole LC/MS run ---------------------------------
#
# Everything below is generated: a version 2.1-style MSScan.xsd whose scan
# record ends in an untyped Padding element (after the SpectrumParamValues and
# XSpecificParamType members), an MSScan.bin of such records, and an
# MSPeak.bin of split (all m/z, then all intensity) float64 blocks whose
# intensities are fractional. No vendor data is involved.

_SQ_XSD = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<xs:schema targetNamespace="http://tempuri.org/XMLSchema.xsd" '
    'xmlns:xs="http://www.w3.org/2001/XMLSchema" '
    'xmlns="http://tempuri.org/XMLSchema.xsd" version="2.1">'
    '<xs:complexType name="ScanRecordType"><xs:sequence>'
    '<xs:element name="ScanID" type="xs:int" />'
    '<xs:element name="ScanTime" type="xs:double" />'
    '<xs:element name="TIC" type="xs:double" />'
    '<xs:element name="BasePeakMZ" type="xs:double" />'
    '<xs:element name="CalibrationID" type="xs:short" minOccurs="0" />'
    '<xs:element name="IonPolarity" type="xs:short" minOccurs="0" />'
    '<xs:element name="SpectrumParamValues" type="SpectrumParamsType" '
    'maxOccurs="unbounded" />'
    '<xs:element name="XSpecificParamType" type="XSpecificParamType" '
    'minOccurs="0" />'
    '<xs:element name="Padding" minOccurs="0"><xs:complexType><xs:sequence>'
    '<xs:element name="PadBytes" type="xs:byte" minOccurs="0" '
    'maxOccurs="unbounded" /></xs:sequence></xs:complexType></xs:element>'
    '</xs:sequence></xs:complexType>'
    '<xs:complexType name="SpectrumParamsType"><xs:sequence>'
    '<xs:element name="SpectrumFormatID" type="xs:short" />'
    '<xs:element name="SpectrumOffset" type="xs:long" />'
    '<xs:element name="ByteCount" type="xs:int" />'
    '<xs:element name="PointCount" type="xs:int" />'
    '<xs:element name="MinX" type="xs:double" />'
    '<xs:element name="MaxX" type="xs:double" />'
    '</xs:sequence></xs:complexType>'
    '<xs:complexType name="XSpecificParamType"><xs:sequence>'
    '<xs:element name="Offset" type="xs:long" />'
    '<xs:element name="ByteCount" type="xs:int" />'
    '</xs:sequence></xs:complexType></xs:schema>')

_SQ_CONTENTS = ('<?xml version="1.0" encoding="utf-8"?><Contents>'
                '<SeparationTechnique>3</SeparationTechnique></Contents>')

# MSScan.bin keeps the offset of its first record in a uint32 at 0x58.
_SQ_RECORDS_START = 0x60


def _synthetic_scans(num_scans=12, seed=7):
    """Per-scan (time, m/z array, fractional intensity array)."""
    rng = np.random.default_rng(seed)
    scans = []
    for i in range(num_scans):
        count = int(rng.integers(3, 9))
        mzs = np.sort(rng.uniform(100.0, 1000.0, count)).round(1)
        intensities = rng.uniform(0.5, 150.0, count)
        scans.append((0.02 + i * 0.017, mzs, intensities))
    return scans


def _write_sq_binaries(folder, stem, scans):
    peaks = bytearray(b'\0' * 68)      # the payload starts past a header
    records = bytearray()
    for i, (time, mzs, intensities) in enumerate(scans):
        offset = len(peaks)
        peaks += mzs.astype('<f8').tobytes() + intensities.astype('<f8').tobytes()
        records += struct.pack(
            '<iddd hh hqiidd qi',
            i + 1, time, intensities.sum(), mzs[np.argmax(intensities)],
            0, 0,
            1, offset, 16 * len(mzs), len(mzs), mzs.min(), mzs.max(),
            0, 0)
    header = bytearray(_SQ_RECORDS_START)
    header[0x58:0x5C] = struct.pack('<I', _SQ_RECORDS_START)
    with open(os.path.join(folder, stem + ".MSScan.bin"), 'wb') as f:
        f.write(bytes(header) + bytes(records))
    with open(os.path.join(folder, stem + ".MSPeak.bin"), 'wb') as f:
        f.write(bytes(peaks))


def _make_single_quad_sirslt(tmp_path, scans):
    stem = "sq"
    folder = tmp_path / (stem + ".sirslt")
    folder.mkdir()
    _write_sq_binaries(str(folder), stem, scans)
    _make_dx(
        str(folder / (stem + ".dx")),
        acmd=lambda text: text.replace(
            '</Signals>', _MS_SIGNAL.format(stem=stem) + '</Signals>'),
        extra={"MSData/MSScan.xsd": _SQ_XSD,
               "MSData/Contents.xml": _SQ_CONTENTS})
    return str(folder)


def test_struct_layout_matches_the_synthetic_schema(tmp_path):
    # Guards the generator: the packed record must be exactly the size the
    # schema describes, or the test below would prove nothing.
    xsd = tmp_path / "MSScan.xsd"
    xsd.write_text(_SQ_XSD, encoding="utf-8")
    types = masshunter.parse_scan_xsd(str(xsd))
    assert masshunter.type_size(types, "ScanRecordType") == \
        struct.calcsize('<iddd hh hqiidd qi')


def test_single_quad_ms_is_read_without_truncation(tmp_path):
    scans = _synthetic_scans()
    path = _make_single_quad_sirslt(tmp_path, scans)
    datadir = rb.read(path, centroid=True)
    centroid = datadir.get_file("MSPeak.bin")
    np.testing.assert_allclose(centroid.xlabels, [t for t, _, _ in scans])
    for i, (_, mzs, intensities) in enumerate(scans):
        got_mz, got_intensity = centroid.scan(i)
        np.testing.assert_array_equal(got_mz, mzs)
        assert got_intensity.dtype == np.float64
        np.testing.assert_array_equal(got_intensity, intensities)
    # With no .acaml, the MS Contents.xml says LC.
    assert datadir.metadata['technique'] == 'LC'


def test_single_quad_ms_binned_keeps_every_scans_total(tmp_path):
    scans = _synthetic_scans()
    path = _make_single_quad_sirslt(tmp_path, scans)
    binned = rb.read(path, centroid=True, bin_width=1.0).get_file("MSPeak.bin")
    np.testing.assert_allclose(
        binned.data.sum(axis=1), [i.sum() for _, _, i in scans], rtol=1e-12)


# --- real folders, when provided ----------------------------------------------

_EXAMPLES = os.environ.get("RAINBOW_SIRSLT_EXAMPLES")


@pytest.mark.skipif(not _EXAMPLES, reason="RAINBOW_SIRSLT_EXAMPLES not set")
def test_real_sirslt_folders():
    folders = sorted(glob.glob(os.path.join(_EXAMPLES, "*.sirslt")))
    assert folders
    for folder in folders:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            datadir = rb.read(folder, centroid=True)
        assert datadir.metadata['technique'] in ('LC', 'GC')
        if datadir.by_name.get("MSPEAK.BIN") is not None:
            _assert_centroid_matches_recorded_tic(folder, datadir)


def _assert_centroid_matches_recorded_tic(folder, datadir):
    """Each scan's peaks sum to the TIC the instrument recorded for it."""
    centroid = datadir.get_file("MSPeak.bin")
    dx_path, _ = sirslt.find_files(folder)
    with zipfile.ZipFile(dx_path) as archive:
        run = sirslt._Run(folder, None, archive)
        with tempfile.TemporaryDirectory() as tmp:
            xsd = os.path.join(tmp, "MSScan.xsd")
            with open(xsd, 'wb') as f:
                f.write(archive.read(run.ms.archived["MSScan.xsd"]))
            records = masshunter.read_scan_records(
                run.ms.beside["MSScan.bin"], masshunter.parse_scan_xsd(xsd))
    recorded = np.array([record['TIC'] for record in records])
    summed = np.array([centroid.scan(i)[1].sum()
                       for i in range(len(centroid.xlabels))])
    np.testing.assert_allclose(summed, recorded, rtol=1e-9)


# --- real, anonymised folders ------------------------------------------------

OLIVE = os.path.join(INPUTS, "olive.sirslt")
PLUM = os.path.join(INPUTS, "plum.sirslt")
LIME = os.path.join(INPUTS, "lime.sirslt")


def _spectrum_over_channel_at_peak(datadir):
    """The spectrum at the channel's wavelength over the channel, at its
    largest peak."""
    spectrum = datadir.get_file("DAD1I.UV")
    channel = datadir.get_file("DAD1A.CH")
    column = int(np.argmin(np.abs(spectrum.ylabels - 220)))
    peak = int(np.argmax(channel.data[:, 0]))
    return spectrum.data[peak, column] / channel.data[peak, 0]


def test_olive_reads_its_detector_signals_and_metadata():
    with warnings.catch_warnings():
        warnings.simplefilter("error")      # no ScaleFactor or MS warning
        datadir = rb.read(OLIVE)
    assert sorted(df.name for df in datadir.datafiles) == \
        ["DAD1A.CH", "DAD1I.UV"]
    spectrum = datadir.get_file("DAD1I.UV")
    assert spectrum.data.shape == (4801, 101)
    np.testing.assert_array_equal(spectrum.ylabels[[0, -1]], [200, 400])
    np.testing.assert_allclose(spectrum.data.max(), 1242.9733648896217,
                               rtol=1e-12)
    channel = datadir.get_file("DAD1A.CH")
    assert channel.data.shape == (4801, 1)
    np.testing.assert_allclose(channel.data.max(), 831.3445448875427,
                               rtol=1e-12)
    metadata = datadir.metadata
    assert metadata['technique'] == 'LC'
    assert metadata['centroid_available'] is True
    assert 'hrms_available' not in metadata
    assert metadata['sample'] == 'QC HSS A-EVENT'
    assert metadata['injection_volume'] == {'value': 0.5, 'unit': 'µL'}
    assert metadata['instrument']['name'] == 'LCMS1'
    assert [m['type'] for m in metadata['instrument']['modules']] == \
        ['SingleQuad', 'Pump', 'ColumnCompartment', 'Detector', 'Sampler']
    assert metadata['ms_devices'] == [{
        'name': 'SQ', 'model': 'LC/MSD iQ', 'serial_no': 'SG00000001',
        'firmware': '8.2.6'}]


def test_olive_spectrum_is_scaled_like_its_channel():
    # The manifest's <ScaleFactor> is 1000 * 2**-27 (a UHPLC DAD). Scaled by
    # it, the spectrum at 220 nm agrees with the 220 nm signal of the same run
    # at the run's largest peak; the 2**-17 rainbow applied before read it
    # 2.4% high.
    assert abs(_spectrum_over_channel_at_peak(rb.read(OLIVE)) - 1) < 0.01


def test_plum_hplc_spectrum_is_scaled_like_its_channel():
    # An HPLC DAD records <ScaleFactor> 1000 * 2**-21, 64 times a UHPLC DAD's.
    # Scaled by it, the spectrum at 220 nm agrees with the 220 nm signal of
    # the same run; the 2**-17 rainbow applied before read it 62.5x low.
    with zipfile.ZipFile(os.path.join(PLUM, "plum.dx")) as archive:
        _, signals = openlab._parse_manifest(archive)
    factors = [s['scale_factor'] for s in signals.values()
               if s['encoding'].endswith('Spectra131')]
    assert factors == [1000 * 2 ** -21]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        datadir = rb.read(PLUM)
    assert abs(_spectrum_over_channel_at_peak(datadir) - 1) < 0.01
    spectrum = datadir.get_file("DAD1I.UV")
    assert spectrum.data.shape == (7200, 106)
    np.testing.assert_array_equal(spectrum.ylabels[[0, -1]], [190, 400])
    np.testing.assert_allclose(spectrum.data.max(), 1152.9016494750977,
                               rtol=1e-12)
    np.testing.assert_allclose(datadir.get_file("DAD1A.CH").data.max(),
                               726.5162467956543, rtol=1e-12)


def test_plum_metadata():
    datadir = rb.read(PLUM, telemetry=True)
    assert sorted(df.name for df in datadir.datafiles) == \
        ["DAD1A.CH", "DAD1I.UV"]
    assert len(datadir.analog) == 11
    metadata = datadir.metadata
    assert metadata['technique'] == 'LC'
    assert metadata['instrument']['name'] == 'HPLC2'
    assert [m['part_no'] for m in metadata['instrument']['modules']] == \
        ['G7112B', 'G7129A', 'G7116A', 'G7115A']
    assert 'centroid_available' not in metadata
    assert rb.read_metadata(PLUM)['metadata'] == rb.read(PLUM).metadata


def test_olive_centroids_are_the_recorded_scans():
    datadir = rb.read(OLIVE, centroid=True)
    centroid = datadir.get_file("MSPeak.bin")
    # MSData/MSTS.xml records 237 scans, and MSScan.bin holds as many.
    assert len(centroid.xlabels) == 237
    assert sum(len(centroid.scan(i)[0]) for i in range(237)) == 239200
    mzs, intensities = centroid.scan(100)
    assert intensities.dtype == np.float64
    np.testing.assert_allclose(mzs[:3], [100.69999695, 102.0, 102.90000153])
    np.testing.assert_allclose(
        intensities[:3], [227.69114685, 1298.63378906, 237.96624756])
    assert np.all(mzs >= 100) and np.all(mzs <= 1000)
    _assert_centroid_matches_recorded_tic(OLIVE, datadir)


def test_olive_centroids_on_unit_bins():
    centroid = rb.read(OLIVE, centroid=True).get_file("MSPeak.bin")
    binned = rb.read(OLIVE, centroid=True, bin_width=1).get_file("MSPeak.bin")
    assert binned.data.shape == (237, 901)
    assert binned.data.dtype == np.float64
    np.testing.assert_array_equal(binned.ylabels[[0, -1]], [100, 1000])
    np.testing.assert_allclose(
        binned.data.sum(axis=1),
        [centroid.scan(i)[1].sum() for i in range(237)], rtol=1e-12)


def test_olive_metadata_matches_its_read():
    listing = rb.read_metadata(OLIVE)
    assert 'MSPeak.bin' in listing['datafiles']
    assert listing['metadata'] == rb.read(OLIVE).metadata


def test_lime_is_an_hplc_run_without_ms():
    datadir = rb.read(LIME, centroid=True)
    assert [df.name for df in datadir.datafiles] == ["DAD1A.CH"]
    assert datadir.metadata['technique'] == 'LC'
    assert 'centroid_available' not in datadir.metadata
    assert 'ms_devices' not in datadir.metadata
    assert sirslt.technique(LIME) == 'LC'


# --- MS binaries found where the manifest does not quite say -----------------

def _ms_signal(paths):
    return _MS_SIGNAL.replace(
        '{stem}.MSPeak.bin,{stem}.MSScan.bin', ','.join(paths))


def test_manifest_paths_with_directories_find_the_files_beside(tmp_path):
    # <ExternalElementPaths> written with a directory, relative or absolute,
    # and in another case, still names the files beside the archive.
    paths = ["..\\run.MSPEAK.BIN", "C:\\Results\\x.sirslt\\run.msscan.bin"]
    path = _make_sirslt(tmp_path, ms=True)
    dx = os.path.join(path, "run.dx")
    with zipfile.ZipFile(dx) as archive:
        members = {m: archive.read(m) for m in archive.namelist()}
    text = members['injection.acmd'].decode('utf-8-sig')
    text = text.replace('run.MSPeak.bin,run.MSScan.bin', ','.join(paths))
    members['injection.acmd'] = text.encode('utf-8')
    with zipfile.ZipFile(dx, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    centroid = rb.read(path, centroid=True).get_file("MSPeak.bin")
    reference = rb.read(os.path.join(INPUTS, "yellow.D"),
                        centroid=True).get_file("MSPeak.bin")
    np.testing.assert_array_equal(centroid.xlabels, reference.xlabels)


def test_manifest_names_that_match_nothing_fall_back_to_a_scan(tmp_path):
    def wrong_names(text):
        return text.replace('</Signals>', _ms_signal(
            ["elsewhere.MSPeak.bin", "elsewhere.MSScan.bin"]) + '</Signals>')
    path = _make_sirslt(tmp_path, acmd=wrong_names)
    for member in ("MSScan.bin", "MSPeak.bin"):
        shutil.copyfile(os.path.join(YELLOW_ACQDATA, member),
                        os.path.join(path, "run." + member))
    extra = {}
    for member in ("MSScan.xsd", "Contents.xml", "Devices.xml", "MSTS.xml"):
        with open(os.path.join(YELLOW_ACQDATA, member), 'rb') as f:
            extra["MSData/" + member] = f.read()
    _make_dx(os.path.join(path, "run.dx"), acmd=wrong_names, extra=extra)
    assert rb.read(path).metadata['centroid_available'] is True
    assert rb.read(path, centroid=True).get_file("MSPeak.bin") is not None


def test_ms_binaries_inside_the_archive_are_read(tmp_path):
    # A run whose binaries were kept under MSData/ rather than beside it.
    extra = {}
    for member in ("MSScan.xsd", "Contents.xml", "Devices.xml", "MSTS.xml",
                   "MSScan.bin", "MSPeak.bin"):
        with open(os.path.join(YELLOW_ACQDATA, member), 'rb') as f:
            extra["MSData/" + member] = f.read()
    path = _make_sirslt(tmp_path, extra=extra)
    assert rb.read_metadata(path)['metadata']['centroid_available'] is True
    centroid = rb.read(path, centroid=True).get_file("MSPeak.bin")
    reference = rb.read(os.path.join(INPUTS, "yellow.D"),
                        centroid=True).get_file("MSPeak.bin")
    np.testing.assert_array_equal(centroid.xlabels, reference.xlabels)


def test_sidecar_names_are_matched_without_regard_to_case(tmp_path):
    path = _make_sirslt(tmp_path, ms=True)
    dx = os.path.join(path, "run.dx")
    with zipfile.ZipFile(dx) as archive:
        members = {m: archive.read(m) for m in archive.namelist()}
    members['msdata/msscan.xsd'] = members.pop('MSData/MSScan.xsd')
    with zipfile.ZipFile(dx, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    assert rb.read(path, centroid=True).get_file("MSPeak.bin") is not None


def test_ms_without_its_schema_warns_and_is_not_reported(tmp_path):
    # read and read_metadata decide availability alike: neither offers MS
    # data that cannot be decoded, and both say why.
    path = _make_sirslt(tmp_path, ms=True)
    dx = os.path.join(path, "run.dx")
    with zipfile.ZipFile(dx) as archive:
        members = {m: archive.read(m) for m in archive.namelist()
                   if not m.endswith("MSScan.xsd")}
    with zipfile.ZipFile(dx, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    with pytest.warns(UserWarning, match="MSScan.xsd"):
        listing = rb.read_metadata(path)
    assert 'centroid_available' not in listing['metadata']
    assert 'MSPeak.bin' not in listing['datafiles']
    with pytest.warns(UserWarning, match="MSScan.xsd"):
        datadir = rb.read(path, centroid=True)
    assert 'MS' not in datadir.detectors
    assert 'centroid_available' not in datadir.metadata


def test_read_metadata_opens_the_archive_once(tmp_path, monkeypatch):
    path = _make_sirslt(tmp_path, ms=True)
    opened = []
    real = zipfile.ZipFile

    def counting(*args, **kwargs):
        opened.append(args[0])
        return real(*args, **kwargs)
    monkeypatch.setattr(sirslt.zipfile, "ZipFile", counting)
    rb.read_metadata(path)
    assert len(opened) == 1


# --- a .D is a .D ------------------------------------------------------------

@pytest.mark.parametrize("name", ["copy.D", "copy"])
def test_a_d_folder_holding_a_dx_and_acaml_stays_a_d(tmp_path, name):
    reference = rb.read(os.path.join(INPUTS, "red.D"))
    path = str(tmp_path / name)
    shutil.copytree(os.path.join(INPUTS, "red.D"), path)
    shutil.copyfile(TEAL, os.path.join(path, "stray.dx"))
    with open(os.path.join(path, "stray.acaml"), 'w', encoding='utf-8') as f:
        f.write(_acaml())
    assert not sirslt.is_sirslt(path)
    datadir = rb.read(path, format='agilent')
    assert sorted(df.name for df in datadir.datafiles) == \
        sorted(df.name for df in reference.datafiles)


# --- a spectrum without its scale factor -------------------------------------

def test_a_spectrum_without_a_scale_factor_warns(tmp_path):
    reference = rb.read(TEAL).get_file("DAD1I.UV")

    def no_factor(text):
        return text.replace('<ScaleFactor>7.4505805969238281E-06',
                            '<ScaleFactor>0')
    dest = str(tmp_path / "old.dx")
    _make_dx(dest, acmd=no_factor)
    with pytest.warns(UserWarning, match="ScaleFactor"):
        spectrum = rb.read(dest).get_file("DAD1I.UV")
    # The fallback is the UHPLC factor teal.dx records, so it reads the same.
    np.testing.assert_allclose(spectrum.data, reference.data)


# --- ECD is no evidence of a GC ----------------------------------------------

def test_an_ecd_does_not_make_a_run_gc(tmp_path):
    def ecd(text):
        return text.replace('<DeviceName>DAD</DeviceName>',
                            '<DeviceName>ECD</DeviceName>')
    path = _make_sirslt(tmp_path, acaml=False, acmd=ecd)
    assert sirslt.technique(path) is None


def test_an_fid_still_makes_a_run_gc(tmp_path):
    def fid(text):
        return text.replace('<DeviceName>DAD</DeviceName>',
                            '<DeviceName>FID</DeviceName>')
    path = _make_sirslt(tmp_path, acaml=False, acmd=fid)
    assert sirslt.technique(path) == 'GC'


# --- the scan schema's inline types ------------------------------------------

def _schema(elements):
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<xs:schema targetNamespace="http://tempuri.org/XMLSchema.xsd" '
        'xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'xmlns="http://tempuri.org/XMLSchema.xsd">'
        '<xs:complexType name="ScanRecordType"><xs:sequence>'
        + elements + '</xs:sequence></xs:complexType></xs:schema>')


_PADDING = ('<xs:element name="Padding" minOccurs="0"><xs:complexType>'
            '<xs:sequence><xs:element name="PadBytes" type="xs:byte" '
            'minOccurs="0" maxOccurs="unbounded" /></xs:sequence>'
            '</xs:complexType></xs:element>')
_INLINE = ('<xs:element name="Extra"><xs:complexType><xs:sequence>'
           '<xs:element name="A" type="xs:int" /></xs:sequence>'
           '</xs:complexType></xs:element>')
_SCAN_ID = '<xs:element name="ScanID" type="xs:int" />'


@pytest.mark.parametrize("elements", [
    _PADDING + _SCAN_ID,                               # Padding not last
    _SCAN_ID + _PADDING.replace(' minOccurs="0"', '', 1),   # not optional
    _SCAN_ID + _INLINE,                                # not Padding
], ids=["padding-not-last", "padding-required", "other-inline-type"])
def test_scan_xsd_refuses_any_other_inline_type(tmp_path, elements):
    xsd = tmp_path / "MSScan.xsd"
    xsd.write_text(_schema(elements), encoding="utf-8")
    with pytest.raises(ValueError, match="inline type"):
        masshunter.parse_scan_xsd(str(xsd))


# --- centroid intensities are float64 everywhere -----------------------------

def test_whole_number_centroid_intensities_are_float64_too(tmp_path):
    # A run whose abundances happen to be whole numbers gets the same dtype as
    # one whose are not, so runs of one sequence agree.
    scans = [(t, mzs, np.round(intensities))
             for t, mzs, intensities in _synthetic_scans()]
    path = _make_single_quad_sirslt(tmp_path, scans)
    centroid = rb.read(path, centroid=True).get_file("MSPeak.bin")
    for i in range(len(scans)):
        assert centroid.scan(i)[1].dtype == np.float64
    binned = rb.read(path, centroid=True, bin_width=1.0).get_file("MSPeak.bin")
    assert binned.data.dtype == np.float64


def test_an_empty_float_grid_is_float64():
    assert masshunter._scatter_sum(
        np.array([], dtype=np.int64), np.array([], dtype=np.float64),
        4).dtype == np.float64
    labels, grid = masshunter.bin_to_grid(
        np.array([100.0]), np.array([1.5]), np.array([0]), 1, 0, 1.0,
        labels_only=True)
    assert grid.dtype == np.float64
