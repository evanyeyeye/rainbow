import os
import re
import struct
import numpy as np
from rainbow.datafile import DataFile
from decimal import Decimal, ROUND_HALF_UP

"""
ANALOG PARSING METHODS

"""

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
    f.close()
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

    f.close()

    return DataFile(path, detector, xlabels, ylabels, data, metadata)


"""
SPECTRUM PARSING METHODS

"""

def parse_spectrum(path):
    """
    """
    datafiles = []

    func_paths = sorted([os.path.join(path, fn) for fn in os.listdir(path) 
                         if re.match('^_FUNC[0-9]{3}.DAT$', fn)])
    func_i = 0
    if '_extern.inf' in os.listdir(path):

        f = open(os.path.join(path, '_HEADER.TXT'), 'r')
        lines = f.read().splitlines()
        calibs = []
        for line in lines:
            if line.startswith("$$ Cal Function"):
                calib = [float(s) for s in line.split(': ')[1].split(',')[:-1]]
                assert(len(calib) == 5)
                calibs.append(calib)
        f.close()

        f = open(os.path.join(path, '_extern.inf'), 'rb')
        lines = f.read().splitlines()
        polarities = []
        nums = []
        for i in range(len(lines)):
            if lines[i].startswith(b"Instrument Parameters"):
                assert(len(lines[i].split(b" ")) == 5)
                nums.append(int(lines[i].split(b" ")[4][:-1]))
                assert(lines[i+1].startswith(b"Polarity") or lines[i+2].startswith(b"Polarity"))
                if lines[i+1].startswith(b"Polarity"):
                    assert(len(lines[i+1].split(b'\t\t\t')) == 2)
                    polarity = chr(lines[i+1].split(b'\t\t\t')[1][-1])
                else:
                    assert(len(lines[i+2].split(b'\t')) == 2)
                    polarity = chr(lines[i+2].split(b'\t')[1][-1])
                polarities.append(polarity)
        assert(nums[0] == 1 and nums[-1] == len(nums))
        assert(nums == sorted(nums))
        f.close()

        assert(len(calibs) == len(polarities))
        
        while func_i < len(calibs):
            datafiles.append(parse_func(func_paths[func_i], calibs[func_i],
                                        polarities[func_i]))
            func_i += 1

    while func_i < len(func_paths):
        datafiles.append(parse_func(func_paths[func_i], None, None))
        func_i += 1

    return datafiles

def parse_func(path, calib, polarity):
    idx_path = path[:-3] + 'IDX'
    times, ylabels_per_time, last_offset = parse_funcidx(idx_path)
    data_len = (os.path.getsize(path) - last_offset) // ylabels_per_time[-1]
    assert(data_len == 6 or data_len == 8)
    if data_len == 6:
        ylabels, data_array = parse_funcdat6(path, ylabels_per_time, calib)
    else:
        return None
        # ylabels, data = parse_funcdat8(path, ylabels_per_time, calib)
    
    detector = 'MS' if calib else 'UV'

    metadata = {}
    if polarity:
        metadata['polarity'] = polarity

    return DataFile(path, detector, times, ylabels, data_array, metadata)

