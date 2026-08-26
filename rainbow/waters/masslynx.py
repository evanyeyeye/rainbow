""" 
Methods for parsing Waters Masslynx files. 

Patched to support case-insensitive filenames (e.g. Perkin-Elmer GC-MS).

"""
import os
import re
import numpy as np
from rainbow.datafile import DataFile
from rainbow._binning import bin_datapairs
# pandas is imported where it is used, not here. It is the single largest cost
# in importing rainbow, and only this module's transition table needs it, so
# paying for it on every import would tax every read that never touches one.
# matplotlib is deferred the same way, in datafile.plot.


# A UV function records one absorbance per whole nanometre, so its ylabels are
# laid out on a 1 nm grid whatever m/z bin_width the caller asked for.
_UV_WAVELENGTH_STEP = 1.0

# Lookup tables for the per-pair exponents in the 6-byte _FUNC.DAT format.
# Both exponents come from small bit-fields, so indexing a table is much
# faster than np.power over the whole pair array - with identical values.
_FUNC6_KEY_POW2 = 2.0 ** (np.arange(32) - 23)  # 2 ** (((raw & 0x1F0) >> 4) - 23)
_FUNC6_VAL_POW4 = (4 ** np.arange(16)).astype(np.int64)  # 4 ** (raw & 0xF)

# _FUNCTNS.INF holds one 416-byte record per function, in funcdat order. The
# low 5 bits of each record's first byte are the MassLynx function-type code
# (0 = MS scan, 1 = SIR = Waters' name for SIM, 12 = diode array). The upper
# bits are acquisition flags (continuum/centroid), so they are masked off.
_FUNCTNS_RECORD = 32 * 13
_FUNC_TYPE_MASK = 0x1F
_FUNC_TYPE_MS_SCAN = 0
_FUNC_TYPE_SIR = 1
# Diode array. The authoritative signal that a function's axis is wavelength
# rather than m/z, and stronger than the absence of a polarity: polarities are
# read from separate metadata that can be missing or short, and white.raw
# records six MRM (type 9) functions for which none is read.
_FUNC_TYPE_DIODE_ARRAY = 12


def _find_file(directory, target_name):
    """
    Case-insensitive file lookup in a directory.

    Args:
        directory (str): Path to the directory.
        target_name (str): Filename to search for (case-insensitive).

    Returns:
        The actual filename as it exists on disk, or None if not found.

    """
    target_lower = target_name.lower()
    for fn in os.listdir(directory):
        if fn.lower() == target_lower:
            return fn
    return None


def _find_file_path(directory, target_name):
    """
    Case-insensitive file lookup that returns the full path.

    Args:
        directory (str): Path to the directory.
        target_name (str): Filename to search for (case-insensitive).

    Returns:
        Full path to the file, or None if not found.

    """
    fn = _find_file(directory, target_name)
    if fn is not None:
        return os.path.join(directory, fn)
    return None


"""
SPECTRUM PARSING METHODS

"""


