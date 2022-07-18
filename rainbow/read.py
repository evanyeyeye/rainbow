import os 
from rainbow import agilent, waters


def read(path):
    """
    Reads a chromatogram data directory. Main method of the package. 

    Args:
        path (str): Path of the directory.

    Returns:
        DataDirectory representing the data directory. 

    """
    if not os.path.isdir(path):
        raise Exception(f"{path} is not a directory.")

    datadir = None
    ext = os.path.splitext(path)[1]
    if ext.upper() == '.D':
        datadir = agilent.parse_directory(path)
    elif ext.lower() == '.raw':
        datadir = waters.parse_directory(path)
    
    if datadir is None:
        raise Exception(f"Rainbow cannot read {path}.")
    return datadir