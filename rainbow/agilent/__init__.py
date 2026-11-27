import os

import numpy as np

from rainbow._arguments import (reject_removed_arguments, validate_bin_width,
                                validate_display_precision)
from rainbow.agilent import chemstation, method
from rainbow.datadirectory import DataDirectory
from rainbow.datasequence import DataSequence


def read(path, display_precision='auto', hrms=False, requested_files=None,
         telemetry=False, centroid=False, bin_width=None, peaks=False,
         _labels_only=False, **removed):
    """
    Reads an Agilent .D directory, .dx archive, or OpenLab .sirslt folder.

    Args:
        path (str): Path of the directory, .dx file, or .sirslt folder.
        display_precision (int or 'auto', optional): Decimals for the displayed
            m/z labels (cosmetic). ``'auto'`` picks per file: 4 for the
            high-resolution MassHunter profile and TOF centroids, and 0 (whole
            numbers) for unit-resolution data.
        hrms (bool, optional): Flag for parsing the MassHunter profile
            spectrum (MSProfile.bin).
        requested_files (list, optional): List of filenames to parse.
        telemetry (bool, optional): Flag for parsing instrument telemetry
            traces, in a .dx archive or alongside a MassHunter DAD's signals.
        centroid (bool, optional): Flag for parsing the MassHunter centroid
            spectrum (MSPeak.bin). Where the .D's own MSD ChemStation .ms
            files hold the same scans (a MassHunter GC/MS acquisition writes
            both), the recording is returned once: from AcqData when its scans
            are read under this flag or ``hrms``, else from the .ms files.
        bin_width (float, optional): m/z bin width in daltons, the lossy binning
            control. For regular MS the default is nominal mass (1 Da); for the
            HRMS profile, omit it (the default) to keep the per-scan
            representation (one
            :class:`~rainbow.agilent.masshunter.ProfileDataFile` per flight-time
            grid), or pass a width to project onto the shared m/z grid.
        peaks (bool, optional): Flag for reading the run's integrated peaks
            into ``DataDirectory.peaks`` (see :func:`injection_peaks`).

    Returns:
        DataDirectory representing the Agilent data.

    """
    if removed:
        reject_removed_arguments("agilent.read", removed)
    # Held to the same rules as rb.read: this is a documented entry point, and
    # an unchecked m/z argument does not raise further down, it returns a grid
    # whose labels no longer name its columns one to one.
    validate_display_precision(display_precision)
    validate_bin_width(bin_width)
    if os.path.splitext(path)[1].lower() == '.dx':
        from rainbow.agilent import openlab
        datadir = openlab.read(
            path, display_precision, requested_files, telemetry, bin_width)
        if peaks and datadir is not None:
            # An archive's results are not read. The run gets an empty list,
            # which alone would read as a run nobody integrated, so the read
            # says why it is empty.
            import warnings
            warnings.warn(
                "rainbow does not read integrated peaks from an OpenLab .dx "
                "archive; {} is read without them.".format(
                    os.path.basename(path)))
            datadir.peaks = []
        return datadir

    from rainbow.agilent import sirslt
    if sirslt.is_sirslt(path):
        return sirslt.read(
            path, display_precision, hrms, requested_files, telemetry,
            centroid, bin_width, peaks, _labels_only)

    datafiles = []
    datafiles.extend(chemstation.parse_allfiles(
        path, display_precision, bin_width, requested_files, _labels_only))
    # MassHunter is always consulted, not only under the MS flags: a .d may also
    # hold DAD data, which is parsed unconditionally the way the Chemstation UV
    # formats are. The MS parsing inside stays gated on hrms/centroid.
    from rainbow.agilent import masshunter
    acquired = masshunter.parse_allfiles(
        path, display_precision, hrms, centroid, bin_width, telemetry,
        requested_files, _labels_only)
    datafiles.extend(acquired)
    # The run's date, method and instrument come from every ChemStation file
    # read, the .ms copies dropped below among them.
    metadata = chemstation.parse_metadata(path, datafiles)

    # A .D written by MassHunter may hold one MS recording twice, in AcqData
    # and as MSD ChemStation .ms files; where AcqData's scans were read, the
    # .ms files holding the same scans are that recording again, unless the
    # caller asked for them by name.
    named = {name.lower() for name in requested_files or ()}
    acq_times = [f.xlabels for f in acquired if f.detector == 'MS']
    if acq_times:
        acq_times = np.concatenate(acq_times)
        datafiles = [f for f in datafiles
                     if f.name.lower() in named
                     or not _same_recording(_ms_milliseconds(f), acq_times)]

    # The method and sample sidecars, and each MS file's acquisition mode and
    # method signal, filling gaps without overriding the values above: the
    # step a .sirslt goes through too (sirslt.read).
    method.state_run(path, datafiles, metadata)

    # Surface unread MassHunter profile/centroid data so the hrms and centroid
    # flags are discoverable: a .D with MSProfile.bin holds a profile spectrum
    # parsed only when hrms=True, and MSPeak.bin a centroid spectrum parsed only
    # when centroid=True. Otherwise read() returns an empty DataDirectory with
    # no hint that the flag is what's missing.
    if not hrms and os.path.isfile(
            os.path.join(path, "AcqData", "MSProfile.bin")):
        metadata['hrms_available'] = True

    if not centroid and os.path.isfile(
            os.path.join(path, "AcqData", "MSPeak.bin")):
        metadata['centroid_available'] = True

    datadir = DataDirectory(path, datafiles, metadata)
    if peaks:
        datadir.peaks = _with_channels(datadir, injection_peaks(path))
    return datadir


