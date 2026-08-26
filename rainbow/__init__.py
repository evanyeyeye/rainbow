import os
import re
from rainbow.datafile import DataFile
from rainbow.datadirectory import DataDirectory
from rainbow.datasequence import DataSequence
from rainbow import agilent, waters
from rainbow._binning import MZ_FLOORS
from rainbow.asm import from_asm, sequence_from_asm


# `debug` is listed although it is not imported above: __getattr__ fetches it on
# first use. Naming it here keeps `from rainbow import *` and tab completion
# working, which a lazy attribute alone would quietly drop.
__all__ = [
    'DataFile', 'DataDirectory', 'DataSequence',
    'agilent', 'waters', 'debug',
    'read', 'read_sequence', 'read_metadata', 'mz_resolution',
    'from_asm', 'sequence_from_asm',
    'VENDORS', 'MZ_FLOORS',
]


def __getattr__(name):
    """Imports ``rainbow.debug`` on first use.

    The metadata-inspection subsystem is off the normal read path, and its ten
    decoders are a fifth of the cost of ``import rainbow`` for a caller who
    never touches them. Deferring it keeps that promise real rather than merely
    documented. ``rb.debug.inspect(...)``, ``from rainbow import debug``, and
    ``import rainbow.debug`` all still work.

    ``from rainbow import *`` is the one form that pays the cost anyway: a star
    import binds every name in ``__all__``, which reaches this function. That
    is the price of listing ``debug`` there, and listing it is worth more than
    the 7 ms, since dropping a documented name from the star import and from
    tab completion is the more surprising failure.
    """
    if name == "debug":
        import importlib
        module = importlib.import_module("rainbow.debug")
        globals()["debug"] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """Lists ``debug`` before it has been imported, so completion offers it."""
    return sorted(set(globals()) | set(__all__))


# Vendor parsers that rainbow can dispatch to.
VENDORS = ('agilent', 'waters')


def _validate_bin_width(bin_width):
    """Rejects a ``bin_width`` that is not a positive number."""
    if bin_width is None:
        return
    if (isinstance(bin_width, bool)
            or not isinstance(bin_width, (int, float)) or bin_width <= 0):
        raise Exception(f"Invalid bin_width: {bin_width}.")


def _mz_floor(datafile, vendor):
    """
    The finest m/z bin ``datafile``'s binary meaningfully records, or None.

    A per-scan channel was never binned, so no floor applies to it. Otherwise
    the floor belongs to the parser that read the channel: one that knows its
    data resolves differently than the vendor default records that floor on the
    file it returns (calibrated MassHunter TOF data resolves far below any
    vendor floor, profile or centroid alike).
    """
    if hasattr(datafile, 'mass_labels'):
        return None
    return getattr(datafile, '_mz_floor', MZ_FLOORS.get(vendor))


def _warn_bin_width_floor(datafiles, bin_width, vendor):
    """
    Warns if ``bin_width`` is finer than the m/z grid a parsed channel records.

    The lossy m/z bin cannot resolve finer than the grid the vendor binary
    actually stores, so a finer ``bin_width`` only inserts empty bins.

    Which floor applies is a property of the channel that was parsed, not of the
    flags the caller passed, so this runs over the parsed files rather than
    guessing from the request. A run read with ``centroid=True`` can still hold
    an ordinary quadrupole channel that does have a floor, and the flag must not
    silence the warning that channel has earned.
    """
    if bin_width is None:
        return
    too_fine = {}
    for datafile in datafiles:
        if datafile.detector != 'MS':
            continue
        floor = _mz_floor(datafile, vendor)
        if floor is not None and bin_width < floor:
            too_fine[datafile.name] = floor
    if not too_fine:
        return
    import warnings
    # Channels in one run can record very different grids (an HRMS profile at
    # 1e-6 beside a Chemstation .ms at 0.1). One number for all of them would
    # be wrong by orders of magnitude for every channel but the coarsest, so
    # they are grouped by the grid they actually record.
    by_floor = {}
    for name, floor in too_fine.items():
        by_floor.setdefault(floor, []).append(name)
    described = "; ".join(
        f"{', '.join(sorted(by_floor[floor]))} (about {floor} Da)"
        for floor in sorted(by_floor, reverse=True))
    warnings.warn(
        f"bin_width={bin_width} is finer than the m/z grid recorded by "
        f"{described}; it only inserts empty bins.")


