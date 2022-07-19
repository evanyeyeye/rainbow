import os
import unittest
import numpy as np
from rainbow import DataFile


class TestDataFile(unittest.TestCase):
    """
    Unit tests for DataFile class functionality.  

    """
    def test_validation(self):
        """
        Tests for constructor input validation. 

        """
        empty_1dim = np.empty(0)
        empty_2dim = np.empty((0, 0))
        self.assertRaises(Exception,
            DataFile, 1, None, empty_1dim, empty_1dim, empty_2dim, {})
        self.assertRaises(Exception,
            DataFile, "lorem", 'OK', empty_1dim, empty_1dim, empty_2dim, {})
        self.assertRaises(Exception,
            DataFile, "lorem", 'UV', [], empty_1dim, empty_2dim, {})
        self.assertRaises(Exception,
            DataFile, "lorem", 'UV', empty_2dim, empty_1dim, empty_2dim, {})
        self.assertRaises(Exception,
            DataFile, "lorem", 'UV', empty_1dim, [], empty_2dim, {})
        self.assertRaises(Exception,
            DataFile, "lorem", 'UV', empty_1dim, empty_2dim, empty_2dim, {})
        self.assertRaises(Exception,
            DataFile, "lorem", 'UV', empty_1dim, empty_1dim, [[]], {})
        self.assertRaises(Exception,
            DataFile, "lorem", 'UV', empty_1dim, empty_1dim, empty_1dim, {})
        self.assertRaises(Exception,
            DataFile, "lorem", 'UV', empty_1dim, empty_1dim, empty_2dim, set())

    def test_attributes(self):
        """ 
        Tests correctness of class attributes.

        """
        datafile = DataFile(
            os.path.join("kick", "ball.ch"), 'ELSD', np.ones(5), np.zeros(1), 
            np.arange(5).reshape((5, 1)), {'pick': 'me'})
        self.assertEqual(datafile.name, "ball.ch")
        self.assertEqual(datafile.detector, 'ELSD')
        np.testing.assert_array_equal(datafile.xlabels, np.ones(5))
        np.testing.assert_array_equal(datafile.ylabels, np.zeros(1))
        np.testing.assert_array_equal(
            datafile.data, np.arange(5).reshape((5, 1)))
        self.assertDictEqual(datafile.metadata, {'pick': 'me'})

    def test_extract_traces(self):
        """ 
        Tests the `DataFile.extract_traces` method.

        """
        datafile = DataFile(
            "sky.DAT", None, np.arange(4), np.array([301.0, 499.9]), 
            np.arange(8).reshape(4, 2), {})
        self.assertRaises(Exception, datafile.extract_traces, "301")
        self.assertRaises(Exception, datafile.extract_traces, ["499.9"])
        self.assertRaises(Exception, datafile.extract_traces, 499.0)
        self.assertRaises(Exception, datafile.extract_traces, [500])
        np.testing.assert_array_equal(
            datafile.extract_traces(), np.arange(8).reshape(4, 2).T)
        np.testing.assert_array_equal(
            datafile.extract_traces(301.0), 
            np.array(np.arange(0, 8, 2), ndmin=2))
        np.testing.assert_array_equal(
            datafile.extract_traces(499.9), 
            np.array(np.arange(1, 8, 2), ndmin=2))
        np.testing.assert_array_equal(
            datafile.extract_traces([301, 499.9]), 
            np.array(np.arange(8).reshape(4, 2).T))

    def test_to_csvstr(self):
        """ 
        Tests the `DataFile.to_csvstr` method.

        """
        datafile = DataFile(
            "nolabel.ms", None, np.arange(2), np.array(['']), 
            np.arange(2, 4).reshape(2, 1), {})
        self.assertRaises(Exception, datafile.to_csvstr, ' ')
        self.assertRaises(Exception, datafile.to_csvstr, 0)
        csvstr = "RT (min),\n0,2\n1,3\n"
        self.assertEqual(datafile.to_csvstr(), csvstr)
        self.assertEqual(datafile.to_csvstr(''), csvstr)
        self.assertEqual(datafile.to_csvstr(['']), csvstr)

        datafile = DataFile(
            "dino.UV", None, np.arange(3), np.array([220, 280]), 
            np.arange(6).astype(np.float32).reshape(3, 2), {})
        self.assertRaises(Exception, datafile.to_csvstr, '')
        self.assertRaises(Exception, datafile.to_csvstr, 0)
        self.assertEqual(datafile.to_csvstr(), 
            "RT (min),220,280\n0,0.0,1.0\n1,2.0,3.0\n2,4.0,5.0\n")
        self.assertEqual(datafile.to_csvstr([220.0]), 
            "RT (min),220.0\n0,0.0\n1,2.0\n2,4.0\n")
        self.assertEqual(datafile.to_csvstr([280]), 
            "RT (min),280\n0,1.0\n1,3.0\n2,5.0\n")
        self.assertEqual(datafile.to_csvstr([220., 280.]), 
            "RT (min),220.0,280.0\n0,0.0,1.0\n1,2.0,3.0\n2,4.0,5.0\n")
        

if __name__ == '__main__':
    unittest.main()