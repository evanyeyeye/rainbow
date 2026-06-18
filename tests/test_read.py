"""
Unit tests for rb.read's vendor dispatch: extension first, content sniffing for
unsuffixed directories, and the explicit ``format`` override.
"""
import os
import shutil

import pytest

import rainbow as rb

WATERS_FIXTURE = os.path.join("tests", "inputs", "blue.raw")
AGILENT_FIXTURE = os.path.join("tests", "inputs", "brown.D")


def _copy_without_suffix(fixture, dest_dir, new_name):
    """Copy a .raw/.D fixture to a folder whose name has no vendor suffix."""
    dest = os.path.join(str(dest_dir), new_name)
    shutil.copytree(fixture, dest)
    return dest


def test_extension_still_dispatches():
    # The conventional suffixes must keep working exactly as before.
    assert rb.read(WATERS_FIXTURE).metadata["vendor"] == "Waters"
    assert "Agilent" in rb.read(AGILENT_FIXTURE).metadata["vendor"]


def test_sniffs_waters_without_suffix(tmp_path):
    path = _copy_without_suffix(WATERS_FIXTURE, tmp_path, "Noscapine 3")
    assert rb.read(path).metadata["vendor"] == "Waters"


def test_sniffs_agilent_without_suffix(tmp_path):
    path = _copy_without_suffix(AGILENT_FIXTURE, tmp_path, "renamed_run")
    assert "Agilent" in rb.read(path).metadata["vendor"]


def test_format_override(tmp_path):
    path = _copy_without_suffix(WATERS_FIXTURE, tmp_path, "anything")
    assert rb.read(path, format="waters").metadata["vendor"] == "Waters"


def test_invalid_format_raises():
    with pytest.raises(Exception):
        rb.read(WATERS_FIXTURE, format="thermo")


def test_unknown_directory_raises(tmp_path):
    empty = os.path.join(str(tmp_path), "not_a_dataset")
    os.makedirs(empty)
    open(os.path.join(empty, "readme.txt"), "w").close()
    with pytest.raises(Exception):
        rb.read(empty)


def test_detect_vendor_helpers(tmp_path):
    waters = _copy_without_suffix(WATERS_FIXTURE, tmp_path, "w")
    agilent = _copy_without_suffix(AGILENT_FIXTURE, tmp_path, "a")
    assert rb._detect_vendor(waters) == "waters"
    assert rb._detect_vendor(agilent) == "agilent"
    assert rb._detect_vendor(str(tmp_path)) is None
    # Extension takes precedence over (and short-circuits) content.
    assert rb._detect_vendor(WATERS_FIXTURE) == "waters"
    assert rb._detect_vendor(AGILENT_FIXTURE) == "agilent"


def test_read_metadata_sniffs(tmp_path):
    path = _copy_without_suffix(WATERS_FIXTURE, tmp_path, "md_test")
    assert rb.read_metadata(path)["metadata"]["vendor"] == "Waters"


def test_read_metadata_format_override(tmp_path):
    path = _copy_without_suffix(WATERS_FIXTURE, tmp_path, "md_override")
    assert rb.read_metadata(
        path, format="waters")["metadata"]["vendor"] == "Waters"


def test_read_metadata_invalid_format_raises():
    with pytest.raises(Exception):
        rb.read_metadata(WATERS_FIXTURE, format="thermo")
