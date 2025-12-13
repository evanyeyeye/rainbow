import numpy as np

from rainbow.datafile import DataFile
from rainbow.agilent.fileparsers.common import *


def parse_ch(path):
    """
    Parses an Agilent .ch file. 

    These files contain data from a FID, CAD, ELSD, or UV channel. \
    Files that contain FID data have a different format than other .ch files.

    This method calls the appropriate subroutine by file format. 

    Args: 
        path (str): Path to the .ch file.
    
    Returns:
        DataFile with data from a channel, if the file can be parsed. \
            Otherwise, None.

    """
    with open(path, 'rb') as f:
        head = read_string(f, offset=0, gap=1)
        if head in ['179', '181']:
            return parse_ch_fid(path, head)
        elif head in ['130', '30']:
            return parse_ch_other(path, head)
        return None


def parse_ch_fid(path, head):
    """
    Parses an Agilent .ch file with FID channel data. 
    
    This method should not be called directly. Use :obj:`parse_ch` instead. 

    Learn more about this file format :ref:`here <ch_fid>`.

    Args:
        path (str): Path to the .ch file with FID data. 

    Returns:
        DataFile with FID data, if the file can be parsed. Otherwise, None.

    """
    if head == '181':
        data_offsets = {
            'num_times': 0x116,
            'scaling_factor': 0x127C,
            'data_start': 0x1800
        }
        metadata_offsets = {
            'notebook': 0x35A,
            'date': 0x957,
            'method': 0xA0E,
            'instrument': 0xC11,
            'unit': 0x104C,
        }
        gap = 2
    elif head == '179':
        data_offsets = {
            'num_times': 0x116,
            'scaling_factor': 0x127C,
            'data_start': 0x1800
        }
        metadata_offsets = {
            'notebook': 0x35A,
            'date': 0x957,
            'method': 0xA0E,
            'instrument': 0xC11,
            'unit': 0x104C,
            'signal': 0x1075
        }

    f = open(path, 'rb')
    raw_bytes = f.read()
    file_size = f.tell()

    # Extract the number of retention times.
    num_times = (file_size - data_offsets['data_start']) // 8

    f.seek(data_offsets['num_times'] + 4)
    # Compute retention times using the first and last times. 
    start_time = struct.unpack(">f", f.read(4))[0]
    end_time = struct.unpack(">f", f.read(4))[0]
    delta_time = (end_time - start_time) / (num_times - 1)
    times = np.arange(start_time, end_time + 1e-3, delta_time)

    # Extract the raw data values.
    if head == '181':
        data = np.array(decode_double_delta(f, data_offsets['data_start']), dtype=np.float64)
    else:
        data = np.ndarray(num_times, '<d', raw_bytes, data_offsets['data_start'], 8)
    data = data.copy().reshape(-1, 1)

    # Convert times into minutes.
    times /= 60000

    # Scale the absorbances.
    f.seek(data_offsets['scaling_factor'])
    scaling_factor = struct.unpack('>d', f.read(8))[0]
    data *= scaling_factor

    # No ylabel for FID data. 
    ylabels = np.array([''])

    # Extract metadata from file header.
    metadata = read_header(f, metadata_offsets)
    f.close()

    return DataFile(path, 'FID', times, ylabels, data, metadata)


