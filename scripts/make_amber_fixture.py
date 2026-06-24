"""
Build the tests/inputs/amber.D fixture.

amber.D is the project's only many-scan HRMS fixture. It backs the real-world
binning heatmap in the documentation (docs/source/agilent/hrms_data_model.rst,
fig "worked example"), which needs many scans so per-scan calibration drift is
visible across a run.

It is a 500-scan slice of the same real Agilent Q-TOF acquisition that cyan.D /
magenta.D are 3-scan slices of (issue #27). To stay small (~0.6 MB) it is
*windowed in m/z*: each scan's MSProfile.bin segment is decoded, sliced to the
flight-time index range covering m/z ~823.8-827.2 (about 0.2% of the points), and
re-encoded to the same run-length format. The MSScan.bin records are patched in
place to point at the new segments; only the files needed to parse are kept
(MSScan.xsd, MSMassCal.bin, DefaultMassCal.xml), so no sample/method names are
copied.

The source acquisition is NOT committed (real data lives under the gitignored
data/). Run this from the repo root with that data present to regenerate amber.D::

    PYTHONPATH=. python3 scripts/make_amber_fixture.py
"""
import os
import struct
import shutil

import numpy as np

import rainbow as rb
from rainbow.agilent import masshunter as M

SRC = "data/57692v1.d"
DST = "tests/inputs/amber.D"
N = 500                                   # scans to keep
MZ_LO, MZ_HI = 823.8, 827.2               # m/z window (mapped to flight indices)


def encode_rle(inten):
    """ Encode uint32 intensities back into the MSProfile.bin RLE body that
    decompress_inten_list reads: a ``count | 0x90<<24`` word, a negated
    leading-zero count, then 4-byte literals and ``-(run*4 + 3)`` zero-run
    controls (which keep the 4-byte width). """
    inten = np.asarray(inten, dtype=np.int64)
    assert inten.max() < 2 ** 31, "intensity too large for a 4-byte literal"
    n = len(inten)
    nz = np.nonzero(inten)[0]
    body = bytearray(struct.pack("<I", n | (0x90 << 24)))
    if nz.size == 0:
        body += struct.pack("<i", -n)
        return bytes(body)
    leading, last = int(nz[0]), int(nz[-1])
    body += struct.pack("<i", -leading)
    i = leading
    while i <= last:
        v = int(inten[i])
        if v != 0:
            body += struct.pack("<i", v)
            i += 1
        else:
            run = 0
            while i <= last and inten[i] == 0:
                run += 1
                i += 1
            body += struct.pack("<i", -(run * 4 + 3))
    return bytes(body)


def main():
    src_acq, dst_acq = os.path.join(SRC, "AcqData"), os.path.join(DST, "AcqData")
    ct = M.parse_scan_xsd(os.path.join(src_acq, "MSScan.xsd"))
    recs = M.read_scan_records(
        os.path.join(src_acq, "MSScan.bin"), ct, M.count_scans(SRC))
    stride = M.type_size(ct, "ScanRecordType")          # profile-only: one block
    with open(os.path.join(src_acq, "MSScan.bin"), "rb") as f:
        f.seek(0x58)
        rec_start = struct.unpack("<I", f.read(4))[0]
        f.seek(0)
        msscan = f.read()

    # m/z window -> a fixed flight-time index range (the tof grid is shared).
    mz0 = rb.read(SRC, hrms=True).get_file("MSProfile.bin").mass_labels(0)
    win = np.where((mz0 >= MZ_LO) & (mz0 <= MZ_HI))[0]
    jlo, jhi = int(win[0]), int(win[-1]) + 1

    twod = struct.Struct("<dd")
    new_profile = bytearray()
    new_msscan = bytearray(msscan[:rec_start])
    with open(os.path.join(src_acq, "MSProfile.bin"), "rb") as pf:
        for i in range(N):
            spv = recs[i]["SpectrumParamValues"]
            pf.seek(spv["SpectrumOffset"])
            comp = pf.read(spv["ByteCount"])
            start_mz, delta = twod.unpack(comp[:16])
            inten = M.decompress_inten_list(
                memoryview(comp)[16:], spv["PointCount"])
            seg = (twod.pack(start_mz + jlo * delta, delta)
                   + encode_rle(inten[jlo:jhi]))
            new_off = len(new_profile)
            new_profile += seg
            rec = bytearray(msscan[rec_start + i*stride:rec_start + (i+1)*stride])
            struct.pack_into("<q", rec, 132, new_off)       # SpectrumOffset
            struct.pack_into("<i", rec, 140, len(seg))      # ByteCount
            struct.pack_into("<i", rec, 144, jhi - jlo)     # PointCount
            struct.pack_into("<i", rec, 148, 0)             # UncompressedByteCount
            new_msscan += rec

    os.makedirs(dst_acq, exist_ok=True)
    with open(os.path.join(dst_acq, "MSProfile.bin"), "wb") as f:
        f.write(new_profile)
    with open(os.path.join(dst_acq, "MSScan.bin"), "wb") as f:
        f.write(new_msscan)
    for fn in ("MSScan.xsd", "MSMassCal.bin", "DefaultMassCal.xml"):
        shutil.copy(os.path.join(src_acq, fn), os.path.join(dst_acq, fn))

    # Verify the windowed fixture decodes to exactly the original windowed scans.
    new = rb.read(DST, hrms=True).get_file("MSProfile.bin")
    with open(os.path.join(src_acq, "MSProfile.bin"), "rb") as pf:
        for i in (0, N // 2, N - 1):
            spv = recs[i]["SpectrumParamValues"]
            pf.seek(spv["SpectrumOffset"])
            comp = pf.read(spv["ByteCount"])
            orig = M.decompress_inten_list(
                memoryview(comp)[16:], spv["PointCount"])[jlo:jhi]
            assert np.array_equal(orig, new.data[i]), f"mismatch at scan {i}"
    print(f"wrote {DST}: {new.data.shape} scans x points, "
          f"{sum(os.path.getsize(os.path.join(dst_acq, f)) for f in os.listdir(dst_acq)) // 1024} KB")


if __name__ == "__main__":
    main()
