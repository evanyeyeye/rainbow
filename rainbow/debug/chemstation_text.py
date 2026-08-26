"""
Parser for the ChemStation / MassHunter ``.D`` text and report sidecars.

A vendor run directory ships several human-readable report files that rainbow's
data parsers never touch. They are heterogeneous - different encodings and
different layouts - so this module dispatches on the file name to a sub-parser,
each of which returns a ``kind``-tagged lossless structure. :func:`canonical`
then promotes the identifier-bearing fields (data file, method, instrument,
operator, save time, module serials, vial position, acquisition time) to the
shared canonical vocabulary.

Sub-formats handled (see ``docs/source/debug/formats/chemstation_text.md``):

================  ========  =================================================
file              encoding  content
================  ========  =================================================
runstart.txt      UTF-8     ChemStation ``CP`` run-variable dump
acq.txt           UTF-16    instrument-parameter report (header + sections)
acqmeth.txt       UTF-16    method instrument-control report (model in banner)
rtlrep.txt        UTF-8     retention-time-lock report
RUN.LOG           UTF-16    paired-line event log (module:serial, timestamps)
Audit.txt         UTF-8     method-folder audit trail (save events, inspect-only)
method.txt        UTF-8     MassHunter "Additional Information" method summary
MSPARMS.txt       UTF-8     MSD parameter report (identity header + numeric body)
report.txt        UTF-8     ChemStation area/report (two-column identity header)
report*.csv       UTF-8     same report exported as quoted Key,Value CSV
acq_methhist.txt  UTF-8     acquisition method-history / audit summary
scstate.txt       UTF-8     SmartCard "SC State Report" (instrument serial, Key=Value)
tic_*.csv/.tsv    UTF-8     chromatogram dump - header line only (data is numeric)
rpthead.txt       ASCII     report-header template (inspect-only)
================  ========  =================================================
"""
import csv
import io
import os
import re

from rainbow.debug._util import decode_text

NAME = "chemstation_text"

# Exact basenames (lowercased) this module claims, mapped to a sub-kind.
_EXACT = {
    "runstart.txt": "runstart",
    "acq.txt": "instrument_report",
    "acqmeth.txt": "instrument_report",
    "rtlrep.txt": "rtl_report",
    "run.log": "run_log",
    "audit.txt": "audit",
    "method.txt": "method_info",
    "msparms.txt": "msparms",
    "report.txt": "report_text",
    "acq_methhist.txt": "methhist",
    "scstate.txt": "scstate",
    "rpthead.txt": "report_header_template",
}

# MSPARMS.txt identity-header labels (lowercased) -> canonical field.
_MSPARMS_FIELDS = {
    "file": "data_file",
    "operator": "operator",
    "date acquired": "acquired",
    "instrument": "instrument",
    "sample name": "sample",
}

# report.txt identity-header labels (lowercased) -> canonical field. The header
# is a fixed-width two-column block (right-aligned colons), so values are read up
# to the next 2-space gap; the wrapped Method/Sequence paths and the numeric peak
# table below are left in the lossless body.
_REPORT_TEXT_FIELDS = {
    "sample name": "sample",
    "acq. operator": "operator",
    "acq. instrument": "instrument",
    "injection date": "acquired",
    "location": "vialpos",
}

# report*.csv ("Key","Value") labels (lowercased) -> canonical field.
_REPORT_CSV_FIELDS = {
    "sample name": "sample",
    "data file": "data_file",
    "acq. instrument": "instrument",
    "acq. method": "method",
    "acq. operator": "operator",
    "injection date": "acquired",
}

# One "Label : value" cell of a report.txt line; the value ends at the next
# 2-space gap (the start of the second column) or the line end.
_REPORT_PAIR = re.compile(r"([A-Za-z][\w. ]*?)\s*:\s+(\S.*?)(?=\s{2,}\S|\s*$)")

# A "Key = Value" line of scstate.txt's configuration blocks.
_EQKV = re.compile(r"^\s*(?P<key>[A-Za-z][\w ./\[\]-]*?)\s*=\s*(?P<value>\S.*?)\s*$")

# A "key : value" report line: non-greedy key, a colon followed by >=1 space,
# then the value. Non-greedy + the required space after the colon means embedded
# path colons (``C:\``) and clock colons (``10:11``) are never split on.
_KV = re.compile(r"^\s*(?P<key>.*?\S)\s*:\s+(?P<value>\S.*?)\s*$")

