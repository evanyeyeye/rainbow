"""
Parser for the Agilent/Waters XML metadata sidecars that rainbow's data parsers
do not read: ``sample_info.xml`` (SampleInfo), ``Devices.xml`` (Devices),
``SAMPLE.XML`` (Sample), ``*-CumulativeAuditTrail.xml`` (AuditTrailDataSet),
``Limsinf.xml`` (SampleLimsInfo), the ACAML method/sequence sidecars
(``.acaml``/``.macaml``/``.acam_``), the Waters ``.scml`` sampler file, and
various method/automation XML.

Two layers:

* ``parse`` builds a faithful, lossless nested-dict view of the whole document
  (every element, attribute, and text), schema-agnostic, recovering from
  malformed XML (e.g. ``Limsinf.xml`` ships an invalid namespace URI).
* ``canonical`` dispatches on the root element to a schema-aware extractor that
  promotes the well-known fields to the shared canonical names. Schemas without
  an extractor yet are still fully present in ``parse``/``inspect``.

See ``docs/debug/formats/xml.md`` for the per-schema field documentation.
"""
import re

# This module recovers structure from malformed and mis-encoded sidecars, which
# needs lxml's recovering parser; the standard library has no equivalent. The
# import is guarded so that rainbow itself still imports without lxml, and only
# using the debug subsystem asks for it.
try:
    from lxml import etree
except ImportError:
    etree = None

from rainbow.debug._util import decode_text, require_lxml

NAME = "xml"

_EXTS = (".xml", ".acaml", ".macaml", ".acam_", ".scml", ".xml.bak", ".drvml",
         ".tune")


def matches(name):
    """Returns True for an XML metadata sidecar (but not the MSScan schema, nor
    mzXML - that ends with ``.xml`` but is large scan data handled by the
    dedicated header-only ``mzxml`` parser)."""
    low = name.lower()
    if low == "msscan.xsd" or low.endswith(".mzxml"):
        return False
    return low.endswith(_EXTS)


