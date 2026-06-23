import os

from rainbow.agilent import chemstation
from rainbow.datadirectory import DataDirectory


def read(path, prec=0, hrms=False, requested_files=None, telemetry=False,
         centroid=False, binned=True):
    """
    Reads an Agilent .D directory or .dx archive.

    Args:
        path (str): Path of the directory or .dx file.
        prec (int, optional): Number of decimals to round masses.
        hrms (bool, optional): Flag for parsing the MassHunter profile
            spectrum (MSProfile.bin).
        requested_files (list, optional): List of filenames to parse.
        telemetry (bool, optional): Flag for parsing .dx telemetry traces.
        centroid (bool, optional): Flag for parsing the MassHunter centroid
            spectrum (MSPeak.bin).
        binned (bool, optional): For the HRMS profile, project onto the shared
            m/z grid (the default) or, when False, keep the per-scan
            representation (one :class:`~rainbow.agilent.masshunter.ProfileDataFile`
            per flight-time grid).

    Returns:
        DataDirectory representing the Agilent data.

    """
    if os.path.splitext(path)[1].lower() == '.dx':
        from rainbow.agilent import openlab
        return openlab.read(path, prec, requested_files, telemetry)

    datafiles = []
    datafiles.extend(chemstation.parse_allfiles(path, prec, requested_files))
    if hrms or centroid:
        try:
            from rainbow.agilent import masshunter
            datafiles.extend(
                masshunter.parse_allfiles(path, prec, hrms, centroid, binned))
        except ModuleNotFoundError:
            raise ModuleNotFoundError("You must install python-lzf to parse masshunter files.")

    metadata = chemstation.parse_metadata(path, datafiles)

    # Surface unread MassHunter centroid data so the centroid flag is
    # discoverable: a .D with MSPeak.bin holds a centroid spectrum that is only
    # parsed when centroid=True.
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
    if len(metadata) == 1:
        datadir = read(path)
        if datadir:
            return {'datafiles': datadir.datafiles + datadir.analog, 'metadata': datadir.metadata}
        return None
    # Masshunter datafiles are not located.
    datafiles = [fn for fn in os.listdir(path) if fn[-3:].lower() in ('.uv', '.ch', '.ms')]
    return {'datafiles': datafiles, 'metadata': metadata}
