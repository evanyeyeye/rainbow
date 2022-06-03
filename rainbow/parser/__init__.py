import struct
import os
import parser.agilent 


def find_ext(dir, ext):
    """
    Helper function to find the file in the directory with the specified extension.

    """
    found = [fn for fn in os.listdir(dir) if fn.lower().endswith(ext)]
    assert (len(found) == 1)
    return found[0]

# Tries to automatically identifies filetype
# Currently relies on file extension to do so
def read(filepath):
    """
    Function to read chromatogram data folders. 

    This function is the main way to use the package. 
    
    Returns a Chromatogram object based on filetype. 

    """
    ext = os.path.splitext(filepath)[1].lower() 
    
    # csv file
    # todo: check if the file is a csv by actually parsing it
    if os.path.isfile(filepath) and ext == ".csv":
        raise NotImplementedError

    # data folders
    if os.path.isdir(filepath): 
        if ext == ".d":
            return agilent.AgilentUV(os.path.join(filepath, find_ext(filepath, ".uv")))
        elif ext == ".raw":
            raise NotImplementedError       