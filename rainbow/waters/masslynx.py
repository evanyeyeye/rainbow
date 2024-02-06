""" 
Methods for parsing Waters Masslynx files. 
 
"""
import os
import re
import numpy as np
from rainbow.datafile import DataFile

"""
SPECTRUM PARSING METHODS

"""


def parse_spectrum(path, prec=0, requested_files=None):
    """
    Finds and parses Waters UV and MS spectra from a .raw directory.

    IMPORTANT: The HRMS data format is not supported. \
        It can be differentiated from low resolution MS data using the \
        _extern.inf or _FUNC .IDX files. 

    Args:
        path (str): Path to the .raw directory. 
        prec (int, optional): Number of decimals to round ylabels.
        requested_files (list, optional): List of filenames to parse.
    
    Returns:
        List with a DataFile for each parsed spectrum.  

    """
    datafiles = []

    # There is MS spectrum data if and only if there is an _extern.inf file.
    # The file stores information about each MS spectrum, like polarity.
    # Future work may find useful metadata there. 
    polarities = []
    calib_nums = []
    if '_extern.inf' in os.listdir(path):
        # Parse MS polarities from _extern.inf. 
        with open(os.path.join(path, '_extern.inf'), 'rb') as f:
            lines = f.read().decode('ascii', 'ignore').splitlines()
        for i in range(len(lines)):
            if not lines[i].startswith("Instrument Parameters"):
                continue
            if lines[i + 1].startswith("Polarity"):
                polarity = lines[i + 1].split('\t\t\t')[1][-1]
            else:
                try:
                    polarity = lines[i + 2].split('\t')[1][-1]
                except Exception:
                    raise Exception("Waters HRMS data is not supported.")
            polarities.append(polarity)

        # Parse mz calibration values from _HEADER.txt. 
        # There are a separate list of values for each MS spectrum. 
        with open(os.path.join(path, '_HEADER.TXT'), 'r') as f:
            lines = f.read().splitlines()
        for line in lines:
            if not line.startswith("$$ Cal Function"):
                continue
            calib_nums.append(
                [float(num) for num in line.split(': ')[1].split(',')[:-1]])

    # The raw spectrum data is stored in _FUNC .DAT files. 
    # Each MS spectrum has an assigned polarity, 
    #     but may not have calibration values.
    funcdat_files = sorted(fn for fn in os.listdir(path) if re.match(r'^_FUNC\d{3}.DAT$', fn))
    assert (os.path.getsize(os.path.join(path, "_FUNCTNS.INF")) == 32 * 13 * len(funcdat_files))
    for funcdat_index, funcdat_file in enumerate(funcdat_files):
        if requested_files and funcdat_file.lower() not in requested_files:
            continue
        polarity = None
        calib = None
        if funcdat_index < len(polarities):
            polarity = polarities[funcdat_index]
            if funcdat_index < len(calib_nums):
                calib = calib_nums[funcdat_index]
        datafile = parse_function(os.path.join(path, funcdat_file), prec, polarity, calib)
        datafiles.append(datafile)
    return datafiles


def parse_function(path, prec=0, polarity=None, calib=None):
    """
    Parses data for a Waters function. 

    Each function corresponds to a MS or UV spectrum. \
        The data is extracted from numbered _FUNC .IDX and _FUNC .DAT files.

    IMPORTANT: There are multiple data formats for Waters spectra that are \
        differentiated by the number of bytes used to store each data pair. \
        This program only supports the 2, 6, and 8 byte formats. 

    Args:
        path (str): Path to the _FUNC .DAT file.
        prec (int, optional): Number of decimals to round ylabels.
        polarity (str, optional): Polarity of the spectrum.
        calib (list, optional): Float calibration values of the spectrum.
    
    Returns:
        DataFile with MS or UV spectrum data. 

    """
    # Extract the retention times, "pair" counts,
    #     and _FUNC .DAT data format from the _FUNC .IDX file.
    # A "pair" refers to a data pair of mz-intensity or wavelength-absorbance.
    times, pair_counts, bytes_per_pair = parse_funcidx(path[:-3] + 'IDX')
    if bytes_per_pair not in {2, 4, 6, 8}:
        raise Exception("The {bytes_per_pair}-bytes format is not supported.")

    # Extract the ylabels and data values from the _FUNC .DAT file. 
    parse_funcdat = parse_funcdat2
    if bytes_per_pair == 6:
        parse_funcdat = parse_funcdat6
    elif bytes_per_pair == 8:
        parse_funcdat = parse_funcdat8
    elif bytes_per_pair == 4:
        parse_funcdat = parse_funcdat4
    ylabels, data = parse_funcdat(path, pair_counts, prec, calib)

    # Spectra without an assigned polarity always contain UV data.
    detector = 'MS' if polarity else 'UV'
    metadata = {'polarity': polarity} if polarity else {}

    return DataFile(path, detector, times, ylabels, data, metadata)


