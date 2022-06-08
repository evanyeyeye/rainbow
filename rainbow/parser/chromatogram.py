from abc import ABC, abstractmethod

# TODO: require exact arguments
class Chromatogram(ABC):
    """
    Abstract class representing a chromatogram data folder.

    This class contains all public methods that may be useful to a user. 
    The abstract methods are implemented differently by each vendor-specific class
    that extend this one. 
    
    This class should not be instantiated on its own.

    """
    def __init__(self, filepath):
        self.detectors = None 
        self.xlabels = None 
        self.ylabels = None 
        self.data = None
        self.metadata = None

    def get_detectors(self):
        """
        Returns a string list containing all detectors present in the file. 

        Possible values are: 'UV', 'MS', 'FID', 'CAD', 'ELSD'

        """
        return self.detectors

    def get_xlabels(self, detector):
        """
        Returns a 1D numpy integer array containing the X-axis retention times (in milliseconds) for the specified detector.

        """
        return self.xlabels[detector]
    
    def get_ylabels(self, detector):
        """
        Returns a 1D numpy array containing the Y-axis labels for the specified detector.

        """
        return self.ylabels[detector]

    def get_data(self, detector):
        """
        Returns a 2D numpy integer array containing the data values for the specified detector.
    
        The rows correspond to the X-axis times and the columns correspond to the Y-axis labels.

        """
        return self.data[detector]

    def get_metadata(self, detector):
        """
        Returns a dictionary containing file metadata as key-value pairs for the specified detector.
 
        The metadata available is based on the vendor and filetype.  

        """
        return self.metadata[detector]

    @abstractmethod
    def extract_traces(self, detector, labels):
        """
        Returns a multidimensional integer numpy array containing data corresponding to the specified detector and label(s).

        Args:
            detector (str): Name of the desired detector. 
            labels (int or int list): Y-axis label(s) to extract. 

        """
        pass

    @abstractmethod
    def export_csv(self, filename, detector, labels, delimiter=","):
        """
        Outputs a CSV file containing data corresponding to the specified detector and label(s). 

        Args:
            filename (str): Filename for the output CSV file.
            detector (str): Name of the desired detector. 
            labels (int or int list): Y-axis label(s) to output. 
            delimiter (str): Delimiter used in the output CSV file. 

        """
        pass 

    @abstractmethod
    def plot(self, detector, label):
        """
        Shows a basic matplotlib plot for the specified detector and label.

        Args:
            detector (str): Name of the desired detector. 
            label (int): Y-axis label to be plotted. 
        """
        pass