def _local(tag):
    """Strips an XML namespace from a tag/attribute name."""
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _try_parse(data):
    """Parses XML bytes, recovering from malformed documents. Returns the root
    element, or None if even recovery fails."""
    try:
        return etree.fromstring(data)
    except etree.XMLSyntaxError:
        try:
            return etree.fromstring(data, etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            return None


def _as_utf8(raw):
    """Re-encodes possibly-UTF-16 XML to UTF-8 bytes, with any XML declaration and
    BOM stripped so lxml parses from a known encoding. Some sidecars (e.g. the
    ``.tune`` files) are UTF-16LE with no BOM and no declaration, which the raw
    byte parse cannot detect. Returns None if decoding yields nothing."""
    text = decode_text(raw)
    if not text:
        return None
    text = text.lstrip("﻿")
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    return text.encode("utf-8", "replace")


def _parse_root(raw):
    """Parses XML bytes into a root element, recovering from malformed documents
    and from non-UTF-8 encodings. Returns the root, or None if recovery fails."""
    body = raw[3:] if raw[:3] == b"\xef\xbb\xbf" else raw
    root = _try_parse(body)
    if root is not None:
        return root
    alt = _as_utf8(raw)
    if alt is not None and alt != body:
        return _try_parse(alt)
    return None


def _el_to_dict(el):
    """Recursively converts an element to a faithful dict: attributes under
    ``@name`` keys, repeated children as lists, text under ``#text`` (or as the
    bare value for a pure leaf)."""
    node = {}
    for key, value in el.attrib.items():
        node["@" + _local(key)] = value
    text = (el.text or "").strip()

    children = [c for c in el if isinstance(c.tag, str)]  # skip comments/PIs
    if not children:
        if not node:
            return text
        if text:
            node["#text"] = text
        return node

    for child in children:
        key = _local(child.tag)
        value = _el_to_dict(child)
        if key in node:
            if isinstance(node[key], list):
                node[key].append(value)
            else:
                node[key] = [node[key], value]
        else:
            node[key] = value
    if text:
        node["#text"] = text
    return node


def parse(path):
    """
    Parses an XML sidecar into its faithful nested-dict structure.

    Requires lxml, whose recovering parser is what makes a malformed sidecar
    readable.

    Args:
        path (str): Path of the XML file.

    Returns:
        Dict ``{'parser': 'xml', 'root': localname, 'namespace': ns,
        'tree': {...}}``, or ``{'parser': 'xml', 'error': ...}`` if unparseable.

    """
    require_lxml(etree, "an XML sidecar")
    with open(path, "rb") as f:
        raw = f.read()
    # An empty (or whitespace-only, or BOM-only) file is a benign vendor
    # placeholder, not a corrupt document - report it distinctly so it is not
    # conflated with a real malformation. Agilent writes a 0-byte TimeStamp.xml
    # into many .D runs.
    body = raw[3:] if raw[:3] == b"\xef\xbb\xbf" else raw
    if not body.strip():
        return {"parser": NAME, "error": "empty file"}
    root = _parse_root(raw)
    if root is None:
        return {"parser": NAME, "error": "unparseable XML"}
    return {
        "parser": NAME,
        "root": _local(root.tag),
        "namespace": etree.QName(root).namespace or "",
        "tree": _el_to_dict(root),
    }


# ---- canonical extraction --------------------------------------------------
def _iter_dicts(node):
    """Yields every dict in a parsed tree (depth-first)."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_dicts(value)


def _records_with(tree, *keys):
    """Yields every dict in the tree that has all of ``keys``."""
    for record in _iter_dicts(tree):
        if all(k in record for k in keys):
            yield record


def _str(value):
    """Returns a stripped string if ``value`` is a non-empty string, else None."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def _aslist(node):
    """Normalizes a dict-or-list (or None) child into a list. A repeated XML
    element parses to a list; a single one to a dict; an absent one to None."""
    if node is None:
        return []
    return node if isinstance(node, list) else [node]


def _dig(node, *keys):
    """Descends a nested dict by ``keys``, returning the value or None. Does not
    traverse lists - used for schemas (ACAML) where the same key name recurs in
    unrelated subtrees, so a path is required rather than a key search."""
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
        if node is None:
            return None
    return node


def _sampleinfo(tree):
    """SampleInfo (sample_info.xml): a table of Name/Value Field records."""
    pairs = {}
    for record in _records_with(tree, "Name"):
        name, value = _str(record.get("Name")), _str(record.get("Value"))
        if name and value:
            pairs.setdefault(name, value)
    mapping = {
        "Sample Name": "sample",
        "Sample ID": "sample_id",
        "Operator": "operator",
        "Sample Position": "vialpos",
        "Method": "method",
        "Data File": "data_file",
        "Inj Vol (µl)": "injection_volume",
        "Acquired Time": "acquired",
    }
    return {canon: pairs[name] for name, canon in mapping.items() if name in pairs}


def _devices(tree):
    """Devices (Devices.xml): one record per instrument module."""
    out, serials, devices = {}, [], []
    for record in _records_with(tree, "SerialNumber"):
        serial = _str(record.get("SerialNumber"))
        device = {
            k: _str(record.get(k))
            for k in ("Name", "ModelNumber", "SerialNumber",
                      "FirmwareVersion", "DriverVersion")
            if _str(record.get(k))
        }
        if device:
            devices.append(device)
        # A SerialNumber of "1" is a placeholder (e.g. the FID), not a real unit.
        if serial and serial != "1":
            serials.append(serial)
    if serials:
        out["serials"] = serials
    if devices:
        out["devices"] = devices
    return out


def _sample(tree):
    """Sample (SAMPLE.XML): flat acquisition fields."""
    out = {}
    method = _str(tree.get("ACQMethodPath"))
    data_file = _str(tree.get("RefDataFilePath"))
    if method:
        out["method"] = method
    if data_file:
        out["data_file"] = data_file
    return out


def _audit_trail(tree):
    """AuditTrailDataSet (*CumulativeAuditTrail.xml): event records carrying the
    acquisition workstation and user."""
    out, computers, users = {}, [], []
    for record in _records_with(tree, "ComputerName"):
        name = _str(record.get("ComputerName"))
        if name and name not in computers:
            computers.append(name)
    for record in _records_with(tree, "User"):
        user = _str(record.get("User"))
        if user and user not in users:
            users.append(user)
    if computers:
        out["computers"] = computers
    if users:
        out["users"] = users
    return out


def _acaml(tree):
    """ACAML (``.acaml``/``.macaml``/``.acam_``): the rich Agilent container.

    Heavily ID-referenced and deeply nested; the generic key ``Name`` recurs in
    hundreds of method-parameter sections, so every field is reached by an
    explicit path (via :func:`_dig`), never a key search.
    """
    out, serials, devices, users, computers = {}, [], [], [], []
    doc = tree.get("Doc")
    if not isinstance(doc, dict):
        return out

    # DocInfo: who/where the document was produced.
    info = doc.get("DocInfo", {})
    user = _str(_dig(info, "CreatedByUser"))
    if user:
        users.append(user)
    client = _str(_dig(info, "ClientName"))
    if client:
        computers.append(client)
    app = _str(_dig(info, "CreatedByApplication", "AgilentApp", "Name"))
    ver = _str(_dig(info, "CreatedByApplication", "AgilentApp", "Version"))
    if app:
        out["software_version"] = app + (" " + ver if ver else "")

    content = doc.get("Content", {})

    # Resources/Instrument/Module: the authoritative module serials.
    for instr in _aslist(_dig(content, "Resources", "Instrument")):
        if not isinstance(instr, dict):
            continue
        name = _str(instr.get("Name"))
        if name:
            out.setdefault("instrument", name)
        for module in _aslist(instr.get("Module")):
            if not isinstance(module, dict):
                continue
            serial = _str(module.get("SerialNo"))
            device = {
                "Name": _str(module.get("Name")),
                "ModelNumber": _str(module.get("PartNo")),
                "SerialNumber": serial,
                "FirmwareVersion": _str(module.get("FirmwareRevision")),
            }
            device = {k: v for k, v in device.items() if v}
            if device:
                devices.append(device)
            if serial and serial != "1":
                serials.append(serial)

    # SampleParams: identity (sample name), vial, injection volume.
    params = content.get("SampleParams", {})
    for ident in _aslist(_dig(params, "IdentParam")):
        name = _str(_dig(ident, "Name"))
        if name:
            out.setdefault("sample", name)
    for acq in _aslist(_dig(params, "AcqParam")):
        vial = _str(_dig(acq, "VialNumber"))
        if vial:
            out.setdefault("vialpos", vial)
        injvol = _str(_dig(acq, "InjectionVolume", "@val"))
        if injvol:
            out.setdefault("injection_volume", injvol)

    # Samples/MeasData/Info: the acquisition operator and time.
    for meas in _aslist(_dig(content, "Samples", "MeasData")):
        operator = _str(_dig(meas, "Info", "CreatedBy", "Username"))
        if operator:
            out.setdefault("operator", operator)
        acquired = _str(_dig(meas, "Info", "CreatedDate"))
        if acquired:
            out.setdefault("acquired", acquired)

    if serials:
        out["serials"] = serials
    if devices:
        out["devices"] = devices
    if users:
        out["users"] = users
    if computers:
        out["computers"] = computers
    return out


def _scml(tree):
    """SampleContainerInfo (``.scml``): the autosampler container file.

    The outer document carries the sampler module identity and the active vial
    position. The gzip+base64 ``XmlContent`` sub-documents are tray rendering
    geometry (no sample/person identity), so they are left unexpanded - see the
    format reference.
    """
    out = {}
    device_info = tree.get("ContainerDeviceInfo", {})
    serial = _str(_dig(device_info, "SerialNumber"))
    device = {
        "Name": _str(_dig(device_info, "DisplayName")),
        "ModelNumber": _str(_dig(device_info, "PartNumber")),
        "SerialNumber": serial,
        "Vendor": _str(_dig(device_info, "Vendor")),
    }
    device = {k: v for k, v in device.items() if v}
    if serial and serial != "1":
        out["serials"] = [serial]
    if device:
        out["devices"] = [device]
    vial = _str(_dig(tree, "ActiveSampleLocation", "@LocationString"))
    if vial:
        out["vialpos"] = vial
    return out


def _module_data(tree):
    """AnalyticalResultsModuleData (``.drvml``): one Agilent driver-results file
    per instrument module, carrying that module's identity in ``ModuleInfo``.

    The richest LC serial source after Devices.xml/ACAML, and the only one in a
    MassHunter ``.D`` that lacks them. One file = one module, so this emits a
    single serial/device record; ``fields()`` accumulates them across the run's
    several ``.drvml`` files.
    """
    out = {}
    info = tree.get("ModuleInfo", {})
    serial = _str(_dig(info, "SerialNumber"))
    device = {
        "Name": _str(_dig(info, "DisplayName")),
        "ModelNumber": _str(_dig(info, "PartNumber")),
        "SerialNumber": serial,
        "FirmwareVersion": _str(_dig(info, "FirmwareRevision")),
        "Vendor": _str(_dig(info, "Vendor")),
    }
    device = {k: v for k, v in device.items() if v}
    if serial and serial != "1":
        out["serials"] = [serial]
    if device:
        out["devices"] = [device]
    return out


# Dispatch by root element local name.
def _tune(tree):
    """Agilent MS ``.tune`` file (root ``<Root>``): instrument serial + model.

    ``Root`` is a generic tag, so this extracts only when the tune-specific
    ``SerialNumber`` is present (else it returns ``{}``, like any unrecognized
    schema). The model comes from ``InternalModel``/``ExternalModel``.
    """
    serials = []
    model = None
    for record in _iter_dicts(tree):
        candidate = _str(record.get("InternalModel")) or _str(
            record.get("ExternalModel"))
        if candidate and model is None:
            model = candidate
        serial = _str(record.get("SerialNumber"))
        if serial and serial not in serials:
            serials.append(serial)
    # Gate everything on a serial: without one this is not a tune file (the
    # model alone must not let a generic <Root> document be claimed).
    if not serials:
        return {}
    first = {"SerialNumber": serials[0]}
    if model:
        first["Name"] = model
    out = {"serials": serials, "devices": [first]}
    if model:
        out["instrument"] = model
    return out


_HANDLERS = {
    "SampleInfo": _sampleinfo,
    "Devices": _devices,
    "Sample": _sample,
    "AuditTrailDataSet": _audit_trail,
    "ACAML": _acaml,
    "SampleContainerInfo": _scml,
    "AnalyticalResultsModuleData": _module_data,
    "Root": _tune,
}


def canonical(parsed):
    """
    Promotes the well-known fields of a recognized schema to canonical names.

    Schemas without an extractor return ``{}`` (their full content is still in
    :func:`parse`/``inspect``).

    Args:
        parsed (dict): Output of :func:`parse`.

    Returns:
        Dict of canonical fields present in this document.

    """
    tree = parsed.get("tree")
    handler = _HANDLERS.get(parsed.get("root"))
    if tree is None or handler is None:
        return {}
    return handler(tree)
