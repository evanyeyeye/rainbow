import os
import re

from rainbow.waters import masslynx
from rainbow.datadirectory import DataDirectory


def read(path, precision='auto', requested_files=None):
    """
    Reads a Waters .raw directory.

    Args:
        path (str): Path of the directory.
        precision (int or 'auto', optional): Number of decimals to round ylabels.
            ``'auto'`` means whole numbers: rainbow applies one calibration per
            function (no per-scan drift is modelled), so Waters MS is treated as
            unit-resolution here.
        requested_files (list, optional): List of filenames to parse.

    Returns:
        DataDirectory representing the Waters .raw directory.

    """
    if precision == 'auto':
        precision = 0
    datafiles = []
    datafiles.extend(masslynx.parse_spectrum(path, precision, requested_files))
    datafiles.extend(masslynx.parse_analog(path, requested_files))

    metadata = masslynx.parse_metadata(path)

    return DataDirectory(path, datafiles, metadata)


def read_metadata(path):
    """
    Reads metdata from a Waters .raw directory.

    Args:
        path (str): Path of the directory.

    Returns:
        Dictionary containing a list of datafiles and the metadata.
    """
    datafiles = []
    metadata = masslynx.parse_metadata(path)
    if len(metadata) == 1:
        datadir = read(path)
        if datadir:
            return {'datafiles': datadir.datafiles + datadir.analog, 'metadata': metadata}
        return None

    datafiles = [fn for fn in os.listdir(path) if re.match(r'^_FUNC\d{3}.DAT$', fn)]
    if '_CHROMS.INF' in os.listdir(path):
        analog_info = masslynx.parse_chroinf(os.path.join(path, '_CHROMS.INF'))
        for i in range(len(analog_info)):
            datafiles.append(f"_CHRO{i + 1:0>3}.DAT")
    return {'datafiles': datafiles, 'metadata': metadata}
