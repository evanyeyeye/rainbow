import os
import re
import struct
import numpy as np
from rainbow.datafile import DataFile


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
        assert(len(line_split) == 6 or len(line_split) == 1)
        info = []
        info.append(line_split[0])
        if len(line_split) == 6:
            info.append(line_split[5])
        analog_info.append(info)
    f.close()
    return analog_info

def parse_chrodat(path, name, units=None):
    """
    """
    data_start = 0x80
    num_times = (os.path.getsize(path) - data_start) // 8
    assert(data_start + num_times * 8 == os.path.getsize(path))

    raw_bytes = open(path, 'rb').read()
    times_immut = np.ndarray(num_times, '<f', raw_bytes, data_start, 4)
    vals_immut = np.ndarray(num_times, '<f', raw_bytes, data_start+4, 4)
    times = times_immut.copy()
    vals = vals_immut.copy().reshape(-1, 1)
    del times_immut, vals_immut, raw_bytes

    detector = None
    name_split = set(name.split(' '))
    if "CAD" in name_split:
        detector = 'CAD'
    elif "ELSD" in name_split:
        detector = 'ELSD'

    ylabels = np.array([''])
    metadata = {
        'description': name,
    }
    if units: 
        metadata['units'] = units 

    return DataFile(path, detector, times, ylabels, vals, metadata)


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
        
        while func_i < len(polarities):
            if func_i < len(calibs):
                calib = calibs[func_i]
            else: 
                calib = None
            datafiles.append(parse_func(func_paths[func_i], 
                                        polarities[func_i], calib))
            func_i += 1

    while func_i < len(func_paths):
        datafiles.append(parse_func(func_paths[func_i], None, None))
        func_i += 1

    return datafiles

def parse_func(path, polarity, calib):
    """ 
    """
    idx_path = path[:-3] + 'IDX'
    times, ylabels_per_time, last_offset = parse_funcidx(idx_path)
    data_len = (os.path.getsize(path) - last_offset) // ylabels_per_time[-1]
    assert(data_len == 6 or data_len == 8)
    
    parser = parse_funcdat6 if data_len == 6 else parse_funcdat8 
    ylabels, data = parser(path, ylabels_per_time, calib)
    
    detector = 'MS' if calib else 'UV'

    metadata = {}
    if polarity:
        metadata['polarity'] = polarity

    return DataFile(path, detector, times, ylabels, data, metadata)

def parse_funcidx(path):
    """ 
    """
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

def parse_funcdat6(path, ylabels_per_time, calib):
    """
    """
    num_times = ylabels_per_time.size
    num_datapairs = np.sum(ylabels_per_time)
    assert(os.path.getsize(path) == num_datapairs * 6)

    # Optimized reading of 6-byte segments into `raw_values`. 
    raw_bytes = open(path, 'rb').read()
    leastsig = np.ndarray(num_datapairs, '<I', raw_bytes, 0, 6)
    mostsig = np.ndarray(num_datapairs, '<H', raw_bytes, 4, 6)
    raw_values = leastsig | (mostsig.astype(np.int64) << 32)
    del leastsig, mostsig, raw_bytes

    # The data is stored as key-value pairs. 
    # For example, in MS data these are mz-intensity pairs. 
    # Calculate the `keys` from each 6-byte segment. 
    key_bases = (raw_values & 0xFFFFFE000000) >> 25
    key_powers = (raw_values & 0x1F00000) >> 20
    key_powers -= 23
    keys = key_bases * (2.0 ** key_powers)
    del key_bases, key_powers

    # If it is MS data, calibrate the masses. 
    if calib:
        keys = calibrate(keys, calib)
    
    # Then round the keys to the nearest whole number. 
    keys = np.round(keys)

    # Calculate the `values` from each 6-byte segment.
    val_bases = (raw_values & 0xFFFF).astype(np.int16)
    val_powers = (raw_values & 0xF0000) >> 16
    values = val_bases * (4 ** val_powers)
    del val_bases, val_powers, raw_values

    # Make the array of `ylabels` containing keys. 
    ylabels = np.unique(keys)
    ylabels.sort()

    # Fill the `data` array containing values. 
    # Optimized using numpy vectorization.
    key_indices = np.searchsorted(ylabels, keys)
    data = np.zeros((num_times, ylabels.size), dtype=np.int64)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + ylabels_per_time[i]
        np.add.at(
            data[i], 
            key_indices[cur_index:stop_index], 
            values[cur_index:stop_index])
        cur_index = stop_index
    del key_indices, keys, values, ylabels_per_time

    return ylabels, data