def parse_funcidx(path):
    """ 
    Parses a Waters _FUNC .IDX file. 

    Learn more about this file format :ref:`here <funcidx>`.

    Args:
        path (str): Path to the _FUNC .IDX file. 

    Returns:
        1D numpy array with retention times. 1D numpy array with the \
            number of data pairs at each time. Integer representing \
            the file format of the corresponding _FUNC .DAT file. 

    """
    num_times = os.path.getsize(path) // 22

    # Extract retention times and indexing info from the _FUNC .IDX file.
    with open(path, 'rb') as f:
        raw_bytes = f.read()
    offsets = np.ndarray(num_times, '<I', raw_bytes, 0, 22)
    pair_counts = np.ndarray(num_times, '<I', raw_bytes, 4, 22) & 0x3FFFFF
    times = np.ndarray(num_times, '<f', raw_bytes, 12, 22).copy()

    # Calculate the _FUNC .DAT file format based on the bytes per pair.
    nonzero = pair_counts != 0
    final_offset = offsets[nonzero][-1]
    final_paircount = pair_counts[nonzero][-1]
    dat_size = os.path.getsize(path[:-3] + 'DAT')
    bytes_per_pair = (dat_size - final_offset) // final_paircount

    return times, pair_counts, bytes_per_pair


def parse_funcdat2(path, pair_counts, prec=0, calib=None):
    """
    Parses a Waters _FUNC .DAT file with the 2-bytes format. 

    This format contains MS data. 

    Learn more about this file format :ref:`here <funcdat2>`.

    Args:
        path (str): Path to the _FUNC .DAT file. 
        pair_counts (np.ndarray): 
            1D array with the number of data pairs at each retention time.
        prec (int, optional): Number of decimals to round ylabels. 
        calib (list, optional): Float calibration values of the spectrum.
    
    Returns: 
        1D numpy array with ylabels. 2D numpy array with \
            data values where the rows correspond to retention times \
            and the columns correspond to ylabels.

    """
    # Extract the mz values from the _FUNCTNS.INF file. 
    # This code makes the assumption that in this format the  
    #     number of mz values is constant at each retention time. 
    inf_path = os.path.join(os.path.dirname(path), '_FUNCTNS.INF')
    func_index = int(re.findall(r"\d+", os.path.basename(path))[0]) - 1
    mzs = parse_funcinf(inf_path)[func_index]
    ylabels = mzs[mzs != 0.0]

    # Extract the intensities from the _FUNC .DAT file. 
    with open(path, 'rb') as f:
        raw_bytes = f.read()
    num_datapairs = np.sum(pair_counts)
    raw_values = np.ndarray(num_datapairs, '<H', raw_bytes)
    val_base = raw_values >> 3
    val_pow = raw_values & 0x7
    values = np.multiply(val_base, 4 ** val_pow, dtype=np.uint32)

    # Note: We have not come across a sample with more than 1 mz value. 
    # This may need to be reshaped differently in the future. 
    data = values.reshape((pair_counts.size, ylabels.size))

    return ylabels, data


def parse_funcdat4(path, pair_counts, prec=0, calib=None):
    """
    Parses a Waters _FUNC .DAT file with the 4-bytes format.

    This format may contain MS or UV data.

    Learn more about this file format :ref:`here <funcdat6>`.

    Args:
        path (str): Path to the Waters _FUNC .DAT file.
        pair_counts (np.ndarray):
            1D array with the number of data pairs at each retention time.
        prec (int, optional): Number of decimals to round ylabels.
        calib (list, optional): Float calibration values of the spectrum.

    Returns:
        1D numpy array with ylabels. 2D numpy array with data values \
            where the rows correspond to retention times and \
            the columns correspond to ylabels.

    """
    # Extract the mz values from the _FUNCTNS.INF file.
    # This code makes the assumption that in this format the
    #     number of mz values is constant at each retention time.
    inf_path = os.path.join(os.path.dirname(path), '_FUNCTNS.INF')
    func_index = int(re.findall("\d+", os.path.basename(path))[0]) - 1
    mzs = parse_funcinf(inf_path)[func_index]
    ylabels = mzs[mzs != 0.0]

    # Read most significant 4 bytes from each segment into `raw_values`.
    with open(path, 'rb') as f:
        raw_bytes = f.read()

    # Calculate the `values` from each 4-byte segment.
    num_datapairs = np.sum(pair_counts)
    raw_values = np.ndarray(num_datapairs, '<I', raw_bytes)

    val_powers = raw_values >> 22  # get the first 10 bits (drop 22 on 32)
    val_separator = (raw_values >> 21) & 0x1  # get bits at position 11
    val_bases = raw_values & 0x1FFFFF  # keep the last 21 bits (11-32)
    val_bases_float = val_bases / 0x400  # out of the 21 bits, the 11 first are the integer part and the 10 last are the "decimal" part
    # bit at position 12 being always '1' it means that the float values
    # is always between 1024 &nd 2048 (factor of 2)
    min_val_bases = np.min(val_bases[val_bases > 0])
    max_val_bases = np.max(val_bases)
    val_base_ampl = max_val_bases - 0xFFFFF

    values = val_bases_float * (2. ** np.subtract(val_powers, 10, dtype=np.int32))

    # Note: We have not come across a sample with more than 1 mz value.
    # This may need to be reshaped differently in the future.
    data = values.reshape((pair_counts.size, ylabels.size))

    del val_bases, val_powers, raw_values, raw_bytes

    return ylabels, data


