import os 
import struct
from collections import deque
import numpy as np
from lxml import etree
from rainbow.datafile import DataFile
from rainbow.datadirectory import DataDirectory


"""
MAIN PARSING METHODS

"""

def parse_allfiles(path, prec=0):
    """
    Finds and parses Agilent Chemstation data files with a .ch, .uv, or .ms extension.

    Each successfully parsed file is stored as a DataFile.
    
    Args:
        path (str): Path to the Agilent .D data directory. 

    Returns:
        List containing a DataFile for each parsed data file. 

    """
    datafiles = []
    for file in os.listdir(path):
        datafile = parse_file(os.path.join(path, file), prec)
        if datafile:
            datafiles.append(datafile)
    return datafiles

def parse_file(path, prec=0):
    """
    Parses an Agilent Chemstation data file. Supported extensions are .ch, .uv, and .ms. 

    Calls the appropriate subroutine based on the file extension. 

    Args:
        path (str): Path to the Agilent data file.
    
    Returns:
        DataFile representing the file, if it can be parsed. Otherwise, None. 

    """
    ext = os.path.splitext(path)[1].lower()
    if ext == '.ch':
        return parse_ch(path)
    elif ext == '.uv':
        return parse_uv(path)
    elif ext == '.ms':
        return parse_ms(path, prec)
    return None


"""
.ch PARSING METHODS

"""

def parse_ch(path):
    """
    Parses Agilent .ch files. 

    The .ch files containing FID data have a different file structure than other .ch files.

    This method determines the type of the .ch file using the file header, and calls the appropriate subroutine. 

    Args: 
        path (str): Path to the Agilent .ch file.
    
    Returns:
        DataFile representing the file, if it can be parsed. Otherwise, None.

    """
    f = open(path, 'rb')
    head = struct.unpack('>I', f.read(4))[0]
    f.close()

    if head == 0x03313739:
        return parse_ch_fid(path)
    elif head == 0x03313330:
        return parse_ch_other(path)
    return None

def parse_ch_fid(path):
    """
    Parses Agilent .ch files containing FID data. This method should not be called directly. Use parse_ch instead.

    The intervals between retention times (x-axis labels) are known to be constant, so the number of data points, first retention time, and last retention time are extracted from the file header and used to calculate every retention time. 

    Since the data values are stored in ascending order with respect to time, they are assigned to their corresponding retention times based on their order in the file.  

    More information about this file structure can be found :ref:`here <agilent_fid>`.

    Args:
        path (str): Path to the Agilent .ch file with FID data. 

    Returns:
        DataFile representing the file, if it can be parsed. Otherwise, None.

    """
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
        'unit':  0x104C, 
        'signal': 0x1075 
    }
    
    f = open(path, 'rb')
    raw_bytes = f.read()

    # Extract the number of retention times.
    f.seek(data_offsets['num_times'])
    num_times = struct.unpack(">I", f.read(4))[0]
    if num_times == 0:
        return None
    
    # Calculate all retention times using the start and end times. 
    start_time = struct.unpack(">f", f.read(4))[0]
    end_time = struct.unpack(">f", f.read(4))[0]
    delta_time = (end_time - start_time) / (num_times - 1)
    times = np.arange(start_time, end_time + 1e-3, delta_time)
    assert (times.size == num_times)

    # Extract the raw data values.
    raw_matrix = np.ndarray(
        num_times, '<d', raw_bytes, data_offsets['data_start'], 8)
    raw_matrix = raw_matrix.copy().reshape(-1, 1)
    assert(raw_matrix.shape == (num_times, 1))

    # Extract the scaling factor. 
    f.seek(data_offsets['scaling_factor'])
    scaling_factor = struct.unpack('>d', f.read(8))[0]

    # Report time in minutes. 
    xlabels = times / 60000
    # No ylabel for FID data. 
    ylabels = np.array([''])
    # Apply scaling factor to raw values to get the real data.  
    data = scaling_factor * raw_matrix
    # Extract metadata from file header.
    metadata = read_header(f, metadata_offsets)

    f.close()

    return DataFile(path, 'FID', xlabels, ylabels, data, metadata)

