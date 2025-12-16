""" 
Methods for parsing Agilent Chemstation files. 
 
"""

import os
from collections import Counter
from lxml import etree

from rainbow.agilent.fileparsers import parse_file

"""
MAIN PARSING METHODS

"""

def parse_allfiles(path, prec=0, requested_files=None):
    """
    Finds and parses Agilent Chemstation data files \
        with a .ch, .uv, or .ms extension from a .D directory.
    
    Args:
        path (str): Path to the .D directory.
        prec (int, optional): Number of decimals to round mz values.
        requested_files (list, optional): List of filenames to parse.

    Returns:
        List with a DataFile for each parsed data file. 

    """
    datafiles = []
    for name in os.listdir(path):
        if requested_files and name.lower() not in requested_files:
            continue
        datafile = parse_file(os.path.join(path, name), prec)
        if datafile:
            datafiles.append(datafile)
    return datafiles


""" 
DIRECTORY METADATA PARSING METHODS 

"""


def parse_metadata(path, datafiles):
    """
    Parses Agilent metadata at the directory level.

    First, the DataFiles are checked for date and vial position metadata.

    Then, several files are scanned for the vial position. \
        This method can look inside the AcqData directory, which may be \
        misleading because this method resides in the Chemstation module.

    Args:
        path (str): Path to the directory.
        datafiles (list): List of DataFile objects.  
    
    Returns:
        Dictionary containing directory metadata. 

    """
    metadata = {}
    metadata['vendor'] = "Agilent"
    metadata['format'] = "Chemstation"

    # Scan each DataFile for the date and vial position.
    # These may be stored in multiple files but the values are constant.
    # In MS files, the time may be saved in a different format.
    # Get the most common values if they differ across files
    dates = Counter(datafile.metadata['date'] for datafile in datafiles if 'date' in datafile.metadata)
    vialposs = Counter(datafile.metadata['vialpos'] for datafile in datafiles if 'vialpos' in datafile.metadata)
    if dates:
        metadata['date'] = dates.most_common(1)[0][0]
    if vialposs:
        metadata['vialpos'] = vialposs.most_common(1)[0][0]

    if 'date' in metadata and 'vialpos' in metadata:
        return metadata

    # Scan certain files for the vial position. 
    dircontents = set(os.listdir(path))

    # sequence.acam_
    if "sequence.acam_" in dircontents:
        vialnum = get_xml_vialnum(os.path.join(path, "sequence.acam_"))
        if vialnum:
            metadata['vialpos'] = vialnum
            return metadata

    # sample.acaml
    if "sample.acaml" in dircontents:
        vialnum = get_xml_vialnum(os.path.join(path, "sample.acaml"))
        if vialnum:
            metadata['vialpos'] = vialnum
            return metadata

    # AcqData/sample_info.xml
    if "AcqData" in dircontents:
        acqdata_path = os.path.join(path, "AcqData")
        if "sample_info.xml" in os.listdir(acqdata_path):
            tree = etree.parse(os.path.join(acqdata_path, "sample_info.xml"))
            root = tree.getroot()
            for samplefield in root.xpath('//Field[Name="Sample Position"]'):
                vialnum = samplefield.find("Value")
                if vialnum is not None and len(vialnum.text.split()) == 1:
                    metadata['vialpos'] = vialnum.text
                    return metadata

    # runstart.txt 
    if "runstart.txt" in dircontents:
        f = open(os.path.join(path, "runstart.txt"))
        lines = f.read().splitlines()
        f.close()
        for line in lines:
            stripped = line.strip()
            if "Alsbottle" not in stripped:
                continue
            vialnum = stripped.split()[-1]
            if int(vialnum):
                metadata['vialpos'] = vialnum
                return metadata

    # RUN.LOG
    if "RUN.LOG" in dircontents:
        f = open(os.path.join(path, "RUN.LOG"), 'rb')
        plaintext = f.read().decode('ascii', 'ignore').replace("\x00", "")
        f.close()
        for line in plaintext.splitlines():
            vialpos = None
            if "Method started" in line:
                split = line.split()
                vialpos = get_nextstr(split, "vial#")
                if not vialpos:
                    vialpos = get_nextstr(split, "location")
            elif "Instrument running sample" in line:
                split = line.split()
                vialpos = get_nextstr(split, "Vial")
                if not vialpos:
                    vialpos = get_nextstr(split, "location")
                if not vialpos:
                    vialpos = get_nextstr(split, "sample")
            if vialpos:
                metadata['vialpos'] = vialpos.replace("'", "")
                break

    return metadata


def get_xml_vialnum(path):
    """
    Returns the VialNumber from an XML document, if it exists.

    Args:
        path (str): Path to the XML document. 

    """
    tree = etree.parse(path)
    root = tree.getroot()
    for vialnum in root.xpath("//*[local-name()='VialNumber']"):
        if vialnum.text:
            return vialnum.text
    return None


def get_nextstr(str_list, target_str):
    """ 
    Returns the string at the next index in :obj:`str_list`, if it exists.

    Args:
        str_list (str): List of strings. 
        target_str (str): Initial string to find. 

    """
    try:
        next_str = str_list[str_list.index(target_str) + 1]
        return next_str
    except Exception:
        return None
