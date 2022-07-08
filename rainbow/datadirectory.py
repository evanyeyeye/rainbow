import os 

class DataDirectory:
    """
    Class representing a chromatogram data directory.

    It contains the following attributes:

    - name: String name of the directory. 
    - detectors: String set of all detectors in the directory. Supported detectors are: UV, MS, FID, CAD, and ELSD.
    - datafiles: Dictionary mapping filenames to DataFile objects. 
    - detector_to_files: Dictionary mapping detector names to lists of DataFile objects. 

    """
    def __init__(self, path, datafiles):
        self.name = os.path.basename(path)
        self.datafiles = datafiles
        self.by_name = {}
        self.by_detector = {}
        self.detectors = set()

        for datafile in datafiles:
            self.by_name[datafile.name.upper()] = datafile
            detector = datafile.detector
            self.detectors.add(detector)
            if detector in self.by_detector:
                self.by_detector[detector].append(datafile)
            else: 
                self.by_detector[detector] = [datafile]

    def __repr__(self):
        return f"{self.name}: {' - '.join(map(str, self.datafiles))}"

    def get_info(self):
        return f"\n{'=' * len(self.name)}\n" \
               f"{self.name}\n" \
               f"{'=' * len(self.name)}\n" \
               f"{''.join(datafile.get_info() for datafile in self.datafiles)}\n"

    def get_file(self, filename):
        if filename.upper() not in self.by_name.keys():
            raise Exception(f"Data file {filename} not found in {self.name}.")
        return self.by_name[filename.upper()]
    
    def get_detector(self, detector):
        if detector.upper() not in self.by_detector.keys():
            raise Exception(f"Detector {detector} not found in {self.name}.")
        return self.by_detector[detector.upper()]

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
        return self.get_file(filename).extract_traces(labels)

    def export_csv(self, in_filename, out_filename, labels=None, delimiter=','):
        """
        Outputs a CSV file containing data corresponding to the specified label(s) from the specified file.

        Args:
            in_filename (str): Name of the data file.
            out_filename (str): Name for the output CSV file.
            labels (str or int or str list or int list): Y-axis label(s) to output. 
            delimiter (str): Delimiter used in the output CSV file. 

        """
        self.get_file(in_filename).export_csv(out_filename, labels, delimiter)
    
    def plot(self, filename, label, **kwargs):
        """
        Shows a basic matplotlib plot for the specified file and label.

        Args:
            filename (str): Name of the data file.
            label (str or int): Y-axis label to be plotted. 
        """
        self.get_file(filename).plot(label, **kwargs)