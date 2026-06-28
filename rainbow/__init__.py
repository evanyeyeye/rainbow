import os
import re
from rainbow.datafile import DataFile
from rainbow.datadirectory import DataDirectory
from rainbow.datasequence import DataSequence
from rainbow import agilent, waters
from rainbow.asm import from_asm, sequence_from_asm


# Vendor parsers that rainbow can dispatch to.
VENDORS = ('agilent', 'waters')

# Finest meaningful m/z bin width per vendor (the m/z grid the binary records;
# see the per-vendor MS docs). A bin_width below this only inserts empty bins.
_MZ_FLOORS = {'agilent': 0.1, 'waters': 0.05}
# High-resolution MassHunter (TOF/Q-TOF) profile data resolves much finer.
_HRMS_MZ_FLOOR = 1e-6


def _check_bin_width(bin_width, vendor, hrms):
    """Validates ``bin_width`` and warns if it is finer than the binary records.

    The lossy m/z bin cannot resolve finer than the m/z grid the vendor binary
    actually stores, so a ``bin_width`` below that floor only inserts empty bins.
    """
    if bin_width is None:
        return
    if (isinstance(bin_width, bool)
            or not isinstance(bin_width, (int, float)) or bin_width <= 0):
        raise Exception(f"Invalid bin_width: {bin_width}.")
    floor = _HRMS_MZ_FLOOR if hrms else _MZ_FLOORS.get(vendor)
    if floor is not None and bin_width < floor:
        import warnings
        label = "HRMS profile" if hrms else vendor
        warnings.warn(
            f"bin_width={bin_width} is finer than the {label} m/z grid "
            f"(about {floor} Da); it only inserts empty bins.")


def _sniff_vendor(path):
    """
    Identifies the vendor of a directory from its contents.

    Used as a fallback when a directory's name lacks the conventional vendor
    suffix (e.g. a Waters .raw folder renamed to ``Noscapine 3``). Returns
    'agilent', 'waters', or None if no signature matches.

    Args:
        path (str): Path of the directory.

    Returns:
        Vendor name, or None.

    """
    try:
        names = os.listdir(path)
    except OSError:
        return None
    lower = {name.lower() for name in names}

    # Waters .raw: the function/header manifests or numbered _FUNC data files.
    if '_functns.inf' in lower or '_header.txt' in lower \
            or any(re.fullmatch(r'_func\d{3}\.dat', name) for name in lower):
        return 'waters'

    # Agilent .D: the AcqData subdirectory or any Chemstation data file.
    if 'acqdata' in lower \
            or any(os.path.splitext(name)[1] in ('.ch', '.uv', '.ms')
                   for name in lower):
        return 'agilent'

    return None


def _detect_vendor(path):
    """
    Determines which vendor parser to use for a path.

    The path's extension is tried first (.D/.dx -> Agilent, .raw -> Waters),
    which preserves rainbow's historical behavior exactly. If the extension is
    unrecognized and the path is a directory, its contents are sniffed for a
    vendor signature, so datasets whose folders were renamed without the
    conventional suffix still parse. Because this fallback only runs when the
    extension matches nothing, it can only make a previously-unreadable path
    readable -- it never changes how an already-recognized path is parsed.

    Args:
        path (str): Path of the directory or .dx file.

    Returns:
        Vendor name ('agilent' or 'waters'), or None.

    """
    if not isinstance(path, str):
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.d', '.dx'):
        return 'agilent'
    if ext == '.raw':
        return 'waters'
    if os.path.isdir(path):
        return _sniff_vendor(path)
    return None


def _resolve_vendor(path, format):
    """Resolves the vendor from an explicit override or by detection."""
    if format is not None:
        if not isinstance(format, str) or format.lower() not in VENDORS:
            raise Exception(
                f"The format argument must be one of {VENDORS} or None.")
        return format.lower()
    return _detect_vendor(path)


