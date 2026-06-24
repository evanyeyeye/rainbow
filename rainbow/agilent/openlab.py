"""
Methods for parsing Agilent OpenLab CDS 2.x (.dx) files.

A .dx file is an Open Packaging Conventions (zip) archive. Its binary
payloads have GUID filenames; the injection.acmd manifest maps each GUID to
its device, description, units, and encoding. rainbow reuses the existing
Chemstation decoders for the payloads:

    .UV (Spectra131)         -> a DAD spectrum             -> parse_uv
    .CH (Signal179)          -> a single-wavelength signal -> parse_ch
    .IT (InstrumentTrace179) -> instrument telemetry       -> parse_ch

Learn more about this file format :ref:`here <dx>`.

"""
import os
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET

from rainbow.agilent import chemstation
from rainbow.datafile import DataFile
from rainbow.datadirectory import DataDirectory

# The DAD spectrum (.UV) in a .dx stores absorbance as doubles carrying an
# extra 17-bit fixed-point shift relative to the older Chemstation .uv format.
# parse_uv applies the in-file scaling factor but not this shift, so its output
# must be multiplied by 2**-17 to recover the physical mAU. This was verified
# against the .CH single-wavelength channels, which share the run and are
# already correctly scaled by parse_ch. The .CH and .IT ("179") payloads need
# no correction.
UV_FIXED_POINT_SHIFT = 2 ** -17

# Namespace of the injection.acmd manifest.
_ACMD_NS = {'a': 'urn:schemas-agilent-com:acmd20'}

# Payload extensions that rainbow knows how to decode.
_DATA_EXTS = ('.uv', '.ch', '.it')

# Single-wavelength DAD/MWD/VWD channels encode their optics in the signal
# description, e.g. "DAD1A,Sig=210.0,4.0  Ref=360.0,100.0": the signal
# wavelength and bandwidth, then (optionally) the reference wavelength and
# bandwidth, all in nm. Spectra ("DAD1I,DAD: Spectrum") and telemetry traces
# carry no Sig= clause.
_SIG_RE = re.compile(r'Sig=([\d.]+),([\d.]+)')
_REF_RE = re.compile(r'Ref=([\d.]+),([\d.]+)')


def read(path, precision='auto', requested_files=None, telemetry=False):
    """
    Reads an Agilent OpenLab CDS .dx archive.

    Instrument telemetry (.IT traces such as pressure and temperature) is
    skipped unless ``telemetry`` is set, since most users only want the
    detector signals. Telemetry that is named explicitly in
    ``requested_files`` is always parsed.

    Args:
        path (str): Path of the .dx file.
        precision (int, optional): Number of decimals to round ylabels.
        requested_files (list, optional): Lowercased names to parse.
        telemetry (bool, optional): Flag for parsing .IT telemetry traces.

    Returns:
        DataDirectory representing the .dx archive, or None if it is empty.

    """
    # .dx archives hold UV / unit-resolution data, so 'auto' means whole numbers.
    if precision == 'auto':
        precision = 0
    with zipfile.ZipFile(path) as archive:
        dir_metadata, signals = _parse_manifest(archive)

        datafiles = []
        used_names = set()
        with tempfile.TemporaryDirectory() as tmp:
            for member in archive.namelist():
                base = os.path.basename(member)
                guid, ext = os.path.splitext(base)
                if ext.lower() not in _DATA_EXTS:
                    continue
                signal = signals.get(guid.lower(), {})
                name = _name_for(signal, guid, ext, used_names)
                requested = requested_files is not None and (
                    name.lower() in requested_files or
                    base.lower() in requested_files)
                if requested_files is not None and not requested:
                    continue
                # Telemetry is opt-in unless requested by name.
                if ext.lower() == '.it' and not telemetry and not requested:
                    continue

                tmppath = os.path.join(tmp, base)
                with open(tmppath, 'wb') as out:
                    out.write(archive.read(member))

                datafile = _parse_member(tmppath, name, ext, signal)
                if datafile is not None:
                    datafiles.append(datafile)

    if not datafiles:
        return None
    return DataDirectory(path, datafiles, dir_metadata)


def read_metadata(path):
    """
    Reads metadata from an Agilent OpenLab CDS .dx archive.

    Args:
        path (str): Path of the .dx file.

    Returns:
        Dictionary containing a list of datafiles and the metadata.

    """
    with zipfile.ZipFile(path) as archive:
        dir_metadata, _ = _parse_manifest(archive)
        datafiles = [
            os.path.basename(member) for member in archive.namelist()
            if os.path.splitext(member)[1].lower() in _DATA_EXTS]
    return {'datafiles': datafiles, 'metadata': dir_metadata}


def _parse_member(tmppath, name, ext, signal):
    """
    Decodes one extracted .dx payload into a DataFile.

    The data values come from the existing Chemstation decoders; the name,
    detector, and metadata are taken from the manifest because the binaries
    only carry GUID filenames and a generic "179" header.

    """
    ext = ext.lower()
    if ext == '.uv':
        datafile = chemstation.parse_uv(tmppath)
        if datafile is None:
            return None
        data = datafile.data * UV_FIXED_POINT_SHIFT
        detector = 'UV'
    else:
        # .ch and .it share the single-channel "179" container.
        datafile = chemstation.parse_ch(tmppath)
        if datafile is None:
            return None
        data = datafile.data
        detector = _classify(signal)

    return DataFile(
        name, detector, datafile.xlabels, datafile.ylabels, data,
        _file_metadata(signal))


