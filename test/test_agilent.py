import os
import json
import unittest
import rainbow as rb 


class TestAgilent(unittest.TestCase):
    """
    Unit tests for parsing Agilent .D directories. 

    """
    def __test_data_directory(self, color):
        """ 
        Runs all tests for a DataDirectory. 

        The DataDirectory is specified by color only because of the 
            naming scheme in the inputs directory. 
        
        The attributes and metadata for each directory is stored in 
            a file in the jsons directory. 
        
        The axis labels and data values are stored as a csv in the 
            outputs directory. 

        """
        json_path = os.path.join("jsons", color + ".json")
        with open(json_path) as json_f:
            json_data = json.load(json_f)

        data_names = []
        detectors = set()
        detector_to_names = {}
        analog_names = []
        for name in json_data['datafiles']:
            file_dict = json_data['datafiles'][name]
            if file_dict['analog']:
                analog_names.append(name)
                continue 
            data_names.append(name)
            detector = file_dict['detector']
            detectors.add(detector)
            if detector in detector_to_names:
                detector_to_names[detector].append(name)
            else:
                detector_to_names[detector] = [name]

        datadir_path = os.path.join("inputs", color + ".D")
        datadir = rb.read(datadir_path)

        # Tests attributes of the DataDirectory.
        # Also tests classification of its DataFiles. 
        self.assertEqual(datadir.name, color + ".D")
        self.assertEqual(len(datadir.datafiles), len(data_names))
        self.assertSetEqual(datadir.detectors, detectors)
        self.assertCountEqual(datadir.by_name.keys(), 
            [name.upper() for name in data_names])
        self.assertCountEqual(
            datadir.by_detector.keys(), list(detector_to_names.keys()))
        for key in datadir.by_detector:
            self.assertCountEqual(
                [df.name for df in datadir.by_detector[key]],
                detector_to_names[key])
        self.assertCountEqual(
            [df.name for df in datadir.analog], analog_names)
        self.assertDictEqual(datadir.metadata, json_data['metadata'])

        # Tests the attributes and data values of each DataFile.
        outputs_path = os.path.join("outputs", color)
        for name in json_data['datafiles']:
            datafile = datadir.get_file(name)
            file_dict = json_data['datafiles'][name]

            self.assertEqual(datafile.name, name)
            self.assertEqual(datafile.detector, file_dict['detector'])
            self.assertDictEqual(datafile.metadata, file_dict['metadata'])

            shape = tuple(file_dict['shape'])
            self.assertEqual(datafile.xlabels.size, shape[0])
            self.assertEqual(datafile.ylabels.size, shape[1])
            self.assertTupleEqual(datafile.data.shape, shape)
 
            csv_name = os.path.splitext(name)[0] + ".csv"
            csv_path = os.path.join(outputs_path, csv_name)
            with open(csv_path) as csv_f:
                csv_lines = csv_f.read().splitlines()
            self.assertListEqual(datafile.to_csvstr().splitlines(), csv_lines)

    def test_red(self):
        """
        Tests a directory containing:
            - UV spectrum 
            - 2 UV channels
            - CAD channel
        
        """
        self.__test_data_directory("red")

    # def test_orange(self):
    #     self.__test_data_directory("orange")

if __name__ == '__main__':
    unittest.main()