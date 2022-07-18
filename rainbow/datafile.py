import os 
import numpy as np


class DataFile:
    """
    Class representing a chromatogram data file. 

    It contains the following attributes:

    - name: String name of the file.
    - detector: String name of the detector. 
        Possible options are: UV, MS, FID, CAD, and ELSD.
    - xlabels: 1D numpy array containing retention times (in minutes). 
    - ylabels: 1D numpy array containing y-axis labels (e.g. mz, wavelength).
    - data: 2D numpy array containing data values (e.g. intensity). 
        The rows correspond to the retention times and the columns correspond 
        to the y-axis labels.
    - metadata: Dictionary containing metadata as key-value pairs. 
        The metadata available is based on the vendor and file format.  

    """
    def __init__(self, filepath, detector, xlabels, ylabels, data, metadata):
        self.name = os.path.basename(filepath)
        self.detector = detector 
        self.xlabels = xlabels 
        self.ylabels = ylabels
        self.data = data
        self.metadata = metadata

    def __repr__(self):
        return f"{self.name}"

    def get_info(self):
        """ 
        Returns a string summary of the DataFile. 
        """ 
        return f"\n{'-' * len(self.name)}\n" \
               f"{self.name}\n" \
               f"{'-' * len(self.name)}\n" \
               f"Detector: {self.detector}\n" \
               f"Xlabels: {self.xlabels}\n" \
               f"Ylabels: {self.ylabels}\n" \
               f"Data: {self.data}\n" \
               f"Metadata: {self.metadata}\n" 

    def extract_traces(self, labels=None):
        """
        Extracts data corresponding to the specified ylabel(s).

        Raises an exception if any ylabel(s) are invalid. 

        Args:
            labels (int or float or int list or float list): 
                Ylabel(s) to extract. 
        
        Returns:
            2D numpy array containing data for the specified ylabel(s). 
            The rows correspond to the ylabels and the columns corrrespond 
                to the retention times. 

        """

        if not labels:
            return self.data.T

        if isinstance(labels, int) or isinstance(labels, float):
            labels = [labels]

        if not isinstance(labels, list):
            raise Exception(f"Invalid type for labels.")

        indices = np.searchsorted(self.ylabels, labels)
        invalid_check = np.where(indices == len(labels))[0]
        if invalid_check.size > 0:
            raise Exception(f"Label {labels[i]} not in {filename}.")
        
        traces = self.data[:,indices].T

        return traces

    def export_csv(self, filename, labels=None, delim=','):
        """
        Outputs a CSV containing data for the specified ylabel(s).

        Args:
            filename (str): Filename for the output CSV.
            labels (int or float or int list or float list): 
                Ylabel(s) to export. 
            delim (str): Delimiter used in the output CSV. 

        """
        f = open(filename, 'w+')
        f.write(self.to_csvstr(labels, delim))
        f.close()
    
    def to_csvstr(self, labels=None, delim=','):
        """
        Returns a string representation of a CSV containing data 
            for the specified ylabel(s).
        
        Args:
            labels (int or float or int list or float list): 
                Ylabel(s) to return.
            delim (str): Delimiter used in the CSV representation.

        """
        str_traces_tp = self.extract_traces(labels).T.astype(str)

        if not labels:
            labels = self.ylabels.tolist()

        if isinstance(labels, int) or isinstance(labels, float):
            labels = [labels]

        if not isinstance(labels, list):
            raise Exception(f"Invalid type for labels.")

        str_labels = [str(label) for label in labels]

        csvstr = f"RT (min){delim}{f'{delim}'.join(str_labels)}\n"
        for i in range(self.xlabels.size):
            csvstr += f"{self.xlabels[i]}{delim}" \
                      f"{f'{delim}'.join(str_traces_tp[i])}\n"
        return csvstr

    def plot(self, label, **kwargs):
        """
        Shows a basic matplotlib plot for the specified ylabel.

        Args:
            label (str or int): Ylabel to be plotted. 
            kwargs: Extra arguments for matplotlib.

        """
        import matplotlib.pyplot as plt
        plt.plot(self.xlabels, self.extract_traces(label).T, **kwargs)
        plt.show()