import os
import struct
import re
from collections import deque
import numpy as np
from rainbow.datafile import DataFile

def parse_analog(path):
    """
    """
    datafiles = []

    dir_contents = os.listdir(path)
    if not '_CHROMS.INF' in dir_contents:
        return datafiles 

    analog_info = parse_chroinf(os.path.join(path, '_CHROMS.INF'))
    analog_paths = [fn for fn in os.listdir(path) if fn.startswith('_CHRO') and fn.endswith('.DAT')]
    assert(len(analog_info) == len(analog_paths))  
    for i in range(len(analog_info)):
        fn = os.path.join(path, f"_CHRO{i+1:0>3}.DAT")
        datafiles.append(parse_chrodat(fn, *analog_info[i]))

    return datafiles

def parse_chroinf(path):
    """
    """
    f = open(path, 'r')
    f.seek(0x84)

    analog_info = []
    end = os.path.getsize(path)
    while f.tell() < end:
        line = re.sub('[\0-\x04]|\$CC\$|\([0-9]*\)', '', f.read(0x55)).strip()
        line_split = line.split(',')
        assert(len(line_split) == 6)
        name = line_split[0]
        units = line_split[5]
        analog_info.append((name, units))
    return analog_info

def parse_chrodat(path, name, units):
    """
    """
    data_start = 0x80

    f = open(path, 'rb')
    f.seek(data_start)

    num_times = (os.path.getsize(path) - data_start) // 8
    times = np.empty(num_times, dtype=float)
    vals = np.empty((num_times, 1), dtype=float)

    for i in range(num_times):
        times[i] = struct.unpack('<f', f.read(4))[0]
        vals[i][0] = struct.unpack('<f', f.read(4))[0]
    assert(f.tell() == os.path.getsize(path))

    detector = None
    name_split = set(name.split(' '))
    if "CAD" in name_split:
        detector = 'CAD'
    elif "ELSD" in name_split:
        detector = 'ELSD'

    xlabels = times 
    ylabels = np.array([''])
    data = vals
    metadata = {
        'description': name,
        'units': units
    }

    return DataFile(path, detector, xlabels, ylabels, data, metadata)



