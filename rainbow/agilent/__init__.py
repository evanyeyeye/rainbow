from rainbow.agilent import chemstation
from rainbow.datadirectory import DataDirectory


def parse_directory(path, prec=0, hrms=False):
    """
    Parses an Agilent .D directory. 

    Args:
        path (str): Path of the directory.
        prec (int, optional): Number of decimals to round ylabels.
        hrms (bool, optional): Flag for HRMS parsing. 

    Returns:
        DataDirectory representing the Agilent .D directory. 

    """
    datafiles = []
    datafiles.extend(chemstation.parse_allfiles(path, prec))
    if hrms: 
        from rainbow.agilent import masshunter 
        datafiles.extend(masshunter.parse_allfiles(path))

    return DataDirectory(path, datafiles, {'vendor': "Agilent"})