import struct
import os
import pathlib
import agilent 


def find_ext(dir, ext):
    found = [fn for fn in os.listdir(dir) if fn.lower().endswith(ext)]
    assert (len(found) == 1)
    return found[0]

# Tries to automatically identifies filetype
# Currently relies on file extension to do so
def read(filepath):

    ext = os.path.splitext(filepath)[1].lower() 
    
    # csv file
    # todo: check if the file is a csv by actually parsing it
    if os.path.isfile(filepath) and ext == ".csv":
        return 1

    # data folders
    if os.path.isdir(filepath): 
        if ext == ".d":
            print(os.path.join(filepath, find_ext(filepath, ".uv")))
            return agilent.AgilentUV(os.path.join(filepath, find_ext(filepath, ".uv")))
        elif ext == ".raw":
            raise NotImplementedError 
