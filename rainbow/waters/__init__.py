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