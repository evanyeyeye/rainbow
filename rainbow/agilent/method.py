"""
Read the per-injection method and sample sidecars of an Agilent .D directory.

Alongside the data channels, a .D holds:

    acq.macaml             the acquisition method (ACAML)
    SAMPLE.XML             the sample setup (name, dilution, method paths)
    AcqData/AcqMethod.xml  the MassHunter acquisition method report

This module distills those into a small, vendor-neutral metadata dict that
read() merges onto a DataDirectory: the operator, injection volume, column
temperature, flow rate, run time, the instrument modules, and the sample
amounts, and the compound each MRM transition of a MassHunter method is
named for. It is best-effort, so any field the sidecars do not carry, or a
sidecar that is missing or unreadable, simply contributes nothing.

It also tags each MS channel SIM, Scan or MRM from its own scans, or, where
they state nothing, from the ``acqmeth.txt`` instrument-control report; see
:func:`tag_acquisition_modes`; and puts what a ChemStation LC/MS method states
of each MS signal (its polarity, ionization, fragmentor, scan table and step,
and SIM ions with their compound names), from acq.macaml or the method
report, onto the signal's ``MSD<n>.MS`` file, by the number both state; see
:func:`ms_signals`, :func:`ms_detectors` and :func:`tag_ms_signals`. Where the
method states otherwise than the file records, the file's stays and the
method's is kept under ``method_disagrees``.
"""
import os
import re
import xml.etree.ElementTree as ET

import numpy as np

from rainbow.agilent import acaml, amx
# The .ms format's m/z step: a file's ion and the method's are one ion when
# they agree at the coarser of it and the method's own written precision.
from rainbow.agilent.chemstation import MS_MZ_STEP


# An instrument-module section is titled like "DAD (G7117B)": the module name
# followed by its model number in parentheses.
_MODULE_RE = re.compile(r"^\s*(.+?)\s*\(([^()]+)\)\s*$")

# ChemStation does not write that spelling. It names the section for the module
# ("Quat. Pump", "DAD", "HiP Sampler") and puts the model in the section's ID:
#
#     <Section><Name>Quat. Pump</Name><ID>G4204A</ID>
#
# Every other section under the acquisition method carries a settings-group ID
# instead ("StopTime", "Timetable", "SolventComposition_Channel"), so the model
# is what tells a module apart from a settings group. Agilent module numbers
# are four digits, usually with a letter on each side: G4204A, G1316C, 5977B.
_MODEL_ID_RE = re.compile(r"^[A-Z]{0,2}\d{4}[A-Z]{0,2}$")

# The MassHunter acquisition method report. Its device sections are not XML
# children but whole XML documents held as escaped text, each a flat list of
# <Section> rows: TableID, RowIndex, ParameterID, ParameterValue. One table row
# (TableID + RowIndex) is one MRM transition, its fields spread over several
# <Section>s with ParameterIDs such as "CompoundName",
# "Report__Header_PrecursorIon", "Report__Header_ProductIon" and
# "Collision_Energy"; the prefix varies with the device, the ending does not.
_MASSHUNTER_METHOD = os.path.join("AcqData", "AcqMethod.xml")

# The ParameterID endings of an MRM transition's fields, lowercased.
_ION_FIELDS = {
    "compound": "compoundname",
    "precursor_mz": "precursorion",
    "product_mz": "production",
    "collision_energy": "collision_energy",
}

# The ChemStation instrument-control report, which names the MS acquisition
# mode ("Scan", "SIM", or "SIM/Scan") in its MS Information section.
_METHOD_REPORT = "acqmeth.txt"

# The "Acquisition Mode : <mode>" line of that report.
_ACQ_MODE_RE = re.compile(
    r"^\s*Acquisition Mode\s*:\s*(?P<mode>.+?)\s*$",
    re.MULTILINE | re.IGNORECASE)

# The banner a Chemstation method report opens with. The instrument names
# itself on this line and nowhere else ("INSTRUMENT CONTROL PARAMETERS:
# 5977B GCMS"), so the window is that one line: the rule, the blank, and the
# method path that follow it are not the instrument's own claim. In the real
# layout the path is line 4, so any window wider than a line reads
# \METHODS\porting-from-GCMS\ as the instrument declaring itself GC, which
# downgrades every UV detector class and makes the schema-required injection
# volume mandatory.
_INSTRUMENT_BANNER_RE = re.compile(
    r"INSTRUMENT\s+CONTROL\s+PARAMETERS\s*:[^\r\n]*", re.IGNORECASE)

