"""
Methods for reading Agilent OpenLab CDS result folders (.sirslt).

OpenLab CDS 2.x stores each single-injection result set as a ``.sirslt``
folder. Its files share the folder's stem::

    <name>.dx            OPC (zip) archive of the detector signals (UV, FID,
                         ...) and instrument telemetry. For an LC/MS run it
                         also carries the MS sidecars under MSData/
                         (MSScan.xsd, MSTS.xml, Contents.xml, Devices.xml).
    <name>.MSScan.bin    MassHunter scan records, written beside the archive
    <name>.MSPeak.bin    because they are too large for it. The manifest names
                         them in the MS signal's <ExternalElementPaths>.
    <name>.acaml         the result-set document: instrument (with its
                         separation technique and modules), sample, method.
    <name>.rx            processing results (not read).
    <name>.mfx           checksums of the files above (not read).
    *.amx, *.pmx, *.sqx, *.scml
                         acquisition method, processing method, sequence and
                         sampler configuration (not read).

The detector signals are decoded by :mod:`rainbow.agilent.openlab`, the reader
for a standalone .dx, and the MS data by :mod:`rainbow.agilent.masshunter`,
which already reads the same MSScan/MSPeak/MSProfile binaries inside a .D.

The same folder layout is written by OpenLab for both LC and GC instruments.
The run's separation technique is recorded in the metadata as ``technique``
(``'LC'`` or ``'GC'``), read from the instrument the result-set document
describes; see :func:`technique`.

"""
import os
import re
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET

from rainbow.agilent import openlab
from rainbow.datadirectory import DataDirectory

# ACAML <Technique> values, and MSData/Contents.xml <SeparationTechnique>
# codes ("Unspecified = 0, None = 1, GC = 2, LC = 3, CE = 4"), mapped onto the
# values rainbow.agilent.method.acquisition_technique gives a .D.
_ACAML_TECHNIQUES = {
    'liquidchromatography': 'LC',
    'gaschromatography': 'GC',
}
_CONTENTS_TECHNIQUES = {'2': 'GC', '3': 'LC'}

# Detectors that only exist on a gas chromatograph, as OpenLab names them.
_GC_DEVICES = ('FID', 'TCD', 'ECD', 'NPD', 'FPD', 'SCD', 'NCD')

# MS binaries are written beside the archive as "<name>.<file>", where <file>
# is the name MassHunter gives it inside a .D's AcqData folder.
_MS_FILE_RE = re.compile(r'(MS[A-Za-z_]*\.bin)$', re.IGNORECASE)


def is_sirslt(path):
    """
    Whether ``path`` is an OpenLab single-injection result folder.

    A folder named ``*.sirslt`` qualifies by its name; one renamed without the
    suffix qualifies by its contents (a .dx archive beside a .acaml document).

    """
    if not isinstance(path, str) or not os.path.isdir(path):
        return False
    if os.path.splitext(os.path.normpath(path))[1].lower() == '.sirslt':
        return True
    try:
        exts = {os.path.splitext(name)[1].lower() for name in os.listdir(path)}
    except OSError:
        return False
    return '.dx' in exts and '.acaml' in exts


def find_files(path):
    """
    Locates the archive and result-set document of a .sirslt folder.

    The files named after the folder are preferred, which is how OpenLab
    names them; otherwise the folder's only .dx/.acaml is used.

    Returns:
        Tuple ``(dx_path, acaml_path)``; either may be None.

    """
    stem = os.path.splitext(os.path.basename(os.path.normpath(path)))[0]
    found = {}
    for ext in ('.dx', '.acaml'):
        candidates = sorted(
            name for name in os.listdir(path)
            if name.lower().endswith(ext)
            and os.path.isfile(os.path.join(path, name)))
        preferred = [name for name in candidates
                     if os.path.splitext(name)[0] == stem]
        chosen = (preferred or candidates or [None])[0]
        found[ext] = os.path.join(path, chosen) if chosen else None
    return found['.dx'], found['.acaml']


