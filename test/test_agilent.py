import unittest
from rainbow import parser


class TestAgilent(unittest.TestCase):
    """
    Unit tests for Agilent data directories. 

    Each test checks the following for validity:
    
    - Axis dimensions.
    - Data values.
    - Metadata. 

    """
    def test_agilent_uv(self):
        """
        Tests a directory containing only UV data. 

        """
        dirpath = "data/uv/caffeine.D"
        chromatogram = parser.read(dirpath)
        
        self.assertCountEqual(chromatogram.get_detectors(), ['UV'])

        # UV tests. 
        self.assertEqual(chromatogram.get_xlabels('UV').size, 4201)
        self.assertEqual(chromatogram.get_ylabels('UV').size, 1)
        self.assertTupleEqual(chromatogram.get_data('UV').shape, (4201, 1))

        uv_path = "data/uv/uv.csv"
        f = open(uv_path)
        uv_data = f.read().splitlines()
        f.close()
        self.assertListEqual(uv_data, chromatogram.to_str('UV').splitlines())

        uv_metadata = {
            'notebook': '0394783-1156_caffeine',
            'date': '30-Jan-19, 14:03:46',
            'method': 'FFP_UPLC_SHORT.M',
            'instrument': 'Asterix ChemStation',
            'unit': 'mAU',
            'signal': 'DAD1A, Sig=210.0,4.0  Ref=off'
        } 
        self.assertDictEqual(uv_metadata, chromatogram.get_metadata('UV'))

    def test_agilent_uv_ms(self):
        """
        Tests a directory containing UV and MS data. 
        
        """
        dirpath = "data/uv_ms/100518-RM_HPLC-01970.D"
        chromatogram = parser.read(dirpath)
        
        self.assertCountEqual(chromatogram.get_detectors(), ['UV', 'MS'])

        # UV tests.
        self.assertEqual(chromatogram.get_xlabels('UV').size, 2403)
        self.assertEqual(chromatogram.get_ylabels('UV').size, 1)
        self.assertTupleEqual(chromatogram.get_data('UV').shape, (2403, 1))

        uv_path = "data/uv_ms/uv.csv"
        f = open(uv_path)
        uv_data = f.read().splitlines()
        f.close()
        self.assertListEqual(uv_data, chromatogram.to_str('UV').splitlines())
        
        uv_metadata = {
            'notebook': '0416044-0032', 
            'date': '10-May-18, 17:43:49', 
            'method': 'RM_HPLC.M', 
            'instrument': 'Asterix ChemStation', 
            'unit': 'mAU', 
            'signal': 'DAD1A, Sig=215.0,16.0  Ref=off'
        }
        self.assertDictEqual(uv_metadata, chromatogram.get_metadata('UV'))

        # MS tests. 
        self.assertEqual(chromatogram.get_xlabels('MS').size, 316)
        self.assertEqual(chromatogram.get_ylabels('MS').size, 824)
        self.assertTupleEqual(chromatogram.get_data('MS').shape, (316, 824))

        ms_path = "data/uv_ms/ms.csv"
        f = open(ms_path)
        ms_data = f.read().splitlines()
        f.close()
        self.assertListEqual(ms_data, chromatogram.to_str('MS').splitlines())
        
        ms_metadata = {
            'time': '10 May 18   5:43 pm -0500', 
            'method': 'RM_HPLC.M'
        } 
        self.assertDictEqual(ms_metadata, chromatogram.get_metadata('MS'))

    def test_agilent_ms_fid(self):
        """
        Tests a directory containing MS and FID data. 
        
        """
        dirpath = "data/ms_fid/cedrol_mix_01.D"
        chromatogram = parser.read(dirpath)
        
        self.assertCountEqual(chromatogram.get_detectors(), ['MS', 'FID'])

        # MS tests. 
        self.assertEqual(chromatogram.get_xlabels('MS').size, 7279)
        self.assertEqual(chromatogram.get_ylabels('MS').size, 271)
        self.assertTupleEqual(chromatogram.get_data('MS').shape, (7279, 271))

        ms_path = "data/ms_fid/ms.csv"
        f = open(ms_path)
        ms_data = f.read().splitlines()
        f.close()
        self.assertListEqual(ms_data, chromatogram.to_str('MS').splitlines())
        
        ms_metadata = {
            'time': '14 Jan 22  01:29 pm', 
            'method': 'Rt-bDEX-SE_mcminn.M'
        } 
        self.assertDictEqual(ms_metadata, chromatogram.get_metadata('MS'))

        # FID tests.
        self.assertEqual(chromatogram.get_xlabels('FID').size, 54285)
        self.assertEqual(chromatogram.get_ylabels('FID').size, 1)
        self.assertTupleEqual(chromatogram.get_data('FID').shape, (54285, 1))

        fid_path = "data/ms_fid/fid.csv"
        f = open(fid_path)
        fid_data = f.read().splitlines()
        f.close()
        self.assertListEqual(fid_data, chromatogram.to_str('FID').splitlines())
        
        fid_metadata = {
            'notebook': 'cedrol_mix_01', 
            'date': '14 Jan 22  01:29 pm', 
            'method': 'Rt-bDEX-SE_mcminn.M', 
            'instrument': 'Mustang ChemStation', 
            'unit': 'pA', 
            'signal': 'Front Signal'
        }
        self.assertDictEqual(fid_metadata, chromatogram.get_metadata('FID'))

    def test_agilent_sim_fid(self):
        """
        Tests a directory containing MS (SIM) and FID data. 
        
        """
        dirpath = "data/sim_fid/caye_nmr_test_mix.D"
        chromatogram = parser.read(dirpath)
        
        self.assertCountEqual(chromatogram.get_detectors(), ['MS', 'FID'])

        # MS (SIM) tests.
        self.assertEqual(chromatogram.get_xlabels('MS').size, 1309)
        self.assertEqual(chromatogram.get_ylabels('MS').size, 2)
        self.assertTupleEqual(chromatogram.get_data('MS').shape, (1309, 2))

        ms_path = "data/sim_fid/sim.csv"
        f = open(ms_path)
        ms_data = f.read().splitlines()
        f.close()
        self.assertListEqual(ms_data, chromatogram.to_str('MS').splitlines())
        
        ms_metadata = {
            'time': '17 Dec 19  10:04 am', 
            'method': 'HP-5MS_HTAchiral_da'
        }
        self.assertDictEqual(ms_metadata, chromatogram.get_metadata('MS'))

        # FID tests. 
        self.assertEqual(chromatogram.get_xlabels('FID').size, 10197)
        self.assertEqual(chromatogram.get_ylabels('FID').size, 1)
        self.assertTupleEqual(chromatogram.get_data('FID').shape, (10197, 1))

        fid_path = "data/sim_fid/fid.csv"
        f = open(fid_path)
        fid_data = f.read().splitlines()
        f.close()
        self.assertListEqual(fid_data, chromatogram.to_str('FID').splitlines())
        
        fid_metadata = {
            'date': '17 Dec 19  10:04 am', 
            'method': 'HP-5MS_HTAchiral_da_100-300_simscan.M', 
            'instrument': 'Mustang ChemStation', 
            'unit': 'pA', 
            'signal': 'Front Signal'
        } 
        self.assertDictEqual(fid_metadata, chromatogram.get_metadata('FID'))


if __name__ == '__main__':
    unittest.main()