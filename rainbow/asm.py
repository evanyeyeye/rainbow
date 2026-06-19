"""
Export parsed data to the Allotrope Simple Model (ASM).

ASM is an open, JSON-based community standard for analytical data, published by
the Allotrope Foundation. Where *rainbow* frees data from a vendor's binary
format, ASM frees it from *rainbow*: a document any ASM-aware tool can read.

This module builds an ASM liquid-chromatography document from a parsed
DataDirectory. The mapping is direct, because rainbow's data model already is
an ASM data cube:

    single-wavelength UV channel  ->  chromatogram data cube
        DataFile.xlabels  ->  dimension "retention time" (minutes -> s)
        DataFile.data     ->  measure   "absorbance"

    multi-wavelength DAD spectrum ->  three-dimensional UV spectrum data cube
        DataFile.xlabels  ->  dimension "retention time" (minutes -> s)
        DataFile.ylabels  ->  dimension "wavelength" (nm)
        DataFile.data     ->  measure   "absorbance" (the flattened grid)

    directory/file metadata  ->  the surrounding measurement envelope

This covers UV detectors from a ``.dx`` archive. Strict JSON-Schema validation
against the published schema is a separate step, so the controlled-vocabulary
terms and the manifest below, while drawn from the schema, are not yet pinned.

Target schema:
http://purl.allotrope.org/json-schemas/adm/liquid-chromatography/

"""
import json

# Identifies the ASM document's schema and ontologies. The exact manifest must
# match the schema version this output is validated against; see module note.
_MANIFEST = ("http://purl.allotrope.org/manifests/"
             "liquid-chromatography/REC/2023/09")

# The controlled-vocabulary terms below are verified to be real classes in the
# Allotrope Foundation Ontology (AFO); see tests/test_asm_ontology.py:
#   concepts:     retention time AFR_0001089, wavelength AFR_0001159,
#                 absorbance AFR_0001157
#   device types: liquid chromatograph AFE_0000808,
#                 ultraviolet detector AFE_0000711

_SECONDS_PER_MINUTE = 60.0

# The two data-cube kinds rainbow reads and writes.
_CHROMATOGRAM_CUBE = "chromatogram data cube"
_SPECTRUM_CUBE = "three-dimensional ultraviolet spectrum data cube"


def to_asm(datadir, spectra=True):
    """
    Builds an ASM liquid-chromatography document from a DataDirectory.

    Each single-wavelength UV channel becomes a measurement carrying a
    chromatogram data cube. Each multi-wavelength DAD spectrum becomes a
    three-dimensional UV spectrum data cube unless ``spectra`` is False.
    Returns a plain ``dict`` ready for ``json.dump``.

    Args:
        datadir (DataDirectory): A parsed directory (e.g. from ``rb.read``).
        spectra (bool, optional): Include multi-wavelength DAD spectra as 3D
            UV spectrum cubes. On by default.

    Returns:
        dict: The ASM document.

    """
    metadata = datadir.metadata
    measurements = []
    for datafile in datadir.datafiles:
        if datafile.detector != 'UV':
            continue
        if datafile.data.shape[1] == 1:
            measurements.append(_chromatogram_measurement(datafile, metadata))
        elif spectra:
            measurements.append(_spectrum_measurement(datafile, metadata))
    return {
        "$asm.manifest": _MANIFEST,
        "liquid chromatography aggregate document": {
            "device system document": _device_system(metadata),
            "liquid chromatography document": [
                {
                    "analyst": metadata.get("operator", "unknown"),
                    "measurement aggregate document": {
                        "measurement document": measurements,
                    },
                },
            ],
        },
    }


def to_asm_str(datadir, spectra=True, indent=2):
    """Returns the ASM document as a JSON string."""
    return json.dumps(
        to_asm(datadir, spectra), indent=indent, ensure_ascii=False)


def _device_system(metadata):
    """The instrument-level device system document."""
    return {
        "asset management identifier": metadata.get("instrument", "unknown"),
        "device document": [
            {"device type": "liquid chromatograph"},
        ],
    }


def _measurement(datafile, metadata, control, cube_key, cube):
    """Wraps a data cube in the shared measurement envelope."""
    measurement = {
        "measurement identifier": datafile.name,
        "sample document": {
            "sample identifier": metadata.get("sample", "unknown"),
        },
        "device control aggregate document": {
            "device control document": [control],
        },
        "chromatography column document": {},
        cube_key: cube,
    }
    if "date" in metadata:
        measurement["measurement time"] = metadata["date"]
    return measurement


def _chromatogram_measurement(datafile, metadata):
    """A measurement for a single-wavelength UV channel."""
    control = {"device type": "ultraviolet detector"}
    wavelength = datafile.metadata.get("wavelength")
    if wavelength is not None:
        control["detector wavelength setting"] = _quantity(wavelength, "nm")
    return _measurement(
        datafile, metadata, control,
        _CHROMATOGRAM_CUBE, _chromatogram_cube(datafile))


def _spectrum_measurement(datafile, metadata):
    """A measurement for a multi-wavelength DAD spectrum."""
    control = {"device type": "ultraviolet detector"}
    return _measurement(
        datafile, metadata, control,
        _SPECTRUM_CUBE, _spectrum_cube(datafile))


