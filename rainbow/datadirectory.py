import os 
from rainbow import DataFile


class DataDirectory:
    """ 
    Class representing a chromatogram data directory.
    
    Args: 
        path (str): Path of the directory.
        datafiles (list): All DataFile objects for the directory.
        metadata (dict): Metadata for the directory. 

    Attributes:
        name (str): Name of the DataDirectory. 
        datafiles (list): DataFile objects with a detector. 
            This does not include miscellaneous analog data.
        detectors (set): String detector names in the DataDirectory.
            Options: UV, MS, FID, CAD, ELSD.
        by_name (dict): Maps filenames to DataFile objects.
        by_detector (dict): Maps detector names to lists of DataFile objects.
        analog (list): DataFile objects with miscellaneous analog data. 
        metadata (dict): Depends on the vendor. 

    """  
    def __init__(self, path, datafiles, metadata):

        if not isinstance(path, str) or \
           not isinstance(datafiles, list) or \
           not all(isinstance(df, DataFile) for df in datafiles) or \
           not isinstance(metadata, dict):
            raise Exception("Wrong argument parameters for DataDirectory.")

        self.name = os.path.basename(path)
        self.datafiles = []
        self.detectors = set()
        self.by_name = {}
        self.by_detector = {}
        self.analog = []
        self.metadata = metadata

        for datafile in datafiles:
            self.by_name[datafile.name.upper()] = datafile
            detector = datafile.detector
            if not detector:
                self.analog.append(datafile)
                continue 
            self.datafiles.append(datafile)
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
        Returns a DataFile object by :code:`filename`. 

        Raises an exception if the :code:`filename` is not in the DataDirectory.

        Args:
            filename (str): DataFile name. 

        """
        if filename.upper() not in self.by_name.keys():
            raise Exception(f"Data file {filename} not found in {self.name}.")
        return self.by_name[filename.upper()]
    
    def get_detector(self, detector):
        """
        Returns a list of DataFile objects by :code:`detector`. 

        Raises an exception if the :code:`detector` is invalid. 

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
            for datafile in self.analog) + "\n")
        
    def extract_traces(self, filename, labels=None):
        """
        Extracts data corresponding to the specified DataFile and :code:`labels`.

        Args:
            filename (str): DataFile name. 
            labels (int/float/list, optional): Ylabel(s) to extract.
        
        Returns:
            2D numpy array containing data for the specified ylabel(s). 
            The rows correspond to the ylabels and the columns corrrespond \
                to the retention times.

        """
        return self.get_file(filename).extract_traces(labels)

    def export_csv(self, in_filename, out_filename, labels=None, delim=','):
        """
        Outputs a CSV with data for the specified DataFile and :code:`labels`.

        Args:
            in_filename (str): DataFile name. 
            out_filename (str): Filename for the output CSV. 
            labels (int/float/list, optional): Ylabel(s) to export.
            delim (str, optional): Delimiter used in the output CSV. 

        """
        self.get_file(in_filename).export_csv(out_filename, labels, delim)
    
    def plot(self, filename, label, **kwargs):
        """
        Shows a basic matplotlib plot for the specified DataFile and :code:`label`.

        Args:
            filename (str): DataFile name. 
            label (int/float): Ylabel to be plotted. 
            **kwargs (optional): Keyword arguments for matplotlib. 
        """
        self.get_file(filename).plot(label, **kwargs)