def parse_ch_other(path):
    """
    Parses Agilent .ch files containing UV, CAD, or ELSD data. This method should not be called directly. Use parse_ch instead.  

    The entire file must be read to determine the total number of retention times (x-axis labels). But using a numpy array (with a fixed size of that number) would require reading the file a second time. It is faster to append elements to a python list than to read the file twice. This method uses a deque instead of a list, which is even faster.

    Since the intervals between retention times are known to be constant, the first retention time and last retention time are extracted from the file header and used to calculate every retention time.

    The wavelength (y-axis label) is extracted from the file header. 

    More information about this file structure can be found :ref:`here <agilent_uv_ch>`.

    Args:
        path (str): Path to the Agilent .ch file with UV, CAD, or ELSD data. 

    Returns:
        DataFile representing the file. 

    """
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
        'unit':  0x104C, 
        'signal': 0x1075 
    }

    f = open(path, 'rb')
    
    # Extract the raw data values.
    # Count the total number of retention times. 
    f.seek(data_offsets['data_start'])
    raw_array = deque()
    num_times = 0
    accum_absorbance = 0
    while True:
        # Parse segment header for the number of retention times.
        # If the segment header is invalid, stop reading.  
        head = struct.unpack('>B', f.read(1))[0] 
        seg_num_times = struct.unpack('>B', f.read(1))[0] 
        num_times += seg_num_times
        if head != 0x10:
            break
        # If the next value is an integer, reset the accumulator to that value.
        # Otherwise it is a delta, so add it to the accumulator. 
        for _ in range(seg_num_times):
            check_int = struct.unpack('>h', f.read(2))[0]
            if check_int == -0x8000:
                accum_absorbance = struct.unpack('>i', f.read(4))[0]
            else: 
                accum_absorbance += check_int
            raw_array.append(accum_absorbance)
    assert(f.tell() == os.path.getsize(path))

    if num_times == 0:
        return None

    # Calculate all retention times using the start and end times.
    f.seek(data_offsets['time_range'])
    start_time, end_time = struct.unpack('>II', f.read(8))
    delta_time = (end_time - start_time) / (num_times - 1)
    times = np.arange(start_time, end_time + 1e-3, delta_time)

    # Extract metadata from file header.
    metadata = read_header(f, metadata_offsets)
    assert('unit' not in metadata or metadata['unit'] in {'mAU', 'mAu'})

    # Determine the detector and signal using the metadata. 
    signal_str = metadata['signal']
    if '=' in signal_str:
        signal = int(float(signal_str.split('=')[1].split(',')[0]))
        detector = 'UV'
    elif 'ADC' in signal_str:
        signal = ''
        if 'CHANNEL' in signal_str:
            detector = 'ELSD'
        else:
            detector = 'CAD'
    assert('=' in signal_str or 'ADC' in signal_str)

    # Extract the scaling factor.
    f.seek(data_offsets['scaling_factor'])
    scaling_factor = struct.unpack('>d', f.read(8))[0]

    # Report time in minutes. 
    xlabels = times / 60000
    # No ylabel for CAD or ELSD data. 
    ylabels = np.array([signal])
    # Apply scaling factor to raw values to get the real data.  
    data = scaling_factor * np.array([raw_array]).transpose()

    f.close()

    return DataFile(path, detector, xlabels, ylabels, data, metadata)


"""
.uv PARSING METHODS

"""

