"""
Methods for reading Agilent OpenLab CDS result folders (.sirslt).

OpenLab CDS 2.x stores each single-injection result set as a ``.sirslt``
folder. Its files share the folder's stem::

    <name>.dx            OPC (zip) archive of the detector signals (UV, FID,
                         ...) and instrument telemetry. For an LC/MS run it
                         also carries the MS sidecars under MSData/
                         (MSScan.xsd, MSTS.xml, Contents.xml, Devices.xml).
    <name>.MSScan.bin    MassHunter scan records and centroid peaks, written
    <name>.MSPeak.bin    beside the archive; the manifest names them in the
                         MS signal's <ExternalElementPaths>. Binaries found
                         under the archive's MSData/ are read as well.
    <name>.acaml         the result-set document: instrument (with its
                         separation technique and modules), sample, method.
    <name>.rx            processing results (not read).
    <name>.mfx           checksums of the files above (not read).
    *.amx                the acquisition method (OPC zip): read by
                         :mod:`rainbow.agilent.amx`.
    *.pmx, *.sqx, *.scml processing method, sequence and sampler
                         configuration (not read).

The detector signals are decoded by :mod:`rainbow.agilent.openlab`, the reader
for a standalone .dx, and the MS data by :mod:`rainbow.agilent.masshunter`,
which already reads the same MSScan/MSPeak/MSProfile binaries inside a .D.

The same folder layout is written by OpenLab for both LC and GC instruments.
The run's separation technique is recorded in the metadata as ``technique``
(``'LC'`` or ``'GC'``), read from the instrument the result-set document
describes; see :func:`technique`.

"""
import contextlib
import os
import re
import shutil
import tempfile
import warnings
import zipfile
import xml.etree.ElementTree as ET

from rainbow.agilent import amx, method, openlab
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
# ECD is not among them: it names a GC electron-capture detector and an HPLC
# electrochemical detector alike, so it is no evidence either way.
_GC_DEVICES = ('FID', 'TCD', 'NPD', 'FPD', 'SCD', 'NCD')

# MS binaries are written beside the archive as "<name>.<file>", where <file>
# is the name MassHunter gives it inside a .D's AcqData folder.
_MS_FILE_RE = re.compile(r'(MS[A-Za-z_]*\.bin)$', re.IGNORECASE)

# The names the MassHunter readers open in an AcqData folder, as they spell
# them. A .sirslt's own spelling of a sidecar or binary is mapped onto these,
# so a case-sensitive filesystem finds it whatever case it was written in.
_ACQDATA_NAMES = {name.lower(): name for name in (
    'MSScan.xsd', 'MSScan.bin', 'MSPeak.bin', 'MSProfile.bin',
    'MSMassCal.bin', 'MSTS.xml', 'Contents.xml', 'Devices.xml',
    'AcqMethod.xml',
    'DefaultMassCal.xml', 'MSScan_XSpecific.bin', 'MSScan_XSpecific.xsd',
    'MSTS_XSpecific.xml')}


