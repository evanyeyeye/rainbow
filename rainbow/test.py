# Unit tests not implemented yet, this temporary file just 
# serves to verify that the parser works as desired.

import parser


data_folders = [
    "100518-RM_HPLC-01970.D",
    "caffeine.D",
    "cedrol_mix_01.D",
    "caye_nmr_test_mix.D"
]

chromatogram = parser.read("../data/" + data_folders[2])

print(chromatogram.xlabels)
print(chromatogram.ylabels)
print(chromatogram.data)
print(chromatogram.metadata)


# print("X values")
# print(chromatogram.get_X())
# print("Y values")
# print(chromatogram.get_Y())
# print("Y labels")
# print(chromatogram.get_Ylabels())
# print("Detectors")
# print(chromatogram.get_detectors())
# print("Metadata")
# print(chromatogram.get_metadata())
# print("Sample traces")
# print(chromatogram.extract_traces("UV", [210, 212]))
# chromatogram.export_csv("test.csv", "UV", [210, 212])
# chromatogram.plot("UV", 210)
# a=0
# e = chromatogram.data['FID']
# f = open("caye_nmr_test_mix.csv").readlines()[1:]
# for i in range(len(f)):
#     d = int(float(f[i][:-1].split(',')[3]))
#     if e[i] != d:
#         a += 1
#         print(i, e[i], d)
# print(a)