def read(path, display_precision='auto', hrms=False, requested_files=None,
         telemetry=False, centroid=False, format=None, bin_width=None):
    """
    Reads a chromatogram data directory. Main method of the package.

    MS m/z resolution is controlled by ``bin_width`` (the lossy step that sums
    intensities into a shared grid), not by ``display_precision`` (which only
    rounds the displayed labels). A finer ``bin_width`` may drastically increase
    memory usage for larger files. The m/z grid the binary records is about
    0.1 Da for Agilent quadrupole MS and 0.05 Da for Waters; the high-resolution
    Agilent HRMS profile is far finer (see :func:`mz_resolution` to inspect a
    file).

    Agilent HRMS parsing may be slow. Set the flag to enable it.

    For Agilent .dx archives, instrument telemetry traces (e.g. pressure, \
        temperature) are skipped unless the telemetry flag is set.

    The vendor is normally detected from the path: a .D/.dx path is read as \
        Agilent and a .raw path as Waters. A directory whose name lacks that \
        suffix is identified from its contents instead. Pass ``format`` \
        ('agilent' or 'waters') to override detection entirely.

    Args:
        path (str): Path of the directory.
        display_precision (int or 'auto', optional): Decimals for the displayed
            m/z (and other ylabel) labels. Cosmetic: it rounds the labels and
            never merges data. The default ``'auto'`` chooses per file: 4 for the
            high-resolution Agilent HRMS profile and TOF centroids, and 0
            (whole numbers) for unit-resolution data (UV, GC/quadrupole MS,
            Waters).
        hrms (bool, optional): Flag for Agilent HRMS (MSProfile.bin) parsing.
        requested_files (list, optional): List of filenames to parse.
        telemetry (bool, optional): Flag for Agilent .dx telemetry traces.
        centroid (bool, optional): Flag for Agilent MassHunter centroid
            (MSPeak.bin) parsing.
        format (str, optional): Force the vendor parser ('agilent' or
            'waters'), bypassing extension/content detection.
        bin_width (float, optional): Width in daltons of each m/z bin: the lossy
            binning control that sums intensities into a shared grid. For regular
            MS the default is nominal mass (1 Da); pass a finer width down to the
            vendor's m/z grid for more resolution (a width below it only warns
            and inserts empty bins). For the Agilent HRMS profile, omit it (the
            default) to keep the per-scan representation, or pass a width to
            project the scans onto one shared m/z grid (see
            :ref:`hrms-data-model`).

    Returns:
        DataDirectory representing the directory.

    """
    vendor = _resolve_vendor(path, format)

    ext = os.path.splitext(path)[1].lower() if isinstance(path, str) else ''
    if ext == '.dx':
        if not isinstance(path, str) or not os.path.isfile(path):
            raise Exception(f"{path} is not a file.")
    elif not isinstance(path, str) or not os.path.isdir(path):
        raise Exception(f"{path} is not a directory.")

    if display_precision != 'auto' and (
            isinstance(display_precision, bool)
            or not isinstance(display_precision, int)
            or display_precision < 0):
        raise Exception(
            f"Invalid display_precision: {display_precision!r}. Use 'auto' or a "
            f"non-negative integer.")

    if not isinstance(hrms, bool):
        raise Exception(f"The hrms flag must be a boolean.")

    if not isinstance(centroid, bool):
        raise Exception(f"The centroid flag must be a boolean.")

    # precision is a label precision (decimals for reported m/z). 'auto' is
    # finalized per file inside each parser, where the data type is actually
    # known: high-resolution data (the HRMS profile, and TOF centroids) resolves
    # to 4 decimals; unit-resolution data (UV, GC/quadrupole MS, Waters) to whole
    # numbers.
    #
    # bin_width is the width of the shared HRMS profile grid, and it is what turns
    # binning on: omit it for the per-scan representation, pass a width to project
    # onto one shared grid. It is entirely independent of precision (precision
    # only rounds the reported m/z labels, never the grid), with no default,
    # because the shared grid has no sensible universal width. (If precision is
    # too coarse to label the bins distinctly, parse_msdata warns; it is not an
    # error.)
    _check_bin_width(bin_width, vendor, hrms)

    if requested_files is not None and not isinstance(requested_files, list):
        raise Exception(f"The requested_files argument must be a list.")

    if requested_files:
        requested_files = list(map(str.lower, requested_files))

    datadir = None
    if vendor == 'agilent':
        datadir = agilent.read(
            path, display_precision, hrms, requested_files, telemetry, centroid,
            bin_width)
    elif vendor == 'waters':
        datadir = waters.read(
            path, display_precision, requested_files, bin_width)

    if datadir is None:
        raise Exception(f"Rainbow cannot read {path}.")
    return datadir


def mz_resolution(path, hrms=False, requested_files=None):
    """
    Inspects the m/z grid a run records, the finest spacing the binary
    actually stores.

    This is the practical ceiling on ``bin_width``: a finer bin only inserts
    empty bins. It is computed by reading the run on a grid finer than any vendor
    lattice (so the underlying spacing shows through) and measuring the smallest
    gap between adjacent m/z labels; the high-resolution HRMS profile is measured
    from one scan's own axis instead. The read is not cheap, so this is opt-in,
    never run on an ordinary :func:`read`.

    Args:
        path (str): Path of the directory.
        hrms (bool, optional): Inspect the Agilent HRMS profile (MSProfile.bin).
        requested_files (list, optional): Limit to these filenames.

    Returns:
        dict: Each MS channel name mapped to its finest m/z spacing in
            daltons. Empty if the run has no MS. Agilent quadrupole MS resolves
            to about 0.1 Da, Waters to about 0.05 Da.

    """
    import warnings
    import numpy as np

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if hrms:
            # Display the per-scan m/z finely, or the default 4-decimal rounding
            # would hide a true sub-mDa profile spacing (or collapse it to 0).
            datadir = read(path, hrms=True, display_precision=8,
                           requested_files=requested_files)
        else:
            # A grid far finer than any vendor lattice exposes the underlying
            # spacing (bin_datapairs keeps only populated bins). The labels must
            # be displayed finely too, or display_precision would round them back
            # together and hide the spacing.
            datadir = read(path, bin_width=1e-3, display_precision=4,
                           requested_files=requested_files)

    resolutions = {}
    for datafile in datadir.datafiles:
        if datafile.detector != 'MS':
            continue
        if hasattr(datafile, 'mass_labels'):
            try:                       # per-scan HRMS: one scan's own m/z axis
                mz = np.asarray(datafile.mass_labels(0), dtype=float)
            except Exception:
                continue
        else:
            try:
                mz = np.asarray(datafile.ylabels, dtype=float)
            except Exception:
                continue               # a per-scan profile with no shared axis
        mz = np.unique(mz)
        if mz.size >= 2:
            # Round off floating-point noise, but finely enough to keep a true
            # high-resolution (HRMS) spacing, which can be well below 1e-4 Da.
            resolutions[datafile.name] = round(float(np.min(np.diff(mz))), 7)
    return resolutions


