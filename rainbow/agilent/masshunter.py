""" 
Methods for parsing Agilent Masshunter files. 
 
"""
import os
import struct
import warnings
import numpy as np
from lxml import etree
from rainbow import DataFile

# NOTE: `lzf` (python-lzf) is imported lazily inside parse_msdata, and only
# when an LZF-compressed MSProfile.bin segment is actually encountered. The
# rest of this module - the scan-counting that replaces MSTS.xml and the
# run-length-encoded (Q-TOF) MSProfile.bin path - works without it installed.

# Optional compiled accelerator for the run-length MSProfile.bin decode. If it
# was not built (no compiler or no Cython at install time), decompress_inten_list
# falls back to the pure-Python loop transparently.
try:
    from rainbow.agilent import _msprofile as _msprofile_fast
except ImportError:
    _msprofile_fast = None


class ProfileDataFile(DataFile):
    """
    A high-resolution profile spectrum whose m/z axis is per-scan.

    Unlike a regular :class:`~rainbow.datafile.DataFile`, an HRMS profile has no
    single m/z axis. Every scan is sampled on the same raw flight-time grid
    (:attr:`tof`), so a column index is the same physical bin in every scan, but
    the flight-time-to-m/z calibration drifts from scan to scan. The m/z of a
    point therefore depends on both the scan and the point. Access a scan's m/z
    with :meth:`mass_labels` or :meth:`scan`; reading ``ylabels`` raises, because
    a single shared m/z axis does not exist (see :ref:`hrms-data-model`).

    Attributes:
        tof (numpy.ndarray): The shared flight-time axis, one value per column
            of ``data``, identical for every scan.
        data (numpy.ndarray): 2D intensities, shape ``(num_scans, num_points)``.
            Rows are scans (retention times); columns are flight-time bins.
        xlabels (numpy.ndarray): Retention time of each scan (row).
        mz_decimals (int or None): Decimals to round reported m/z to; None keeps
            full float precision.

    """
    def __init__(self, path, xlabels, tof, data, calib, use_flags, metadata,
                 mz_decimals=4):
        self.name = os.path.basename(path)
        self.detector = 'MS'
        self.xlabels = xlabels
        self.tof = tof
        self.data = data
        self._calib = calib
        self._use_flags = use_flags
        self.mz_decimals = mz_decimals
        self.metadata = metadata
        warnings.filterwarnings("ignore", category=FutureWarning)

    @property
    def ylabels(self):
        raise AttributeError(
            "An HRMS profile has a per-scan m/z axis (it drifts with "
            "calibration), so there is no single ylabels. Use "
            ".mass_labels(scan_index) for one scan's m/z, or .scan(i).")

    def mass_labels(self, i):
        """ The calibrated m/z values for scan ``i`` (rounded to
        :attr:`mz_decimals`). """
        mz = calibrate_mz(self.tof, self._calib[i], self._use_flags[i])
        if self.mz_decimals is not None:
            mz = np.round(mz, self.mz_decimals)
        return mz

    def scan(self, i):
        """ The native spectrum of scan ``i`` as ``(mass_labels, intensities)``,
        i.e. the per-scan m/z axis and that scan's intensities, with no binning
        and no inserted zeros. """
        return self.mass_labels(i), self.data[i]

    def get_info(self):
        n, k = self.data.shape
        return f"\n{'-' * len(self.name)}\n" \
               f"{self.name}\n" \
               f"{'-' * len(self.name)}\n" \
               f"Detector: {self.detector}\n" \
               f"Xlabels: {self.xlabels}\n" \
               f"Profile: {n} scans x {k} points " \
               f"(per-scan m/z; use scan(i)/mass_labels(i))\n" \
               f"TOF axis: {self.tof}\n" \
               f"Data: {self.data}\n" \
               f"Metadata: {self.metadata}\n"


"""
MAIN PARSING METHOD

"""

def parse_allfiles(path, prec=0, hrms=False, centroid=False):
    """
    Finds and parses Agilent Masshunter MS data files.

    MassHunter stores a scan's spectrum as a dense profile trace
    (``MSProfile.bin``) and/or a peak-picked centroid list (``MSPeak.bin``).
    Both are opt-in: ``hrms`` parses the profile and ``centroid`` parses the
    centroids (see :obj:`parse_msdata` and :obj:`parse_mspeakdata`). With
    neither flag set nothing is parsed here.

    Args:
        path (str): Path to the Agilent .D directory.
        prec (int, optional): Number of decimals to round ylabels.
        hrms (bool, optional): Parse the profile spectrum (MSProfile.bin).
        centroid (bool, optional): Parse the centroid spectrum (MSPeak.bin).

    Returns:
        List containing a DataFile for each parsed file.

    """
    datafiles = []

    acqdata_path = os.path.join(path, "AcqData")
    if not os.path.isdir(acqdata_path):
        return datafiles

    acqdata_files = set(os.listdir(acqdata_path))
    # MSTS.xml is no longer required: the scan count is recovered from the
    # MSScan.bin record geometry (see read_scan_records). This lets us parse
    # Agilent OpenLab .rslt/.sirslt result folders, which omit MSTS.xml.
    if {"MSScan.xsd", "MSScan.bin"} <= acqdata_files:
        # ICP-MS data is distinguished by the presence of MSScan_XSpecific.bin,
        # which records the per-isotope channels. Its MSProfile.bin is stored
        # uncompressed in a different layout than the HRMS one, so it needs a
        # dedicated parser, and it is parsed under the hrms flag like the HRMS
        # profile it stands in for.
        if "MSScan_XSpecific.bin" in acqdata_files:
            if hrms:
                datafiles.append(parse_icpmsdata(acqdata_path, prec))
        else:
            if centroid and "MSPeak.bin" in acqdata_files:
                datafiles.append(parse_mspeakdata(acqdata_path, prec))
            if hrms and "MSProfile.bin" in acqdata_files:
                datafiles.append(parse_msdata(acqdata_path, prec))

    return datafiles


"""
MS PARSING METHODS 

"""

