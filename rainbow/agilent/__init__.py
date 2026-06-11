import os

from rainbow.agilent import chemstation
from rainbow.datadirectory import DataDirectory


def read(path, prec=0, hrms=False, requested_files=None):
    """
    Reads an Agilent .D directory. 

    Args:
        path (str): Path of the directory.
        prec (int, optional): Number of decimals to round masses.
        hrms (bool, optional): Flag for HRMS parsing.
        requested_files (list, optional): List of filenames to parse.

    Returns:
        DataDirectory representing the Agilent .D directory. 

    """
    datafiles = []
    masshunter_metadata = {}
    datafiles.extend(chemstation.parse_allfiles(path, prec, requested_files))
    if hrms:
        try:
            from rainbow.agilent import masshunter
            datafiles.extend(masshunter.parse_allfiles(path))
            masshunter_metadata = masshunter.parse_metadata(path)
        except ModuleNotFoundError:
            raise ModuleNotFoundError("You must install python-lzf to parse masshunter files.")

    metadata = chemstation.parse_metadata(path, datafiles)
    metadata.update({
        key: value for key, value in masshunter_metadata.items()
        if key not in metadata
    })

    return DataDirectory(path, datafiles, metadata)


def read_metadata(path):
    """
    Reads metadata from an Agilent .D directory.

    Args:
        path (str): Path of the directory.

    Returns:
        Dictionary containing a list of datafiles and the metadata.

    """
    datafiles = []
    metadata = chemstation.parse_metadata(path, datafiles)
    try:
        from rainbow.agilent import masshunter
        metadata.update({
            key: value for key, value in masshunter.parse_metadata(path).items()
            if key not in metadata
        })
    except ModuleNotFoundError:
        pass

    if len(metadata) == 1:
        datadir = read(path)
        if datadir:
            return {'datafiles': datadir.datafiles + datadir.analog, 'metadata': datadir.metadata}
        return None
    datafiles = [fn for fn in os.listdir(path) if fn[-3:].lower() in ('.uv', '.ch', '.ms')]
    acqdata_path = os.path.join(path, "AcqData")
    if os.path.isdir(acqdata_path):
        if "MSProfile.bin" in os.listdir(acqdata_path):
            datafiles.append("MSProfile.bin")
    return {'datafiles': datafiles, 'metadata': metadata}
