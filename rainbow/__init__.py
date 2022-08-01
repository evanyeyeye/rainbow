import os 
from rainbow.datafile import DataFile
from rainbow.datadirectory import DataDirectory
from rainbow import agilent, waters


def read(path, prec=0, hrms=False):
    """
    Reads a chromatogram data directory. Main method of the package. 

    Increasing the precision may drastically increase memory usage for \
        larger files. Specifying a higher precision mainly affects the \
        parsing of MS data, because intensities are summed within the given \
        precision for each ylabel.
        
    Max precision available for Agilent MS data is 1. 
    
    Max precision recommended for Waters MS data is 3. 
   
    Agilent HRMS parsing may be slow. Set the flag to enable it.

    Args:
        path (str): Path of the directory.
        prec (int, optional): Number of decimals to round ylabels.
        hrms (bool, optional): Flag for Agilent HRMS parsing. 

    Returns:
        DataDirectory representing the directory. 

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
        datadir = agilent.read(path, prec, hrms)
    elif ext.lower() == '.raw':
        datadir = waters.read(path, prec)
    
    if datadir is None:
        raise Exception(f"Rainbow cannot read {path}.")
    return datadir