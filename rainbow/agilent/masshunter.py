"""
Methods for parsing Agilent Masshunter files.

Supports two MS storage formats found in AcqData/:
  - MSProfile.bin  : HRMS profile data (original rainbow implementation)
  - MSPeak.bin     : centroided peak data (added implementation)

The format is auto-detected from the files present in AcqData/.
"""
import os
import struct
import numpy as np
try:
    import lzf as _lzf
    _LZF_AVAILABLE = True
except ImportError:
    _lzf = None
    _LZF_AVAILABLE = False
from lxml import etree
from rainbow import DataFile


# ── Record layout for MSScan.bin (MSPeak.bin variant) ─────────────────────────
#
# Each record is 184 bytes, structured as two blocks:
#
#   PREAMBLE (bytes 0–71) — spectrum pointer block, not defined in MSScan.xsd:
#     +000  4×5  unknown header fields     (5 × int32)
#     +020  4    SpectrumFormatID          (int32)
#     +024  8    SpectrumOffset            (int64)  byte offset into MSPeak.bin
#     +032  4    ByteCount                 (int32)  total bytes for this scan's peaks
#     +036  4    PointCount                (int32)  number of peaks
#     +040  8    MinY                      (double) DBL_MAX sentinel = unset
#     +048  8    MaxY                      (double) max intensity in scan
#     +056  8    MinX                      (double)
#     +064  8    MaxX                      (double)
#
#   XSD SCANRECORD (bytes 72–183) — matches MSScan.xsd ScanRecordType:
#     +072  4    ScanID                    (int32)
#     +076  4    ScanMethodID              (int32)
#     +080  4    TimeSegmentID             (int32)
#     +084  8    ScanTime                  (double) retention time in minutes
#     +092  4    MSLevel                   (int32)
#     +096  4    ScanType                  (int32)
#     +100  8    TIC                       (double)
#     +108  8    BasePeakMZ                (double)
#     +116  8    BasePeakValue             (double)
#     +124  4    CycleNumber               (int32)
#     +128  4    Status                    (int32)
#     +132  4    IonMode                   (int32)
#     +136  4    IonPolarity               (int32)
#     +140  8    Fragmentor                (double)
#     +148  8    CollisionEnergy           (double)
#     +156  8    MzOfInterest              (double)
#     +164  8    SamplingPeriod            (double)
#     +172  8    MeasuredMassRangeMin      (double)
#     +180  4    (trailing field)          (int32)
#
# MSPeak.bin peak encoding is determined by ByteCount / PointCount:
#   8  bytes/peak → float32 mz + float32 intensity  (low-res single quad)
#   12 bytes/peak → float64 mz + float32 intensity  (some QTOF)
#   16 bytes/peak → float64 mz + float64 intensity  (high-res, confirmed)

_MSPEAK_RECORD_FORMAT = (
    '<'
    'iiiii'   # +000 unknown ×5
    'i'       # +020 SpectrumFormatID
    'q'       # +024 SpectrumOffset
    'i'       # +032 ByteCount
    'i'       # +036 PointCount
    'dddd'    # +040 MinY, MaxY, MinX, MaxX
    'iii'     # +072 ScanID, ScanMethodID, TimeSegmentID
    'd'       # +084 ScanTime
    'ii'      # +092 MSLevel, ScanType
    'ddd'     # +100 TIC, BasePeakMZ, BasePeakValue
    'iiii'    # +124 CycleNumber, Status, IonMode, IonPolarity
    'ddddd'   # +140 Fragmentor, CollisionEnergy, MzOfInterest,
              #      SamplingPeriod, MeasuredMassRangeMin
    'i'       # +180 trailing int32
)
_MSPEAK_RECORD_SIZE   = struct.calcsize(_MSPEAK_RECORD_FORMAT)
_MSPEAK_HEADER_OFFSET = 0x58

assert _MSPEAK_RECORD_SIZE == 184, (
    f"MSPeak record size mismatch: expected 184, got {_MSPEAK_RECORD_SIZE}"
)

