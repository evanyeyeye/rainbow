import io
import struct
from pathlib import Path
from typing import BinaryIO

import numpy as np

from rainbow.datafile import DataFile
from rainbow.agilent.fileparsers.common import *

# --- Public API ---

def parse_uv(path: str | Path):
    """
    Parses an Agilent .uv file from a filepath.

    These files contain UV spectra. 

    Learn more about this file format :ref:`here <uv>`.

    Args:
        path (str): Path to the Agilent .uv file. 
    
    Returns:
        DataFile with UV data, if the file can be parsed. Otherwise, None.

    """
    with open(path, "rb") as f:
        return _parse_uv_core(f, path)

def parse_uv_fileobj(f: BinaryIO, 
                     path: str | Path = "UNSPECIFIED"):
    """
    Parses an Agilent .uv file from a BinaryIO object (useful if you've already
    opened the file).

    These files contain UV spectra. 

    Learn more about this file format :ref:`here <uv>`.

    Args:
        f (BinaryIO): An open binary stream for an Agilent .uv file.
        path (str, optional): Optional filepath (used for the DataFile output).
    
    Returns:
        DataFile with UV data, if the file can be parsed. Otherwise, None.

    """

    # Ensure binary stream (e.g. opened with 'rb' not 'r')
    if isinstance(f, io.TextIOBase):
        raise TypeError(
            "Expected a binary file-like object (opened in 'rb' mode), "
            "but got a text file object (opened in 'r' mode).")
    
    # Ensure stream is positioned at start (safe even if already at 0)
    try:
        f.seek(0)
    except Exception as e:
        raise IOError("Expected a seekable binary stream.") from e
    return _parse_uv_core(f, path)

def parse_uv_partial(path: str | Path):
    """
    Parses a partial Agilent .uv file from a filepath. 

    Learn more about this file format :ref:`here <uv>`.

    Args:
        path (str): Path to the partial .uv file. 
    
    Returns:
        DataFile with UV data, if the file can be parsed. Otherwise, None.

    """
    
    with open(path, "rb") as f:
        return _parse_uv_partial_core(f, path)

def parse_uv_partial_from_fileobj(f: BinaryIO, 
                                  path: str | Path = "UNSPECIFIED"):
    """
    Parses a partial Agilent .uv file from a BinaryIO object (useful if you've 
    already opened the file). 

    Learn more about this file format :ref:`here <uv>`.

    Args:
        f (BinaryIO): An open binary stream for an Agilent .uv file.
        path (str, optional): Optional filepath (used for the DataFile output).
    
    Returns:
        DataFile with UV data, if the file can be parsed. Otherwise, None.

    """
    
    if isinstance(f, io.TextIOBase):
        raise TypeError(
            "Expected a binary file-like object (opened in 'rb' mode), "
            "but received a text file object (opened in 'r' mode). "
            "Open the file in binary mode, e.g., open(path, 'rb')."
        )
    try:
        f.seek(0)
    except Exception as e:
        raise IOError("Expected a seekable binary stream.") from e
    return _parse_uv_partial_core(f, path)

# --- Internal cores ---

