import os 
from rainbow.datafile import DataFile
from rainbow.datadirectory import DataDirectory


def read(path, prec=0, hrms=False):
    """
    Reads a chromatogram data directory. Main method of the package. 

    Increasing the precision may drastically increase memory usage for \
        larger files. Specifying a higher precision mainly affects the \
        parsing of MS data, because intensities are summed within the given \
        precision for each ylabel.
        
    Max precision available for Agilent MS data is 1. 
    
    Max precision recommended for Waters MS data is 3. 
   
    The accuracy of Agilent HRMS is not guaranteed. Set the flag to try it.

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
        from rainbow import agilent
        datadir = agilent.parse_directory(path, prec, hrms)
    elif ext.lower() == '.raw':
        from rainbow import waters
        datadir = waters.parse_directory(path, prec)
    
    if datadir is None:
        raise Exception(f"Rainbow cannot read {path}.")
    return datadir