from abc import ABC, abstractmethod


class Chromatogram(ABC):
    """
    Abstract class representing a chromatogram.

    This class contains all public methods that may be useful to a user. 
    The abstract methods are implemented differently by each vendor-specific class
    that extend this one. 
    
    This class should not be instantiated on its own.

    """

    def __init__(self, filepath):
        self.X = None 
        self.Y = None 
        self.Ylabels = None 
        self.detectors = None 
        self.metadata = None

    def get_X(self):
        """
        Returns a 1D integer numpy array containing the X-axis retention times (in milliseconds).

        """
        return self.X
    
    def get_Y(self):
        """
        Returns a 3D integer numpy array containing the data values. 

        Each inner 2D array corresponds to the detector at the same index in ``get_detectors()``. 
        Inside, each row contains the data taken at the time with the same index in ``get_X()``. 

        NOTE: This may need to be changed to a dictionary mapping detector names to 2D arrays.

        """
        return self.Y

    def get_Ylabels(self):
        """
        Returns a 2D integer numpy array containing the Y-axis labels. 

        Each row corresponds to the detector at the same index in ``get_detectors()``. 

        NOTE: This may need to be changed to a dictionary mapping detector names to 1d arrays. 

        """
        return self.Ylabels 

    def get_detectors(self):
        """
        Returns a string list containing all detectors present in the file. 

        Possible values are: 'UV', 'MS', 'CAD', 'ELSD', 'FID'

        """
        return self.detectors

    def get_metadata(self):
        """
        Returns a dictionary containing file metadata as key-value pairs.
 
        The metadata available is based on the implementing class (vendor). 

        """
        return self.metadata

    # TODO: require arguments in abstract methods
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