# Field names matching the format string above
_MSPEAK_FIELD_NAMES = [
    'unk0', 'unk1', 'unk2', 'unk3', 'unk4',
    'spectrum_format_id', 'spectrum_offset', 'byte_count', 'point_count',
    'min_y', 'max_y', 'min_x', 'max_x',
    'scan_id', 'scan_method_id', 'time_segment_id',
    'scan_time',
    'ms_level', 'scan_type',
    'tic', 'base_peak_mz', 'base_peak_value',
    'cycle_number', 'status', 'ion_mode', 'ion_polarity',
    'fragmentor', 'collision_energy', 'mz_of_interest',
    'sampling_period', 'measured_mz_min',
    'unk_last',
]


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def parse_allfiles(path, prec=0):
    """
    Finds and parses Agilent Masshunter data files.

    Supports both MSProfile.bin (HRMS profile) and MSPeak.bin (centroided)
    formats. The format is auto-detected from the files present in AcqData/.

    Args:
        path (str): Path to the Agilent .D directory.
        prec (int, optional): Number of decimals to round ylabels (m/z values).

    Returns:
        List containing a DataFile for each parsed file.
    """
    datafiles = []

    acqdata_path = os.path.join(path, "AcqData")
    if not os.path.isdir(acqdata_path):
        return datafiles

    acqdata_files = set(os.listdir(acqdata_path))

    if {"MSTS.xml", "MSScan.xsd", "MSScan.bin"} <= acqdata_files:
        if "MSProfile.bin" in acqdata_files:
            datafiles.append(parse_msdata(acqdata_path, prec))
        elif "MSPeak.bin" in acqdata_files:
            datafiles.append(parse_mspeak_data(acqdata_path, prec))

    return datafiles


# ══════════════════════════════════════════════════════════════════════════════
# MSProfile.bin  (original rainbow implementation, unchanged)
# ══════════════════════════════════════════════════════════════════════════════

def parse_msdata(path, prec=0):
    """
    Parses Masshunter HRMS data stored in MSProfile.bin.

    IMPORTANT: This method only supports MSProfile.bin.
    For centroided data in MSPeak.bin, use :func:`parse_mspeak_data`.

    The following files are used (in order of listing): 
        - MSTS.xml -> Number of retention times.
        - MSScan.xsd -> File structure of MSScan.bin.
        - MSScan.bin -> Offsets and compression info for MSProfile.bin.
        - MSMassCal.bin -> Calibration info for masses.
          - MSProfile.bin -> Actual data values. (LZF compressed).

    Learn more about this file format :ref:`here <hrms>`.

    Args:
        path (str): Path to the AcqData subdirectory.
        prec (int, optional): Number of decimals to round mz values.

    Returns:
        DataFile containing Masshunter HRMS MS data.
    """
    if not _LZF_AVAILABLE:
        raise ImportError(
            "The 'python-lzf' package is required for MSProfile.bin data.\n"
            "Install it with:  pip install python-lzf\n"
            "For MSPeak.bin data use parse_mspeak_data() instead."
        )

         # MSTS.xml: Extract number of retention times. 
    # In future work, this step could potentially be skipped by reading 
    #    MSScan.bin until EOF and counting the offsets. 
    # This would remove reliance on MSTS.xml being in the directory.
    tree = etree.parse(os.path.join(path, "MSTS.xml"))
    root = tree.getroot()
    num_times = 0
    for time_seg in root.findall("TimeSegment"):
        num_times += int(time_seg.find("NumOfScans").text)

    # MSScan.xsd: Extract the file structure of MSScan.bin. 
    # There are "simple" types can be directly translated into number types.
    # But there are "complex" types that are made up of other
    #     "simple" and "complex" types.
    # These are stored in a dictionary to enable recursive parsing. 
    tree = etree.parse(os.path.join(path, "MSScan.xsd"))
    root = tree.getroot()
    namespace = tree.xpath('namespace-uri(.)')
    complextypes_dict = {}
    for complextype in root.findall(f"{{{namespace}}}complexType"):
        innertypes = []
        for element in complextype[0].findall(f"{{{namespace}}}element"):
            innertypes.append((element.get('name'), element.get('type')))
        complextypes_dict[complextype.get('name')] = innertypes

    # MSScan.bin: Extract information about MSProfile.bin. 
    # For each retention time, this includes: 
    #   - the retention time itself 
    #   - starting offset of data in MSProfile.bin
    #   - length in bytes of the compressed data 
    #   - length in bytes of the uncompressed data 
    #   - number of masses recorded at the retention time
    # Future work could determine if the data blocks for each retention time 
    #     are always contiguous. If that is the case, the offset is unneeded. 
    f = open(os.path.join(path, "MSScan.bin"), 'rb')
    f.seek(0x58) # start offset
    f.seek(struct.unpack('<I', f.read(4))[0])
    data_info = np.empty(num_times, dtype=object)
    for i in range(num_times):
        # "ScanRecordType" is always the name of the root "complex" type.
        scan_info = read_complextype(f, complextypes_dict, "ScanRecordType")
        spectrum_info = scan_info['SpectrumParamValues']
        data_info[i]  = (
            scan_info['ScanTime'],
            spectrum_info['PointCount'],
            spectrum_info['SpectrumOffset'],
            spectrum_info['ByteCount'],
            spectrum_info['UncompressedByteCount']
        )
    f.close()

    # MSMassCal.bin: Extract calibration values for masses. 
    # There seem to be 10 doubles stored for each retention time. But this
    #     method only uses the first 2. Future work could determine what the
    #     other 8 doubles are used for.
    f = open(os.path.join(path, "MSMassCal.bin"), 'rb')
    f.seek(0x4c) # start offset
    calib_vals = np.ndarray((num_times, 2), '<d', f.read(), 0, (84, 8))
    f.close()

    # # MSProfile.bin: Extract the data values (decompress and decode intensities). 
    # The raw bytes are decompressed using the `python-lzf` library. 
    # This code may be slow. We note that LZF decompression seems to not
    #     rely on being decoded in smaller blocks as the code suggests. 
    #     Future work could potentially implement numpy speedups by
    #     decompressing all the bytes at once and using clever indexing. 
    f = open(os.path.join(path, "MSProfile.bin"), 'rb')
    twodoubles_unpack = struct.Struct('<dd').unpack
    times            = np.empty(num_times)
    num_mz_per_time  = np.empty(num_times)
    mz_list          = []
    intensity_bytearr = bytearray()
    for i in range(num_times):
        time, num_mz, offset, comp_len, decomp_len = data_info[i]
        times[i]           = time
        num_mz_per_time[i] = num_mz

        # Decompress the bytes for the current retention time. 
        f.seek(offset)
        comp_bytes   = f.read(comp_len)
        decomp_bytes = _lzf.decompress(comp_bytes, decomp_len)
        decomp_view  = memoryview(decomp_bytes)

        # Calculate the calibrated mz values. 
        start_mz, delta_mz = twodoubles_unpack(decomp_view[:16])
        mzs = np.arange(
            start_mz,
            start_mz + delta_mz * (num_mz - 1) + 1e-3,
            delta_mz
        )
        coeff, base = calib_vals[i]
        mzs -= base
        mzs *= coeff
        mzs **= 2

        mz_list.extend(mzs.tolist())
        intensity_bytearr.extend(decomp_view[16:])

    # Process the extracted data values. 
    mz_arr = np.round(np.array(mz_list), prec)
    intensities = np.ndarray(mz_arr.size, '<I', bytes(intensity_bytearr))

    # Make the array of ylabels containing mz values. 
    mz_ylabels = np.unique(mz_arr)
    mz_ylabels.sort()

    # Fill the `data` array containing intensities. 
    # Optimized using numpy vectorization.
    mz_indices = np.searchsorted(mz_ylabels, mz_arr)
    data = np.zeros((num_times, mz_ylabels.size), dtype=np.uint64)
    cur_index = 0
    for i in range(num_times):
        stop_index = cur_index + int(num_mz_per_time[i])
        np.add.at(
            data[i],
            mz_indices[cur_index:stop_index],
            intensities[cur_index:stop_index]
        )
        cur_index = stop_index

    f.close()

    return DataFile("MSProfile.bin", 'MS', times, mz_ylabels, data, {})


