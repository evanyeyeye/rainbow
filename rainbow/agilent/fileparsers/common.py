import struct 

""" 
FILE METADATA PARSING METHODS
"""

def read_header(f, offsets, gap=2):
    """
    Extracts metadata from the header of an Agilent data file. 

    Args:
        f (_io.BufferedReader): File opened in 'rb' mode.
        offsets (dict): Dictionary mapping properties to file offsets. 
        gap (int): Distance between two adjacent characters.

    Returns:
        Dictionary containing metadata as string key-value pairs. 

    """
    metadata = {}
    for key, offset in offsets.items():
        string = read_string(f, offset, gap)
        if string:
            metadata[key] = string
    return metadata


def read_string(f, offset, gap=2):
    """
    Extracts a string from the specified offset.

    This method is primarily useful for retrieving metadata. 

    Args:
        f (_io.BufferedReader): File opened in 'rb' mode. 
        offset (int): Offset to begin reading from. 
        gap (int): Distance between two adjacent characters.
    
    Returns:
        String at the specified offset in the file header. 

    """
    f.seek(offset)
    str_len = struct.unpack("<B", f.read(1))[0] * gap
    try:
        return f.read(str_len)[::gap].decode().strip()
    except Exception:
        return ""
    
