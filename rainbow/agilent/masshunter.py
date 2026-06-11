""" 
Methods for parsing Agilent Masshunter files. 
 
"""
import os
import ntpath
import struct
import numpy as np
from lxml import etree
from rainbow import DataFile


"""
MAIN PARSING METHOD 

"""

def parse_allfiles(path, prec=0):
    """
    Finds and parses Agilent Masshunter data files. \
    Currently, only HRMS data is supported. \
    See the documentation on :obj:`parse_msdata` for info on the limitations.

    If more file formats are added in the future, \
        parsing should branch out from this method. 

    Args:
        path (str): Path to the Agilent .D directory.
        prec (int, optional): Number of decimals to round ylabels.
    
    Returns:
        List containing a DataFile for each parsed file.

    """
    datafiles = []

    acqdata_path = os.path.join(path, "AcqData")
    if not os.path.isdir(acqdata_path):
        return datafiles

    acqdata_files = set(os.listdir(acqdata_path))
    if {"MSTS.xml", "MSScan.xsd", "MSScan.bin"} <= acqdata_files:
        if "MSProfile.bin" in acqdata_files:
            datafiles.append(parse_msdata(acqdata_path, prec))
        # Future work should also parse the MSPeak.bin format. 
        # elif "MSPeak.bin" in acqdata_files:
        #     ...

    return datafiles


def parse_metadata(path):
    """
    Parses Agilent MassHunter metadata at the directory level.

    Args:
        path (str): Path to the Agilent .D directory.

    Returns:
        Dictionary containing directory metadata.

    """
    acqdata_path = os.path.join(path, "AcqData")
    if not os.path.isdir(acqdata_path):
        return {}

    file_metadata = parse_acqdata_metadata(acqdata_path)
    metadata = {
        key: file_metadata[key] for key in ("date", "vialpos")
        if key in file_metadata
    }
    if metadata:
        metadata["vendor"] = "Agilent"
    return metadata


def parse_acqdata_metadata(path):
    """
    Parses minimal MassHunter metadata from the AcqData directory.

    Args:
        path (str): Path to the AcqData subdirectory.

    Returns:
        Dictionary containing metadata.

    """
    metadata = {}
    sample_info_path = os.path.join(path, "sample_info.xml")
    if os.path.exists(sample_info_path):
        sample_fields = read_sample_info(sample_info_path)
        if "AcqTime" in sample_fields:
            metadata["date"] = sample_fields["AcqTime"]
        if "Sample Position" in sample_fields:
            metadata["vialpos"] = sample_fields["Sample Position"]
        if "Method" in sample_fields:
            metadata["method"] = ntpath.basename(sample_fields["Method"])
        if "InstrumentName" in sample_fields:
            metadata["instrument"] = sample_fields["InstrumentName"]

    contents_path = os.path.join(path, "Contents.xml")
    if "date" not in metadata and os.path.exists(contents_path):
        tree = etree.parse(contents_path)
        acquired_time = clean_text(tree.getroot().findtext("AcquiredTime"))
        if acquired_time:
            metadata["date"] = acquired_time

    return metadata


def read_sample_info(path):
    """
    Reads a MassHunter sample_info.xml file as a name-value dictionary.

    """
    tree = etree.parse(path)
    root = tree.getroot()
    fields = {}
    for field in root.findall("Field"):
        name = clean_text(field.findtext("Name"))
        value = clean_text(field.findtext("Value"))
        if name and value:
            fields[name] = value
    return fields


def clean_text(text):
    """
    Returns stripped text or None for empty XML text.

    """
    if text is None:
        return None
    text = text.strip()
    return text or None


"""
MS PARSING METHODS 

"""