# ══════════════════════════════════════════════════════════════════════════════
# MSPeak.bin  (new implementation)
# ══════════════════════════════════════════════════════════════════════════════

def parse_mspeak_data(path, prec=0):
    """
    Parses Masshunter centroided MS data stored in MSPeak.bin.

    This format stores picked/centroided peaks rather than the full profile.
    It is produced by single-quadrupole and some QTOF GC-MS instruments
    running MassHunter acquisition software.

    The following files are used:
        - MSTS.xml   → Total number of scans.
        - MSScan.bin → Per-scan metadata and pointers into MSPeak.bin.
        - MSPeak.bin → Raw (mz, intensity) peak pairs.

    The returned DataFile matches the same interface as :func:`parse_msdata`:

    - ``xlabels`` — 1D array of retention times in minutes, shape (n_scans,)
    - ``ylabels`` — 1D array of unique rounded m/z values, shape (n_mz,)
    - ``data``    — 2D intensity array, shape (n_scans × n_mz), dtype float64

    Because centroided data is sparse (each scan has only a few peaks),
    most entries in ``data`` are zero. This is the same convention used
    by :func:`parse_msdata` for MSProfile.bin data.

    The ``metadata`` dict contains per-scan information extracted from
    MSScan.bin:

    - ``tic``            — 1D array of total ion currents
    - ``base_peak_mz``   — 1D array of base peak m/z values
    - ``base_peak_value``— 1D array of base peak intensities
    - ``ms_level``       — 1D array of MS levels (1 = MS1)
    - ``scan_type``      — 1D array of scan type codes
    - ``ion_mode``       — 1D array of ionisation mode codes
    - ``ion_polarity``   — 1D array of polarity codes (0 = positive)

    Args:
        path (str): Path to the AcqData subdirectory.
        prec (int, optional): Number of decimals to round m/z values.
            Use 0 for unit-resolution (default), 2-4 for high-resolution.

    Returns:
        DataFile containing centroided Masshunter MS data.
    """
    # ── Step 1: total scan count from MSTS.xml ─────────────────────────────
    tree      = etree.parse(os.path.join(path, "MSTS.xml"))
    root      = tree.getroot()
    num_scans = sum(
        int(ts.find("NumOfScans").text)
        for ts in root.findall("TimeSegment")
    )

    # ── Step 2: parse MSScan.bin — one 184-byte record per scan ────────────
    scan_records = _parse_msscan_bin(os.path.join(path, "MSScan.bin"),
                                     num_scans)

    # ── Step 3: read peak data from MSPeak.bin ─────────────────────────────
    spectra = _parse_mspeak_bin(os.path.join(path, "MSPeak.bin"),
                                scan_records)

    # ── Step 4: build xlabels (retention times) ────────────────────────────
    times = np.array([r['scan_time'] for r in scan_records])

    # ── Step 5: collect all m/z values and build ylabels ──────────────────
    all_mz = np.concatenate(
        [mz for _, mz, _ in spectra if len(mz) > 0]
    ) if any(len(mz) > 0 for _, mz, _ in spectra) else np.array([])

    if all_mz.size == 0:
        # No peaks at all — return empty DataFile
        return DataFile(
            "MSPeak.bin", 'MS',
            times,
            np.array([], dtype=np.float64),
            np.zeros((num_scans, 0), dtype=np.float64),
            {}
        )

    mz_ylabels = np.unique(np.round(all_mz, prec))
    mz_ylabels.sort()

    # ── Step 6: fill the 2D intensity array ───────────────────────────────
    # Rows = scans, columns = m/z bins (same convention as MSProfile.bin)
    data = np.zeros((num_scans, mz_ylabels.size), dtype=np.float64)
    for i, (_, mz_arr, int_arr) in enumerate(spectra):
        if len(mz_arr) == 0:
            continue
        mz_rounded = np.round(mz_arr, prec)
        indices    = np.searchsorted(mz_ylabels, mz_rounded)
        # Guard against out-of-bounds (rounding edge cases)
        valid      = indices < mz_ylabels.size
        np.add.at(data[i], indices[valid], int_arr[valid])

    # ── Step 7: build metadata dict ────────────────────────────────────────
    metadata = {
        'tic'            : np.array([r['tic']              for r in scan_records]),
        'base_peak_mz'   : np.array([r['base_peak_mz']     for r in scan_records]),
        'base_peak_value': np.array([r['base_peak_value']  for r in scan_records]),
        'ms_level'       : np.array([r['ms_level']         for r in scan_records]),
        'scan_type'      : np.array([r['scan_type']        for r in scan_records]),
        'ion_mode'       : np.array([r['ion_mode']         for r in scan_records]),
        'ion_polarity'   : np.array([r['ion_polarity']     for r in scan_records]),
    }

    return DataFile("MSPeak.bin", 'MS', times, mz_ylabels, data, metadata)


