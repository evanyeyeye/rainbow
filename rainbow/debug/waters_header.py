"""
Parser for the Waters MassLynx ``_HEADER.TXT`` sidecar found in every ``.raw``
run directory.

It is a flat ``$$ Key: Value`` text file (ASCII, CRLF) that MassLynx writes
alongside the binary ``_FUNC*.DAT`` traces. rainbow's Waters reader
(:mod:`rainbow.waters.masslynx`) opens it only to recover the m/z calibration
coefficients; it ignores the identity fields. This is the single richest
metadata file in a Waters run: the instrument (model and serial), the acquired
data-file name/date/time, the sample description and id, the acquiring user, the
vial (bottle) position, and the inlet/MS/tune method paths.

The parse is full and lossless: every ``$$`` line is preserved verbatim.
:func:`canonical` then promotes the well-known keys to the canonical field names
shared across the debug subsystem (the same vocabulary the Agilent parsers emit,
so a mixed corpus merges cleanly).
"""
from rainbow.debug._util import decode_text

NAME = "waters_header"


def matches(name):
    """Returns True for the Waters ``_HEADER.TXT`` sidecar."""
    return name.lower() == "_header.txt"


def parse(path):
    """
    Parses ``_HEADER.TXT`` into its flat key/value structure.

    Each content line has the form ``$$ Key: Value``. The key is split on the
    first ``:`` only, so a value's own colons (a ``C:\\MassLynx\\...`` path, a
    ``10:11:45`` clock) stay intact. Values are kept verbatim as
    strings, including the empty string for keys MassLynx leaves blank. A later
    duplicate key (none seen in the wild) overwrites the earlier one.

    Args:
        path (str): Path of the _HEADER.TXT file.

    Returns:
        Dict ``{'parser': 'waters_header', 'header': {key: value}}``.

    """
    with open(path, "rb") as f:
        raw = f.read()
    text = decode_text(raw)

    header = {}
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("$$"):
            continue
        s = s[2:].strip()
        if ":" not in s:
            continue
        key, value = s.split(":", 1)
        header[key.strip()] = value.strip()
    return {"parser": NAME, "header": header}


def _split_instrument(value):
    """Splits the ``Instrument`` value ``MODEL#SERIAL`` into ``(model, serial)``.

    The serial is often the placeholder ``NotSet`` (e.g. ``ACQ-QDA#NotSet``),
    which is treated as absent. Returns ``(model_or_None, serial_or_None)``.
    """
    model, _, serial = value.partition("#")
    model = model.strip() or None
    serial = serial.strip()
    if not serial or serial.lower() == "notset":
        serial = None
    return model, serial


def canonical(parsed):
    """
    Projects the well-known ``_HEADER.TXT`` keys onto the shared canonical field
    names.

    Args:
        parsed (dict): Output of :func:`parse`.

    Returns:
        Dict of canonical fields present in this file (blank values omitted).
        ``serials`` is a list (a Waters run reports at most one here); the rest
        are scalars.

    """
    h = parsed["header"]

    def get(key):
        v = h.get(key, "")
        return v.strip() if isinstance(v, str) else v

    out = {}

    model, serial = _split_instrument(get("Instrument"))
    if model:
        out["instrument"] = model
    if serial:
        out["serials"] = [serial]

    # Acquired Date + Acquired Time -> a single timestamp (either may be blank).
    date, time = get("Acquired Date"), get("Acquired Time")
    acquired = " ".join(p for p in (date, time) if p)
    if acquired:
        out["acquired"] = acquired

    # Acquired Name is the run/data-file basename; Sample Description is the
    # human label. Mirror the Agilent split of data_file vs sample.
    if get("Acquired Name"):
        out["data_file"] = get("Acquired Name")
    if get("Sample Description"):
        out["sample"] = get("Sample Description")
    if get("SampleID"):
        out["sample_id"] = get("SampleID")
    if get("User Name"):
        out["operator"] = get("User Name")
    if get("Bottle Number"):
        out["vialpos"] = get("Bottle Number")

    # Method: prefer the MS method, else the inlet method (both full paths).
    method = get("MS Method") or get("Inlet Method")
    if method:
        out["method"] = method

    return out
