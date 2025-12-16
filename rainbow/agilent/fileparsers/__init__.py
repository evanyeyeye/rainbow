import os
from pathlib import Path
from typing import BinaryIO

from rainbow.agilent.fileparsers.ch_parser import parse_ch, parse_ch
from rainbow.agilent.fileparsers.ms_parser import parse_ms
from rainbow.agilent.fileparsers.uv_parser import parse_uv, parse_uv_fileobj

def parse_file(path, prec=0):
    """
    Parses an Agilent Chemstation data file. 
    
    Supported extensions are .ch, .uv, and .ms. 

    Args:
        path (str): Path to the data file.
        prec (int, optional): Number of decimals to round mz values.
    
    Returns:
        DataFile representing the file, if it can be parsed. Otherwise, None.

    """
    ext = os.path.splitext(path)[1].lower()
    if ext == '.ch':
        return parse_ch(path)
    elif ext == '.uv':
        return parse_uv(path)
    elif ext == '.ms':
        return parse_ms(path, prec)
    return None

def parse_file_from_fileobj(fileobj: BinaryIO, 
                            path: str | Path = "UNSPECIFIED",
                            prec: int = 0):
    """
    Parses an Agilent Chemstation data file. 
    
    Supported extensions are .ch, .uv, and .ms. 

    Args:
        path (str): Path to the data file.
        prec (int, optional): Number of decimals to round mz values.
    
    Returns:
        DataFile representing the file, if it can be parsed. Otherwise, None.

    """
    ext = os.path.splitext(path)[1].lower()
    if ext == '.ch':
        return None # TODO: Implement
    elif ext == '.uv':
        return parse_uv_fileobj(fileobj)
    elif ext == '.ms':
        return None # TODO: Implement
    return None