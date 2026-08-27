"""
Parser for .NET ``BinaryFormatter`` (MS-NRBF) sidecars - principally
``QualResult.bin``, the MassHunter Qualitative-analysis result/settings graph.

MS-NRBF (``[MS-NRBF]``, the .NET Remoting Binary Format) is a self-describing
object-graph stream: a one-byte record type tags each record, and strings are
length-prefixed with a 7-bit-varint length then UTF-8 bytes. The stream opens
with a ``SerializationHeaderRecord`` (type ``0x00``, MajorVersion 1).

**Depth decision.** A full object-graph reconstruction would be hundreds of
lines of MS-NRBF type machinery (class metadata, member-type tables, primitive
and array value decoding) - and for this file it would yield, on top of the
identifiers, ~1000 internal serialization member names (``m_value``,
``m_displayName``, ...) and ~200 .NET type/assembly descriptors. That is exactly
the "pile of text" the subsystem avoids. The identifier payload is small and
lives entirely in the string table: a handful of **file-path** values and the
**assembly version** stack. So this parser validates the NRBF header and walks
the length-prefixed string table, then surfaces a bounded summary - the
assemblies, the path-like values, and a count - rather than the whole graph.

See ``docs/source/debug/formats/dotnet.md``.
"""
import os
import re
import struct

NAME = "dotnet"

# Strings shorter/longer than these are not plausible identifiers/type names.
_MIN_LEN = 1
_MAX_LEN = 512

# A bare .NET assembly identity, e.g.
# ``CoreDefinitions, Version=8.0.8208.38, Culture=neutral, PublicKeyToken=null``.
# Anchored and bracket-free so the generic type constructions that merely embed
# assembly refs (``Dictionary`2[[...]]``) are excluded - they are type metadata,
# not part of the software stack.
_ASSEMBLY = re.compile(
    r"^[A-Za-z][\w.]*, Version=[\d.]+, Culture=[\w-]+, PublicKeyToken=\w+$")

# A filesystem path value: a drive (``D:\``), a UNC (``\\``), or a ChemStation
# template root (``#CUSTOMERHOME#``).
_PATH = re.compile(r"[A-Za-z]:\\|\\\\|#[A-Za-z]+#")


def matches(name):
    """Returns True for a ``.bin`` that may be a .NET BinaryFormatter stream.

    Excludes the MassHunter ``MS*.bin`` numeric data files (MSScan, MSProfile,
    MSPeak, MSMassCal, ...); :func:`parse` still validates the NRBF header, so a
    non-NRBF ``.bin`` that slips through contributes nothing.
    """
    low = name.lower()
    return low.endswith(".bin") and not low.startswith("ms")


def _is_nrbf(head):
    """True if ``head`` (>=17 bytes) starts with an MS-NRBF stream header."""
    if len(head) < 17 or head[0] != 0x00:
        return False
    _root, _hdr, major, minor = struct.unpack("<iiii", head[1:17])
    return major == 1 and minor in (0, 1)


def _read_varint(buf, i):
    """Reads a 7-bit-encoded length at ``buf[i]``. Returns (value, next_index),
    or (None, i) if it runs off the end or exceeds the 5-byte .NET limit."""
    value = shift = 0
    for _ in range(5):
        if i >= len(buf):
            return None, i
        byte = buf[i]
        i += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, i
        shift += 7
    return None, i


def _strings(buf):
    """Yields every length-prefixed UTF-8 string in ``buf``, in order.

    A real MS-NRBF walk would need the full record grammar to know exactly where
    each string sits; instead this scans for the format's own length-prefix
    convention and validates each candidate strictly (printable ASCII/UTF-8, in
    range), jumping past accepted strings so their bytes are not re-scanned. The
    NRBF string framing is distinctive enough that this recovers the string table
    cleanly (verified against the known content of QualResult.bin)."""
    i = 0
    n = len(buf)
    while i < n:
        length, j = _read_varint(buf, i)
        if length and _MIN_LEN <= length <= _MAX_LEN and j + length <= n:
            raw = buf[j:j + length]
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                i += 1
                continue
            if text and all(32 <= ord(c) < 127 for c in text):
                yield text
                i = j + length
                continue
        i += 1


def parse(path):
    """
    Parses a .NET BinaryFormatter sidecar into a bounded structured summary.

    Args:
        path (str): Path of the ``.bin`` file.

    Returns:
        Dict ``{'parser': 'dotnet', 'format': 'ms-nrbf', 'header': {...},
        'assemblies': [...], 'paths': [...], 'string_count': N}``. A file that is
        not an MS-NRBF stream yields ``{'parser': 'dotnet', 'format': None}``.

    """
    with open(path, "rb") as f:
        head = f.read(17)
        if not _is_nrbf(head):
            return {"parser": NAME, "format": None}
        buf = head + f.read()

    root, _hdr, major, minor = struct.unpack("<iiii", buf[1:17])
    assemblies, paths, seen = [], [], set()
    count = 0
    for text in _strings(buf):
        count += 1
        if text in seen:
            continue
        seen.add(text)
        if _ASSEMBLY.search(text):
            assemblies.append(text)
        elif _PATH.search(text):
            paths.append(text)
    return {
        "parser": NAME,
        "format": "ms-nrbf",
        "header": {"root_id": root, "major_version": major,
                   "minor_version": minor},
        "assemblies": assemblies,
        "paths": paths,
        "string_count": count,
    }


def canonical(parsed):
    """
    Promotes the identifier-bearing values to canonical names.

    Args:
        parsed (dict): Output of :func:`parse`.

    Returns:
        Dict with ``data_file`` if an analyzed-data path was found. The assembly
        versions are kept in :func:`parse` for context but not promoted - they
        are a data-analysis tool stack, a different notion from the acquisition
        ``software_version``.

    """
    out = {}
    # The analyzed data file: an absolute path ending in a .d run directory.
    candidates = [p for p in parsed.get("paths", [])
                  if re.search(r"\.[dD]\s*$", p) and ":\\" in p]
    if candidates:
        out["data_file"] = max(candidates, key=len)
    return out
