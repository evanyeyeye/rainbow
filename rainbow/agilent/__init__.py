from rainbow.agilent import chemstation
from rainbow.datadirectory import DataDirectory


def read(path, prec=0, hrms=False):
    """
    Reads an Agilent .D directory. 

    Args:
        path (str): Path of the directory.
        prec (int, optional): Number of decimals to round masses.
        hrms (bool, optional): Flag for HRMS parsing. 

    Returns:
        DataDirectory representing the Agilent .D directory. 

    """
    datafiles = []
    datafiles.extend(chemstation.parse_allfiles(path, prec))
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
        Dictionary representing metadata in the Agilent .D directory.

    """
    datafiles = []
    metadata = chemstation.parse_metadata(path, datafiles)
    if len(metadata) == 1:
        datadir = read(path)
        return datadir.metadata if datadir else None
    return metadata
