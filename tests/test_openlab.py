"""
Unit tests for the Agilent OpenLab CDS (.dx) manifest parser.

The ``teal`` case in test_agilent.py exercises the end-to-end happy path on a
real archive, but that archive is a standby/flush injection: its sample name
and vial are empty and its injection volume is zero. These tests drive the
manifest parser directly with synthetic ``injection.acmd`` documents so the
populated paths (a real injection volume, a sample and vial, the Sig=/Ref=
optics clause) and the skip-empty behavior are both covered.

"""
import io
import zipfile

import pytest

from rainbow.agilent import openlab


def _archive(acmd_bytes):
    """
    Builds an in-memory .dx-like archive holding one injection.acmd.

    Passing ``None`` omits the manifest entirely, modeling a malformed archive.

    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        if acmd_bytes is not None:
            archive.writestr('injection.acmd', acmd_bytes)
    buf.seek(0)
    return zipfile.ZipFile(buf)


def _acmd(injection_info='', signals=''):
    """Wraps manifest fragments in a minimal ACMD document."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<ACMD xmlns="urn:schemas-agilent-com:acmd20">'
        '<InjectionInfo>' + injection_info +
        '<Signals>' + signals + '</Signals>'
        '</InjectionInfo></ACMD>'
    ).encode('utf-8')


def _signal(trace_id, description, device='DAD', encoding='Signal179'):
    return (
        '<Signal>'
        '<Encoding>Agilent.OpenLab.Rawdata/' + encoding + '</Encoding>'
        '<TraceId>' + trace_id + '</TraceId>'
        '<DeviceName>' + device + '</DeviceName>'
        '<Description>' + description + '</Description>'
        '<Units>mAU</Units>'
        '</Signal>'
    )


# --- _parse_optics ---------------------------------------------------------

def test_parse_optics_full():
    assert openlab._parse_optics("DAD1A,Sig=210.0,4.0  Ref=360.0,100.0") == {
        'wavelength': 210.0,
        'bandwidth': 4.0,
        'reference_wavelength': 360.0,
        'reference_bandwidth': 100.0,
    }


def test_parse_optics_integer_values_and_no_reference():
    # Integer-style values still parse as floats; "Ref=off" has no numbers,
    # so the reference fields are omitted rather than guessed.
    assert openlab._parse_optics("VWD1A,Sig=254,4  Ref=off") == {
        'wavelength': 254.0,
        'bandwidth': 4.0,
    }


@pytest.mark.parametrize("description", [
    "DAD1I,DAD: Spectrum",   # a spectrum, not a single wavelength
    "WPS1A,Temperature",     # telemetry
    "PMP1B,Pressure",        # telemetry
    "",                      # no description at all
])
def test_parse_optics_absent(description):
    assert openlab._parse_optics(description) == {}


# --- _parse_manifest: run-level metadata -----------------------------------

def test_manifest_populated_injection():
    injection = (
        '<RunDateTime>2025-01-02T03:04:05.0000000-05:00</RunDateTime>'
        '<AcquisitionMethod>C:\\Methods\\assay.amx</AcquisitionMethod>'
        '<SampleName>Caffeine Std</SampleName>'
        '<Location>P1-A1</Location>'
        '<RunOperator>jdoe</RunOperator>'
        '<SequenceLine>7</SequenceLine>'
        '<InjectionVolume>5</InjectionVolume>'
        '<InjectionVolumeUnits>µl</InjectionVolumeUnits>'
    )
    metadata, _ = openlab._parse_manifest(_archive(_acmd(injection)))
    assert metadata == {
        'vendor': 'Agilent',
        'date': '2025-01-02T03:04:05.0000000-05:00',
        'method': 'assay.amx',              # basename of the Windows path
        'sample': 'Caffeine Std',
        'vialpos': 'P1-A1',
        'operator': 'jdoe',
        'seqline': 7,                        # parsed to int
        'injection_volume': 5.0,             # parsed to float
        'injection_volume_unit': 'µl',
    }


def test_manifest_skips_empty_and_zero():
    # Mirrors the standby-flush fixture: empty sample/vial and a zero
    # injection volume should leave those keys absent.
    injection = (
        '<RunDateTime>2025-06-19T20:30:07.0000000-04:00</RunDateTime>'
        '<AcquisitionMethod>standbyflush.amx</AcquisitionMethod>'
        '<SampleName></SampleName>'
        '<Location></Location>'
        '<RunOperator>SYSTEM (SYSTEM)</RunOperator>'
        '<SequenceLine>1</SequenceLine>'
        '<InjectionVolume>0</InjectionVolume>'
        '<InjectionVolumeUnits></InjectionVolumeUnits>'
    )
    metadata, _ = openlab._parse_manifest(_archive(_acmd(injection)))
    assert metadata == {
        'vendor': 'Agilent',
        'date': '2025-06-19T20:30:07.0000000-04:00',
        'method': 'standbyflush.amx',
        'operator': 'SYSTEM (SYSTEM)',
        'seqline': 1,
    }
    assert 'sample' not in metadata
    assert 'vialpos' not in metadata
    assert 'injection_volume' not in metadata
    assert 'injection_volume_unit' not in metadata


def test_manifest_non_numeric_sequence_line():
    # A non-integer SequenceLine is kept verbatim rather than dropped.
    metadata, _ = openlab._parse_manifest(
        _archive(_acmd('<SequenceLine>1A</SequenceLine>')))
    assert metadata['seqline'] == '1A'


@pytest.mark.parametrize("acmd_bytes", [None, b'not valid xml <<<'])
def test_manifest_missing_or_malformed_returns_defaults(acmd_bytes):
    metadata, signals = openlab._parse_manifest(_archive(acmd_bytes))
    assert metadata == {'vendor': 'Agilent'}
    assert signals == {}


# --- _parse_manifest: per-signal optics ------------------------------------

def test_manifest_signal_carries_optics():
    signals_xml = (
        _signal('ABC-123', 'DAD1A,Sig=210.0,4.0  Ref=360.0,100.0') +
        _signal('SPEC-1', 'DAD1I,DAD: Spectrum', encoding='Spectra131')
    )
    _, signals = openlab._parse_manifest(_archive(_acmd('', signals_xml)))

    # TraceId is lowercased to key the signal map.
    channel = signals['abc-123']
    assert channel['wavelength'] == 210.0
    assert channel['bandwidth'] == 4.0
    assert channel['reference_wavelength'] == 360.0
    assert channel['reference_bandwidth'] == 100.0

    # A spectrum has no Sig= clause, so it carries no optics.
    spectrum = signals['spec-1']
    assert 'wavelength' not in spectrum


# --- _file_metadata: optics propagation ------------------------------------

def test_file_metadata_includes_present_optics():
    signal = {
        'device': 'DAD',
        'description': 'DAD1A,Sig=210.0,4.0  Ref=360.0,100.0',
        'unit': 'mAU',
        'wavelength': 210.0,
        'bandwidth': 4.0,
        'reference_wavelength': 360.0,
        'reference_bandwidth': 100.0,
    }
    assert openlab._file_metadata(signal) == signal


def test_file_metadata_omits_absent_optics():
    signal = {
        'device': 'WPS',
        'description': 'WPS1A,Temperature',
        'unit': '°C',
    }
    # No optics keys present, so none are invented.
    assert openlab._file_metadata(signal) == signal
