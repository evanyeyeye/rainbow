import os 


class DataDirectory:
    """
    Class representing a chromatogram data directory.

    It contains the following attributes:

    - name: String name of the directory. 
    - datafiles: List of DataFile objects that match a detector. 
    - detectors: String set of all detectors in the directory.
        Possible options are: UV, MS, FID, CAD, and ELSD.
    - by_name: Dictionary of filenames -> DataFile objects.
    - by_detector: Dictionary of detector names -> lists of DataFile objects.
    - analog: List of DataFile objects for miscellaneous analog data.
    - metadata: Dictionary containing metadata as key-value pairs. 
        The metadata available is based on the vendor.

    """
    def __init__(self, path, datafiles, metadata):

        self.name = os.path.basename(path)
        self.datafiles = datafiles
        self.detectors = set()
        self.by_name = {}
        self.by_detector = {}
        self.analog = []
        self.metadata = metadata

        for datafile in datafiles:
            detector = datafile.detector
            if not detector:
                analog.append(datafiles)
                continue 
            self.by_name[datafile.name.upper()] = datafile
            self.detectors.add(detector)
            if detector in self.by_detector:
                self.by_detector[detector].append(datafile)
            else: 
                self.by_detector[detector] = [datafile]

    def __repr__(self):
        return f"{self.name}: {' - '.join(map(str, self.datafiles))}"

    def get_info(self):
        """
        Returns a string summary of the DataDirectory.  

        """
        return f"\n{'=' * len(self.name)}\n" \
            f"{self.name}\n" \
            f"{'=' * len(self.name)}\n" \
            f"Directory Metadata: {self.metadata}\n" \
            f"{''.join(datafile.get_info() for datafile in self.datafiles)}\n"

    def get_file(self, filename):
        """
        Returns a DataFile object by filename. 

        Raises an exception is the file is not in the DataDirectory.

        Args:
            filename (str): DataFile name. 

        """
        if filename.upper() not in self.by_name.keys():
            raise Exception(f"Data file {filename} not found in {self.name}.")
        return self.by_name[filename.upper()]
    
    def get_detector(self, detector):
        """
        Returns a list of DataFile objects by detector. 

        Raises an exception if the detector name is invalid. 

        Args:
            detector (str): Detector name. 

        """
        if detector.upper() not in self.by_detector.keys():
            raise Exception(f"Detector {detector} not found in {self.name}.")
        return self.by_detector[detector.upper()]

    def list_analog(self):
        """
        Prints a summary of the miscellaneous analog data.

        """
        print("\n".join(f"{datafile.name}: {datafile.metadata['description']}"
            for datafile in analog))

    def extract_traces(self, filename, labels=None):
        """
        Extracts data corresponding to the specified DataFile and ylabel(s).

        Args:
            filename (str): DataFile name. 
            labels (int or float or int list or float list): 
                Ylabel(s) to extract.
        
        Returns:
            2D numpy array containing data for the specified ylabel(s). 
            The rows correspond to the ylabels and the columns corrrespond 
                to the retention times.

        """
        return self.get_file(filename).extract_traces(labels)

    def export_csv(self, in_filename, out_filename, labels=None, delim=','):
        """
        Outputs a CSV with data for the specified DataFile and ylabel(s).

        Args:
            in_filename (str): DataFile name. 
            out_filename (str): Filename for the output CSV. 
            labels (str or int or str list or int list): Ylabel(s) to export.
            delim (str): Delimiter used in the output CSV. 

        """
        self.get_file(in_filename).export_csv(out_filename, labels, delim)
    
    def plot(self, filename, label, **kwargs):
        """
        Shows a basic matplotlib plot for the specified DataFile and ylabel.

        Args:
            filename (str): DataFile name. 
            label (str or int): Ylabel to be plotted. 
        """
        self.get_file(filename).plot(label, **kwargs)