def parse_funcinf(path):
    """
    Parses a Waters _FUNCTNS.INF file. 

    This file contains mz values for the 2-byte format. 

    Learn more about this file format :ref:`here <funcdat2>`.

    Args:
        path (str): Path to the _FUNCTNS.INF file. 

    Returns:
        2D numpy array of mz values where the rows correspond to functions.

    """
    with open(path, 'rb') as f:
        raw_bytes = f.read()
    num_funcs = os.path.getsize(path) // 416
    mzs = np.ndarray((num_funcs, 32), "<f", raw_bytes, 160, (416, 4))
    return mzs


def parse_funcdat6(path, pair_counts, prec=0, calib=None):
    """
    Parses a Waters _FUNC .DAT file with the 6-bytes format. 

    This format may contain MS or UV data. 

    Learn more about this file format :ref:`here <funcdat6>`.

    Args:
        path (str): Path to the Waters _FUNC .DAT file. 
        pair_counts (np.ndarray): 
            1D array with the number of data pairs at each retention time.
        prec (int, optional): Number of decimals to round ylabels. 
        calib (list, optional): Float calibration values of the spectrum.
    
    Returns: 
        1D numpy array with ylabels. 2D numpy array with data values \
            where the rows correspond to retention times and \
            the columns correspond to ylabels.

    """
    num_times = pair_counts.size
    num_datapairs = np.sum(pair_counts)

    # Read most significant 4 bytes from each segment into `raw_values`.
    with open(path, 'rb') as f:
        raw_bytes = f.read()
    raw_values = np.ndarray(num_datapairs, '<I', raw_bytes, 2, 6)

    # The data is stored as key-value pairs. 
    # For example, in MS data these are mz-intensity pairs. 
    # Calculate the `keys` from each 6-byte segment. 
    key_bases = raw_values >> 9
    key_powers = (raw_values & 0x1F0) >> 4
    key_powers = np.subtract(key_powers, 23, dtype=np.int32)
    keys = key_bases * (2.0 ** key_powers)
    del key_bases, key_powers

    # If it is MS data, calibrate the masses. 
    if calib:
        keys = calibrate(keys, calib)

    # Then round the keys to the nearest whole number. 
    keys = np.round(keys, prec)

    # Calculate the `values` from each 6-byte segment.
    val_bases = np.ndarray(num_datapairs, '<h', raw_bytes, 0, 6)
    val_powers = raw_values & 0xF
    values = val_bases * (4 ** val_powers)
    del val_bases, val_powers, raw_values, raw_bytes

    # Make the array of `ylabels` with keys. 
    ylabels = np.unique(keys)
    ylabels.sort()

    # Fill the `data` array with values. 
    key_indices = np.searchsorted(ylabels, keys)
    data = np.zeros((num_times, ylabels.size), dtype=np.int64)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + pair_counts[i]
        np.add.at(
            data[i],
            key_indices[cur_index:stop_index],
            values[cur_index:stop_index])
        cur_index = stop_index
    del key_indices, keys, values, pair_counts

    return ylabels, data


