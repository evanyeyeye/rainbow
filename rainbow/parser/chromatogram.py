from abc import ABC, abstractmethod

# TODO: require exact arguments
class Chromatogram(ABC):
    """
    Abstract class representing a chromatogram data folder.

    This class contains most of the public methods that may be useful to a user. 
    The abstract methods are implemented differently by each vendor-specific class
    that extend this one. 
    
    This class (and its children) contain the following important attributes:
    - detectors: String list of detector names.
    - xlabels: Dictionary mapping detector names to corresponding 1D numpy arrays with X-axis times.
    - ylabels: Dictionary mapping detector names to corresponding 1D numpy arrays with Y-axis labels.
    - data: Dictionary mapping detector names to corresponding 2D numpy arrays with data values.
    - metadata: Dictionary mapping detector names to corresponding dictionaries with metadata.

    More details about these attributes are documented under their get functions.

    This class should not be instantiated on its own.

    """
    def __init__(self, dirpath):
        self.detectors = []
        self.xlabels = {} 
        self.ylabels = {} 
        self.data = {}
        self.metadata = {}

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
    def extract_traces(self, detector, labels=None):
        """
        Returns a multidimensional integer numpy array containing data corresponding to the specified detector and label(s).

        The rows correspond to the Y-axis labels and the columns corrrespond to the X-axis times.

        Args:
            detector (str): Name of the desired detector. 
            labels (str or int or str list or int list): Y-axis label(s) to extract. 

        """
        pass

    @abstractmethod
    def export_csv(self, filename, detector, labels=None, delimiter=','):
        """
        Outputs a CSV file containing data corresponding to the specified detector and label(s). 

        Args:
            filename (str): Filename for the output CSV file.
            detector (str): Name of the desired detector. 
            labels (str or int or str list or int list): Y-axis label(s) to output. 
            delimiter (str): Delimiter used in the output CSV file. 

        """
        pass 

    @abstractmethod
    def plot(self, detector, label):
        """
        Shows a basic matplotlib plot for the specified detector and label.

        Args:
            detector (str): Name of the desired detector. 
            label (str or int): Y-axis label to be plotted. 
        """
        pass