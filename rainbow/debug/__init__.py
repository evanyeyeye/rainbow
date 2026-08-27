"""
Debug metadata subsystem.

rainbow's normal read path surfaces a lean set of metadata to keep overhead low.
A vendor run directory, however, ships many sidecar files (registers, INIs,
audit trails, method dumps, ...) carrying far more context: instrument module
serials, firmware/software versions, the acquisition operator, method-save
details, injection volume, signal optics, and so on. This subsystem decodes
those sidecars into structured fields on demand.

Two entry points:

    from rainbow import debug

    debug.inspect(path)   # {relpath: structured metadata} - faithful per file
    debug.fields(path)    # one merged canonical run-metadata record

Each format has a parser module exposing ``matches(name)``, ``parse(path)``
(full, lossless structure), and ``canonical(parsed)`` (the well-known keys
promoted to shared canonical names). The canonical field vocabulary grows as
formats are added; see ``docs/source/debug/`` for the per-format catalog and the
depth/output-shape decisions behind each parser.

Read-only; nothing is ever written back.
"""
import os
import tempfile
import zipfile

__all__ = ["inspect", "fields"]

from rainbow.debug import ini
from rainbow.debug import xml
from rainbow.debug import chemstation_text
from rainbow.debug import chemstation_header
from rainbow.debug import dotnet
from rainbow.debug import reg
from rainbow.debug import method
from rainbow.debug import waters_header
from rainbow.debug import waters_inf
from rainbow.debug import mzxml

# Parser registry. Each module: matches(name)->bool, parse(path)->dict,
# canonical(parsed)->dict. Order matters only if patterns overlap.
_PARSERS = [ini, xml, chemstation_text, chemstation_header, dotnet, reg, method,
            waters_header, waters_inf, mzxml]

# Canonical fields that accumulate across files instead of taking the first
# value (a run legitimately has several serials / devices / users / signals).
_LIST_FIELDS = ("serials", "signal_optics", "devices", "computers", "users")

# Container archives the walker transparently steps into, treating each member
# like a file in a sub-directory. An Agilent OpenLab ``.dx`` is an OPC (zip)
# package; rb.read decodes its signal *data*, while debug mines the per-signal
# ChemStation *headers* (operator, full method path, signal optics) that rb.read
# drops. The manifest (injection.acmd) is left to rb.read to avoid duplicating
# its job; debug only reaches the sidecar identity inside the archive.
_ARCHIVE_EXTS = (".dx",)


def _validate(path):
    """Raises if ``path`` is not a readable file or directory.

    Mirrors ``rb.read``'s contract: a debug entry point accepts a run directory
    or a single sidecar file, and anything else is an error rather than a
    silently empty result.
    """
    if not isinstance(path, str) or not os.path.exists(path):
        raise Exception(f"{path} is not a file or directory.")


def _iter_files(path):
    """Yields ``(abspath, relpath)`` for every file under ``path`` (or the file
    itself), sorted for stable output. A ``.dx`` archive (file or nested) is
    transparently descended into, yielding its identity-bearing members."""
    if os.path.isfile(path):
        if path.lower().endswith(_ARCHIVE_EXTS):
            yield from _iter_archive(path, os.path.basename(path))
        else:
            yield path, os.path.basename(path)
        return
    # Sorted by relpath across the whole tree, not per directory: os.walk lists
    # a directory's own files before descending, and hands back sibling
    # directories in readdir order, which is the creation order on APFS and a
    # hash order on ext4. fields() keeps the first value it sees for a scalar,
    # so an unsorted walk makes the reported instrument and method depend on the
    # filesystem the run happens to sit on.
    entries = []
    for dirpath, dirnames, names in os.walk(path):
        dirnames.sort()
        for name in names:
            full = os.path.join(dirpath, name)
            entries.append((os.path.relpath(full, path), full, name))
    for rel, full, name in sorted(entries):
        if name.lower().endswith(_ARCHIVE_EXTS):
            yield from _iter_archive(full, rel)
        else:
            yield full, rel


