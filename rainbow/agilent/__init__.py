import os

from rainbow._arguments import reject_removed_arguments
from rainbow.agilent import chemstation
from rainbow.datadirectory import DataDirectory
from rainbow.datasequence import DataSequence


def read(path, display_precision='auto', hrms=False, requested_files=None,
         telemetry=False, centroid=False, bin_width=None, **removed):
    """
    Reads an Agilent .D directory or .dx archive.

    Args:
        path (str): Path of the directory or .dx file.
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
            spectrum (MSPeak.bin).
        bin_width (float, optional): m/z bin width in daltons, the lossy binning
            control. For regular MS the default is nominal mass (1 Da); for the
            HRMS profile, omit it (the default) to keep the per-scan
            representation (one
            :class:`~rainbow.agilent.masshunter.ProfileDataFile` per flight-time
            grid), or pass a width to project onto the shared m/z grid.

    Returns:
        DataDirectory representing the Agilent data.

    """
    if removed:
        reject_removed_arguments("agilent.read", removed)
    if os.path.splitext(path)[1].lower() == '.dx':
        from rainbow.agilent import openlab
        return openlab.read(
            path, display_precision, requested_files, telemetry, bin_width)

    datafiles = []
    datafiles.extend(chemstation.parse_allfiles(
        path, display_precision, bin_width, requested_files))
    # MassHunter is always consulted, not only under the MS flags: a .d may also
    # hold DAD data, which is parsed unconditionally the way the Chemstation UV
    # formats are. The MS parsing inside stays gated on hrms/centroid.
    from rainbow.agilent import masshunter
    datafiles.extend(masshunter.parse_allfiles(
        path, display_precision, hrms, centroid, bin_width, telemetry,
        requested_files))

    metadata = chemstation.parse_metadata(path, datafiles)

    # Enrich with the per-injection method and sample sidecars (acq.macaml,
    # SAMPLE.XML), filling gaps without overriding the values above.
    from rainbow.agilent import method
    for key, value in method.parse_injection_metadata(path).items():
        metadata.setdefault(key, value)

    # Tag each MS channel SIM or Scan from the acquisition method, so a SIM run
    # (its monitored ions) is distinguishable from a full scan.
    method.tag_acquisition_modes(path, datafiles)

    # Record the separation technique the method declares (gas vs liquid
    # chromatography), so an export routes by what the instrument says rather
    # than guessing from the detectors.
    technique = method.acquisition_technique(path)
    if technique:
        metadata.setdefault('technique', technique)

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

    return DataDirectory(path, datafiles, metadata)


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
    # run-wide operator fill any injection that lacked one.
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
    if sequence_acaml is not None:
        by_injection = sequence.parse_peaks(sequence_acaml)
        folded = {name.lower(): groups
                  for name, groups in by_injection.items()}
    else:
        folded = {}

    for injection, injection_path in zip(injections, injection_paths):
        groups = folded.get(injection.name.lower())
        if not groups:
            groups = _injection_peaks(injection, injection_path)
        injection.peaks = groups or []


def _injection_peaks(injection, injection_path):
    """Peaks from an injection's own result document (sequence.acam_)."""
    from rainbow.agilent import sequence
    document = sequence.find_result_document(injection_path)
    if document is None:
        return None
    by_injection = sequence.parse_peaks(document)
    if not by_injection:
        return None
    folded = {name.lower(): groups for name, groups in by_injection.items()}
    groups = folded.get(injection.name.lower())
    if groups is None and len(by_injection) == 1:
        # A per-injection document holds exactly this injection's peaks.
        groups = next(iter(by_injection.values()))
    return groups


def read_metadata(path):
    """
    Reads metadata from an Agilent .D directory.

    Args:
        path (str): Path of the directory.

    Returns:
        Dictionary containing a list of datafiles and the metadata.

    """
    if os.path.splitext(path)[1].lower() == '.dx':
        from rainbow.agilent import openlab
        return openlab.read_metadata(path)

    datafiles = []
    metadata = chemstation.parse_metadata(path, datafiles)

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
        # A diode-array detector writes its chromatograms and spectra here too,
        # and read() returns those with no flag needed - so a run holding them
        # must not be reported as MS-only.
        for name in sorted(acqdata_files):
            stem, ext = os.path.splitext(name)
            if (ext.lower() in ('.cg', '.sp')
                    and stem[:3].upper() in masshunter._DAD_DEVICES):
                mh_datafiles.append(name)
        if {"MSScan.xsd", "MSScan.bin"} <= acqdata_files:
            if "MSProfile.bin" in acqdata_files:
                mh_datafiles.append("MSProfile.bin")
                metadata['hrms_available'] = True
            if "MSPeak.bin" in acqdata_files:
                mh_datafiles.append("MSPeak.bin")
                metadata['centroid_available'] = True
        if mh_datafiles:
            return {'datafiles': mh_datafiles, 'metadata': metadata}

    if len(metadata) == 1:
        datadir = read(path)
        if datadir:
            return {'datafiles': datadir.datafiles + datadir.analog, 'metadata': datadir.metadata}
        return None
    # Masshunter datafiles are not located.
    datafiles = [fn for fn in os.listdir(path) if fn[-3:].lower() in ('.uv', '.ch', '.ms')]
    return {'datafiles': datafiles, 'metadata': metadata}