# A ChemStation CP variable line, e.g. ``Methfile (_methfile$) = HP-5MS...M``
# or ``Datafile(,_datafile$) = sample_mix .D``.
_CPVAR = re.compile(
    r"^\s*(?P<label>.*?)\(\s*,?\s*(?P<var>[^)]*?)\s*\)\s*=\s*(?P<value>.*?)\s*$")

# Trailing ``HH:MM:SS MM/DD/YY`` timestamp on a RUN.LOG message line.
_LOGTIME = re.compile(r"(?P<time>\d{1,2}:\d{2}:\d{2})\s+(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s*$")

# A ``MODULE:SERIAL`` token inside a RUN.LOG message, e.g. ``G4212A:DEAA900001``.
_MODSERIAL = re.compile(r"\b(?P<module>[A-Z]\d{3,4}[A-Z]?):(?P<serial>[A-Z0-9]{4,})\b")

# A RUN.LOG framing line: only hex tokens separated by whitespace.
_HEXLINE = re.compile(r"^\s*[0-9a-fA-F]+(?:\s+[0-9a-fA-F]+)+\s*$")

# A weekday-stamped local time, e.g. ``Tue Dec 17 10:13:52 2019``.
_WEEKDAY = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b")


def _is_tic(low):
    """True for ``tic*.csv``/``.tsv`` (the chromatogram dump; only its first
    line is read, so the tab variant is harmless)."""
    return low.startswith("tic") and (low.endswith(".csv") or low.endswith(".tsv"))


def _is_report_csv(low):
    """True for ``report*.csv`` (the quoted Key,Value report). Restricted to
    ``.csv``: the reader is comma-delimited, so a true ``.tsv`` is not claimed."""
    return low.startswith("report") and low.endswith(".csv")


def matches(name):
    """Returns True if ``name`` is a ChemStation text/report sidecar."""
    low = name.lower()
    if low in _EXACT:
        return True
    return _is_tic(low) or _is_report_csv(low)


def _kind(name):
    low = name.lower()
    if low in _EXACT:
        return _EXACT[low]
    if _is_report_csv(low):
        return "report_csv"
    return "tic_header"


def _read(path):
    with open(path, "rb") as f:
        return decode_text(f.read())


def _is_banner(line):
    """True for a section rule line: only ``=`` or only ``-`` (plus the spaces
    that separate underlined multi-word titles). Timetable rules carry ``|`` and
    are deliberately excluded so they stay data, not section headers."""
    s = line.strip()
    if not s or set(s) - {"=", "-", " "}:
        return False
    return len(s.replace(" ", "")) >= 3


def _is_title(s):
    """True if ``s`` looks like a section title (a short phrase) rather than a
    columnar data row. Titles carry a letter and have no aligned (2+ space) gap;
    data rows like ``A      100.0 % Water`` or a stray ``95.00`` do not qualify."""
    return len(s) >= 3 and any(c.isalpha() for c in s) and "  " not in s


def parse(path):
    """
    Parses a ChemStation text/report sidecar into a ``kind``-tagged structure.

    Args:
        path (str): Path of the sidecar file.

    Returns:
        Dict ``{'parser': 'chemstation_text', 'kind': <kind>, ...}``; the
        remaining keys depend on the sub-format (see the per-kind parsers).

    """
    kind = _kind(os.path.basename(path))
    text = _read(path)
    builder = {
        "runstart": _parse_runstart,
        "instrument_report": _parse_report,
        "rtl_report": _parse_rtlrep,
        "run_log": _parse_run_log,
        "audit": _parse_audit,
        "method_info": _parse_method_info,
        "msparms": _parse_msparms,
        "report_text": _parse_report_text,
        "report_csv": _parse_report_csv,
        "methhist": _parse_methhist,
        "scstate": _parse_scstate,
        "tic_header": _parse_tic_header,
        "report_header_template": _parse_rpthead,
    }[kind]
    out = builder(text)
    out["parser"] = NAME
    out["kind"] = kind
    return out


def _parse_runstart(text):
    """``runstart.txt`` - the CP run-variable dump.

    Collects every ``Label (_var$) = value`` pair into ``variables`` (keyed by
    the CP variable name) with the human label kept alongside.
    """
    variables = {}
    for line in text.splitlines():
        m = _CPVAR.match(line)
        if not m:
            continue
        var = m.group("var").strip()
        if not var:
            continue
        variables[var] = {
            "label": m.group("label").strip(),
            "value": m.group("value").strip(),
        }
    return {"variables": variables}