def _sniff_vendor(path):
    """
    Identifies the vendor of a directory from its contents.

    Used as a fallback when a directory's name lacks the conventional vendor
    suffix (e.g. a Waters .raw folder renamed to ``Caffeine 3``). Returns
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
    0.1 Da for Agilent quadrupole MS and 0.03 Da for Waters; the high-resolution
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
            never merges data. Where a coarse value would round neighbouring
            bins onto one label, it is raised to what the grid needs, so the
            labels always name the columns one to one. It does not apply to a
            per-scan centroid at all, whose labels are its data. The default
            ``'auto'`` chooses per file: 4 for the high-resolution Agilent HRMS
            profile and TOF centroids, and 0 (whole numbers) for
            unit-resolution data (UV, GC/quadrupole MS, Waters).
        hrms (bool, optional): Flag for Agilent HRMS (MSProfile.bin) parsing.
        requested_files (list, optional): List of filenames to parse.
        telemetry (bool, optional): Flag for Agilent .dx telemetry traces.
        centroid (bool, optional): Flag for Agilent MassHunter centroid
            (MSPeak.bin) parsing.
        format (str, optional): Force the vendor parser ('agilent' or
            'waters'), bypassing extension/content detection.
        bin_width (float, optional): Width in daltons of each m/z bin: the lossy
            binning control that sums intensities into a shared grid. It applies
            to MS channels only, never to a UV or wavelength axis. For regular
            MS the default is nominal mass (1 Da); pass a finer width down to the
            vendor's m/z grid for more resolution (a width below it only warns
            and inserts empty bins, and one small enough to overflow the bin
            index is refused). For the Agilent HRMS profile, omit it (the
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

    # display_precision is a label precision (decimals for the reported m/z),
    # and is cosmetic: it rounds the labels, never the data. 'auto' is finalized
    # per file inside each parser, where the acquisition is actually known:
    # high-resolution data (the HRMS profile, and calibrated TOF centroids)
    # resolves to 4 decimals; unit-resolution data (UV, GC/quadrupole MS,
    # Waters) to whole numbers.
    #
    # bin_width is the lossy control: it is the width of the m/z bin that
    # intensities are summed into. Regular MS binning defaults to nominal mass
    # (1 Da); for the per-scan representations (the HRMS profile, a centroid
    # peak list) there is no default, because a shared grid has no sensible
    # universal width, and omitting it is what keeps them per scan. The two are
    # independent. (If display_precision is too coarse to label the bins
    # distinctly, the parser warns; it is not an error.) Whether a bin_width is
    # finer than the channel can support is checked after the read, where the
    # parsed channels say which floor applies.
    _validate_bin_width(bin_width)

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
    # Warned here, not before the read, because the floor is a property of the
    # channels the parsers actually returned.
    _warn_bin_width_floor(datadir.datafiles, bin_width, vendor)
    return datadir


def _mz_spacings(datadir, only=None):
    """
    Finest m/z spacing of each MS channel in ``datadir``.

    A per-scan channel (the HRMS profile, a centroid peak list) is measured
    from one scan's own m/z axis; a binned channel from its shared axis. Pass
    ``only=True`` for just the per-scan channels or ``only=False`` for just the
    binned ones, so a caller that read one kind on the wrong grid can measure
    each kind on the read that suits it.

    """
    import numpy as np

    resolutions = {}
    for datafile in datadir.datafiles:
        if datafile.detector != 'MS':
            continue
        per_scan = hasattr(datafile, 'mass_labels')
        if only is not None and per_scan is not only:
            continue
        try:
            if per_scan:               # per-scan: one scan's own m/z axis
                mz = np.asarray(datafile.mass_labels(0), dtype=float)
            else:
                mz = np.asarray(datafile.ylabels, dtype=float)
        except Exception:
            continue                   # a per-scan channel with no shared axis
        mz = np.unique(mz)
        if mz.size >= 2:
            # Round off floating-point noise, but finely enough to keep a true
            # high-resolution (HRMS) spacing, which can be well below 1e-4 Da.
            resolutions[datafile.name] = round(float(np.min(np.diff(mz))), 7)
    return resolutions


def _has_binned_ms(datadir):
    """Whether ``datadir`` holds an MS channel on a shared (binned) m/z axis."""
    return any(datafile.detector == 'MS'
               and not hasattr(datafile, 'mass_labels')
               for datafile in datadir.datafiles)


def mz_resolution(path, hrms=False, requested_files=None, centroid=False):
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
        centroid (bool, optional): Inspect the Agilent MassHunter centroid
            (MSPeak.bin). A centroid run's MS data is parsed only under this
            flag, so without it such a run looks like one with no MS at all.

    Returns:
        dict: Each MS channel name mapped to its finest m/z spacing in
            daltons. Empty if the run has no MS that was parsed. Agilent
            quadrupole MS resolves to about 0.1 Da, Waters to between about
            0.03 and 0.07 Da depending on the run.

    """
    import warnings

    def _probe():
        # A grid far finer than any vendor lattice exposes the underlying
        # spacing (bin_datapairs keeps only populated bins). The labels must be
        # displayed finely too, or display_precision would round them back
        # together and hide the spacing. The flags are forwarded because they
        # decide which channels are parsed at all, not just how: Agilent ICP-MS
        # is gated behind `hrms` and yet comes back on a shared axis, so a
        # probe without the flag would not see it in either read.
        return read(path, bin_width=1e-3, display_precision=4, hrms=hrms,
                    centroid=centroid, requested_files=requested_files)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if not (hrms or centroid):
            return _mz_spacings(_probe())

        # The HRMS profile and the centroid peak list are per scan and already
        # at the instrument's own resolution, so they are read as they are
        # rather than binned, and measured from one scan's own axis. Display
        # that axis finely, or the default 4-decimal rounding would hide a true
        # sub-mDa spacing (or collapse it to 0).
        datadir = read(path, hrms=hrms, centroid=centroid,
                       display_precision=8, requested_files=requested_files)
        resolutions = _mz_spacings(datadir, only=True)

        # A channel on a shared axis can sit in the same directory (a
        # Chemstation .ms beside a MassHunter MSPeak.bin), and Agilent ICP-MS
        # is one even though `hrms` gates it. The read above binned those at
        # the default nominal width, so measuring them there would report that
        # default instead of the grid the binary records. They get the probe
        # grid, in a second read, which the common case of a run with no such
        # channel does not pay for.
        #
        # Only the channels the first read did not already measure are taken
        # from the probe. `only=False` cannot be trusted to exclude the rest:
        # the probe passes a bin_width, which is exactly what turns a per-scan
        # channel into a binned one, so a channel measured correctly above
        # comes back from the probe as binned and would otherwise overwrite its
        # own answer with 1e-3, the probe constant.
        if _has_binned_ms(datadir):
            for name, spacing in _mz_spacings(_probe(), only=False).items():
                resolutions.setdefault(name, spacing)
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

    _validate_bin_width(bin_width)

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
    # One warning for the sequence, not one per injection: the injections of a
    # sequence share an acquisition method, so they share their channels.
    _warn_bin_width_floor(
        [datafile for injection in datasequence.injections
         for datafile in injection.datafiles], bin_width, vendor)
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
