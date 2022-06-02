from abc import ABC, abstractmethod

class Chromatogram(ABC):

    @abstractmethod 
    def get_X():
        pass
    
    @abstractmethod 
    def get_Y():
        pass

    @abstractmethod 
    def get_Ylabels():
        pass

    @abstractmethod 
    def get_detectors():
        pass

    @abstractmethod
    def get_metadata():
        pass

    @abstractmethod
    def extract_traces(detector, labels):
        pass

