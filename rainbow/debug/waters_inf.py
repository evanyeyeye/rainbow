"""
Parser for the Waters MassLynx method sidecars ``_INLET.INF`` / ``inlet.inf`` and
``_extern.inf`` found in a ``.raw`` run directory.

These are the human-readable method records MassLynx writes next to the binary
``_FUNC*.DAT`` traces. rainbow's Waters reader
(:mod:`rainbow.waters.masslynx`) never opens them; it reads ``_HEADER.TXT`` for
the m/z calibration (see :mod:`rainbow.debug.waters_header`) and the numeric
``_FUNCTNS.INF``. The identity these sidecars add is the **method reference** the
run was acquired with: usually a method file path under a named MassLynx project
(e.g. ``c:\\masslynx\\PROJECT01.pro\\acqudb\\...`` or
``C:\\MassLynx\\PROJECT02.PRO\\...``, where the ``.PRO`` project name is
per-instance context), or, for the GC run-log ``inlet.inf``, a bare method name.
Either way the rest of the run does not carry it.

MassLynx also writes a parenthesized copy (``_extern(1).inf``, ``_inlet(2).inf``)
when a ``.raw`` is re-acquired or re-processed in place; the copy carries the same
method-reference identity and is treated as its base name.

Layouts, all handled by reading the decoded lines (the leading underscore is
sometimes dropped, e.g. the GC run-log variant ``inlet.inf``):

================  ============================================================
file              content
================  ============================================================
_INLET.INF        "ACE Experimental Record" + ``Inlet Method File: <path>`` +
                  per-module run-method parameters (pump, autosampler, ...)
inlet.inf         GC run log + ``Method File: <name>`` + GC inlet parameters
                  (oven, injector, carrier, split); the method is a bare name,
                  not a path
_extern.inf       ``Parameters for <method path>`` (or a bare label) + tune /
                  data-processing parameters; sometimes UTF-16, sometimes a
                  short binary stub
================  ============================================================

The parse keeps the decoded non-blank lines verbatim (lossless for inspect);
:func:`canonical` promotes only the method reference. Both inlet layouts
(``Inlet Method File:`` and ``Method File:``) always introduce a method, so the
value is taken as-is (a MassLynx project path or a bare GC method name); the
``_extern.inf`` prefix (``Parameters for``) can instead be a bare label, so
there the value is taken only when it looks like a path (a bare
``Parameters for test`` is left in the lossless body and not mis-promoted).
Deliberately excluded: ``_HEADER.TXT`` (owned by
:mod:`rainbow.debug.waters_header`), and the numeric/binary ``_FUNCTNS.INF``,
``_CHROMS.INF`` and ``_HISTORY.INF`` (no readable identity).
"""
import os
import re

from rainbow.debug._util import decode_text

NAME = "waters_inf"

# Exact basenames (lowercased) this module claims, mapped to a sub-kind. Some
# instruments (e.g. the GC run-log variant) drop the leading underscore.
_NAMES = {
    "_inlet.inf": "inlet",
    "inlet.inf": "inlet",
    "_extern.inf": "extern",
    "extern.inf": "extern",
}

# MassLynx writes a parenthesized copy (``_extern(1).inf``, ``_inlet(2).inf``)
# each time a ``.raw`` is re-acquired or re-processed in place; the copy carries
# the same method-reference identity. Strip the ``(N)`` so the base name matches.
_NUMBERED = re.compile(r"\(\d+\)(?=\.inf$)")


def _kind(name):
    """Sub-kind for ``name`` (a numbered copy maps to its base), or None."""
    return _NAMES.get(_NUMBERED.sub("", name.lower()))

# How each kind announces its method, by line prefix (lowercased). The inlet
# record appears in two layouts: the MassLynx "Inlet Method File: <path>" and the
# GC run-log "Method File: <name>"; both name the acquiring method.
_INLET_PREFIXES = ("inlet method file:", "method file:")
_EXTERN_PREFIXES = ("parameters for",)


def matches(name):
    """True for ``_INLET.INF``/``inlet.inf``/``_extern.inf``/``extern.inf``
    and their numbered MassLynx copies (e.g. ``_extern(1).inf``),
    case-insensitive."""
    return _kind(name) is not None


def parse(path):
    """
    Decodes the sidecar into its non-blank lines.

    The encoding varies (ASCII, UTF-16, occasionally a binary stub), so the bytes
    go through the shared :func:`decode_text`. Blank lines are dropped; every
    other line is kept verbatim, so the full method record is available to
    ``inspect`` even though :func:`canonical` only lifts the method path.

    Args:
        path (str): Path of the _INLET.INF / _extern.inf file.

    Returns:
        Dict ``{'parser': 'waters_inf', 'kind': 'inlet'|'extern',
        'lines': [...]}``.

    """
    with open(path, "rb") as f:
        raw = f.read()
    text = decode_text(raw)
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    kind = _kind(os.path.basename(path))
    return {"parser": NAME, "kind": kind, "lines": lines}


def _looks_like_path(value):
    """True if ``value`` looks like a file path rather than a bare label.

    MassLynx method paths carry a drive/dir separator (``c:\\...`` or ``/...``);
    a label such as ``test`` does not, and must not be promoted to a method.
    """
    return "\\" in value or "/" in value or ":" in value


def _method_path(parsed):
    """Returns the method/inlet file reference from the decoded lines, or None.

    For the ``inlet`` kind the value is taken as-is (a MassLynx project path or a
    bare GC method name, both identity); for ``extern`` it is taken only when it
    looks like a path, so a bare ``Parameters for test`` label is not promoted.
    """
    kind = parsed.get("kind")
    prefixes = _INLET_PREFIXES if kind == "inlet" else _EXTERN_PREFIXES
    for line in parsed.get("lines", []):
        low = line.lower()
        prefix = next((p for p in prefixes if low.startswith(p)), None)
        if prefix is None:
            continue
        value = line[len(prefix):].strip()
        # The "...Method File:" layouts carry a colon; "Parameters for" does not.
        if value.startswith(":"):
            value = value[1:].strip()
        if not value:
            continue
        if kind == "extern" and not _looks_like_path(value):
            continue  # a bare label, not a path; leave it in the lossless body
        return value
    return None


def canonical(parsed):
    """
    Projects the parsed sidecar onto the shared canonical fields.

    Args:
        parsed (dict): Output of :func:`parse`.

    Returns:
        Dict with ``method`` (the method/inlet file path) when one is present,
        else empty. The full parameter body stays in :func:`parse`'s ``lines``.

    """
    method = _method_path(parsed)
    return {"method": method} if method else {}
