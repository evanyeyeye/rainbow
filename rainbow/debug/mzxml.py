"""
Parser for mzXML files (the open HUPO-PSI interchange format vendors export to).

Unlike the vendor sidecars the other debug parsers read, mzXML is an open,
documented format - exactly the kind of liberated export rainbow exists to
encourage. A converted run still carries useful provenance in its header: the
instrument (manufacturer/model/ionisation/analyzer/detector), the acquisition
and conversion software, and ``parentFile`` references back to the source vendor
files.

Only the **header** is read. An mzXML file inlines every scan's peak list as
base64 (these run to megabytes - 10k+ scans is common), so the parser uses a
streaming pass that stops at the first ``<scan>``: it never materializes the
spectral data, the same "skip the bulk numeric payload, keep the identifiers"
line the other parsers draw.
"""
# lxml's recovering parser is what lets a truncated mzXML still yield its
# header; see the note in rainbow/debug/xml.py. Guarded so importing rainbow
# does not require lxml.
try:
    from lxml import etree
except ImportError:
    etree = None

from rainbow.debug._util import require_lxml

NAME = "mzxml"

# Header sub-elements whose ``value`` attribute describes the instrument.
_INSTRUMENT_PARTS = ("msManufacturer", "msModel", "msIonisation",
                     "msMassAnalyzer", "msDetector")


def matches(name):
    """Returns True for an ``.mzXML`` file."""
    return name.lower().endswith(".mzxml")


def parse(path):
    """
    Reads the mzXML header (everything before the first ``<scan>``).

    Requires lxml, whose recovering parser is what lets a truncated file still
    yield its header.

    Streams with ``iterparse`` and breaks at the first scan, so the megabytes of
    base64 peak data are never parsed. Returns the run-level attributes, the
    ``parentFile`` references, the instrument description, and the software
    history.

    Args:
        path (str): Path of the .mzXML file.

    Returns:
        Dict ``{'parser': 'mzxml', 'msRun': {...}, 'parent_files': [...],
        'instrument': {...}, 'software': [{...}]}``, or
        ``{'parser': 'mzxml', 'error': ...}`` if the header cannot be read.

    """
    require_lxml(etree, "an mzXML header")
    msrun = {}
    parent_files = []
    instrument = {}
    software = []
    try:
        # start events expose each element's attributes before its children are
        # read, so breaking at the first <scan> avoids the peak data entirely.
        for _, el in etree.iterparse(path, events=("start",), recover=True):
            tag = etree.QName(el).localname
            if tag == "scan":
                break
            if tag == "msRun":
                msrun = dict(el.attrib)
            elif tag == "parentFile":
                name = el.get("fileName")
                if name:
                    parent_files.append(name)
            elif tag in _INSTRUMENT_PARTS:
                value = el.get("value")
                if value:
                    instrument[tag] = value
            elif tag == "software":
                software.append({k: el.get(k)
                                 for k in ("type", "name", "version")
                                 if el.get(k)})
    except etree.XMLSyntaxError as e:
        return {"parser": NAME, "error": repr(e)}

    return {
        "parser": NAME,
        "msRun": msrun,
        "parent_files": parent_files,
        "instrument": instrument,
        "software": software,
    }


def _source_datafile(parent_files):
    """Extracts the source vendor run from a ``parentFile`` path.

    mzXML ``parentFile`` references point at files inside the source run, e.g.
    ``file:///D:/.../SAMPLE-001.d/AcqData/MSProfile.bin``. Returns the run
    directory (``...SAMPLE-001.d``) when a ``.d``/``.raw`` component is
    present, else the raw reference, else None. The scheme prefix is stripped;
    any operator/project name embedded earlier in the path is left in place
    (mirrors the Agilent ACQMethodPath handling).
    """
    if not parent_files:
        return None
    ref = parent_files[0]
    path = ref.split("://", 1)[1] if "://" in ref else ref
    parts = path.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part.lower().endswith((".d", ".raw")):
            return "/".join(parts[:i + 1]).lstrip("/")
    return path.lstrip("/")


def canonical(parsed):
    """
    Promotes the mzXML header to the shared canonical field names.

    Args:
        parsed (dict): Output of :func:`parse`.

    Returns:
        Dict of canonical fields present in the header. ``instrument`` comes
        from the model (else manufacturer); ``software_version`` from the
        acquisition software (else the first listed); ``data_file`` from the
        source run referenced by ``parentFile``.

    """
    out = {}

    inst = parsed.get("instrument", {})
    model = inst.get("msModel") or inst.get("msManufacturer")
    if model:
        out["instrument"] = model

    # Prefer the acquisition software; fall back to the first NAMED entry (often
    # the conversion tool) so a blank leading entry does not suppress a usable
    # version.
    sw = parsed.get("software", [])
    acq = next((s for s in sw if s.get("type") == "acquisition" and s.get("name")),
               None)
    chosen = acq or next((s for s in sw if s.get("name")), None)
    if chosen:
        version = chosen.get("version")
        out["software_version"] = (
            f"{chosen['name']} {version}" if version else chosen["name"])

    data_file = _source_datafile(parsed.get("parent_files", []))
    if data_file:
        out["data_file"] = data_file

    return out