# ══════════════════════════════════════════════════════════════════════════════
# Private helpers for MSPeak.bin parsing
# ══════════════════════════════════════════════════════════════════════════════

def _parse_msscan_bin(filepath, num_scans):
    """
    Reads MSScan.bin and returns a list of dicts, one per scan.

    Each dict contains the fields listed in _MSPEAK_FIELD_NAMES, giving
    the scan's retention time, TIC, base peak, and a pointer
    (spectrum_offset, byte_count, point_count) into MSPeak.bin.
    """
    records = []
    with open(filepath, 'rb') as f:
        f.seek(_MSPEAK_HEADER_OFFSET)
        for _ in range(num_scans):
            raw = f.read(_MSPEAK_RECORD_SIZE)
            if len(raw) < _MSPEAK_RECORD_SIZE:
                break
            fields = struct.unpack(_MSPEAK_RECORD_FORMAT, raw)
            records.append(dict(zip(_MSPEAK_FIELD_NAMES, fields)))
    return records


def _parse_mspeak_bin(filepath, scan_records):
    """
    Reads MSPeak.bin using the offsets stored in scan_records.

    Returns a list of (scan_time, mz_array, intensity_array) tuples.

    The bytes-per-peak (bpp) is derived from ByteCount / PointCount:
      bpp == 8  → float32 mz  + float32 intensity
      bpp == 12 → float64 mz  + float32 intensity
      bpp == 16 → float64 mz  + float64 intensity  (this instrument)
    """
    spectra = []
    with open(filepath, 'rb') as f:
        for rec in scan_records:
            n_pts  = rec['point_count']
            offset = rec['spectrum_offset']
            b_cnt  = rec['byte_count']

            if n_pts <= 0 or b_cnt <= 0 or offset < 0:
                spectra.append((rec['scan_time'],
                                np.array([], dtype=np.float64),
                                np.array([], dtype=np.float64)))
                continue

            bpp = b_cnt // n_pts

            f.seek(offset)
            raw = f.read(b_cnt)

            if len(raw) < b_cnt:
                spectra.append((rec['scan_time'],
                                np.array([], dtype=np.float64),
                                np.array([], dtype=np.float64)))
                continue

            if bpp == 8:
                data    = np.frombuffer(raw, dtype='<f4').reshape(n_pts, 2)
                mz_arr  = data[:, 0].astype(np.float64)
                int_arr = data[:, 1].astype(np.float64)

            elif bpp == 16:
                # Layout: first half = n_pts x float64 nominal m/z,
                #         second half = n_pts x float64 intensity.
                # NOT interleaved pairs - two separate contiguous blocks.
                half    = n_pts * 8
                mz_arr  = np.frombuffer(raw[:half], dtype='<f8').copy()
                int_arr = np.frombuffer(raw[half:], dtype='<f8').copy()

            elif bpp == 12:
                mz_arr  = np.array([
                    struct.unpack_from('<d', raw, i * 12)[0]
                    for i in range(n_pts)
                ])
                int_arr = np.array([
                    struct.unpack_from('<f', raw, i * 12 + 8)[0]
                    for i in range(n_pts)
                ])

            else:
                # Unknown format — emit empty and warn
                import warnings
                warnings.warn(
                    f"Unknown bytes-per-peak={bpp} at "
                    f"RT={rec['scan_time']:.3f} min. Skipping scan.",
                    RuntimeWarning
                )
                spectra.append((rec['scan_time'],
                                np.array([], dtype=np.float64),
                                np.array([], dtype=np.float64)))
                continue

            spectra.append((rec['scan_time'], mz_arr, int_arr))

    return spectra


