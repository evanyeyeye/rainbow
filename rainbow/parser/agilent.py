import os 
import struct
from collections import deque
import numpy as np
from datadirectory import DataDirectory 
from datafile import DataFile 


def parse_directory(dirpath):
    """
    Parses an Agilent .D data directory. 

    It tries to parse all files in the directory with a .ch, .uv, or .ms extension.

    Each successfully parsed file is stored as a DataFile, which are all added to a DataDirectory. 
    
    Args:
        dirpath (str): Path to the Agilent data directory. 

    Returns:
        DataDirectory representing the directory. It contains each valid data file as a DataFile. 

    """
    detector_to_files = {} 

    valid_exts = {'.ch', '.uv', '.ms'}
    for file in os.listdir(dirpath):
        ext = os.path.splitext(file)[1].lower()
        if ext not in valid_exts:
            continue 
        datafile = parse_file(os.path.join(dirpath, file))
        if not datafile:
            continue 
        detector = datafile.detector
        if detector in detector_to_files:
            detector_to_files[detector].append(datafile)
        else: 
            detector_to_files[detector] = [datafile]

    return DataDirectory(dirpath, detector_to_files)

def parse_file(filepath):
    """
    Parses an Agilent data file. Supported extensions are .ch, .uv, and .ms. 

    It calls the appropriate subroutine based on the file extension. 

    Args:
        filepath (str): Path to the Agilent data file.
    
    Returns:
        DataFile representing the file, if it can be parsed. Otherwise, None. 

    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.ch':
        return parse_ch(filepath)
    elif ext == '.uv':
        return parse_uv(filepath)
    elif ext == '.ms':
        return parse_ms(filepath)

    return None

def parse_ch(filepath):
    """
    Parses Agilent .ch files. 

    There are different file structures for .ch files containing UV versus FID data. 

    This method determines which type of data the file contains using the file header, and calls the appropriate subroutine. 

    Args: 
        filepath (str): Path to the Agilent .ch file.
    
    Returns:
        DataFile representing the file, if it can be parsed. Otherwise, None.

    """
    f = open(filepath, 'rb')
    head = struct.unpack('>I', f.read(4))[0]
    f.close()

    if head == 0x03313330:
        return _parse_ch_uv(filepath)
    elif head == 0x03313739:
        return _parse_ch_fid(filepath)
    return None

def _parse_ch_uv(filepath):
    """
    Parses Agilent .ch files containing UV data. It should not be called directly. Use parse_ch instead.  

    The entire file must be read to determine the total number of retention times (x-axis labels). But using a numpy array (with a fixed size of that number) would require reading the file a second time. It is faster to append elements to a python list than to read the file twice. This method uses a deque instead of a list, which is even faster.

    Since the intervals between retention times are known to be constant, the first retention time and last retention time are extracted from the file header and used to calculate every retention time.

    The wavelength (y-axis label) is extracted from the file header. 

    More information about this file structure can be found :ref:`here <agilent_uv_ch>`.

    Args:
        filepath (str): Path to the Agilent .ch file with UV data. 

    Returns:
        DataFile representing the file. 

    """
    data_offsets = {
        'time': 0x11A,
        'body': 0x1800
    }

    f = open(filepath, 'rb')
    
    # Extract data values.
    f.seek(data_offsets['body'])
    
    data_array = deque()
    num_data_points = 0
    accum = 0
    while True:
        # Read in header information.
        head = struct.unpack('>B', f.read(1))[0] 
        seg_num_data_points = struct.unpack('>B', f.read(1))[0] 
        num_data_points += seg_num_data_points
        if head != 0x10:
            break

        # If next value is a delta, add it to the last integer value (accumulating).
        for _ in range(seg_num_data_points):
            check_val = struct.unpack('>h', f.read(2))[0]
            if check_val == -0x8000:
                accum = struct.unpack('>i', f.read(4))[0]
            else: accum += check_val
            data_array.append(accum)

    # Calculate the x-axis labels (retention time). 
    f.seek(data_offsets['time'])
    start_time, end_time = struct.unpack('>II', f.read(8))
    delta_time = (end_time - start_time) // (num_data_points - 1)
    times = np.arange(start_time, end_time + 1, delta_time)

    # Extract the y-axis label (signal).
    signal_str = _read_string(f, 0x1075, 2)
    signal = int(signal_str.split("Sig=")[1].split('.')[0])

    # Extract metadata
    metadata_offsets = {
        'notebook': 0x35A, 
        'date': 0x957, 
        'method': 0xA0E, 
        'instrument': 0xC11, 
        'unit':  0x104C, 
        'signal': 0x1075 
    }
    xlabels = times
    ylabels = np.array([signal])
    data = np.array([data_array]).transpose()
    metadata = _extract_metadata(f, metadata_offsets, 2)
    
    f.close()

    return DataFile(filepath, 'UV', xlabels, ylabels, data, metadata)

def _parse_ch_fid(filepath):
    """
    Parses Agilent .ch files containing FID data. It should not be called directly. Use parse_ch instead.  

    The intervals between retention times (x-axis labels) are known to be constant, so the number of data points, first retention time, and last retention time are extracted from the file header and used to calculate every retention time. 

    Since the data values are stored in ascending order with respect to time, they are assigned to their corresponding retention times based on their order in the file.  

    More information about this file structure can be found :ref:`here <agilent_fid>`.

    Args:
        filepath (str): Path to the Agilent .ch file with FID data. 

    Returns:
        DataFile representing the file. 

    """
    data_offsets = {
        'count': 0x116,
        'body': 0x1800
    }
    
    f = open(filepath, 'rb')

    f.seek(data_offsets['count'])
    num_data_points = struct.unpack(">I", f.read(4))[0]
    
    start_time = int(struct.unpack(">f", f.read(4))[0])
    end_time = int(struct.unpack(">f", f.read(4))[0])
    delta_time = (end_time - start_time) // (num_data_points - 1)
    times = np.arange(start_time, end_time + 1, delta_time)

    # Extract data values.
    f.seek(data_offsets['body'])

    data_array = np.empty((num_data_points, 1), dtype=int)
    for i in range(num_data_points):
        data_array[i, 0] = struct.unpack("<d", f.read(8))[0]

    # Extract metadata
    metadata_offsets = {
        'notebook': 0x35A, 
        'date': 0x957, 
        'method': 0xA0E, 
        'instrument': 0xC11, 
        'unit':  0x104C, 
        'signal': 0x1075 
    }

    xlabels = times
    ylabels = np.array(['TIC'])
    data = data_array
    metadata = _extract_metadata(f, metadata_offsets, 2)

    f.close()

    return DataFile(filepath, 'FID', xlabels, ylabels, data, metadata)

def parse_uv(filepath):
    """
    Parses Agilent .uv files.

    More information about this file structure can be found :ref:`here <agilent_uv_uv>`.

    Args:
        filepath (str): Path to file. 
    
    Returns:
        DataFile representing the file, if it can be parsed. Otherwise, None.

    """
    f = open(filepath, 'rb')
    head = struct.unpack('>I', f.read(4))[0]

    if head != 0x03313331:
        return None
    
    data_offsets = {
        "number of data points": 0x116,
        "start of data body": 0x1000
    }

    # Sets the total number of x-axis values (or rows) for the array.
    f.seek(data_offsets["number of data points"])
    num_data_points = struct.unpack(">i", f.read(4))[0]

    times = np.zeros(num_data_points, np.uint64)

    # Get the number of wavelengths using the header for the first data segment.
    f.seek(data_offsets["start of data body"] + 8)
    wavelength_range = tuple(num // 20 for num in struct.unpack("<HHH", f.read(6)))
    
    wavelengths = np.arange(wavelength_range[0], wavelength_range[1] + 1, wavelength_range[2])
    num_wavelengths = wavelengths.size

    # Extract absorbance data from each data segment.
    absorbances = np.zeros((num_data_points, num_wavelengths), np.int64)
    f.seek(data_offsets["start of data body"])
    for i in range(num_data_points):
        # Read in header information.
        f.read(4)
        times[i] = struct.unpack("<I", f.read(4))[0]
        f.read(14)
    
        # If next value is a delta, add it to the last integer value (accumulating).
        accum = 0 
        for j in range(num_wavelengths):
            check_val = struct.unpack('<h', f.read(2))[0]
            if check_val == -0x8000:
                accum = struct.unpack('<i', f.read(4))[0]
            else: accum += check_val
            absorbances[i, j] = accum

    # Extract metadata
    metadata_offsets = {
        "notebook": 0x35A,
        "date": 0x957,
        "method": 0xA0E,
        "unit": 0xC15,
        "datatype": 0xC40,
        "position": 0xFD7
    }

    xlabels = times 
    ylabels = [wavelengths]
    data = absorbances
    metadata = _extract_metadata(f, metadata_offsets, 2)

    f.close()

    return DataFile(filepath, 'UV', xlabels, ylabels, data, metadata)

def parse_ms(filepath):   
    """
    Parses Agilent .ms files.

    The type of .ms file is determined using the descriptive string at the start of the file. 

    Because the data segments for each retention time (x-axis label) contain data values for an arbitrary set of masses, the entire file must be read to determine the whole list of unique masses. To avoid rereading the file, the data is saved in a numpy matrix named memo as (mass, count) tuples.

    It turns out that checking membership in a python set is significantly faster than reading a value from a 2D numpy matrix. Accordingly, this method uses a set to populate the data array which increases speed by more than 3x.  

    More information about this file structure can be found :ref:`here <agilent_ms>`.

    Args:
        filepath (str): Path to file. 
    
    Returns:
        DataFile representing the file, if it can be parsed. Otherwise, None.

    """

    f = open(filepath, 'rb')
    head = struct.unpack('>I', f.read(4))[0]

    if head != 0x01320000:
        return None

    data_offsets = {
        'type': 0x4,
        'start': 0x10A,
        'count1': 0x118,
        'count2': 0x142
    }

    # Check the type of .ms file. 
    type_ms = _read_string(f, data_offsets['type'], 1)

    if type_ms == "MSD Spectral File":
        f.seek(data_offsets['count1'])
        num_rows = struct.unpack('>H', f.read(2))[0]
    else: 
        f.seek(data_offsets['count2'])
        num_rows = struct.unpack('<H', f.read(2))[0]
    
    # Go to start of data body. 
    f.seek(data_offsets['start'])
    f.seek(struct.unpack('>H', f.read(2))[0] * 2)

    # Extract data values.
    times = np.empty(num_rows, dtype=int)
    memo = np.empty(num_rows, dtype=object)
    masses_set = set()
    for i in range(num_rows):
        # Read in header information.
        times[i] = struct.unpack('>I', f.read(4))[0]
        f.read(6)
        num_masses = struct.unpack('>H', f.read(2))[0]
        f.read(4)

        # Process the data values. 
        data = struct.unpack('>' + num_masses * 'HH', f.read(num_masses * 4))
        masses = (np.array(data[::2]) + 10) // 20
        masses_set.update(masses)

        counts_enc = np.array(data[1::2])
        counts_head = counts_enc >> 14
        counts_tail = counts_enc & 0x3fff
        counts = (8 ** counts_head) * counts_tail

        memo[i] = (masses, counts)
        f.read(12)
        
    masses_array = np.array(sorted(masses_set))
    mass_indices = dict(zip(masses_array, range(masses_array.size)))

    data_array = np.zeros((num_rows, masses_array.size), dtype=int)
    for i in range(num_rows):
        masses, counts = memo[i]
        visited = set()
        for j in range(masses.size):
            if masses[j] in visited:
                data_array[i, mass_indices[masses[j]]] += counts[j]
            else:
                data_array[i, mass_indices[masses[j]]] = counts[j]
                visited.add(masses[j])

    # Extract metadata.
    metadata_offsets = {
        'time': 0xB2,
        'method': 0xE4
    }

    xlabels = times 
    ylabels = masses_array 
    data = data_array 
    metadata = _extract_metadata(f, metadata_offsets, 1)

    f.close()

    return DataFile(filepath, 'MS', xlabels, ylabels, data, metadata)

def _extract_metadata(f, offsets, gap):
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
        string = _read_string(f, offset, gap)
        if string:
            metadata[key] = string
    return metadata
    
def _read_string(f, offset, gap):
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
    return f.read(str_len)[::gap].decode()