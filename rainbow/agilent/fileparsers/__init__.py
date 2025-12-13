import os

from rainbow.agilent.fileparsers.ch_parser import parse_ch
from rainbow.agilent.fileparsers.ms_parser import parse_ms
from rainbow.agilent.fileparsers.uv_parser import parse_uv

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