def parse_funcidx(path):
    f = open(path, 'rb')
    num_times = os.path.getsize(path) // 22 
    assert(os.path.getsize(path) // 22 == os.path.getsize(path) / 22)
    times = np.empty(num_times, dtype=np.float32)
    ylabels_per_time = np.empty(num_times, dtype=np.uint32)
    for i in range(num_times):
        offset_bytes = f.read(4)
        if i == num_times - 1:
            last_offset = struct.unpack('<I', offset_bytes)[0]
        info = struct.unpack('<I', f.read(4))[0]
        ylabels_per_time[i] = info & 0x3FFFFF 
        calibrated_flag = (info & 0x40000000) >> 30
        assert(calibrated_flag == 0)
        f.read(4) # tic
        times[i] = struct.unpack('<f', f.read(4))[0]
        f.read(6)
    assert(f.tell() == os.path.getsize(f.name))

    return times, ylabels_per_time, last_offset

def unpack48(x):
    x1, x2, x3 = struct.unpack('<HHI', x)
    return x1, x2 | (x3 << 16)

# def parse_funcdat6(path, ylabels_per_time, calib):
#     f = open(path, 'rb')
#     num_times = ylabels_per_time.size
#     memo = np.empty(num_times, dtype=object)
#     ylabels_set = set()

#     total_ylabels = np.sum(ylabels_per_time)
#     raw_bytes = np.array([struct.unpack("<Q", f.read(6) + b"\x00\x00")[0] for _ in range(total_ylabels)], dtype=np.int64)
#     base_ylabels = (raw_bytes & 0xFFFFFE000000) >> 25
#     pow_ylabels = ((raw_bytes & 0x1F00000) >> 20) - 23
#     ylabels = base_ylabels * (np.power(2.0, pow_ylabels))
#     if calib:
#         ylabels = calibrate(ylabels, calib)
#     rounded = [int(Decimal(float(ylabel)).quantize(Decimal(1), ROUND_HALF_UP)) for ylabel in ylabels]
        
#     ylabels_set.update(rounded)
#     ylabels_list = np.array(sorted(ylabels_set))
#     ylabel_indices = dict(zip(ylabels_list, range(ylabels_list.size)))

#     base_datavals = (raw_bytes & 0xFFFF).astype(np.int16)
#     pow_datavals = (raw_bytes & 0xF0000) >> 16
#     datavals = base_datavals * (4 ** pow_datavals)

#     index = 0
#     data_array = np.zeros((num_times, ylabels_list.size), dtype=np.int64)
#     for i in range(num_times):
#         num_ylabels = ylabels_per_time[i]
#         visited = set()
#         for j in range(num_ylabels):
#             ylabel = rounded[index]
#             dataval = datavals[index]
#             if ylabel in visited:
#                 data_array[i, ylabel_indices[ylabel]] += dataval 
#             else: 
#                 data_array[i, ylabel_indices[ylabel]] = dataval
#                 visited.add(ylabel)
#             index += 1

#     return ylabels_list, data_array

# def parse_funcdat6(path, ylabels_per_time, calib):
#     f = open(path, 'rb')
#     num_times = ylabels_per_time.size
#     memo = np.empty(num_times, dtype=object)
#     ylabels_set = set()

#     total_ylabels = np.sum(ylabels_per_time)
#     raw_bytes = np.array([struct.unpack("<Q", f.read(6) + b"\x00\x00")[0] for _ in range(total_ylabels)], dtype=np.int64)
#     base_ylabels = (raw_bytes & 0xFFFFFE000000) >> 25
#     pow_ylabels = ((raw_bytes & 0x1F00000) >> 20) - 23
#     ylabels = base_ylabels * (np.power(2.0, pow_ylabels))
#     if calib:
#         ylabels = calibrate(ylabels, calib)
#     rounded = [int(Decimal(float(ylabel)).quantize(Decimal(1), ROUND_HALF_UP)) for ylabel in ylabels]
        
#     ylabels_set.update(rounded)
#     ylabels_list = np.array(sorted(ylabels_set))
#     ylabel_indices = dict(zip(ylabels_list, range(ylabels_list.size)))

#     base_datavals = (raw_bytes & 0xFFFF).astype(np.int16)
#     pow_datavals = (raw_bytes & 0xF0000) >> 16
#     datavals = base_datavals * (4 ** pow_datavals)

#     index = 0
#     data_array = np.zeros((num_times, ylabels_list.size), dtype=np.int64)
#     for i in range(num_times):
#         num_ylabels = ylabels_per_time[i]
#         visited = set()
#         for j in range(num_ylabels):
#             ylabel = rounded[index]
#             dataval = datavals[index]
#             if ylabel in visited:
#                 data_array[i, ylabel_indices[ylabel]] += dataval 
#             else: 
#                 data_array[i, ylabel_indices[ylabel]] = dataval
#                 visited.add(ylabel)
#             index += 1

#     return ylabels_list, data_array

def parse_funcdat6(path, ylabels_per_time, calib):
    f = open(path, 'rb')
    num_times = ylabels_per_time.size
    memo = np.empty(num_times, dtype=object)
    ylabels_set = set()

    for i in range(num_times):
        num_ylabels = ylabels_per_time[i]
        raw_bytes = np.empty(num_ylabels, dtype=np.int64)
        for j in range(num_ylabels):
            raw_bytes[j] = struct.unpack("<Q", f.read(6) + b"\x00\x00")[0]
        base_ylabels = (raw_bytes & 0xFFFFFE000000) >> 25
        pow_ylabels = ((raw_bytes & 0x1F00000) >> 20) - 23
        ylabels = base_ylabels * (2 ** pow_ylabels.astype(np.double))
        # print(base_ylabels, pow_ylabels, ylabels)
        if calib:
            ylabels = calibrate(ylabels, calib)
        rounded = [int(Decimal(float(ylabel)).quantize(Decimal(1), ROUND_HALF_UP)) for ylabel in ylabels]
        
        ylabels = np.array(rounded)
        ylabels_set.update(rounded)

        base_datavals = (raw_bytes & 0xFFFF).astype(np.int16)
        pow_datavals = (raw_bytes & 0xF0000) >> 16
        datavals = base_datavals * (4 ** pow_datavals)

        memo[i] = (ylabels, datavals)

    ylabels_list = np.array(sorted(ylabels_set))
    ylabel_indices = dict(zip(ylabels_list, range(ylabels_list.size)))

    data_array = np.zeros((num_times, ylabels_list.size), dtype=np.int64)
    for i in range(num_times):
        ylabels, datavals = memo[i]
        visited = set()
        for j in range(ylabels.size):
            ylabel = ylabels[j]
            if ylabel in visited:
                data_array[i, ylabel_indices[ylabel]] += datavals[j]
            else:
                data_array[i, ylabel_indices[ylabel]] = datavals[j]
                visited.add(ylabel)

    return ylabels_list, data_array

# def parse_funcdat6(path, ylabels_per_time, calib):
#     f = open(path, 'rb')
#     num_times = ylabels_per_time.size
#     memo = np.empty(num_times, dtype=object)
#     ylabels_set = set()
#     for i in range(num_times):
#         num_ylabels = ylabels_per_time[i]
#         memo[i] = np.empty(num_ylabels, dtype=object)
#         for j in range(num_ylabels):
#             raw_bytes = struct.unpack("<Q", f.read(6) + b"\x00\x00")[0]
            
#             base_ylabel = (raw_bytes & 0xFFFFFE000000) >> 25
#             pow_ylabel = ((raw_bytes & 0x1F00000) >> 20) - 23
#             ylabel = base_ylabel * (2 ** pow_ylabel)
#             if calib:
#                 ylabel = calibrate(ylabel, calib)
#             ylabel = int(Decimal(ylabel).quantize(Decimal(1), ROUND_HALF_UP))
#             ylabels_set.add(ylabel)

#             base_dataval = struct.unpack(
#                 '<h', struct.pack('<H', raw_bytes & 0xFFFF))[0]
#             pow_dataval = (raw_bytes & 0xF0000) >> 16
#             dataval = base_dataval * (4 ** pow_dataval)

#             memo[i][j] = (ylabel, dataval)


    # ylabels = np.array(sorted(ylabels_set))
    # ylabel_indices = dict(zip(ylabels, range(ylabels.size)))

    # data_array = np.zeros((num_times, ylabels.size), dtype=np.int64)
    # for i in range(num_times):
    #     visited = set()
    #     for j in range(memo[i].size):
    #         ylabel, dataval = memo[i][j]
    #         if ylabel in visited:
    #             data_array[i, ylabel_indices[ylabel]] += dataval
    #         else:
    #             data_array[i, ylabel_indices[ylabel]] = dataval
    #             visited.add(ylabel)

    # return ylabels, data_array

def parse_funcdat8(path, ylabels_per_time, calib):
    pass

def calibrate(masses, calib_nums):
    calib_masses = np.zeros(masses.size)
    var = np.ones(masses.size, dtype=float)
    for cof in calib_nums:
        calib_masses += cof * var
        var *= masses
    return calib_masses

# def calibrate(mass, calib_nums):
#     calib_mass = 0.0
#     var = 1.0
#     for cof in calib_nums:
#         calib_mass += cof * var
#         var *= mass
#     return calib_mass