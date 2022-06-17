import struct
import os
from rainbow.parser import agilent


def read(dirpath):
    """
    Function that reads chromatogram data directory. 
    
    Args:
        dirpath (str): Path of the directory.

    Returns:
        DataDirectory representing the data directory. 

    """
    ext = os.path.splitext(dirpath)[1].lower()
    
    # csv file
    # todo: check if the file is a csv by actually parsing it
    if os.path.isfile(dirpath) and ext == ".csv":
        raise NotImplementedError

    # data folders
    if os.path.isdir(dirpath): 
        if ext.upper() == ".D":
            return agilent.parse_directory(dirpath)
        elif ext == ".raw":
            raise NotImplementedError       