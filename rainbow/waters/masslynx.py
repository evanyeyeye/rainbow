import os
import re
import struct
import numpy as np
from rainbow.datafile import DataFile


"""
SPECTRUM PARSING METHODS

"""
def parse_spectrum(path, prec=0):
    """
    Finds and parses Waters UV and MS spectra.

    Args:
        path (str): Path to the Waters .raw directory. 
        prec (int, optional): Number of decimals to round ylabels. 
    
    Returns:
        List containing a DataFile for each parsed spectrum.  

    """
    datafiles = []

    # There is MS spectrum data if and only if there is an _extern.inf file.
    # The file stores information about each MS spectrum, like polarity.
    # Future work may find useful metadata there. 
    polarities = []
    calib_nums = []
    if '_extern.inf' in os.listdir(path):
        # Parse MS polarities from _extern.inf. 
        f = open(os.path.join(path, '_extern.inf'), 'rb')
        lines = f.read().decode('ascii', 'ignore').splitlines()
        f.close()
        for i in range(len(lines)):
            if not lines[i].startswith("Instrument Parameters"):
                continue
            if lines[i + 1].startswith("Polarity"):
                polarity = lines[i + 1].split('\t\t\t')[1][-1]
            else:
                try:
                    polarity = lines[i + 2].split('\t')[1][-1]
                except:
                    raise Exception("Waters HRMS data is not supported.")
            polarities.append(polarity)

        # Parse mz calibration values from _HEADER.txt. 
        # There are a separate list of values for each MS spectrum. 
        f = open(os.path.join(path, '_HEADER.TXT'), 'r')
        lines = f.read().splitlines()
        f.close()
        for line in lines:
            if not line.startswith("$$ Cal Function"):
                continue
            calib_nums.append(
                [float(num) for num in line.split(': ')[1].split(',')[:-1]])

    # The raw spectrum data is stored in _FUNC .DAT files. 
    # Each MS spectrum has an assigned polarity, 
    #     but may not have calibration values. 
    funcdat_paths = sorted([os.path.join(path, fn) for fn in os.listdir(path)
                            if re.match('^_FUNC[0-9]{3}.DAT$', fn)])
    funcdat_index = 0
    while funcdat_index < len(funcdat_paths):
        polarity = None
        calib = None
        if funcdat_index < len(polarities):
            polarity = polarities[funcdat_index]
            if funcdat_index < len(calib_nums):
                calib = calib_nums[funcdat_index]
        datafile = parse_func(
            funcdat_paths[funcdat_index], prec, polarity, calib)
        datafiles.append(datafile)
        funcdat_index += 1

    return datafiles

def parse_func(path, prec=0, polarity=None, calib=None):
    """ 
    """
    idx_path = path[:-3] + 'IDX'
    times, ylabels_per_time, data_len = parse_funcidx(idx_path)
    if data_len not in {2, 6, 8}:
        print(path, data_len, times)
    assert(data_len == 6 or data_len == 8 or data_len == 2)

    if polarity is None and data_len != 6:
        print(data_len)

    if data_len == 2:
        inf = parse_funcinf(os.path.join(os.path.dirname(path), '_FUNCTNS.INF'))
        ylabels, data = parse_funcdat2(path, ylabels_per_time, inf, prec, calib)
    elif data_len == 6:
        ylabels, data = parse_funcdat6(path, ylabels_per_time, prec, calib)
    elif data_len == 8:
        ylabels, data = parse_funcdat8(path, ylabels_per_time, prec, calib) 
    
    # Spectra without an assigned polarity contain UV data. 
    detector = 'MS' if polarity else 'UV'

    metadata = {}
    if polarity:
        metadata['polarity'] = polarity

    return DataFile(path, detector, times, ylabels, data, metadata)

