import numpy as np

from rainbow.datafile import DataFile
from rainbow.agilent.fileparsers.common import *


def parse_uv(path):
    """
    Parses an Agilent .uv file.

    These files contain UV spectra. 

    Learn more about this file format :ref:`here <uv>`.

    Args:
        path (str): Path to the Agilent .uv file. 
    
    Returns:
        DataFile with UV data, if the file can be parsed. Otherwise, None.

    """

    f = open(path, 'rb')
    uint_unpack = struct.Struct('<I').unpack
    int_unpack = struct.Struct('<i').unpack
    short_unpack = struct.Struct('<h').unpack

    # Validate file header.
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
        f.close()
        return None

    # Extract the number of retention times.
    f.seek(data_offsets["num_times"])
    num_times = struct.unpack(">I", f.read(4))[0]
    # If there are none, the file may be a partial. 
    if num_times == 0:
        f.close()
        return parse_uv_partial(path)

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
    f.close()

    return DataFile(path, 'UV', times, wavelengths, data, metadata)


def parse_uv_partial(path):
    """
    Parses a partial Agilent .uv file. 

    Learn more about this file format :ref:`here <uv>`.

    Args:
        path (str): Path to the partial .uv file. 
    
    Returns:
        DataFile with UV data, if the file can be parsed. Otherwise, None.

    """
    data_offsets = {
        'num_times': 0x116,
        'scaling_factor': 0xC0D,
        'data_start': 0x1000
    }

    f = open(path, 'rb')
    uint_unpack = struct.Struct('<I').unpack
    int_unpack = struct.Struct('<i').unpack
    short_unpack = struct.Struct('<h').unpack

    # Compute the wavelengths by taking the range from 
    #     the header of the first data segment.
    # If this process fails, then the file is not a partial. 
    f.seek(data_offsets["data_start"] + 0x8)
    try:
        start_wlen, end_wlen, delta_wlen = \
            tuple(num // 20 for num in struct.unpack("<HHH", f.read(6)))
        wavelengths = np.arange(start_wlen, end_wlen + 1, delta_wlen)
    except Exception:
        return None

    # Extract the retention times and absorbances from each data segment.
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

    # Process the extracted values.
    times = np.array(times) / 60000
    data = np.array(absorbances).reshape((times.size, wavelengths.size))

    # Scale the absorbances. 
    f.seek(data_offsets['scaling_factor'])
    scaling_factor = struct.unpack('>d', f.read(8))[0]
    data = data * scaling_factor

    # Read file metadata.
    metadata_offsets = {
        "notebook": 0x35A,
        "date": 0x957,
        "method": 0xA0E,
        "unit": 0xC15,
        "signal": 0xC40,
        "vialpos": 0xFD7
    }
    metadata = read_header(f, metadata_offsets)
    f.close()

    return DataFile(path, 'UV', times, wavelengths, data, metadata)

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