def parse_funcdat8(path, ylabels_per_time, calib):
    """
    """
    num_times = ylabels_per_time.size
    num_datapairs = np.sum(ylabels_per_time)
    assert(os.path.getsize(path) == num_datapairs * 8)

    # Optimized reading of 8-byte segments into `raw_values`. 
    raw_bytes = open(path, 'rb').read()
    raw_values = np.ndarray(num_datapairs, '<Q', raw_bytes, 0, 8)

    # The data is stored as key-value pairs. 
    # For example, in MS data these are mz-intensity pairs. 
    # Split each segment into `key_bits` and `val_bits`.
    key_bits = raw_values >> 28 
    val_bits = raw_values & 0xFFFFFFF
    del raw_values, raw_bytes

    # Split `key_bits` into integer and fractional components.
    num_keyint_bits = key_bits >> 31  
    keyint_masks = pow(2, num_keyint_bits) - 1
    num_keyfrac_bits = 31 - num_keyint_bits 
    keyfrac_masks = pow(2, num_keyfrac_bits) - 1
    keyints = (key_bits >> num_keyfrac_bits) & keyint_masks 
    keyfracs = calc_frac(key_bits & keyfrac_masks, num_keyfrac_bits)
    del num_keyint_bits, num_keyfrac_bits, key_bits 
    del keyint_masks, keyfrac_masks

    # Get the `keys` by adding the components. 
    # If it is MS data, calibrate the masses. 
    keys = keyints + keyfracs
    if calib:
        keys = calibrate(keys, calib)
    del keyints, keyfracs 

    # Round the keys to the nearest whole number. 
    keys = np.round(keys)

    # Find the integers that need to be scaled via left shift. 
    # This is based on the number of bits allocated for each integer.
    num_valint_bits = val_bits >> 22
    num_shifted = np.zeros(num_datapairs, np.uint8)
    shift_cond = num_valint_bits > 21 
    num_shifted[shift_cond] = num_valint_bits[shift_cond] - 21 
    num_valint_bits[shift_cond] = 21 
    del shift_cond

    # Split `val_bits` into integer and fractional components.
    valint_masks = pow(2, num_valint_bits) - 1
    num_valfrac_bits = 21 - num_valint_bits 
    valfrac_masks = pow(2, num_valfrac_bits) - 1
    valints = ((val_bits >> num_valfrac_bits) & valint_masks) << num_shifted
    valfracs = calc_frac(val_bits & valfrac_masks, num_valfrac_bits)
    del num_shifted, num_valint_bits, num_valfrac_bits
    del valint_masks, valfrac_masks

    # Get the `values` by adding the components. 
    values = valints + valfracs
    del valints, valfracs
   
    # Make the array of `ylabels` containing keys. 
    ylabels = np.unique(keys)
    ylabels.sort()

    # Fill the `data` array containing values. 
    # Optimized using numpy vectorization.
    key_indices = np.searchsorted(ylabels, keys)
    data = np.zeros((num_times, ylabels.size), dtype=np.int64)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + ylabels_per_time[i]
        np.add.at(
            data[i], 
            key_indices[cur_index:stop_index], 
            values[cur_index:stop_index])
        cur_index = stop_index
    del key_indices, keys, values, ylabels_per_time

    return ylabels, data

def calibrate(masses, calib_nums):
    """ 
    """
    calib_masses = np.zeros(masses.size, dtype=np.float32)
    var = np.ones(masses.size, dtype=np.float32)
    for cof in calib_nums:
        calib_masses += cof * var
        var *= masses
    del var 
    return calib_masses

def calc_frac(keyfrac_bits, num_bits):
    """ 
    """
    exponent = np.uint64(0x3FF << 52) 
    num_shifted = 52 - num_bits
    base = keyfrac_bits << num_shifted
    fracs = (exponent | base).view(np.float64)
    fracs -= 1.0
    del num_shifted, base
    return fracs