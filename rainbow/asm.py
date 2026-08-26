"""
Export parsed data to the Allotrope Simple Model (ASM).

ASM is an open, JSON-based community standard for analytical data, published by
the Allotrope Foundation. Where *rainbow* frees data from a vendor's binary
format, ASM frees it from *rainbow*: a document any ASM-aware tool can read.

This module builds an ASM liquid- or gas-chromatography document from a parsed
DataDirectory (one injection) or DataSequence (a whole run). The technique is
read from the acquisition method (the sample inlet rainbow records as
``metadata['technique']``); absent that, a run with an FID channel is taken as
gas chromatography, and the caller can force either with ``technique=``. rainbow
targets Allotrope revision REC/2026/03, whose gas-chromatography ADM admits the
FID, MS, and UV cubes together, so a gas-chromatography run exports losslessly.
rainbow's data model already is an ASM data cube:

    single-wavelength UV channel  ->  chromatogram data cube
        DataFile.xlabels  ->  dimension "retention time" (minutes -> s)
        DataFile.data     ->  measure   "absorbance"

    multi-wavelength DAD spectrum ->  three-dimensional UV spectrum data cube
        DataFile.xlabels  ->  dimension "retention time" (minutes -> s)
        DataFile.ylabels  ->  dimension "wavelength" (nm)
        DataFile.data     ->  measure   "absorbance" (the flattened grid)

    directory/file metadata  ->  the surrounding measurement envelope

Where the metadata supports it, the envelope is filled in: the instrument and
its modules become the device system document, the injection volume an
injection document, and (for a sequence read with peaks) the integrated peaks a
processed data aggregate document. A DataSequence becomes one aggregate
document with one chromatography document per injection.

Most detectors are exported faithfully: UV as absorbance, CAD and FID as
electric current, ELSD as light intensity, each a 1-D chromatogram cube with its
real measure concept and a truthful device type. RID alone is an interim, riding
the absorbance cube because the published schema has no refractive-index measure.
SIM MS is exported faithfully and in full: every
monitored ion becomes a mass chromatogram data cube (ion count over retention
time). Full-scan MS is a 2D retention-by-m/z grid that the published schema
has no faithful home for; rather than fabricate one, the caller can name the
``ions`` of interest and each is pulled from the grid as its own mass
chromatogram (the same cube SIM uses). SIM and scan are told apart by the
channel's acquisition mode, read from the acquisition method. FID is faithful
too: it routes the run to a gas-chromatography document, where it becomes an
electric-current (pA) chromatogram, the FID's real quantity. A per-scan HRMS
profile is out of scope (it has no single shared m/z axis).

Strict JSON-Schema validation against the published schema is a separate step,
so the controlled-vocabulary terms and the manifests below, while drawn from the
schema and the Allotrope Foundation Ontology, are not pinned here.

Target schemas:
http://purl.allotrope.org/json-schemas/adm/liquid-chromatography/
http://purl.allotrope.org/json-schemas/adm/gas-chromatography/

"""
import json
import os
import re
import warnings

import numpy as np

# Each ASM document declares the manifest for its technique and schema revision.
# rainbow targets REC/2026/03: unlike 2023/09, its gas-chromatography ADM carries
# cubes for FID, MS, and UV together, so a gas-chromatography run exports
# losslessly. The exact manifest must match the schema this output is validated
# against; see the module note and tests/test_asm_schema.py.
_LC_MANIFEST = (
    "http://purl.allotrope.org/manifests/"
    "liquid-chromatography/REC/2026/03/liquid-chromatography.manifest")
_GC_MANIFEST = (
    "http://purl.allotrope.org/manifests/"
    "gas-chromatography/REC/2026/03/gas-chromatography.tabular.manifest")

# A run is exported as one technique's document. FID is a gas-chromatography
# detector, so any run that has an FID channel becomes a gas chromatography
# document (which on 2026/03 also admits the run's UV and MS cubes); every other
# run stays a liquid chromatography document. The two differ only in the manifest
# and the aggregate/document wrapper keys; the measurement documents are shared.
_LC = {
    "manifest": _LC_MANIFEST,
    "aggregate": "liquid chromatography aggregate document",
    "document": "liquid chromatography document",
}
_GC = {
    "manifest": _GC_MANIFEST,
    "aggregate": "gas chromatography aggregate document",
    "document": "gas chromatography document",
}

# The controlled-vocabulary terms below are verified to be real classes in the
# Allotrope Foundation Ontology (AFO); see tests/test_asm_ontology.py. The JSON
# schema types these fields as free strings, so the ontology is the only thing
# that catches an invented label.
#   concepts:     retention time AFR_0001089, wavelength AFR_0001159,
#                 absorbance AFR_0001157
#   device types: liquid chromatograph AFE_0000808, gas chromatograph
#                 AFE_0000024, pump AFE_0000499, autosampler AFE_0000073,
#                 column compartment AFE_0002198
#   detectors:    detector AFE_0000317 > chromatographic detector AFE_0000246 >
#                 {liquid chromatography detector AFE_0002200 >
#                    ultraviolet detector AFE_0000711,
#                    diode array detector AFE_0000090,
#                    refractive index detector AFE_0000363,
#                    fluorescence detector AFE_0000567;
#                  gas chromatography detector AFE_0002188 >
#                    flame ionization detector AFE_0000209,
#                    thermal conductivity detector AFE_0000316,
#                    electron capture detector AFE_0000534}
#                 evaporative light scattering detector AFE_0002277 hangs
#                 directly off detector, under neither technique.

_SECONDS_PER_MINUTE = 60.0

# How close (in Da) a requested ion must lie to a grid m/z to count as a match
# when extracting ions from a full-scan MS cube. Loose enough to map a unit-mass
# request onto a calibrated-float grid, tight enough not to grab the wrong peak.
_ION_MATCH_TOLERANCE = 0.5

# The data-cube keys, shared by the forward and reverse mappings.
_CHROMATOGRAM_CUBE = "chromatogram data cube"
_SPECTRUM_CUBE = "three-dimensional ultraviolet spectrum data cube"
_MASS_CHROMATOGRAM_CUBE = "mass chromatogram data cube"
_PROCESSED_DATA = "processed data aggregate document"

# Maps an instrument module's type to its AFO device-type class. A module whose
# type is not mapped is emitted without a device type rather than with a guess.
_MODULE_DEVICE_TYPES = {
    "pump": "pump",
    "auto sampler": "autosampler",
    "autosampler": "autosampler",
    "column compartment": "column compartment",
}

# Detector typing follows the AFO equipment hierarchy. Under `detector`
# (AFE_0000317) sits `chromatographic detector` (AFE_0000246), and under that
# `liquid chromatography detector` (AFE_0002200) and `gas chromatography
# detector` (AFE_0002188) are disjoint siblings. So the two matter separately:
#
#   * An exact class is used whenever the module names one AND the document
#     agrees with the side of the split that class sits on. FID/TCD/ECD are gas
#     chromatography detectors and UV/DAD/RID/FLD liquid chromatography ones, so
#     a DAD on a gas chromatograph cannot be called a diode array detector
#     without the document asserting it is part of an LC system. Where they
#     disagree the nearest class making no technique claim is used instead (see
#     _DETECTOR_TECHNIQUES). ELSD and mass spectrometer claim neither technique,
#     so they are unaffected.
#   * A detector that cannot be named falls back to the generic class for the
#     document's own technique, never to a fixed one: calling a detector in a
#     gas chromatography document a liquid chromatography detector asserts a
#     class the document contradicts.
#
# Vendors write a module's name with any separator at hand (DAD1A, FID_2,
# RID-1A, "Analog/Digital Converter"), and an underscore is a word character, so
# the text is normalized to spaced words before matching. Acronyms are matched
# as whole words with an optional module index, so "rid" stays out of "hybrid"
# and "cad" out of "cascade".
#
# Ordered most specific first. Every value is a checked AFO class label; a
# detector with no AFO class of its own (charged aerosol, and whatever is wired
# into an analog input) is deliberately absent and takes the generic fallback.
_NEUTRAL_ABSORBANCE = "electronic absorbance detector"   # AFE_0000734
_DETECTOR_RULES = (
    # rainbow writes this itself for an absorbance channel in a document whose
    # technique contradicts the UV and DAD classes, so it has to read it back
    # as itself rather than re-specializing on the "absorbance" phrase below.
    ("electronic absorbance", (), _NEUTRAL_ABSORBANCE),
    ("diode array|photodiode array", ("dad", "pda"), "diode array detector"),
    # VWD, MWD, and TUV are the vendor names for variable-, multiple-, and
    # tunable-wavelength ultraviolet detectors.
    ("ultraviolet|variable wavelength|multiple wavelength|multi wavelength"
     "|tunable wavelength|absorbance",
     ("uv", "vwd", "mwd", "tuv"), "ultraviolet detector"),
    ("flame ionization", ("fid",), "flame ionization detector"),
    ("thermal conductivity", ("tcd",), "thermal conductivity detector"),
    # Agilent's micro-ECD is written with a micro sign, which normalizes away
    # to leave "ecd", but also plainly as "uECD", where it does not.
    ("electron capture", ("ecd", "uecd"), "electron capture detector"),
    # FLR is the Waters spelling, FLD the Agilent one.
    ("fluorescence", ("fld", "flr"), "fluorescence detector"),
    ("refractive index", ("rid", "ri"), "refractive index detector"),
    # A word boundary does not span "els" into "elsd", so both are listed.
    ("evaporative light scattering", ("elsd", "els"),
     "evaporative light scattering detector"),
    ("mass spectrometer|mass selective", ("msd", "qqq", "qtof"),
     "mass spectrometer"),
)