def parse_funcdat8(path, pair_counts, prec=0, calib=None):
    """
    Parses a Waters _FUNC .DAT file with the 8-bytes format. 

    This format contains MS data. 

    Learn more about this file format :ref:`here <funcdat8>`.

    Args:
        path (str): Path to the _FUNC .DAT file. 
        pair_counts (np.ndarray): 
            1D array with the number of data pairs at each retention time.
        prec (int, optional): Number of decimals to round ylabels. 
        calib (list, optional): Float calibration values of the spectrum.
    
    Returns: 
        1D numpy array with ylabels. 2D numpy array with \
            data values where the rows correspond to retention times \
            and the columns correspond to ylabels.
    """
    num_times = pair_counts.size
    num_datapairs = np.sum(pair_counts)

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

    # Make the array of `ylabels` with keys. 
    ylabels = np.unique(keys)
    ylabels.sort()

    # Fill the `data` array with values. 
    key_indices = np.searchsorted(ylabels, keys)
    data = np.zeros((num_times, ylabels.size), dtype=np.int64)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + pair_counts[i]
        np.add.at(
            data[i],
            key_indices[cur_index:stop_index],
            values[cur_index:stop_index])
        cur_index = stop_index
    del key_indices, keys, values, pair_counts

    return ylabels, data


def calibrate(mzs, calib_nums):
    """
    Calibrates :obj:`mzs` using :obj:`calib_nums`. 

    Computes the formula c1 * mz^0 + c2 * mz^1 + c3 * mz^2 \
        for each mz where c1, c2, and c3 are the calibration values.

    Args:
        mzs (np.ndarray): 1D array with uncalibrated mz values.
        calib_nums (list): Float calibration values.

    Returns:
        1D numpy array with calibrated mz values.

    """
    calib_mzs = np.zeros(mzs.size, dtype=np.float32)
    var = np.ones(mzs.size, dtype=np.float32)
    for coeff in calib_nums:
        calib_mzs += coeff * var
        var *= mzs
    del var
    return calib_mzs


def calc_frac(keyfrac_bits, num_bits):
    """ 
    Decodes fractional values from :obj:`keyfrac_bits`. 

    This method skips the costly computation of decoding a Waters \
        fraction by manipulating the bits into the standard \
        double-precision floating point format.

    Args:
        keyfrac_bits (np.ndarray): Bits representing a fractional value. 
        num_bits (np.ndarray): 
            Bitlength of each fractional value. This number is greater than
            the actual bitlength of the corresponding value in `keyfrac_bits` 
            when there are unseen zero bits padding the head.

    Returns: 
        1D numpy array with fractional values. 

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


def parse_analog(path, requested_files=None):
    """
    Finds and parses analog data from a Waters .raw directory.

    Args:
        path (str): Path to the .raw directory.
        requested_files (list, optional): List of filenames to parse.
    
    Returns:
        List of DataFiles that contain analog data. 

    """
    datafiles = []

    if '_CHROMS.INF' not in os.listdir(path):
        return datafiles

    analog_info = parse_chroinf(os.path.join(path, '_CHROMS.INF'))
    for i in range(len(analog_info)):
        fn = f"_CHRO{i + 1:0>3}.DAT"
        if requested_files and fn.lower() not in requested_files:
            continue
        datafile = parse_chrodat(os.path.join(path, fn), *analog_info[i])
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
        List of string lists that contain the name and unit (if it exists) \
            of the data in each analog file. 

    """
    f = open(path, 'r')
    f.seek(0x84)  # start offset
    analog_info = []
    while f.tell() < os.path.getsize(path):
        line = re.sub(r'[\0-\x04]|\$CC\$|\([0-9]*\)', '', f.read(0x55)).strip()
        split = line.split(',')
        info = []
        info.append(split[0])  # name
        if len(split) == 6:
            info.append(split[5])  # unit
        analog_info.append(info)
    f.close()
    return analog_info


def parse_chrodat(path, name, units=None):
    """
    Parses a Waters _CHRO .DAT file.

    These files may contain data for CAD, ELSD, or UV channels. \
        They may also contain other miscellaneous data like system pressure.
    
    IMPORTANT: MassLynx classifies these files as "analog" data, but \
        a DataDirectory will not treat CAD, ELSD, or UV channels as analog. \
        Instead, those channels will be mapped to their detector.

    Learn more about this file format :ref:`here <chrodat>`.

    Args:
        path (str): Path to the _CHRO .DAT file. 
        name (str): Name of the analog data.
        units (str, optional): Units of the analog data.
    
    Returns:
        DataFile with analog data, if the file can be parsed. Otherwise, None.

    """
    data_start = 0x80

    num_times = (os.path.getsize(path) - data_start) // 8
    if num_times == 0:
        return None

    with open(path, 'rb') as f:
        raw_bytes = f.read()
    times_immut = np.ndarray(num_times, '<f', raw_bytes, data_start, 8)
    vals_immut = np.ndarray(num_times, '<f', raw_bytes, data_start + 4, 8)

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
        path (str): Path to the .raw directory. 
    
    Returns:
        Dictionary with directory metadata. 

    """
    metadata = {}
    metadata['vendor'] = "Waters"

    with open(os.path.join(path, '_HEADER.TXT'), 'r') as f:
        lines = f.read().splitlines()
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