def parse_funcinf(path):
    """ 
    """
    f = open(path, 'rb')
    while True:
        try:
            packed = struct.unpack('<H', f.read(2))[0]
            func = packed & 0x1F 
            form = packed >> 10
            f.read(16)
            num_scans = struct.unpack('<I', f.read(4))[0]
            f.read(10)
            f.read(32 * 4)
            q1 = np.ndarray(32, '<f', f.read(32 * 4))
            q3 = np.ndarray(32, '<f', f.read(34 * 4))
        except:
            break 
    assert(f.tell() == os.path.getsize(path))
    f.close()
    return (num_scans, func, q1, q3)

def parse_funcidx(path):
    """ 
    """
    f = open(path, 'rb')
    size = os.path.getsize(path)
    num_times = size // 22 
    assert(os.path.getsize(path) // 22 == os.path.getsize(path) / 22)
    times = np.empty(num_times, dtype=np.float32)
    ylabels_per_time = np.empty(num_times, dtype=np.uint32)
    int_unpack = struct.Struct('<I').unpack
    for i in range(num_times):
        offset = int_unpack(f.read(4))[0]
        info = struct.unpack('<I', f.read(4))[0]
        ylabels_per_time[i] = info & 0x3FFFFF
        if ylabels_per_time[i] != 0:
            last_offset = offset
            last_index = i
        calibrated_flag = (info & 0x40000000) >> 30
        assert(calibrated_flag == 0)
        f.read(4) # tic
        times[i] = struct.unpack('<f', f.read(4))[0]
        f.read(6)
    assert(f.tell() == os.path.getsize(f.name))
    f.close() 
    data_len = (os.path.getsize(path[:-3] + 'DAT') - last_offset) // ylabels_per_time[last_index]

    return times, ylabels_per_time, data_len

def parse_funcdat2(path, ylabels_per_time, inf, prec=0, calib=None):
    num_times, func, q1, q3 = inf
    num_datapairs = np.sum(ylabels_per_time)
    assert(np.all(ylabels_per_time == ylabels_per_time[0]))
    assert(os.path.getsize(path) == num_datapairs * 2)
    with open(path, 'rb') as f:
        raw_bytes = f.read()
    raw_values = np.ndarray(num_datapairs, '<H', raw_bytes)
    val_base = raw_values >> 3
    val_pow = raw_values & 0x7
    values = np.multiply(val_base, 4 ** val_pow, dtype=np.uint32)
    assert(func == 1)
    ylabels = q1[:ylabels_per_time[0]]
    data = np.empty((ylabels_per_time.size, ylabels_per_time[0]), dtype=np.uint32)
    index = 0
    for i in range(ylabels_per_time.size):
        for j in range(ylabels_per_time[0]):
            data[i][j] = values[index]
            index += 1

    return ylabels, data

def parse_funcdat6(path, ylabels_per_time, prec=0, calib=None):
    """
    """
    num_times = ylabels_per_time.size
    num_datapairs = np.sum(ylabels_per_time)
    assert(os.path.getsize(path) == num_datapairs * 6)

    # Optimized reading of 6-byte segments into `raw_values`. 
    with open(path, 'rb') as f:
        raw_bytes = f.read()
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
    keys = np.round(keys, prec)

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

def parse_funcdat8(path, ylabels_per_time, prec=0, calib=None):
    """
    """
    num_times = ylabels_per_time.size
    num_datapairs = np.sum(ylabels_per_time)
    assert(os.path.getsize(path) == num_datapairs * 8)

    # Optimized reading of 8-byte segments into `raw_values`. 
    with open(path, 'rb') as f:
        raw_bytes = f.read()
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
    keys = np.round(keys, prec)

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
    for coeff in calib_nums:
        calib_masses += coeff * var
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


"""
ANALOG PARSING METHODS

"""
def parse_analog(path):
    """
    Finds and parses analog data from a Waters .raw directory.

    Args:
        path (str): Path to the Waters .raw directory. 
    
    Returns:
        List of DataFiles that contain analog data. 

    """
    datafiles = []

    if '_CHROMS.INF' not in os.listdir(path):
        return datafiles 

    analog_info = parse_chroinf(os.path.join(path, '_CHROMS.INF'))
    for i in range(len(analog_info)):
        fn = os.path.join(path, f"_CHRO{i+1:0>3}.DAT")
        datafile = parse_chrodat(fn, *analog_info[i])
        if datafile:
            datafiles.append(datafile)
    return datafiles

def parse_chroinf(path):
    """
    Parses a Waters _CHROMS.INF file.

    Retrieves the name and unit for each analog data file. 

    Args:
        path (str): Path to the _CHROMS.INF file. 
    
    Returns:
        List of string lists that contain the name of each analog file. \
            The inner lists also includes the unit, if it exists. 

    """
    f = open(path, 'r')
    f.seek(0x84) # start offset 
    analog_info = []
    while f.tell() < os.path.getsize(path):
        line = re.sub('[\0-\x04]|\$CC\$|\([0-9]*\)', '', f.read(0x55)).strip()
        split = line.split(',')
        info = []
        info.append(split[0]) # name
        if len(split) == 6:
            info.append(split[5]) # unit
        analog_info.append(info)
    f.close()
    return analog_info

def parse_chrodat(path, name, units=None):
    """
    Parses a Waters _CHRO .DAT file.

    These files may contain data for CAD, ELSD, or UV channels. \
        They may also contain other miscellaneous data like system pressure.
    
    IMPORTANT: MassLynx classifies all of these files as "analog" data, but \
        a DataDirectory will not treat CAD, ELSD, or UV channels as analog \
        data. Instead, those channels will be mapped to their detector.

    Args:
        path (str): Path to the _CHRO .DAT file. 
        name (str): Name of the analog data.
        units (str, optional): Units of the analog data.
    
    Returns:
        DataFile containing the analog data, if it exists. 

    """
    data_start = 0x80

    num_times = (os.path.getsize(path) - data_start) // 8
    if num_times == 0:
        return None

    with open(path, 'rb') as f:
        raw_bytes = f.read()
    times_immut = np.ndarray(num_times, '<f', raw_bytes, data_start, 8)
    vals_immut = np.ndarray(num_times, '<f', raw_bytes, data_start+4, 8)

    # The arrays are copied so that they are mutable. 
    # This is just for user convenience. 
    times = times_immut.copy()
    vals = vals_immut.copy().reshape(-1, 1)
    del times_immut, vals_immut, raw_bytes

    # A `detector` value of None corresponds to miscellaneous analog data.
    detector = None
    if "CAD" in name:
        detector = 'CAD'
    elif "ELSD" in name:
        detector = 'ELSD'
    elif "nm@" in name:
        detector = 'UV'

    ylabels = np.array([''])
    metadata = {'signal': name}
    if units: 
        metadata['unit'] = units 

    return DataFile(path, detector, times, ylabels, vals, metadata)


""" 
METADATA PARSING METHOD

"""

def parse_metadata(path):
    """
    Parses metadata from a Waters .raw directory.

    Specifically, the date and vial position are extracted from _HEADER.txt.

    Args:
        path (str): Path to the directory. 
    
    Returns:
        Dictionary containing directory metadata. 

    """
    metadata = {}
    metadata['vendor'] = "Waters"

    f = open(os.path.join(path, '_HEADER.TXT'), 'r')
    lines = f.read().splitlines()
    f.close()
    for line in lines:
        if line.startswith("$$ Acquired Date"):
            value = line.split(': ')[1]
            if not value.isspace():
                metadata['date'] = value + " "
        elif line.startswith("$$ Acquired Time"):
            # assert('date' in metadata)
            value = line.split(': ')[1]
            if not value.isspace():
                metadata['date'] += value
        elif line.startswith("$$ Bottle Number"):
            value = line.split(': ')[1]
            if not value.isspace():
                metadata['vialpos'] = value
    return metadata 