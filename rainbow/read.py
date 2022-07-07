import struct
import os
from rainbow.agilent import chemstation, masshunter


def read(path):
    """
    Function that reads a chromatogram data directory. 
    
    Args:
        path (str): Path of the directory.

    Returns:
        DataDirectory representing the data directory. 

    """
    if not os.path.isdir(path):
        raise Exception(f"{path} is not a directory.")

    datadir = None

    ext = os.path.splitext(path)[1].lower()
    if ext.upper() == '.D':
        datadir = chemstation.read_directory(path)
        if not datadir:
            datadir = masshunter.read_directory(path)
    elif ext.lower() == '.raw':
        raise NotImplementedError

    if not datadir:
        raise Exception(f"Rainbow cannot read {path}.")

    return datadir


def read_csv():
    pass   