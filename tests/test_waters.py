"""
Unit tests for parsing Waters .raw directories.

"""
import pytest

import rainbow as rb
from tests.datatester import assert_data_directory


# Each case is (color, ext). The docstrings of the former methods describe the
# contents of each fixture:
#   - blue:      UV spectrum, MS spectrum (8-byte format), CAD channel
#   - indigo:    MS trace (2-byte format), 2 analog channels
#   - violet:    UV spectrum, 3 UV channels (analog), 2 MS spectra (6-byte
#                format), ELSD channel
#   - white:     6 MRM functions (4-byte format; 2 ES+, 4 ES-, no
#                _extern.inf), 2 analog channels
#   - turquoise: Perkin-Elmer / TurboMass .raw export with lowercase filenames
#                and PE _extern.inf polarity format
@pytest.mark.parametrize(
    "color, ext",
    [
        ("blue", "raw"),
        ("indigo", "raw"),
        ("violet", "raw"),
        ("white", "raw"),
        ("turquoise", "raw"),
    ],
    ids=["blue", "indigo", "violet", "white", "turquoise"],
)
def test_waters(color, ext):
    assert_data_directory(color, ext)


def test_acquisition_mode_tagged_from_function_type():
    # The MS acquisition mode is read from the function type in _FUNCTNS.INF,
    # not guessed: indigo is a SIR (Waters' SIM) acquisition, turquoise a full
    # scan. (SIR is the low-5-bit type code 1; an MS scan is 0.)
    def ms_modes(color):
        datadir = rb.read(f"tests/inputs/{color}.raw")
        return {df.name: df.metadata.get("acquisition_mode")
                for df in datadir.datafiles if df.detector == "MS"}

    assert ms_modes("indigo") == {"_FUNC001.DAT": "SIM"}
    assert ms_modes("turquoise") == {"_func001.dat": "Scan"}


def test_function_type_helpers_degrade_and_map():
    # The function-type helpers must not crash on a missing/short sidecar, and
    # the type-code mapping is scan (0), SIR=SIM (1), MRM (9), and untagged otherwise.
    from rainbow.waters import masslynx
    assert masslynx._function_types("/tmp/does-not-exist.inf", 3) == []
    assert masslynx._acquisition_mode(0) == "Scan"
    assert masslynx._acquisition_mode(1) == "SIM"
    assert masslynx._acquisition_mode(9) == "MRM"   # MRM: chosen transitions
    assert masslynx._acquisition_mode(12) is None  # diode array: not an MS mode


def test_a_diode_array_axis_ignores_the_m_z_bin_width():
    """The DAD wavelength axis is in nanometres on a 1 nm step, whatever
    bin_width the caller passed for the MS channels in the same run."""
    import numpy as np
    for bin_width in (1.0, 0.05):
        datadir = rb.read("tests/inputs/violet.raw", bin_width=bin_width)
        labels = np.asarray(
            datadir.get_file("_FUNC003.DAT").ylabels, dtype=float)
        assert np.allclose(np.diff(labels), 1.0), bin_width
        # The MS channels in the same run do follow bin_width.
        ms = np.asarray(datadir.get_file("_FUNC001.DAT").ylabels, dtype=float)
        assert np.min(np.diff(ms)) <= bin_width


def test_the_uv_wavelength_step_is_not_the_ms_bin_width():
    from rainbow.waters.masslynx import (
        _UV_WAVELENGTH_STEP, _FUNC_TYPE_DIODE_ARRAY)

    assert _UV_WAVELENGTH_STEP == 1.0
    assert _FUNC_TYPE_DIODE_ARRAY == 12


def test_the_function_type_names_the_detector_and_the_ion_mode_its_polarity():
    # white.raw has no _extern.inf, which is where the polarity used to come
    # from, and with it the detector: its six MRM functions (type 9) were read
    # as UV. The first word of each _FUNCTNS.INF record states both the type
    # and the ion mode (bits 5-9: 8 = ES+, 9 = ES-).
    datadir = rb.read("tests/inputs/white.raw")
    got = [(f.detector, f.metadata.get("polarity"),
            f.metadata.get("acquisition_mode")) for f in datadir.datafiles]
    assert got == [("MS", "+", "MRM")] * 2 + [("MS", "-", "MRM")] * 4