def parse_msdata(path, prec=0, native=False):
    """
    Parses Masshunter MS data.

    IMPORTANT: Masshunter MS data can be either stored in MSProfile.bin or \
        MSPeak.bin. This method only supports parsing MSProfile.bin.  
    
    The following files are used (in order of listing):
        - MSScan.xsd -> File structure of MSScan.bin.
        - MSScan.bin -> Offsets, compression info, and scan count.
        - MSMassCal.bin -> Calibration info for masses.
        - MSProfile.bin -> Actual data values.

    The scan count is recovered by reading MSScan.bin to EOF, so MSTS.xml is \
        not required. This lets us parse OpenLab .rslt/.sirslt result \
        folders, which omit MSTS.xml.

    Learn more about this file format :ref:`here <hrms>`.

    By default the per-scan spectra are projected onto a single shared m/z grid
    (rounded to ``prec`` decimals), which is convenient for extracted-ion
    chromatograms and heatmaps but inserts zeros and loses resolution for
    high-resolution data (see :ref:`hrms-data-model`). With ``native=True`` the
    faithful per-scan representation is returned instead: a list of
    :class:`ProfileDataFile` objects (one per flight-time grid), each keeping the
    raw intensities and exposing the per-scan m/z via ``scan(i)``.

    Args:
        path (str): Path to the AcqData subdirectory.
        prec (int, optional): Number of decimals to round mz values (shared-grid
            mode only).
        native (bool, optional): Return the faithful per-scan representation (a
            list of :class:`ProfileDataFile`) instead of the shared grid.

    Returns:
        A :class:`~rainbow.datafile.DataFile` on the shared grid, or, when
        ``native=True``, a list of :class:`ProfileDataFile` (one per grid).

    """
    # MSScan.xsd: Extract the file structure of MSScan.bin.
    complextypes_dict = parse_scan_xsd(os.path.join(path, "MSScan.xsd"))

    # MSScan.bin: Read every scan record until EOF. The number of records is
    # the number of retention times - historically read from MSTS.xml, which
    # is absent in OpenLab result folders. For each retention time we keep:
    #   - the retention time itself
    #   - the number of masses recorded
    #   - the starting offset of the data in MSProfile.bin
    #   - the compressed length in bytes
    #   - the uncompressed length in bytes
    #   - the calibration id (selects a polynomial calibration; see below)
    scan_records = read_scan_records(
        os.path.join(path, "MSScan.bin"), complextypes_dict, count_scans(path))
    num_times = len(scan_records)
    data_info = [
        (rec['ScanTime'],
         rec['SpectrumParamValues']['PointCount'],
         rec['SpectrumParamValues']['SpectrumOffset'],
         rec['SpectrumParamValues']['ByteCount'],
         rec['SpectrumParamValues']['UncompressedByteCount'],
         rec.get('CalibrationID'))
        for rec in scan_records]

    # Mass calibration (see _load_calibration and calibrate_mz): the per-scan
    # 10 doubles and polynomial flags. A profile m/z axis is stored as raw
    # time-of-flight, so MSProfile.bin always needs the calibration.
    calib_vals, calib_flags = _load_calibration(
        path, [cid for *_, cid in data_info])
    if calib_vals is None:
        raise FileNotFoundError(
            "Cannot calibrate MSProfile.bin: neither MSMassCal.bin nor a "
            f"usable DefaultMassCal.xml was found in {path}.")

    # MSProfile.bin: Extract the data values.
    # Each retention time has a data segment that starts with two doubles
    #     (the smallest mz and the mz delta, before calibration), followed by
    #     the intensities. The intensities are stored in one of two ways:
    #       - LZF compression (the historically supported case). The whole
    #         segment - header included - is compressed; we decompress it and
    #         read the intensities as a contiguous block of uint32 values.
    #       - A run-length encoding that leaves the 16-byte header raw and
    #         encodes the intensities itself (see decompress_inten_list). This
    #         is what Q-TOF profile acquisitions emit; LZF decompression fails
    #         on it ("error in compressed data", issue #27).
    #     UncompressedByteCount does not reliably distinguish the two (it is
    #     sometimes set, sometimes zero, for the RLE case), so we detect the
    #     RLE format from the segment's own header (see segment_is_rle).
    profile_path = os.path.join(path, "MSProfile.bin")
    profile_size = os.path.getsize(profile_path)
    f = open(profile_path, 'rb')
    twodoubles_unpack = struct.Struct('<dd').unpack
    times = np.empty(num_times)
    num_mz_per_time = np.empty(num_times)
    mz_arrs = []
    inten_arrs = []
    grid_keys = []        # (num_mz, start_mz, delta) per scan, for native mode
    scan_calib_ids = []   # CalibrationID per scan, for native mode
    for i in range(num_times):
        time, num_mz, offset, comp_len, decomp_len, calib_id = data_info[i]

        # An interrupted acquisition leaves MSScan.bin describing scans whose
        # MSProfile.bin segment was never (fully) written. Stop at the first
        # such scan and keep the complete prefix instead of failing the parse.
        if offset + comp_len > profile_size:
            num_times = i
            times = times[:num_times]
            num_mz_per_time = num_mz_per_time[:num_times]
            break

        times[i] = time
        num_mz_per_time[i] = num_mz

        # Read and decompress the segment for the current retention time.
        f.seek(offset)
        comp_bytes = f.read(comp_len)
        if segment_is_rle(comp_bytes, num_mz):
            start_mz, delta_mz = twodoubles_unpack(comp_bytes[:16])
            body = memoryview(comp_bytes)[16:]
            # Use the compiled accelerator if it was built (identical output).
            if _msprofile_fast is not None:
                inten = _msprofile_fast.decompress_inten_list(body, num_mz)
            else:
                inten = decompress_inten_list(body, num_mz)
        else:
            # Only LZF-compressed segments need python-lzf; import it lazily so
            # RLE-only data (and the rest of this module) works without it.
            try:
                import lzf
            except ModuleNotFoundError:
                raise ModuleNotFoundError(
                    "You must install python-lzf to parse LZF-compressed "
                    "MSProfile.bin (HRMS) data.")
            decomp_view = memoryview(lzf.decompress(comp_bytes, decomp_len))
            start_mz, delta_mz = twodoubles_unpack(decomp_view[:16])
            inten = np.ndarray(num_mz, '<I', bytes(decomp_view[16:]))

        if native:
            # The native path keeps the raw per-scan intensities and recovers
            # m/z per scan on demand, so it skips the calibration here.
            grid_keys.append((num_mz, start_mz, delta_mz))
            scan_calib_ids.append(calib_id)
        else:
            # Calculate the calibrated mz values from the raw flight-time axis.
            tof = np.arange(
                start_mz, start_mz + delta_mz * (num_mz - 1) + 1e-3, delta_mz)
            tof = tof[:num_mz]
            mzs = calibrate_mz(tof, calib_vals[i], calib_flags.get(calib_id))
            mz_arrs.append(mzs)
        inten_arrs.append(inten)

    f.close()

    if num_times == 0:
        raise ValueError(
            f"MSProfile.bin in {path} contains no complete scans.")

    if native:
        return _build_native_profiles(
            times, inten_arrs, grid_keys, calib_vals[:num_times],
            scan_calib_ids, calib_flags)

    # Concatenating the per-scan arrays avoids materializing a ~100M-element
    # Python list (and the numpy round-trip through it), which otherwise
    # dominates parsing of large profile files.
    mz_arr = np.round(np.concatenate(mz_arrs), prec)
    intensities = np.concatenate(inten_arrs).astype(np.uint64)
    rows = np.repeat(np.arange(num_times), num_mz_per_time.astype(np.int64))
    mz_ylabels, data = bin_to_grid(mz_arr, intensities, rows, num_times, prec)

    return DataFile("MSProfile.bin", 'MS', times, mz_ylabels, data, {})


