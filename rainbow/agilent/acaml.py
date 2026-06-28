"""
Read Agilent ACAML documents.

ACAML is the XML that Agilent ChemStation / OpenLab writes alongside a run.
Three flavors appear next to the data:

    acq.macaml      the per-injection acquisition method
    da.macaml       the per-injection data-analysis method
    sequence.acaml  the sequence-level document (instruments, samples, results)

They share a common skeleton, and this module reads that skeleton:

    DocInfo header      -> who/what/when produced the document
    Section tree        -> the method settings, as nested Sections of
                           Parameters (name/id/unit/value), with Table/Row
                           groupings for tabular settings (e.g. the DAD
                           signal table)

The instrument, sample, and peak-result elements that only sequence.acaml
carries have their own typed shapes and are parsed elsewhere; this module is
the shared primitive the others build on.
"""
import xml.etree.ElementTree as ET


def _local(tag):
    """The local name of a tag, dropping any ``{namespace}`` prefix."""
    return tag.rsplit('}', 1)[-1]


def _children(element, name):
    """Direct children of an element with the given local name."""
    return [child for child in element if _local(child.tag) == name]


def _child(element, name):
    """First direct child with the given local name, or None."""
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _child_text(element, name):
    """Text of the first direct child with the given local name, or None."""
    child = _child(element, name)
    return child.text if child is not None else None


def _descendant(element, name):
    """First descendant (self included) with the given local name, or None."""
    for node in element.iter():
        if _local(node.tag) == name:
            return node
    return None


def _root(source):
    """
    Resolves ``source`` to an XML element.

    Accepts an already-parsed element, a raw XML string or bytes, or a path to
    an ACAML file. This lets callers parse a file on disk or test against an
    inline document with the same entry point.
    """
    if isinstance(source, ET.Element):
        return source
    if isinstance(source, (bytes, bytearray)):
        return ET.fromstring(source)
    if isinstance(source, str) and source.lstrip().startswith('<'):
        return ET.fromstring(source)
    return ET.parse(source).getroot()


def read(source):
    """
    Reads an ACAML document's shared skeleton.

    Args:
        source: An ACAML file path, raw XML string/bytes, or parsed element.

    Returns:
        dict: ``{"doc_info": {...}, "sections": [...]}``. See ``doc_info`` and
        ``sections`` for the shape of each part.
    """
    root = _root(source)
    return {"doc_info": doc_info(root), "sections": sections(root)}


def doc_info(source):
    """
    Reads the ``DocInfo`` header.

    Returns:
        dict: Any of ``description``, ``operator`` (the ``CreatedByUser``),
        ``created``, ``client``, ``application``, ``application_version``, and
        ``doc_id`` that the document supplies. Absent fields are omitted.
    """
    root = _root(source)
    info = _descendant(root, "DocInfo")
    out = {}
    if info is not None:
        out["description"] = _child_text(info, "Description")
        out["operator"] = _child_text(info, "CreatedByUser")
        out["created"] = _child_text(info, "CreationDate")
        out["client"] = _child_text(info, "ClientName")
        app = _descendant(info, "AgilentApp")
        if app is not None:
            out["application"] = _child_text(app, "Name")
            out["application_version"] = _child_text(app, "Version")
    doc_id = _descendant(root, "DocID")
    if doc_id is not None:
        out["doc_id"] = doc_id.text
    return {key: value for key, value in out.items() if value is not None}


def sections(source):
    """
    Reads the method Section tree.

    Method documents nest their settings under ``MethodDescription``; if that
    is present its direct Sections are used, otherwise the document root's
    direct Sections are. Each section is a dict with ``name``, ``id``,
    ``parameters``, ``tables``, and nested ``sections``.

    Returns:
        list: The top-level sections.
    """
    root = _root(source)
    description = _descendant(root, "MethodDescription")
    container = description if description is not None else root
    return [_section(element) for element in _children(container, "Section")]


def _section(element):
    """A single Section, recursively."""
    return {
        "name": _child_text(element, "Name"),
        "id": _child_text(element, "ID"),
        "parameters": [_parameter(p) for p in _children(element, "Parameter")],
        "tables": [_table(t) for t in _children(element, "Table")],
        "sections": [_section(s) for s in _children(element, "Section")],
    }


def _table(element):
    """A Table as a list of rows, each row a list of Parameters."""
    return {
        "name": _child_text(element, "Name"),
        "id": _child_text(element, "ID"),
        "rows": [
            [_parameter(p) for p in _children(row, "Parameter")]
            for row in _children(element, "Row")
        ],
    }


def _parameter(element):
    """A single Parameter: name, id, unit, value."""
    return {
        "name": _child_text(element, "Name"),
        "id": _child_text(element, "ID"),
        "unit": _child_text(element, "Unit"),
        "value": _child_text(element, "Value"),
    }


def iter_parameters(sections):
    """
    Yields every Parameter in a Section tree, depth first.

    Parameters inside Table rows are included, so this is a flat view of all
    method settings regardless of how deeply they are nested.
    """
    for section in sections:
        for parameter in section["parameters"]:
            yield parameter
        for table in section["tables"]:
            for row in table["rows"]:
                for parameter in row:
                    yield parameter
        for parameter in iter_parameters(section["sections"]):
            yield parameter


def index(sections):
    """
    Maps each Parameter's ``id`` to the Parameter, for direct lookup.

    Later parameters win on the rare duplicate id; ids are otherwise unique
    within a document.
    """
    return {p["id"]: p for p in iter_parameters(sections) if p.get("id")}