def is_sirslt(path):
    """
    Whether ``path`` is an OpenLab single-injection result folder.

    A folder named ``*.sirslt`` qualifies by its name; one renamed without the
    suffix qualifies by its contents (a .dx archive beside a .acaml document).
    A ``*.D`` folder never does, whatever it holds, and nor does a renamed
    one that still holds a .D's AcqData folder or Chemstation files: each is
    read as the Chemstation/MassHunter run it is.

    """
    if not isinstance(path, str) or not os.path.isdir(path):
        return False
    ext = os.path.splitext(os.path.normpath(path))[1].lower()
    if ext == '.sirslt':
        return True
    if ext == '.d':
        return False
    try:
        names = [name.lower() for name in os.listdir(path)]
    except OSError:
        return False
    exts = {os.path.splitext(name)[1] for name in names}
    # A renamed .D that happens to hold a .dx and a .acaml is still a .D: its
    # AcqData folder or Chemstation files say so, and they would be lost.
    if 'acqdata' in names or exts & {'.ch', '.uv', '.ms'}:
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

    After its data files, the run goes through the step a .D goes through
    (:func:`rainbow.agilent.method.state_run`), on the run laid out as a .D
    (the archive's MSData/ as its AcqData, and the folder's acquisition
    method, its .amx): each MS file states the acquisition mode its scans
    state, and the method and sample sidecars the run holds state what they
    say. What the run does not record is not stated.

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

    with zipfile.ZipFile(dx_path) as archive:
        run = _Run(path, acaml_path, archive)
        datafiles = openlab.decode_archive(
            archive, run.signals, requested_files, telemetry)
        metadata = run.metadata
        ms = run.ms
        if ms.warning:
            warnings.warn(ms.warning)
        want_centroid = centroid and 'MSPeak.bin' in ms.available
        want_profile = hrms and 'MSProfile.bin' in ms.available
        want_ms = want_centroid or want_profile
        with _as_d(archive, ms, want_ms, path) as view:
            if want_ms:
                from rainbow.agilent import masshunter
                datafiles.extend(masshunter.parse_allfiles(
                    view, display_precision, hrms, centroid, bin_width,
                    requested_files=None, labels_only=labels_only))
            # What the run's sidecars and its MS files' scans say of it, by
            # the step a .D goes through.
            method.state_run(view, datafiles, metadata)
    if not centroid and 'MSPeak.bin' in ms.available:
        metadata['centroid_available'] = True
    if not hrms and 'MSProfile.bin' in ms.available:
        metadata['hrms_available'] = True

    datadir = DataDirectory(path, datafiles, metadata)
    if peaks:
        warnings.warn(
            "rainbow does not read integrated peaks from an OpenLab .sirslt "
            "folder; {} is read without them.".format(os.path.basename(path)))
        datadir.peaks = []
    return datadir