# Detectors AFO has no class for. They are recognized so that they are typed by
# the document's technique rather than by whatever else their name happens to
# contain: an analog input channel is how a vendor exposes a detector it does
# not model (red.D's charged-aerosol detector arrives as one), and what is wired
# into it is not knowable from the name.
_GENERIC_DETECTOR_RULE = (
    "charged aerosol|analog digital converter|analog to digital converter",
    ("cad", "adc"))


def _acronyms(words):
    """A pattern matching any of ``words`` as a whole word plus module index.

    A vendor's index may carry a trailing letter or several (DAD1A, VWD-3400RS,
    DAD3000RS), so the whole index is consumed rather than one letter of it.
    """
    return "|".join(r"\b{}(\d+[a-z]*)?\b".format(word) for word in words)


def _detector_pattern(phrases, words):
    # An empty acronym list must not contribute an empty alternative, which
    # would match anywhere at all.
    return re.compile("|".join(filter(None, (phrases, _acronyms(words)))))


_DETECTOR_PATTERNS = tuple(
    (_detector_pattern(phrases, words), device_type)
    for phrases, words, device_type in _DETECTOR_RULES)
_GENERIC_DETECTOR_PATTERN = _detector_pattern(*_GENERIC_DETECTOR_RULE)

# Each single-signal detector becomes a 1-D chromatogram cube. The table gives
# the AFO device type and the cube's measure concept and unit:
#   UV    faithful absorbance (the source unit normalized to mAU).
#   FID   faithful electric current; its presence also routes the run to a gas
#         chromatography document (see :func:`_technique`).
#   CAD   faithful electric current: a charged-aerosol detector measures a
#         current. AFO has no charged-aerosol class, so it takes the generic
#         detector class for the document's technique ("generic": True below).
#   ELSD  faithful light intensity.
#   RID   interim: a refractive-index detector has no measure concept in the
#         published schema, so it alone still rides the absorbance cube. Its
#         device type stays truthful.
# A named class is kept only where the document's technique agrees with it. AFO
# puts UV and DAD under `liquid chromatography detector` and FID under `gas
# chromatography detector`, and those are disjoint, so a UV channel riding along
# in a gas chromatography document is typed by the nearest class that claims
# neither technique rather than one the document contradicts.
# Values are the vendor's own, unscaled, except UV absorbance (normalized
# AU->mAU). MS is handled separately (mass chromatograms). See the ASM detectors
# documentation.
_DETECTOR_CUBES = {
    "UV": {"device_type": "ultraviolet detector",
           "concept": "absorbance", "unit": "mAU"},
    "RID": {"device_type": "refractive index detector",
            "concept": "absorbance", "unit": "mAU"},
    "CAD": {"generic": True, "concept": "electric current", "unit": "pA"},
    "ELSD": {"device_type": "evaporative light scattering detector",
             "concept": "intensity", "unit": "RLU"},
    "FID": {"device_type": "flame ionization detector",
            "concept": "electric current", "unit": "pA",
            "detection_type": "flame ionization"},
}


def to_asm(datadir, export_dad_cube=True, wavelengths=None, ions=None,
           decimal_places=None, technique=None, timezone=None):
    """
    Builds an ASM liquid- or gas-chromatography document from a DataDirectory.

    Each single-wavelength UV channel becomes a measurement carrying a
    chromatogram data cube. Each multi-wavelength DAD spectrum becomes a
    three-dimensional UV spectrum data cube unless ``export_dad_cube`` is False.
    Returns a plain ``dict`` ready for ``json.dump``.

    Args:
        datadir (DataDirectory): A parsed directory (e.g. from ``rb.read``).
        export_dad_cube (bool, optional): Include multi-wavelength DAD spectra
            as 3D UV spectrum cubes. On by default. The DAD cube is by far the
            largest part of a document, so turning it off (single-wavelength
            channels still export) shrinks the output dramatically.
        wavelengths (float/list, optional): Restrict the DAD spectrum cube to
            these wavelengths (nearest available, in nm); the default keeps
            every wavelength. A request with no wavelength within 1 nm is
            dropped with a warning.
        ions (float/list, optional): m/z value(s) to extract from full-scan MS
            data, each exported as its own mass chromatogram. Single-ion (SIM)
            MS is always exported regardless of this argument.
        decimal_places (int, optional): Round emitted numeric values (signals,
            retention times, peak metrics) to this many decimal places. The
            default keeps full precision. Fewer places yield a smaller document.
        technique (str, optional): Force the export technique, ``"GC"`` or
            ``"LC"``, overriding what the method declares and the FID-presence
            fallback. By default the technique is read from the acquisition
            method (see :func:`_technique`).
        timezone (str, optional): UTC offset such as
            ``"-05:00"`` or ``"Z"``, stamped on timestamps the
            instrument recorded without one. An offset the source
            did record is never overridden.

    Returns:
        dict: The ASM document.

    """
    options = _Options(export_dad_cube, wavelengths, ions, decimal_places,
                       timezone)
    metadata = datadir.metadata
    technique = _technique(datadir.datafiles, metadata, technique)
    return _aggregate_document(
        technique,
        _device_system(metadata, technique),
        [_injection_document(datadir, metadata, options, technique)])


def sequence_to_asm(datasequence, export_dad_cube=True, wavelengths=None,
                    ions=None, decimal_places=None, technique=None,
                    timezone=None):
    """
    Builds one ASM document from a DataSequence.

    The aggregate document carries a single device system document (the
    instrument shared by the run) and one liquid chromatography document per
    injection, in acquisition order. Peaks read with the sequence become each
    injection's processed data.

    Args:
        datasequence (DataSequence): A parsed sequence (from
            ``rb.read_sequence``).
        export_dad_cube (bool, optional): Include multi-wavelength DAD spectra
            as 3D UV spectrum cubes. On by default. The dominant size driver of
            a sequence document, so turning it off shrinks the output sharply.
        wavelengths (float/list, optional): Restrict the DAD spectrum cube to
            these wavelengths (nearest available, in nm); the default keeps
            every wavelength.
        ions (float/list, optional): m/z value(s) to extract from full-scan MS
            data, each exported as its own mass chromatogram. Single-ion (SIM)
            MS is always exported regardless of this argument.
        decimal_places (int, optional): Round emitted numeric values
            to this many decimal places. The default keeps full
            precision.
        technique (str, optional): Force the export technique, ``"GC"`` or
            ``"LC"``, overriding the method's declaration and the FID-presence
            fallback.
        timezone (str, optional): UTC offset such as
            ``"-05:00"`` or ``"Z"``, stamped on timestamps the
            instrument recorded without one. An offset the source
            did record is never overridden.

    Returns:
        dict: The ASM document.

    """
    options = _Options(export_dad_cube, wavelengths, ions, decimal_places,
                       timezone)
    metadata = _sequence_metadata(datasequence)
    technique = _technique(
        _sequence_datafiles(datasequence), metadata, technique)
    return _aggregate_document(
        technique,
        _device_system(metadata, technique),
        [_injection_document(injection, injection.metadata, options, technique)
         for injection in datasequence.injections])


def _sequence_metadata(datasequence):
    """The run-level metadata used for a sequence's device system + technique.

    Falls back to a per-injection value when the sequence has none of its own
    (no top-level sequence.acaml): an injection's modules name the hardware, and
    an injection's recorded technique routes the whole sequence.
    """
    metadata = dict(datasequence.metadata)
    if "instrument" not in metadata and "modules" not in metadata:
        for injection in datasequence.injections:
            if injection.metadata.get("modules"):
                metadata["modules"] = injection.metadata["modules"]
                break
    if "technique" not in metadata:
        for injection in datasequence.injections:
            if injection.metadata.get("technique"):
                metadata["technique"] = injection.metadata["technique"]
                break
    return metadata


def _sequence_datafiles(datasequence):
    """Every datafile across the sequence, for technique detection."""
    return [datafile for injection in datasequence.injections
            for datafile in injection.datafiles]


def _aggregate_document(technique, device_system, documents):
    """Wraps per-injection documents in the technique's aggregate document."""
    return {
        "$asm.manifest": technique["manifest"],
        technique["aggregate"]: {
            "device system document": device_system,
            technique["document"]: documents,
        },
    }


