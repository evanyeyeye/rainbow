import tests.datatester


class TestAgilent(tests.datatester.DataTester):
    """
    Unit tests for parsing Agilent .D directories. 

    """
    def test_red(self):
        """
        Tests a directory containing:
            - UV spectrum 
            - 2 UV channels
            - CAD channel
        
        """
        self._DataTester__test_data_directory("red", "D")

    def test_orange(self):
        """ 
        Tests a directory containing:
            - ELSD channel
            - MS spectrum (LC format)

        """
        self._DataTester__test_data_directory("orange", "D")

    def test_yellow(self):
        """
        Tests a directory containing:
            - FID channel
            - MS spectrum (GC format)
            - MS SIM (GC format)
        
        """
        self._DataTester__test_data_directory("yellow", "D")

    def test_green(self):
        """
        Tests a directory containing:
            - Partial UV spectrum
            - 4 partial MS traces (LC format)
        
        """
        self._DataTester__test_data_directory("green", "D")

    def test_brown(self):
        """
        Tests a directory containing:
            - 31-version UV spectrum
            - 4 30-version MS traces (LC format)

        """
        self._DataTester__test_data_directory("brown", "D")

    def test_pink(self):
        """
        Tests a directory containing:
            - UV spectrum (131 OL format)
            - 6 MS channels (179 OL format)

        """
        self._DataTester__test_data_directory("pink", "D")

if __name__ == '__main__':
    unittest.main()