def read_metadata(path):
    """
    Reads metadata from an Agilent OpenLab CDS .sirslt result folder: the
    metadata :func:`read` states, its sidecars read by the same step, with
    no data file decoded.

    Args:
        path (str): Path of the .sirslt folder.

    Returns:
        Dictionary containing a list of datafiles and the metadata.

    """
    dx_path, acaml_path = find_files(path)
    if dx_path is None:
        return None
    with zipfile.ZipFile(dx_path) as archive:
        run = _Run(path, acaml_path, archive)
        datafiles = openlab.payload_names(archive)
        metadata = run.metadata
        ms = run.ms
        with _as_d(archive, ms, False, path) as view:
            method.state_run(view, [], metadata)
    if ms.warning:
        warnings.warn(ms.warning)
    for name in ('MSPeak.bin', 'MSProfile.bin'):
        if name in ms.available:
            datafiles.append(name)
    if 'MSPeak.bin' in ms.available:
        metadata['centroid_available'] = True
    if 'MSProfile.bin' in ms.available:
        metadata['hrms_available'] = True
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
       TCD, NPD, FPD, SCD, NCD).

    Args:
        path (str): Path of the .sirslt folder.

    Returns:
        str or None.

    """
    dx_path, acaml_path = find_files(path)
    if dx_path is None:
        return _technique(_instrument(acaml_path) if acaml_path else None,
                          None, '', {})
    with zipfile.ZipFile(dx_path) as archive:
        return _Run(path, acaml_path, archive).technique


class _MSLayout:
    """
    Where a run's MS data is, and whether it can be decoded.

    Attributes:
        beside (dict): MassHunter name -> path of a binary beside the archive.
        archived (dict): MassHunter name -> archive member, for everything
            under the archive's MSData/ (sidecars, and any binaries there).
        available (set): The data binaries (MSPeak.bin, MSProfile.bin) that
            can be decoded: MSScan.bin and MSData/MSScan.xsd are both present.
        warning (str or None): Why MS data that is present cannot be decoded.

    """

    def __init__(self, beside, archived, available, warning):
        self.beside = beside
        self.archived = archived
        self.available = available
        self.warning = warning


class _Run:
    """
    What a .sirslt's archive and result-set document say, each read once.

    Built on an archive the caller keeps open, so that the manifest, the MS
    sidecars and the .acaml are parsed a single time however many of the
    run's properties are asked for.

    """

    def __init__(self, path, acaml_path, archive):
        root = openlab.manifest_root(archive)
        self.metadata, self.signals = openlab.parse_manifest_root(root)
        archived = {}
        for member in archive.namelist():
            parts = member.replace('\\', '/').split('/')
            if len(parts) == 2 and parts[0].lower() == 'msdata' and parts[1]:
                archived[_canonical_name(parts[1])] = member
        contents = _archive_xml(archive, archived.get('Contents.xml'))
        devices = _archive_xml(archive, archived.get('Devices.xml'))
        self.ms = _ms_layout(path, self.signals, archived)

        instrument = _instrument(acaml_path) if acaml_path else None
        if instrument:
            self.metadata.setdefault('instrument', instrument)
        self.technique = _technique(
            instrument, contents, _injection_source(root), self.signals)
        if self.technique:
            self.metadata['technique'] = self.technique
        ms_devices = _ms_devices(devices)
        if ms_devices:
            self.metadata['ms_devices'] = ms_devices


def _technique(instrument, contents, injection_source, signals):
    """:func:`technique`, from what the caller has already read."""
    if instrument and instrument.get('technique'):
        found = _ACAML_TECHNIQUES.get(instrument['technique'].lower())
        if found:
            return found
    if contents is not None:
        code = (contents.findtext('SeparationTechnique') or '').strip()
        if code in _CONTENTS_TECHNIQUES:
            return _CONTENTS_TECHNIQUES[code]
    if injection_source and re.search(r'\bGC\b', injection_source,
                                      re.IGNORECASE):
        return 'GC'
    devices = {signal.get('device', '').upper() for signal in signals.values()}
    if any(device.startswith(_GC_DEVICES) for device in devices):
        return 'GC'
    return None


def _ms_devices(devices):
    """The spectrometers MSData/Devices.xml lists, or []."""
    if devices is None:
        return []
    found = []
    for device in devices.iter('Device'):
        entry = {
            'name': (device.findtext('Name') or '').strip() or None,
            'model': (device.findtext('ModelNumber') or '').strip() or None,
            'serial_no': (device.findtext('SerialNumber') or '').strip()
            or None,
            'firmware': (device.findtext('FirmwareVersion') or '').strip()
            or None,
        }
        entry = {key: value for key, value in entry.items() if value}
        if entry:
            found.append(entry)
    return found


def _instrument(acaml_path):
    """The instrument block of a .acaml, or None if it cannot be read."""
    from rainbow.agilent import sequence
    return sequence.parse_header(acaml_path).get('instrument')


def _ms_layout(path, signals, archived):
    """
    Finds a run's MS binaries and decides which can be decoded.

    The binaries beside the archive are the ones the MS signal's
    <ExternalElementPaths> names, matched by file name alone (so a name
    written with a directory, relative or absolute, still finds the file
    beside the archive) and without regard to case. If those names find no
    MSScan.bin, the folder is scanned for ``*.MS*.bin`` files instead.
    Binaries under the archive's MSData/ count too; one beside the archive
    takes precedence over an archived one of the same name.

    Both :func:`read` and :func:`read_metadata` decide availability here, so
    neither can report MS data the other cannot read.

    """
    listing = {}
    for name in os.listdir(path):
        if os.path.isfile(os.path.join(path, name)):
            listing[name.lower()] = name

    def collect(names):
        found = {}
        for name in names:
            actual = listing.get(name.lower())
            match = _MS_FILE_RE.search(actual) if actual else None
            if match:
                found.setdefault(_canonical_name(match.group(1)),
                                 os.path.join(path, actual))
        return found

    named = []
    for signal in signals.values():
        if signal.get('encoding', '').endswith('/MSData'):
            named.extend(
                _basename(name) for name in signal.get('external', []))
    beside = collect(named)
    if 'MSScan.bin' not in beside:
        scanned = collect(sorted(listing))
        beside = dict(scanned, **beside) if 'MSScan.bin' in scanned else beside

    binaries = set(beside) | {name for name in archived
                              if name.lower().endswith('.bin')}
    data = binaries & {'MSPeak.bin', 'MSProfile.bin'}
    available, warning = set(), None
    if data and 'MSScan.bin' not in binaries:
        warning = ("{} holds MS data ({}) but no MSScan.bin, the scan index "
                   "it is decoded through; the MS data is not read.").format(
                       os.path.basename(os.path.normpath(path)),
                       ', '.join(sorted(data)))
    elif data and 'MSScan.xsd' not in archived:
        warning = ("{} holds MS data ({}) but its archive has no "
                   "MSData/MSScan.xsd, the schema MSScan.bin is decoded "
                   "with; the MS data is not read.").format(
                       os.path.basename(os.path.normpath(path)),
                       ', '.join(sorted(data)))
    else:
        available = data
    return _MSLayout(beside, archived, available, warning)


def _basename(name):
    """The file name of a Windows or POSIX path, on any platform."""
    return name.replace('\\', '/').rstrip('/').rsplit('/', 1)[-1]


def _canonical_name(name):
    """``mspeak.bin`` -> ``MSPeak.bin``, as MassHunter spells it."""
    return _ACQDATA_NAMES.get(name.lower(), name)


@contextlib.contextmanager
def _as_d(archive, ms, binaries, path):
    """
    The run laid out as a .D, in a temporary folder, for the readers of a
    .D: what is under the archive's MSData/ in its AcqData folder (MSScan.xsd
    above all, which describes the MSScan.bin records, and any method or
    device sidecars), the folder's acquisition method (its .amx, as
    :func:`rainbow.agilent.amx.find` finds it in ``path``) at the top, and,
    with ``binaries``, the MS binaries beside the archive, linked where the
    filesystem allows and copied where it does not. Without ``binaries``
    only the sidecars are written: no binary is copied to state what the
    sidecars say. The folder is removed on exit.

    """
    tmp = tempfile.mkdtemp(prefix='rainbow-sirslt-')
    try:
        method_file = amx.find(path)
        if method_file is not None:
            _place(method_file,
                   os.path.join(tmp, os.path.basename(method_file)))
        acqdata = os.path.join(tmp, 'AcqData')
        os.mkdir(acqdata)
        for name, member in ms.archived.items():
            if name in ms.beside or (
                    not binaries and name.lower().endswith('.bin')):
                continue
            with open(os.path.join(acqdata, name), 'wb') as out:
                out.write(archive.read(member))
        if binaries:
            for name, source in ms.beside.items():
                _place(source, os.path.join(acqdata, name))
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _place(source, target):
    """``source`` at ``target``: linked where the filesystem allows,
    copied where it does not."""
    try:
        os.link(source, target)
    except (OSError, AttributeError, NotImplementedError):
        shutil.copyfile(source, target)


def _archive_xml(archive, member):
    """A small XML member of the archive, parsed, or None."""
    if member is None:
        return None
    try:
        return ET.fromstring(archive.read(member))
    except (KeyError, ET.ParseError):
        return None


def _injection_source(root):
    """The manifest's <InjectionSource> (e.g. "GC Injector"), or ''."""
    if root is None:
        return ''
    for element in root.iter():
        if element.tag.rsplit('}', 1)[-1] == 'InjectionSource':
            return (element.text or '').strip()
    return ''