def _parse_manifest(archive):
    """
    Parses the injection.acmd manifest of a .dx archive.

    Returns:
        Tuple of ``(dir_metadata, signals)``, where ``signals`` maps each
        lowercased trace GUID to its per-trace metadata.

    """
    dir_metadata = {'vendor': "Agilent"}
    signals = {}

    try:
        root = ET.fromstring(archive.read('injection.acmd'))
    except (KeyError, ET.ParseError):
        return dir_metadata, signals

    for sig in root.findall('.//a:Signal', _ACMD_NS):
        guid = _text(sig, 'TraceId').lower()
        if not guid:
            continue
        entry = {
            'encoding': _text(sig, 'Encoding'),
            'device': _text(sig, 'DeviceName'),
            'description': _text(sig, 'Description'),
            'unit': _text(sig, 'Units'),
        }
        entry.update(_parse_optics(entry['description']))
        signals[guid] = entry

    info = root.find('.//a:InjectionInfo', _ACMD_NS)
    if info is not None:
        date = _text(info, 'RunDateTime')
        if date:
            dir_metadata['date'] = date
        method = _text(info, 'AcquisitionMethod')
        if method:
            dir_metadata['method'] = method.replace('\\', '/').split('/')[-1]
        sample = _text(info, 'SampleName')
        if sample:
            dir_metadata['sample'] = sample
        vialpos = _text(info, 'Location')
        if vialpos:
            dir_metadata['vialpos'] = vialpos
        operator = _text(info, 'RunOperator')
        if operator:
            dir_metadata['operator'] = operator
        seqline = _text(info, 'SequenceLine')
        if seqline:
            try:
                dir_metadata['seqline'] = int(seqline)
            except ValueError:
                dir_metadata['seqline'] = seqline
        # A standby/flush injection reports a volume of 0, which carries no
        # information; only record a real injection volume.
        volume = _text(info, 'InjectionVolume')
        try:
            volume = float(volume)
        except ValueError:
            volume = 0.0
        if volume:
            dir_metadata['injection_volume'] = volume
            units = _text(info, 'InjectionVolumeUnits')
            if units:
                dir_metadata['injection_volume_unit'] = units

    return dir_metadata, signals


def _classify(signal):
    """
    Maps an OpenLab trace to a rainbow detector.

    Returns None for instrument telemetry, which rainbow treats as analog data.

    """
    encoding = signal.get('encoding', '')
    if encoding.startswith('Agilent.OpenLab.Rawdata/InstrumentTrace'):
        return None
    device = signal.get('device', '').upper()
    if device[:3] in ('DAD', 'MWD', 'VWD') or signal.get('unit') == 'mAU':
        return 'UV'
    if device.startswith('FID'):
        return 'FID'
    if device.startswith('RID'):
        return 'RID'
    return None


def _name_for(signal, guid, ext, used_names):
    """
    Builds a readable, unique name for a trace from its manifest description.

    The description begins with the signal code (e.g. "DAD1A"); GUID filenames
    are not meaningful to users. Falls back to the GUID if no code is present.

    """
    description = signal.get('description', '')
    code = description.split(',', 1)[0].strip()
    base = code or signal.get('device', '') or guid
    name = base + ext
    if name.upper() in used_names:
        name = "{}_{}{}".format(base, guid[:8], ext)
    used_names.add(name.upper())
    return name


def _parse_optics(description):
    """
    Extracts wavelength settings from a signal description, if present.

    Returns a dict with any of ``wavelength``, ``bandwidth``,
    ``reference_wavelength``, and ``reference_bandwidth`` (in nm), parsed from
    the ``Sig=``/``Ref=`` clause of a single-wavelength channel. Spectra and
    telemetry traces have no such clause and yield an empty dict.

    """
    optics = {}
    sig = _SIG_RE.search(description)
    if sig:
        optics['wavelength'] = float(sig.group(1))
        optics['bandwidth'] = float(sig.group(2))
    ref = _REF_RE.search(description)
    if ref:
        optics['reference_wavelength'] = float(ref.group(1))
        optics['reference_bandwidth'] = float(ref.group(2))
    return optics


def _file_metadata(signal):
    """Builds per-trace metadata from the manifest."""
    metadata = {}
    for key in ('device', 'description', 'unit'):
        value = signal.get(key)
        if value:
            metadata[key] = value
    for key in ('wavelength', 'bandwidth',
                'reference_wavelength', 'reference_bandwidth'):
        if key in signal:
            metadata[key] = signal[key]
    return metadata


def _text(element, tag):
    """Returns the stripped text of a namespaced child, or ''."""
    value = element.findtext('a:' + tag, default='', namespaces=_ACMD_NS)
    return value.strip() if value else ''