def _build_native_profiles(times, inten_arrs, grid_keys, calib_vals,
                           scan_calib_ids, calib_flags, mz_decimals=4):
    """
    Builds the native per-scan profile representation (see :obj:`parse_msdata`
    with ``native=True``).

    Scans that share a flight-time grid (same point count, start, and delta)
    have an index-aligned intensity rectangle, so each such group becomes one
    :class:`ProfileDataFile`. The m/z is not stored per point; instead each file
    keeps the shared flight-time axis plus the per-scan calibration and
    recomputes m/z on demand, which is exact and compact (the only thing that
    varies scan to scan is the calibration).

    Args:
        times (np.ndarray): Retention time of each (kept) scan.
        inten_arrs (list): Per-scan uint32 intensity arrays.
        grid_keys (list): ``(num_mz, start_mz, delta)`` flight-time grid of each
            scan.
        calib_vals (np.ndarray): ``(num_scans, 10)`` calibration rows.
        scan_calib_ids (list): CalibrationID of each scan.
        calib_flags (dict): Maps CalibrationID to polynomial ValueUseFlags.

    Returns:
        A list of :class:`ProfileDataFile`, largest grid first.

    """
    groups = {}
    for idx, key in enumerate(grid_keys):
        groups.setdefault(key, []).append(idx)

    profiles = []
    for seg, (key, idxs) in enumerate(
            sorted(groups.items(), key=lambda kv: -len(kv[1]))):
        num_mz, start_mz, delta_mz = key
        tof = np.arange(
            start_mz, start_mz + delta_mz * (num_mz - 1) + 1e-3, delta_mz)
        tof = tof[:num_mz]
        data = np.stack([inten_arrs[i] for i in idxs]).astype(np.uint32)
        xlabels = times[idxs]
        calib = calib_vals[idxs]
        use_flags = [calib_flags.get(scan_calib_ids[i]) for i in idxs]
        # One grid keeps the canonical name; extra grids are suffixed.
        name = "MSProfile.bin" if seg == 0 else f"MSProfile.bin.{seg + 1}"
        profiles.append(ProfileDataFile(
            name, xlabels, tof, data, calib, use_flags, {},
            mz_decimals=mz_decimals))
    return profiles