def _parse_report(text):
    """``acq.txt`` / ``acqmeth.txt`` - instrument-parameter reports.

    Captures the identifying header (data file, method, instrument model, save
    time) and the parameter body as ``{section: {key: value}}``. The body is
    overwhelmingly numeric instrument settings; it is preserved for losslessness
    but only the header feeds :func:`canonical`.
    """
    lines = text.splitlines()
    is_banner = [_is_banner(s) for s in lines]

    header = {}
    sections = {}
    current = ""
    for i, line in enumerate(lines):
        if is_banner[i]:
            continue
        s = line.strip()
        if not s:
            continue
        m = _KV.match(line)
        adj_banner = is_banner[i - 1] or (i + 1 < len(lines) and is_banner[i + 1])
        if m:
            key, value = m.group("key"), m.group("value")
            sections.setdefault(current, {})[key] = value
            low = key.lower()
            if low == "data file":
                header.setdefault("data_file", value)
            elif low in ("acq. method", "acq method", "acquisition method"):
                header.setdefault("method", value)
            elif low == "instrument control parameters":
                header.setdefault("instrument", value)
        elif adj_banner and _is_title(s):
            current = s
            sections.setdefault(current, {})
        # A bare full method path line (acqmeth lists the method this way) and
        # the weekday save-time line both sit outside the key:value grid.
        elif re.match(r"^[A-Za-z]:\\.*\.[Mm]$", s):
            header.setdefault("method", s)
        elif _WEEKDAY.search(s) and re.search(r"\d{4}\s*$", s):
            header.setdefault("save_time", s)
    return {"header": header, "sections": sections}


def _parse_rtlrep(text):
    """``rtlrep.txt`` - retention-time-lock report.

    The header is a small ``Field: value`` block (locked method, cal date,
    instrument, operator); the body is a numeric RT calibration table that is
    ignored. ``Compound`` and the RTL curve line are kept verbatim.
    """
    header = {}
    extra = {}
    for line in text.splitlines():
        m = _KV.match(line)
        if not m:
            # rtlrep uses single-space ``Field: value`` too; retry looser.
            m2 = re.match(r"^\s*(?P<key>[A-Za-z][\w .]*?)\s*:\s+(?P<value>\S.*?)\s*$", line)
            if not m2:
                continue
            m = m2
        key, value = m.group("key").strip(), m.group("value").strip()
        low = key.lower()
        if low in ("retention locked method", "retention locked cal date",
                   "instrument", "operator"):
            header[key] = value
        elif low in ("compound", "rtl curve", "maximum deviation"):
            extra[key] = value
    return {"header": header, "extra": extra}


def _parse_run_log(text):
    """``RUN.LOG`` - the instrument event log.

    Each event is a hex framing line followed by a message line ending in a
    ``HH:MM:SS MM/DD/YY`` stamp. Captures one record per message line and the
    embedded ``MODULE:SERIAL`` tokens (the authoritative on-instrument serials).
    """
    events = []
    for line in text.splitlines():
        s = line.strip()
        if not s or _HEXLINE.match(s):
            continue
        tm = _LOGTIME.search(s)
        time = tm.group("time") if tm else ""
        date = tm.group("date") if tm else ""
        body = s[:tm.start()].rstrip() if tm else s
        tokens = body.split()
        module = tokens[0] if tokens else ""
        event = {"module": module, "message": body, "time": time, "date": date}
        ms = _MODSERIAL.search(body)
        if ms:
            event["module_serial"] = ms.group(0)
        events.append(event)
    return {"events": events}


def _parse_audit(text):
    """``Audit.txt`` - the method-folder audit trail.

    A header line naming the audit file's own path, an optional ``Created`` line,
    then a run of ``Key : Value`` records (``Modified``/``Event``/``Message``/
    ``Why``/``Severity``); a new record begins at each ``Modified``. The events
    carry method-save paths and timestamps - per-instance forensic context, but
    no single canonical identifier - so this is inspect-only: the records are
    kept verbatim and nothing is promoted to :func:`canonical`.
    """
    _RECORD = ("modified", "event", "message", "why", "severity")
    path = ""
    created = ""
    events = []
    cur = {}
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = _KV.match(line)
        if m:
            key = m.group("key").strip().lower()
            if key in _RECORD:
                if key == "modified" and cur:
                    events.append(cur)
                    cur = {}
                cur[key] = m.group("value").strip()
                continue
        cm = re.match(r"(?i)^created\b[:\s]*(?P<ts>.*)$", s)
        if cm:
            created = cm.group("ts").strip()
        elif not path:
            path = s
    if cur:
        events.append(cur)
    return {"path": path, "created": created, "events": events}