def _technique(datafiles, metadata, override=None):
    """The ASM technique (``_LC`` or ``_GC``) a run is exported as.

    Resolved in order of authority: an explicit ``override`` ("GC"/"LC") wins;
    then the technique the method recorded (``metadata['technique']``, read from
    the acquisition method's sample inlet); then, only when neither is present, a
    fallback to detector evidence, where an FID channel (a gas-chromatography
    detector) marks a gas-chromatography run. On 2026/03 the gas-chromatography
    document also admits the run's UV and MS cubes, so a mixed GC-MS or
    UV-plus-FID run stays lossless.
    """
    declared = override or metadata.get("technique")
    if declared:
        normalized = str(declared).upper()
        if normalized == "GC":
            return _GC
        if normalized == "LC":
            return _LC
        raise ValueError(
            "technique must be 'GC' or 'LC', not {!r}".format(declared))
    if any(datafile.detector == 'FID' for datafile in datafiles):
        return _GC
    return _LC


def to_asm_str(datadir, export_dad_cube=True, wavelengths=None, ions=None,
               decimal_places=None, technique=None, timezone=None, indent=2):
    """Returns the DataDirectory ASM document as a JSON string."""
    return json.dumps(
        to_asm(datadir, export_dad_cube, wavelengths, ions, decimal_places,
               technique, timezone),
        indent=indent, ensure_ascii=False)


def sequence_to_asm_str(datasequence, export_dad_cube=True, wavelengths=None,
                        ions=None, decimal_places=None, technique=None,
                        timezone=None, indent=2):
    """Returns the DataSequence ASM document as a JSON string."""
    return json.dumps(
        sequence_to_asm(datasequence, export_dad_cube, wavelengths, ions,
                        decimal_places, technique, timezone),
        indent=indent, ensure_ascii=False)


# A placeholder for the per-injection document array, swapped out for a streamed
# array so the whole sequence never lives in memory at once. Chosen to never
# collide with real envelope metadata (device system / manifest strings).
_DOCUMENTS_PLACEHOLDER = "@@RAINBOW_INJECTION_DOCUMENTS@@"


def export_asm(datadir, fileobj, export_dad_cube=True, wavelengths=None,
               ions=None, decimal_places=None, technique=None,
               timezone=None, indent=2):
    """Streams a DataDirectory ASM document to an open text file.

    Equivalent to writing :func:`to_asm_str`, but the (potentially large) data
    cubes are serialized one injection document at a time so the whole JSON
    string is never held in memory. See :func:`to_asm` for the arguments.
    """
    options = _Options(export_dad_cube, wavelengths, ions, decimal_places,
                       timezone)
    metadata = datadir.metadata
    technique = _technique(datadir.datafiles, metadata, technique)
    _stream_aggregate(fileobj, technique, _device_system(metadata, technique),
                       [(datadir, metadata)], options, indent)


def sequence_export_asm(datasequence, fileobj, export_dad_cube=True,
                        wavelengths=None, ions=None, decimal_places=None,
                        technique=None, timezone=None, indent=2):
    """Streams a DataSequence ASM document to an open text file.

    Like :func:`sequence_to_asm_str`, but each injection document is built and
    written in turn, so a long sequence of large spectra never materializes the
    whole multi-gigabyte document at once. See :func:`sequence_to_asm` for the
    arguments.
    """
    options = _Options(export_dad_cube, wavelengths, ions, decimal_places,
                       timezone)
    metadata = _sequence_metadata(datasequence)
    technique = _technique(
        _sequence_datafiles(datasequence), metadata, technique)
    specs = [(injection, injection.metadata)
             for injection in datasequence.injections]
    _stream_aggregate(fileobj, technique, _device_system(metadata, technique),
                       specs, options, indent)


def sequence_export_asm_per_injection(datasequence, directory,
                                      export_dad_cube=True, wavelengths=None,
                                      ions=None, decimal_places=None,
                                      technique=None, timezone=None,
                                      indent=2):
    """Streams one standalone ASM document per injection into ``directory``.

    Instead of bundling a long run into a single multi-gigabyte file, each
    injection becomes its own complete document: its own manifest, the run's
    shared device system, and that one injection's chromatography document,
    written to ``<directory>/<injection name>.asm.json``. The directory is
    created if needed. Returns the list of paths written, in injection order.
    """
    options = _Options(export_dad_cube, wavelengths, ions, decimal_places,
                       timezone)
    metadata = _sequence_metadata(datasequence)
    technique = _technique(
        _sequence_datafiles(datasequence), metadata, technique)
    device_system = _device_system(metadata, technique)
    os.makedirs(directory, exist_ok=True)
    paths = []
    taken = set()
    for injection in datasequence.injections:
        # Injection names are not unique (re-injected blanks/standards often
        # share one), so suffix collisions rather than silently overwrite.
        filename = _unique_filename(_injection_filename(injection.name), taken)
        taken.add(filename)
        path = os.path.join(directory, filename)
        with open(path, "w", encoding="utf-8") as fileobj:
            _stream_aggregate(fileobj, technique, device_system,
                              [(injection, injection.metadata)], options,
                              indent)
        paths.append(path)
    return paths


def _injection_filename(name):
    """A per-injection ASM filename from an injection (directory) name."""
    base = name.replace(os.sep, "_")
    if os.altsep:
        base = base.replace(os.altsep, "_")
    for extension in (".D", ".d", ".raw"):
        if base.endswith(extension):
            base = base[:-len(extension)]
            break
    # Collapse anything not filename-safe (e.g. ':' '*' on other platforms) to
    # an underscore, and never yield an empty or hidden name.
    base = "".join(c if (c.isalnum() or c in "._-") else "_" for c in base)
    base = base.strip(". ") or "injection"
    return base + ".asm.json"


def _unique_filename(filename, taken):
    """``filename`` if free, else suffixed ``_2``, ``_3``, ... to avoid clobber."""
    if filename not in taken:
        return filename
    stem = filename[:-len(".asm.json")]
    index = 2
    while "{}_{}.asm.json".format(stem, index) in taken:
        index += 1
    return "{}_{}.asm.json".format(stem, index)


def _stream_aggregate(fileobj, technique, device_system, specs, options,
                      indent):
    """Writes the aggregate document, materializing one injection at a time.

    The envelope (manifest + device system) is rendered once with a placeholder
    where the injection-document array goes; the placeholder is then replaced by
    a streamed JSON array whose elements are each built, written, and released
    before the next. Peak memory is one injection document, not the whole run.
    """
    envelope = _aggregate_document(technique, device_system,
                                   _DOCUMENTS_PLACEHOLDER)
    rendered = json.dumps(envelope, indent=indent, ensure_ascii=False)
    # The placeholder is the injection-array slot, emitted after the device
    # system, so it is the LAST occurrence of the sentinel; splitting there
    # (rpartition) keeps a device-system field that happens to contain the
    # sentinel text from corrupting the split.
    head, _, tail = rendered.rpartition(json.dumps(_DOCUMENTS_PLACEHOLDER))
    # Indent each streamed injection document to sit where the placeholder did,
    # so the pretty-printed array nests correctly under the aggregate document.
    pretty = bool(indent)
    key_line = head.rsplit("\n", 1)[-1]
    base = len(key_line) - len(key_line.lstrip(" ")) if pretty else 0
    pad = " " * (base + indent) if pretty else ""
    fileobj.write(head)
    fileobj.write("[")
    for index, (datadir, metadata) in enumerate(specs):
        document = _injection_document(datadir, metadata, options, technique)
        chunk = json.dumps(document, indent=indent, ensure_ascii=False)
        if pretty:
            chunk = "\n".join(pad + line for line in chunk.split("\n"))
            fileobj.write(("," if index else "") + "\n" + chunk)
        else:
            fileobj.write(("," if index else "") + chunk)
        del document, chunk
    if specs and pretty:
        fileobj.write("\n" + " " * base)
    fileobj.write("]")
    fileobj.write(tail)


# The largest tolerance, in nanometres, between a requested export wavelength
# and an available DAD column for them to be considered the same wavelength.
_WAVELENGTH_TOLERANCE = 1.0