# The "Sample Inlet : GC" / "Sample Inlet : LC" line names the separation
# technique (gas vs liquid chromatography), the instrument's own record of it.
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


def read_acq_method(path):
    """
    The .D directory's acq.macaml, parsed (:func:`acaml.read`), or None when
    it is missing or unreadable. Read once and passed to
    :func:`parse_injection_metadata` and :func:`ms_signals`.
    """
    acq_path = os.path.join(path, "acq.macaml")
    if not os.path.isfile(acq_path):
        return None
    try:
        return acaml.read(acq_path)
    except (ET.ParseError, ValueError, LookupError, OSError):
        # A sidecar that is missing or unreadable contributes nothing, which
        # includes one whose XML declaration names an encoding Python does not
        # have: that raises LookupError out of the parser, and taking the whole
        # read down over an optional metadata file is the wrong failure mode.
        return None


_UNREAD = object()      # acq.macaml not yet read: the function reads it


def parse_injection_metadata(path, acq=_UNREAD):
    """
    Reads per-injection method and sample metadata from a .D directory.

    Args:
        path (str): Path of the .D directory.
        acq: its acq.macaml as :func:`read_acq_method` gives it, when already
            read; read here otherwise.

    Returns:
        dict: Any of ``operator``, ``modules``, ``injection_volume``,
        ``column_temperature``, ``flow_rate``, ``run_time``, ``dilution``,
        ``multiplier``, ``sample_amount``, ``acq_method``, and
        ``monitored_compounds`` that the sidecars supply. Quantities are
        ``{"value": float, "unit": str}``. ``monitored_compounds`` lists the
        MRM transitions a MassHunter method names a compound for, in its
        order, each ``{"compound": str, "precursor_mz": float,
        "product_mz": float, "collision_energy": float}``, the last two None
        where the method gives none; collision energy is in volts.

    """
    metadata = {}
    metadata.update(_from_acq_method(read_acq_method(path) if acq is _UNREAD else acq))
    metadata.update(_from_sample_xml(path))
    metadata.update(_from_masshunter_method(path))
    return metadata


def _from_acq_method(doc):
    """Method settings from acq.macaml (`doc`: read_acq_method's)."""
    if doc is None:
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


def _from_masshunter_method(path):
    """Monitored-ion compound names from MassHunter's AcqData/AcqMethod.xml."""
    report = os.path.join(path, _MASSHUNTER_METHOD)
    if not os.path.isfile(report):
        return {}
    rows = {}
    try:
        for outer in ET.parse(report).iter():
            text = (outer.text or "").lstrip()
            if not text.startswith("<?xml") or "Section" not in text:
                continue
            for section in ET.fromstring(text.encode("utf-8")).iterfind(
                    ".//{*}Section"):
                fields = {child.tag.rsplit("}", 1)[-1]:
                          (child.text or "").strip() for child in section}
                table = fields.get("TableID")
                parameter = fields.get("ParameterID")
                if table and parameter:
                    row = rows.setdefault((table, fields.get("RowIndex")), {})
                    row[parameter.lower()] = fields.get("ParameterValue")
    except (ET.ParseError, ValueError, LookupError, OSError):
        return {}

    compounds = []
    for row in rows.values():
        ion = {}
        for key, ending in _ION_FIELDS.items():
            value = next((value for parameter, value in row.items()
                          if parameter.endswith(ending) and value), None)
            if key != "compound":
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    value = None
            ion[key] = value
        if ion["compound"] and ion["precursor_mz"] is not None:
            compounds.append(ion)
    return {"monitored_compounds": compounds} if compounds else {}


