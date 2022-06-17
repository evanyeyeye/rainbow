import os 
import matplotlib.pyplot as plt

class DataDirectory:
    """
    Class representing a chromatogram data directory.

    It contains the following attributes:

    - name: String name of the directory. 
    - detectors: String list of all detectors in the directory. Supported detectors are: UV, MS, FID, CAD, and ELSD.
    - datafiles: Dictionary mapping filenames to DataFile objects. 
    - detector_to_files: Dictionary mapping detector names to lists of DataFile objects. 

    """
    def __init__(self, dirname, detector_to_files):
        self.name = os.path.basename(dirname).upper()
        self.detectors = []
        self.datafiles = {}
        self.detector_to_files = detector_to_files

        for detector, files in detector_to_files.items():
            self.detectors.append(detector)
            for file in files:
                self.datafiles[file.name] = file

    def __repr__(self):
        return f"\n{'=' * len(self.name)}\n" \
               f"{self.name}\n" \
               f"{'=' * len(self.name)}\n" \
               f"{self.detector_to_files}\n"

    def extract_traces(self, filename, labels=None):
        """
        Extracts data corresponding to the specified label(s) from the specified file.

        It raises an exception if the file is not found in the directory.

        Args:
            filename (str): Name of the data file. 
            labels (str or int or str list or int list): Y-axis label(s) to extract. 
        
        Returns:
            2D numpy array containing data for the specified labels. The rows correspond to the y-axis labels and the columns corrrespond to the x-axis times.

        """
        filename = filename.upper()
        if filename not in self.datafiles.keys():
            raise Exception(f"Data file {filename} not found in {self.name}.")
        
        file = datafiles[filename]
        return file.extract_traces(labels)

    def export_csv(self, in_filename, out_filename, labels=None, delimiter=','):
        """
        Outputs a CSV file containing data corresponding to the specified label(s) from the specified file.

        Args:
            in_filename (str): Name of the data file.
            out_filename (str): Name for the output CSV file.
            labels (str or int or str list or int list): Y-axis label(s) to output. 
            delimiter (str): Delimiter used in the output CSV file. 

        """
        in_filename = in_filename.upper()
        if in_filename not in self.datafiles.keys():
            raise Exception(f"Data file {in_filename} not found in {self.name}.")

        file = self.datafiles[in_filename]
        file.export_csv(out_filename, labels, delimiter)
    
    def plot(self, filename, label, **kwargs):
        """
        Shows a basic matplotlib plot for the specified file and label.

        Args:
            filename (str): Name of the data file.
            label (str or int): Y-axis label to be plotted. 
        """
        filename = filename.upper()
        if filename not in self.datafiles.keys():
            raise Exception(f"Data file {filename} not found in {self.name}.")

        file = self.datafiles[filename]
        file.plot(label, **kwargs)