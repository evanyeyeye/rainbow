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

    def test_teal(self):
        """
        Tests an Agilent OpenLab CDS .dx archive containing:
            - DAD spectrum (.UV, Spectra131)
            - 2 single-wavelength DAD signals (.CH, Signal179)
            - 2 instrument telemetry traces (.IT, InstrumentTrace179)

        Parsed with telemetry=True so the .IT analog traces are included.

        """
        self._DataTester__test_data_directory("teal", "dx", telemetry=True)

    def test_teal_telemetry_off(self):
        """
        Tests that .dx telemetry (.IT) is skipped unless requested.

        """
        import rainbow as rb

        path = "tests/inputs/teal.dx"

        # By default the telemetry traces are not parsed.
        datadir = rb.read(path)
        self.assertEqual(datadir.analog, [])
        self.assertTrue(all(df.detector == 'UV' for df in datadir.datafiles))

        # The telemetry flag includes them as analog data.
        datadir = rb.read(path, telemetry=True)
        self.assertCountEqual(
            [df.name for df in datadir.analog], ["WPS1A.IT", "PMP1B.IT"])

        # An explicitly requested telemetry trace is parsed even when the flag
        # is off.
        datadir = rb.read(path, requested_files=["PMP1B.IT"])
        self.assertCountEqual(
            [df.name for df in datadir.analog], ["PMP1B.IT"])

if __name__ == '__main__':
    unittest.main()