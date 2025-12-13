import numpy as np

from rainbow.datafile import DataFile
from rainbow.agilent.fileparsers.common import *


def parse_ms(path, prec=0):
    """
    Parses an Agilent .ms file.

    These files contain MS spectra and SIM. 

    Learn more about this file format :ref:`here <ms>`.

    Args:
        path (str): Path to Agilent .ms file.
        prec (int, optional): Number of decimals to round mz values. 
    
    Returns:
        DataFile with MS data, if the file can be parsed. Otherwise, None.

    """
    data_offsets = {
        'type': 0x4,
        'data_start': 0x10A,
        'lc_num_times': 0x116,
        'gc_num_times': 0x142
    }

    f = open(path, 'rb')
    short_unpack = struct.Struct('>H').unpack
    int_unpack = struct.Struct('>I').unpack

    # Validate file header.
    # If invalid, the file may be a partial.
    head = int_unpack(f.read(4))[0]
    if head != 0x01320000:
        f.close()
        return parse_ms_partial(path, prec)

    # Determine the type of .ms file based on header.
    # Read the number of retention times from different offsets by type.
    type_ms = read_string(f, data_offsets['type'], 1)
    if type_ms == "MSD Spectral File":
        f.seek(data_offsets['lc_num_times'])
        num_times = int_unpack(f.read(4))[0]
    else:
        f.seek(data_offsets['gc_num_times'])
        num_times = struct.unpack('<H', f.read(2))[0]

    # Go to the data start offset.
    f.seek(data_offsets['data_start'])
    f.seek(short_unpack(f.read(2))[0] * 2 - 2)

    # Extract retention times and data pair counts for each time. 
    # Store the bytes holding mz-intensity pairs.
    times = np.empty(num_times, dtype=np.uint32)
    pair_counts = np.zeros(num_times, dtype=np.uint16)
    pair_bytearr = bytearray()
    for i in range(num_times):
        f.read(2)
        times[i] = int_unpack(f.read(4))[0]
        f.read(6)
        pair_counts[i] = short_unpack(f.read(2))[0]
        f.read(4)
        pair_bytes = f.read(pair_counts[i] * 4)
        pair_bytearr.extend(pair_bytes)
        f.read(10)

    # Minor processing on the extracted data.
    raw_bytes = bytes(pair_bytearr)
    times = times / 60000
    total_paircount = np.sum(pair_counts)

    # Calculate the mz values. 
    mzs = np.ndarray(total_paircount, '>H', raw_bytes, 0, 4)
    mzs = np.round(mzs / 20, prec)

    # Calculate the intensity values. 
    int_encs = np.ndarray(total_paircount, '>H', raw_bytes, 2, 4)
    int_heads = int_encs >> 14
    int_tails = int_encs & 0x3fff
    int_values = np.multiply(8 ** int_heads, int_tails, dtype=np.uint32)
    del int_encs, int_heads, int_tails, raw_bytes

    # Make the array of `ylabels` with mz values. 
    ylabels = np.unique(mzs)
    ylabels.sort()

    # Make the `data` array with intensities. 
    mz_indices = np.searchsorted(ylabels, mzs)
    data = np.zeros((num_times, ylabels.size), dtype=np.uint32)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + int(pair_counts[i])
        np.add.at(
            data[i],
            mz_indices[cur_index:stop_index],
            int_values[cur_index:stop_index])
        cur_index = stop_index
    del mz_indices, mzs, int_values, pair_counts

    # Read file metadata.
    metadata_offsets = {
        'date': 0xB2,
        'method': 0xE4
    }
    metadata = read_header(f, metadata_offsets, 1)
    f.close()

    return DataFile(path, 'MS', times, ylabels, data, metadata)


def parse_ms_partial(path, prec=0):
    """
    Parses a partial Agilent .ms file. 

    IMPORTANT: This method only supports LC .ms partials.

    Learn more about this file format :ref:`here <ms>`.

    Args:
        path (str): Path to the partial .ms file.
        prec (int, optional): Number of decimal to round mz values.

    Returns:
        DataFile with MS data, if the file can be parsed. Otherwise, None.

    """
    f = open(path, 'rb')
    short_unpack = struct.Struct('>H').unpack
    int_unpack = struct.Struct('>I').unpack

    # Partial .ms files do not store the start offset.
    # Shallow validation of filetype by checking that offset is null.
    f.seek(0x10A)
    if short_unpack(f.read(2))[0] != 0:
        f.close()
        return None

    # The start offset for data in .ms files is technically variable, 
    #     but it has been constant for every .ms file we have tested. 
    # Since the start offset is not stored in partials, this code uses that
    #     "constant" common starting offset. It may not work in all cases. 
    f.seek(0x2F2)

    # Extract retention times and data pair counts for each time. 
    # Store the bytes holding mz-intensity pairs.
    times = []
    pair_counts = []
    pair_bytearr = bytearray()
    while True:
        try:
            f.read(2)
            time = int_unpack(f.read(4))[0]
            f.read(6)
            pair_count = short_unpack(f.read(2))[0]
            f.read(4)
            pair_bytes = f.read(pair_count * 4)
            f.read(10)
            times.append(time)
            pair_counts.append(pair_count)
            pair_bytearr.extend(pair_bytes)
        except Exception:
            break

    # Minor processing on the extracted data.
    raw_bytes = bytes(pair_bytearr)
    times = np.array(times) / 60000
    pair_counts = np.array(pair_counts)
    num_times = times.size
    total_paircount = np.sum(pair_counts)

    # Calculate the mz values. 
    mzs = np.ndarray(total_paircount, '>H', raw_bytes, 0, 4)
    mzs = np.round(mzs / 20, prec)

    # Calculate the intensity values.
    int_encs = np.ndarray(total_paircount, '>H', raw_bytes, 2, 4)
    int_heads = int_encs >> 14
    int_tails = int_encs & 0x3fff
    int_values = np.multiply(8 ** int_heads, int_tails, dtype=np.uint32)
    del int_encs, int_heads, int_tails, raw_bytes

    # Make the array of `ylabels` with mz values. 
    ylabels = np.unique(mzs)
    ylabels.sort()

    # Fill the `data` array with intensities.
    mz_indices = np.searchsorted(ylabels, mzs)
    data = np.zeros((num_times, ylabels.size), dtype=np.uint32)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + pair_counts[i]
        np.add.at(
            data[i],
            mz_indices[cur_index:stop_index],
            int_values[cur_index:stop_index])
        cur_index = stop_index
    del mz_indices, mzs, int_values, pair_counts

    # Read file metadata. 
    metadata_offsets = {
        'date': 0xB2,
        'method': 0xE4
    }
    metadata = read_header(f, metadata_offsets, 1)
    f.close()

    return DataFile(path, 'MS', times, ylabels, data, metadata)