import unittest
from rainbow import parser


class TestAgilent(unittest.TestCase):
    """
    Unit tests for Agilent data parsing. 

    """
    def _test_data_file(self, datadir, name, detector, xlabels_count, ylabels_count, csv_path, metadata):
        """
        Helper function containing tests for an Agilent data file.
        
        """
        f = open(csv_path)
        csv_data = f.read().splitlines()
        f.close()
        
        datafile = datadir.datafiles[name]
        self.assertEqual(datafile.name, name)
        self.assertEqual(datafile.detector, detector)
        self.assertEqual(datafile.xlabels.size, xlabels_count)
        self.assertEqual(datafile.ylabels.size, ylabels_count)
        self.assertTupleEqual(datafile.data.shape, (xlabels_count, ylabels_count))
        self.assertListEqual(datafile.to_csv_str().splitlines(), csv_data)
        self.assertDictEqual(datafile.metadata, metadata)

    def test_agilent_uv(self):
        """
        Tests an Agilent data directory with UV data. 

        """
        dirpath = "data/uv/caffeine.D"
        
        # caffine.D tests. 
        datadir = parser.read(dirpath)
        self.assertEqual(datadir.name, 'CAFFEINE.D')
        self.assertCountEqual(datadir.detectors, ['UV'])
        self.assertCountEqual(datadir.datafiles.keys(), ['DAD1.UV', 'DAD1A.CH'])
        self.assertCountEqual(datadir.detector_to_files.keys(), ['UV'])
        self.assertCountEqual([file.name for file in datadir.detector_to_files['UV']], ['DAD1.UV', 'DAD1A.CH'])

        # DAD1.uv tests. 
        uv_metadata = {
            'notebook': '0394783-1156_caffeine', 
            'date': '30-Jan-19, 14:03:46', 
            'method': 'FFP_UPLC_SHORT.M', 
            'unit': 'mAU', 
            'datatype': 'DAD1I, DAD: Spectrum', 
            'position': 'D1B-A4'
        }
        self._test_data_file(datadir, 'DAD1.UV', 'UV', 4201, 106, "data/uv/DAD1.csv", uv_metadata)

        # DAD1A.ch tests. 
        ch_metadata = {
            'notebook': '0394783-1156_caffeine',
            'date': '30-Jan-19, 14:03:46',
            'method': 'FFP_UPLC_SHORT.M',
            'instrument': 'Asterix ChemStation',
            'unit': 'mAU',
            'signal': 'DAD1A, Sig=210.0,4.0  Ref=off'
        } 
        self._test_data_file(datadir, 'DAD1A.CH', 'UV', 4201, 1, "data/uv/DAD1A.csv", ch_metadata)

    def test_agilent_uv_ms(self):
        """
        Tests an Agilent data directory with UV and MS data. 
        
        """
        dirpath = "data/uv_ms/100518-RM_HPLC-01970.D"

        # 100518-RM_HPLC-01970.D tests.
        datadir = parser.read(dirpath)
        self.assertEqual(datadir.name, '100518-RM_HPLC-01970.D')
        self.assertCountEqual(datadir.detectors, ['UV', 'MS'])
        self.assertCountEqual(datadir.datafiles.keys(), ['DAD1.UV', 'DAD1A.CH', 'MSD1.MS'])
        self.assertCountEqual(datadir.detector_to_files.keys(), ['UV', 'MS'])
        self.assertCountEqual([file.name for file in datadir.detector_to_files['UV']], ['DAD1.UV', 'DAD1A.CH'])
        self.assertCountEqual([file.name for file in datadir.detector_to_files['MS']], ['MSD1.MS'])

        # DAD1.uv tests.
        uv_metadata = {
            'notebook': '0416044-0032', 
            'date': '10-May-18, 17:43:49', 
            'method': 'RM_HPLC.M', 
            'unit': 'mAU', 
            'datatype': 'DAD1I, DAD: Spectrum'
        }
        self._test_data_file(datadir, 'DAD1.UV', 'UV', 2403, 106, "data/uv_ms/DAD1.csv", uv_metadata)

        # DAD1A.ch tests.
        ch_metadata = {
            'notebook': '0416044-0032', 
            'date': '10-May-18, 17:43:49', 
            'method': 'RM_HPLC.M', 
            'instrument': 'Asterix ChemStation', 
            'unit': 'mAU', 
            'signal': 'DAD1A, Sig=215.0,16.0  Ref=off'
        }
        self._test_data_file(datadir, 'DAD1A.CH', 'UV', 2403, 1, "data/uv_ms/DAD1A.csv", ch_metadata)

        # MSD1.MS tests. 
        ms_metadata = {
            'time': '10 May 18   5:43 pm -0500', 
            'method': 'RM_HPLC.M'
        } 
        self._test_data_file(datadir, 'MSD1.MS', 'MS', 316, 824, "data/uv_ms/MSD1.csv", ms_metadata)

    def test_agilent_ms_fid(self):
        """
        Tests a directory with MS and FID data. 
        
        """
        dirpath = "data/ms_fid/cedrol_mix_01.D"

        # cedrol_mix_01.D tests.
        datadir = parser.read(dirpath)
        self.assertEqual(datadir.name, 'CEDROL_MIX_01.D')
        self.assertCountEqual(datadir.detectors, ['MS', 'FID'])
        self.assertCountEqual(datadir.datafiles.keys(), ['FID1A.CH', 'DATA.MS'])
        self.assertCountEqual(datadir.detector_to_files.keys(), ['MS', 'FID'])
        self.assertCountEqual([file.name for file in datadir.detector_to_files['MS']], ['DATA.MS'])
        self.assertCountEqual([file.name for file in datadir.detector_to_files['FID']], ['FID1A.CH'])

        # data.ms tests. 
        ms_metadata = {
            'time': '14 Jan 22  01:29 pm', 
            'method': 'Rt-bDEX-SE_mcminn.M'
        }
        self._test_data_file(datadir, 'DATA.MS', 'MS', 7279, 271, "data/ms_fid/data.csv", ms_metadata)

        # FID1A.ch tests. 
        fid_metadata = {
            'notebook': 'cedrol_mix_01', 
            'date': '14 Jan 22  01:29 pm', 
            'method': 'Rt-bDEX-SE_mcminn.M', 
            'instrument': 'Mustang ChemStation', 
            'unit': 'pA', 
            'signal': 'Front Signal'
        }
        self._test_data_file(datadir, 'FID1A.CH', 'FID', 54285, 1, "data/ms_fid/FID1A.csv", fid_metadata)

    def test_agilent_sim_fid(self):
        """
        Tests a directory containing MS (SIM) and FID data. 
        
        """
        dirpath = "data/sim_fid/caye_nmr_test_mix.D"
        chromatogram = parser.read(dirpath)
        
        # caye_nmr_test_mix.D tests.
        datadir = parser.read(dirpath)
        self.assertEqual(datadir.name, 'CAYE_NMR_TEST_MIX.D')
        self.assertCountEqual(datadir.detectors, ['MS', 'FID'])
        self.assertCountEqual(datadir.datafiles.keys(), ['FID1A.CH', 'DATA.MS', 'DATASIM.MS'])
        self.assertCountEqual(datadir.detector_to_files.keys(), ['MS', 'FID'])
        self.assertCountEqual([file.name for file in datadir.detector_to_files['MS']], ['DATA.MS', 'DATASIM.MS'])
        self.assertCountEqual([file.name for file in datadir.detector_to_files['FID']], ['FID1A.CH'])

        # data.ms tests. 
        ms_metadata = {
            'time': '17 Dec 19  10:04 am', 
            'method': 'HP-5MS_HTAchiral_da'
        }
        self._test_data_file(datadir, 'DATA.MS', 'MS', 1307, 199, "data/sim_fid/data.csv", ms_metadata)

        # dataSim.ms tests.
        sim_metadata = {
            'time': '17 Dec 19  10:04 am', 
            'method': 'HP-5MS_HTAchiral_da'
        }
        self._test_data_file(datadir, 'DATASIM.MS', 'MS', 1309, 2, "data/sim_fid/dataSim.csv", sim_metadata)

        # FID1A.ch tests. 
        fid_metadata = {
            'date': '17 Dec 19  10:04 am', 
            'method': 'HP-5MS_HTAchiral_da_100-300_simscan.M', 
            'instrument': 'Mustang ChemStation', 
            'unit': 'pA', 
            'signal': 'Front Signal'
        } 
        self._test_data_file(datadir, 'FID1A.CH', 'FID', 10197, 1, "data/sim_fid/FID1A.csv", fid_metadata)


if __name__ == '__main__':
    unittest.main()