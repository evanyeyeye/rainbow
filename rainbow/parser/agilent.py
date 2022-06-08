import os
import struct
from collections import deque
import numpy as np
import matplotlib.pyplot as plt
from parser.chromatogram import Chromatogram 


class Agilent(Chromatogram):

    def __init__(self, dirpath):
        
        self.xlabels = {}
        self.ylabels = {}
        self.data = {}
        self.detectors = []
        self.metadata = {}

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
        signal_str = self.read_string(f, 0x1075)
        signal = int(signal_str.split("Sig=")[1].split('.')[0])

        self.xlabels['UV'] = times
        self.ylabels['UV'] = np.array([signal])
        self.data['UV'] = np.array(data_array)
        
        # Extract metadata
        metadata_offsets = {
            'notebook': 0x35A, 
            'date': 0x957, 
            'method': 0xA0E, 
            'instrument': 0xC11, 
            'unit':  0x104C, 
            'signal': 0x1075 
        }

        self.metadata['UV'] = self.extract_metadata(f, metadata_offsets)
    
    def parse_fid(self, filepath):
        
        data_offsets = {
            'info': 0x116,
            'body': 0x1800
        }
        
        f = open(filepath, 'rb')

        f.seek(data_offsets['info'])
        num_data_points = struct.unpack(">I", f.read(4))[0]
        
        start_time = int(struct.unpack(">f", f.read(4))[0])
        end_time = int(struct.unpack(">f", f.read(4))[0])
        delta_time = (end_time - start_time) // (num_data_points - 1)
        times = np.arange(start_time, end_time + 1, delta_time)

        # Extract data values.
        f.seek(data_offsets['body'])

        data_array = np.empty(num_data_points, dtype=int)
        for i in range(num_data_points):
            data_array[i] = struct.unpack("<d", f.read(8))[0]

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

        self.metadata['FID'] = self.extract_metadata(f, metadata_offsets)
    
    def parse_ms(self, filepath):
        pass

    def find_file(self, dirpath, detector):
        """
        Helper function to find the file in the directory corresponding to the desired detector. 

        """
        detector_fileinfo = {
            'UV': ('.ch', 0x03313330),
            'FID': ('.ch', 0x03313739),
            'MS': ('.ms', 0x01320000)
        }

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

    def extract_metadata(self, f, offsets):
        """
        Helper function that extracts metadata from the file header. 

        Args:
            f (_io.BufferedReader): File opened in 'rb' mode.
            offsets (dict): Dictionary mapping properties to file offsets. 

        Returns:
            dict: Dictionary containing metadata as string key-value pairs. 

        """
        metadata = {}
        for key, offset in offsets.items():
            metadata[key] = self.read_string(f, offset)
        return metadata
        
    def read_string(self, f, offset):
        """
        Returns the string at the specified offset in the file header.

        This function is primarily useful for retrieving metadata. 

        Args:
            f (_io.BufferedReader): File opened in 'rb' mode. 
            offset (int): Offset to begin reading from. 

        """
        f.seek(offset)
        str_len = struct.unpack("<B", f.read(1))[0] * 2
        return f.read(str_len)[::2].decode()

    def extract_traces(self):
        pass 
    
    def export_csv(self):
        pass 
    
    def plot(self):
        pass


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

#     """ 
#     Documentation for the following functions can be found in chromatogram.py (parent). 
    
#     """

#     # TODO: error handling
#     def extract_traces(self, detector, labels):
        
#         if isinstance(labels, int): 
#             labels = [labels]
       
#         detector_i = self.detectors.index(detector)
#         tp = np.transpose(self.Y[detector_i])
        
#         traces = np.zeros((len(labels), self.X.size), np.int64)
#         for i in range(len(labels)): 
#             label_i = np.where(self.Ylabels[detector_i] == labels[i])[0][0]
#             cur_trace = tp[label_i]
#             for j in range(cur_trace.size):
#                 traces[i, j] = cur_trace[j]

#         return traces
 
#     # TODO: encoding arg
#     # TODO: add headers
#     # TODO: all detector/label option
#     def export_csv(self, filename, detector, labels, delimiter=","):
#         traces = self.extract_traces(detector, labels)
#         np.savetxt(filename, np.transpose(traces), delimiter=delimiter, fmt="%i")

#     # TODO: add more args 
#     # TODO: add multiple labels
#     def plot(self, detector, label):
#         plt.plot(self.X, np.transpose(self.extract_traces(detector, label)))
#         plt.show()