def parse_msdata(path, prec=0):
    """
    Parses Masshunter MS data. 

    IMPORTANT: Masshunter MS data can be either stored in MSProfile.bin or \
        MSPeak.bin. This method only supports parsing MSProfile.bin.  
    
    The following files are used (in order of listing): 
        - MSTS.xml -> Number of retention times.
        - MSScan.xsd -> File structure of MSScan.bin.
        - MSScan.bin -> Offsets, compression info, and calibration ID for MSProfile.bin.
        - DefaultMassCal.xml -> Calibration method and ID.
        - MSMassCal.bin -> Calibration info for masses.
        - MSProfile.bin -> Actual data values.

    Learn more about this file format :ref:`here <hrms>`.

    Args:
        path (str): Path to the AcqData subdirectory.
        prec (int, optional): Number of decimals to round mz values.
    
    Returns:
        DataFile containing Masshunter MS data.

    """
    import lzf

    metadata = parse_acqdata_metadata(path)

    # MSTS.xml: Extract number of retention times. 
    # In future work, this step could potentially be skipped by reading 
    #    MSScan.bin until EOF and counting the offsets. 
    # This would remove reliance on MSTS.xml being in the directory.
    tree = etree.parse(os.path.join(path, "MSTS.xml"))
    root = tree.getroot()
    num_times = 0
    for time_seg in root.findall("TimeSegment"):
        num_times += int(time_seg.find("NumOfScans").text)

    # MSScan.xsd: Extract the file structure of MSScan.bin. 
    # There are "simple" types can be directly translated into number types.
    # But there are "complex" types that are made up of other
    #     "simple" and "complex" types.
    # These are stored in a dictionary to enable recursive parsing. 
    tree = etree.parse(os.path.join(path, "MSScan.xsd"))
    root = tree.getroot()
    namespace = tree.xpath('namespace-uri(.)') 
    complextypes_dict = {}
    for complextype in root.findall(f"{{{namespace}}}complexType"):
        innertypes = []
        for element in complextype[0].findall(f"{{{namespace}}}element"):
            innertypes.append((element.get('name'), element.get('type')))
        complextypes_dict[complextype.get('name')] = innertypes

    # MSScan.bin: Extract information about MSProfile.bin. 
    # For each retention time, this includes: 
    #   - the retention time itself 
    #   - starting offset of data in MSProfile.bin
    #   - length in bytes of the compressed data 
    #   - length in bytes of the uncompressed data 
    #   - number of masses recorded at the retention time
    # Future work could determine if the data blocks for each retention time 
    #     are always contiguous. If that is the case, the offset is unneeded. 
    f = open(os.path.join(path, "MSScan.bin"), 'rb')
    f.seek(0x4c)
    SpectrumParamsType_repeat = struct.unpack('<I', f.read(4))[0]   # somehow this value is stored here
    f.seek(0x58) # start offset
    f.seek(struct.unpack('<I', f.read(4))[0])
    data_info = np.empty(num_times, dtype=object)
    for i in range(num_times):
        # "ScanRecordType" is always the name of the root "complex" type.
        scan_info = read_complextype(f, complextypes_dict, "ScanRecordType")
        # Sometimes multiple spectrum params are recorded per scan, e.g., profile and centroid.
        # In observed files, SpectrumFormatID 1 is profile data in MSProfile.bin, but this is not known to be guaranteed.
        # SpectrumFormatID 2 was centroid data in the current test data; this parser only supports profile data.
        for j in range(1, SpectrumParamsType_repeat):
            # you have to read "f" anyway to move the file pointer forward
            spectrum_info = read_complextype(f, complextypes_dict, "SpectrumParamsType")
            if spectrum_info["SpectrumFormatID"] == 1:
                scan_info['SpectrumParamValues'] = spectrum_info
        spectrum_info = scan_info['SpectrumParamValues']
        data_info[i] = (
            scan_info['ScanTime'], 
            spectrum_info['PointCount'],
            spectrum_info['SpectrumOffset'], 
            spectrum_info['ByteCount'], 
            spectrum_info['UncompressedByteCount'],
            scan_info['CalibrationID']
        )
    f.close()

    # DefaultMassCal.xml: Extract calibration methods.
    # Information needed (ValueUseFlags) is located here:
    # <DefaultMassCalibration>
    #     <DefaultCalibrations>
    #         <DefaultCalibration ...>
    #            <Step Number="2">
    #                <ValueUseFlags>XX</ValueUseFlags>
    # Usually there are two DefaultCalibration entries, one for positive and the other for negative ion mode.
    default_calib = {}
    default_mass_cal_path = os.path.join(path, "DefaultMassCal.xml")
    if os.path.exists(default_mass_cal_path):
        tree = etree.parse(default_mass_cal_path)
        root = tree.getroot()
        for calib in root.findall("./DefaultCalibrations/DefaultCalibration"):
            calib_id = calib.get("DefaultCalibrationID")
            # Number="1" is for coeff and base, which we do not collect here because they varies per scan.
            # Get info for Step Number="2", which holds the polynomial calibration coefficients shared for all scans.
            step2 = calib.find("./Step[@Number='2']")
            if step2 is None:
                continue
            tech = step2.findtext("CalibrationTechnique")
            formula = step2.findtext("CalibrationFormula")
            if tech != "ExternalReference" or formula != "Polynomial":
                continue
            flags = format(int(step2.findtext("ValueUseFlags")), '08b')[::-1]
            values = [float(v.text) for v in step2.findall("./Values/Value")]
            default_calib[int(calib_id)] = {
                "ValueUseFlags": flags,
                "Values": values
            }
    for _, _, _, _, _, calib_id in data_info:
        default_calib.setdefault(calib_id, {"ValueUseFlags": "00000000", "Values": []})

    # MSMassCal.bin: Extract calibration values for masses. 
    # There seem to be 10 doubles stored for each retention time. The first two
    #     are coeff and base, which vary per scan. The other 8 are usually the
    #     same as those in DefaultMassCal.xml, but we read them per scan just in case.
    # The structure is:
    #   - coeff (double)
    #   - base (double)
    #   - left (double)
    #   - right (double)
    #   - a2 (double)
    #   - b2 (double)
    #   - c2 (double)
    #   - d2 (double)
    #   - e2 (double)
    #   - f2 (double)
    # We also need flag from DefaultMassCal.xml to know which of a2-f2 to use.
    #   - If the flag in int is 86, for example, its binary representation is 01010110 -> 01101010 (bit order reversed)
    #   - The position of “1” indicates the degree of the polynomial.
    #   - This means
    #     """
    #     flag:  0  1  1  0  1  0  1  0
    #     order: 0  1  2  3  4  5  6  7
    #     coeff: NA a2 b2 NA c2 NA d2 NA
    #     """ 
    #     - a2, b2, c2, and d2 are used (because the "1" appears in positions 1, 2, 4, and 6)
    #     - They are assigned as coefficients of t^1, t^2, t^4, and t^6 respectively (according to the positions of "1"s).
    #     - e2 and f2 are not used (usually their values are 0.0)
    #     - Then the calibrated m/z is calculated as:
    #         m/z = (coeff * (t - base))**2 - (a2*t**1 + b2*t**2 + c2*t**4 + d2*t**6)
    #         where t is the time of flight of ions before the calibration.
    f = open(os.path.join(path, "MSMassCal.bin"), 'rb')
    f.seek(0x4c) # start offset
    calib_vals = np.ndarray((num_times, 10), '<d', f.read(), 0, (84, 8))
    f.close()

    # MSProfile.bin: Extract the data values. 
    # The raw bytes are decompressed using the `python-lzf` library. 
    # This code may be slow. We note that LZF decompression seems to not
    #     rely on being decoded in smaller blocks as the code suggests. 
    #     Future work could potentially implement numpy speedups by
    #     decompressing all the bytes at once and using clever indexing. 
    f = open(os.path.join(path, "MSProfile.bin"), 'rb')
    twodoubles_unpack = struct.Struct('<dd').unpack
    times = np.empty(num_times)
    num_mz_per_time = np.empty(num_times)
    mz_list = []
    inten_list = []
    for i in range(num_times):
        time, num_mz, offset, comp_len, decomp_len, calib_id = data_info[i]
        times[i] = time
        num_mz_per_time[i] = num_mz

        # Decompress the bytes for the current retention time. 
        f.seek(offset)
        comp_bytes = f.read(comp_len)
        # Decompress intensity values.
        if decomp_len > 0:
            mem_view = memoryview(lzf.decompress(comp_bytes, decomp_len))
            inten = np.ndarray(num_mz, '<I', bytes(mem_view[16:]))
        else:   # sometimes decomp_len is not provided, using different compression method
            mem_view = memoryview(comp_bytes)
            inten = decompress_inten_list(mem_view[16:], endian="<", total_len=num_mz)
        # Calculate the primary calibration of mz values. 
        start_mz, delta_mz = twodoubles_unpack(mem_view[:16])
        t_list = np.linspace(start_mz, start_mz + delta_mz * (num_mz - 1), num_mz)  # more accurate to use linspace than arange here
        # Calculate the polynomial calibration of mz values.
        coeff, base, left, right, a2, b2, c2, d2, e2, f2 = calib_vals[i]
        flag = default_calib[calib_id]["ValueUseFlags"]     # e.g., '1010110'
        mzs = t_list - base
        mzs *= coeff
        mzs **= 2
        coefficients = (a2, b2, c2, d2, e2, f2)
        coeff_idx = 0
        poly_coeffs = [0.0] * 8
        for j, b in enumerate(flag):
            if b == '1' and coeff_idx < len(coefficients):
                poly_coeffs[j] = coefficients[coeff_idx]
                coeff_idx += 1
        calib_values = sum(c * (np.clip(t_list, left, right)**ord) for ord, c in enumerate(poly_coeffs))
        calib_mzs = mzs - calib_values

        mz_list.extend(calib_mzs.tolist())   
        inten_list.extend(inten.tolist())

    # Process the extracted data values. 
    mz_arr = np.round(np.array(mz_list), prec)
    intensities = np.array(inten_list, dtype=np.uint32)

    # Make the array of ylabels containing mz values. 
    mz_ylabels = np.unique(mz_arr)
    mz_ylabels.sort()

    # Fill the `data` array containing intensities. 
    # Optimized using numpy vectorization.
    mz_indices = np.searchsorted(mz_ylabels, mz_arr)
    data = np.zeros((num_times, mz_ylabels.size), dtype=np.uint64)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + int(num_mz_per_time[i])
        np.add.at(
            data[i], 
            mz_indices[cur_index:stop_index], 
            intensities[cur_index:stop_index])
        cur_index = stop_index
    
    f.close()
    
    return DataFile("MSProfile.bin", 'MS', times, mz_ylabels, data, dict(metadata))
   
