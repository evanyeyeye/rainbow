import os


def parse_files(path):
    """
    A
    """
    datafiles = []

    contents = set(os.listdir(path))
    if 'AcqData' not in contents:
        return datafiles

    acqdata_path = os.path.join(path, 'AcqData')
    acqdata_contents = set(os.listdir(acqdata_path))
    if {'MSTS.xml', 'MSScan.xml', 'MSScan.xsd'} <= acqdata_contents:
        if 'MSProfile.bin' in acqdata_contents:
            datafiles.append(parse_msdata(acqdata_path))

    return datafiles

def parse_msdata(path):
    pass