def _parse_uv_core(f: BinaryIO, path: str | Path = None):
    """Common parsing function based on filestreams."""
    head = read_string(f, 0, gap=1)

    if head == '131':
        data_offsets = {
            'num_times': 0x116,
            'scaling_factor': 0xC0D,
            'data_start': 0x1000
        }
        metadata_offsets = {
            "notebook": 0x35A,
            "date": 0x957,
            "method": 0xA0E,
            "unit": 0xC15,
            "signal": 0xC40,
            "vialpos": 0xFD7
        }
        file_type = read_string(f, 347, gap=2)
        if file_type.startswith('LC'):
            decode = decode_uv_delta
        elif file_type.startswith('OL'):
            decode = decode_uv_array
        else:
            return None
        gap = 2
    elif head == '31':
        data_offsets = {
            'num_times': 0x116,
            'scaling_factor': 0x13E,
            'data_start': 0x200
        }
        metadata_offsets = {
            "notebook": 0x18,
            "date": 0xB2,
            "method": 0xE4,
            "unit": 0x146
        }
        decode = decode_uv_delta
        gap = 1
    else:
        return None

    # Extract the number of retention times.
    f.seek(data_offsets["num_times"])
    num_times = struct.unpack(">I", f.read(4))[0]

    # If there are none, the file may be a partial.
    if num_times == 0:
        return _parse_uv_partial_core(f, path)

    # Compute the wavelengths by taking the range from 
    #     the header of the first data segment
    f.seek(data_offsets["data_start"] + 0x8)
    start_wlen, end_wlen, delta_wlen = \
        tuple(num // 20 for num in struct.unpack("<HHH", f.read(6)))
    wavelengths = np.arange(start_wlen, end_wlen + 1, delta_wlen)
    num_wavelengths = wavelengths.size

    # Extract the retention times and absorbances from each data segment.
    times, data = decode(f, data_offsets, num_times, num_wavelengths)

    # Covert times to minutes. 
    times = times / 60000

    # Scale the absorbances.
    f.seek(data_offsets['scaling_factor'])
    scaling_factor = struct.unpack('>d', f.read(8))[0]
    data = data * scaling_factor

    # Read file metadata.

    metadata = read_header(f, metadata_offsets, gap=gap)

    return DataFile(path, 'UV', times, wavelengths, data, metadata)

def _parse_uv_partial_core(f: BinaryIO, path: str | Path = None):
    """Common parsing function for 'partial' files."""
    data_offsets = {
        'num_times': 0x116,
        'scaling_factor': 0xC0D,
        'data_start': 0x1000
    }

    uint_unpack = struct.Struct('<I').unpack
    int_unpack = struct.Struct('<i').unpack
    short_unpack = struct.Struct('<h').unpack

    # Compute wavelengths from first data segment header
    f.seek(data_offsets["data_start"] + 0x8)
    try:
        start_wlen, end_wlen, delta_wlen = \
            tuple(num // 20 for num in struct.unpack("<HHH", f.read(6)))
        wavelengths = np.arange(start_wlen, end_wlen + 1, delta_wlen)
    except Exception:
        return None

    # Extract times and absorbances
    f.seek(data_offsets['data_start'])
    times = []
    absorbances = []
    while True:
        try:
            f.read(4)
            time = uint_unpack(f.read(4))[0]
            times.append(time)
            f.read(14)
            # If the next short is equal to -0x8000
            #     then the next absorbance value is the next integer. 
            # Otherwise, the short is a delta from the last absorbance value.
            absorb_accum = 0
            for _ in range(wavelengths.size):
                check_int = short_unpack(f.read(2))[0]
                if check_int == -0x8000:
                    absorb_accum = int_unpack(f.read(4))[0]
                else:
                    absorb_accum += check_int
                absorbances.append(absorb_accum)
        except Exception:
            break

    times = np.array(times) / 60000
    data = np.array(absorbances).reshape((times.size, wavelengths.size))

    # Scale the absorbances
    f.seek(data_offsets['scaling_factor'])
    scaling_factor = struct.unpack('>d', f.read(8))[0]
    data = data * scaling_factor

    # Read metadata
    metadata_offsets = {
        "notebook": 0x35A,
        "date": 0x957,
        "method": 0xA0E,
        "unit": 0xC15,
        "signal": 0xC40,
        "vialpos": 0xFD7
    }
    metadata = read_header(f, metadata_offsets)

    return DataFile(path, 'UV', times, wavelengths, data, metadata)

# --- Decoders ---

def decode_uv_delta(f, data_offsets, num_times, num_wavelengths):
    uint_unpack = struct.Struct('<I').unpack
    int_unpack = struct.Struct('<i').unpack
    short_unpack = struct.Struct('<h').unpack

    f.seek(data_offsets["data_start"])
    times = np.empty(num_times, dtype=np.uint32)
    data = np.empty((num_times, num_wavelengths), dtype=np.int64)
    for i in range(num_times):
        f.read(4)
        times[i] = uint_unpack(f.read(4))[0]
        f.read(14)
        # If the next short is equal to -0x8000
        #     then the next absorbance value is the next integer.
        # Otherwise, the short is a delta from the last absorbance value.
        absorb_accum = 0
        for j in range(num_wavelengths):
            check_int = short_unpack(f.read(2))[0]
            if check_int == -0x8000:
                absorb_accum = int_unpack(f.read(4))[0]
            else:
                absorb_accum += check_int
            data[i, j] = absorb_accum

    return times, data


def decode_uv_array(f, data_offsets, num_times, num_wavelengths):
    uint_unpack = struct.Struct('<I').unpack

    f.seek(data_offsets["data_start"])
    times = np.empty(num_times, dtype=np.uint32)
    data = np.empty((num_times, num_wavelengths), dtype=np.float64)
    for i in range(num_times):
        f.read(4)
        times[i] = uint_unpack(f.read(4))[0]
        f.read(14)
        for j in range(num_wavelengths):
            data[i, j] = struct.unpack('<d', f.read(8))[0]

    return times, data