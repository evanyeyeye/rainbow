""" 
Methods for parsing Agilent OpenLab CDS .dx files. 
 
"""

import io
import os
import zipfile
from collections import Counter
from lxml import etree

from rainbow.agilent.fileparsers import parse_file_from_fileobj

"""
MAIN PARSING METHODS

"""

def parse_dx_file(path, prec=0, requested_files=None):
    """
    Finds and parses Agilent Openlab CDS data files \
        with a .ch, .uv, or .ms extension from a .dx compressed directory.
    
    Args:
        path (str): Path to the .dx file.
        prec (int, optional): Number of decimals to round mz values.
        requested_files (list, optional): List of filenames to parse.

    Returns:
        List with a DataFile for each parsed data file. 

    """
    datafiles = []
    with zipfile.ZipFile(path, 'r') as zip_file:
        for name in zip_file.namelist():
            # Skip directories
            if name.endswith('/'):
                continue
            
            # Get just the filename without path
            filename = os.path.basename(name)
            
            if requested_files and filename.lower() not in requested_files:
                continue
            
            with zip_file.open(name) as zipped_file:
                file_content = zipped_file.read()
            
            # Wrap in BytesIO for seek-compatibility
            fileobj = io.BytesIO(file_content)
            datafile = parse_file_from_fileobj(fileobj, filename, prec)
            
            if datafile:
                datafiles.append(datafile)
    return datafiles


""" 
DIRECTORY METADATA PARSING METHODS 

"""


def parse_metadata(path, datafiles):
    """
    Parses Agilent metadata from a .dx file.

    First, the DataFiles are checked for date and vial position metadata.

    Then, the injection.acmd file is parsed for comprehensive metadata.

    Args:
        path (str): Path to the .dx file.
        datafiles (list): List of DataFile objects.  
    
    Returns:
        Dictionary containing directory metadata. 

    """
    metadata = {}
    metadata['vendor'] = "Agilent"
    metadata['format'] = "OpenLab CDS"

    # Scan each DataFile for the date and vial position.
    # These may be stored in multiple files but the values are constant.
    # In MS files, the time may be saved in a different format.
    # Get the most common values if they differ across files
    dates = Counter(datafile.metadata['date'] 
                    for datafile in datafiles 
                    if 'date' in datafile.metadata)
    vialposs = Counter(datafile.metadata['vialpos'] 
                       for datafile in datafiles 
                       if 'vialpos' in datafile.metadata)
    if dates:
        metadata['date'] = dates.most_common(1)[0][0]
    if vialposs:
        metadata['vialpos'] = vialposs.most_common(1)[0][0]

    # Parse injection.acmd for comprehensive metadata
    with zipfile.ZipFile(path, 'r') as zip_file:
        if 'injection.acmd' in zip_file.namelist():
            with zip_file.open('injection.acmd') as f:
                tree = etree.parse(f)
                root = tree.getroot()
                
                # Initialize raw metadata structure
                metadata['raw'] = {
                    'injection.acmd': {
                        'InjectionInfo': {},
                        'Signals': {}
                    }
                }
                
                # Extract InjectionInfo fields
                root_text = '{urn:schemas-agilent-com:acmd20}'
                inj_pattern = f'.//{root_text}InjectionInfo'
                injection_info = root.find(inj_pattern)
                if injection_info is not None:
                    ii_dict = metadata['raw']['injection.acmd']['InjectionInfo']
                    for child in injection_info:
                        if isinstance(child.tag, str):
                            tag_name = child.tag.replace(root_text, '')
                            # Skip the Signals element
                            if tag_name != 'Signals' and child.text is not None:
                                ii_dict[tag_name] = child.text.strip()
                    
                    # Extract normalized date from RunDateTime
                    if 'date' not in metadata and 'RunDateTime' in ii_dict:
                        metadata['date'] = ii_dict['RunDateTime']
                    
                    # Extract normalized vialpos from Location
                    if 'vialpos' not in metadata and 'Location' in ii_dict:
                        location = ii_dict['Location']
                        if location:  # Only set if not empty
                            metadata['vialpos'] = location
                
                
                # Extract Signal metadata, keyed by TraceId
                signals = root.findall(f'.//{root_text}Signal')
                signals_data = metadata['raw']['injection.acmd']['Signals']
                for signal in signals:
                    trace_id = None
                    signal_data = {}
                    
                    for child in signal:
                        if isinstance(child.tag, str):
                            tag_name = child.tag.replace(root_text, '')
                            if child.text is not None:
                                value = child.text.strip()
                                signal_data[tag_name] = value
                                if tag_name == 'TraceId':
                                    trace_id = value
                    
                    # Store signal data keyed by TraceId
                    if trace_id:
                        signals_data[trace_id] = signal_data

    return metadata