def _parse_method_info(text):
    """``method.txt`` - the MassHunter "Additional Information" method summary.

    A small ``Key : Value`` block (``Method``/``Renamed`` paths, ``File
    created`` time) followed by free prose. The key/value pairs are collected and
    every non-blank line is kept verbatim; :func:`canonical` lifts the method
    path.
    """
    info = {}
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        lines.append(s)
        m = _KV.match(line)
        if m:
            info[m.group("key").strip()] = m.group("value").strip()
    return {"info": info, "lines": lines}


def _parse_msparms(text):
    """``MSPARMS.txt`` - the MSD parameter report.

    A short ``Label : value`` identity header (data file, operator, acquisition
    time, instrument, tune file, sample name) over a long numeric body of MS tune
    parameters (skimmer/lens voltages, mass-axis calibration, EM settings). The
    body is instrument state, not identity, so - as with the other reports here -
    it is kept verbatim for losslessness but only the labeled header feeds
    :func:`canonical`.

    Returns ``{'header': {<canonical field>: value}, 'lines': [...]}``: the
    header keyed already by canonical name (first value wins), and every non-blank
    line verbatim.
    """
    header = {}
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        lines.append(s)
        m = _KV.match(line)
        if not m:
            continue
        key = m.group("key").strip().lower()
        value = m.group("value").strip()
        if key in _MSPARMS_FIELDS and value:
            header.setdefault(_MSPARMS_FIELDS[key], value)
    return {"header": header, "lines": lines}


def _parse_report_text(text):
    """``report.txt`` - the ChemStation acquisition / area-percent report.

    A fixed-width header (two right-aligned ``Label : value`` columns) names the
    run; below it sit method/sequence prose and a numeric peak table. The peak
    table and the wrapped Method/Sequence paths are kept in the lossless ``lines``
    but not mined; only the single-line identity labels feed :func:`canonical`.

    Returns ``{'header': {<canonical field>: value}, 'lines': [...]}``.
    """
    header = {}
    lines = []
    for line in text.splitlines():
        if not line.strip():
            continue
        s = line.rstrip()
        lines.append(s)
        ls = s.strip()
        # The data-file line has no colon ("Data File <path>"); take the rest.
        if ls.startswith("Data File") and "data_file" not in header:
            value = ls[len("Data File"):].lstrip(": ").strip()
            if value:
                header["data_file"] = value
            continue
        for m in _REPORT_PAIR.finditer(s):
            field = _REPORT_TEXT_FIELDS.get(m.group(1).strip().lower())
            value = m.group(2).strip()
            if field and value:
                header.setdefault(field, value)
    return {"header": header, "lines": lines}


def _parse_report_csv(text):
    """``report00.csv`` .. ``report03.csv`` - the report as quoted CSV.

    Each row is ``"Key","Value",""``; the identity keys map directly to canonical
    fields. The full row list is kept for losslessness.

    Returns ``{'header': {<canonical field>: value}, 'rows': [[...], ...]}``.
    """
    text = text.lstrip("﻿")  # drop a leading BOM so the first key matches
    header = {}
    rows = []
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        rows.append(row)
        if len(row) >= 2:
            field = _REPORT_CSV_FIELDS.get(row[0].strip().lower())
            value = row[1].strip()
            if field and value:
                header.setdefault(field, value)
    return {"header": header, "rows": rows}


def _parse_methhist(text):
    """``acq_methhist.txt`` - the acquisition method-history summary.

    A single-column ``Key : Value`` head (``Data File``, ``Acq. Method``)
    followed by a repeating ``Operator``/``Date``/``Change Info`` method audit
    trail. The trail is kept verbatim in ``lines``; :func:`canonical` lifts the
    data file and acquisition method.

    Returns ``{'header': {<canonical field>: value}, 'lines': [...]}``.
    """
    header = {}
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        lines.append(s)
        m = _KV.match(line)
        if not m:
            continue
        key = m.group("key").strip().lower()
        value = m.group("value").strip()
        if key == "data file":
            header.setdefault("data_file", value)
        elif key == "acq. method":
            header.setdefault("method", value)
    return {"header": header, "lines": lines}


def _parse_scstate(text):
    """``scstate.txt`` - the SmartCard "SC State Report".

    Configuration blocks of ``Key = Value`` lines (instrument model, serial
    number, smartcard/firmware settings, ...). The values are mostly numeric
    instrument state, kept in ``lines`` and the ``info`` map for losslessness;
    :func:`canonical` lifts the instrument serial(s) and model.

    Returns ``{'info': {key: value}, 'serials': [...], 'lines': [...]}``.
    """
    info = {}
    serials = []
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        lines.append(s)
        m = _EQKV.match(line)
        if not m:
            continue
        key = m.group("key").strip()
        value = m.group("value").strip()
        info.setdefault(key, value)
        if key.lower() == "serial number" and value and value not in serials:
            serials.append(value)
    return {"info": info, "serials": serials, "lines": lines}


