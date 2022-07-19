import os
import unittest
import numpy as np
from rainbow import DataFile, DataDirectory


class TestDataDirectory(unittest.TestCase):
    """
    Unit tests for DataDirectory class functionality.  

    """
    def test_validation(self):
        """
        Tests for constructor input validation. 

        """
        datafile = DataFile(
            "", None, np.empty(0), np.empty(0), np.empty((0, 0)), {})
        self.assertRaises(Exception, DataDirectory, 1, [datafile], {})
        self.assertRaises(Exception, DataDirectory, "lorem", datafile, {})
        self.assertRaises(Exception, DataDirectory, "lorem", set(), {})
        self.assertRaises(Exception, DataDirectory, "lorem", {datafile}, [])

    def test_attributes(self):
        """ 
        Tests correctness of class attributes.

        """
        datadir = DataDirectory("", [], {})
        self.assertEqual(datadir.name, "")
        self.assertCountEqual(datadir.datafiles, [])
        self.assertSetEqual(datadir.detectors, set())
        self.assertDictEqual(datadir.by_name, {})
        self.assertDictEqual(datadir.by_detector, {})
        self.assertCountEqual(datadir.analog, [])
        self.assertDictEqual(datadir.metadata, {})

        empty_1dim = np.empty(0)
        empty_2dim = np.empty((0, 0))
        datafile_list = [
            DataFile("cow.ch", 'ELSD', empty_1dim, empty_1dim, empty_2dim, {}),
            DataFile("bird.DAT", None, empty_1dim, empty_1dim, empty_2dim, {}),
            DataFile("ant.UV", 'UV', empty_1dim, empty_1dim, empty_2dim, {})
        ]
        datadir = DataDirectory(
            os.path.join("paper", "st.raw"), datafile_list, {'vendor': "you"})
        self.assertEqual(datadir.name, "st.raw")
        self.assertCountEqual(
            [df.name for df in datadir.datafiles], ["cow.ch", "ant.UV"])
        self.assertSetEqual(datadir.detectors, {'ELSD', 'UV'})
        self.assertCountEqual(
            datadir.by_name.keys(), ["COW.CH", "BIRD.DAT", "ANT.UV"])
        self.assertCountEqual(datadir.by_detector.keys(), ['UV', 'ELSD'])
        self.assertCountEqual([df.name for df in datadir.analog], ["bird.DAT"])
        self.assertDictEqual(datadir.metadata, {'vendor': "you"})


    def test_extract_traces(self):
        """ 
        Tests the `DataDirectory.extract_traces` method.

        """
        datafile = DataFile(
            "peer.MS", None, np.arange(4), np.array([301.1, 499.]), 
            np.arange(8).reshape(4, 2), {})
        datadir = DataDirectory("d.raw", [datafile], {})
        self.assertRaises(Exception, datadir.extract_traces, 301)
        self.assertRaises(Exception, datadir.extract_traces, "d.raw")
        self.assertRaises(Exception, datadir.extract_traces, "peer")
        self.assertRaises(Exception, datadir.extract_traces, "peer.MS", 0)
        np.testing.assert_array_equal(
            datadir.extract_traces("peer.ms"), np.arange(8).reshape(4, 2).T)
        np.testing.assert_array_equal(
            datadir.extract_traces("pEeR.mS", 301.1), 
            np.array(np.arange(0, 8, 2), ndmin=2))
        np.testing.assert_array_equal(
            datadir.extract_traces("peer.MS", 499), 
            np.array(np.arange(1, 8, 2), ndmin=2))
        np.testing.assert_array_equal(
            datadir.extract_traces("peer.ms", [301.1, 499.0]), 
            np.array(np.arange(8).reshape(4, 2).T))
   

if __name__ == '__main__':
    unittest.main()