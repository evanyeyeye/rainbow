# Unit tests not implemented yet, this temporary file just 
# serves to verify that the parser works as desired

import parser

chromatogram = parser.read("../data/caffeine.D")
print("X values")
print(chromatogram.get_X())
print("Y values")
print(chromatogram.get_Y())
print("Y labels")
print(chromatogram.get_Ylabels())
print("Detectors")
print(chromatogram.get_detectors())
print("Metadata")
print(chromatogram.get_metadata())
print("Sample traces")
print(chromatogram.extract_traces("UV", [210, 212]))
chromatogram.export_csv("test.csv", "UV", [210, 212])
chromatogram.plot("UV", 210)