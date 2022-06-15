import os
import struct
from collections import deque
import numpy as np
import matplotlib.pyplot as plt
from rainbow.parser import chromatogram

# TODO: Save extra data from UV and MS folders.
class Agilent(chromatogram.Chromatogram):
    """ 
    Class representing an Agilent data folder (.D).

    Upon instantiation with a directory path, this class automatically detects and parses .ch, .ms, and .uv data files. 

    There are 3 detector types currently supported: 'UV', 'FID', and 'MS'.

    """
    def __init__(self, dirpath):
        
        super().__init__(dirpath)

        detector_funcs = {
            'UV':  self.parse_uv,
            'FID': self.parse_fid,
            'MS': self.parse_ms
        }

        for detector in detector_funcs:
            filepath = self.find_file(dirpath, detector)
            if filepath is not None:
                self.detectors.append(detector)
                detector_funcs[detector](filepath)

    def parse_uv(self, filepath):
        """
        Function that parses .ch files containing UV data.

        Args:
            filepath (str): Path to file. 

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
        signal_str = self.read_string(f, 0x1075, 2)
        signal = int(signal_str.split("Sig=")[1].split('.')[0])

        self.xlabels['UV'] = times
        self.ylabels['UV'] = np.array([signal])
        self.data['UV'] = np.array([data_array]).transpose()
        
        # Extract metadata
        metadata_offsets = {
            'notebook': 0x35A, 
            'date': 0x957, 
            'method': 0xA0E, 
            'instrument': 0xC11, 
            'unit':  0x104C, 
            'signal': 0x1075 
        }

        self.metadata['UV'] = self.extract_metadata(f, metadata_offsets, 2)
        
        f.close()
    
    def parse_fid(self, filepath):
        """
        Function that parses .ch files containing FID data.

        The intervals between x-axis times are known to be constant, so the number of data points, first x-axis time, and last x-axis time (taken from the file header) are used to find every x-axis label. 

        Since the data values are stored in ascending order with respect to time, their order is used to assign them to their corresponding x-axis times.  

        More information about this file structure can be found :ref:`here <agilent_fid>`.

        Args:
            filepath (str): Path to file. 

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

        self.xlabels['FID'] = times
        self.ylabels['FID'] = np.array(['TIC'])
        self.data['FID'] = data_array

        # Extract metadata
        metadata_offsets = {
            'notebook': 0x35A, 
            'date': 0x957, 
            'method': 0xA0E, 
            'instrument': 0xC11, 
            'unit':  0x104C, 
            'signal': 0x1075 
        }

        self.metadata['FID'] = self.extract_metadata(f, metadata_offsets, 2)

        f.close()
    
    def parse_ms(self, filepath):
        """
        Function that parses .ms files containing MS data.

        The type of .ms file is determined using the descriptive string at the start of the file. 

        Because the data segments for each x-axis time contain data values for an arbitrary set of masses, the entire file must be read to determine the total list of unique masses. To prevent from rereading the file, the data is parsed and saved in the memo matrix as (mass, count) tuples.

        Surprisingly, it turns out that checking membership in a set is noticeably faster than reading a value from a 2D numpy matrix. Accordingly, we use a set to fill the data array at the end to increase speed by more than 3x.  

        More information about this file structure can be found :ref:`here <agilent_ms>`.

        Args:
            filepath (str): Path to file. 

        """
        data_offsets = {
            'type': 0x4,
            'start': 0x10A,
            'count1': 0x118,
            'count2': 0x142
        }

        f = open(filepath, 'rb')

        # Check the type of .ms file. 
        type_ms = self.read_string(f, data_offsets['type'], 1)

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

        self.xlabels['MS'] = times 
        self.ylabels['MS'] = masses_array 
        self.data['MS'] = data_array 

        # Extract metadata.
        metadata_offsets = {
            'time': 0xB2,
            'method': 0xE4
        }

        self.metadata['MS'] = self.extract_metadata(f, metadata_offsets, 1)

        f.close()
     
    def find_file(self, dirpath, detector):
        """
        Helper function to find the file in the directory corresponding to the desired detector. 

        Returns None if detector is not found in the directory.

        Args:
            dirpath (str): Path of directory.
            detector (str): Name of the desired detector.

        """
        detector_fileinfo = {
            'UV': ('.ch', 0x03313330),
            'FID': ('.ch', 0x03313739),
            'MS': ('.ms', 0x01320000)
        }

        detector = detector.upper()

        if detector not in detector_fileinfo:
            return None
    
        ext, head = detector_fileinfo[detector]

        matches = [file for file in os.listdir(dirpath) if file.lower().endswith(ext)]
        
        for file in matches:
            filepath = os.path.join(dirpath, file)
            f = open(filepath, 'rb')
            file_header = struct.unpack('>I', f.read(4))[0]
            f.close()
            if file_header == head:
                return filepath

        return None

    def extract_metadata(self, f, offsets, gap):
        """
        Helper function that extracts metadata from the file header. 

        Args:
            f (_io.BufferedReader): File opened in 'rb' mode.
            offsets (dict): Dictionary mapping properties to file offsets. 
            gap (int): Distance between two adjacent characters.

        Returns:
            dict: Dictionary containing metadata as string key-value pairs. 

        """
        metadata = {}
        for key, offset in offsets.items():
            string = self.read_string(f, offset, gap)
            if string:
                metadata[key] = string
        return metadata
        
    def read_string(self, f, offset, gap):
        """
        Returns the string at the specified offset in the file header.

        This function is primarily useful for retrieving metadata. 

        Args:
            f (_io.BufferedReader): File opened in 'rb' mode. 
            offset (int): Offset to begin reading from. 
            gap (int): Distance between two adjacent characters.

        """
        f.seek(offset)
        str_len = struct.unpack("<B", f.read(1))[0] * gap
        return f.read(str_len)[::gap].decode()

    """ 
    The following functions are documented in the parent class chromatogram.py.
    
    """
    def extract_traces(self, detector, labels=None):

        detector = detector.upper()

        # Input validation for detector.
        if detector not in self.detectors:
            raise Exception("Detector not present.")
        
        detector_ylabels = self.ylabels[detector].astype(str)
        detector_data_tp = self.data[detector].transpose()

        if not labels:
            return detector_data_tp

        # Input validation for labels.
        if isinstance(labels, str) or isinstance(labels, int):
            labels = [labels]

        if not isinstance(labels, list):
            raise Exception("Incorrect type for labels.")
        
        # Extracting traces. 
        output_array = np.empty((len(labels), self.xlabels[detector].size), dtype=int)

        for i in range(len(labels)):
            indices = np.where(detector_ylabels == str(labels[i]))[0]
            if len(indices) == 0:
                raise Exception(f"Label {labels[i]} not present.")
            output_array[i] = detector_data_tp[indices[0]]
        
        return output_array

    def to_str(self, detector, labels=None, delimiter=','):

        detector = detector.upper()

        traces_tp = self.extract_traces(detector, labels).transpose().astype(str)
        detector_xlabels = self.xlabels[detector]

        output = ""
        output += f"RT (ms),{','.join(self.ylabels[detector].astype(str))}\n"
        for i in range(detector_xlabels.size):
            output += f"{detector_xlabels[i]},{','.join(traces_tp[i])}\n"
        return output

    def export_csv(self, filename, detector, labels=None, delimiter=','):
        
        f = open(filename, 'w+')
        f.write(self.to_str(detector, labels, delimiter))
        f.close()
    
    def plot(self, detector, label, **kwargs):

        detector = detector.upper()

        plt.plot(self.xlabels[detector], self.extract_traces(detector, label).transpose(), **kwargs)
        plt.show()