@pytest.mark.parametrize("color", ["blue", "indigo", "violet"])
def test_the_ion_mode_agrees_with_extern_inf(color):
    # Where _extern.inf states each function's polarity, the ion mode in
    # _FUNCTNS.INF states the same one, and a diode array (type 12) none.
    from rainbow.waters import masslynx
    path = f"tests/inputs/{color}.raw"
    datadir = rb.read(path)
    words = masslynx._function_words(f"{path}/_FUNCTNS.INF",
                                     len(datadir.datafiles))
    for f, (func_type, ion_mode) in zip(datadir.datafiles, words):
        if func_type == masslynx._FUNC_TYPE_DIODE_ARRAY:
            assert f.detector == "UV" and "polarity" not in f.metadata
        else:
            assert f.detector == "MS"
            assert masslynx._ION_MODE_POLARITY[ion_mode] == \
                f.metadata["polarity"]


def test_an_mrm_function_states_each_transition():
    # Three transitions of one precursor were three columns all labelled
    # 112.97. Each column is labelled by its product and states its
    # transition, precursor and product, in column order.
    import numpy as np
    f = rb.read("tests/inputs/white.raw").get_file("_FUNC001.DAT")
    assert np.allclose(f.ylabels, [40.0, 52.9, 84.9])
    assert f.metadata["transitions"] == [
        {"precursor_mz": 112.97, "product_mz": 40.0},
        {"precursor_mz": 112.97, "product_mz": 52.9},
        {"precursor_mz": 112.97, "product_mz": 84.9}]
    f = rb.read("tests/inputs/white.raw").get_file("_FUNC005.DAT")
    assert [t["precursor_mz"] for t in f.metadata["transitions"]] == [
        98.8, 100.84, 100.84]


# NOT COVERED, and no bundled fixture can cover it: reading the axis from the
# declared function type rather than from the detector only changes an
# answer for a function that is (a) not type 12 and (b) in the 6/8 format,
# which is the only one that bins rather than taking its labels from
# _FUNCTNS.INF, and (c) has no polarity. Covering it needs a fixture that does
# not exist yet.


@pytest.mark.parametrize("func_type,detector,expected", [
    # A function the file calls a diode array is a wavelength axis whatever the
    # polarity metadata says.
    (12, 'UV', True),
    (12, 'MS', True),
    # Any other recorded type is m/z, and must stay subject to bin_width. This
    # is the MRM-without-polarity case: the polarity alone would call it UV and
    # silently exempt an m/z axis from the caller's binning.
    (0, 'UV', False),
    (6, 'UV', False),
    (6, 'MS', False),
    # With no recorded type there is nothing better than the polarity.
    (None, 'UV', True),
    (None, 'MS', False),
])
def test_the_wavelength_axis_rule(func_type, detector, expected):
    from rainbow.waters.masslynx import _is_wavelength_axis

    assert _is_wavelength_axis(func_type, detector) is expected


def test_a_diode_array_function_ignores_bin_width():
    # The rule's whole point: an m/z bin width must not merge DAD channels.
    # blue.raw's UV function is a real diode array, so a coarse bin_width must
    # leave its wavelength axis alone.
    import numpy as np
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plain = rb.read("tests/inputs/blue.raw")
        coarse = rb.read("tests/inputs/blue.raw", bin_width=5.0)

    for a, b in zip(plain.datafiles, coarse.datafiles):
        if a.detector != 'UV':
            continue
        np.testing.assert_array_equal(np.asarray(a.ylabels, dtype=float),
                                      np.asarray(b.ylabels, dtype=float))


def _renamed_copy(source, target, rename):
    """A copy of a .raw folder with each file named rename(name)."""
    import os
    import shutil
    os.makedirs(target)
    for name in os.listdir(source):
        shutil.copyfile(os.path.join(source, name),
                        os.path.join(target, rename(name)))
    return str(target)


def test_a_raw_folder_named_in_another_case_reads_the_same(tmp_path):
    """Waters file names are matched regardless of case: a copy of indigo.raw
    whose folder and files are named in another case reads as indigo does."""
    import numpy as np
    original = rb.read("tests/inputs/indigo.raw")
    path = _renamed_copy("tests/inputs/indigo.raw", tmp_path / "INDIGO.RAW",
                         str.lower)
    copy = rb.read(path)
    assert sorted(f.name.lower() for f in copy.datafiles + copy.analog) == \
        sorted(f.name.lower() for f in original.datafiles + original.analog)
    for f in original.datafiles + original.analog:
        g = copy.get_file(f.name.lower())
        assert np.array_equal(g.xlabels, f.xlabels)
        assert np.array_equal(g.data, f.data)
    assert copy.metadata == original.metadata