def injection_peaks(path):
    """
    Reads the integrated peaks of one injection .D directory.

    The same peaks :func:`read_sequence` attaches to the injection, found the
    same way: from the ``sequence.acaml`` of the sequence directory the .D
    sits in, matched by the .D's folder name, or failing that from the .D's
    own ``sequence.acam_``.

    The result document of a sequence holds every injection's results. It is
    parsed once while it is unchanged, so reading the injections of one
    sequence one at a time parses it once; each call gets its own copy.

    Args:
        path (str): Path of the .D directory.

    Returns:
        list: The injection's signal groups (see
        :func:`rainbow.agilent.sequence.parse_peaks`), or ``[]`` when no
        result document covers it.

    """
    from rainbow.agilent import sequence
    # Absolute, so a relative path such as "run.D" still has a parent
    # directory to look for the sequence.acaml in.
    path = os.path.abspath(path)
    name = os.path.basename(path)
    sequence_acaml = sequence.find(os.path.dirname(path) or os.curdir)
    groups = None
    if sequence_acaml is not None:
        groups = sequence.injection_groups(sequence_acaml, name)
    if not groups:
        groups = _own_peaks(name, path)
    return groups or []


def injection_dirs(path):
    """
    Returns the injection .D subdirectories of a sequence directory, sorted.

    A ChemStation/OpenLab sequence directory holds one .D subdirectory per
    injection (the sequence-level method and acaml live alongside them). The
    .D names are sorted, which is acquisition order for the names ChemStation
    writes by default, since it prefixes each with the sequence line number.

    It is name order, though, not a timestamp: nothing here reads one. Names
    that do not zero-pad that number sort 1, 10, 2, and a directory renamed by
    hand sorts wherever its new name falls.

    Args:
        path (str): Path of the sequence directory.

    Returns:
        list: Absolute paths of the injection .D subdirectories.

    """
    if not isinstance(path, str) or not os.path.isdir(path):
        return []
    return [
        os.path.join(path, name)
        for name in sorted(os.listdir(path))
        if name.lower().endswith('.d')
        and os.path.isdir(os.path.join(path, name))
    ]