def read_complextype(f, complextypes_dict, name):
    """ 
    Reads a "complex" type from :obj:`f`. Used only for MSScan.bin. 

    Mutually recurs with :obj:`read_type`.

    Args:
        f (_io.BufferedReader): File opened in 'rb' mode.
        complextypes_dict (dict): Dictionary defining all "complex" types.
        name (str): Name of the "complex" type to parse. 

    Returns:
        Dictionary mapping subtype names to values. \
        If the subtype is "complex", the value is a nested dictionary. \
        Otherwise, the value is a number.
        
    """ 
    desc_to_value = {}
    for subname, subtype in complextypes_dict[name]:
        desc_to_value[subname] = read_type(f, complextypes_dict, subtype)
    return desc_to_value

def read_type(f, complextype_dict, name):
    """
    Reads a type from :obj:`f`. Used only for MSScan.bin. 

    Mutually recurs with :obj:`read_complextype`.

    Args: 
        f (_io.BufferedReader): File opened in 'rb' mode.
        complextypes_dict (dict): Dictionary defining all "complex" types.
        name (str): Name of the type to parse. 

    Returns:
        If the type is "simple", a number value. \
        If the type is "complex", a dictionary mapping names to values. 

    """
    if name == 'xs:byte':
        return struct.unpack('c', f.read(1))[0]
    elif name == 'xs:short':
        return struct.unpack('<H', f.read(2))[0]
    elif name == 'xs:int':
        return struct.unpack('<I', f.read(4))[0]
    elif name == 'xs:long':
        return struct.unpack('<Q', f.read(8))[0]
    elif name == 'xs:float':
        return struct.unpack('<f', f.read(4))[0]
    elif name == 'xs:double':
        return struct.unpack('<d', f.read(8))[0]
    else:
        return read_complextype(f, complextype_dict, name.split(":")[-1])   # works with regardless of namespace prefix

