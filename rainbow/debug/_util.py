"""
Shared helpers for the debug metadata parsers.

Self-contained on purpose: the debug subsystem ships inside the ``rainbow``
package, so it must not import the developer-only tools under ``tools/``.
"""


def decode_text(raw):
    """
    Decodes a metadata text blob whose encoding is not known in advance.

    Agilent/Waters sidecars are a mix of UTF-8, UTF-16LE, and UTF-16BE (often
    with a BOM, sometimes only inferable from interleaved NUL bytes). Returns a
    ``str`` decoded with the best-guess encoding, never raising.

    Args:
        raw (bytes): Raw file contents.

    Returns:
        Decoded text.

    """
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        enc = "utf-16"
    elif b"encoding=\"utf-16\"" in raw[:120].lower() \
            or b"encoding='utf-16'" in raw[:120].lower():
        enc = "utf-16"
    elif b"\x00" in raw[:64]:
        enc = "utf-16-le"
    elif raw[:3] == b"\xef\xbb\xbf":
        enc = "utf-8-sig"
    else:
        enc = "utf-8"
    try:
        return raw.decode(enc, "replace")
    except (LookupError, ValueError):
        return raw.decode("latin-1", "replace")


def require_lxml(etree, what):
    """
    Raises a clear error when a debug parser is used without lxml installed.

    The debug parsers recover structure from malformed and mis-encoded
    sidecars, which the standard library's parser cannot do, so lxml is a real
    requirement here rather than an accelerator. Callers pass the ``etree`` they
    imported, which is None when lxml is absent.

    Args:
        etree: The imported lxml etree module, or None.
        what (str): What the caller was trying to read, for the message.

    """
    if etree is None:
        raise ImportError(
            f"Reading {what} needs lxml, which recovers structure from the "
            f"malformed sidecars vendors write. rainbow installs it by "
            f"default, so this environment has had it removed; reinstall it "
            f"with 'pip install lxml'.")
