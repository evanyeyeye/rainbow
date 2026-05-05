import os

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

    """
    datafiles = []
    datafiles.extend(chemstation.parse_allfiles(path, prec, requested_files))

    acqdata = os.path.join(path, "AcqData")
    if os.path.isdir(acqdata):
        acqdata_files = set(os.listdir(acqdata))

        if {"MSTS.xml", "MSScan.xsd", "MSScan.bin"} <= acqdata_files:

            if "MSPeak.bin" in acqdata_files:
                # Centroided data — no extra dependency, always attempt.
                from rainbow.agilent import masshunter
                datafiles.extend(masshunter.parse_allfiles(path, prec))

            elif "MSProfile.bin" in acqdata_files and hrms:
                # HRMS profile data — requires python-lzf.
                try:
                    from rainbow.agilent import masshunter
                    datafiles.extend(masshunter.parse_allfiles(path, prec))
                except ModuleNotFoundError:
                    raise ModuleNotFoundError(
                        "You must install python-lzf to parse MSProfile.bin "
                        "files.\nRun: pip install python-lzf\n"
                        "If you have MSPeak.bin data, no extra packages are "
                        "needed — it is parsed automatically."
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