# The wall-clock spellings the vendor parsers hand back. Only the ChemStation
# MS-file form carries a UTC offset, and not always; the rest record local time
# with no zone at all, which is the whole reason `timezone=` exists.
#
#   27-Feb-18, 10:11:50         ChemStation .ch/.uv header
#   06-Aug-2021 10:52:20        Waters _HEADER.TXT
#   3 Feb 22  11:22 am -0500    ChemStation .ms (the one with an offset)
#   17 Dec 19  10:04 am         ChemStation .ms, offset absent
#
# An Agilent OpenLab .dx already stores ISO 8601 and is handled separately.
_MONTHS = {name: number for number, name in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"), 1)}

# One pattern covers all four spellings above. strptime would be the obvious
# tool, but its %b and %p read the process locale: under a non-English LC_TIME
# every vendor timestamp fails to parse, and rainbow is a library that does not
# control the locale of the application embedding it. Matching the month name
# here keeps the parse independent of that.
_VENDOR_TIMESTAMP = re.compile(r"""
    ^(?P<day>[0-9]{1,2})[-\s]+(?P<month>[A-Za-z]{3,9})[-\s]+(?P<year>[0-9]{2,4})
    [\s,]+(?P<hour>[0-9]{1,2}):(?P<minute>[0-9]{2})(?::(?P<second>[0-9]{2}))?
    (?:\s*(?P<meridiem>[AaPp])\.?[Mm]\.?)?
    (?:\s*(?P<offset>[+-][0-9]{2}:?[0-9]{2}))?$
""", re.VERBOSE)

# A .NET timestamp carries 7 fractional digits, and older Pythons accept exactly
# 3 or 6 (and no trailing Z), so an ISO string is normalized before it is parsed.
_ISO_FRACTION = re.compile(r"\.([0-9]+)")
_UTC_OFFSET = re.compile(r"[+-][0-9]{2}:?[0-9]{2}\Z")


def _utc_offset(timezone):
    """Validates a ``timezone`` export option, returning a UTC offset string."""
    if timezone is None:
        return None
    if not isinstance(timezone, str):
        raise Exception(
            "timezone must be a UTC offset string such as '+00:00' or 'Z', "
            "not {!r}.".format(timezone))
    # An offset arriving from a config file or a shell capture keeps its
    # trailing newline, and the offset is concatenated onto every timestamp in
    # the document, so a stray one would corrupt all of them at once.
    timezone = timezone.strip()
    if timezone in ("Z", "z"):
        return "+00:00"
    invalid = Exception(
        "timezone must be a UTC offset such as '+00:00', '-05:00', or 'Z', "
        "not {!r}.".format(timezone))
    if not _UTC_OFFSET.fullmatch(timezone):
        raise invalid
    normalized = timezone if ":" in timezone else timezone[:3] + ":" + timezone[3:]
    # The shape alone is not enough: the offset is written into the document
    # verbatim, so an out-of-range one produces a timestamp no RFC 3339 reader
    # will accept, and validation is opt-in so nothing would catch it.
    hours, minutes = int(normalized[1:3]), int(normalized[4:6])
    if hours > 14 or minutes > 59 or (hours == 14 and minutes):
        raise invalid
    return normalized


def _parse_vendor(value):
    """Parses a vendor wall-clock spelling, independent of the locale."""
    from datetime import datetime, timedelta, timezone as _timezone

    match = _VENDOR_TIMESTAMP.match(value)
    if match is None:
        return None
    month = _MONTHS.get(match.group("month")[:3].lower())
    if month is None:
        return None
    year = int(match.group("year"))
    if len(match.group("year")) <= 2:
        # The same pivot strptime's %y uses, so no vendor's two-digit year
        # changes meaning: 69-99 is last century, 00-68 is this one.
        year += 1900 if year >= 69 else 2000
    hour = int(match.group("hour"))
    meridiem = match.group("meridiem")
    if meridiem:
        if hour > 12:
            return None
        hour = hour % 12 + (12 if meridiem.lower() == "p" else 0)
    offset = match.group("offset")
    tzinfo = None
    if offset:
        sign = -1 if offset[0] == "-" else 1
        digits = offset[1:].replace(":", "")
        tzinfo = _timezone(sign * timedelta(
            hours=int(digits[:2]), minutes=int(digits[2:])))
    try:
        return datetime(year, month, int(match.group("day")), hour,
                        int(match.group("minute")),
                        int(match.group("second") or 0), tzinfo=tzinfo)
    except ValueError:
        return None                        # a day or time the calendar rejects


def _parse_iso(value):
    """Parses an ISO 8601 timestamp, tolerating 'Z' and .NET's 7 digits."""
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    match = _ISO_FRACTION.search(text)
    if match and len(match.group(1)) != 6:
        # Pythons before 3.11 accept exactly 3 or 6 fractional digits. .NET
        # writes 7 and trims trailing zeros, so both padding and truncating are
        # needed for the same .dx to read on every interpreter rainbow supports.
        text = (text[:match.start()] + "." + match.group(1)[:6].ljust(6, "0")
                + text[match.end():])
    try:
        from datetime import datetime
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _iso_timestamp(value, timezone=None):
    """
    A vendor timestamp as ISO 8601, or None if it cannot be read.

    ASM types every timestamp as ISO 8601, but the vendors write wall clock in
    their own formats, and most of them record no UTC offset at all. Where the
    source has one it is kept. Where it does not, the timestamp is emitted
    without one rather than with an invented one: a fabricated offset would
    move the recorded instant by up to a day, and rainbow does not know where
    the instrument was. A caller who does know can supply ``timezone``.

    """
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = _parse_vendor(value.strip()) or _parse_iso(value)
    if parsed is None:
        return None                            # a shape rainbow cannot read
    if parsed.tzinfo is None and timezone is not None:
        return parsed.isoformat() + timezone
    return parsed.isoformat()


class _Options:
    """The caller's export controls, threaded through the document builders.

    Attributes:
        export_dad_cube (bool): include the multi-wavelength DAD spectrum cube.
        wavelengths (list or None): when set, the DAD spectrum cube is
            restricted to these wavelengths (nearest available, in nm).
        ions (float/list or None): m/z trace(s) to extract from full-scan MS.
        decimals (int or None): round emitted numeric values to this
            many decimal places; ``None`` keeps full precision.
        timezone (str or None): UTC offset to stamp on timestamps the source
            recorded without one.
    """

    def __init__(self, export_dad_cube=True, wavelengths=None, ions=None,
                 decimal_places=None, timezone=None):
        self.export_dad_cube = export_dad_cube
        self.wavelengths = _wavelength_list(wavelengths)
        self.ions = ions
        self.decimals = decimal_places
        self.timezone = _utc_offset(timezone)

    def timestamp(self, value, required=False, recorded_offset=None):
        """
        ``value`` as an ISO 8601 timestamp, or None if it cannot be read.

        An unreadable vendor spelling is normally dropped: ASM types every
        timestamp as ISO 8601, so passing the vendor string through would put a
        value there that no reader can parse. Where the schema makes the field
        required that trade goes the other way, because omitting it breaks the
        document's structure rather than one field's format, and it throws away
        the only copy of the acquisition time. Such a field keeps the vendor
        string, and either way the caller is told.

        """
        # An offset another file in the same run recorded outranks the
        # caller's: it is what the instrument said, and `timezone` is only
        # meant to fill in a zone nothing recorded.
        stamped = _iso_timestamp(value, recorded_offset or self.timezone)
        if stamped is not None or not isinstance(value, str) or not value.strip():
            return stamped
        if required:
            warnings.warn(
                f"cannot read {value!r} as a timestamp; writing it through "
                "unchanged, because the schema requires the field. The "
                "document will not validate until the value is corrected.")
            return value
        warnings.warn(
            f"cannot read {value!r} as a timestamp; omitting the field.")
        return None

    def array(self, values):
        """The values as a Python list, rounded if a precision was set."""
        result = np.asarray(values, dtype=float)
        if self.decimals is not None:
            result = np.round(result, self.decimals)
        return result.tolist()

    def scalar(self, value):
        """One float, rounded if a precision was set."""
        value = float(value)
        return round(value, self.decimals) if self.decimals is not None \
            else value


def _wavelength_list(wavelengths):
    """Normalizes the ``wavelengths`` argument to a list of floats, or None."""
    if wavelengths is None:
        return None
    if isinstance(wavelengths, (int, float)):
        wavelengths = [wavelengths]
    return [float(wavelength) for wavelength in wavelengths]


def _select_wavelengths(ylabels, wavelengths):
    """The DAD column indices to keep, or None to keep every wavelength.

    Each requested wavelength selects the nearest available column, provided it
    is within :data:`_WAVELENGTH_TOLERANCE`; a request with no column that close
    is dropped with a warning. The kept indices are returned in ascending
    wavelength order, de-duplicated.
    """
    if wavelengths is None:
        return None
    labels = ylabels.astype(float)
    indices = []
    for wanted in wavelengths:
        index = int(np.argmin(np.abs(labels - wanted)))
        if abs(labels[index] - wanted) > _WAVELENGTH_TOLERANCE:
            warnings.warn(
                "no DAD wavelength within {:g} nm of {:g} nm; skipping".format(
                    _WAVELENGTH_TOLERANCE, wanted))
            continue
        indices.append(index)
    return sorted(set(indices))


def _injection_document(datadir, metadata, options, technique):
    """The liquid- or gas-chromatography document for one injection."""
    document = {
        "analyst": metadata.get("operator", "unknown"),
        "measurement aggregate document": {
            "measurement document": _measurements(
                datadir, options, technique),
        },
    }
    # A gas chromatography document requires a device method identifier.
    if technique is _GC:
        document["device method identifier"] = \
            metadata.get("acq_method") or "unknown"
    return document


def _device_system(metadata, technique=None):
    """The instrument-level device system document."""
    manufacturer = metadata.get("vendor")
    instrument = metadata.get("instrument")
    if isinstance(instrument, dict) and instrument.get("modules"):
        return {
            "asset management identifier": instrument.get("name") or "unknown",
            "device document": [
                _module_device(i + 1, module, manufacturer, technique)
                for i, module in enumerate(instrument["modules"])
            ],
        }
    modules = metadata.get("modules")
    if modules:
        return {
            "asset management identifier": "unknown",
            "device document": [
                _module_device(i + 1, module, manufacturer, technique)
                for i, module in enumerate(modules)
            ],
        }
    asset = metadata.get("instrument")
    return {
        "asset management identifier": asset if isinstance(asset, str)
        else "unknown",
        # With no module inventory, the only thing known about the instrument is
        # what the document itself declares it to be.
        "device document": [
            {"device type": "gas chromatograph" if technique is _GC
             else "liquid chromatograph"},
        ],
    }


def _module_device(index, module, manufacturer=None, technique=None):
    """One device document entry for an instrument module."""
    entry = {"@index": index}
    name = module.get("name")
    if name:
        entry["device identifier"] = name
    # device type is schema-required; fall back to the generic AFO device class
    # ("device", AFE_0000354) when the specific type cannot be determined, so an
    # unrecognized module still yields a valid device document entry.
    entry["device type"] = _module_device_type(module, technique) or "device"
    model = module.get("part_no") or module.get("model")
    if model:
        entry["model number"] = model
        if manufacturer:
            entry["product manufacturer"] = manufacturer
    serial = module.get("serial_no")
    if serial:
        entry["equipment serial number"] = serial
    firmware = module.get("firmware")
    if firmware:
        entry["firmware version"] = firmware
    return entry


def _normalize_module_text(text):
    """Lowercases ``text`` and reduces every separator to a single space.

    Vendors join a module's name to its index with whatever is at hand (DAD1A,
    FID_2, RID-1A, "Analog/Digital Converter"). An underscore is a word
    character, so a word-boundary match would not see one in "FID_2".
    """
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _module_device_type(module, technique=None):
    """The AFO device type for a module, or None if it cannot be mapped."""
    name = _normalize_module_text(module.get("name") or "")
    module_type = _normalize_module_text(module.get("type") or "")
    text = f"{name} {module_type}"
    # A detector that can be named must be recognized before anything below
    # falls back to a generic class.
    specific = _specific_detector_type(text, technique)
    if specific:
        return specific
    # A declared non-detector type is unambiguous, so it wins over the name.
    if module_type in _MODULE_DEVICE_TYPES:
        return _MODULE_DEVICE_TYPES[module_type]
    # When the module carries no type (the per-injection modules read from a
    # method's section headers), infer it from the name. Every term below is a
    # checked AFO class.
    if "pump" in name:
        return "pump"
    if "sampler" in name:
        return "autosampler"
    if "column" in name:
        return "column compartment"
    # Plainly a detector, but not one AFO has a class for. The generic class for
    # the document's technique says that much without asserting a measurement
    # the module may not make: an inventory entry that contradicts the cube it
    # describes is worse than one that is merely unspecific.
    if _GENERIC_DETECTOR_PATTERN.search(text) or "detector" in text:
        return _generic_detector(technique)
    return None


def _generic_detector(technique):
    """The AFO detector class for a technique, for a detector AFO cannot name.

    ``liquid chromatography detector`` and ``gas chromatography detector`` are
    disjoint siblings in AFO, so the generic fallback has to follow the document
    the device system belongs to.
    """
    return ("gas chromatography detector" if technique is _GC
            else "liquid chromatography detector")


# The named classes are not technique-neutral: AFO asserts
# `liquid chromatography detector` as a direct parent of the UV, DAD, RID and
# FLD classes, and `gas chromatography detector` of FID, TCD and ECD, each
# defined as a component of that kind of system. So naming a detector places it
# on one side of the split whether or not the document agrees, and a DAD bolted
# to a gas chromatograph would have its document assert it is part of an LC
# system. Where the document contradicts the class, the nearest ancestor that
# makes no technique claim is used instead. AFO has a real one for the
# absorbance detectors; the rest fall back to `chromatographic detector`.
_DETECTOR_TECHNIQUES = {
    "ultraviolet detector": (_LC, _NEUTRAL_ABSORBANCE),
    "diode array detector": (_LC, _NEUTRAL_ABSORBANCE),
    "refractive index detector": (_LC, "chromatographic detector"),
    "fluorescence detector": (_LC, "chromatographic detector"),
    "flame ionization detector": (_GC, "chromatographic detector"),
    "thermal conductivity detector": (_GC, "chromatographic detector"),
    "electron capture detector": (_GC, "chromatographic detector"),
}


def _for_technique(device_type, technique):
    """``device_type``, or a neutral ancestor if the document contradicts it.

    An unknown technique contradicts nothing, so the named class is kept. That
    differs from :func:`_generic_detector`, which has to name some class and
    defaults to the far more common liquid chromatography; here the honest
    answer to "which document is this in?" being unknown is to leave the
    detector's own class alone.
    """
    claim = _DETECTOR_TECHNIQUES.get(device_type)
    if claim is None or technique is None:
        return device_type            # ELSD and mass spectrometer claim neither
    claimed, neutral = claim
    return device_type if claimed is technique else neutral


def _specific_detector_type(text, technique=None):
    """The AFO class for the detector named in ``text``, or None.

    ``text`` must already be normalized (see :func:`_normalize_module_text`).
    """
    for pattern, device_type in _DETECTOR_PATTERNS:
        if pattern.search(text):
            return _for_technique(device_type, technique)
    return None


def _measurements(datadir, options, technique):
    """The measurement documents for a directory's exported channels."""
    metadata = datadir.metadata
    peak_groups = _peak_groups_by_channel(getattr(datadir, "peaks", None))
    measurements = []
    for datafile in datadir.datafiles:
        group = peak_groups.get(_channel_key(datafile.name))
        has_peaks = bool(group and group.get("peaks"))
        for measurement in _build_measurements(
                datafile, metadata, options, has_peaks, technique):
            _add_injection_document(
                measurement, metadata, datadir.name, technique, options)
            if group and _admits_peaks(measurement):
                _add_processed_data(measurement, group, options)
            measurements.append(measurement)
    return measurements


def _admits_peaks(measurement):
    """Whether the measurement's cube can carry a peak list (absorbance only)."""
    cube = measurement.get(_CHROMATOGRAM_CUBE)
    if not cube:
        return False
    measures = cube.get("cube-structure", {}).get("measures", [])
    return bool(measures) and measures[0].get("concept") == "absorbance"


def _channel_device_type(descriptor, technique):
    """The AFO device type for a channel's detector.

    A detector AFO has a class for keeps it in any document; one it does not
    (charged aerosol) takes the generic class for the document's technique.
    """
    if descriptor.get("generic"):
        return _generic_detector(technique)
    return _for_technique(descriptor["device_type"], technique)


def _build_measurements(datafile, metadata, options, has_peaks=False,
                        technique=None):
    """The measurements for one datafile: zero, one, or several."""
    descriptor = _DETECTOR_CUBES.get(datafile.detector)
    if descriptor is not None:
        # A diode-array acquisition is the only multi-column case (a 2-D
        # spectrum). Every other detector here is single-signal; an unexpected
        # multi-column grid is skipped rather than silently flattened.
        if datafile.detector == 'UV' and datafile.data.shape[1] > 1:
            if not options.export_dad_cube:
                return []
            measurement = _spectrum_measurement(
                datafile, metadata,
                _channel_device_type(descriptor, technique), options)
            return [measurement] if measurement is not None else []
        if datafile.data.shape[1] == 1:
            return [_detector_measurement(
                datafile, metadata, descriptor, options, has_peaks,
                technique)]
        return []
    if datafile.detector == 'MS':
        return _mass_chromatogram_measurements(datafile, metadata, options)
    return []


# The measure a non-absorbance channel is relabeled to so its peak list can be
# carried (the schema models a peak list only on an absorbance measurement).
_ABSORBANCE_DESCRIPTOR = {"concept": "absorbance", "unit": "mAU"}


def _detector_measurement(datafile, metadata, descriptor, options,
                          has_peaks=False, technique=None):
    """A measurement for a single-signal detector channel (1-D chromatogram).

    The cube's measure concept and unit come from the detector descriptor
    (:data:`_DETECTOR_CUBES`). Most detectors get their faithful quantity (UV
    absorbance, FID and CAD electric current, ELSD intensity); RID alone keeps
    the absorbance-cube interim. An FID also carries its detection type, and a
    UV channel its detector wavelength setting.

    One exception: the schema models a processed-data peak list only on an
    absorbance measurement. So a non-absorbance channel that carries integrated
    peaks is relabeled to absorbance (the device type stays truthful) so the
    peaks survive, with a note recording the real quantity. Dropping the peaks
    would lose more than the imprecise unit does, and the published model is
    still being refined.
    """
    control = {"device type": _channel_device_type(descriptor, technique)}
    detection_type = descriptor.get("detection_type")
    if detection_type:
        control["detection type"] = detection_type
    if datafile.detector == 'UV':
        wavelength = datafile.metadata.get("wavelength")
        if wavelength is not None:
            control["detector wavelength setting"] = _quantity(
                wavelength, "nm", options)
    relabel = has_peaks and descriptor["concept"] != "absorbance"
    cube_descriptor = _ABSORBANCE_DESCRIPTOR if relabel else descriptor
    measurement = _measurement(
        datafile, metadata, control, _CHROMATOGRAM_CUBE,
        _detector_cube(datafile, cube_descriptor, options), options)
    if relabel:
        _note_relabeled_measure(measurement, descriptor)
    return measurement


def _note_relabeled_measure(measurement, descriptor):
    """Records the real quantity of a channel relabeled to absorbance."""
    measurement["custom information aggregate document"] = {
        "custom information document": [{
            "datum label": "reported measure",
            "scalar string datum": (
                "This channel measures {} (in {}); its values are reported as "
                "absorbance in mAU so the integrated peak list can be carried, "
                "which the schema models only on an absorbance measurement."
                .format(descriptor["concept"], descriptor["unit"])),
        }],
    }


def _mass_chromatogram_measurements(datafile, metadata, options):
    """Mass chromatogram measurements for an MS channel.

    A SIM channel (its monitored ions) is always exported: every ion becomes a
    mass chromatogram (ion count over retention time). A full scan is a 2D
    retention-by-m/z grid that the published schema cannot hold faithfully, so
    it is exported only ion by ion: each requested m/z in ``ions`` is pulled
    from the grid as its own mass chromatogram. SIM and scan are told apart by
    the channel's ``acquisition_mode`` (read from the acquisition method);
    absent that, only a single-ion channel is taken as SIM. A per-scan HRMS
    profile has no single shared m/z axis (reading ``ylabels`` raises), so it is
    skipped. See the ASM detectors documentation.
    """
    try:
        ylabels = datafile.ylabels
    except Exception:
        return []  # per-scan HRMS, out of scope
    if _is_sim(datafile):
        return [_extracted_ion(datafile, metadata, ylabels, index, options,
                               single=datafile.data.shape[1] == 1)
                for index in range(datafile.data.shape[1])]
    measurements = []
    for requested in _normalize_ions(options.ions):
        index = _nearest_ion(ylabels, requested)
        if index is None:
            warnings.warn(
                f"No m/z within {_ION_MATCH_TOLERANCE} of {requested:g} in "
                f"{datafile.name}; skipping that ion.")
            continue
        measurements.append(
            _extracted_ion(datafile, metadata, ylabels, index, options))
    return measurements


def _is_sim(datafile):
    """Whether an MS channel is SIM (all ions exported) rather than a scan.

    Trusts the ``acquisition_mode`` tag set from the acquisition method. With no
    tag, a single-ion channel is SIM and a multi-column grid is treated as a
    scan (exported only on request) rather than guessed.
    """
    mode = datafile.metadata.get("acquisition_mode")
    if mode == "SIM":
        return True
    if mode == "Scan":
        return False
    return datafile.data.shape[1] == 1


def _extracted_ion(datafile, metadata, ylabels, index, options, single=False):
    """One ion's mass chromatogram, taken from column ``index`` of the grid."""
    mz = float(ylabels[index]) if len(ylabels) > index else None
    # A single-ion channel keeps the file's own name; for one of several ions the
    # m/z disambiguates the identifier, unless the ylabel is missing (no m/z).
    identifier = datafile.name if (single or mz is None) \
        else "{} m/z {:g}".format(datafile.name, mz)
    return _mass_chromatogram_measurement(
        datafile, metadata, datafile.data[:, index], mz, identifier, options)


def _mass_chromatogram_measurement(datafile, metadata, intensities, mz,
                                   identifier, options):
    """One mass chromatogram measurement for a monitored or extracted ion."""
    control = {"device type": "mass spectrometer"}
    return _measurement(
        datafile, metadata, control,
        _MASS_CHROMATOGRAM_CUBE,
        _mass_chromatogram_cube(intensities, mz, datafile, options), options,
        identifier=identifier)


def _normalize_ions(ions):
    """The requested ions as a list, accepting a single number or None."""
    if ions is None:
        return []
    if isinstance(ions, (int, float)) and not isinstance(ions, bool):
        return [ions]
    return list(ions)


def _nearest_ion(ylabels, mz):
    """Index of the grid m/z nearest ``mz`` within tolerance, or None."""
    import numpy as np
    labels = np.asarray(ylabels, dtype=float)
    if labels.size == 0:
        return None
    index = int(np.argmin(np.abs(labels - mz)))
    if abs(labels[index] - mz) > _ION_MATCH_TOLERANCE:
        return None
    return index


def _measurement(datafile, metadata, control, cube_key, cube, options,
                 identifier=None):
    """Wraps a data cube in the shared measurement envelope."""
    sample = {"sample identifier": metadata.get("sample", "unknown")}
    if "vialpos" in metadata:
        sample["location identifier"] = str(metadata["vialpos"])
    measurement = {
        "measurement identifier": identifier or datafile.name,
        "sample document": sample,
        "device control aggregate document": {
            "device control document": [control],
        },
        "chromatography column document": {},
        cube_key: cube,
    }
    # Optional in both ADMs, so an unreadable vendor spelling is dropped rather
    # than passed through: ASM types this as ISO 8601, and a vendor-format
    # string here would be a value no reader can parse.
    timestamp = options.timestamp(
        metadata.get("date"), recorded_offset=metadata.get("utc_offset"))
    if timestamp:
        measurement["measurement time"] = timestamp
    return measurement


def _spectrum_measurement(datafile, metadata, device_type, options):
    """A measurement for a multi-wavelength DAD spectrum.

    Returns ``None`` when ``options.wavelengths`` selects none of the grid's
    wavelengths, so the caller emits no spectrum rather than an empty cube.
    """
    cube = _spectrum_cube(datafile, options)
    if cube is None:
        return None
    control = {"device type": device_type}
    return _measurement(
        datafile, metadata, control, _SPECTRUM_CUBE, cube, options)


def _add_injection_document(measurement, metadata, identifier, technique,
                            options):
    """Adds an injection document, per the technique's rules.

    Liquid chromatography makes the injection document optional, so it is
    emitted only when the injection volume is known, carrying the identifier,
    the volume (in mm^3, the LC ADM's unit), and the injection time. Gas
    chromatography requires an injection document on every measurement, so it
    is always emitted there, carrying the identifier and time and the volume
    (in uL, the GC ADM's unit) when the source records it. A GC run that does
    not record an injection volume cannot fully satisfy the schema, which
    requires that field; the document is still emitted with what is known.
    """
    volume = metadata.get("injection_volume")
    has_volume = isinstance(volume, dict) and volume.get("value") is not None
    if technique is _LC:
        if not has_volume:
            return
        document = {
            "injection identifier": identifier or "unknown",
            # The LC ADM expresses injection volume in mm^3; 1 uL == 1 mm^3.
            "autosampler injection volume setting (chromatography)": {
                "value": options.scalar(volume["value"]),
                "unit": "mm^3",
            },
        }
    else:
        document = {"injection identifier": identifier or "unknown"}
        if has_volume:
            # The GC ADM expresses injection volume in microlitres. The schema
            # pins the Greek small mu (U+03BC), not the micro sign (U+00B5).
            document["injection volume setting"] = {
                "value": options.scalar(volume["value"]),
                "unit": "μL",
            }
    # Required by both ADMs, so an unreadable vendor spelling is written
    # through rather than dropped; see _Options.timestamp.
    timestamp = options.timestamp(
        metadata.get("date"), required=True,
        recorded_offset=metadata.get("utc_offset"))
    if timestamp:
        document["injection time"] = timestamp
    measurement["injection document"] = document


def _add_processed_data(measurement, group, options):
    """Adds a processed data document carrying the channel's peak list."""
    peaks = [_asm_peak(i + 1, peak, options)
             for i, peak in enumerate(group["peaks"])]
    measurement[_PROCESSED_DATA] = {
        "processed data document": [
            {"@index": 1, "peak list": {"peak": peaks}},
        ],
    }


def _asm_peak(index, peak, options=None):
    """One ASM peak, with retention/start/end times in seconds."""
    entry = {"@index": index}
    mapping = (
        ("retention_time", "retention time", "s", _SECONDS_PER_MINUTE),
        ("start_time", "peak start", "s", _SECONDS_PER_MINUTE),
        ("end_time", "peak end", "s", _SECONDS_PER_MINUTE),
        ("area", "peak area", "mAU.s", 1.0),
        ("area_percent", "relative peak area", "%", 1.0),
        ("height", "peak height", "mAU", 1.0),
        ("height_percent", "relative peak height", "%", 1.0),
        ("symmetry", "asymmetry factor measured at 5 % height",
         "(unitless)", 1.0),
    )
    for source, target, unit, scale in mapping:
        value = peak.get(source)
        # A malformed val attribute can arrive as a non-numeric string; skip it
        # rather than fail the whole export.
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            entry[target] = _quantity(value * scale, unit, options)
    return entry


def _peak_groups_by_channel(peaks):
    """Indexes an injection's peak groups by channel (e.g. ``DAD1A``)."""
    groups = {}
    for group in (peaks or []):
        if group.get("channel_file"):
            groups[_channel_key(group["channel_file"])] = group
        elif group.get("signal"):
            # Match the channel-name normalization used on the lookup side.
            groups[group["signal"].replace(" ", "").upper()] = group
    return groups


def _channel_key(name):
    """A channel name normalized for matching (no extension, upper case)."""
    return os.path.splitext(name)[0].upper()


# The ultraviolet-absorbance cube measure is pinned to mAU in the ADM, so a
# source unit is normalized to mAU on the way out, scaling the values to match.
# ChemStation already reports mAU; Waters UV chromatograms report AU (1 AU =
# 1000 mAU). An unrecognized unit is labeled mAU unscaled, as before.
_ABSORBANCE_TO_MAU = {"AU": 1000.0, "mAU": 1.0}


def _absorbance_unit_and_scale(datafile):
    """The schema absorbance unit (mAU) and the value multiplier to reach it."""
    return "mAU", _ABSORBANCE_TO_MAU.get(datafile.metadata.get("unit"), 1.0)


def _detector_cube(datafile, descriptor, options):
    """Lays a single-signal trace into a 1-D (retention time) data cube.

    The measure concept and unit come from the detector descriptor. Absorbance
    (UV and the RID interim) is normalized to the schema's mAU, scaling the
    values; every other detector's values are the vendor's own, unscaled.
    """
    concept, unit = descriptor["concept"], descriptor["unit"]
    values = datafile.data[:, 0]
    if concept == "absorbance":
        unit, scale = _absorbance_unit_and_scale(datafile)
        values = values * scale
    return {
        "label": datafile.name,
        "cube-structure": {
            "dimensions": [_component("retention time", "s")],
            "measures": [_component(concept, unit)],
        },
        "data": {
            "dimensions": [_retention_seconds(datafile, options)],
            "measures": [options.array(values)],
        },
    }


def _spectrum_cube(datafile, options):
    """
    Lays a DAD spectrum into a 2D (retention time x wavelength) data cube.

    ASM measure arrays are flat, so the (retention time, wavelength) grid is
    flattened with wavelength varying fastest, which is numpy's C order. When
    ``options.wavelengths`` is set, only those wavelengths' columns are kept;
    if none match, the cube is omitted (``None``).
    """
    unit, scale = _absorbance_unit_and_scale(datafile)
    labels = datafile.ylabels.astype(float)
    data = datafile.data
    indices = _select_wavelengths(datafile.ylabels, options.wavelengths)
    if indices is not None:
        if not indices:
            return None
        labels = labels[indices]
        data = data[:, indices]
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
                _retention_seconds(datafile, options),
                options.array(labels),
            ],
            "measures": [options.array(data.flatten() * scale)],
        },
    }


