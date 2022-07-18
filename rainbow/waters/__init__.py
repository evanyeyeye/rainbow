from rainbow.waters import masslynx
from rainbow.datadirectory import DataDirectory


def parse_directory(path, prec=0):
    """

    """
    datafiles = []
    datafiles.extend(masslynx.parse_analog(path))
    datafiles.extend(masslynx.parse_spectrum(path))

    metadata = masslynx.parse_header(path)

    return DataDirectory(path, datafiles, {'vendor': "Waters"})