def read_sequence(path, display_precision='auto', hrms=False,
                  requested_files=None, telemetry=False, centroid=False,
                  peaks=False, bin_width=None, **removed):
    """
    Reads an Agilent ChemStation/OpenLab sequence directory.

    Each injection .D subdirectory is read with :func:`read`, so the per-
    injection result is exactly what a single read returns. The injections are
    returned in sorted-name order, which is acquisition order for ChemStation's
    default naming (see :func:`injection_dirs`).

    Args:
        path (str): Path of the sequence directory.
        display_precision (int or 'auto', optional): Decimals for displayed m/z
            labels (cosmetic).
        hrms (bool, optional): Flag for parsing the MassHunter profile
            spectrum (MSProfile.bin).
        requested_files (list, optional): List of filenames to parse.
        telemetry (bool, optional): Flag for parsing .dx telemetry traces.
        centroid (bool, optional): Flag for parsing the MassHunter centroid
            spectrum (MSPeak.bin).
        peaks (bool, optional): Flag for reading the integrated peaks from
            sequence.acaml and attaching them to each injection.

    Returns:
        DataSequence representing the sequence, or None if no injections.

    """
    if removed:
        reject_removed_arguments("agilent.read_sequence", removed)
    injection_paths = injection_dirs(path)
    if not injection_paths:
        return None

    injections = [
        read(p, display_precision, hrms, requested_files, telemetry, centroid,
             bin_width)
        for p in injection_paths
    ]
    metadata = {'injection_count': len(injections)}

    # Merge the sequence-level document (instrument, operator), and let its
    # sequence-wide operator fill any injection that lacked one.
    from rainbow.agilent import sequence
    sequence_acaml = sequence.find(path)
    if sequence_acaml is not None:
        header = sequence.parse_header(sequence_acaml)
        metadata.update(header)
        operator = header.get('operator')
        if operator is not None:
            for injection in injections:
                injection.metadata.setdefault('operator', operator)

    # With no sequence-level operator, adopt the injections' operator when they
    # agree, so the sequence carries it too.
    if 'operator' not in metadata:
        operators = {inj.metadata.get('operator') for inj in injections}
        operators.discard(None)
        if len(operators) == 1:
            metadata['operator'] = operators.pop()

    if peaks:
        _attach_peaks(injections, injection_paths, sequence_acaml)
        metadata['peaks_read'] = True

    return DataSequence(path, injections, metadata)


def _attach_peaks(injections, injection_paths, sequence_acaml):
    """
    Attaches integrated peaks to each injection.

    Peaks come from the sequence-level sequence.acaml when present, matched to
    each injection by its .D folder name. Any injection not covered there (for
    example a sequence that has no top-level document) falls back to the
    per-injection sequence.acam_ inside its own .D.
    """
    from rainbow.agilent import sequence
    for injection, injection_path in zip(injections, injection_paths):
        groups = None
        if sequence_acaml is not None:
            groups = sequence.injection_groups(sequence_acaml, injection.name)
        if not groups:
            groups = _own_peaks(injection.name, injection_path)
        injection.peaks = _with_channels(injection, groups or [])


def _with_channels(datadir, groups):
    """``groups`` with each one's detector and metadata from its DataFile.

    A result document names the channel a signal was integrated on but not
    its detector, which the run's own file for that channel does say. A
    group whose channel the run did not read keeps None.
    """
    by_key = {os.path.splitext(datafile.name)[0].upper(): datafile
              for datafile in datadir.datafiles + datadir.analog}
    for group in groups:
        channel = group.get("channel_file") or group.get("signal") or ""
        datafile = by_key.get(
            os.path.splitext(channel)[0].replace(" ", "").upper())
        if datafile is not None:
            group["detector"] = datafile.detector
            group["metadata"] = dict(datafile.metadata)
            _fill_units(group, datafile.metadata.get("unit"))
    return groups


def _fill_units(group, unit):
    """Gives a group's peaks the channel's unit where they state none.

    ChemStation's peak table is in the channel's unit, a height in it and an
    area in it per second, but does not say so.
    """
    if not unit:
        return
    lists = [group["peaks"]] + [alternate["peaks"] for alternate
                                in group.get("alternates") or []]
    for peaks in lists:
        for peak in peaks:
            if peak.get("height_unit") is None:
                peak["height_unit"] = unit
            if peak.get("area_unit") is None:
                peak["area_unit"] = unit + ".s"


def _own_peaks(injection_name, injection_path):
    """Peaks from an injection's own result document (sequence.acam_)."""
    from rainbow.agilent import sequence
    document = sequence.find_result_document(injection_path)
    if document is None:
        return None
    # A per-injection document holds exactly this injection's peaks.
    return sequence.injection_groups(document, injection_name, sole=True)