def _mass_chromatogram_cube(intensities, mz, datafile, options):
    """Lays a single ion's trace into a 1D (retention time) data cube.

    The measure is ion count. ``intensities`` is the trace at the monitored or
    extracted m/z. That m/z has no dimension of its own in a mass chromatogram,
    so it is recorded in the cube label.
    """
    label = datafile.name
    if mz is not None:
        label = "{} (m/z {:g})".format(datafile.name, mz)
    return {
        "label": label,
        "cube-structure": {
            "dimensions": [_component("retention time", "s")],
            "measures": [_component("count", "Counts")],
        },
        "data": {
            "dimensions": [_retention_seconds(datafile, options)],
            "measures": [options.array(intensities)],
        },
    }


def _retention_seconds(datafile, options):
    """Retention times in seconds (rainbow stores minutes)."""
    return options.array(datafile.xlabels * _SECONDS_PER_MINUTE)


def _component(concept, unit):
    """A cube-structure dimension/measure descriptor."""
    return {"concept": concept, "unit": unit, "@componentDatatype": "double"}


def _quantity(value, unit, options=None):
    """An ASM quantity value, rounded when ``options`` sets a precision."""
    value = options.scalar(value) if options is not None else float(value)
    return {"value": value, "unit": unit}


# --- Reverse mapping: ASM document -> rainbow objects ---


