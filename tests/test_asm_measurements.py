"""
rb.measurements: the measurements to_asm writes, read without the document.

Each must be what a reader of the document reads back from that measurement,
so every field is checked against to_asm's own document, written to JSON and
parsed, on every bundled run.
"""
import json
import os
import warnings

import numpy as np
import pytest

import rainbow as rb
from rainbow import asm

INPUTS = os.path.join("tests", "inputs")
RUNS = sorted(name for name in os.listdir(INPUTS)
              if name.endswith((".D", ".raw", ".dx")))
DOCUMENTS = sorted(name for name in os.listdir(INPUTS)
                   if name.endswith(".asm.json"))


def _quiet(call, *args, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return call(*args, **kwargs)


def _runs():
    for name in RUNS:
        yield name, lambda name=name: _quiet(
            rb.read, os.path.join(INPUTS, name), peaks=True)
    for name in DOCUMENTS:
        def read(name=name):
            with open(os.path.join(INPUTS, name)) as f:
                return _quiet(rb.from_asm, json.load(f))
        yield name, read


def _read_back(measurement):
    """What a reader of the written document reads of one measurement."""
    said = {}
    asm._absorb_samples([measurement], said)
    asm._absorb_envelope(measurement, said)
    return said


@pytest.mark.parametrize("name, read", list(_runs()),
                         ids=[name for name, _ in _runs()])
def test_each_measurement_is_what_the_document_reads_back(name, read):
    datadir = read()
    ions = [100.0, 200.0, 300.0]
    document = json.loads(json.dumps(_quiet(
        rb.DataDirectory.to_asm, datadir, export_dad_cube=False, ions=ions)))
    written = [m for chrom in next(
        v for k, v in document.items() if k.endswith("aggregate document")
    )[next(k for k in next(v for k, v in document.items()
                           if k.endswith("aggregate document"))
           if k.endswith("chromatography document"))]
        for m in chrom["measurement aggregate document"]
        ["measurement document"]]
    got = _quiet(rb.measurements, datadir, ions=ions)

    assert [m["identifier"] for m in got] == \
        [m["measurement identifier"] for m in written]
    for record, measurement in zip(got, written):
        mass = asm._MASS_CHROMATOGRAM_CUBE in measurement
        cube = measurement[asm._MASS_CHROMATOGRAM_CUBE if mass
                           else asm._CHROMATOGRAM_CUBE]
        assert record["label"] == cube["label"]
        channel = asm._channel_metadata(measurement)
        if mass:
            assert record["mz"] is not None
            assert record["detector"] == "MS"
            assert record["unit"] == "Counts"
            assert np.array_equal(
                record["values"],
                np.asarray(cube["data"]["measures"][0], float))
        else:
            assert record["mz"] is None
            assert record["channel"] == channel
            assert record["detector"] == asm._detector_of(measurement)
            # The trace a reader rebuilds from the written document.
            rebuilt = asm._datafile_from_measurement(measurement)
            assert record["unit"] == rebuilt.metadata.get("unit")
            # The run's own times; the document's are its seconds, which a
            # float32 time axis rounds once more on the way there.
            assert np.allclose(record["times"], rebuilt.xlabels,
                               rtol=1e-6, atol=1e-9)
            assert np.array_equal(record["values"], rebuilt.data[:, 0])
        source = datadir.get_file(record["file"])
        assert np.array_equal(record["times"], source.xlabels)
        said = _read_back(measurement)
        assert record["sample"] == {
            "identifier": said.get("sample"),
            "name": said.get("sample_name"),
            "location": said.get("vialpos"),
            "plate": said.get("well_plate_id"),
            "role": said.get("sample_role"),
            "fields": said.get("sample_custom") or {}}
        volume = said.get("injection_volume")
        assert record["injection"] == {
            "identifier": said.get("injection_identifier"),
            "time": said.get("injection_time"),
            "volume_ul": volume["value"] if volume else None}
        assert record["measurement_time"] == said.get("date")
        assert record["acquisition_method"] == said.get("acq_method")
        assert record["peaks"] == rb.peaks_from_asm(measurement)


def test_the_arrays_stay_numpy_and_nothing_is_said_of_a_document():
    """No list is made of any array, and a run whose full-scan MS is left out,
    or whose time has no UTC offset, gets no warning that a document will not
    validate: there is no document."""
    datadir = rb.read(os.path.join(INPUTS, "yellow.D"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        got = rb.measurements(datadir)
    assert got
    for record in got:
        cube = record["document"].get(asm._CHROMATOGRAM_CUBE) or \
            record["document"][asm._MASS_CHROMATOGRAM_CUBE]
        assert isinstance(cube["data"]["measures"][0], np.ndarray)
        assert isinstance(cube["data"]["dimensions"][0], np.ndarray)
        assert record["times"] is not None and len(record["times"]) == \
            len(record["values"])


def test_a_full_scan_ion_is_taken_as_to_asm_takes_it():
    datadir = rb.read(os.path.join(INPUTS, "turquoise.raw"))
    assert _quiet(rb.measurements, datadir) == []
    got = datadir.measurements(ions=[100.0])
    assert [(m["file"], m["mz"], m["detector"]) for m in got] == \
        [("_func001.dat", 100.0, "MS")]
    scan = datadir.get_file("_func001.dat")
    column = int(np.argmin(np.abs(np.asarray(scan.ylabels, float) - 100.0)))
    assert np.array_equal(got[0]["values"], scan.data[:, column])
    assert np.array_equal(got[0]["times"], scan.xlabels)


def test_to_asm_is_unchanged_by_a_measurements_read():
    """The two share their builders; a read leaves the document as it was."""
    datadir = rb.read(os.path.join(INPUTS, "red.D"), peaks=True)
    before = json.dumps(_quiet(datadir.to_asm, export_dad_cube=False))
    datadir.measurements()
    assert json.dumps(_quiet(datadir.to_asm, export_dad_cube=False)) == before
