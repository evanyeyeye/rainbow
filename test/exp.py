# This temporary file is used for exploratory testing.

from rainbow import parser


data_folders = [
    "uv_ms/100518-RM_HPLC-01970.D",
    "uv/caffeine.D",
    "ms_fid/cedrol_mix_01.D",
    "sim_fid/caye_nmr_test_mix.D"
]

chromatogram = parser.read("data/" + data_folders[3])

detector = 'MS'

print("X labels:")
print(chromatogram.xlabels[detector].shape)
print()

print("Y labels:")
print(chromatogram.ylabels[detector].shape)
print()

print("Data array:")
print(chromatogram.data[detector].shape)
print()

print("Metadata:")
print(chromatogram.metadata[detector])
print()

print("Sample traces:")
traces = chromatogram.extract_traces(detector)
print(traces)

chromatogram.export_csv("test.csv", detector)
# chromatogram.plot(detector, 210)