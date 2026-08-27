"""
Parser for the Agilent ``.ini`` metadata sidecars (``GC.ini``, ``method.ini``,
``PRE_POST.INI``, ``EZXSMETH.INI``, ``CSlbk.ini``, ``tgtmass.ini``, ...).

These are plain ``[section]`` / ``key=value`` files (frequently UTF-16) that
rainbow's data parsers ignore. They carry instrument module serials, firmware
and software versions, the method-save operator, injection volume, and signal
optics. The parse is full and lossless: every section and key is preserved
verbatim; :func:`canonical` then promotes the well-known keys to the canonical
field names shared across the debug subsystem.
"""
from rainbow.debug._util import decode_text

NAME = "ini"


def matches(name):
    """Returns True if ``name`` is an INI sidecar this module handles."""
    return name.lower().endswith(".ini")


def parse(path):
    """
    Parses an INI sidecar into its full section/key structure.

    Values are kept verbatim as strings; a key that repeats within a section
    becomes a list (e.g. the two ``CS=`` lines in ``CSlbk.ini``). Keys that
    appear before any ``[section]`` header are collected under the ``""`` key.

    Args:
        path (str): Path of the .ini file.

    Returns:
        Dict ``{'parser': 'ini', 'sections': {section: {key: value}}}``.

    """
    with open(path, "rb") as f:
        raw = f.read()
    text = decode_text(raw)

    sections = {"": {}}
    current = ""
    for line in text.splitlines():
        s = line.strip()
        if not s or s[0] in ";#":
            continue
        if s[0] == "[" and s[-1] == "]":
            current = s[1:-1].strip()
            sections.setdefault(current, {})
            continue
        if "=" not in s:
            continue
        key, value = s.split("=", 1)
        key, value = key.strip(), value.strip()
        bucket = sections[current]
        if key in bucket:
            if isinstance(bucket[key], list):
                bucket[key].append(value)
            else:
                bucket[key] = [bucket[key], value]
        else:
            bucket[key] = value

    if not sections[""]:
        del sections[""]
    return {"parser": NAME, "sections": sections}


def canonical(parsed):
    """
    Projects the well-known INI keys onto the shared canonical field names.

    Args:
        parsed (dict): Output of :func:`parse`.

    Returns:
        Dict of canonical fields present in this file (others omitted). List
        fields (``serials``, ``signal_optics``) accumulate; scalar fields take
        the first value seen.

    """
    # Flatten to a case-insensitive view; keep the raw sections for SmartCard.
    flat = {}
    for keys in parsed["sections"].values():
        for key, value in keys.items():
            flat.setdefault(key.lower(), value)

    out = {}
    serials = []
    optics = []

    if "gc.sn" in flat:
        serials.append(flat["gc.sn"])
    # SmartCard=AGILENT TECHNOLOGIES,5977,SN00000012,6.00.34
    #           vendor              ,model,serial    ,firmware
    smartcard = flat.get("smartcard")
    if isinstance(smartcard, str) and "," in smartcard:
        parts = [p.strip() for p in smartcard.split(",")]
        if len(parts) >= 2 and parts[1]:
            out.setdefault("instrument", parts[1])
        if len(parts) >= 3 and parts[2]:
            serials.append(parts[2])
    if "uvasig" in flat:
        optics.append(flat["uvasig"])

    if serials:
        out["serials"] = serials
    if optics:
        out["signal_optics"] = optics
    if "methsavewho" in flat:
        out["operator"] = flat["methsavewho"]
    if "methsavetime" in flat:
        out["method_save_time"] = flat["methsavetime"]
    if "acqversion" in flat:
        out["software_version"] = flat["acqversion"]
    elif "application" in flat:
        out["software_version"] = flat["application"]
    if "injvolume" in flat:
        out["injection_volume"] = flat["injvolume"]
    if "date" in flat:
        out["acquired"] = flat["date"]
    return out