def parse_ch_other(path, head):
    """
    Parses an Agilent .ch file with CAD, ELSD, or UV channel data.
    
    This method should not be called directly. Use :obj:`parse_ch` instead.

    IMPORTANT: ELSD data may be mistakenly labeled as CAD on rare occasions. Users may need to make this distinction on their own when decoding Agilent CAD or ELSD data.

    Learn more about this file format :ref:`here <ch_other>`.

    Args:
        path (str): Path to the .ch file with UV, CAD, or ELSD data. 

    Returns:
        DataFile with CAD, ELSD, or UV data, if parsable. Otherwise, None.

    """
    if head == '130':
        data_offsets = {
            'time_range': 0x11A,
            'scaling_factor': 0x127C,
            'data_start': 0x1800
        }
        metadata_offsets = {
            'notebook': 0x35A,
            'date': 0x957,
            'method': 0xA0E,
            'instrument': 0xC11,
            'unit': 0x104C,
            'signal': 0x1075
        }
        gap = 2
    elif head == '30':
        data_offsets = {
            'time_range': 0x11A,
            'scaling_factor': 0x284,
            'data_start': 0x400
        }
        metadata_offsets = {
            'notebook': 0x18,
            'date': 0xB2,
            'method': 0xE4,
            'instrument': 0xDA,
            'unit': 0x244,
            'signal': 0x254
        }
        gap = 1
    else:
        return None

    f = open(path, 'rb')
    byte_unpack = struct.Struct('>B').unpack
    short_unpack = struct.Struct('>h').unpack
    int_unpack = struct.Struct('>i').unpack

    # Extract the raw data values.
    # Count the total number of retention times.
    # Process the extracted values.
    # If no values are extracted, this file is invalid.
    data = np.array(decode_delta(f, data_offsets['data_start']))
    num_times = data.size
    if num_times == 0:
        return None

    # Calculate retention times using the first and last times.
    f.seek(data_offsets['time_range'])
    start_time, end_time = struct.unpack('>ii', f.read(8))
    delta_time = (end_time - start_time) / (num_times - 1)
    times = np.arange(start_time, end_time + 1e-3, delta_time)

    # Convert time to minutes
    times /= 60000

    # Process the absorbances.
    f.seek(data_offsets['scaling_factor'])
    scaling_factor = struct.unpack('>d', f.read(8))[0]
    data = data.reshape(-1, 1) * scaling_factor

    # Read file metadata.

    metadata = read_header(f, metadata_offsets, gap=gap)
    f.close()

    # Determine the detector and ylabels using metadata. 
    detector = None
    ylabel = ''
    signal = metadata['signal']
    if '=' in signal:
        ylabel = signal.split('=')[1].split(',')[0]
        detector = 'UV'
    elif 'ADC' in signal:
        detector = 'ELSD' if 'CHANNEL' in signal else 'CAD'
    ylabels = np.array([ylabel])

    return DataFile(path, detector, times, ylabels, data, metadata)

def decode_delta(f, offset):
    byte_unpack = struct.Struct('>B').unpack
    short_unpack = struct.Struct('>h').unpack
    int_unpack = struct.Struct('>i').unpack
    # Extract the raw data values.
    # Count the total number of retention times.
    f.seek(offset)
    absorbances = []
    absorb_accum = 0
    while True:
        # If the segment header is invalid, stop reading.
        head = byte_unpack(f.read(1))[0]
        if head != 0x10:
            break
        num_times_seg = byte_unpack(f.read(1))[0]

        # If the next short is equal to -0x8000
        #     then the next absorbance value is the next integer.
        # Otherwise, the short is a delta from the last absorbance value.
        for _ in range(num_times_seg):
            check_int = short_unpack(f.read(2))[0]
            if check_int == -0x8000:
                absorb_accum = int_unpack(f.read(4))[0]
            else:
                absorb_accum += check_int
            absorbances.append(absorb_accum)

    return absorbances

def decode_double_delta(f, offset):
    byte_unpack = struct.Struct('>B').unpack
    short_unpack = struct.Struct('>h').unpack
    int_unpack = struct.Struct('>i').unpack
    f.seek(0, 2)
    file_size = f.tell()
    f.seek(offset)
    signals = []
    count = 1
    buffer = [0, 0, 0]

    while f.tell() < file_size:
        buffer[2] = short_unpack(f.read(2))[0]
        if buffer[2] == 0x7fff:
            buffer[0] = short_unpack(f.read(2))[0] << 32 | int_unpack(f.read(4))[0]
            buffer[1] = 0
        else:
            buffer[1] += buffer[2]
            buffer[0] += buffer[1]
        signals.append(buffer[0])

    return signals