# ══════════════════════════════════════════════════════════════════════════════
# XSD-based helpers (used by parse_msdata, unchanged from original)
# ══════════════════════════════════════════════════════════════════════════════

def read_complextype(f, complextypes_dict, name):
    """ 
    Reads a "complex" type from :obj:`f`. Used only for MSScan.bin. 

    Mutually recurs with :obj:`read_type`.

    Args:
        f (_io.BufferedReader): File opened in 'rb' mode.
        complextypes_dict (dict): Dictionary defining all "complex" types.
        name (str): Name of the "complex" type to parse. 

    Returns:
        Dictionary mapping subtype names to values. \
        If the subtype is "complex", the value is a nested dictionary. \
        Otherwise, the value is a number.
        
    """ 
    desc_to_value = {}
    for subname, subtype in complextypes_dict[name]:
        desc_to_value[subname] = read_type(f, complextypes_dict, subtype)
    return desc_to_value


def read_type(f, complextype_dict, name):
    """
    Reads a type from :obj:`f`. Used only for MSScan.bin. 

    Used only for MSProfile.bin parsing via MSScan.xsd.
    Mutually recurs with :obj:`read_complextype`.

    Args:
        f (_io.BufferedReader): File opened in 'rb' mode.
        complextypes_dict (dict): Dictionary defining all "complex" types.
        name (str): Name of the type to parse. 

    Returns:
        A numeric value for simple types, or a dict for complex types.
    """
    if name == 'xs:byte':
        return struct.unpack('c', f.read(1))[0]
    elif name == 'xs:short':
        return struct.unpack('<H', f.read(2))[0]
    elif name == 'xs:int':
        return struct.unpack('<I', f.read(4))[0]
    elif name == 'xs:long':
        return struct.unpack('<Q', f.read(8))[0]
    elif name == 'xs:float':
        return struct.unpack('<f', f.read(4))[0]
    elif name == 'xs:double':
        return struct.unpack('<d', f.read(8))[0]
    return read_complextype(f, complextype_dict, name)
