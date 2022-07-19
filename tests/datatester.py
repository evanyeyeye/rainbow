import json
import unittest
from pathlib import Path
import rainbow as rb 


class DataTester(unittest.TestCase):
    """
    Unit tests for parsing file formats. 

    """
    def __test_data_directory(self, color, ext):
        """ 
        Runs all tests for a DataDirectory after parsing. 

        The DataDirectory is specified by color because of the 
            naming scheme of the inputs directory. 
        
        The attributes and metadata for each directory is stored in 
            a file in the jsons directory. 
        
        The axis labels and data values are stored as a csv in the 
            outputs directory. 

        """
        tests_path = Path("tests")
        json_path = tests_path / "jsons" / (color + ".json")
        with open(str(json_path)) as json_f:
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

        datadir_path = tests_path / "inputs" / (color + "." + ext)
        datadir = rb.read(str(datadir_path))

        # Tests attributes of the DataDirectory.
        # Also tests classification of its DataFiles. 
        self.assertEqual(datadir.name, color + "." + ext)
        self.assertCountEqual(
            [df.name for df in datadir.datafiles], data_names)
        self.assertSetEqual(datadir.detectors, detectors)
        self.assertCountEqual(datadir.by_name.keys(), 
            [name.upper() for name in data_names] + 
                [name.upper() for name in analog_names])
        self.assertCountEqual(
            datadir.by_detector.keys(), detector_to_names.keys())
        for key in datadir.by_detector:
            self.assertCountEqual(
                [df.name for df in datadir.by_detector[key]],
                detector_to_names[key])
        self.assertCountEqual(
            [df.name for df in datadir.analog], analog_names)
        self.assertDictEqual(datadir.metadata, json_data['metadata'])

        # Tests the attributes and data values of each DataFile.
        outputs_path = tests_path / "outputs" / color
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
            csv_path = outputs_path / (Path(name).stem + ".csv")
            with open(csv_path) as csv_f:
                csv_lines = csv_f.read().splitlines()
            self.assertListEqual(datafile.to_csvstr().splitlines(), csv_lines)