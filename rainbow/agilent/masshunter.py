import os
import struct
import numpy as np
import lzf
from lxml import etree


def parse_files(path):
    """
    """
    datafiles = []

    contents = set(os.listdir(path))
    if 'AcqData' not in contents:
        return datafiles

    acqdata_path = os.path.join(path, 'AcqData')
    acqdata_contents = set(os.listdir(acqdata_path))
    if {'MSTS.xml', 'MSScan.xsd', 'MSScan.bin'} <= acqdata_contents:
        if 'MSProfile.bin' in acqdata_contents:
            datafiles.append(parse_msdata(path))

    return datafiles

def parse_msdata(path):
    """
    """
    acqdata_path = os.path.join(path, 'AcqData')

    # Get number of scans from MSTS.xml
    tree = etree.parse(os.path.join(acqdata_path, "MSTS.xml"))
    root = tree.getroot()
    num_times = 0
    for time_segment in root.findall("TimeSegment"):
        num_times += int(time_segment.find("NumOfScans").text)
    # print(num_times)

    # Get file structure of MSScan.bin from MSScan.xsd
    # The root type is ScanRecordType
    tree = etree.parse(os.path.join(acqdata_path, "MSScan.xsd"))
    root = tree.getroot()
    namespace = tree.xpath('namespace-uri(.)') 

    complex_types = {}
    for complex_type in root.findall(f"{{{namespace}}}complexType"):
        elements = []
        for element in complex_type[0].findall(f"{{{namespace}}}element"):
            elements.append((element.get('name'), element.get('type')))
        complex_types[complex_type.get('name')] = elements 
    assert(len(root[0][1][0].getchildren()) == 1)

    # Parse info from MSScan.bin
    offsets = {
        'start': 0x58
    }

    f = open(os.path.join(acqdata_path, "MSScan.bin"), 'rb')

    f.seek(offsets['start'])
    f.seek(struct.unpack('<I', f.read(4))[0])
    info = np.empty(num_times, dtype=object)
    for i in range(num_times):
        scan_vals = recur_complex_type(f, complex_types, "ScanRecordType")
        # if i == 0:
        #     print(scan_vals)
        spec_vals = scan_vals['SpectrumParamValues']
        info[i] = (
            scan_vals['ScanTime'], 
            spec_vals['SpectrumOffset'], 
            spec_vals['ByteCount'], 
            spec_vals['PointCount'],
            spec_vals['UncompressedByteCount'],
            scan_vals['CalibrationID']
        )
    assert(f.tell() == os.path.getsize(os.path.join(acqdata_path, "MSScan.bin")))

    # Parse calibration info from MSMassCal.bin
    f = open(os.path.join(acqdata_path, "MSMassCal.bin"), 'rb')
    f.seek(0x44)

    start, stop = struct.unpack('<II', f.read(8))
    cals = np.empty(num_times, dtype=object)
    for i in range(num_times): 
        traditional = struct.unpack('<dd', f.read(16))
        poly = struct.unpack('<' + 8 * 'd', f.read(8 * 8))
        cals[i] = (traditional, poly)
        f.read(4)
    assert(f.tell() == os.path.getsize(os.path.join(acqdata_path, "MSMassCal.bin")))

    # Decode compressed MSProfile.bin
    f = open(os.path.join(acqdata_path, "MSProfile.bin"), 'rb')
    const_1 = None
    const_2 = None
    const_3 = None
    times = np.empty(num_times)
    masses = None
    data_array = None
    for i in range(num_times):
        
        time, offset, byte_c, points_c, uncompressed_byte_c, cal_id = info[i]
        times[i] = time
        assert(cal_id >= 1 and cal_id <= 1)
        if not const_1:
            const_1 = (points_c, uncompressed_byte_c)
        assert(points_c == const_1[0])
        assert(uncompressed_byte_c == const_1[1])

        f.seek(offset)
        db = lzf.decompress(f.read(byte_c), uncompressed_byte_c)
        assert(len(db) == 16 + points_c * 4)

        initial, delta = struct.unpack('<dd', db[:16])
        if not const_2:
            const_2 = (initial, delta)
        assert(initial == const_2[0])
        assert(delta == const_2[1])
        intensities = struct.unpack('<' + points_c * 'I', db[16:])
        
        scale, t0 = cals[cal_id - 1][0]
        if not const_3:
            const_3 = (scale, t0)
        assert(scale == const_3[0])
        assert(t0 == const_3[1])
        pairs = {}
        if masses is None:
            masses = np.empty(len(intensities))
            for j in range(len(intensities)):
                masses[j] = (scale * (initial - t0)) ** 2
                initial += delta
        if data_array is None:
            data_array = np.empty((num_times, masses.size), dtype=np.uint32)
        data_array[i] = np.array(intensities)

    print(times)
    print(masses, len(masses))
    for i in range(10):
        print(i, np.sum(data_array[i]))
   
def recur_complex_type(f, complex_types, complex_name):
    values = {}
    complex_type = complex_types[complex_name]
    for element_name, type_name in complex_type:
        values[element_name] = parse_type(f, complex_types, type_name)
    return values

def parse_type(f, complex_types, name):
    if name == 'xs:byte':
        return struct.unpack('c', f.read(1))[0]
    elif name == 'xs:short':
        raise Exception("THE TYPE {name} EXISTS")
    elif name == 'xs:int':
        return struct.unpack('<I', f.read(4))[0]
    elif name == 'xs:long':
        return struct.unpack('<Q', f.read(8))[0]
    elif name == 'xs:float':
        raise Exception("THE TYPE {name} EXISTS")
    elif name == 'xs:double':
        return struct.unpack('<d', f.read(8))[0]
    return recur_complex_type(f, complex_types, name)

