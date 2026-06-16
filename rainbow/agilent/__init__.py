import os
import struct
import warnings

from lxml import etree

from rainbow.agilent import chemstation
from rainbow.datadirectory import DataDirectory


def read(path, prec=0, hrms=False, requested_files=None):
    """
    Reads an Agilent .D directory.

    MSPeak.bin (centroided GC-MS / LC-MS data) is parsed automatically
    whenever it is present in AcqData/. No extra flags are needed.

    MSProfile.bin (HRMS profile data) requires ``hrms=True`` and the
    ``python-lzf`` package to be installed.

    Args:
        path (str): Path of the directory.
        prec (int, optional): Number of decimals to round masses.
        hrms (bool, optional): Flag for HRMS (MSProfile.bin) parsing.
            Requires python-lzf.
        requested_files (list, optional): List of filenames to parse.

    Returns:
        DataDirectory representing the Agilent .D directory.

    Raises:
        ImportError: If ``hrms=True`` and ``python-lzf`` is not installed.
        FileNotFoundError: If ``path`` does not exist.
        NotADirectoryError: If ``path`` is not a directory.
    """
    # ── Validate path ──────────────────────────────────────────────────────
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Directory not found: {path}"
        )
    if not os.path.isdir(path):
        raise NotADirectoryError(
            f"Path is not a directory: {path}"
        )

    datafiles = []
    datafiles.extend(chemstation.parse_allfiles(path, prec, requested_files))

    # MassHunter data (AcqData/) — masshunter.parse_allfiles owns the format
    # detection and the hrms gating. MSPeak.bin (centroided) is parsed
    # automatically; MSProfile.bin (HRMS profile) only when hrms is set.
    if os.path.isdir(os.path.join(path, "AcqData")):
        from rainbow.agilent import masshunter
        try:
            datafiles.extend(masshunter.parse_allfiles(path, prec, hrms))
        except (OSError, struct.error, ValueError, etree.XMLSyntaxError) as e:
            # A malformed file shouldn't sink the whole directory read. Narrow
            # to the errors parsing can realistically raise so unexpected
            # exceptions (AttributeError, KeyError, ...) still propagate and a
            # parser regression fails loudly. A missing python-lzf surfaces as
            # ImportError from parse_msdata, which propagates with its own
            # install hint.
            warnings.warn(
                f"Failed to parse MassHunter data in {path}: {e}",
                RuntimeWarning,
                stacklevel=2,
            )

    metadata = chemstation.parse_metadata(path, datafiles)
    return DataDirectory(path, datafiles, metadata)


def read_metadata(path):
    """
    Reads metadata from an Agilent .D directory.

    Args:
        path (str): Path of the directory.

    Returns:
        Dictionary containing a list of datafiles and the metadata.

    """
    datafiles = []
    metadata = chemstation.parse_metadata(path, datafiles)
    if len(metadata) == 1:
        datadir = read(path)
        if datadir:
            return {
                'datafiles': datadir.datafiles + datadir.analog,
                'metadata': datadir.metadata,
            }
        return None
    # Masshunter datafiles are not located.
    datafiles = [
        fn for fn in os.listdir(path)
        if fn[-3:].lower() in ('.uv', '.ch', '.ms')
    ]
    return {'datafiles': datafiles, 'metadata': metadata}
