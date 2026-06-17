import os

from rainbow.agilent import chemstation
from rainbow.datadirectory import DataDirectory


def read(path, prec=0, hrms=False, requested_files=None, telemetry=False):
    """
    Reads an Agilent .D directory or .dx archive.

    Args:
        path (str): Path of the directory or .dx file.
        prec (int, optional): Number of decimals to round masses.
        hrms (bool, optional): Flag for HRMS parsing.
        requested_files (list, optional): List of filenames to parse.
        telemetry (bool, optional): Flag for parsing .dx telemetry traces.

    Returns:
        DataDirectory representing the Agilent data.

    """
    if os.path.splitext(path)[1].lower() == '.dx':
        from rainbow.agilent import openlab
        return openlab.read(path, prec, requested_files, telemetry)

    datafiles = []
    datafiles.extend(chemstation.parse_allfiles(path, prec, requested_files))
    if hrms:
        try:
            from rainbow.agilent import masshunter
            datafiles.extend(masshunter.parse_allfiles(path))
        except ModuleNotFoundError:
            raise ModuleNotFoundError("You must install python-lzf to parse masshunter files.")

    metadata = chemstation.parse_metadata(path, datafiles)

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