def parse_icpmsdata(path, prec=0):
    """
    Parses Agilent Masshunter ICP-MS data (MSProfile.bin).

    ICP-MS acquisitions store an intensity for each isotope channel at every
    retention time. Unlike the HRMS MSProfile.bin parsed by :obj:`parse_msdata`,
    the ICP-MS MSProfile.bin is NOT LZF-compressed and is laid out as four
    parallel blocks per scan (channel index, reported value, raw pulse count,
    analog value). This parser reads the reported values, which are the
    intensities Masshunter reports in its CSV export.

    The decoding was contributed by Jeremy Hourigan (UC Santa Cruz); see
    issue #25. It has been verified against an Agilent 8900 triple-quadrupole
    ICP-MS file. It currently supports time-resolved acquisitions with a single
    tune mode and one measurement per isotope; files with multiple tune modes
    or multiple measurements per isotope are not yet handled.

    The following files are used (in order of listing):
        - MSScan.xsd -> File structure of MSScan.bin.
        - MSScan.bin -> Per-scan retention time, offset, and point count.
        - MSTS_XSpecific.xml -> Number of isotope channels.
        - MSTS_XAddition.xml (parent dir) -> Real isotope m/z labels.
        - MSProfile.bin -> Actual data values (uncompressed).

    Args:
        path (str): Path to the AcqData subdirectory.
        prec (int, optional): Number of decimals to round m/z values.

    Returns:
        DataFile containing Masshunter ICP-MS data.

    """
    # MSScan.xsd: Extract the file structure of MSScan.bin.
    complextypes_dict = parse_scan_xsd(os.path.join(path, "MSScan.xsd"))

    # MSScan.bin: Read one scan record per retention time. ICP-MS MSProfile.bin
    # is uncompressed, so only the retention time, point count, and data offset
    # are needed (no byte counts or calibration ids).
    scan_records = read_scan_records(
        os.path.join(path, "MSScan.bin"), complextypes_dict, count_scans(path))
    num_times = len(scan_records)
    data_info = [
        (rec['ScanTime'],
         rec['SpectrumParamValues']['PointCount'],
         rec['SpectrumParamValues']['SpectrumOffset'])
        for rec in scan_records]

    # MSTS_XSpecific.xml: Extract the number of isotope channels (masses).
    root = etree.parse(os.path.join(path, "MSTS_XSpecific.xml")).getroot()
    num_masses = 0
    for ion_record in root.findall("IonRecord"):
        num_masses += len(ion_record.findall("Masses"))

    # Determine the m/z label for each isotope channel.
    mz_ylabels = _read_icpms_mzs(path, num_masses)

    # MSProfile.bin: Extract the data values (uncompressed).
    # Each scan stores four parallel blocks of `num_mz` points:
    #   - channel index : num_mz * 4 bytes (float32, unused here)
    #   - reported value : num_mz * 8 bytes (float64) <- the reported intensity
    #   - raw pulse count: num_mz * 8 bytes (float64, unused here)
    #   - analog value   : num_mz * 8 bytes (float64, unused here)
    # Only the reported values are kept; the pulse and analog blocks are used
    # for detector cross-calibration but are not part of the DataFile.
    f = open(os.path.join(path, "MSProfile.bin"), 'rb')
    times = np.empty(num_times)
    data = np.empty((num_times, num_masses), dtype=np.float64)
    double_block = struct.Struct(f'<{num_masses}d').unpack
    for i in range(num_times):
        time, num_mz, offset = data_info[i]
        times[i] = time
        f.seek(offset)
        f.read(num_mz * 4) # skip the channel-index block
        data[i] = double_block(f.read(num_mz * 8)) # reported values
    f.close()

    # Sort channels by m/z so the ylabels are monotonically increasing.
    mz_ylabels = np.round(mz_ylabels, prec)
    order = np.argsort(mz_ylabels, kind='stable')

    return DataFile(
        "MSProfile.bin", 'MS', times, mz_ylabels[order], data[:, order], {})


def _read_icpms_mzs(path, num_masses):
    """
    Returns the m/z label for each ICP-MS isotope channel.

    Prefers the real isotope m/z values from MSTS_XAddition.xml (located one
    directory above AcqData). Falls back to the per-channel XValue stored in
    MSScan_XSpecific.bin when that file is absent or does not match the
    expected channel count.

    Args:
        path (str): Path to the AcqData subdirectory.
        num_masses (int): Number of isotope channels.

    Returns:
        1D numpy array of m/z values, length num_masses.

    """
    addition_path = os.path.join(path, os.pardir, "MSTS_XAddition.xml")
    if os.path.isfile(addition_path):
        root = etree.parse(addition_path).getroot()
        mzs = [float(im.findtext("ProductIonMZ"))
               for im in root.findall(".//MSTS_XAddition_IndexedMasses")
               if im.findtext("ProductIonMZ") is not None]
        if len(mzs) == num_masses:
            return np.array(mzs, dtype=np.float64)

    # Fallback: XValue per channel from MSScan_XSpecific.bin. Its layout is
    # described by MSScan_XSpecific.xsd, parsed the same way as MSScan.xsd.
    complextypes_dict = parse_scan_xsd(
        os.path.join(path, "MSScan_XSpecific.xsd"))
    f = open(os.path.join(path, "MSScan_XSpecific.bin"), 'rb')
    f.seek(0x48) # start offset
    mzs = [read_complextype(f, complextypes_dict, "IonRecordType")['XValue']
           for _ in range(num_masses)]
    f.close()
    return np.array(mzs, dtype=np.float64)


# Cap on the dense (retention time x mz-bin) grid the fast binning path will
# allocate, in cells. 50M uint64 cells is ~400 MB; above this we fall back to
# the sort-based mapping, which only allocates the occupied columns.
_MAX_DENSE_BINS = 50_000_000


def bin_to_grid(mz_arr, intensities, rows, num_times, prec):
    """
    Bins per-point (mz, intensity) values into a (retention time x mz) grid.

    Rounding to ``prec`` decimals puts the mz values on a discrete grid of
    spacing ``10**-prec``. Scaling them to integers lets us assign each point a
    column directly and sum with a single pass, avoiding the global sort that
    :func:`numpy.unique`/:func:`numpy.searchsorted` would do over every point.
    For wide mz ranges at high ``prec`` the dense grid would be too large, so
    above :data:`_MAX_DENSE_BINS` we fall back to the sort-based mapping.

    Args:
        mz_arr (np.ndarray): Rounded mz value of every point, all scans
            concatenated.
        intensities (np.ndarray): uint64 intensity of every point.
        rows (np.ndarray): Retention-time (row) index of every point.
        num_times (int): Number of retention times (grid rows).
        prec (int): Number of decimals the mz values were rounded to.

    Returns:
        Tuple ``(mz_ylabels, data)``: the sorted unique mz values that occur,
        and the ``(num_times, mz_ylabels.size)`` uint64 intensity grid.

    """
    scale = 10 ** prec
    keys = np.round(mz_arr * scale).astype(np.int64)
    low = int(keys.min())
    span = int(keys.max()) - low + 1

    if span * num_times <= _MAX_DENSE_BINS:
        # Dense path: integer mz keys index straight into the grid.
        grid = np.zeros(num_times * span, dtype=np.uint64)
        np.add.at(grid, rows * span + (keys - low), intensities)
        grid = grid.reshape(num_times, span)
        present = np.nonzero(grid.any(axis=0))[0]
        return (low + present) / scale, grid[:, present]

    # Sparse path: map mz values onto only the columns that occur.
    mz_ylabels = np.unique(mz_arr)
    cols = np.searchsorted(mz_ylabels, mz_arr)
    grid = np.zeros(num_times * mz_ylabels.size, dtype=np.uint64)
    np.add.at(grid, rows * mz_ylabels.size + cols, intensities)
    return mz_ylabels, grid.reshape(num_times, mz_ylabels.size)


