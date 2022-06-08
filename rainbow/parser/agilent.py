from parser.chromatogram import Chromatogram 
import numpy as np
import matplotlib.pyplot as plt
import struct


class Agilent(Chromatogram):

    def read_string(self, f, offset):
        """
        Returns the string at the specified offset in the file header.

        This function is primarily useful for retrieving metadata. 

        Args:
            f (_io.BufferedReader): File opened in 'rb' mode. 
            offset (int): Offset to begin reading from. 

        """
        f.seek(offset)
        length = struct.unpack("<B", f.read(1))[0] * 2
        return f.read(length)[::2].decode()
    
    def extract_metadata(self, f, offsets):
        """
        Helper function that extracts metadata from the file header. 

        Args:
            f (_io.BufferedReader): File opened in 'rb' mode.

        Returns:
            dict: Dictionary containing metadata as string key-value pairs. 

        """

        metadata = {}
        metadata["vendor"] = "agilent"

        for key, value in offsets.items():
            metadata[key] = self.read_string(f, value)
        
        return metadata


class AgilentUV(Agilent):
    """
    Class representing the data from a Agilent .UV file. 

    Details about this file format are available :ref:`here <agilentuv>`. 

    The available metadata includes: 

    - vendor: Agilent.
    - instrument: HPLC. 
    - notebook: Lab notebook and sample number.
    - date: Date and time measurement was taken.
    - method: Method of data acquisition.
    - unit: Y-axis units.
    - datatype: Type of data. 
    - position: Drawer and vial position. 

    """
    def __init__(self, filepath):
        self.parse(filepath)

    # Completely parse file at the start
    # so future operations do not require the file
    def parse(self, filepath):
        """
        Parses all relevant data from the data file. 

        This function is called by the constructor and performs all necessary processing 
        on the data file. As such, the data file is only ever opened once. 

        Sets ``self.X``, ``self.Y``, ``self.Ylabels``, ``self.detectors``, and ``self.metadata``. 

        Args:
            filepath (str): Path to .UV data file. 

        """
        offsets = {
            "number of data points": 0x116,
            "start of data body": 0x1000
        }

        f = open(filepath, "rb")

        # Sets the total number of x-axis values (or rows) for the array.
        f.seek(offsets["number of data points"])
        num_data_points = struct.unpack(">i", f.read(4))[0]

        times = np.zeros(num_data_points, np.uint64)

        # Get the number of wavelengths using the header for the first data segment.
        f.seek(offsets["start of data body"] + 8)
        wavelength_range = tuple(num // 20 for num in struct.unpack("<HHH", f.read(6)))
        print(wavelength_range)
        wavelengths = np.arange(wavelength_range[0], wavelength_range[1] + 1, wavelength_range[2])
        num_wavelengths = wavelengths.size

        # Extract absorbance data from each data segment.
        absorbances = np.zeros((num_data_points, num_wavelengths), np.int64)
        f.seek(offsets["start of data body"])
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

        print(f.tell())
        self.X = times 
        self.Y = np.array([absorbances])
        self.Ylabels = np.array([wavelengths])
        self.detectors = ["UV"]

        # Extract metadata
        metadata_offsets = {
            "notebook": 0x35A,
            "date": 0x957,
            "method": 0xA0E,
            "unit": 0xC15,
            "datatype": 0xC40,
            "position": 0xFD7
        }

        self.metadata = self.extract_metadata(f, metadata_offsets)
        self.metadata["instrument"] = "HPLC"

        f.close()

    """ 
    Documentation for the following functions can be found in chromatogram.py (parent). 
    
    """

    # TODO: error handling
    def extract_traces(self, detector, labels):
        
        if isinstance(labels, int): 
            labels = [labels]
       
        detector_i = self.detectors.index(detector)
        tp = np.transpose(self.Y[detector_i])
        
        traces = np.zeros((len(labels), self.X.size), np.int64)
        for i in range(len(labels)): 
            label_i = np.where(self.Ylabels[detector_i] == labels[i])[0][0]
            cur_trace = tp[label_i]
            for j in range(cur_trace.size):
                traces[i, j] = cur_trace[j]

        return traces
 
    # TODO: encoding arg
    # TODO: add headers
    # TODO: all detector/label option
    def export_csv(self, filename, detector, labels, delimiter=","):
        traces = self.extract_traces(detector, labels)
        np.savetxt(filename, np.transpose(traces), delimiter=delimiter, fmt="%i")

    # TODO: add more args 
    # TODO: add multiple labels
    def plot(self, detector, label):
        plt.plot(self.X, np.transpose(self.extract_traces(detector, label)))
        plt.show()