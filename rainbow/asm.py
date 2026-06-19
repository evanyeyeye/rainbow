"""
Export parsed data to the Allotrope Simple Model (ASM).

ASM is an open, JSON-based community standard for analytical data, published by
the Allotrope Foundation. Where *rainbow* frees data from a vendor's binary
format, ASM frees it from *rainbow*: a document any ASM-aware tool can read.

This module builds an ASM liquid-chromatography document from a parsed
DataDirectory. The mapping is direct, because rainbow's data model already is
an ASM data cube:

    DataFile.xlabels  ->  cube dimension "retention time" (converted to s)
    DataFile.data     ->  cube measure   "absorbance"
    directory/file metadata  ->  the surrounding measurement envelope

This is a first, deliberately small cut. It emits a ``chromatogram data cube``
for each single-wavelength UV channel; the multi-wavelength DAD spectrum (a
3D UV spectrum cube) and strict JSON-Schema validation are not done here yet.
The controlled-vocabulary terms and manifest below are reasonable but are not
yet pinned against the published schema.

Target schema:
http://purl.allotrope.org/json-schemas/adm/liquid-chromatography/

"""
import json

# Identifies the ASM document's schema and ontologies. The exact manifest must
# match the schema version this output is validated against; see module note.
_MANIFEST = ("http://purl.allotrope.org/manifests/"
             "liquid-chromatography/REC/2023/09")

_SECONDS_PER_MINUTE = 60.0


def to_asm(datadir):
    """
    Builds an ASM liquid-chromatography document from a DataDirectory.

    Each single-wavelength UV channel becomes one measurement carrying a
    chromatogram data cube. Returns a plain ``dict`` ready for ``json.dump``.

    Args:
        datadir (DataDirectory): A parsed directory (e.g. from ``rb.read``).

    Returns:
        dict: The ASM document.

    """
    metadata = datadir.metadata
    measurements = [
        _chromatogram_measurement(datafile, metadata)
        for datafile in datadir.datafiles
        if datafile.detector == 'UV' and datafile.data.shape[1] == 1
    ]
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


def to_asm_str(datadir, indent=2):
    """Returns the ASM document as a JSON string."""
    return json.dumps(to_asm(datadir), indent=indent, ensure_ascii=False)


def _device_system(metadata):
    """The instrument-level device system document."""
    return {
        "asset management identifier": metadata.get("instrument", "unknown"),
        "device document": [
            {"device type": "liquid chromatography device"},
        ],
    }


def _chromatogram_measurement(datafile, metadata):
    """Builds one measurement document for a single-wavelength channel."""
    control = {"device type": "ultraviolet absorbance detector"}
    wavelength = datafile.metadata.get("wavelength")
    if wavelength is not None:
        control["detector wavelength setting"] = _quantity(wavelength, "nm")

    measurement = {
        "measurement identifier": datafile.name,
        "sample document": {
            "sample identifier": metadata.get("sample", "unknown"),
        },
        "device control aggregate document": {
            "device control document": [control],
        },
        "chromatography column document": {},
        "chromatogram data cube": _chromatogram_cube(datafile),
    }
    if "date" in metadata:
        measurement["measurement time"] = metadata["date"]
    return measurement


def _chromatogram_cube(datafile):
    """Lays a single-wavelength trace into an ASM data cube."""
    times_s = [float(t) * _SECONDS_PER_MINUTE for t in datafile.xlabels]
    absorbance = [float(v) for v in datafile.data[:, 0]]
    unit = datafile.metadata.get("unit", "mAU")
    return {
        "label": datafile.name,
        "cube-structure": {
            "dimensions": [
                _component("retention time", "s"),
            ],
            "measures": [
                _component("absorbance", unit),
            ],
        },
        "data": {
            "dimensions": [times_s],
            "measures": [absorbance],
        },
    }


def _component(concept, unit):
    """A cube-structure dimension/measure descriptor."""
    return {"concept": concept, "unit": unit, "@componentDatatype": "double"}


def _quantity(value, unit):
    """An ASM quantity value."""
    return {"value": float(value), "unit": unit}
