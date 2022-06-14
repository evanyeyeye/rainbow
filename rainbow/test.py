# This temporary file is used for exploratory testing.

import rainbow.parser


data_folders = [
    "100518-RM_HPLC-01970.D",
    "caffeine.D",
    "cedrol_mix_01.D",
    "caye_nmr_test_mix.D"
]

chromatogram = parser.read("../data/" + data_folders[1])

print("X labels:")
print(chromatogram.xlabels)
print()

print("Y labels:")
print(chromatogram.ylabels)
print()

print("Data array:")
print(chromatogram.data)
print()

print("Metadata:")
print(chromatogram.metadata)
print()

print("Sample traces:")
traces = chromatogram.extract_traces('UV')
print(traces)

chromatogram.export_csv("test.csv", 'UV')
chromatogram.plot('UV', 210)

# a=0
# e = chromatogram.data['FID']
# f = open("caye_nmr_test_mix.csv").readlines()[1:]
# for i in range(len(f)):
#     d = int(float(f[i][:-1].split(',')[3]))
#     if e[i] != d:
#         a += 1
#         print(i, e[i], d)
# print(a)