def parse_uv(path):
    """
    Parses Agilent .uv files.

    More information about this file structure can be found :ref:`here <agilent_uv_uv>`.

    Args:
        path (str): Path to the Agilent .uv file. 
    
    Returns:
        DataFile representing the file, if it can be parsed. Otherwise, None.

    """
    data_offsets = {
        'num_times': 0x116,
        'scaling_factor': 0xC0D,
        'data_start': 0x1000
    }
    metadata_offsets = {
        "notebook": 0x35A,
        "date": 0x957,
        "method": 0xA0E,
        "unit": 0xC15,
        "signal": 0xC40,
        "vialpos": 0xFD7
    }

    f = open(path, 'rb')

    # Validate file header. 
    head = struct.unpack('>I', f.read(4))[0]
    if head != 0x03313331:
        f.close()
        return None

    # Extract the number of retention times.
    f.seek(data_offsets["num_times"])
    num_times = struct.unpack(">I", f.read(4))[0]
    # If there are none, the file may be a partial. 
    if not num_times:
        f.close()
        return parse_uv_partial(path)

    # Calculate all the wavelengths using the range from the first data segment header.
    f.seek(data_offsets["data_start"] + 0x8)
    start_wv, end_wv, delta_wv = tuple(num // 20 for num in struct.unpack("<HHH", f.read(6)))
    wavelengths = np.arange(start_wv, end_wv + 1, delta_wv)
    num_wavelengths = wavelengths.size

    uint_unpack = struct.Struct('<I').unpack 
    int_unpack = struct.Struct('<i').unpack 
    short_unpack = struct.Struct('<h').unpack

    # Extract the retention times and raw data values from each data segment.
    f.seek(data_offsets["data_start"])
    times = np.empty(num_times, np.uint32)
    raw_matrix = np.empty((num_times, num_wavelengths), np.int32)
    for i in range(num_times):
        # Parse segment header for the retention time.
        f.read(4)
        times[i] = uint_unpack(f.read(4))[0]
        f.read(14)
        # If the next value is an integer, reset the accumulator to that value.
        # Otherwise it is a delta, so add it to the accumulator.
        accum_absorbance = 0 
        for j in range(num_wavelengths):
            check_int = short_unpack(f.read(2))[0]
            if check_int == -0x8000:
                accum_absorbance = int_unpack(f.read(4))[0]
            else: 
                accum_absorbance += check_int
            raw_matrix[i, j] = accum_absorbance
    end_offset = f.tell()
    f.seek(0x104)
    assert(end_offset == struct.unpack('>I', f.read(4))[0])

    # Extract the scaling factor.
    f.seek(data_offsets['scaling_factor'])
    scaling_factor = struct.unpack('>d', f.read(8))[0]

    # Report time in minutes. 
    xlabels = times / 60000
    # For UV spectrum data, the ylabels are the wavelengths. 
    ylabels = wavelengths
    # Apply scaling factor to raw values to get the real data.  
    data = scaling_factor * raw_matrix
    # Extract metadata from file header.
    metadata = read_header(f, metadata_offsets)

    f.close()

    return DataFile(path, 'UV', xlabels, ylabels, data, metadata)

def parse_uv_partial(path):
    """
    A
    """
    data_offsets = {
        'num_times': 0x116,
        'scaling_factor': 0xC0D,
        'data_start': 0x1000
    }
    metadata_offsets = {
        "notebook": 0x35A,
        "date": 0x957,
        "method": 0xA0E,
        "unit": 0xC15,
        "signal": 0xC40,
        "vialpos": 0xFD7
    }

    f = open(path, 'rb')

    # Calculate all the wavelengths using the range from the first data segment header.
    # If there is no data, then it is not a valid partial file. 
    try:
        f.seek(data_offsets["data_start"] + 0x8)
        start_wv, end_wv, delta_wv = tuple(num // 20 for num in struct.unpack("<HHH", f.read(6)))
        wavelengths = np.arange(start_wv, end_wv + 1, delta_wv)
        num_wavelengths = wavelengths.size
    except struct.error:
        return None

    uint_unpack = struct.Struct('<I').unpack 
    int_unpack = struct.Struct('<i').unpack 
    short_unpack = struct.Struct('<h').unpack

    # Extract the retention times and raw data values from each data segment.
    f.seek(data_offsets['data_start'])
    memo = []
    while True:
        try:
            # Parse segment header for the retention time.
            f.read(4)
            time = uint_unpack(f.read(4))[0]
            f.read(14)
            # If the next value is an integer, reset the accumulator to that value.
            # Otherwise it is a delta, so add it to the accumulator.
            raw_vals = np.empty(num_wavelengths, dtype=np.int32)
            accum_absorbance = 0 
            for j in range(num_wavelengths):
                check_int = short_unpack(f.read(2))[0]
                if check_int == -0x8000:
                    accum_absorbance = int_unpack(f.read(4))[0]
                else: 
                    accum_absorbance += check_int
                raw_vals[j] = accum_absorbance
            memo.append((time, raw_vals))
        except struct.error:
            break
    assert(f.tell() == os.path.getsize(path))

    # Organize the data using the number of retention times.
    num_times = len(memo)
    times = np.empty(num_times, dtype=np.uint32)
    raw_matrix = np.empty((num_times, num_wavelengths), dtype=np.int32)
    for i in range(num_times):
        time, raw_vals = memo[i]
        times[i] = time
        raw_matrix[i] = raw_vals

    # Extract the scaling factor.
    f.seek(data_offsets['scaling_factor'])
    scaling_factor = struct.unpack('>d', f.read(8))[0]

    # Report time in minutes. 
    xlabels = times / 60000
    # For UV spectrum data, the ylabels are the wavelengths. 
    ylabels = wavelengths
    # Apply scaling factor to raw values to get the real data.  
    data = scaling_factor * raw_matrix
    # Extract metadata from file header.
    metadata = read_header(f, metadata_offsets)

    f.close()

    return DataFile(path, 'UV', xlabels, ylabels, data, metadata)


"""
.ms PARSING METHODS

"""

def parse_ms(path, prec=0):   
    """
    Parses Agilent .ms files.

    The type of .ms file is determined using the descriptive string at the start of the file. 

    Because the data segments for each retention time (x-axis label) contain data values for an arbitrary set of masses, the entire file must be read to determine the whole list of unique masses. To avoid rereading the file, the data is saved in a numpy matrix named memo as (mass, count) tuples.

    It turns out that checking membership in a python set is significantly faster than reading a value from a 2D numpy matrix. Accordingly, this method uses a set to populate the data array which increases speed by more than 3x.  

    More information about this file structure can be found :ref:`here <agilent_ms>`.

    Args:
        path (str): Path to Agilent .ms file. 
    
    Returns:
        DataFile representing the file, if it can be parsed. Otherwise, None.

    """
    data_offsets = {
        'type': 0x4,
        'data_start_pos': 0x10A,
        'lc_num_times': 0x116,
        'gc_num_times': 0x142
    }
    metadata_offsets = {
        'date': 0xB2,
        'method': 0xE4
    }

    f = open(path, 'rb')

    # Validate file header.
    # If invalid, the file may be a partial.
    head = struct.unpack('>I', f.read(4))[0]
    if head != 0x01320000:
        f.close()
        return parse_ms_partial(path, prec)

    # Determine the type of .ms file based on header.
    # Read the number of retention times differently based on type.
    type_ms = read_string(f, data_offsets['type'], 1)
    if type_ms == "MSD Spectral File":
        f.seek(data_offsets['lc_num_times'])
        num_times = struct.unpack('>I', f.read(4))[0]
    else: 
        f.seek(data_offsets['gc_num_times'])
        num_times = struct.unpack('<I', f.read(4))[0]
    
    # Find the starting offset for the data.  
    f.seek(data_offsets['data_start_pos'])
    f.seek(struct.unpack('>H', f.read(2))[0] * 2 - 2)
    assert(type_ms != "MSD Spectral File" or f.tell() == 754)

    short_unpack = struct.Struct('>H').unpack
    int_unpack = struct.Struct('>I').unpack
    # Extract data values.

    byte_arr = bytearray()
    times = np.empty(num_times, dtype=np.uint32)
    masses_per_time = np.zeros(num_times, dtype=np.uint16)

    for i in range(num_times):
        # Read in header information.
        cur = f.tell()
        length = short_unpack(f.read(2))[0] * 2
        # f.read(2)
        times[i] = int_unpack(f.read(4))[0]
        f.read(6)
        masses_per_time[i] = short_unpack(f.read(2))[0]
        f.read(4)
        byte_arr.extend(f.read(masses_per_time[i] * 4))

        f.read(10)
        assert(cur + length == f.tell())

    total_masses = np.sum(masses_per_time)
    the_bytes = bytes(byte_arr)
    # print(type(the_bytes))
    masses = np.ndarray(total_masses, '>H', the_bytes, 0, 4).copy()
    masses = np.round(masses / 20, prec)
    
    counts_enc = np.ndarray(total_masses, '>H', the_bytes, 2, 4).copy()
    counts_head = counts_enc >> 14
    counts_tail = counts_enc & 0x3fff
    counts = np.multiply(8 ** counts_head, counts_tail, dtype=np.uint32)

    masses_array = np.unique(masses)
    masses_array.sort()

    # Optimized using numpy vectorization.
    key_indices = np.searchsorted(masses_array, masses)
    data = np.zeros((num_times, masses_array.size), dtype=np.int64)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + masses_per_time[i]
        np.add.at(
            data[i], 
            key_indices[cur_index:stop_index], 
            counts[cur_index:stop_index])
        cur_index = stop_index
    # del key_indices, keys, values, ylabels_per_time

    # print(path, hex(f.tell()))

    xlabels = times / 60000
    metadata = read_header(f, metadata_offsets, 1)

    f.close()

    return DataFile(path, 'MS', xlabels, masses_array, data, metadata)

def parse_ms_partial(path, prec=0):
    """
    A
    """
    f = open(path, 'rb')
    f.seek(0x10A)
    if struct.unpack('>H', f.read(2))[0] != 0:
        print(path)
        f.close()
        return None

    
    short_unpack = struct.Struct('>H').unpack
    int_unpack = struct.Struct('>I').unpack

    f.seek(754)

    byte_arr = bytearray()
    times = []
    masses_per_time = []

    while True:
        try:
            cur = f.tell()
            length = short_unpack(f.read(2))[0] * 2
            times.append(int_unpack(f.read(4))[0])
            f.read(6)
            masses_per_time.append(short_unpack(f.read(2))[0])
            f.read(4)
            byte_arr.extend(f.read(masses_per_time[-1] * 4))
            f.read(10)
            assert(cur + length == f.tell())
        except struct.error:
            break

    num_times = len(times)
    times = np.array(times)
    masses_per_time = np.array(masses_per_time)

    total_masses = np.sum(masses_per_time)
    the_bytes = bytes(byte_arr)
    # print(type(the_bytes))
    masses = np.ndarray(total_masses, '>H', the_bytes, 0, 4).copy()
    masses = np.round(masses / 20, prec)
    
    counts_enc = np.ndarray(total_masses, '>H', the_bytes, 2, 4).copy()
    counts_head = counts_enc >> 14
    counts_tail = counts_enc & 0x3fff
    counts = np.multiply(8 ** counts_head, counts_tail, dtype=np.uint32)

    masses_array = np.unique(masses)
    masses_array.sort()

    # Optimized using numpy vectorization.
    key_indices = np.searchsorted(masses_array, masses)
    data = np.zeros((num_times, masses_array.size), dtype=np.int64)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + masses_per_time[i]
        np.add.at(
            data[i], 
            key_indices[cur_index:stop_index], 
            counts[cur_index:stop_index])
        cur_index = stop_index
    # del key_indices, keys, values, ylabels_per_time

    
    metadata_offsets = {
        'date': 0xB2,
        'method': 0xE4
    }

    xlabels = times / 60000
    metadata = read_header(f, metadata_offsets, 1)

    f.close()

    return DataFile(path, 'MS', xlabels, masses_array, data, metadata)


""" 
METADATA PARSING METHODS

"""

def read_header(f, offsets, gap=2):
    """
    Extracts metadata from the header of an Agilent data file. 

    Args:
        f (_io.BufferedReader): File opened in 'rb' mode.
        offsets (dict): Dictionary mapping properties to file offsets. 
        gap (int): Distance between two adjacent characters.

    Returns:
        Dictionary containing metadata as string key-value pairs. 

    """
    metadata = {}
    for key, offset in offsets.items():
        string = read_string(f, offset, gap)
        if string:
            metadata[key] = string
    return metadata

def read_string(f, offset, gap=2):
    """
    Extracts a string from the specified offset.

    This method is primarily useful for retrieving metadata. 

    Args:
        f (_io.BufferedReader): File opened in 'rb' mode. 
        offset (int): Offset to begin reading from. 
        gap (int): Distance between two adjacent characters.
    
    Returns:
        String at the specified offset in the file header. 

    """
    f.seek(offset)
    str_len = struct.unpack("<B", f.read(1))[0] * gap
    try:
        return f.read(str_len)[::gap].decode()
    except:
        return ""

def parse_metadata(path, datafiles):
    """
    Parses Agilent metadata at the directory level.

    Since metadata is also stored in Agilent files, the parsed DataFiles \
        are first checked for date and vial position metadata. 

    Then, several possible files are scanned for the vial position. \
        This method can look inside the AcqData directory, which may be \
        misleading because this is the Chemstation module.  

    Args:
        path (str): Path to the directory.
        datafiles (list): List of DataFile objects.  
    
    Returns:
        Dictionary containing directory metadata. 

    """
    metadata = {}
    metadata['vendor'] = "Agilent"

    # Scan each DataFile for the date and vial position. 
    for datafile in datafiles:
        if 'date' not in metadata and 'date' in datafile.metadata:
            metadata['date'] = datafile.metadata['date']
        if 'vialpos' not in metadata and 'vialpos' in datafile.metadata:
            metadata['vialpos'] = datafile.metadata['vialpos']
    if 'date' in metadata and 'vialpos' in metadata:
        print("FROM DATAFILES")
        return metadata

    # Scan certain files for the vial position. 

    dircontents = set(os.listdir(path))

    # sequence.acam_
    if "sequence.acam_" in dircontents:
        tree = etree.parse(os.path.join(path, "sequence.acam_"))
        root = tree.getroot()
        for vialnum in root.xpath("//*[local-name()='VialNumber']"):
            if vialnum.text:
                metadata['vialpos'] = vialnum.text
                print("FROM SEQUENCE")
                return metadata
    else: assert(all(n.lower() != "sequence.acam_" for n in dircontents))

    # sample.acaml
    if "sample.acaml" in dircontents:
        tree = etree.parse(os.path.join(path, "sample.acaml"))
        root = tree.getroot()
        for vialnum in root.xpath("//*[local-name()='VialNumber']"):
            if vialnum.text:
                metadata['vialpos'] = vialnum.text
                print("FROM SAMPLE")
                return metadata
    else: assert(all(n.lower() != "sample.acaml" for n in dircontents))

    # AcqData/sample_info.xml
    if "AcqData" in dircontents:
        acqdata_path = os.path.join(path, "AcqData")
        if "sample_info.xml" in os.listdir(acqdata_path):
            tree = etree.parse(os.path.join(acqdata_path, "sample_info.xml"))
            root = tree.getroot()
            for samplefield in root.xpath('//Field[Name="Sample Position"]'):
                vialnum = samplefield.find("Value")
                if vialnum is not None and len(vialnum.text.split()) == 1:
                    metadata['vialpos'] = vialnum.text
                    print("FROM SAMPLE_INFO")
                    return metadata
        else: assert(all(n.lower() != "sample_info.xml" for n in os.listdir(acqdata_path)))

    # runstart.txt 
    if "runstart.txt" in dircontents:
        f = open(os.path.join(path, "runstart.txt"))
        lines = f.read().splitlines()
        f.close()
        for line in lines:
            stripped = line.strip()
            if "Alsbottle" in stripped:
                assert(int(stripped.split(" ")[-1]) != 0)
                metadata['vialpos'] = stripped.split(" ")[-1]
                print("FROM RUNSTART")
                return metadata
    else: assert(all(n.lower() != "runstart.txt" for n in dircontents))

    # RUN.LOG
    if "RUN.LOG" in dircontents:
        f = open(os.path.join(path, "RUN.LOG"), 'rb')
        plaintext = f.read().decode('ascii', 'ignore').replace("\x00", "")
        f.close()
        for line in plaintext.splitlines():
            if "Method started" in line:
                split = line.split()
                try:
                    metadata['vialpos'] = split[split.index("vial#") + 1]
                    print("FROM RUNLOG")
                    return metadata
                except:
                    pass
                try:
                    metadata['vialpos'] = \
                        split[split.index("location") + 1][1:-1]
                    print("FROM RUNLOG")
                    return metadata
                except: 
                    pass
            elif "Instrument running sample" in line:
                split = line.split()
                print("FROM RUNLOG")
                try:
                    metadata['vialpos'] = split[split.index("Vial") + 1]
                    print("FROM RUNLOG")
                    return metadata
                except:
                    pass
                try:
                    metadata['vialpos'] = split[split.index("sample") + 1]
                    print("FROM RUNLOG")
                    return metadata
                except: 
                    pass
    else: assert(all(n.upper() != "RUN.LOG" for n in dircontents))
    
    return metadata