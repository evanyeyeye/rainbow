"""
Read the per-injection method and sample sidecars of an Agilent .D directory.

Alongside the data channels, a ChemStation/OpenLab .D holds:

    acq.macaml   the acquisition method (ACAML)
    SAMPLE.XML   the sample setup (name, dilution, method paths)

This module distills those into a small, vendor-neutral metadata dict that
read() merges onto a DataDirectory: the operator, injection volume, column
temperature, flow rate, run time, the instrument modules, and the sample
amounts. It is best-effort, so any field the sidecars do not carry, or a
sidecar that is missing or unreadable, simply contributes nothing.

It also reads the MS acquisition mode from the ``acqmeth.txt`` instrument-
control report so each MS channel can be tagged SIM or Scan; see
:func:`tag_acquisition_modes`.
"""
import os
import re
import xml.etree.ElementTree as ET

from rainbow.agilent import acaml


# An instrument-module section is titled like "DAD (G7117B)": the module name
# followed by its model number in parentheses.
_MODULE_RE = re.compile(r"^\s*(.+?)\s*\(([^()]+)\)\s*$")

# The ChemStation instrument-control report, which names the MS acquisition
# mode ("Scan", "SIM", or "SIM/Scan") in its MS Information section.
_METHOD_REPORT = "acqmeth.txt"

# The "Acquisition Mode : <mode>" line of that report.
_ACQ_MODE_RE = re.compile(
    r"^\s*Acquisition Mode\s*:\s*(?P<mode>.+?)\s*$",
    re.MULTILINE | re.IGNORECASE)

# The "Sample Inlet : GC" / "Sample Inlet : LC" line names the separation
# technique (gas vs liquid chromatography), the instrument's own record of it.
# The banner a Chemstation method report opens with, through the end of the
# line that names the instrument. Bounded to a few lines so a mention of the
# instrument type elsewhere in the report (a file path, an operator's note)
# does not read as the instrument declaring itself.
_INSTRUMENT_BANNER_RE = re.compile(
    r"INSTRUMENT\s+CONTROL\s+PARAMETERS\s*:.*?(?:\n.*?){0,3}\n",
    re.IGNORECASE | re.DOTALL)

_SAMPLE_INLET_RE = re.compile(
    r"^\s*Sample Inlet\s*:\s*(?P<inlet>\S+)", re.MULTILINE | re.IGNORECASE)


def decode_text(raw):
    """
    Decodes a metadata text blob whose encoding is not known in advance.

    Agilent sidecars are a mix of UTF-8, UTF-16LE, and UTF-16BE (often with a
    BOM, sometimes only inferable from interleaved NUL bytes). Returns a ``str``
    decoded with the best-guess encoding, never raising. (Mirrors the helper in
    the debug subsystem's ``_util``; kept here so the core read has no
    dependency on it.)
    """
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        enc = "utf-16"
    elif b"\x00" in raw[:64]:
        enc = "utf-16-le"
    elif raw[:3] == b"\xef\xbb\xbf":
        enc = "utf-8-sig"
    else:
        enc = "utf-8"
    try:
        return raw.decode(enc, "replace")
    except (LookupError, ValueError):
        return raw.decode("latin-1", "replace")


def parse_injection_metadata(path):
    """
    Reads per-injection method and sample metadata from a .D directory.

    Args:
        path (str): Path of the .D directory.

    Returns:
        dict: Any of ``operator``, ``modules``, ``injection_volume``,
        ``column_temperature``, ``flow_rate``, ``run_time``, ``dilution``,
        ``multiplier``, ``sample_amount``, and ``acq_method`` that the sidecars
        supply. Quantities are ``{"value": float, "unit": str}``.

    """
    metadata = {}
    metadata.update(_from_acq_method(path))
    metadata.update(_from_sample_xml(path))
    return metadata