def read(path, display_precision='auto', hrms=False, requested_files=None,
         telemetry=False, centroid=False, bin_width=None, peaks=False,
         labels_only=False):
    """
    Reads an Agilent OpenLab CDS .sirslt result folder.

    The detector signals are read from the folder's .dx archive exactly as
    :func:`rainbow.agilent.openlab.read` reads a standalone one. MS data, when
    the run recorded any, is read like a MassHunter .D's: the centroid
    (MSPeak.bin) under ``centroid`` and the profile (MSProfile.bin) under
    ``hrms``. A run with MS data that was not asked for is flagged in the
    metadata (``centroid_available`` / ``hrms_available``).

    A run that recorded no detector signal (a column flush, for instance, whose
    archive holds only instrument telemetry) still returns its metadata, with
    no datafiles.

    Args:
        path (str): Path of the .sirslt folder.
        display_precision (int or 'auto', optional): Decimals for displayed
            m/z labels.
        hrms (bool, optional): Flag for parsing the MS profile (MSProfile.bin).
        requested_files (list, optional): Lowercased names to parse.
        telemetry (bool, optional): Flag for parsing instrument telemetry.
        centroid (bool, optional): Flag for parsing the MS centroid spectrum
            (MSPeak.bin).
        bin_width (float, optional): m/z bin width in daltons for the MS data;
            see :func:`rainbow.agilent.read`.
        peaks (bool, optional): Integrated peaks are not read from a .sirslt;
            asking for them warns and leaves ``DataDirectory.peaks`` empty.

    Returns:
        DataDirectory representing the run.

    """
    dx_path, acaml_path = find_files(path)
    if dx_path is None:
        raise Exception(f"{path} holds no .dx archive to read.")

    datafiles, metadata, signals = openlab.read_archive(
        dx_path, requested_files, telemetry)

    ms_files = _ms_files(path, signals)
    if ms_files:
        names = {name.lower() for name in ms_files}
        want_centroid = centroid and 'mspeak.bin' in names
        want_profile = hrms and 'msprofile.bin' in names
        if want_centroid or want_profile:
            datafiles.extend(_read_ms(
                dx_path, ms_files, display_precision, hrms, centroid,
                bin_width, labels_only))
        if not centroid and 'mspeak.bin' in names:
            metadata['centroid_available'] = True
        if not hrms and 'msprofile.bin' in names:
            metadata['hrms_available'] = True

    _add_result_metadata(metadata, dx_path, acaml_path, signals)

    datadir = DataDirectory(path, datafiles, metadata)
    if peaks:
        import warnings
        warnings.warn(
            "rainbow does not read integrated peaks from an OpenLab .sirslt "
            "folder; {} is read without them.".format(os.path.basename(path)))
        datadir.peaks = []
    return datadir


def read_metadata(path):
    """
    Reads metadata from an Agilent OpenLab CDS .sirslt result folder.

    Args:
        path (str): Path of the .sirslt folder.

    Returns:
        Dictionary containing a list of datafiles and the metadata.

    """
    dx_path, acaml_path = find_files(path)
    if dx_path is None:
        return None
    listing = openlab.read_metadata(dx_path)
    with zipfile.ZipFile(dx_path) as archive:
        _, signals = openlab._parse_manifest(archive)
    metadata = listing['metadata']
    datafiles = list(listing['datafiles'])
    ms_files = _ms_files(path, signals)
    for name in ms_files:
        if name.lower() in ('mspeak.bin', 'msprofile.bin'):
            datafiles.append(name)
    if any(name.lower() == 'mspeak.bin' for name in ms_files):
        metadata['centroid_available'] = True
    if any(name.lower() == 'msprofile.bin' for name in ms_files):
        metadata['hrms_available'] = True
    _add_result_metadata(metadata, dx_path, acaml_path, signals)
    return {'datafiles': datafiles, 'metadata': metadata}


def technique(path):
    """
    The separation technique of a .sirslt run: ``'LC'``, ``'GC'``, or None.

    OpenLab writes the same folder layout for liquid and gas chromatographs,
    so the technique is read from what the run records rather than from the
    layout. In order of authority:

    1. the instrument's ``<Technique>`` in the result-set document (.acaml);
    2. the ``<SeparationTechnique>`` of the MS sidecar ``MSData/Contents.xml``
       in the archive (LC/MS and GC/MS runs only);
    3. the manifest: a "GC" injection source, or a GC-only detector (FID,
       TCD, ECD, NPD, FPD, SCD, NCD).

    Args:
        path (str): Path of the .sirslt folder.

    Returns:
        str or None.

    """
    dx_path, acaml_path = find_files(path)
    signals = {}
    if dx_path is not None:
        with zipfile.ZipFile(dx_path) as archive:
            _, signals = openlab._parse_manifest(archive)
    return _technique(dx_path, acaml_path, signals)


def _technique(dx_path, acaml_path, signals, instrument=None):
    """:func:`technique`, from files the caller has already located."""
    if instrument is None and acaml_path is not None:
        instrument = _instrument(acaml_path)
    if instrument and instrument.get('technique'):
        found = _ACAML_TECHNIQUES.get(instrument['technique'].lower())
        if found:
            return found

    if dx_path is not None:
        with zipfile.ZipFile(dx_path) as archive:
            contents = _archive_xml(archive, 'MSData/Contents.xml')
            source = _injection_source(archive)
        if contents is not None:
            code = (contents.findtext('SeparationTechnique') or '').strip()
            if code in _CONTENTS_TECHNIQUES:
                return _CONTENTS_TECHNIQUES[code]
        if source and re.search(r'\bGC\b', source, re.IGNORECASE):
            return 'GC'

    devices = {signal.get('device', '').upper() for signal in signals.values()}
    if any(device.startswith(_GC_DEVICES) for device in devices):
        return 'GC'
    return None