def from_asm(document, name="asm"):
    """
    Reconstructs a DataDirectory from an ASM liquid- or gas-chromatography
    document.

    The inverse of :func:`to_asm`: each measurement's data cube becomes a
    DataFile (retention time back from seconds to minutes, the measure back to
    the data array) and the shared envelope becomes directory metadata. Only
    the UV cubes that :func:`to_asm` writes are reconstructed. Use
    :func:`sequence_from_asm` to recover a per-injection sequence.

    Args:
        document (dict): An ASM document (e.g. from ``json.load``).
        name (str, optional): Name for the reconstructed DataDirectory.

    Returns:
        DataDirectory.

    """
    aggregate, documents = _aggregate_and_documents(document)
    metadata = {}
    instrument = _instrument_from_device_system(
        aggregate.get("device system document"))
    if instrument:
        metadata["instrument"] = instrument

    datafiles = []
    peak_groups = []
    for lc_document in documents:
        _absorb_lc_document(lc_document, metadata, datafiles, peak_groups)
    return _directory(name, datafiles, metadata, peak_groups)


def _first(value):
    """
    The first entry of a field the schema declares as a list, or ``{}``.

    Documents rainbow did not write are shaped more freely than its own: a
    writer may emit a lone object where a list is declared, or an empty list
    where rainbow assumes one entry. Callers want whichever object is there, or
    nothing, never an IndexError on someone else's document.

    """
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def _as_documents(value):
    """A schema list field normalized to a list, tolerating a lone object."""
    if isinstance(value, dict):
        return [value]
    return value if isinstance(value, list) else []