# "Zero-specific implementation of Run-Length Encoding
def decompress_inten_list(comp_view, endian="<", total_len=None):
    if total_len is None:
        raise ValueError("total_len is required to decompress RLE intensity data.")
    # The lower 24 bits of the first 4 bytes represent the data length
    first_24 = struct.unpack(f'{endian}I', comp_view[0:4])[0] & 0x00FFFFFF
    if total_len != first_24:
        raise ValueError(
            f"RLE data length mismatch: expected {total_len}, found {first_24}.")
    # 4th byte seems to be fixed to \x90 ...?
    if comp_view[3] != 144:
        raise ValueError(
            f"Unexpected RLE marker byte: expected 144, found {comp_view[3]}.")

    # Initial values
    init_zero_repeat, size_switch_flag = struct.unpack(f'{endian}ii', comp_view[4:12])
    init_zero_repeat *= -1
    size_switch_flag *= -1
    if init_zero_repeat < 0:
        raise ValueError(f"Invalid initial zero repeat count: {init_zero_repeat}.")
    if size_switch_flag not in (1,2,3,4):
        raise ValueError(f"Invalid RLE size switch flag: {size_switch_flag}.")

    ##########
    inten_list = [0] * total_len    # initialize the list with zeros because the length of consecutive zeros at the end of the data is not included.
    UNPACKERS = {
        1: struct.Struct(f'{endian}b').unpack,
        2: struct.Struct(f'{endian}h').unpack,
        3: struct.Struct(f'{endian}i').unpack,
        4: struct.Struct(f'{endian}q').unpack,
    }
    SIZES = {1:1, 2:2, 3:4, 4:8}
    inten_list[0:init_zero_repeat] = [0] * init_zero_repeat
    cur_idx = init_zero_repeat
    cur_size = SIZES[size_switch_flag]
    cur_unpacker = UNPACKERS[size_switch_flag]
    offset = 12
    while offset < len(comp_view):
        cur_bytes = cur_unpacker(comp_view[offset:offset+cur_size])[0]
        offset += cur_size
        # if positive, direct data
        if cur_bytes >= 0:
            inten_list[cur_idx] = cur_bytes
            cur_idx += 1
        # if negative, zero run-length or size switch
        else:
            cur_bytes *= -1
            # zero-filling
            len_zero, size_switch_flag = divmod(cur_bytes, 4)
            inten_list[cur_idx:cur_idx+len_zero] = [0] * len_zero
            cur_idx += len_zero
            # size switch
            cur_size = SIZES[size_switch_flag]
            cur_unpacker = UNPACKERS[size_switch_flag]
    return np.array(inten_list, dtype=np.uint32)
