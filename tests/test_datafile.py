import os
import numpy as np
import pytest
from rainbow import DataFile


def test_validation():
    """
    Tests for constructor input validation.

    """
    empty_1dim = np.empty(0)
    empty_2dim = np.empty((0, 0))
    with pytest.raises(Exception):
        DataFile(1, None, empty_1dim, empty_1dim, empty_2dim, {})
    with pytest.raises(Exception):
        DataFile("lorem", 'OK', empty_1dim, empty_1dim, empty_2dim, {})
    with pytest.raises(Exception):
        DataFile("lorem", 'UV', [], empty_1dim, empty_2dim, {})
    with pytest.raises(Exception):
        DataFile("lorem", 'UV', empty_2dim, empty_1dim, empty_2dim, {})
    with pytest.raises(Exception):
        DataFile("lorem", 'UV', empty_1dim, [], empty_2dim, {})
    with pytest.raises(Exception):
        DataFile("lorem", 'UV', empty_1dim, empty_2dim, empty_2dim, {})
    with pytest.raises(Exception):
        DataFile("lorem", 'UV', empty_1dim, empty_1dim, [[]], {})
    with pytest.raises(Exception):
        DataFile("lorem", 'UV', empty_1dim, empty_1dim, empty_1dim, {})
    with pytest.raises(Exception):
        DataFile("lorem", 'UV', empty_1dim, empty_1dim, empty_2dim, set())


def test_attributes():
    """
    Tests correctness of class attributes.

    """
    datafile = DataFile(
        os.path.join("kick", "ball.ch"), 'ELSD', np.ones(5), np.zeros(1),
        np.arange(5).reshape((5, 1)), {'pick': 'me'})
    assert datafile.name == "ball.ch"
    assert datafile.detector == 'ELSD'
    np.testing.assert_array_equal(datafile.xlabels, np.ones(5))
    np.testing.assert_array_equal(datafile.ylabels, np.zeros(1))
    np.testing.assert_array_equal(
        datafile.data, np.arange(5).reshape((5, 1)))
    assert datafile.metadata == {'pick': 'me'}


def test_extract_traces():
    """
    Tests the `DataFile.extract_traces` method.

    """
    datafile = DataFile(
        "sky.DAT", None, np.arange(4), np.array([301.0, 499.9]),
        np.arange(8).reshape(4, 2), {})
    with pytest.raises(Exception):
        datafile.extract_traces("301")
    with pytest.raises(Exception):
        datafile.extract_traces(["499.9"])
    with pytest.raises(Exception):
        datafile.extract_traces(499.0)
    with pytest.raises(Exception):
        datafile.extract_traces([500])
    np.testing.assert_array_equal(
        datafile.extract_traces(), np.arange(8).reshape(4, 2).T)
    np.testing.assert_array_equal(
        datafile.extract_traces(301.0),
        np.array(np.arange(0, 8, 2), ndmin=2))
    np.testing.assert_array_equal(
        datafile.extract_traces(499.9),
        np.array(np.arange(1, 8, 2), ndmin=2))
    np.testing.assert_array_equal(
        datafile.extract_traces([301, 499.9]),
        np.array(np.arange(8).reshape(4, 2).T))


def test_to_csvstr():
    """
    Tests the `DataFile.to_csvstr` method.

    """
    datafile = DataFile(
        "nolabel.ms", None, np.arange(2), np.array(['']),
        np.arange(2, 4).reshape(2, 1), {})
    with pytest.raises(Exception):
        datafile.to_csvstr(' ')
    with pytest.raises(Exception):
        datafile.to_csvstr(0)
    csvstr = "RT (min),\n0,2\n1,3\n"
    assert datafile.to_csvstr() == csvstr
    assert datafile.to_csvstr('') == csvstr
    assert datafile.to_csvstr(['']) == csvstr

    datafile = DataFile(
        "dino.UV", None, np.arange(3), np.array([220, 280]),
        np.arange(6).astype(np.float32).reshape(3, 2), {})
    with pytest.raises(Exception):
        datafile.to_csvstr('')
    with pytest.raises(Exception):
        datafile.to_csvstr(0)
    assert datafile.to_csvstr() == \
        "RT (min),220,280\n0,0.0,1.0\n1,2.0,3.0\n2,4.0,5.0\n"
    assert datafile.to_csvstr([220.0]) == \
        "RT (min),220.0\n0,0.0\n1,2.0\n2,4.0\n"
    assert datafile.to_csvstr([280]) == \
        "RT (min),280\n0,1.0\n1,3.0\n2,5.0\n"
    assert datafile.to_csvstr([220., 280.]) == \
        "RT (min),220.0,280.0\n0,0.0,1.0\n1,2.0,3.0\n2,4.0,5.0\n"