def _text(value):
    """
    A schema string field as a string, or None.

    A value datum may be written either bare or as a ``{"value": ...}`` object,
    and a document rainbow did not write may put anything at all in a field it
    declares as text. rainbow's own objects take strings, so a non-string here
    has to become None rather than propagate to a constructor that rejects it.

    """
    if isinstance(value, dict):
        value = value.get("value")
    return value if isinstance(value, str) else None


def _number(value):
    """
    A schema numeric field as a number, or None.

    The counterpart to :func:`_text`. A foreign writer routinely spells a
    number as the string ``"1.5"``, and rainbow tolerates that inside a cube
    because numpy coerces it. Everywhere else the value reaches arithmetic or
    user code directly, so a non-number has to become None here rather than
    surface as a TypeError halfway through a read.

    """
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _cube_data(cube):
    """
    A cube's inlined ``(dimensions, measures)``, or None when it has none.

    The published cube structure does not require the ``data`` member, so a
    conforming document may describe a cube's shape while carrying its values
    somewhere rainbow cannot follow. Such a cube is skipped the way an
    unrepresentable one is, rather than taking the whole read down.

    """
    if not isinstance(cube, dict):
        return None
    data = cube.get("data")
    if not isinstance(data, dict):
        return None
    dimensions = data.get("dimensions")
    measures = data.get("measures")
    if not isinstance(dimensions, list) or not dimensions:
        return None
    if not isinstance(measures, list) or not measures:
        return None
    return dimensions, measures


def _aggregate_and_documents(document):
    """The aggregate document and its per-injection documents, either technique.

    Reads a liquid- or gas-chromatography document, so a gas-chromatography
    export round-trips its UV channels too (the FID and MS cubes are
    export-only, like the mass chromatograms; see the round-trip caveat).
    """
    if not isinstance(document, dict):
        raise TypeError(
            f"ASM document must be a dict, not {type(document).__name__}. "
            "Parse the file first, e.g. json.load(open(path)).")
    for technique in (_LC, _GC):
        aggregate = document.get(technique["aggregate"])
        if isinstance(aggregate, dict):
            return aggregate, _as_documents(aggregate.get(technique["document"]))
    raise KeyError(
        "document has no liquid- or gas-chromatography aggregate document")


def sequence_from_asm(document, name="asm"):
    """
    Reconstructs a DataSequence from an ASM liquid- or gas-chromatography
    document.

    The inverse of :func:`sequence_to_asm`: each liquid chromatography document
    becomes one injection (a DataDirectory), the device system document becomes
    the sequence's instrument, and any processed-data peaks are reattached to
    the injections they belong to.

    Round-trip caveat: only what :func:`sequence_to_asm` writes is recoverable.
    The injection's original .D folder name is not stored, so injections are
    named from their sample identifier; metadata rainbow reads but does not
    export (column temperature, flow rate, dilution) is not restored.

    Args:
        document (dict): An ASM document (e.g. from ``json.load``).
        name (str, optional): Name for the reconstructed DataSequence.

    Returns:
        DataSequence.

    """
    from rainbow.datasequence import DataSequence

    aggregate, documents = _aggregate_and_documents(document)
    metadata = {}
    instrument = _instrument_from_device_system(
        aggregate.get("device system document"))
    if instrument:
        metadata["instrument"] = instrument

    injections = []
    for index, lc_document in enumerate(documents):
        injection_metadata = {}
        datafiles = []
        peak_groups = []
        _absorb_lc_document(
            lc_document, injection_metadata, datafiles, peak_groups)
        injection_name = injection_metadata.get("sample") \
            or f"injection_{index + 1}"
        injections.append(_directory(
            injection_name, datafiles, injection_metadata, peak_groups))

    metadata["injection_count"] = len(injections)
    operators = {inj.metadata.get("operator") for inj in injections} - {None}
    if len(operators) == 1:
        metadata["operator"] = operators.pop()
    return DataSequence(name, injections, metadata)


