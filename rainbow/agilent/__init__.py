from rainbow.agilent import chemstation, masshunter
from rainbow.datadirectory import DataDirectory


def parse_directory(path, prec=0, hrms=False):
    """
     
    """
    datafiles = []
    datafiles.extend(chemstation.parse_files(path))
    # datafiles.extend(masshunter.parse_files(path))

    return DataDirectory(path, datafiles, {'vendor': "Agilent"})