def _modules(sections):
    """The instrument modules, read from the method's section headers."""
    acquisition = _section(sections, "Acquisition Method")
    container = acquisition["sections"] if acquisition else sections
    modules = []
    for section in container:
        name = (section.get("name") or "").strip()
        match = _MODULE_RE.match(name)
        if match:
            modules.append(
                {"name": match.group(1).strip(),
                 "model": match.group(2).strip()})
            continue
        model = (section.get("id") or "").strip()
        if name and model and model != name and _MODEL_ID_RE.match(model):
            modules.append({"name": name, "model": model})
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
    liquid-chromatography. Failing that, the report's opening banner is read,
    and an instrument that names itself GC there ("7890A GC / 5975C MS", and
    the bare word is enough) is taken as a secondary GC signal. This is read
    rather than inferred from the detectors, so a run is routed by what the
    method says, not by a detector tag.

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
    # Scoped to the instrument banner line, not the whole report: that is where
    # the instrument names itself, and it is the only place this claim is worth
    # reading.
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


def state_run(path, datafiles, metadata):
    """
    States what a run's method and sample sidecars, and its MS files' own
    scans, say of it: the one step every Agilent run read goes through after
    its data files are read, a .D and an OpenLab .sirslt alike.

    The directory's metadata gains, where it does not state them already,
    what :func:`parse_injection_metadata` reads (acq.macaml, SAMPLE.XML,
    AcqData/AcqMethod.xml), what an OpenLab acquisition method (.amx) in
    the folder states (:func:`rainbow.agilent.amx.read`), and the technique
    the method report declares (:func:`acquisition_technique`). Each MS
    DataFile is tagged with its acquisition mode
    (:func:`tag_acquisition_modes`) and with what the method states of its
    signal (:func:`tag_ms_signals`). A sidecar the run
    does not hold states nothing.

    Args:
        path (str): The run's folder, laid out as a .D: a .D itself, or the
            .D-shaped view of a .sirslt (:func:`rainbow.agilent.sirslt.read`).
        datafiles (list): The run's DataFiles, tagged in place; empty for a
            listing (``read_metadata``), which states the metadata alone.
        metadata (dict): The directory's metadata, filled in place.

    Returns:
        dict: ``metadata``.

    """
    acq = read_acq_method(path)          # acq.macaml, parsed once
    for key, value in parse_injection_metadata(path, acq).items():
        metadata.setdefault(key, value)
    # An OpenLab acquisition method (.amx) in the folder, in the same keys.
    for key, value in amx.read_run(path).items():
        metadata.setdefault(key, value)
    # Tag each MS channel SIM or Scan from its scans, else the acquisition
    # method, so a SIM run (its monitored ions) is told from a full scan.
    tag_acquisition_modes(path, datafiles)
    # What the method states of each MS signal (polarity, fragmentor, SIM
    # ions and their compound names), onto the file holding it.
    tag_ms_signals(path, datafiles, acq)
    # The separation technique the method declares (gas vs liquid
    # chromatography), so an export routes by what the instrument says
    # rather than guessing from the detectors.
    technique = acquisition_technique(path)
    if technique:
        metadata.setdefault('technique', technique)
    return metadata