# Bytes-per-peak -> (mz dtype, intensity dtype) for the MSPeak.bin centroid
# encodings seen in the wild. 8 and 12 interleave one mz and one intensity per
# peak; 16 stores all mz values then all intensities (a split block).
_PEAK_DTYPES = {8: ('<f4', '<f4'), 12: ('<f8', '<f4'), 16: ('<f8', '<f8')}


def parse_mspeakdata(path, prec=0):
    """
    Parses Masshunter centroided MS data stored in MSPeak.bin.

    MSPeak.bin holds the peak-picked (centroid) spectrum of each scan - a list
    of (mz, intensity) pairs - in contrast to the dense profile trace in
    MSProfile.bin (:obj:`parse_msdata`). GC quadrupole acquisitions store only
    centroids; Q-TOF/TOF acquisitions store a profile block and a centroid block
    per scan (see :obj:`read_scan_records`), and this reads the centroid one.

    The following files are used:
        - MSScan.xsd  -> File structure of MSScan.bin.
        - MSScan.bin  -> Per-scan metadata and pointers into MSPeak.bin.
        - MSPeak.bin  -> Raw (mz, intensity) peak pairs.

    The MSPeak.bin centroid decoding was contributed by denisshragin (issue #37).

    Args:
        path (str): Path to the AcqData subdirectory.
        prec (int, optional): Number of decimals to round mz values.

    Returns:
        DataFile containing Masshunter centroided MS data.

    """
    complextypes_dict = parse_scan_xsd(os.path.join(path, "MSScan.xsd"))
    scan_records = read_scan_records(
        os.path.join(path, "MSScan.bin"), complextypes_dict, count_scans(path))
    num_times = len(scan_records)

    # Mass calibration. GC-quadrupole MSPeak.bin already stores m/z (no
    # calibration files, so calib_vals is None), but a TOF/Q-TOF centroid axis
    # is raw time-of-flight and is calibrated exactly like the profile axis.
    calibration_ids = [record.get('CalibrationID') for record in scan_records]
    calib_vals, calib_flags = _load_calibration(path, calibration_ids)

    peak_path = os.path.join(path, "MSPeak.bin")
    peak_size = os.path.getsize(peak_path)
    times = np.empty(num_times)
    num_peaks_per_time = np.zeros(num_times, dtype=np.int64)
    mz_arrs = []
    inten_arrs = []
    with open(peak_path, 'rb') as f:
        for i, record in enumerate(scan_records):
            times[i] = record['ScanTime']
            block = _select_centroid_block(record['SpectrumParamsBlocks'])
            if block is None:
                continue
            num_peaks = block['PointCount']
            offset = block['SpectrumOffset']
            byte_count = block['ByteCount']
            # Skip scans with no peaks, or whose data was never (fully) written
            # (an interrupted acquisition - keep the complete scans).
            if (num_peaks <= 0 or byte_count <= 0
                    or offset + byte_count > peak_size):
                continue
            f.seek(offset)
            mzs, intensities = _decode_peak_block(
                f.read(byte_count), num_peaks, byte_count // num_peaks)
            if calib_vals is not None:
                mzs = calibrate_mz(np.asarray(mzs, dtype=np.float64),
                                   calib_vals[i], calib_flags.get(
                                       calibration_ids[i]))
            mz_arrs.append(np.round(mzs, prec))
            inten_arrs.append(intensities)
            num_peaks_per_time[i] = num_peaks

    if not mz_arrs:
        return DataFile(
            "MSPeak.bin", 'MS', times, np.array([], dtype=np.float64),
            np.zeros((num_times, 0), dtype=np.uint64), {})

    mz_arr = np.concatenate(mz_arrs)
    intensities = np.concatenate(inten_arrs).astype(np.uint64)
    rows = np.repeat(np.arange(num_times), num_peaks_per_time)
    mz_ylabels, data = bin_to_grid(mz_arr, intensities, rows, num_times, prec)
    return DataFile("MSPeak.bin", 'MS', times, mz_ylabels, data, {})


def _select_centroid_block(blocks):
    """
    Returns the centroid (MSPeak.bin) block among a scan's SpectrumParamValues
    blocks, or None if there is no peak block.

    A centroid block stores fixed-width (mz, intensity) peaks, so its ByteCount
    is an exact multiple of PointCount equal to one of the known bytes-per-peak
    widths. A profile block's ByteCount is a compressed length and does not
    satisfy this, which distinguishes the two on instruments that store both.
    """
    for block in blocks:
        num_peaks = block['PointCount']
        byte_count = block['ByteCount']
        if (num_peaks > 0 and byte_count % num_peaks == 0
                and byte_count // num_peaks in _PEAK_DTYPES):
            return block
    return None


def _decode_peak_block(raw, num_peaks, bytes_per_peak):
    """
    Decodes one MSPeak.bin centroid segment into (mz, intensity) float arrays.

    The segment is a split block: all ``num_peaks`` mz values followed by all
    ``num_peaks`` intensities. ``bytes_per_peak`` selects the dtypes (see
    :data:`_PEAK_DTYPES`).
    """
    mz_dtype, inten_dtype = _PEAK_DTYPES[bytes_per_peak]
    mz_bytes = num_peaks * np.dtype(mz_dtype).itemsize
    mzs = np.frombuffer(raw[:mz_bytes], dtype=mz_dtype)
    intensities = np.frombuffer(
        raw[mz_bytes:num_peaks * bytes_per_peak], dtype=inten_dtype)
    return mzs, intensities


def parse_default_masscal(xml_path):
    """
    Reads the polynomial ``ValueUseFlags`` for each calibration id from
    DefaultMassCal.xml.

    Each ``DefaultCalibration`` has a ``Polynomial`` step whose
    ``ValueUseFlags`` is a bitmask: bit ``k`` (counting from the least
    significant) being set means the polynomial includes a term of order
    ``k``, and the active coefficients in MSMassCal.bin fill those orders in
    ascending order. A flag of 0 (or a missing file) means no polynomial
    refinement - only the traditional calibration is used.

    Args:
        xml_path (str): Path to DefaultMassCal.xml.

    Returns:
        Dictionary mapping calibration id (int) to its ValueUseFlags (int).
        Empty if the file does not exist.

    """
    if not os.path.exists(xml_path):
        return {}
    flags = {}
    root = etree.parse(xml_path).getroot()
    for calibration in root.iter("DefaultCalibration"):
        calib_id = calibration.get("DefaultCalibrationID")
        if calib_id is None:
            continue
        for step in calibration.iter("Step"):
            if step.findtext("CalibrationFormula") == "Polynomial":
                use_flags = step.findtext("ValueUseFlags")
                flags[int(calib_id)] = int(use_flags) if use_flags else 0
    return flags


def read_default_masscal_rows(xml_path):
    """
    Reads the default per-calibration-id calibration rows from
    DefaultMassCal.xml.

    Used as the fallback when the per-scan MSMassCal.bin is absent. Each
    ``DefaultCalibration`` provides a ``Traditional`` step (coeff, base) and,
    optionally, a ``Polynomial`` step (left, right, then six coefficients).
    Together these are the ten doubles MSMassCal.bin would otherwise store per
    scan - ``[coeff, base, left, right, c0..c5]`` - so a row can stand in for a
    MSMassCal.bin row directly (see :obj:`calibrate_mz`). The polynomial's
    ValueUseFlags is read separately by :obj:`parse_default_masscal`.

    Args:
        xml_path (str): Path to DefaultMassCal.xml.

    Returns:
        Dictionary mapping calibration id (int) to a length-10 list of doubles.
        Empty if the file does not exist or defines no traditional calibration.

    """
    if not os.path.exists(xml_path):
        return {}
    rows = {}
    root = etree.parse(xml_path).getroot()
    for calibration in root.iter("DefaultCalibration"):
        calib_id = calibration.get("DefaultCalibrationID")
        if calib_id is None:
            continue
        traditional, polynomial = [], []
        for step in calibration.iter("Step"):
            values = [float(v.text) for v in step.iter("Value")]
            formula = step.findtext("CalibrationFormula")
            if formula == "Traditional":
                traditional = values
            elif formula == "Polynomial":
                polynomial = values
        if len(traditional) < 2:
            continue
        row = list(traditional[:2]) + list(polynomial[:8])
        row += [0.0] * (10 - len(row))
        rows[int(calib_id)] = row[:10]
    return rows


def _load_calibration(path, calibration_ids):
    """
    Loads the per-scan mass calibration for an AcqData directory.

    Returns ``(calib_vals, calib_flags)`` where ``calib_vals`` is an ``(N, 10)``
    array of the ten calibration doubles for each of the N scans (in the order
    of ``calibration_ids``) and ``calib_flags`` maps each CalibrationID to its
    polynomial ValueUseFlags. The values come from the per-scan MSMassCal.bin
    when present, otherwise from DefaultMassCal.xml by CalibrationID (see
    :obj:`read_default_masscal_rows`); the per-scan refinement MSMassCal.bin
    adds is sub-ppm.

    Returns ``(None, None)`` when the directory has no calibration at all - e.g.
    GC-quadrupole centroid data, whose MSPeak.bin already stores m/z directly.

    Args:
        path (str): Path to the AcqData subdirectory.
        calibration_ids (list): CalibrationID of each scan, in scan order.

    Returns:
        Tuple ``(calib_vals, calib_flags)``, or ``(None, None)`` if uncalibrated.

    """
    masscal_path = os.path.join(path, "MSMassCal.bin")
    if os.path.isfile(masscal_path):
        with open(masscal_path, 'rb') as f:
            f.seek(0x4c)  # start offset
            calib_vals = np.ndarray(
                (len(calibration_ids), 10), '<d', f.read(), 0, (84, 8))
    else:
        default_rows = read_default_masscal_rows(
            os.path.join(path, "DefaultMassCal.xml"))
        if not default_rows:
            return None, None
        fallback_row = next(iter(default_rows.values()))
        calib_vals = np.array(
            [default_rows.get(cid, fallback_row) for cid in calibration_ids],
            dtype='<d')
    calib_flags = parse_default_masscal(
        os.path.join(path, "DefaultMassCal.xml"))
    return calib_vals, calib_flags


def calibrate_mz(tof, calib_row, use_flags):
    """
    Converts a raw time-of-flight axis to calibrated mz values.

    The traditional calibration is ``mz = (coeff * (tof - base))**2``. When a
    polynomial refinement is active (``use_flags`` truthy), a correction is
    subtracted: the six MSMassCal.bin coefficients are assigned to the
    polynomial orders whose bits are set in ``use_flags`` (ascending), and the
    polynomial is evaluated on the time-of-flight clipped to ``[left, right]``.
    This matches the masses Agilent MassHunter reports (validated to <0.0001
    Da against exported spectra); without it the masses are off by ~1-2 ppm.

    Args:
        tof (np.ndarray): Raw time-of-flight values for one scan.
        calib_row (np.ndarray): The scan's 10 MSMassCal.bin doubles
            (coeff, base, left, right, and six polynomial coefficients).
        use_flags (int or None): The polynomial ValueUseFlags for this scan's
            calibration id, or None/0 to apply only the traditional formula.

    Returns:
        A numpy array of calibrated mz values.

    """
    coeff, base, left, right = calib_row[:4]
    mzs = (coeff * (tof - base)) ** 2
    if not use_flags:
        return mzs

    # Map the six coefficients onto the polynomial orders flagged for use.
    coefficients = calib_row[4:10]
    orders = [k for k in range(use_flags.bit_length()) if use_flags >> k & 1]
    poly = np.zeros(max(orders) + 1) if orders else np.zeros(1)
    for order, coefficient in zip(orders, coefficients):
        poly[order] = coefficient
    # np.polyval wants coefficients highest-order first; Horner's method keeps
    # the high-order terms stable for the large time-of-flight magnitudes.
    correction = np.polyval(poly[::-1], np.clip(tof, left, right))
    return mzs - correction


def segment_is_rle(comp_bytes, num_mz):
    """
    Returns whether a MSProfile.bin segment uses run-length encoding.

    RLE segments leave the 16-byte (smallest mz, mz delta) header raw and
    follow it with an intensity stream whose first 4 bytes are a little-endian
    word: the low 3 bytes hold the point count and the high byte is a fixed
    0x90 marker. Both must match for us to treat the segment as RLE, which
    makes this a self-validating check rather than a guess (LZF-compressed
    segments effectively never satisfy it). See :obj:`decompress_inten_list`.

    Args:
        comp_bytes (bytes): The raw segment bytes read from MSProfile.bin.
        num_mz (int): The expected number of mz-intensity pairs.

    Returns:
        True if the segment is RLE-encoded, False otherwise.

    """
    if len(comp_bytes) < 20:
        return False
    header = struct.unpack('<I', comp_bytes[16:20])[0]
    return (header & 0x00FFFFFF) == num_mz and (header >> 24) == 0x90


def decompress_inten_list(comp_view, num_mz):
    """
    Decompresses the run-length-encoded intensity stream of a MSProfile.bin
    segment (see :obj:`segment_is_rle`). Q-TOF profile acquisitions store
    intensities this way instead of LZF-compressing them (issue #27).

    The stream begins with a 4-byte point-count word (low 3 bytes) and a fixed
    0x90 marker (high byte), then a negated little-endian int32 giving the
    count of leading zero intensities. The token stream follows, opening at a
    width of 4 bytes (signed). Each value is read at the current width:

    - A non-negative value is a literal intensity.
    - A negative value -v encodes ``divmod(v, 4)``: the quotient is a run
      of zero intensities to emit, and the remainder is the new width flag
      (1, 2, 3 -> 1-, 2-, 4-byte; 4 -> 8-byte) to switch to for subsequent
      values.

    Most scans open with an ``0xffffffff`` token, read as -1 at the 4-byte
    starting width, which emits no zeros and switches to 1-byte values; this is
    why the opening width is rarely seen directly. High-signal scans instead
    open with a literal 4-byte intensity. (Issue #27: an earlier reading
    mistook that first token for a separate "width flag" field, which decoded
    identically for the common case but failed on the literal-first scans.)

    Trailing zero intensities are not stored, so the output is pre-filled with
    zeros to length ``num_mz``.

    Args:
        comp_view (memoryview): Segment bytes after the 16-byte header.
        num_mz (int): The number of mz-intensity pairs (output length).

    Returns:
        A numpy array of ``num_mz`` uint32 intensities.

    Raises:
        ValueError: If the stream is malformed (bad width flag, runs past the
            point count, or is truncated).

    """
    unpackers = {
        1: struct.Struct('<b').unpack,
        2: struct.Struct('<h').unpack,
        3: struct.Struct('<i').unpack,
        4: struct.Struct('<q').unpack,
    }
    sizes = {1: 1, 2: 2, 3: 4, 4: 8}

    init_zero_repeat = struct.unpack('<i', comp_view[4:8])[0]
    cur_idx = -init_zero_repeat
    # cur_idx only ever advances, so once it starts non-negative it stays in
    # range and out-of-bounds literals raise IndexError below. A positive
    # init_zero_repeat would make it start negative (and silently wrap), so
    # reject that up front. Bad width flags and truncated tails surface as
    # KeyError / struct.error inside the loop; all are reported as ValueError
    # rather than added as per-iteration checks that would slow the hot path.
    if cur_idx < 0:
        raise ValueError(
            "Malformed MSProfile.bin RLE segment: negative initial index.")

    inten = np.zeros(num_mz, dtype=np.uint32)
    # The token stream begins right after the leading-zero count, at an initial
    # width of 4 bytes (width flag 3); a control value switches it thereafter.
    offset = 8
    end = len(comp_view)
    try:
        cur_size = sizes[3]
        cur_unpack = unpackers[3]
        while offset < end:
            value = cur_unpack(comp_view[offset:offset + cur_size])[0]
            offset += cur_size
            if value >= 0:
                inten[cur_idx] = value
                cur_idx += 1
            else:
                num_zeros, width_flag = divmod(-value, 4)
                cur_idx += num_zeros
                cur_size = sizes[width_flag]
                cur_unpack = unpackers[width_flag]
    except (KeyError, IndexError, struct.error) as err:
        raise ValueError(
            "Malformed MSProfile.bin RLE segment.") from err
    return inten


def parse_scan_xsd(xsd_path):
    """
    Parses MSScan.xsd into a dictionary describing its "complex" types.

    There are "simple" types that translate directly into number types, and
    "complex" types made up of other "simple" and "complex" types. The
    returned dictionary maps each complex type's name to a list of its
    (name, type) members, which enables the recursive parsing in
    :obj:`read_complextype`.

    Args:
        xsd_path (str): Path to MSScan.xsd.

    Returns:
        Dictionary mapping complex type names to lists of (name, type) tuples.

    """
    tree = etree.parse(xsd_path)
    root = tree.getroot()
    namespace = tree.xpath('namespace-uri(.)')
    complextypes_dict = {}
    for complextype in root.findall(f"{{{namespace}}}complexType"):
        innertypes = []
        for element in complextype[0].findall(f"{{{namespace}}}element"):
            innertypes.append((element.get('name'), element.get('type')))
        complextypes_dict[complextype.get('name')] = innertypes
    return complextypes_dict


# Byte sizes of the MSScan.xsd "simple" types (mirrors the readers in
# read_type). Used to compute a record's on-disk size without reading it.
_SIMPLE_TYPE_SIZES = {
    'xs:byte': 1, 'xs:short': 2, 'xs:int': 4,
    'xs:long': 8, 'xs:float': 4, 'xs:double': 8,
}

# A scan may store more than one SpectrumParamValues block; this bounds how many
# we will consider when inferring the record stride (see read_scan_records).
_MAX_SPECTRUM_BLOCKS = 8


def type_size(complextypes_dict, name):
    """
    Returns the on-disk byte size of one MSScan.bin record of the given type.

    Mirrors :obj:`read_complextype`/:obj:`read_type`: each member is counted
    once, so for ScanRecordType this is the size of a record with a single
    SpectrumParamValues block. Lets read_scan_records reason about the record
    stride without reading the file.

    Args:
        complextypes_dict (dict): Output of :obj:`parse_scan_xsd`.
        name (str): A simple ("xs:int", ...) or complex type name.

    Returns:
        Size in bytes (int).

    """
    if name in _SIMPLE_TYPE_SIZES:
        return _SIMPLE_TYPE_SIZES[name]
    return sum(type_size(complextypes_dict, subtype)
               for _, subtype in complextypes_dict[name.split(':')[-1]])


def read_scan_records(msscan_path, complextypes_dict, num_records=None):
    """
    Reads the scan records (ScanRecordType) from MSScan.bin, one per retention
    time.

    Each record holds the scalar scan fields followed by one or more
    ``SpectrumParamValues`` blocks - the schema element is
    ``maxOccurs="unbounded"``. A profile-only acquisition writes a single block,
    but an acquisition that also stores centroids (MSPeak.bin) writes a profile
    block *and* a centroid block, making the record larger.
    :obj:`read_complextype` reads only the first block, so reading records
    back-to-back would mis-parse the trailing block(s) as the next record.

    To stay aligned we read each record at the true record stride and skip to
    the next. The stride is ``scalar + n * block`` for some block count ``n``;
    it is taken from the MSTS.xml scan count when that is consistent, otherwise
    inferred as the value of ``n`` that tiles the record region exactly. The
    first block of each record is the profile spectrum, which is what
    :obj:`parse_msdata` consumes. Only when no stride tiles the region (a record
    truncated mid-write) do we fall back to reading single-block records to EOF.

    Args:
        msscan_path (str): Path to MSScan.bin.
        complextypes_dict (dict): Output of :obj:`parse_scan_xsd`.
        num_records (int, optional): Scan count from MSTS.xml (:obj:`count_scans`),
            used as a hint. May be None (OpenLab result folders omit MSTS.xml)
            or stale (interrupted acquisitions); the stride is validated against
            the file geometry either way.

    Returns:
        List of dictionaries, one per retention time, each mapping the
        ScanRecordType member names to their parsed values.

    """
    file_size = os.path.getsize(msscan_path)
    block = type_size(complextypes_dict, "SpectrumParamsType")
    scalar = type_size(complextypes_dict, "ScanRecordType") - block
    records = []
    with open(msscan_path, 'rb') as f:
        f.seek(0x58)  # offset to the uint32 pointer at the start of records
        rec_start = struct.unpack('<I', f.read(4))[0]
        body = file_size - rec_start

        candidates = [scalar + n * block
                      for n in range(1, _MAX_SPECTRUM_BLOCKS + 1)]
        stride = None
        # Trust the MSTS scan count when it implies a structurally valid stride.
        if num_records and num_records > 0 and body % num_records == 0:
            hinted = body // num_records
            if hinted in candidates:
                stride = hinted
        # Otherwise infer it: the record size must tile the region exactly. If
        # several block counts do, prefer the scan count nearest MSTS (a stale
        # MSTS is still in the right range), else the fewest blocks.
        if stride is None:
            divisors = [s for s in candidates if body % s == 0]
            if divisors:
                stride = min(divisors, key=lambda s: (
                    abs(body // s - num_records) if num_records else s))

        if stride is not None:
            # Number of SpectrumParamValues blocks per record (e.g. a profile
            # block plus a centroid block). read_complextype consumes the scalar
            # fields and the first block; read any remaining blocks explicitly so
            # callers that need the centroid block (parse_mspeakdata) can see it.
            num_blocks = (stride - scalar) // block
            for i in range(body // stride):
                f.seek(rec_start + i * stride)
                record = read_complextype(
                    f, complextypes_dict, "ScanRecordType")
                blocks = [record['SpectrumParamValues']]
                for _ in range(num_blocks - 1):
                    blocks.append(read_complextype(
                        f, complextypes_dict, "SpectrumParamsType"))
                record['SpectrumParamsBlocks'] = blocks
                records.append(record)
        else:
            # No stride tiles the region (e.g. truncated mid-record): best-effort
            # single-block read to EOF.
            f.seek(rec_start)
            while f.tell() < file_size:
                record = read_complextype(
                    f, complextypes_dict, "ScanRecordType")
                record['SpectrumParamsBlocks'] = [record['SpectrumParamValues']]
                records.append(record)
    return records


def count_scans(acqdata_path):
    """
    Returns the total scan count from MSTS.xml, or None if MSTS.xml is absent.

    MSTS.xml lists the number of scans per acquisition time segment
    (``<NumOfScans>``); the total is their sum. Agilent OpenLab .rslt/.sirslt
    result folders omit MSTS.xml, in which case :obj:`read_scan_records` infers
    the scan count from the record geometry instead.

    Args:
        acqdata_path (str): Path to the AcqData subdirectory.

    Returns:
        Total scan count (int), or None if MSTS.xml does not exist.

    """
    msts_path = os.path.join(acqdata_path, "MSTS.xml")
    if not os.path.isfile(msts_path):
        return None
    root = etree.parse(msts_path).getroot()
    counts = [int(el.text) for el in root.iter("NumOfScans") if el.text]
    return sum(counts) if counts else None


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

    Mutually recurs with :obj:`read_complextype`.

    Args: 
        f (_io.BufferedReader): File opened in 'rb' mode.
        complextypes_dict (dict): Dictionary defining all "complex" types.
        name (str): Name of the type to parse. 

    Returns:
        If the type is "simple", a number value. \
        If the type is "complex", a dictionary mapping names to values.

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
    # A "complex" type. Newer MassHunter acquisition software qualifies these
    # references with the schema's target-namespace prefix (e.g.
    # "mstns:ScanRecordType"), while the complexType is defined under its bare
    # local name. Strip any such prefix before looking it up.
    return read_complextype(f, complextype_dict, name.split(':')[-1])