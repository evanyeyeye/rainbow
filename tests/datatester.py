"""
Helpers for parsing-file-format tests.

"""
import json
from pathlib import Path
import numpy as np
import rainbow as rb


def assert_data_directory(color, ext, hrms=False, telemetry=False):
    """
    Runs all checks for a DataDirectory after parsing.

    The DataDirectory is specified by color because of the
        naming scheme of the inputs directory.

    The attributes and metadata for each directory is stored in
        a file in the jsons directory.

    The axis labels and data values are stored as a csv in the
        outputs directory.

    """
    tests_path = Path("tests")
    json_path = tests_path / "outputs" / color / "info.json"
    with open(str(json_path)) as json_f:
        json_data = json.load(json_f)

    data_names = []
    detectors = set()
    detector_to_names = {}
    analog_names = []
    for name in json_data['datafiles']:
        file_dict = json_data['datafiles'][name]
        detector = file_dict['detector']
        if detector is None:
            analog_names.append(name)
            continue
        data_names.append(name)
        detectors.add(detector)
        if detector in detector_to_names:
            detector_to_names[detector].append(name)
        else:
            detector_to_names[detector] = [name]

    datadir_path = tests_path / "inputs" / (color + "." + ext)
    datadir = rb.read(str(datadir_path), hrms=hrms, telemetry=telemetry)

    # Tests attributes of the DataDirectory.
    # Also tests classification of its DataFiles.
    assert datadir.name == color + "." + ext
    assert sorted(df.name for df in datadir.datafiles) == sorted(data_names)
    assert datadir.detectors == detectors
    assert sorted(datadir.by_name.keys()) == sorted(
        [name.upper() for name in data_names] +
        [name.upper() for name in analog_names])
    assert sorted(datadir.by_detector.keys()) == sorted(detector_to_names.keys())
    for key in datadir.by_detector:
        assert sorted(df.name for df in datadir.by_detector[key]) == sorted(
            detector_to_names[key])
    assert sorted(df.name for df in datadir.analog) == sorted(analog_names)
    assert datadir.metadata == json_data['metadata']

    # Tests the attributes and data values of each DataFile.
    outputs_path = tests_path / "outputs" / color
    for name in json_data['datafiles']:
        datafile = datadir.get_file(name)
        file_dict = json_data['datafiles'][name]

        assert datafile.name == name
        assert datafile.detector == file_dict['detector']
        assert datafile.metadata == file_dict['metadata']

        shape = tuple(file_dict['shape'])
        assert datafile.xlabels.size == shape[0]
        assert datafile.ylabels.size == shape[1]
        assert datafile.data.shape == shape
        csv_path = outputs_path / (Path(name).stem + ".csv")
        with open(csv_path) as csv_f:
            csv_lines = csv_f.read().splitlines()
            data_lines = datafile.to_csvstr().splitlines()
        csv_list = [tuple(map(float, line.split(','))) for line in csv_lines[1:]]
        data_list = [tuple(map(float, line.split(','))) for line in data_lines[1:]]
        assert csv_lines[0] == data_lines[0]
        # Compare numerically with a tight tolerance rather than by exact
        # text. Retention times are accumulated with np.arange, whose last
        # bit can differ across NumPy versions/platforms; an exact float
        # comparison is spuriously fragile while still failing on any real
        # numeric discrepancy.
        assert len(csv_list) == len(data_list)
        np.testing.assert_allclose(
            np.array(data_list), np.array(csv_list),
            rtol=1e-9, atol=1e-9,
            err_msg=f"{name}: data differs beyond tolerance")