def _directory(name, datafiles, metadata, peak_groups):
    """Builds a DataDirectory and attaches any reconstructed peaks."""
    from rainbow.datadirectory import DataDirectory
    datadir = DataDirectory(name, datafiles, metadata)
    if peak_groups:
        datadir.peaks = peak_groups
    return datadir


def _absorb_lc_document(lc_document, metadata, datafiles, peak_groups):
    """Reads one liquid chromatography document into datafiles and metadata."""
    if not isinstance(lc_document, dict):
        return
    analyst = _text(lc_document.get("analyst"))
    if analyst and analyst != "unknown":
        metadata.setdefault("operator", analyst)
    # A document rainbow did not write may carry neither key, or emit a single
    # measurement where a list is declared. Absorbing what is there beats
    # raising on a document that is merely shaped differently.
    measurements = _as_documents(
        _first(lc_document.get("measurement aggregate document"))
        .get("measurement document"))
    for measurement in measurements:
        if not isinstance(measurement, dict):
            continue
        datafile = _datafile_from_measurement(measurement)
        if datafile is None:
            continue  # a measurement rainbow did not write (no UV cube)
        _absorb_envelope(measurement, metadata)
        datafiles.append(datafile)
        group = _peaks_from_measurement(measurement)
        if group:
            peak_groups.append(group)


def _absorb_envelope(measurement, metadata):
    """Lifts a measurement's envelope fields up to directory metadata."""
    sample = _first(measurement.get("sample document"))
    identifier = _text(sample.get("sample identifier"))
    if identifier and identifier != "unknown":
        metadata.setdefault("sample", identifier)
    location = _text(sample.get("location identifier"))
    if location:
        metadata.setdefault("vialpos", location)
    date = _text(measurement.get("measurement time"))
    if date:
        metadata.setdefault("date", date)
    volume = _number(_first(measurement.get("injection document")).get(
        "autosampler injection volume setting (chromatography)"))
    if volume is not None:
        # ASM stores mm^3; rainbow reports uL (1 mm^3 == 1 uL).
        metadata.setdefault(
            "injection_volume", {"value": volume, "unit": "µL"})


def _datafile_from_measurement(measurement):
    """Reconstructs one DataFile from an ASM measurement document."""
    import numpy as np
    from rainbow.datafile import DataFile

    identifier = measurement.get("measurement identifier")
    name = _text(identifier)
    if name is None:
        if identifier is not None:
            # Present but unusable: the channel keeps its data under the
            # fallback name, where it can collide with another such channel,
            # so say so rather than let one quietly replace the other.
            warnings.warn(
                "measurement identifier is not text "
                f"({type(identifier).__name__}); naming the channel 'trace'.")
        name = "trace"
    file_metadata = {}

    control = _first(_first(measurement.get(
        "device control aggregate document")).get("device control document"))
    wavelength = _number(control.get("detector wavelength setting"))

    # A cube's inlined values are declared numeric, but nothing stops another
    # writer putting text (or nulls) there. The channel is skipped the way an
    # unrepresentable one is, rather than failing the whole read.
    try:
        if _SPECTRUM_CUBE in measurement:
            cube = _cube_data(measurement[_SPECTRUM_CUBE])
            if cube is None or len(cube[0]) < 2:
                return None  # no inlined grid to rebuild
            dimensions, measures = cube
            times, wavelengths = dimensions[0], dimensions[1]
            xlabels = np.array(times, dtype=float) / _SECONDS_PER_MINUTE
            ylabels = np.array(wavelengths, dtype=float)
            # Un-flatten the grid (wavelength varied fastest, i.e. C order).
            data = np.array(measures[0], dtype=float).reshape(
                len(times), len(wavelengths))
        elif _CHROMATOGRAM_CUBE in measurement and _is_absorbance(
                measurement[_CHROMATOGRAM_CUBE]):
            cube = _cube_data(measurement[_CHROMATOGRAM_CUBE])
            if cube is None:
                return None  # no inlined values to rebuild
            dimensions, measures = cube
            xlabels = np.array(dimensions[0], dtype=float) / _SECONDS_PER_MINUTE
            data = np.array(measures[0], dtype=float).reshape(-1, 1)
            # reshape(-1, 1) accepts any length, so a measure array that does
            # not match its time axis would pair every later point with the
            # wrong retention time. Nothing downstream rechecks this.
            if xlabels.ndim == 1 and data.shape[0] != xlabels.size:
                warnings.warn(
                    f"{name}: chromatogram cube has {data.shape[0]} values for "
                    f"{xlabels.size} retention times; skipping the channel.")
                return None
            if wavelength is not None:
                ylabels = np.array([wavelength])
                file_metadata["wavelength"] = wavelength
            else:
                ylabels = np.array([''])
        else:
            # Reconstruct only an absorbance (UV) trace. A faithful generic
            # detector cube (CAD/ELSD/FID electric current or intensity) or a
            # mass chromatogram is export-only, so it is skipped. A CAD/ELSD/FID
            # channel relabeled to absorbance to carry peaks does come back, as
            # a UV trace; that is the documented cost of the relabel.
            return None
        # A time axis that is not a flat list of numbers still converts under
        # numpy, just to the wrong number of axes. Checking here skips the one
        # bad channel; leaving it to DataFile would raise its internal argument
        # error and take down every other channel in the document with it.
        if xlabels.ndim != 1 or ylabels.ndim != 1 or data.ndim != 2:
            warnings.warn(
                f"{name}: cube axes are not the flat lists of numbers the "
                "cube declares; skipping the channel.")
            return None
        return DataFile(name, 'UV', xlabels, ylabels, data, file_metadata)
    except (TypeError, ValueError, OverflowError) as error:
        # OverflowError: JSON integer literals are unbounded, so a 400-digit
        # one raises here rather than converting to a float.
        warnings.warn(
            f"{name}: cube values are not the numbers the cube declares "
            f"({error}); skipping the channel.")
        return None


def _is_absorbance(cube):
    """Whether a chromatogram cube's measure is absorbance (a UV trace)."""
    if not isinstance(cube, dict):
        return False
    measures = _first(cube.get("cube-structure")).get("measures")
    return _first(measures).get("concept") == "absorbance"


def _peaks_from_measurement(measurement):
    """Reconstructs a peak group from a measurement's processed data, or None."""
    processed = _first(measurement.get(_PROCESSED_DATA))
    document = _first(processed.get("processed data document"))
    asm_peaks = [peak for peak
                 in _as_documents(_first(document.get("peak list")).get("peak"))
                 if isinstance(peak, dict)]
    if not asm_peaks:
        return None

    channel = _text(measurement.get("measurement identifier"))
    if channel is None:
        # An unkeyed group is dropped by _peak_groups_by_channel on the way
        # back out, so these peaks are read and then silently discarded.
        warnings.warn(
            f"a peak list of {len(asm_peaks)} peaks has no usable measurement "
            "identifier; it cannot be joined to a channel and will be lost on "
            "re-export.")
    control = _first(_first(measurement.get(
        "device control aggregate document")).get("device control document"))
    wavelength = _number(control.get("detector wavelength setting"))
    return {
        "signal": _channel_key(channel) if channel else None,
        "wavelength": wavelength,
        "description": None,
        "channel_file": channel,
        "peaks": [_peak_from_asm(peak) for peak in asm_peaks],
    }


def _peak_from_asm(peak):
    """Reconstructs a peak's measures, times back from seconds to minutes."""
    def value(key):
        # A foreign writer may spell a measure as text, or as something else
        # entirely. These go straight into user code and into arithmetic just
        # below, so anything that is not a number has to drop out here.
        return _number(peak.get(key))

    def minutes(key):
        seconds = value(key)
        return seconds / _SECONDS_PER_MINUTE if seconds is not None else None

    return {
        "retention_time": minutes("retention time"),
        "start_time": minutes("peak start"),
        "end_time": minutes("peak end"),
        "area": value("peak area"),
        "area_percent": value("relative peak area"),
        "height": value("peak height"),
        "height_percent": value("relative peak height"),
        "symmetry": value("asymmetry factor measured at 5 % height"),
    }


def _instrument_from_device_system(device_system):
    """Reconstructs the instrument dict from a device system document, or None."""
    if not isinstance(device_system, dict):
        return None
    modules = []
    for device in _as_documents(device_system.get("device document")):
        if not isinstance(device, dict):
            continue
        if "model number" not in device \
                and "equipment serial number" not in device:
            continue  # the bare chromatograph fallback entry
        modules.append({
            "name": _text(device.get("written name"))
            or _text(device.get("device identifier")),
            "type": _text(device.get("device type")),
            "part_no": _text(device.get("model number")),
            "serial_no": _text(device.get("equipment serial number")),
            "firmware": _text(device.get("firmware version")),
        })
    if not modules:
        return None
    return {
        "name": _text(device_system.get("asset management identifier")),
        "modules": modules,
    }
