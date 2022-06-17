# This temporary file is used for exploratory testing.

from rainbow import parser


data_folders = [
    "uv_ms/100518-RM_HPLC-01970.D",
    "uv/caffeine.D",
    "ms_fid/cedrol_mix_01.D",
    "sim_fid/caye_nmr_test_mix.D"
]

datadir = parser.read("data/" + data_folders[2])

print(datadir)