import os
import numpy as np
import pytest
from rainbow import DataFile, DataDirectory


def test_validation():
    """
    Tests for constructor input validation.

    """
    datafile = DataFile(
        "", None, np.empty(0), np.empty(0), np.empty((0, 0)), {})
    with pytest.raises(Exception):
        DataDirectory(1, [datafile], {})
    with pytest.raises(Exception):
        DataDirectory("lorem", datafile, {})
    with pytest.raises(Exception):
        DataDirectory("lorem", set(), {})
    with pytest.raises(Exception):
        DataDirectory("lorem", {datafile}, [])


def test_attributes():
    """
    Tests correctness of class attributes.

    """
    datadir = DataDirectory("", [], {})
    assert datadir.name == ""
    assert sorted(datadir.datafiles) == []
    assert datadir.detectors == set()
    assert datadir.by_name == {}
    assert datadir.by_detector == {}
    assert sorted(datadir.analog) == []
    assert datadir.metadata == {}

    empty_1dim = np.empty(0)
    empty_2dim = np.empty((0, 0))
    datafile_list = [
        DataFile("cow.ch", 'ELSD', empty_1dim, empty_1dim, empty_2dim, {}),
        DataFile("bird.DAT", None, empty_1dim, empty_1dim, empty_2dim, {}),
        DataFile("ant.UV", 'UV', empty_1dim, empty_1dim, empty_2dim, {})
    ]
    datadir = DataDirectory(
        os.path.join("paper", "st.raw"), datafile_list, {'vendor': "you"})
    assert datadir.name == "st.raw"
    assert sorted(df.name for df in datadir.datafiles) == sorted(
        ["cow.ch", "ant.UV"])
    assert datadir.detectors == {'ELSD', 'UV'}
    assert sorted(datadir.by_name.keys()) == sorted(
        ["COW.CH", "BIRD.DAT", "ANT.UV"])
    assert sorted(datadir.by_detector.keys()) == sorted(['UV', 'ELSD'])
    assert sorted(df.name for df in datadir.analog) == sorted(["bird.DAT"])
    assert datadir.metadata == {'vendor': "you"}


def test_extract_traces():
    """
    Tests the `DataDirectory.extract_traces` method.

    """
    datafile = DataFile(
        "peer.MS", None, np.arange(4), np.array([301.1, 499.]),
        np.arange(8).reshape(4, 2), {})
    datadir = DataDirectory("d.raw", [datafile], {})
    with pytest.raises(Exception):
        datadir.extract_traces(301)
    with pytest.raises(Exception):
        datadir.extract_traces("d.raw")
    with pytest.raises(Exception):
        datadir.extract_traces("peer")
    with pytest.raises(Exception):
        datadir.extract_traces("peer.MS", 0)
    np.testing.assert_array_equal(
        datadir.extract_traces("peer.ms"), np.arange(8).reshape(4, 2).T)
    np.testing.assert_array_equal(
        datadir.extract_traces("pEeR.mS", 301.1),
        np.array(np.arange(0, 8, 2), ndmin=2))
    np.testing.assert_array_equal(
        datadir.extract_traces("peer.MS", 499),
        np.array(np.arange(1, 8, 2), ndmin=2))
    np.testing.assert_array_equal(
        datadir.extract_traces("peer.ms", [301.1, 499.0]),
        np.array(np.arange(8).reshape(4, 2).T))