def _detect_sequence_vendor(path):
    """
    Determines which vendor parser to use for a sequence directory.

    A sequence directory is identified by the injection subdirectories it
    holds: .D subdirectories mean Agilent, .raw subdirectories mean Waters. The
    directory itself carries no vendor suffix, so its own name is not enough.

    Args:
        path (str): Path of the sequence directory.

    Returns:
        Vendor name ('agilent' or 'waters'), or None.

    """
    if not isinstance(path, str) or not os.path.isdir(path):
        return None
    has_agilent = has_waters = False
    for name in os.listdir(path):
        if not os.path.isdir(os.path.join(path, name)):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext == '.d':
            has_agilent = True
        elif ext == '.raw':
            has_waters = True
    if has_agilent:
        return 'agilent'
    if has_waters:
        return 'waters'
    return None


def read_sequence(path, display_precision='auto', hrms=False,
                  requested_files=None, telemetry=False, centroid=False,
                  peaks=False, format=None, bin_width=None):
    """
    Reads a multi-injection sequence directory.

    Where :func:`read` reads a single injection, this reads the whole run: a
    directory holding one injection subdirectory per sample, plus the
    sequence-level method and metadata. Each injection is read with
    :func:`read`, and the injections are returned in acquisition order inside a
    DataSequence.

    The vendor is detected from the injection subdirectories (.D means Agilent,
    .raw means Waters); pass ``format`` to override detection. Sequence reading
    is currently implemented for Agilent.

    Args:
        path (str): Path of the sequence directory.
        display_precision (int or 'auto', optional): Decimals for displayed m/z
            labels (cosmetic).
        hrms (bool, optional): Flag for Agilent HRMS (MSProfile.bin) parsing.
        requested_files (list, optional): List of filenames to parse.
        telemetry (bool, optional): Flag for Agilent .dx telemetry traces.
        centroid (bool, optional): Flag for Agilent MassHunter centroid
            (MSPeak.bin) parsing.
        peaks (bool, optional): Flag for reading the integrated peaks from
            sequence.acaml and attaching them to each injection.
        bin_width (float, optional): m/z bin width passed to each injection's
            read (see :func:`read`); the lossy binning control.
        format (str, optional): Force the vendor parser ('agilent' or
            'waters'), bypassing detection.

    Returns:
        DataSequence representing the sequence directory.

    """
    if format is not None:
        if not isinstance(format, str) or format.lower() not in VENDORS:
            raise Exception(
                f"The format argument must be one of {VENDORS} or None.")
        vendor = format.lower()
    else:
        vendor = _detect_sequence_vendor(path)

    if not isinstance(path, str) or not os.path.isdir(path):
        raise Exception(f"{path} is not a directory.")

    if display_precision != 'auto' and (
            isinstance(display_precision, bool)
            or not isinstance(display_precision, int)
            or display_precision < 0):
        raise Exception(
            f"Invalid display_precision: {display_precision!r}. Use 'auto' or a "
            f"non-negative integer.")

    if not isinstance(hrms, bool):
        raise Exception("The hrms flag must be a boolean.")

    if not isinstance(centroid, bool):
        raise Exception("The centroid flag must be a boolean.")

    if not isinstance(peaks, bool):
        raise Exception("The peaks flag must be a boolean.")

    _check_bin_width(bin_width, vendor, hrms)

    if requested_files is not None and not isinstance(requested_files, list):
        raise Exception("The requested_files argument must be a list.")

    if requested_files:
        requested_files = list(map(str.lower, requested_files))

    datasequence = None
    if vendor == 'agilent':
        datasequence = agilent.read_sequence(
            path, display_precision, hrms, requested_files, telemetry, centroid,
            peaks, bin_width)

    if datasequence is None:
        raise Exception(f"Rainbow cannot read {path} as a sequence.")
    return datasequence


def read_metadata(path, format=None):
    """
    Reads the metadata for a chromatogram data directory. Main method of the package.

    Args:
        path (str): Path of the directory.
        format (str, optional): Force the vendor parser ('agilent' or
            'waters'), bypassing extension/content detection.

    Returns:
        Dictionary containing a list of datafiles and the metadata.

    """
    vendor = _resolve_vendor(path, format)

    metadata = None
    if vendor == 'agilent':
        metadata = agilent.read_metadata(path)
    elif vendor == 'waters':
        metadata = waters.read_metadata(path)

    if metadata is None:
        raise Exception(f"Rainbow cannot read {path}.")
    return metadata