def _iter_archive(archive_path, relbase):
    """Yields ``(temp_path, relpath)`` for each recognized member of a ``.dx``
    (OPC zip) package.

    Only members a parser actually claims are extracted - the GUID-named binary
    signal payloads (``.CH``/``.UV``) carry the ChemStation identity headers, so
    they are kept. The OPC packaging parts (the ``[Content_Types].xml`` map and
    the ``_rels`` relationship files), the numeric ``.IT`` traces, and the
    manifest (``injection.acmd``, rb.read's territory) carry no instrument
    identity and are skipped without extraction. Member relpaths are reported as
    ``<archive>!<member>`` to mark the boundary.

    The temp directory lives for the life of this generator: the ``with`` stays
    open while suspended at each ``yield``, so a member file is still on disk
    when the caller parses it, and is cleaned up once iteration completes.
    """
    try:
        archive = zipfile.ZipFile(archive_path)
        members = archive.namelist()
    except Exception:
        # An archive rainbow cannot open contributes nothing, and must not stop
        # the walk reaching the sidecars beside it. namelist() is inside the
        # guard because reading the central directory is where a truncated or
        # otherwise malformed package fails.
        return
    with archive, tempfile.TemporaryDirectory() as tmp:
        for member in members:
            base = os.path.basename(member)
            # OPC packaging parts are pure container plumbing, no identity.
            low = member.lower()
            if base.lower() == "[content_types].xml" or "_rels/" in low:
                continue
            if not base or _dispatch(base) is None:
                continue
            dest = os.path.join(tmp, base)
            try:
                with open(dest, "wb") as out:
                    out.write(archive.read(member))
            except Exception:
                # One member is skipped, never the archive and never the walk.
                # zipfile.read raises more than a bad-zip error: an unsupported
                # compression method (deflate64) is a NotImplementedError and an
                # encrypted member a RuntimeError, neither of which is an
                # OSError. This generator is advanced by the caller's `for`
                # header, outside its per-file try, so anything escaping here
                # takes down the whole inspection rather than one sidecar.
                continue
            yield dest, "{}!{}".format(relbase, member)


def _dispatch(name):
    """Returns the parser module that handles ``name``, or None."""
    for module in _PARSERS:
        if module.matches(name):
            return module
    return None


def inspect(path):
    """
    Decodes every recognized metadata sidecar under ``path`` into its full
    structure.

    Args:
        path (str): Path of a run directory (or a single sidecar file).

    Returns:
        Dict ``{relpath: parsed}`` where ``parsed`` is the parser's faithful,
        lossless structure. A file that fails to parse maps to
        ``{'parser': ..., 'error': ...}`` rather than being dropped.

    """
    _validate(path)
    out = {}
    for full, rel in _iter_files(path):
        module = _dispatch(os.path.basename(full))
        if module is None:
            continue
        try:
            out[rel] = module.parse(full)
        except ImportError:
            # A missing dependency is the caller's environment, not a bad file:
            # reporting it per-file would bury it in every entry at once.
            raise
        except Exception as e:  # never let one bad sidecar abort the inspection
            out[rel] = {"parser": module.NAME, "error": repr(e)}
    return out


def fields(path):
    """
    Merges every recognized sidecar under ``path`` into one canonical
    run-metadata record.

    List-valued fields (e.g. ``serials``) accumulate unique values across
    files; scalar fields take the first non-empty value seen. Each merged value
    records which file(s) it came from under the ``_sources`` key.

    Args:
        path (str): Path of a run directory (or a single sidecar file).

    Returns:
        Dict of canonical fields, plus ``_sources`` mapping each field to the
        relpath(s) that supplied it.

    """
    _validate(path)
    merged = {}
    sources = {}
    for full, rel in _iter_files(path):
        module = _dispatch(os.path.basename(full))
        if module is None:
            continue
        try:
            contributed = module.canonical(module.parse(full))
        except ImportError:
            # Otherwise a missing dependency looks like a run with no metadata.
            raise
        except Exception:
            continue
        for key, value in contributed.items():
            if key in _LIST_FIELDS:
                bucket = merged.setdefault(key, [])
                for item in (value if isinstance(value, list) else [value]):
                    if item not in bucket:
                        bucket.append(item)
                        sources.setdefault(key, []).append(rel)
            elif key not in merged and value not in (None, ""):
                merged[key] = value
                sources[key] = rel
    if merged:
        merged["_sources"] = sources
    return merged
