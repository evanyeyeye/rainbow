import os 
from rainbow import agilent, waters


def read(path, prec=0, hrms=False):
    """
    Reads a chromatogram data directory. Main method of the package. 

    Args:
        path (str): Path of the directory.
        prec (int, optional): Number of decimals to round ylabels.
        hrms (bool, optional): Flag for Agilent HRMS parsing. 

    Returns:
        DataDirectory representing the data directory. 

    """
    if not isinstance(path, str) or not os.path.isdir(path):
        raise Exception(f"{path} is not a directory.")

    if not isinstance(prec, int) or prec < 0:
        raise Exception(f"Invalid precision: {prec}.") 

    if not isinstance(hrms, bool):
        raise Exception(f"The hrms flag must be a boolean.")

    datadir = None
    ext = os.path.splitext(path)[1]
    if ext.upper() == '.D':
        datadir = agilent.parse_directory(path, prec, hrms)
    elif ext.lower() == '.raw':
        datadir = waters.parse_directory(path, prec)
    
    if datadir is None:
        raise Exception(f"Rainbow cannot read {path}.")
    return datadir