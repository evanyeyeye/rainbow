import os
import re
from rainbow.datafile import DataFile
from rainbow.datadirectory import DataDirectory
from rainbow import agilent, waters


# Vendor parsers that rainbow can dispatch to.
VENDORS = ('agilent', 'waters')


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


def read(path, precision='auto', hrms=False, requested_files=None,
         telemetry=False, centroid=False, format=None, bin_width=None):
    """
    Reads a chromatogram data directory. Main method of the package.

    Increasing the precision may drastically increase memory usage for \
        larger files. Specifying a higher precision mainly affects the \
        parsing of MS data, because intensities are summed within the given \
        precision for each ylabel.

    Max precision available for Agilent MS data is 1.

    Max precision recommended for Waters MS data is 3.

    Agilent HRMS parsing may be slow. Set the flag to enable it.

    For Agilent .dx archives, instrument telemetry traces (e.g. pressure, \
        temperature) are skipped unless the telemetry flag is set.

    The vendor is normally detected from the path: a .D/.dx path is read as \
        Agilent and a .raw path as Waters. A directory whose name lacks that \
        suffix is identified from its contents instead. Pass ``format`` \
        ('agilent' or 'waters') to override detection entirely.

    Args:
        path (str): Path of the directory.
        precision (int or 'auto', optional): Number of decimals to round
            reported m/z (and other ylabels) to. The default ``'auto'`` chooses
            per file: 4 for high-resolution data (the Agilent HRMS profile and
            TOF centroids) and 0 (whole numbers) for unit-resolution data (UV,
            GC/quadrupole MS, Waters). Pass an explicit integer to override
            (including ``0`` to force nominal mass).
        hrms (bool, optional): Flag for Agilent HRMS (MSProfile.bin) parsing.
        requested_files (list, optional): List of filenames to parse.
        telemetry (bool, optional): Flag for Agilent .dx telemetry traces.
        centroid (bool, optional): Flag for Agilent MassHunter centroid
            (MSPeak.bin) parsing.
        format (str, optional): Force the vendor parser ('agilent' or
            'waters'), bypassing extension/content detection.
        bin_width (float, optional): Width in daltons of each shared-grid bin
            for Agilent HRMS profile data. Omit it (the default) to keep the
            per-scan representation; pass a width to project the scans onto one
            shared m/z grid (see :ref:`hrms-data-model`). This is the grid's only
            control and is fully independent of ``precision`` (which only rounds
            the reported m/z labels, never the grid). A ``bin_width`` finer than
            ``10**-precision`` is allowed but warns, since two bins may then round
            to the same m/z label.

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

    if precision != 'auto' and (
            isinstance(precision, bool) or not isinstance(precision, int)
            or precision < 0):
        raise Exception(
            f"Invalid precision: {precision!r}. Use 'auto' or a non-negative "
            f"integer.")

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
    if bin_width is not None and (
            isinstance(bin_width, bool)
            or not isinstance(bin_width, (int, float)) or bin_width <= 0):
        raise Exception(f"Invalid bin_width: {bin_width}.")

    if requested_files is not None and not isinstance(requested_files, list):
        raise Exception(f"The requested_files argument must be a list.")

    if requested_files:
        requested_files = list(map(str.lower, requested_files))

    datadir = None
    if vendor == 'agilent':
        datadir = agilent.read(
            path, precision, hrms, requested_files, telemetry, centroid,
            bin_width)
    elif vendor == 'waters':
        datadir = waters.read(path, precision, requested_files)

    if datadir is None:
        raise Exception(f"Rainbow cannot read {path}.")
    return datadir


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