def test_read_metadata_lists_data_files_whatever_their_case(tmp_path):
    """read_metadata finds the _FUNC and _CHRO files of a folder named in lower
    case, listed as they are on disk, as it does in upper case."""
    from rainbow import waters
    upper = waters.read_metadata("tests/inputs/indigo.raw")
    assert upper["datafiles"] == ["_FUNC001.DAT", "_CHRO001.DAT",
                                  "_CHRO002.DAT"]
    path = _renamed_copy("tests/inputs/indigo.raw", tmp_path / "indigo.raw",
                         str.lower)
    lower = waters.read_metadata(path)
    assert lower["datafiles"] == ["_func001.dat", "_chro001.dat",
                                  "_chro002.dat"]
    assert lower["metadata"] == upper["metadata"]


def test_requested_files_match_regardless_of_case(tmp_path):
    """waters.read and rb.read take requested_files in any case, on files named
    in any case."""
    from rainbow import waters
    path = _renamed_copy("tests/inputs/indigo.raw", tmp_path / "indigo.raw",
                         str.lower)
    for read in (waters.read, rb.read):
        datadir = read(path, requested_files=["_FUNC001.DAT"])
        assert [f.name for f in datadir.datafiles + datadir.analog] == \
            ["_func001.dat"]
    datadir = waters.read("tests/inputs/turquoise.raw",
                          requested_files=["_FUNC001.DAT"])
    assert [f.name for f in datadir.datafiles] == ["_func001.dat"]


def test_white_exports_each_mrm_transition_by_its_transition():
    # Every transition is exported as a mass chromatogram, named by its
    # precursor and product (two transitions of a function can share a
    # product), with the function's own retention times and counts.
    import numpy as np
    datadir = rb.read("tests/inputs/white.raw")
    got = rb.measurements(datadir)
    names = [m["identifier"] for m in got]
    assert len(names) == len(set(names)) == 15
    assert names[:3] == ["_FUNC001.DAT MRM 112.97 > 40",
                         "_FUNC001.DAT MRM 112.97 > 52.9",
                         "_FUNC001.DAT MRM 112.97 > 84.9"]
    assert "_FUNC005.DAT MRM 100.84 > 85.22" in names
    f = datadir.get_file("_FUNC001.DAT")
    one = got[1]
    assert one["mz"] == 52.9 and one["label"] == "_FUNC001.DAT (MRM 112.97 > 52.9)"
    assert np.allclose(one["values"], f.data[:, 1])
    assert np.allclose(one["times"], f.xlabels)


def test_a_function_nothing_names_states_no_detector(tmp_path):
    """Without _FUNCTNS.INF and without a polarity, a function is not called
    UV: its detector is unstated, its keys as recorded, and it stays among
    the run's datafiles (several columns: not an analog trace)."""
    import shutil
    src = "tests/inputs/turquoise.raw"
    dst = tmp_path / "bare.raw"
    shutil.copytree(src, dst)
    for name in ("_functns.inf", "_extern.inf"):
        (dst / name).unlink()
    datadir = rb.read(str(dst))
    func = datadir.get_file("_func001.dat")
    assert func.detector is None
    assert func in datadir.datafiles and func not in datadir.analog
    full = rb.read(src, bin_width="recorded").get_file("_func001.dat")
    assert len(func.ylabels) == len(full.ylabels)


def test_a_diode_array_nothing_names_stays_in_the_run(tmp_path):
    """violet.raw without _FUNCTNS.INF: its diode array (_FUNC003) has no
    polarity, so no detector is stated; it is still one of the run's
    datafiles, by no detector, its wavelengths as recorded, and the ASM
    export says why it carries no cube for it."""
    import shutil
    import warnings
    dst = tmp_path / "violet.raw"
    shutil.copytree("tests/inputs/violet.raw", dst)
    (dst / "_FUNCTNS.INF").unlink()
    datadir = rb.read(str(dst))
    func = datadir.get_file("_FUNC003.DAT")
    assert func.detector is None
    assert func in datadir.datafiles
    assert func.data.shape[1] > 1
    assert None not in datadir.by_detector
    assert {f.name for f in datadir.datafiles if f.detector == "MS"} == \
        {"_FUNC001.DAT", "_FUNC002.DAT"}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        datadir.to_asm()
    assert any("_FUNC003.DAT" in str(c.message) and "states no detector"
               in str(c.message) for c in caught)
