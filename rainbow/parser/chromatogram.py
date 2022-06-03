from abc import ABC, abstractmethod

class Chromatogram(ABC):

    def get_X(self):
        return self.X
    
    def get_Y(self):
        return self.Y

    def get_Ylabels(self):
        return self.Ylabels 

    def get_detectors(self):
        return self.detectors

    def get_metadata(self):
        return self.metadata

    @abstractmethod
    def extract_traces(detector, labels):
        pass

    @abstractmethod
    def export_csv(filename, detector, labels, delimiter):
        pass 

    @abstractmethod
    def plot(detector, label):
        pass