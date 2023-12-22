import tests.datatester


class TestWaters(tests.datatester.DataTester):
    """
    Unit tests for parsing Waters .raw directories. 

    """
    def test_blue(self):
        """
        Tests a directory containing:
            - UV spectrum 
            - MS spectrum (8-byte format)
            - CAD channel
        
        """
        self._DataTester__test_data_directory("blue", "raw")

    def test_indigo(self):
        """
        Tests a directory containing:
            - MS trace (2-byte format)
            - 2 analog channels
        
        """
        self._DataTester__test_data_directory("indigo", "raw")

    def test_violet(self):
        """
        Tests a directory containing:
            - UV spectrum 
            - 3 UV channels (analog)
            - 2 MS spectra (6-byte format)
            - ELSD channel

        """
        self._DataTester__test_data_directory("violet", "raw")

    def test_white(self):
        """
        Tests a directory containing:
            - 6 UV spectrum (4-byte format)
            - 2 analog channels

        """
        self._DataTester__test_data_directory("white", "raw")

if __name__ == '__main__':
    unittest.main()