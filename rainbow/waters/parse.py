from rainbow.waters import masslynx
from rainbow.datadirectory import DataDirectory


def parse_directory(path):
    """

    """
    datafiles = []
    datafiles.extend(masslynx.parse_analog(path))
    datafiles.extend(masslynx.parse_spectrum(path))
    
    return DataDirectory(path, datafiles)