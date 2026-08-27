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


@pytest.mark.parametrize(
    "call",
    [
        lambda: rb.agilent.read(AGILENT_FIXTURE, labels_only=True),
        lambda: rb.waters.read(WATERS_FIXTURE, labels_only=True),
    ],
)
def test_the_labels_only_shortcut_is_not_public(call):
    # It exists for mz_resolution, which reads nothing but the m/z axis. What
    # it returns is not a usable read: the labels are right and the data has
    # zero columns, so extract_traces raises IndexError on a label the file
    # plainly has. rb.read spells it _labels_only; the vendor entry points are
    # documented in api.rst just as it is, so they spell it the same way rather
    # than offering the sharp edge under a public name.
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        call()

    datadir = rb.agilent.read(os.path.join("tests", "inputs", "orange.D"),
                              bin_width=0.1, _labels_only=True)
    datafile = datadir.get_file("MSD1.MS")
    assert datafile.ylabels.size > 1
    assert datafile.data.shape[1] == 0


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


def test_a_sequence_directory_passed_to_read_names_read_sequence():
    # "Rainbow cannot read X." on its own is a dead end when the answer is one
    # function away.
    with pytest.raises(Exception, match="read_sequence"):
        rb.read("tests/inputs")


def test_a_single_run_passed_to_read_sequence_names_read():
    with pytest.raises(Exception, match=r"rb\.read\(\)"):
        rb.read_sequence(AGILENT_FIXTURE)


def test_an_unsuffixed_directory_is_told_about_format(tmp_path):
    # A .D directory renamed without its suffix, holding nothing rainbow sniffs.
    plain = tmp_path / "Caffeine 3"
    plain.mkdir()
    (plain / "notes.txt").write_text("nothing to parse here")
    with pytest.raises(Exception, match="format="):
        rb.read(str(plain))


def test_a_missing_path_says_so():
    # Caught by the vendor parser before the vendor-resolution error, and its
    # message already says what is wrong.
    with pytest.raises(Exception, match="is not a directory"):
        rb.read("tests/inputs/does-not-exist.D")
