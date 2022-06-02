# Unit tests not implemented yet, this temporary file just 
# serves to verify that the parser works as desired

import parser

chromatogram = parser.read("../data/caffeine.D")
print(chromatogram.get_X())
print(chromatogram.get_Y())
print(chromatogram.get_Ylabels())
print(chromatogram.get_detectors())
print(chromatogram.get_metadata())