def parse_spectrum(path, display_precision=0, bin_width=1.0,
                   requested_files=None, labels_only=False):
    """
    Finds and parses Waters UV and MS spectra from a .raw directory.

    IMPORTANT: The HRMS data format is not supported. \
        It can be differentiated from low resolution MS data using the \
        _extern.inf or _FUNC .IDX files.

    Args:
        path (str): Path to the .raw directory.
        display_precision (int, optional): Decimals for displayed ylabels.
        bin_width (float, optional): m/z bin width for MS binning.
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
    extern_inf = _find_file(path, '_extern.inf')
    if extern_inf is not None:
        # Parse MS polarities from _extern.inf. 
        with open(os.path.join(path, extern_inf), 'rb') as f:
            lines = f.read().decode('ascii', 'ignore').splitlines()
        for i in range(len(lines)):
            # Waters format: "Instrument Parameters" trigger
            if lines[i].startswith("Instrument Parameters"):
                if lines[i + 1].startswith("Polarity"):
                    polarity = lines[i + 1].split('\t\t\t')[1][-1]
                else:
                    try:
                        polarity = lines[i + 2].split('\t')[1][-1]
                    except Exception:
                        raise Exception("Waters HRMS data is not supported.")
                polarities.append(polarity)
            # PE/TurboMass format: "Function N:" trigger
            elif re.match(r'^Function\s+\d+', lines[i]):
                for j in range(i + 1, min(i + 5, len(lines))):
                    if lines[j].strip().startswith("Polarity"):
                        pol_value = lines[j].split('\t')[-1].strip()
                        polarity = pol_value[-1]  # last char: + or -
                        polarities.append(polarity)
                        break

        # Parse mz calibration values from _HEADER.txt. 
        # There are a separate list of values for each MS spectrum. 
        # PE exports may omit _HEADER.TXT; skip calibration instead of failing.
        header_txt = _find_file_path(path, '_HEADER.TXT')
        if header_txt is not None:
            with open(header_txt, 'r') as f:
                lines = f.read().splitlines()
            for line in lines:
                if not line.startswith("$$ Cal Function"):
                    continue
                calib_nums.append(
                    [float(num) for num in line.split(': ')[1].split(',')[:-1]])

    # The raw spectrum data is stored in _FUNC .DAT files. 
    # Each MS spectrum has an assigned polarity, 
    #     but may not have calibration values.
    funcdat_files = sorted(
        fn for fn in os.listdir(path)
        if re.match(r'^_FUNC\d{3}\.DAT$', fn, re.IGNORECASE))
    # Waters validates _FUNCTNS.INF size; PE exports may omit this file entirely.
    functns_inf = _find_file_path(path, '_FUNCTNS.INF')
    func_types = []
    if functns_inf is not None:
        assert (os.path.getsize(functns_inf) == 32 * 13 * len(funcdat_files))
        func_types = _function_types(functns_inf, len(funcdat_files))
    for funcdat_index, funcdat_file in enumerate(funcdat_files):
        if requested_files and funcdat_file.lower() not in requested_files:
            continue
        polarity = None
        calib = None
        # polarities/calib_nums may be shorter than funcdat_files when metadata
        # is missing or only partially parsed; spectra parse without calib/polarity.
        if funcdat_index < len(polarities):
            polarity = polarities[funcdat_index]
            if funcdat_index < len(calib_nums):
                calib = calib_nums[funcdat_index]
        func_type = (func_types[funcdat_index]
                     if funcdat_index < len(func_types) else None)
        datafile = parse_function(
            os.path.join(path, funcdat_file), display_precision, bin_width,
            polarity, calib, func_type, labels_only)
        # Tag the MS acquisition mode (SIM vs scan) from the function type, so a
        # SIR (Waters' SIM) channel is distinguishable from a full scan.
        if datafile.detector == 'MS' and funcdat_index < len(func_types):
            mode = _acquisition_mode(func_types[funcdat_index])
            if mode:
                datafile.metadata['acquisition_mode'] = mode
        datafiles.append(datafile)
    return datafiles


def _function_types(functns_inf_path, count):
    """The MassLynx function-type code of each function, in funcdat order."""
    try:
        with open(functns_inf_path, 'rb') as f:
            data = f.read()
    except OSError:
        return []
    types = []
    for index in range(count):
        offset = index * _FUNCTNS_RECORD
        if offset >= len(data):
            break
        types.append(data[offset] & _FUNC_TYPE_MASK)
    return types


def _acquisition_mode(func_type):
    """``'SIM'`` or ``'Scan'`` for an MS function type, or None if unrecognized.

    SIR (Selected Ion Recording) is Waters' SIM. A plain MS scan is a scan. Other
    MS modes (MRM, parent/daughter scans) are left untagged so the exporter falls
    back to treating only single-ion data as SIM.
    """
    if func_type == _FUNC_TYPE_SIR:
        return 'SIM'
    if func_type == _FUNC_TYPE_MS_SCAN:
        return 'Scan'
    return None


def parse_function(path, display_precision=0, bin_width=1.0, polarity=None,
                   calib=None, func_type=None, labels_only=False):
    """
    Parses data for a Waters function. 

    Each function corresponds to a MS or UV spectrum. \
        The data is extracted from numbered _FUNC .IDX and _FUNC .DAT files.

    IMPORTANT: There are multiple data formats for Waters spectra that are \
        differentiated by the number of bytes used to store each data pair. \
        This program only supports the 2, 6, and 8 byte formats. 

    Args:
        path (str): Path to the _FUNC .DAT file.
        precision (int, optional): Number of decimals to round ylabels.
        polarity (str, optional): Polarity of the spectrum.
        calib (list, optional): Float calibration values of the spectrum.
    
    Returns:
        DataFile with MS or UV spectrum data. 

    """
    # Extract the retention times, "pair" counts,
    #     and _FUNC .DAT data format from the _FUNC .IDX file.
    # A "pair" refers to a data pair of mz-intensity or wavelength-absorbance.
    dat_dir = os.path.dirname(path)
    dat_base = os.path.basename(path)
    root, _ = os.path.splitext(dat_base)
    idx_path = _find_file_path(dat_dir, root + '.IDX')
    if idx_path is None:
        idx_path = path[:-3] + 'IDX'  # fallback to original behavior
    times, pair_counts, bytes_per_pair = parse_funcidx(idx_path)
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
    # Spectra without an assigned polarity always contain UV data.
    detector = 'MS' if polarity else 'UV'
    metadata = {'polarity': polarity} if polarity else {}

    # bin_width is an m/z control, so it only applies to the m/z functions. A
    # wavelength axis binned to an m/z width would quietly merge DAD channels
    # (at bin_width=5.0 a 190-wavelength trace came back as 39, five nanometres
    # to a column), and nothing warns about it: the too-fine-bin_width check
    # only looks at MS files.
    #
    # The recorded function type decides it where there is one, because the
    # polarity that names `detector` above comes from separate metadata that
    # can be missing: white.raw records six MRM functions with m/z axes and no
    # polarity for any of them, and exempting those would silently discard the
    # caller's bin_width. Only a function the file calls a diode array is
    # treated as wavelength; without a type, fall back to the polarity.
    is_wavelength = (func_type == _FUNC_TYPE_DIODE_ARRAY if func_type is not None
                     else detector == 'UV')
    ylabels, data = parse_funcdat(
        path, pair_counts, display_precision,
        _UV_WAVELENGTH_STEP if is_wavelength else bin_width, calib,
        labels_only)

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
    base = os.path.basename(path)
    root, _ = os.path.splitext(base)
    dat_path = _find_file_path(os.path.dirname(path), root + '.DAT')
    if dat_path is None:
        dat_path = path[:-3] + 'DAT'  # fallback
    nonzero = pair_counts != 0
    final_offset = offsets[nonzero][-1]
    final_paircount = pair_counts[nonzero][-1]
    dat_size = os.path.getsize(dat_path)
    bytes_per_pair = (dat_size - final_offset) // final_paircount

    return times, pair_counts, bytes_per_pair


def parse_funcdat2(path, pair_counts, display_precision=0, bin_width=1.0,
                   calib=None, labels_only=False):
    """
    Parses a Waters _FUNC .DAT file with the 2-bytes format. 

    This format contains MS data. 

    Learn more about this file format :ref:`here <funcdat2>`.

    Args:
        path (str): Path to the _FUNC .DAT file. 
        pair_counts (np.ndarray): 
            1D array with the number of data pairs at each retention time.
        precision (int, optional): Number of decimals to round ylabels. 
        calib (list, optional): Float calibration values of the spectrum.
    
    Returns: 
        1D numpy array with ylabels. 2D numpy array with \
            data values where the rows correspond to retention times \
            and the columns correspond to ylabels.

    """
    # Extract the mz values from the _FUNCTNS.INF file. 
    # This code makes the assumption that in this format the  
    #     number of mz values is constant at each retention time. 
    inf_path = _find_file_path(os.path.dirname(path), '_FUNCTNS.INF')
    if inf_path is None:
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


def parse_funcdat4(path, pair_counts, display_precision=0, bin_width=1.0,
                   calib=None, labels_only=False):
    """
    Parses a Waters _FUNC .DAT file with the 4-bytes format.

    This format may contain MS or UV data.

    Learn more about this file format :ref:`here <funcdat6>`.

    Args:
        path (str): Path to the Waters _FUNC .DAT file.
        pair_counts (np.ndarray):
            1D array with the number of data pairs at each retention time.
        precision (int, optional): Number of decimals to round ylabels.
        calib (list, optional): Float calibration values of the spectrum.

    Returns:
        1D numpy array with ylabels. 2D numpy array with data values \
            where the rows correspond to retention times and \
            the columns correspond to ylabels.

    """
    # Extract the mz values from the _FUNCTNS.INF file.
    # This code makes the assumption that in this format the
    #     number of mz values is constant at each retention time.
    inf_path = _find_file_path(os.path.dirname(path), '_FUNCTNS.INF')
    if inf_path is None:
        inf_path = os.path.join(os.path.dirname(path), '_FUNCTNS.INF')
    func_index = int(re.findall(r"\d+", os.path.basename(path))[0]) - 1
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


def parse_funcdat6(path, pair_counts, display_precision=0, bin_width=1.0,
                   calib=None, labels_only=False):
    """
    Parses a Waters _FUNC .DAT file with the 6-bytes format. 

    This format may contain MS or UV data. 

    Learn more about this file format :ref:`here <funcdat6>`.

    Args:
        path (str): Path to the Waters _FUNC .DAT file. 
        pair_counts (np.ndarray): 
            1D array with the number of data pairs at each retention time.
        precision (int, optional): Number of decimals to round ylabels. 
        calib (list, optional): Float calibration values of the spectrum.
    
    Returns: 
        1D numpy array with ylabels. 2D numpy array with data values \
            where the rows correspond to retention times and \
            the columns correspond to ylabels.

    """
    num_datapairs = np.sum(pair_counts)

    # Read most significant 4 bytes from each segment into `raw_values`.
    with open(path, 'rb') as f:
        raw_bytes = f.read()
    raw_values = np.ndarray(num_datapairs, '<I', raw_bytes, 2, 6)

    # The data is stored as key-value pairs.
    # For example, in MS data these are mz-intensity pairs.
    # Calculate the `keys` from each 6-byte segment.
    key_bases = raw_values >> 9
    keys = key_bases * _FUNC6_KEY_POW2[(raw_values & 0x1F0) >> 4]
    del key_bases

    # If it is MS data, calibrate the masses.
    if calib:
        keys = calibrate(keys, calib)

    # Calculate the `values` from each 6-byte segment.
    val_bases = np.ndarray(num_datapairs, '<h', raw_bytes, 0, 6)
    values = val_bases * _FUNC6_VAL_POW4[raw_values & 0xF]
    del val_bases, raw_values, raw_bytes

    # Bin the raw keys (binning is the lossy step; labels are cosmetic).
    return bin_datapairs(keys, values, pair_counts, bin_width,
                         display_precision=display_precision,
                         labels_only=labels_only)


def parse_funcdat8(path, pair_counts, display_precision=0, bin_width=1.0,
                   calib=None, labels_only=False):
    """
    Parses a Waters _FUNC .DAT file with the 8-bytes format. 

    This format contains MS data. 

    Learn more about this file format :ref:`here <funcdat8>`.

    Args:
        path (str): Path to the _FUNC .DAT file. 
        pair_counts (np.ndarray): 
            1D array with the number of data pairs at each retention time.
        precision (int, optional): Number of decimals to round ylabels. 
        calib (list, optional): Float calibration values of the spectrum.
    
    Returns: 
        1D numpy array with ylabels. 2D numpy array with \
            data values where the rows correspond to retention times \
            and the columns correspond to ylabels.
    """
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

    # Bin the raw keys (binning is the lossy step; labels are cosmetic).
    return bin_datapairs(keys, values, pair_counts, bin_width,
                         display_precision=display_precision,
                         labels_only=labels_only)


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

    chroms_inf = _find_file_path(path, '_CHROMS.INF')
    if chroms_inf is None:
        return datafiles

    analog_info = parse_chroinf(chroms_inf)
    for i in range(len(analog_info)):
        fn = f"_CHRO{i + 1:0>3}.DAT"
        actual_fn = _find_file(path, fn)
        if actual_fn is None:
            continue
        if requested_files and fn.lower() not in requested_files:
            continue
        datafile = parse_chrodat(os.path.join(path, actual_fn), *analog_info[i])
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

    header_txt = _find_file_path(path, '_HEADER.TXT')
    if header_txt is None:
        return metadata

    with open(header_txt, 'r') as f:
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



def parse_compound_names(path):
    cmp_file = _find_file_path(path, '_FUNC001.CMP')
    if cmp_file is None:
        cmp_file = os.path.join(path, "_FUNC001.CMP")
    with open(cmp_file, "rb") as f:
        data = f.read().decode("ascii", "ignore")
        data = data[7:]
        data = data.split("\x00")
        data = list(filter(lambda x: x != "", data))
        # loop through the da{}ta and remove the byte sequences x18 
        data = [re.sub(r'\x18', '', x) for x in data]
    data

    compounds = []
    transition = []
    for i in range(0, len(data), 3):
        compounds.append(data[i])
        transition.append(data[i+1])
    try:
        import pandas as pd
    except ImportError:
        raise ImportError(
            "The compound transition table is returned as a pandas DataFrame, "
            "and rainbow does not install pandas by default because nothing "
            "else needs it. Install it with "
            "'pip install rainbow-api[waters]'.") from None
    df = pd.DataFrame({"compounds": compounds, "transition": transition})

    df["index"] =  [i for i in range(1, len(transition)+1)]
    df["measurments"] = df["compounds"] + df["index"].astype(str)

    return  df


def parse_funcinf_q3(path):
    """
    Parses a Waters _FUNCTNS.INF file for Q3 transitions

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
    mzs = np.ndarray((num_funcs, 32), "<f", raw_bytes, 288, (416, 4))
    return mzs
