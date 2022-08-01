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
        from rainbow.agilent import masshunter 
        datafiles.extend(masshunter.parse_allfiles(path))

    metadata = chemstation.parse_metadata(path, datafiles)

    return DataDirectory(path, datafiles, metadata)