def _add_result_metadata(metadata, dx_path, acaml_path, signals):
    """Fills the run metadata from the result-set document and MS sidecars."""
    instrument = _instrument(acaml_path) if acaml_path else None
    if instrument:
        metadata.setdefault('instrument', instrument)
    found = _technique(dx_path, acaml_path, signals, instrument)
    if found:
        metadata['technique'] = found

    with zipfile.ZipFile(dx_path) as archive:
        devices = _archive_xml(archive, 'MSData/Devices.xml')
    if devices is not None:
        ms_devices = []
        for device in devices.iter('Device'):
            entry = {
                'name': (device.findtext('Name') or '').strip() or None,
                'model': (device.findtext('ModelNumber') or '').strip()
                or None,
                'serial_no': (device.findtext('SerialNumber') or '').strip()
                or None,
                'firmware': (device.findtext('FirmwareVersion') or '').strip()
                or None,
            }
            ms_devices.append(
                {key: value for key, value in entry.items() if value})
        if ms_devices:
            metadata['ms_devices'] = ms_devices


def _instrument(acaml_path):
    """The instrument block of a .acaml, or None if it cannot be read."""
    from rainbow.agilent import sequence
    return sequence.parse_header(acaml_path).get('instrument')


def _ms_files(path, signals):
    """
    Maps each MS binary beside the archive to its MassHunter name.

    The manifest's <ExternalElementPaths> name them; with no manifest entry,
    the folder is scanned for ``*.MS*.bin`` files instead.

    Returns:
        dict: ``{'MSScan.bin': <path>, 'MSPeak.bin': <path>, ...}``.

    """
    names = []
    for signal in signals.values():
        if signal.get('encoding', '').endswith('/MSData'):
            names.extend(signal.get('external', []))
    if not names:
        names = [name for name in os.listdir(path)
                 if _MS_FILE_RE.search(name)]

    found = {}
    for name in names:
        full = os.path.join(path, name)
        match = _MS_FILE_RE.search(name)
        if match and os.path.isfile(full):
            found[_canonical_ms_name(match.group(1))] = full
    # The scan index is what every MS reader starts from; without it the data
    # files beside it cannot be decoded.
    if not any(name.lower() == 'msscan.bin' for name in found):
        return {}
    return found


def _canonical_ms_name(name):
    """``mspeak.bin`` -> ``MSPeak.bin``, as MassHunter spells them."""
    canonical = {'msscan.bin': 'MSScan.bin', 'mspeak.bin': 'MSPeak.bin',
                 'msprofile.bin': 'MSProfile.bin',
                 'msmasscal.bin': 'MSMassCal.bin'}
    return canonical.get(name.lower(), name)


def _read_ms(dx_path, ms_files, display_precision, hrms, centroid, bin_width,
             labels_only):
    """
    Reads the MS data of a .sirslt with the MassHunter decoders.

    Those decoders read a .D's AcqData folder. One is assembled in a temporary
    directory from the sidecars inside the archive (MSScan.xsd above all,
    which describes the MSScan.bin records) and the binaries beside it, linked
    where the filesystem allows and copied where it does not.

    """
    from rainbow.agilent import masshunter

    tmp = tempfile.mkdtemp(prefix='rainbow-sirslt-')
    try:
        acqdata = os.path.join(tmp, 'AcqData')
        os.mkdir(acqdata)
        with zipfile.ZipFile(dx_path) as archive:
            for member in archive.namelist():
                parts = member.replace('\\', '/').split('/')
                if len(parts) == 2 and parts[0].lower() == 'msdata' \
                        and parts[1]:
                    with open(os.path.join(acqdata, parts[1]), 'wb') as out:
                        out.write(archive.read(member))
        if not os.path.isfile(os.path.join(acqdata, 'MSScan.xsd')):
            return []
        for name, source in ms_files.items():
            target = os.path.join(acqdata, name)
            try:
                os.link(source, target)
            except (OSError, AttributeError, NotImplementedError):
                shutil.copyfile(source, target)
        return masshunter.parse_allfiles(
            tmp, display_precision, hrms, centroid, bin_width,
            requested_files=None, labels_only=labels_only)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _archive_xml(archive, name):
    """A small XML member of the archive, parsed, or None."""
    for member in archive.namelist():
        if member.replace('\\', '/').lower() == name.lower():
            try:
                return ET.fromstring(archive.read(member))
            except ET.ParseError:
                return None
    return None


def _injection_source(archive):
    """The manifest's <InjectionSource> (e.g. "GC Injector"), or ''."""
    root = _archive_xml(archive, 'injection.acmd')
    if root is None:
        return ''
    for element in root.iter():
        if element.tag.rsplit('}', 1)[-1] == 'InjectionSource':
            return (element.text or '').strip()
    return ''