def read_metadata(path):
    """
    Reads metadata from an Agilent .D directory.

    Args:
        path (str): Path of the directory.

    Returns:
        Dictionary containing a list of datafiles and the metadata. Where the
        .D holds its MS scans twice (AcqData and .ms files, see :func:`read`),
        the .ms files are listed and ``copies`` names, for each AcqData file
        the ``centroid`` or ``hrms`` flag reads, the .ms files it takes the
        place of: ``{'MSPeak.bin': ['data.ms', 'dataSim.ms']}``.

    """
    if os.path.splitext(path)[1].lower() == '.dx':
        from rainbow.agilent import openlab
        return openlab.read_metadata(path)

    from rainbow.agilent import sirslt
    if sirslt.is_sirslt(path):
        return sirslt.read_metadata(path)

    # The date and vial position come from the Chemstation files' headers,
    # read without their data, so they are what read() states.
    metadata = chemstation.parse_header_metadata(path)
    # read() parses the .D's own Chemstation files in every run, AcqData or
    # not, so they are listed in every run, ahead of the MassHunter files as
    # read() returns them.
    chemstation_files = chemstation.datafile_names(path)

    # MassHunter acquisitions (a .D with an AcqData subfolder) keep their data
    # in MSProfile.bin (profile/HRMS) and/or MSPeak.bin (centroid), which the
    # Chemstation .uv/.ch/.ms scan below never finds - so they used to come
    # back with an empty datafile list. Mirror masshunter.parse_allfiles'
    # detection to surface the datafile names and the flags needed to read
    # them (hrms / centroid), without parsing the binaries.
    acqdata_path = os.path.join(path, "AcqData")
    if os.path.isdir(acqdata_path):
        from rainbow.agilent import masshunter
        acqdata_files = set(os.listdir(acqdata_path))
        mh_datafiles = []
        held = []
        said = {}
        # A diode-array detector writes its chromatograms and spectra here too,
        # and read() returns those with no flag needed - so a run holding them
        # must not be reported as MS-only.
        for name in sorted(acqdata_files):
            stem, ext = os.path.splitext(name)
            if (ext.lower() in ('.cg', '.sp')
                    and stem[:3].upper() in masshunter._DAD_DEVICES):
                mh_datafiles.append(name)
        if {"MSScan.xsd", "MSScan.bin"} <= acqdata_files:
            # The scans' one recording is listed once: where the .D's own .ms
            # files hold AcqData's scans, by them, as read() returns it
            # without a flag (the flags read it from AcqData instead).
            ms_names = [name for name in chemstation_files
                        if name.lower().endswith('.ms')]
            if ms_names:
                times = masshunter.scan_times(acqdata_path)
                held = [name for name in ms_names
                        if _same_recording(chemstation.ms_scan_times(
                            os.path.join(path, name)), times)]
            if "MSProfile.bin" in acqdata_files:
                if not held:
                    mh_datafiles.append("MSProfile.bin")
                metadata['hrms_available'] = True
            if "MSPeak.bin" in acqdata_files:
                if not held:
                    mh_datafiles.append("MSPeak.bin")
                metadata['centroid_available'] = True
        if held:
            # What the flags read instead: each AcqData file with the .ms
            # files holding its scans.
            said['copies'] = {
                name: held for name in ("MSPeak.bin", "MSProfile.bin")
                if name in acqdata_files}
        if mh_datafiles or held:
            return {**said, 'datafiles': chemstation_files + mh_datafiles,
                    'metadata': method.state_run(path, [], metadata)}

    if len(metadata) == 1:
        datadir = read(path)
        if datadir:
            return {'datafiles': datadir.datafiles + datadir.analog, 'metadata': datadir.metadata}
        return None
    # Masshunter datafiles are not located.
    return {'datafiles': chemstation_files,
            'metadata': method.state_run(path, [], metadata)}


def _ms_milliseconds(datafile):
    """A ChemStation .ms DataFile's scan times in the integer milliseconds the
    file stores them in, or None for any other file."""
    if datafile.detector != 'MS' or not datafile.name.lower().endswith('.ms'):
        return None
    return np.round(np.asarray(datafile.xlabels) * 60000).astype(np.int64)


def _same_recording(ms_times, acq_times):
    """
    Whether an MSD ChemStation .ms file holds scans MassHunter's AcqData
    recorded: every scan time it stores is one of AcqData's scan times, at the
    millisecond the .ms format stores times to. A MassHunter GC/MS acquisition
    writes its scans to AcqData (MSScan.bin with MSPeak.bin) and the same scans
    again as data.ms (Scan) and dataSim.ms (SIM), so these are one recording.

    Args:
        ms_times (numpy.ndarray): The .ms file's scan times, in milliseconds
            (:obj:`chemstation.ms_scan_times`), or None.
        acq_times (numpy.ndarray): AcqData's scan times, in minutes, or None.

    Returns:
        bool

    """
    if ms_times is None or acq_times is None:
        return False
    ms_times = np.asarray(ms_times)
    if not ms_times.size:
        return False
    acq_ms = np.round(np.asarray(acq_times, dtype=np.float64) * 60000)
    return bool(np.isin(ms_times, acq_ms.astype(np.int64)).all())