def _parse_tic_header(text):
    """``tic_front.csv`` / ``.tsv`` - chromatogram dump.

    Only the first line carries metadata: ``<data file path> <acquired time>``.
    Everything after ``Start of data points`` is numeric and ignored.
    """
    first = ""
    for line in text.splitlines():
        if line.strip():
            first = line.strip()
            break
    header = {}
    m = re.match(r"^(?P<file>.*\.[Dd])\s+(?P<ts>(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*)$",
                 first)
    if m:
        header["data_file"] = m.group("file").strip()
        header["acquired"] = m.group("ts").strip()
    else:
        header["line"] = first
    return {"header": header}


def _parse_rpthead(text):
    """``rpthead.txt`` - the report-header template.

    A customizable page printed atop method reports; it "can be used to identify
    the laboratory which uses the method." The default is Agilent ASCII art with
    no parseable field, so this is inspect-only: the prose lines are kept
    verbatim and nothing is promoted to canonical.
    """
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    return {"lines": lines}


def canonical(parsed):
    """
    Projects a parsed ChemStation text sidecar onto the shared canonical fields.

    Args:
        parsed (dict): Output of :func:`parse`.

    Returns:
        Dict of the canonical fields this file supplies (others omitted).
        ``serials`` and ``devices`` are lists; the rest are scalars.

    """
    kind = parsed.get("kind")
    if kind == "runstart":
        return _canon_runstart(parsed)
    if kind == "instrument_report":
        return _canon_report(parsed)
    if kind == "rtl_report":
        return _canon_rtlrep(parsed)
    if kind == "run_log":
        return _canon_run_log(parsed)
    if kind == "method_info":
        return _canon_method_info(parsed)
    if kind == "scstate":
        return _canon_scstate(parsed)
    if kind in ("msparms", "tic_header", "report_text", "report_csv", "methhist"):
        # All keep their canonical fields ready-keyed in 'header'.
        return dict(parsed.get("header", {}))
    # 'audit' (and rpthead) are inspect-only: forensic detail, no clean field.
    return {}


def _canon_runstart(parsed):
    out = {}
    var = parsed.get("variables", {})

    def val(name):
        v = var.get(name)
        return v["value"].strip() if v and v["value"].strip() else None

    mapping = {
        "_methfile$": "method",
        "_datafile$": "data_file",
        "_alsbottle": "vialpos",
        "_dataname$": "sample",
    }
    for name, field in mapping.items():
        v = val(name)
        if v:
            out[field] = v
    return out


def _canon_report(parsed):
    out = {}
    header = parsed.get("header", {})
    for field in ("data_file", "method", "instrument"):
        if header.get(field):
            out[field] = header[field]
    if header.get("save_time"):
        out["method_save_time"] = header["save_time"]
    return out


def _canon_rtlrep(parsed):
    out = {}
    for key, value in parsed.get("header", {}).items():
        if not value:
            continue
        low = key.lower()
        if low == "retention locked method":
            out["method"] = value
        elif low == "operator":
            out["operator"] = value
        elif low == "instrument":
            out["instrument"] = value
    return out


def _canon_method_info(parsed):
    info = parsed.get("info", {})
    # The original method path is the cleanest identifier; fall back to the
    # renamed/instance path if that is all the file carries.
    for key in ("Method", "Renamed"):
        if info.get(key):
            return {"method": info[key]}
    return {}


def _canon_scstate(parsed):
    out = {}
    serials = parsed.get("serials", [])
    model = parsed.get("info", {}).get("Instrument Model")
    if serials:
        out["serials"] = list(serials)
        first = {"SerialNumber": serials[0]}
        if model:
            first["Name"] = model
        out["devices"] = [first]
    if model:
        out["instrument"] = model
    return out


def _canon_run_log(parsed):
    serials = []
    devices = []
    vialpos = None
    for event in parsed.get("events", []):
        token = event.get("module_serial")
        if token:
            module, serial = token.split(":", 1)
            if serial not in serials:
                serials.append(serial)
                devices.append({"Name": module, "SerialNumber": serial})
        if vialpos is None:
            vm = re.search(r"vial#\s*(\d+)", event.get("message", ""))
            if vm:
                vialpos = vm.group(1)
    out = {}
    if serials:
        out["serials"] = serials
        out["devices"] = devices
    if vialpos:
        out["vialpos"] = vialpos
    return out
