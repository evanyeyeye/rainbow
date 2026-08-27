import os
import re

from rainbow._arguments import reject_removed_arguments
from rainbow.waters import masslynx
from rainbow.datadirectory import DataDirectory


def read(path, display_precision='auto', requested_files=None,
         bin_width=None, _labels_only=False, **removed):
    """
    Reads a Waters .raw directory.

    Args:
        path (str): Path of the directory.
        display_precision (int or 'auto', optional): Decimals for the displayed
            m/z (or wavelength) labels. Cosmetic. ``'auto'`` means whole numbers.
        requested_files (list, optional): List of filenames to parse.
        bin_width (float, optional): m/z bin width, the lossy binning control.
            The default is nominal mass (1 Da). Waters MS m/z is calibrated to
            roughly 0.03 Da.

    Returns:
        DataDirectory representing the Waters .raw directory.

    """
    if removed:
        reject_removed_arguments("waters.read", removed)
    if display_precision == 'auto':
        display_precision = 0
    if bin_width is None:
        bin_width = 1.0
    datafiles = []
    datafiles.extend(masslynx.parse_spectrum(
        path, display_precision, bin_width, requested_files, _labels_only))
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
