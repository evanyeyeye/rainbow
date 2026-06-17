""" 
Methods for parsing Agilent Masshunter files. 
 
"""
import os
import struct
import numpy as np
from lxml import etree
from rainbow import DataFile

# NOTE: `lzf` (python-lzf) is imported lazily inside parse_msdata. It is only
# needed to decompress MSProfile.bin, so the rest of this module - including
# the scan-counting that replaces MSTS.xml - works without it installed.


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
    # MSTS.xml is no longer required: the scan count is recovered by reading
    # MSScan.bin to EOF (see parse_msdata). This lets us parse Agilent OpenLab
    # .rslt/.sirslt result folders, which omit MSTS.xml.
    if {"MSScan.xsd", "MSScan.bin"} <= acqdata_files:
        if "MSProfile.bin" in acqdata_files:
            datafiles.append(parse_msdata(acqdata_path, prec))
        # Future work should also parse the MSPeak.bin format. 
        # elif "MSPeak.bin" in acqdata_files:
        #     ...

    return datafiles


"""
MS PARSING METHODS 

"""

def parse_msdata(path, prec=0):
    """
    Parses Masshunter MS data. 

    IMPORTANT: Masshunter MS data can be either stored in MSProfile.bin or \
        MSPeak.bin. This method only supports parsing MSProfile.bin.  
    
    The following files are used (in order of listing):
        - MSScan.xsd -> File structure of MSScan.bin.
        - MSScan.bin -> Offsets, compression info, and scan count.
        - MSMassCal.bin -> Calibration info for masses.
        - MSProfile.bin -> Actual data values.

    The scan count is recovered by reading MSScan.bin to EOF, so MSTS.xml is \
        not required. This lets us parse OpenLab .rslt/.sirslt result \
        folders, which omit MSTS.xml.

    Learn more about this file format :ref:`here <hrms>`.

    Args:
        path (str): Path to the AcqData subdirectory.
        prec (int, optional): Number of decimals to round mz values.

    Returns:
        DataFile containing Masshunter MS data.

    """
    # lzf is only needed to decompress MSProfile.bin below. Import it lazily
    # with a clear message so that everything up to this point can run (and be
    # tested) without python-lzf installed.
    try:
        import lzf
    except ModuleNotFoundError:
        raise ModuleNotFoundError(
            "You must install python-lzf to parse MSProfile.bin (HRMS) data.")

    # MSScan.xsd: Extract the file structure of MSScan.bin.
    complextypes_dict = parse_scan_xsd(os.path.join(path, "MSScan.xsd"))

    # MSScan.bin: Read every scan record until EOF. The number of records is
    # the number of retention times - historically read from MSTS.xml, which
    # is absent in OpenLab result folders. For each retention time we keep:
    #   - the retention time itself
    #   - the number of masses recorded
    #   - the starting offset of the data in MSProfile.bin
    #   - the compressed length in bytes
    #   - the uncompressed length in bytes
    scan_records = read_scan_records(
        os.path.join(path, "MSScan.bin"), complextypes_dict)
    num_times = len(scan_records)
    data_info = [
        (rec['ScanTime'],
         rec['SpectrumParamValues']['PointCount'],
         rec['SpectrumParamValues']['SpectrumOffset'],
         rec['SpectrumParamValues']['ByteCount'],
         rec['SpectrumParamValues']['UncompressedByteCount'])
        for rec in scan_records]

    # MSMassCal.bin: Extract calibration values for masses. 
    # There seem to be 10 doubles stored for each retention time. But this
    #     method only uses the first 2. Future work could determine what the
    #     other 8 doubles are used for.
    f = open(os.path.join(path, "MSMassCal.bin"), 'rb')
    f.seek(0x4c) # start offset
    calib_vals = np.ndarray((num_times, 2), '<d', f.read(), 0, (84, 8))
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
    intensity_bytearr = bytearray()
    for i in range(num_times):
        time, num_mz, offset, comp_len, decomp_len = data_info[i]
        times[i] = time
        num_mz_per_time[i] = num_mz

        # Decompress the bytes for the current retention time. 
        f.seek(offset)
        comp_bytes = f.read(comp_len)
        decomp_bytes = lzf.decompress(comp_bytes, decomp_len)
        decomp_view = memoryview(decomp_bytes)

        # Calculate the calibrated mz values. 
        start_mz, delta_mz = twodoubles_unpack(decomp_view[:16])
        mzs = np.arange(
            start_mz, start_mz + delta_mz * (num_mz - 1) + 1e-3, delta_mz)
        coeff, base = calib_vals[i]
        mzs -= base
        mzs *= coeff
        mzs **= 2

        mz_list.extend(mzs.tolist())   
        intensity_bytearr.extend(decomp_view[16:])

    # Process the extracted data values. 
    mz_arr = np.round(np.array(mz_list), prec)
    intensities = np.ndarray(mz_arr.size, '<I', bytes(intensity_bytearr))

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
    
    return DataFile("MSProfile.bin", 'MS', times, mz_ylabels, data, {})


def parse_scan_xsd(xsd_path):
    """
    Parses MSScan.xsd into a dictionary describing its "complex" types.

    There are "simple" types that translate directly into number types, and
    "complex" types made up of other "simple" and "complex" types. The
    returned dictionary maps each complex type's name to a list of its
    (name, type) members, which enables the recursive parsing in
    :obj:`read_complextype`.

    Args:
        xsd_path (str): Path to MSScan.xsd.

    Returns:
        Dictionary mapping complex type names to lists of (name, type) tuples.

    """
    tree = etree.parse(xsd_path)
    root = tree.getroot()
    namespace = tree.xpath('namespace-uri(.)')
    complextypes_dict = {}
    for complextype in root.findall(f"{{{namespace}}}complexType"):
        innertypes = []
        for element in complextype[0].findall(f"{{{namespace}}}element"):
            innertypes.append((element.get('name'), element.get('type')))
        complextypes_dict[complextype.get('name')] = innertypes
    return complextypes_dict


def read_scan_records(msscan_path, complextypes_dict):
    """
    Reads every scan record (ScanRecordType) from MSScan.bin until EOF.

    The records are contiguous and the file ends exactly on a record
    boundary, so reading until EOF yields one record per retention time.
    The length of the returned list is therefore the scan count, which was
    historically read from MSTS.xml. Recovering it here removes that
    dependency, so result folders that omit MSTS.xml (Agilent OpenLab
    .rslt/.sirslt) can be parsed.

    The exact members of each record depend on the instrument's MSScan.xsd;
    callers extract whichever fields they need (e.g. parse_msdata pulls the
    MSProfile.bin offsets and byte counts).

    Args:
        msscan_path (str): Path to MSScan.bin.
        complextypes_dict (dict): Output of :obj:`parse_scan_xsd`.

    Returns:
        List of dictionaries, one per retention time, each mapping the
        ScanRecordType member names to their parsed values.

    """
    file_size = os.path.getsize(msscan_path)
    records = []
    with open(msscan_path, 'rb') as f:
        f.seek(0x58)  # offset to the uint32 pointer at the start of records
        f.seek(struct.unpack('<I', f.read(4))[0])
        while f.tell() < file_size:
            # "ScanRecordType" is always the name of the root "complex" type.
            records.append(
                read_complextype(f, complextypes_dict, "ScanRecordType"))
    return records


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
    return read_complextype(f, complextype_dict, name)