def tag_acquisition_modes(path, datafiles):
    """
    Tags each MS DataFile with its ``acquisition_mode`` where determinable,
    and ``acquisition_mode_from``, what said it.

    A file's own scans decide (``'scans'``): an .ms file's scan records
    (chemstation.parse_ms) or MassHunter's (MSScan.bin), when every scan
    states the same one of SIM, Scan or MRM; a file whose scans are of both
    kinds is ``'mixed'`` (:func:`_tag_interleaved`). The scans are the data,
    so the method report never overwrites them: where it states the other
    mode, the file keeps its scans' and ``method_disagrees`` holds the
    report's (``{'acquisition_mode': 'SIM'}``).

    Where the scans state nothing, the method report (acqmeth.txt) decides
    (``'method report'``): a pure SIM or pure Scan method tags all its MS
    files. A simultaneous SIM/Scan run's report does not say which file is
    which, so ChemStation's naming habit is used (the monitored ions in a
    ``*SIM*.ms`` file), and said (``'file name'``). With neither, a channel
    of one m/z column is SIM (``'one m/z column'``). Otherwise it is left
    untagged.

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
        if _tag_interleaved(datafile):
            datafile.metadata["acquisition_mode_from"] = "scans"
            continue
        stated = _mode_of_scans(datafile) \
            or datafile.metadata.get("acquisition_mode")
        reported, how = _classify_ms(datafile, modes)
        if stated:
            datafile.metadata["acquisition_mode"] = stated
            datafile.metadata["acquisition_mode_from"] = "scans"
            if how == "method report" and reported != stated:
                _disagree(datafile, "acquisition_mode", reported)
        elif reported:
            datafile.metadata["acquisition_mode"] = reported
            datafile.metadata["acquisition_mode_from"] = how


def _mode_of_scans(datafile):
    """The one mode every scan of a file states (``scans['scan_type']``):
    ``'SIM'``, ``'Scan'`` or ``'MRM'``, else None."""
    types = (datafile.metadata.get("scans") or {}).get("scan_type")
    if types is None or not len(types):
        return None
    types = np.asarray(types).astype(str)
    first = str(types[0])
    if first in ("SIM", "Scan", "MRM") and (types == first).all():
        return first
    return None


def _disagree(datafile, key, value):
    """Keeps ``value``, what the method states of ``key`` where the file's
    own record says otherwise, under ``metadata['method_disagrees']``."""
    datafile.metadata.setdefault("method_disagrees", {})[key] = value


def _tag_interleaved(datafile):
    """
    Tags a file whose own scans are of both kinds, Scan and SIM (a MassHunter
    acquisition's one MSScan.bin holding a simultaneous SIM/Scan run), from
    those scans: ``acquisition_mode`` ``'mixed'``, and ``acquisition_modes``
    the mode of each scan program entry (``scan_method``), ``{1: 'Scan',
    2: 'SIM'}``; each scan's own kind stays in ``scans``. Returns whether it
    did.
    """
    scans = datafile.metadata.get("scans") or {}
    monitoring = scans.get("monitoring")
    if monitoring is None:
        return False
    monitoring = np.asarray(monitoring, dtype=bool)
    if monitoring.all() or not monitoring.any():
        return False
    datafile.metadata["acquisition_mode"] = "mixed"
    methods = scans.get("scan_method")
    if methods is not None:
        datafile.metadata["acquisition_modes"] = {
            int(m): ("SIM" if monitoring[np.asarray(methods) == m].all()
                     else "Scan" if not monitoring[np.asarray(methods) == m].any()
                     else "mixed")
            for m in np.unique(methods)}
    return True


def _classify_ms(datafile, modes):
    """(``"SIM"`` or ``"Scan"``, what said it) for one MS channel from the
    method report's modes, else from its one column, or (None, None)."""
    if modes == {"SIM"}:
        return "SIM", "method report"
    if modes == {"Scan"}:
        return "Scan", "method report"
    if modes:
        # Simultaneous SIM/Scan: ChemStation writes the monitored ions to a
        # *SIM*.ms file and the full scan to the other.
        return ("SIM" if "sim" in datafile.name.lower() else "Scan"), \
            "file name"
    try:
        single_ion = datafile.data.shape[1] == 1
    except Exception:
        single_ion = False  # a per-scan profile has no shared m/z grid
    if single_ion:
        return "SIM", "one m/z column"
    return None, None


# A ChemStation LC/MS signal's data file is named MSD<n>.MS, n the number of
# the method's [Signal n] it holds. Its header's description names the
# detector ("MSD1, Initial Ions=204.30"), the same in each signal's file, and
# the first signal's ions or range, not this file's.
_MS_SIGNAL_FILE_RE = re.compile(r"^MSD(\d+)\.MS$", re.IGNORECASE)
_MS_HEADER_DETECTOR_RE = re.compile(r"^MSD(\d+)\s*,")
# Where an .ms file's header keeps that description: a length byte, then the
# text (chemstation.read_header reads its other strings the same way).
_MS_HEADER_DESCRIPTION = 0x140

# The method report as run, in the .D: acq.txt (OpenLab ChemStation), else the
# ACQ.TXT of the ACQ.M copy older ChemStation keeps there. Both are the same
# text report, their MS section laid out alike.
_MS_REPORTS = (("acq.txt",), ("ACQ.M", "ACQ.TXT"))

# The polarity words a ChemStation MS signal states, in rainbow's spelling
# (Waters' too); any other word is not read as a polarity.
_POLARITY_WORDS = {"positive": "+", "negative": "-"}

_SIGNAL_RE = re.compile(r"^\s*\[Signal\s+(\d+)\]\s*$", re.IGNORECASE)
# A report table's rule line, under its two header lines: " -------|------|".
_RULE_RE = re.compile(r"^\s*-+(\|-+)+\s*$")
# A report heading's underline: "-------" or "----- -------", no bars.
_UNDERLINE_RE = re.compile(r"^\s*-+(\s+-+)*\s*$")
_SETTING_RE = re.compile(r"^\s*([A-Za-z][A-Za-z .\-]*?)\s*:\s*(.*?)\s*$")
# A report table's column heads (its two header lines joined, letters only),
# as acq.macaml's ids: "SIM" over "Ion", "Frag-" over "mentor".
_REPORT_HEADS = {"simion": "SIMIon", "fragmentor": "Fragmentor",
                 "compoundname": "CompoundName", "masslow": "MassRangeLow",
                 "rangehigh": "MassRangeHigh", "stepsize": "Stepsize",
                 "timemin": "Time(min)"}
_MS_DETECTOR_TITLE = "Mass Spectrometer Detector"



def ms_signals(path, acq=_UNREAD):
    """
    What a ChemStation LC/MS method states of each MS signal of its one MS
    detector.

    Read from ``acq.macaml``, else from the method report as run
    (``acq.txt``, or the ``ACQ.M/ACQ.TXT`` older ChemStation writes; UTF-8 or
    UTF-16, see :func:`decode_text`). Only what the method states is given.
    A method of several MS detectors states its signals per detector: see
    :func:`ms_detectors`.

    Args:
        path (str): Path of the .D directory.
        acq: its acq.macaml as :func:`read_acq_method` gives it, when already
            read; read here otherwise.

    Returns:
        dict: ``{signal number: settings}`` for each active signal, each
        settings dict holding any of ``polarity`` (``"+"`` or ``"-"``),
        ``ionization_mode`` (as written, ``"AJS-ES"``), ``fragmentor`` (V,
        where every row of the signal's table states the same one; each row's
        own is in its ``scan_parameters`` row or ``monitored_ions`` entry),
        ``mz_step`` (a Scan signal's step size, where every row states the
        same one), ``scan_parameters`` (a Scan signal's table rows, each any
        of ``time``, ``mz_low``, ``mz_high``, ``fragmentor``, ``mz_step``) and
        ``monitored_ions`` (a SIM signal's ions in the method's order, each
        ``{"mz": float, "fragmentor": float or None, "compound": str or
        None}``). Empty when neither source has an MS section, or it names
        more than one MS detector.
    """
    detectors = _ms_detectors(path, acq)
    if len(detectors) != 1:
        return {}
    return {n: _public(s) for n, s in detectors[0]["signals"].items()}


def ms_detectors(path, acq=_UNREAD):
    """
    What a ChemStation LC/MS method states of each of its MS detectors, in
    the method's order.

    Args:
        path (str): Path of the .D directory.
        acq: as for :func:`ms_signals`.

    Returns:
        list: One ``{"name": str or None, "signals": {signal number:
        settings}}`` per MS detector section, ``name`` the module its heading
        names (``"G6135B"``), the settings as :func:`ms_signals` gives them.

    UNVERIFIED for more than one detector: no method report or acq.macaml of
    two MS detectors has been seen, so splitting the report at each heading
    that names a module, and the acq.macaml at each "Mass Spectrometer
    Detector" section, follows the one-detector layout, not a seen file.
    """
    return [{"name": d["name"],
             "signals": {n: _public(s) for n, s in d["signals"].items()}}
            for d in _ms_detectors(path, acq)]


def _public(settings):
    return {k: v for k, v in settings.items() if not k.startswith("_")}


def tag_ms_signals(path, datafiles, acq=_UNREAD):
    """
    Puts each MS signal's settings (:func:`ms_signals`) onto the metadata of
    the data file that holds it, filling only keys the file does not state
    itself, and ``method_signal``, the signal's number.

    ``MSD<n>.MS`` holds ``[Signal n]``, the number both state. With several MS
    detectors, the detector is taken to be the one its header names
    (``MSD<k>``, the k-th detector section); a file whose header names none
    is left untagged then. That mapping is UNVERIFIED: no run with two MS
    detectors has been seen, so it rests on the header naming its detector
    ("MSD1, ...") in the one-detector runs. A file named otherwise (a GC/MS
    ``data.ms``) holds the method's one signal, where it has one.

    What the file records is a check, never the pairing: where a SIM signal's
    ions are not the ions the file recorded, or a Scan signal's range does
    not hold them, nothing of the signal is put on the file; its number and
    whole settings (a Scan signal's with its ``scan_range``) are kept under
    ``method_disagrees`` (``signal``, ``settings``, and ``detector`` where
    there are several), and the file's own ions stay its m/z labels. Ions
    are compared at the coarser of the .ms format's m/z step
    (:data:`rainbow.agilent.chemstation.MS_MZ_STEP`) and the method's written
    precision. Where the file states a setting (its polarity) that the method
    states otherwise, the file's stays and the method's is kept there too.

    Args:
        path (str): Path of the .D directory.
        datafiles (list): The directory's DataFiles; MS entries are tagged in
            place.
        acq: as for :func:`ms_signals`.

    """
    detectors = _ms_detectors(path, acq)
    if not detectors:
        return
    ms_files = [f for f in datafiles if f.detector == "MS"]
    for datafile in ms_files:
        n = _signal_of(path, datafile, detectors, len(ms_files))
        if n is None:
            continue
        k, number = n
        settings = detectors[k]["signals"][number]
        span = settings.get("_scan_range")
        if ("monitored_ions" in settings and not _ions_agree(datafile, settings)) \
                or (span is not None and not _range_holds(datafile, span, settings)):
            # The file did not record what the signal names: none of the
            # signal's settings is put on it; the whole signal is kept apart.
            kept = _public(settings)
            if span is not None:
                kept["scan_range"] = span
            _disagree(datafile, "signal", number)
            _disagree(datafile, "settings", kept)
            if len(detectors) > 1:
                _disagree(datafile, "detector", k + 1)
            continue
        datafile.metadata["method_signal"] = number
        if len(detectors) > 1:
            datafile.metadata["method_detector"] = k + 1
        for key, value in _public(settings).items():
            if key in datafile.metadata and datafile.metadata[key] != value:
                _disagree(datafile, key, value)
                continue
            datafile.metadata.setdefault(key, value)


def _signal_of(path, datafile, detectors, ms_count):
    """(detector index, signal number) of the signal a data file holds
    (tag_ms_signals), or None."""
    match = _MS_SIGNAL_FILE_RE.match(os.path.basename(datafile.name))
    if len(detectors) == 1:
        k = 0
    else:
        k = _header_detector(os.path.join(path, datafile.name))
        if k is None or not 0 <= k < len(detectors):
            return None
    signals = detectors[k]["signals"]
    if match:
        number = int(match.group(1))
        return (k, number) if number in signals else None
    if len(signals) == 1 and ms_count == 1:
        return k, next(iter(signals))
    return None


def _header_detector(file_path):
    """The index of the MS detector an .ms file's header names (``MSD2`` is
    1), or None."""
    try:
        with open(file_path, "rb") as f:
            f.seek(_MS_HEADER_DESCRIPTION)
            length = f.read(1)
            text = f.read(length[0]).decode("latin-1") if length else ""
    except (OSError, IndexError):
        return None
    match = _MS_HEADER_DETECTOR_RE.match(text)
    return int(match.group(1)) - 1 if match else None


def _labels(datafile):
    try:
        return sorted(float(x) for x in datafile.ylabels)
    except (TypeError, ValueError):
        return None


def _step(settings):
    """The step at which a file's m/z and the method's are compared: the
    coarser of the .ms format's and the method's written precision."""
    return max(MS_MZ_STEP, settings.get("_written_step") or 0.0)


def _same_mz(a, b, step):
    return round(a / step) == round(b / step)


def _ions_agree(datafile, settings):
    """Whether a SIM signal's ions are the ions the file recorded."""
    labels = _labels(datafile)
    ions = sorted(e["mz"] for e in settings.get("monitored_ions", []))
    if labels is None or len(ions) != len(labels):
        return False
    step = _step(settings)
    return all(_same_mz(a, b, step) for a, b in zip(ions, labels))


def _range_holds(datafile, span, settings):
    """Whether a Scan signal's m/z range holds every m/z the file recorded."""
    labels = _labels(datafile)
    if not labels:
        return True
    step = _step(settings)
    return round(labels[0] / step) >= round(span[0] / step) and \
        round(labels[-1] / step) <= round(span[1] / step)


def _ms_detectors(path, acq):
    """Each MS detector's ``{"name", "signals"}``, its signals with private
    keys (``_scan_range``, ``_written_step``), the active ones only."""
    doc = read_acq_method(path) if acq is _UNREAD else acq
    detectors = _ms_detectors_from_acaml(doc) if doc is not None else None
    if not detectors:
        detectors = _ms_detectors_from_report(path)
    out = []
    for detector in detectors or []:
        signals = {n: s for n, s in detector["signals"].items() if s}
        out.append({"name": detector["name"], "signals": signals})
    return [d for d in out if d["signals"]]


def _decimals(text):
    """How many decimals a number is written with ("1247.60": 2)."""
    text = str(text or "").strip()
    return len(text.split(".", 1)[1]) if "." in text else 0


def _settings_of(fields, rows, sim):
    """One signal's settings from its fields ({id: value}) and its table rows
    ([{id: value}]), ids as acq.macaml writes them; `sim`: its table is a SIM
    table."""
    out = {}
    polarity = _POLARITY_WORDS.get(str(fields.get("Polarity") or "").strip().lower())
    if polarity:
        out["polarity"] = polarity
    ionization = str(fields.get("IonizationMode") or "").strip()
    if ionization:
        out["ionization_mode"] = ionization
    if sim:
        rows = [row for row in rows if _float(row.get("SIMIon")) is not None]
        ions = [{"mz": _float(row["SIMIon"]), "fragmentor": _float(row.get("Fragmentor")),
                 "compound": str(row.get("CompoundName") or "").strip() or None}
                for row in rows]
        if ions:
            out["monitored_ions"] = ions
            out["_written_step"] = 10.0 ** -min(
                _decimals(row["SIMIon"]) for row in rows)
    else:
        lows = [_float(row.get("MassRangeLow")) for row in rows]
        highs = [_float(row.get("MassRangeHigh")) for row in rows]
        if rows and None not in lows + highs:
            out["_scan_range"] = (min(lows), max(highs))
            out["_written_step"] = 10.0 ** -min(
                _decimals(row.get(key)) for row in rows
                for key in ("MassRangeLow", "MassRangeHigh"))
        table = []
        for row in rows:
            entry = {name: _float(row.get(key)) for name, key in (
                ("time", "Time(min)"), ("mz_low", "MassRangeLow"),
                ("mz_high", "MassRangeHigh"), ("fragmentor", "Fragmentor"),
                ("mz_step", "Stepsize"))}
            entry = {k: v for k, v in entry.items() if v is not None}
            if entry:
                table.append(entry)
        if table:
            out["scan_parameters"] = table
        steps = {_float(row.get("Stepsize")) for row in rows}
        if len(steps) == 1 and None not in steps:
            out["mz_step"] = steps.pop()
    frags = {_float(row.get("Fragmentor")) for row in rows}
    if len(frags) == 1 and None not in frags:
        out["fragmentor"] = frags.pop()
    return out


def _float(text):
    """Text as a float, or None."""
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def _module_name(title):
    """The module a detector heading names ("Mass Spectrometer Detector
    (G6135B)": "G6135B"), or None."""
    match = re.search(r"\(([^)]*)\)\s*$", title or "")
    return match.group(1).strip() or None if match else None


def _ms_detectors_from_acaml(doc):
    """_ms_detectors' detectors from acq.macaml (`doc`: read_acq_method's);
    None when it has no MS detector section."""
    acquisition = _section(doc["sections"], "Acquisition Method")
    container = acquisition["sections"] if acquisition else doc["sections"]
    detectors = [s for s in container
                 if (s.get("name") or "").startswith(_MS_DETECTOR_TITLE)]
    if not detectors:
        return None
    out = []
    for detector in detectors:
        signals = _section(detector["sections"], "Signals")
        found = {}
        for section in (signals or {}).get("sections", []):
            match = _SIGNAL_RE.match(section.get("name") or "")
            if not match:
                continue
            fields = {p["id"]: p["value"] for p in section["parameters"] if p.get("id")}
            tables = section["tables"] + [t for s in section["sections"] for t in s["tables"]]
            tables = [t for t in tables if t.get("id") in ("SimParameters", "ScanParameters")]
            rows = [{p["id"]: p["value"] for p in row if p.get("id")}
                    for t in tables for row in t["rows"]]
            sim = any(t["id"] == "SimParameters" for t in tables)
            found[int(match.group(1))] = _settings_of(fields, rows, sim)
        out.append({"name": _module_name(detector.get("name")), "signals": found})
    return out


def _ms_detectors_from_report(path):
    """_ms_detectors' detectors from the method report's MS section; None
    when no report has one. Each detector's part starts at its heading naming
    its module ("Mass Spectrometer Detector (G6135B)"); a report with only
    the section's banner title has one detector, from there."""
    text = None
    for parts in _MS_REPORTS:
        report = _find_any_case(path, parts)
        if report is None:
            continue
        try:
            with open(report, "rb") as f:
                text = decode_text(f.read())
        except OSError:
            continue
        break
    if text is None:
        return None
    lines = text.splitlines()
    titled = [i for i, line in enumerate(lines)
              if line.strip().startswith(_MS_DETECTOR_TITLE)]
    if not titled:
        return None
    starts = [i for i in titled if lines[i].strip() != _MS_DETECTOR_TITLE] \
        or titled[:1]
    out = []
    for at, start in enumerate(starts):
        end = starts[at + 1] if at + 1 < len(starts) else len(lines)
        out.append({"name": _module_name(lines[start].strip()),
                    "signals": _report_signals(lines, start, end)})
    return out


def _report_signals(lines, start, end):
    """The signals of one MS detector's part of a method report, the lines
    ``start`` (its heading) to ``end``."""
    out = {}
    current, fields, rows, sim = None, {}, [], False
    i = start + 1
    while i < end:
        line = lines[i]
        if "END OF MS ACQUISITION PARAMETERS" in line.upper():
            break
        signal = _SIGNAL_RE.match(line)
        if signal:
            if current is not None:
                out[current] = _settings_of(fields, rows, sim)
            current, fields, rows, sim = int(signal.group(1)), {}, [], False
        elif current is not None and line[:1].strip() and i + 1 < len(lines) \
                and _UNDERLINE_RE.match(lines[i + 1]):
            # A heading at the margin, underlined ("Spray Chamber" over
            # "----- -------"): the MS section's next part; the signals end.
            break
        elif current is not None and _RULE_RE.match(line) and i >= 2:
            table, i = _report_table(lines, i)
            rows.extend(table)
            continue
        elif current is not None:
            if line.strip().lower() == "sim parameters":
                sim = True
            setting = _SETTING_RE.match(line)
            if setting:
                fields[setting.group(1).replace(" ", "")] = setting.group(2)
        i += 1
    if current is not None:
        out[current] = _settings_of(fields, rows, sim)
    return out


def _report_table(lines, at):
    """(rows, the index of the line after the table) of the report table
    whose rule line is ``lines[at]``: each row ``{id: text}`` for the heads
    _REPORT_HEADS names. A row's words go to the column they start in (the
    rule's bars cut the columns), so a name running past its column's bar
    stays whole. Its rows are the indented lines after the rule, blank lines
    between them (a SIM table's groups) included; it ends at a line at the
    margin (the next signal, a heading) or the report's end."""
    rule = lines[at]
    cuts = [j for j, c in enumerate(rule) if c == "|"]

    def column(pos):
        return sum(1 for c in cuts if c < pos)

    def cells(line):
        out = [[] for _ in range(len(cuts) + 1)]
        for word in re.finditer(r"[^\s|]+", line):
            out[column(word.start())].append(word)
        return [line[w[0].start():w[-1].end()] if w else "" for w in out]

    heads = [re.sub(r"[^a-z]", "", (top + " " + bottom).lower())
             for top, bottom in zip(cells(lines[at - 2]), cells(lines[at - 1]))]
    ids = [_REPORT_HEADS.get(h) for h in heads]
    rows = []
    i = at + 1
    while i < len(lines) and (not lines[i].strip() or lines[i][:1].isspace()):
        if lines[i].strip() and not _RULE_RE.match(lines[i]):
            rows.append({k: v for k, v in zip(ids, cells(lines[i])) if k and v})
        i += 1
    return rows, i


def _find_any_case(path, parts):
    """The file at ``path``/``parts...``, each part's name matched in any
    case, or None."""
    here = path
    for part in parts:
        try:
            names = os.listdir(here)
        except OSError:
            return None
        hit = next((n for n in names if n.lower() == part.lower()), None)
        if hit is None:
            return None
        here = os.path.join(here, hit)
    return here if os.path.isfile(here) else None