# class AgilentUV(Agilent):
#     """
#     Class representing the data from a Agilent .UV file. 

#     Details about this file format are available :ref:`here <agilentuv>`. 

#     The available metadata includes: 

#     - vendor: Agilent.
#     - instrument: HPLC. 
#     - notebook: Lab notebook and sample number.
#     - date: Date and time measurement was taken.
#     - method: Method of data acquisition.
#     - unit: Y-axis units.
#     - datatype: Type of data. 
#     - position: Drawer and vial position. 

#     """
#     def __init__(self, filepath):
#         self.parse(filepath)

#     # Completely parse file at the start
#     # so future operations do not require the file
#     def parse(self, filepath):
#         """
#         Parses all relevant data from the data file. 

#         This function is called by the constructor and performs all necessary processing 
#         on the data file. As such, the data file is only ever opened once. 

#         Sets ``self.X``, ``self.Y``, ``self.Ylabels``, ``self.detectors``, and ``self.metadata``. 

#         Args:
#             filepath (str): Path to .UV data file. 

#         """
#         offsets = {
#             "number of data points": 0x116,
#             "start of data body": 0x1000
#         }

#         f = open(filepath, 'rb')

#         # Sets the total number of x-axis values (or rows) for the array.
#         f.seek(offsets["number of data points"])
#         num_data_points = struct.unpack(">i", f.read(4))[0]

#         times = np.zeros(num_data_points, np.uint64)

#         # Get the number of wavelengths using the header for the first data segment.
#         f.seek(offsets["start of data body"] + 8)
#         wavelength_range = tuple(num // 20 for num in struct.unpack("<HHH", f.read(6)))
#         print(wavelength_range)
#         wavelengths = np.arange(wavelength_range[0], wavelength_range[1] + 1, wavelength_range[2])
#         num_wavelengths = wavelengths.size

#         # Extract absorbance data from each data segment.
#         absorbances = np.zeros((num_data_points, num_wavelengths), np.int64)
#         f.seek(offsets["start of data body"])
#         for i in range(num_data_points):
#             # Read in header information.
#             f.read(4)
#             times[i] = struct.unpack("<I", f.read(4))[0]
#             f.read(14)
        
#             # If next value is a delta, add it to the last integer value (accumulating).
#             accum = 0 
#             for j in range(num_wavelengths):
#                 check_val = struct.unpack('<h', f.read(2))[0]
#                 if check_val == -0x8000:
#                     accum = struct.unpack('<i', f.read(4))[0]
#                 else: accum += check_val
#                 absorbances[i, j] = accum

#         self.X = times 
#         self.Y = np.array([absorbances])
#         self.Ylabels = np.array([wavelengths])
#         self.detectors = ['uv']

#         # Extract metadata
#         metadata_offsets = {
#             "notebook": 0x35A,
#             "date": 0x957,
#             "method": 0xA0E,
#             "unit": 0xC15,
#             "datatype": 0xC40,
#             "position": 0xFD7
#         }

#         self.metadata = self.extract_metadata(f, metadata_offsets)
#         self.metadata["instrument"] = "HPLC"

#         f.close()