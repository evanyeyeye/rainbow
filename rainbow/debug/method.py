"""
Parser for ChemStation / MassHunter method and macro files: ``.mth``, ``.e``,
``.p``, ``.val``, ``.mac``.

This family is heterogeneous - ASCII or UTF-16 macro scripts (``NAME x`` followed
by indented ``KEYWORD args`` / ``KEY$ = "value"`` lines), ``[section]`` INI-style
``.mth``, and binary numeric ``.mth`` databases. But its content is almost
entirely **invariant method-template** material: integration parameters, event
tables, quant settings, macro command bodies - the same across runs, carrying no
acquisition identity. Per the subsystem rule we do not surface that boilerplate.

A survey of every method/macro fixture finds exactly one identifier-bearing
value: a macro that records the **last data file** as a quoted path. So this
parser classifies the file (so the format is recognized, not silently skipped)
and extracts only the **path / data-file references** from the quoted values; it
does not dump the script bodies. ``canonical`` promotes a data-file path when one
is present, and nothing otherwise.

See ``docs/debug/formats/method.md``.
"""
import re

from rainbow.debug._util import decode_text

NAME = "method"

_EXTS = (".mth", ".e", ".p", ".val", ".mac")

# A double-quoted value in a macro assignment (KEY$ = "value").
_QUOTED = re.compile(r'"([^"\r\n]{1,200})"')
# A value that looks like a filesystem path or a data-file/method-file name.
_PATHLIKE = re.compile(r"[A-Za-z]:\\|\\\\|\.[dDmM]\s*$")


def matches(name):
    """Returns True for a method/macro file in this family."""
    return name.lower().endswith(_EXTS)


def _kind(raw, text):
    """Classifies the file as 'binary', 'ini', or 'macro'/'script'."""
    sample = raw[:256]
    nonprintable = sum(1 for c in sample if c < 9 or 13 < c < 32)
    if nonprintable > len(sample) // 8:
        return "binary"
    stripped = text.lstrip()
    if stripped.startswith("["):
        return "ini"
    return "macro"


def parse(path):
    """
    Classifies a method/macro file and extracts its path / data-file references.

    Args:
        path (str): Path of the method or macro file.

    Returns:
        Dict ``{'parser': 'method', 'kind': ..., 'paths': [...]}``. ``paths``
        holds the quoted values that look like a filesystem path or a
        data/method file name; the invariant script body is not included.

    """
    with open(path, "rb") as f:
        raw = f.read()
    text = decode_text(raw)
    kind = _kind(raw, text)

    paths = []
    if kind != "binary":
        for value in _QUOTED.findall(text):
            value = value.strip()
            if value and _PATHLIKE.search(value) and value not in paths:
                paths.append(value)
    return {"parser": NAME, "kind": kind, "paths": paths}


def canonical(parsed):
    """
    Promotes a data-file path to ``data_file`` when the file records one.

    A macro that stores the last data file keeps the directory and the file name
    as separate quoted values; they are joined here. Files with no path
    references (the vast majority - invariant method templates) contribute
    nothing.

    Args:
        parsed (dict): Output of :func:`parse`.

    Returns:
        Dict with ``data_file`` if a data-file reference was found, else empty.

    """
    paths = parsed.get("paths", [])
    # A value that is already a full path to a .d data file.
    for value in paths:
        if re.search(r":\\.*\.[dD]$", value):
            return {"data_file": value}
    # Otherwise join a drive directory with a .d file name, if both are present.
    directory = next((p for p in paths
                      if re.search(r"[A-Za-z]:\\", p) and p.endswith("\\")), None)
    filename = next((p for p in paths if re.search(r"\.[dD]$", p)), None)
    if directory and filename:
        return {"data_file": directory + filename}
    if filename:
        return {"data_file": filename}
    return {}