def _chromatogram_cube(datafile):
    """Lays a single-wavelength trace into a 1D (retention time) data cube."""
    unit = datafile.metadata.get("unit", "mAU")
    return {
        "label": datafile.name,
        "cube-structure": {
            "dimensions": [_component("retention time", "s")],
            "measures": [_component("absorbance", unit)],
        },
        "data": {
            "dimensions": [_retention_seconds(datafile)],
            "measures": [datafile.data[:, 0].tolist()],
        },
    }


def _spectrum_cube(datafile):
    """
    Lays a DAD spectrum into a 2D (retention time x wavelength) data cube.

    ASM measure arrays are flat, so the (retention time, wavelength) grid is
    flattened with wavelength varying fastest, which is numpy's C order.

    """
    unit = datafile.metadata.get("unit", "mAU")
    return {
        "label": datafile.name,
        "cube-structure": {
            "dimensions": [
                _component("retention time", "s"),
                _component("wavelength", "nm"),
            ],
            "measures": [_component("absorbance", unit)],
        },
        "data": {
            "dimensions": [
                _retention_seconds(datafile),
                datafile.ylabels.astype(float).tolist(),
            ],
            "measures": [datafile.data.flatten().tolist()],
        },
    }


def _retention_seconds(datafile):
    """Retention times in seconds (rainbow stores minutes)."""
    return (datafile.xlabels * _SECONDS_PER_MINUTE).tolist()


def _component(concept, unit):
    """A cube-structure dimension/measure descriptor."""
    return {"concept": concept, "unit": unit, "@componentDatatype": "double"}


def _quantity(value, unit):
    """An ASM quantity value."""
    return {"value": float(value), "unit": unit}


def from_asm(document, name="asm"):
    """
    Reconstructs a DataDirectory from an ASM liquid-chromatography document.

    The inverse of :func:`to_asm`: each measurement's data cube becomes a
    DataFile (retention time back from seconds to minutes, the measure back to
    the data array) and the shared envelope becomes directory metadata. Only
    the UV cubes that :func:`to_asm` writes are reconstructed; a measurement
    carrying another cube kind (e.g. a mass chromatogram) is skipped, so
    reading a document rainbow did not write is safe.

    Args:
        document (dict): An ASM document (e.g. from ``json.load``).
        name (str, optional): Name for the reconstructed DataDirectory.

    Returns:
        DataDirectory.

    """
    from rainbow.datadirectory import DataDirectory

    aggregate = document["liquid chromatography aggregate document"]
    metadata = {}
    datafiles = []
    for lc_document in aggregate["liquid chromatography document"]:
        analyst = lc_document.get("analyst")
        if analyst and analyst != "unknown":
            metadata.setdefault("operator", analyst)
        measurements = (lc_document["measurement aggregate document"]
                        ["measurement document"])
        for measurement in measurements:
            # Lift the shared envelope fields up to the directory level.
            sample = measurement.get(
                "sample document", {}).get("sample identifier")
            if sample and sample != "unknown":
                metadata.setdefault("sample", sample)
            if measurement.get("measurement time"):
                metadata.setdefault("date", measurement["measurement time"])
            datafile = _datafile_from_measurement(measurement)
            if datafile is not None:
                datafiles.append(datafile)

    return DataDirectory(name, datafiles, metadata)


def _datafile_from_measurement(measurement):
    """
    Reconstructs one DataFile from an ASM measurement document.

    Returns None if the measurement carries no cube kind that rainbow knows
    how to reconstruct (currently the UV chromatogram and spectrum cubes).

    """
    import numpy as np
    from rainbow.datafile import DataFile

    if _SPECTRUM_CUBE not in measurement and _CHROMATOGRAM_CUBE not in measurement:
        return None

    name = measurement.get("measurement identifier", "trace")
    file_metadata = {}

    control = (measurement.get("device control aggregate document", {})
               .get("device control document", [{}])[0])
    setting = control.get("detector wavelength setting")
    wavelength = setting["value"] if setting else None

    if _SPECTRUM_CUBE in measurement:
        cube = measurement[_SPECTRUM_CUBE]["data"]
        times, wavelengths = cube["dimensions"][0], cube["dimensions"][1]
        xlabels = np.array(times, dtype=float) / _SECONDS_PER_MINUTE
        ylabels = np.array(wavelengths, dtype=float)
        # Un-flatten the grid (wavelength varied fastest, i.e. C order).
        data = np.array(cube["measures"][0], dtype=float).reshape(
            len(times), len(wavelengths))
    else:
        cube = measurement[_CHROMATOGRAM_CUBE]["data"]
        xlabels = np.array(cube["dimensions"][0], dtype=float) \
            / _SECONDS_PER_MINUTE
        data = np.array(cube["measures"][0], dtype=float).reshape(-1, 1)
        if wavelength is not None:
            ylabels = np.array([wavelength])
            file_metadata["wavelength"] = wavelength
        else:
            ylabels = np.array([''])

    return DataFile(name, 'UV', xlabels, ylabels, data, file_metadata)
