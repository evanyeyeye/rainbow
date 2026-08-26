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
    path = _copy_without_suffix(WATERS_FIXTURE, tmp_path, "Caffeine 3")
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


# The 1.5.0 migration affordance: `precision` was split into `bin_width` and
# `display_precision`, and `precision` sits positionally where
# `display_precision` now does, so a caller who misses the change gets a wrong
# answer rather than an error. Every documented entry point must say so; this
# had no test at all, and replacing the whole guard with a no-op passed the
# suite.
@pytest.mark.parametrize(
    "call",
    [
        lambda: rb.read(AGILENT_FIXTURE, precision=3),
        lambda: rb.read_sequence("tests/inputs", precision=3),
        lambda: rb.agilent.read(AGILENT_FIXTURE, precision=3),
        lambda: rb.agilent.read_sequence("tests/inputs", precision=3),
        lambda: rb.waters.read(WATERS_FIXTURE, precision=3),
    ],
)
def test_precision_names_what_replaced_it(call):
    with pytest.raises(TypeError) as excinfo:
        call()
    message = str(excinfo.value)
    assert "no longer takes precision" in message
    assert "bin_width" in message and "display_precision" in message


@pytest.mark.parametrize(
    "call",
    [
        lambda: rb.read(AGILENT_FIXTURE, prec=3),
        lambda: rb.waters.read(WATERS_FIXTURE, prec=3),
    ],
)
def test_prec_names_what_replaced_it(call):
    with pytest.raises(TypeError, match="no longer takes prec"):
        call()


def test_an_argument_that_never_existed_still_reads_as_a_typo():
    # The guard must not turn every unknown keyword into a migration lecture.
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        rb.agilent.read(AGILENT_FIXTURE, nonsense=1)


# Flag validation. Each of these was a live check that no test exercised, so
# deleting the check passed the suite.
@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"telemetry": "yes"}, "telemetry flag must be a boolean"),
        ({"hrms": "yes"}, "hrms flag must be a boolean"),
        ({"centroid": 1}, "centroid flag must be a boolean"),
    ],
)
def test_flags_must_be_booleans(kwargs, message):
    with pytest.raises(Exception, match=message):
        rb.read(AGILENT_FIXTURE, **kwargs)


def test_display_precision_and_bin_width_are_validated():
    with pytest.raises(Exception, match="display_precision"):
        rb.read(AGILENT_FIXTURE, display_precision=-1)
    with pytest.raises(Exception, match="display_precision"):
        rb.read(AGILENT_FIXTURE, display_precision=True)
    with pytest.raises(Exception, match="bin_width"):
        rb.read(AGILENT_FIXTURE, bin_width=0)
    with pytest.raises(Exception, match="bin_width"):
        rb.read(AGILENT_FIXTURE, bin_width=-1.0)
