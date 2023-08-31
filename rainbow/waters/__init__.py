from rainbow.waters import masslynx
from rainbow.datadirectory import DataDirectory


def read(path, prec=0):
    """
    Reads a Waters .raw directory. 

    Args:
        path (str): Path of the directory.
        prec (int, optional): Number of decimals to round ylabels.

    Returns:
        DataDirectory representing the Waters .raw directory. 

    """
    datafiles = []
    datafiles.extend(masslynx.parse_spectrum(path, prec))
    datafiles.extend(masslynx.parse_analog(path))

    metadata = masslynx.parse_metadata(path)

    return DataDirectory(path, datafiles, metadata)

def read_metadata(path):
    """
    Reads metdata from a Waters .raw directory.

    Args:
        path (str): Path of the directory.

    Returns:
        Dictionary representing metadata in the Waters .raw directory.
    """
    datafiles = []
    metadata = masslynx.parse_metadata(path)
    if len(metadata) == 1:
        datadir = read(path)
        return datadir.metadata if datadir else None
    return metadata