def _from_acq_method(path):
    """Method settings from acq.macaml."""
    acq_path = os.path.join(path, "acq.macaml")
    if not os.path.isfile(acq_path):
        return {}
    try:
        doc = acaml.read(acq_path)
    except (ET.ParseError, ValueError, LookupError, OSError):
        # A sidecar that is missing or unreadable contributes nothing, which
        # includes one whose XML declaration names an encoding Python does not
        # have: that raises LookupError out of the parser, and taking the whole
        # read down over an optional metadata file is the wrong failure mode.
        return {}
    sections = doc["sections"]

    out = {}
    operator = doc["doc_info"].get("operator")
    if operator:
        out["operator"] = operator

    modules = _modules(sections)
    if modules:
        out["modules"] = modules

    fields = {
        "injection_volume": _quantity(_param(sections, "Injection Volume")),
        "flow_rate": _quantity(_param(sections, "Flow", unit_has="mL/min")),
        "column_temperature": _column_temperature(sections),
        "run_time": _quantity(_param(sections, "Stoptime", unit="min")),
    }
    out.update({key: value for key, value in fields.items() if value})
    return out


def _from_sample_xml(path):
    """Sample setup from SAMPLE.XML."""
    sample_path = os.path.join(path, "SAMPLE.XML")
    if not os.path.isfile(sample_path):
        return {}
    try:
        root = ET.parse(sample_path).getroot()
    except (ET.ParseError, ValueError, LookupError, OSError):
        return {}

    out = {}
    for key, tag in (("dilution", "Dilution"),
                     ("multiplier", "Multiplier"),
                     ("sample_amount", "Amount")):
        element = root.find(tag)
        if element is not None and element.text is not None:
            out[key] = _number(element.text)

    method_path = root.find("ACQMethodPath")
    if method_path is not None and method_path.text:
        # Only the method file name; the directory part can carry a user's
        # name or path and is not needed.
        normalized = method_path.text.replace("\\", "/").rstrip("/")
        out["acq_method"] = os.path.basename(normalized)
    return out


def _modules(sections):
    """The instrument modules, read from the method's section headers."""
    acquisition = _section(sections, "Acquisition Method")
    container = acquisition["sections"] if acquisition else sections
    modules = []
    for section in container:
        match = _MODULE_RE.match(section.get("name") or "")
        if match:
            modules.append(
                {"name": match.group(1).strip(),
                 "model": match.group(2).strip()})
    return modules


def _column_temperature(sections):
    """The controlled column-compartment temperature, if any."""
    control = _section(sections, "Left Temperature Control")
    if not control:
        return None
    for parameter in control["parameters"]:
        if parameter["name"] == "Temperature":
            return _quantity(parameter)
    return None


def _section(sections, name):
    """First section with the given name, searched recursively."""
    for section in sections:
        if section.get("name") == name:
            return section
        found = _section(section["sections"], name)
        if found:
            return found
    return None


def _param(sections, name, unit=None, unit_has=None):
    """First parameter matching the name and optional unit constraints."""
    for parameter in acaml.iter_parameters(sections):
        if parameter.get("name") != name:
            continue
        parameter_unit = parameter.get("unit") or ""
        if unit is not None and parameter_unit != unit:
            continue
        if unit_has is not None and unit_has not in parameter_unit:
            continue
        return parameter
    return None


def _quantity(parameter):
    """A parameter as ``{"value": float, "unit": str}``, or None."""
    if not parameter:
        return None
    try:
        value = float(parameter["value"])
    except (TypeError, ValueError, KeyError):
        return None
    return {"value": value, "unit": parameter.get("unit")}


