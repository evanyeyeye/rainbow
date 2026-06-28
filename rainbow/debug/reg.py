"""
Best-effort reader for ChemStation ``.REG`` register files (``ACQRES.REG``,
``LCDIAG.REG``, ``DAMETHOD.REG``, ``MSACQINF.REG``, the per-module ``L*.REG``,
...).

A ``.REG`` is an **MFC ``CArchive``** stream: it opens with a ``REGISTER FILE``
magic and stores a tree of serialized ``CHP*`` objects (``CHPUserObject``,
``CHPDatDoubleRow``, ``CHPTable``, ``CHPList``, ``CHPNdrDouble``, ...). Those
``CHP*`` record layouts are Agilent-proprietary and were never published, and
their payloads are numeric instrument register values (calibration, diagnostics,
module configuration). So this is a deliberate **best-effort** parser, at the
"readable-complete ceiling":

* it confirms the format (magic + CArchive version),
* it recovers the structural record inventory - which ``CHP*`` object types the
  archive contains, and how many of each (a compact fingerprint of what kind of
  register file this is),
* and it stops there. The numeric payloads are not decoded (proprietary, and
  numeric data the subsystem does not mine), and an exhaustive survey of every
  ``.REG`` fixture finds **no operator / method / sample / path identifiers** in
  them. ``canonical`` therefore returns nothing.

See ``docs/debug/formats/reg.md``.
"""
import re

NAME = "reg"

_MAGIC = b"REGISTER FILE"

# An MFC CArchive class name as stored: a 2-byte little-endian length followed by
# that many printable bytes. We keep only ones that look like a class identifier
# (CHP*, CObArray, ...) to avoid mistaking numeric payload bytes for strings.
_CLASS = re.compile(r"^[A-Z][A-Za-z0-9]{3,}$")


def matches(name):
    """Returns True for a ``.reg`` register file."""
    return name.lower().endswith(".reg")


def _class_names(buf):
    """Yields the MFC CArchive class names (2-byte length-prefixed) in order."""
    i, n = 0, len(buf)
    while i + 2 < n:
        length = buf[i] | (buf[i + 1] << 8)
        if 4 <= length <= 64 and i + 2 + length <= n:
            raw = buf[i + 2:i + 2 + length]
            if all(32 <= c < 127 for c in raw):
                text = raw.decode("latin-1")
                if _CLASS.match(text):
                    yield text
                    i += 2 + length
                    continue
        i += 1


def parse(path):
    """
    Recovers the structural inventory of a ``.REG`` register file.

    Args:
        path (str): Path of the ``.reg`` file.

    Returns:
        Dict ``{'parser': 'reg', 'format': 'mfc-carchive', 'magic': ...,
        'version': ..., 'record_types': {class: count}}``. A file without the
        ``REGISTER FILE`` magic yields ``{'parser': 'reg', 'format': None}``.

    """
    with open(path, "rb") as f:
        buf = f.read()

    if _MAGIC not in buf[:64]:
        return {"parser": NAME, "format": None}

    # Header: 0x02, a 2-char CArchive version tag ("32"), then the magic string.
    version = None
    head = buf[1:3]
    if all(32 <= c < 127 for c in head):
        version = head.decode("latin-1")

    record_types = {}
    for name in _class_names(buf):
        record_types[name] = record_types.get(name, 0) + 1

    return {
        "parser": NAME,
        "format": "mfc-carchive",
        "magic": _MAGIC.decode("ascii"),
        "version": version,
        "record_types": record_types,
    }


def canonical(parsed):
    """
    Returns ``{}`` - ``.REG`` files carry no recoverable identifiers.

    The ``CHP*`` record payloads are proprietary and numeric; the structural
    inventory in :func:`parse` is the most these files yield. Kept as a parser so
    the format is recognized (rather than silently skipped) and its ceiling is
    documented.

    Args:
        parsed (dict): Output of :func:`parse`.

    Returns:
        An empty dict.

    """
    return {}
