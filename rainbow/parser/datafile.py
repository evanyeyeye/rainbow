import os 
import matplotlib.pyplot as plt


class DataFile:
    """
    Class representing a chromatogram data file. 

    It contains the following attributes:

    - name: String name of the file.
    - detector: String name of the detector. Supported detectors are: UV, MS, FID, CAD, and ELSD.
    - xlabels: 1D integer numpy array containing retention times (in milliseconds). 
    - ylabels: 1D numpy array containing y-axis labels.
    - data: 2D integer numpy array containing data values. The rows correspond to the x-axis times and the columns correspond to the y-axis labels.
    - metadata: Dictionary containing metadata as key-value pairs. The metadata available is based on the vendor and filetype.  

    """
    def __init__(self, filepath, detector, xlabels, ylabels, data, metadata):
        self.name = os.path.basename(filepath)
        self.detector = detector 
        self.xlabels = xlabels 
        self.ylabels = ylabels
        self.data = data
        self.metadata = metadata

    def __repr__(self):
        return f"\n{'-' * len(self.name)}\n" \
               f"{self.name}\n" \
               f"{'-' * len(self.name)}\n" \
               f"Detector: {self.detector}\n" \
               f"X labels: {self.xlabels}\n" \
               f"Y labels: {self.ylabels}\n" \
               f"Data: {self.data}\n" \
               f"Metadata: {self.metadata}\n" 

    def extract_traces(self, labels=None):
        """
        Extracts data corresponding to the specified y-axis label(s).

        It raises an exception if the labels are invalid. 

        Args:
            labels (str or int or str list or int list): Y-axis label(s) to extract. 
        
        Returns:
            2D numpy array containing data for the specified y-axis labels. The rows correspond to the y-axis labels and the columns corrrespond to the x-axis times.

        """
        ylabels_str = self.ylabels.astype(str)
        data_tp = self.data.transpose()

        if not labels:
            return data_tp

        # Input validation for labels.
        if isinstance(labels, str) or isinstance(labels, int):
            labels = [labels]

        if not isinstance(labels, list):
            raise Exception("Incorrect input type for labels.")
        
        # Extracting traces. 
        traces = np.empty((len(labels), self.xlabels.size), dtype=int)

        for i in range(len(labels)):
            indices = np.where(ylabels_str == str(labels[i]))[0]
            if len(indices) == 0:
                raise Exception(f"Label {labels[i]} not in {filename}.")
            traces[i] = data_tp[indices[0]]
        
        return traces

    def export_csv(self, filename, labels=None, delimiter=','):
        """
        Outputs a CSV file containing data corresponding to the specified y-axis label(s).

        Args:
            filename (str): Name for the output CSV file.
            labels (str or int or str list or int list): Y-axis label(s) to output. 
            delimiter (str): Delimiter used in the output CSV file. 

        """
        f = open(filename, 'w+')
        f.write(self.to_csv_str(labels, delimiter))
        f.close()
    
    def to_csv_str(self, labels=None, delimiter=','):
        """
        Returns a string representation of a CSV with data corresponding to the specified y-axis label(s).
        
        Args:
            labels (str or int or str list or int list): Y-axis label(s) to include.
            delimiter (str): Delimiter used in the representation of a CSV.

        """
        traces_tp = self.extract_traces(labels).transpose().astype(str)

        output = ""
        output += f"RT (ms),{','.join(self.ylabels.astype(str))}\n"
        for i in range(self.xlabels.size):
            output += f"{self.xlabels[i]},{','.join(traces_tp[i])}\n"
        return output

    def plot(self, label, **kwargs):
        """
        Shows a basic matplotlib plot for the specified y-axis label.

        Args:
            label (str or int): Y-axis label to be plotted. 
            kwargs: Extra arguments for matplotlib.

        """
        plt.plot(self.xlabels, self.extract_traces(label).transpose(), **kwargs)
        plt.show()