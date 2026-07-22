import os

from rainbow.agilent import chemstation
from rainbow.datadirectory import DataDirectory


def read(path, precision='auto', hrms=False, requested_files=None,
         telemetry=False, centroid=False, bin_width=None):
    """
    Reads an Agilent .D directory or .dx archive.

    Args:
        path (str): Path of the directory or .dx file.
        precision (int or 'auto', optional): Number of decimals to round masses.
            ``'auto'`` picks 4 for high-resolution data and 0 otherwise, per file.
        hrms (bool, optional): Flag for parsing the MassHunter profile
            spectrum (MSProfile.bin).
        requested_files (list, optional): List of filenames to parse.
        telemetry (bool, optional): Flag for parsing .dx telemetry traces.
        centroid (bool, optional): Flag for parsing the MassHunter centroid
            spectrum (MSPeak.bin).
        bin_width (float, optional): Shared-grid bin width in daltons for the
            HRMS profile. Omit it (the default) to keep the per-scan
            representation (one
            :class:`~rainbow.agilent.masshunter.ProfileDataFile` per flight-time
            grid); pass a width to project onto the shared m/z grid.

    Returns:
        DataDirectory representing the Agilent data.

    """
    if os.path.splitext(path)[1].lower() == '.dx':
        from rainbow.agilent import openlab
        return openlab.read(path, precision, requested_files, telemetry)

    datafiles = []
    datafiles.extend(chemstation.parse_allfiles(path, precision, requested_files))
    if hrms or centroid:
        try:
            from rainbow.agilent import masshunter
            datafiles.extend(masshunter.parse_allfiles(
                path, precision, hrms, centroid, bin_width))
        except ModuleNotFoundError:
            raise ModuleNotFoundError("You must install python-lzf to parse masshunter files.")

    metadata = chemstation.parse_metadata(path, datafiles)

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
        acqdata_files = set(os.listdir(acqdata_path))
        if {"MSScan.xsd", "MSScan.bin"} <= acqdata_files:
            mh_datafiles = []
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