def _number(text):
    """Text as an int or float when it parses numerically, else unchanged."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return text
    return int(value) if value.is_integer() else value


def _read_method_report(path):
    """The decoded text of the .D method report, or None if unreadable."""
    report = os.path.join(path, _METHOD_REPORT)
    if not os.path.isfile(report):
        return None
    try:
        with open(report, "rb") as f:
            return decode_text(f.read())
    except OSError:
        return None


def acquisition_technique(path):
    """
    The separation technique a .D directory's method report declares.

    Reads the "Sample Inlet" field of ``acqmeth.txt`` ("GC" or "LC"), the
    instrument's authoritative record of whether the run is gas- or
    liquid-chromatography (an instrument descriptor naming GC/MS is taken as a
    secondary GC signal). This is read rather than inferred from the detectors,
    so a run is routed by what the method says, not by a detector tag.

    Args:
        path (str): Path of the .D directory.

    Returns:
        str: ``"GC"`` or ``"LC"``, or None when the report is absent or states
        neither.

    """
    text = _read_method_report(path)
    if text is None:
        return None
    match = _SAMPLE_INLET_RE.search(text)
    if match:
        inlet = match.group("inlet").upper()
        if inlet in ("GC", "LC"):
            return inlet
    # Scoped to the instrument banner, not the whole report. Searched over the
    # entire file, any path that happens to contain the letters (a method
    # filed under \METHODS\porting-from-GCMS\) declared the run GC, which
    # downgrades every UV detector class and makes the schema-required
    # injection volume mandatory. The banner is where the instrument names
    # itself, and it is the only place this claim is worth reading.
    banner = _INSTRUMENT_BANNER_RE.search(text)
    if banner and re.search(r"\bGC\b|GCMS", banner.group(0), re.IGNORECASE):
        # Inside the banner, the bare word is enough and is what a real report
        # gives: "7890A GC / 5975C MS" names the model between the two, so a
        # pattern requiring GC and MS to be adjacent misses it, and a GC-FID
        # run with no MS at all is still gas chromatography.
        return "GC"
    return None


def acquisition_modes(path):
    """
    The MS acquisition modes declared in a .D directory's method report.

    Reads the "Acquisition Mode" field of ``acqmeth.txt`` (for example
    ``Scan``, ``SIM``, or ``SIM/Scan``, the last being a simultaneous run).

    Args:
        path (str): Path of the .D directory.

    Returns:
        set: A subset of ``{"SIM", "Scan"}``, or None when the report is
        absent or carries no recognizable mode.

    """
    text = _read_method_report(path)
    if text is None:
        return None
    match = _ACQ_MODE_RE.search(text)
    if not match:
        return None
    mode_text = match.group("mode")
    modes = set()
    # ChemStation usually writes the abbreviations "SIM"/"Scan" (a simultaneous
    # run as "SIM/Scan"); tolerate a comma separator and the spelled-out
    # "Selected Ion Monitoring" so neither is mis-read.
    if "selected ion monitoring" in mode_text.lower():
        modes.add("SIM")
    for token in re.split(r"[\s/,]+", mode_text):
        low = token.lower()
        if low == "sim":
            modes.add("SIM")
        elif low == "scan":
            modes.add("Scan")
    return modes or None


def tag_acquisition_modes(path, datafiles):
    """
    Tags each MS DataFile with its ``acquisition_mode`` where determinable.

    A single-ion channel (one m/z column) is SIM. For a multi-column channel
    the method report decides: a pure SIM or pure Scan method tags all its MS
    files; a simultaneous SIM/Scan run tags the file ChemStation wrote the
    monitored ions to (named ``*SIM*.ms``) as SIM and the full-scan file as
    Scan. A channel that cannot be classified is left untagged.

    Args:
        path (str): Path of the .D directory.
        datafiles (list): The directory's DataFiles; MS entries are tagged in
            place.

    """
    ms_files = [datafile for datafile in datafiles
                if datafile.detector == "MS"]
    if not ms_files:
        return
    modes = acquisition_modes(path)
    for datafile in ms_files:
        mode = _classify_ms(datafile, modes)
        if mode:
            datafile.metadata["acquisition_mode"] = mode


def _classify_ms(datafile, modes):
    """``"SIM"`` or ``"Scan"`` for one MS channel, or None if undetermined."""
    try:
        single_ion = datafile.data.shape[1] == 1
    except Exception:
        single_ion = False  # a per-scan profile has no shared m/z grid
    if single_ion:
        return "SIM"
    if not modes:
        return None
    if modes == {"SIM"}:
        return "SIM"
    if modes == {"Scan"}:
        return "Scan"
    # Simultaneous SIM/Scan: ChemStation writes the monitored ions to a
    # *SIM*.ms file and the full scan to the other.
    return "SIM" if "sim" in datafile.name.lower() else "Scan"
