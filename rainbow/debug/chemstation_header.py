"""
Parser for the text fields in ChemStation ``.ch`` / ``.uv`` / ``.ms`` binary
**headers**.

rainbow's data parsers (``rainbow/agilent/chemstation.py``) read these same
binary files for their signal arrays and pull a few header strings into
``DataFile.metadata`` (notebook, date, method, instrument, unit, signal,
vialpos). They do not, however, surface every identifier the header carries -
in particular the **operator**, the acquisition **workstation** name (e.g.
``<host> ChemStation``), the data-file technique marker (``LC DATA FILE``),
and the ``LC``/``GC``/``OL`` file-type token. This module reads only the header
window (never the data) and exposes all of those.

The header layout depends on a version marker at offset 0 (``130``/``179``/...
for ``.ch``/``.uv``; the ``0x01320000`` magic for ``.ms``). Each string is
length-prefixed: a one-byte length ``N`` followed by ``N`` characters at stride
``gap`` (1 for the legacy DOS-ChemStation layout, 2 for the newer one). The
offset tables below mirror ``chemstation.py`` and extend it with the dropped
fields; see ``docs/source/debug/formats/chemstation_header.md``.
"""
import os
import struct

NAME = "chemstation_header"

_EXTS = (".ch", ".uv", ".ms")

# How many header bytes to read. Every offset below (max ~0x104C plus a short
# string, and the .uv vialpos at 0xFD7) sits well within this window, so we
# never touch the - potentially multi-megabyte - data block.
_HEADER_BYTES = 0x1900

# Offset tables keyed by the version marker. Each entry is (gap, {field:
# offset}). Fields beyond rainbow's own set: ``data_marker`` (technique banner),
# ``operator``, ``file_type`` (LC/GC/OL), ``workstation`` (PC + " ChemStation"),
# and for .ms the ``inlet`` instrument id.
_TABLES = {
    # Newer gap=2 .ch - FID (179/181) and CAD/ELSD/UV (130).
    "179": (2, {
        "data_marker": 0x15B, "notebook": 0x35A, "operator": 0x758,
        "date": 0x957, "file_type": 0x9E5, "method": 0xA0E,
        "workstation": 0xC11, "unit": 0x104C, "signal": 0x1075,
    }),
    "181": (2, {
        "data_marker": 0x15B, "notebook": 0x35A, "operator": 0x758,
        "date": 0x957, "file_type": 0x9E5, "method": 0xA0E,
        "workstation": 0xC11, "unit": 0x104C,
    }),
    "130": (2, {
        "data_marker": 0x15B, "notebook": 0x35A, "operator": 0x758,
        "date": 0x957, "file_type": 0x9E5, "method": 0xA0E,
        "workstation": 0xC11, "unit": 0x104C, "signal": 0x1075,
    }),
    # Newer gap=2 .uv (131). No workstation field; carries vialpos.
    "131": (2, {
        "data_marker": 0x15B, "notebook": 0x35A, "operator": 0x758,
        "date": 0x957, "file_type": 0x9E5, "method": 0xA0E,
        "unit": 0xC15, "signal": 0xC40, "vialpos": 0xFD7,
    }),
    # Legacy gap=1 .ch (30). rainbow's "instrument" offset (0xDA) is really the
    # file-type token here; the workstation name sits at 0x142.
    "30": (1, {
        "data_marker": 0x4, "notebook": 0x18, "operator": 0x94,
        "date": 0xB2, "file_type": 0xDA, "method": 0xE4,
        "workstation": 0x142, "unit": 0x244, "signal": 0x254,
    }),
    # Legacy gap=1 .uv (31).
    "31": (1, {
        "data_marker": 0x4, "notebook": 0x18, "operator": 0x94,
        "date": 0xB2, "file_type": 0xDA, "method": 0xE4, "unit": 0x146,
    }),
}

# The .ms files use the same legacy gap=1 layout but are identified by a 4-byte
# magic rather than a version string, and carry an inlet id at 0xD0.
_MS_TABLE = (1, {
    "data_marker": 0x4, "operator": 0x94, "inlet": 0xD0, "date": 0xB2,
    "file_type": 0xDA, "method": 0xE4,
})
_MS_MAGIC = 0x01320000

# Lossless header field -> canonical name. Fields kept for context only
# (data_marker, file_type, notebook, unit) are intentionally absent.
_CANON = {
    "operator": "operator",
    "method": "method",
    "date": "acquired",
    "vialpos": "vialpos",
    "workstation": "computers",
    "inlet": "instrument",
    "signal": "signal_optics",
}
_LIST = ("computers", "signal_optics")


def matches(name):
    """Returns True if ``name`` is a ChemStation binary data file."""
    return name.lower().endswith(_EXTS)


def _read_string(buf, offset, gap):
    """Reads a length-prefixed header string (``N`` then ``N`` chars at stride
    ``gap``). Returns None when the slot is empty, out of range, or unreadable."""
    if offset < 0 or offset >= len(buf):
        return None
    n = buf[offset]
    if n == 0:
        return None
    raw = buf[offset + 1: offset + 1 + n * gap: gap]
    if len(raw) < n:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    text = text.strip()
    return text or None


def _table_for(path, buf):
    """Returns (head, gap, offsets) for ``buf`` or (None, None, None)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".ms":
        if len(buf) >= 4 and struct.unpack(">I", buf[:4])[0] == _MS_MAGIC:
            gap, offsets = _MS_TABLE
            return "ms", gap, offsets
        return None, None, None
    head = _read_string(buf, 0, 1)
    if head in _TABLES:
        gap, offsets = _TABLES[head]
        return head, gap, offsets
    return None, None, None


def parse(path):
    """
    Reads the header strings of a ChemStation ``.ch`` / ``.uv`` / ``.ms`` file.

    Args:
        path (str): Path of the binary data file.

    Returns:
        Dict ``{'parser': 'chemstation_header', 'ext': ..., 'head': ...,
        'gap': ..., 'fields': {name: value}}``. ``fields`` holds every header
        string present. An unrecognized header yields an empty ``fields`` (and a
        ``head`` of None) rather than raising.

    """
    with open(path, "rb") as f:
        buf = f.read(_HEADER_BYTES)
    head, gap, offsets = _table_for(path, buf)
    fields = {}
    if offsets:
        for name, offset in offsets.items():
            value = _read_string(buf, offset, gap)
            if value:
                fields[name] = value
    return {
        "parser": NAME,
        "ext": os.path.splitext(path)[1].lower(),
        "head": head,
        "gap": gap,
        "fields": fields,
    }


def canonical(parsed):
    """
    Projects the header strings onto the shared canonical field names.

    Args:
        parsed (dict): Output of :func:`parse`.

    Returns:
        Dict of canonical fields. ``computers`` and ``signal_optics`` are lists;
        the rest are scalars. Context-only header fields are not promoted.

    """
    out = {}
    for name, value in parsed.get("fields", {}).items():
        canon = _CANON.get(name)
        if not canon or not value:
            continue
        if canon in _LIST:
            out.setdefault(canon, [])
            if value not in out[canon]:
                out[canon].append(value)
        else:
            out.setdefault(canon, value)
    return out
