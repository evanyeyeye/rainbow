"""
Read the sequence-level document of an Agilent sequence directory.

A sequence directory holds, alongside the injection .D subdirectories, a
``sequence.acaml`` describing the run as a whole: the instrument and its
modules (with serial numbers and firmware), the operator, the sample setups,
and the data-analysis results. This module reads the header part of that
document, the instrument and operator, which read_sequence merges onto a
DataSequence. The result graph (integrated peaks) is read separately.

``sequence.acaml`` is large (tens of MB), so it is read by streaming with
iterparse, never building the whole tree: the header stops as soon as the
instrument is seen, and the peak reader visits only the elements it needs.

When the optional ``lxml`` accelerator is installed, its ``iterparse`` is used
with a tag filter, so the parser only sees the handful of relevant elements
instead of every node. This is faster and lower-memory on large documents; the
``xml.etree`` fallback produces identical results.
"""
import os
import re
import xml.etree.ElementTree as ET

try:
    from lxml import etree as _lxml
    _PARSE_ERRORS = (ET.ParseError, _lxml.XMLSyntaxError)
except ImportError:
    _lxml = None
    _PARSE_ERRORS = (ET.ParseError,)


# The signal description embeds the acquisition wavelength, e.g.
# "DAD1 A, Sig=254,4 Ref=360,100".
_WAVELENGTH_RE = re.compile(r"Sig=(\d+)")

# Peak measures worth keeping, mapped to their ACAML element names. Each is
# stored on the element as a ``val`` attribute.
_PEAK_MEASURES = {
    "retention_time": "RetentionTime",
    "area": "Area",
    "area_percent": "AreaPercent",
    "height": "Height",
    "height_percent": "HeightPercent",
    "start_time": "BeginTime",
    "end_time": "EndTime",
    "symmetry": "Symmetry",
}


def _local(tag):
    """The local name of a tag, dropping any ``{namespace}`` prefix."""
    return tag.rsplit('}', 1)[-1]


def _child_text(element, name):
    """Text of the first direct child with the given local name, or None."""
    for child in element:
        if _local(child.tag) == name:
            return child.text
    return None


def _stream(path, names):
    """
    Yields ``(local_name, element)`` for elements whose local name is in
    ``names``, clearing each once the consumer is done with it so the tree
    never accumulates.

    With lxml, a tag filter limits the parse to just those elements; without
    it, every element is visited and filtered in Python. Either way the
    consumer sees the same sequence of elements.
    """
    wanted = set(names)
    # The consumer stops as soon as it has what it needs, which abandons this
    # generator mid-parse. Owning the handle and closing it in a finally means
    # an early break releases the file at once rather than at collection time.
    fileobj = open(path, "rb")
    try:
        if _lxml is not None:
            tags = tuple("{*}" + name for name in names)
            context = _lxml.iterparse(fileobj, events=("end",), tag=tags)
            for _, element in context:
                yield _local(element.tag), element
                element.clear()
                # Drop already-seen siblings so lxml does not retain the tree.
                while element.getprevious() is not None:
                    del element.getparent()[0]
        else:
            for _, element in ET.iterparse(fileobj, events=("end",)):
                name = _local(element.tag)
                if name in wanted:
                    yield name, element
                    element.clear()
    finally:
        fileobj.close()


def find(path):
    """Returns the sequence.acaml path inside a sequence directory, or None."""
    if not isinstance(path, str) or not os.path.isdir(path):
        return None
    for name in os.listdir(path):
        if name.lower() == "sequence.acaml":
            return os.path.join(path, name)
    return None


def find_result_document(path):
    """
    Returns a result document inside a directory, or None.

    OpenLab writes the data-analysis result graph either as a sequence-level
    ``sequence.acaml`` or, when there is none, as a per-injection
    ``sequence.acam_`` inside each .D. Both share the same shape, so the peak
    reader works on either.

    Args:
        path (str): Path of a sequence directory or an injection .D directory.

    Returns:
        str: Path of the result document, or None.

    """
    if not isinstance(path, str) or not os.path.isdir(path):
        return None
    available = {name.lower(): name for name in os.listdir(path)}
    for candidate in ("sequence.acaml", "sequence.acam_"):
        if candidate in available:
            return os.path.join(path, available[candidate])
    return None


def parse_header(path):
    """
    Reads the operator and instrument from a sequence.acaml file.

    Streams the document and stops once the instrument has been read, so the
    multi-megabyte result section is never loaded.

    Args:
        path (str): Path of the sequence.acaml file.

    Returns:
        dict: Any of ``operator`` and ``instrument`` that the document carries.
        ``instrument`` is ``{"name", "technique", "modules"}`` where each
        module is ``{"name", "type", "part_no", "serial_no", "firmware"}``.

    """
    metadata = {}
    try:
        for name, element in _stream(path, ("CreatedByUser", "Instrument")):
            if name == "CreatedByUser" and "operator" not in metadata:
                if element.text:
                    metadata["operator"] = element.text
            elif name == "Instrument":
                metadata["instrument"] = _instrument(element)
                break
    except _PARSE_ERRORS:
        return metadata
    return metadata


def parse_peaks(path):
    """
    Reads the integrated peaks from a sequence.acaml file.

    Walks the data-analysis result graph and resolves each peak back to the
    injection and channel it belongs to. The join runs through the signal: a
    SignalResult references a Signal, and the Signal records both the
    injection's .D folder name (its data-file path) and the acquisition
    wavelength (its description), so peaks land on the right injection and
    channel without any UUID bookkeeping in the caller.

    The document is streamed and its heavy elements are cleared as they are
    read, so memory stays modest despite the file size.

    Args:
        path (str): Path of the sequence.acaml file.

    Returns:
        dict: Maps each injection's .D folder name to a list of signal groups.
        Each group is ``{"signal", "wavelength", "description", "channel_file",
        "peaks"}``, where ``peaks`` is a list of measure dicts. Only signals
        with at least one peak are included.

    """
    signals = {}        # signal id -> signal info
    signal_results = []  # (signal id, [peak, ...]) for each non-empty result
    try:
        for name, element in _stream(path, ("Signal", "SignalResult")):
            if name == "Signal" and element.get("id"):
                info = _signal_info(element)
                if info:
                    signals[element.get("id")] = info
            elif name == "SignalResult":
                signal_id = None
                peaks = []
                for child in element:
                    child_tag = _local(child.tag)
                    if child_tag == "Signal_ID":
                        signal_id = child.get("id")
                    elif child_tag == "Peak":
                        peaks.append(_peak(child))
                if signal_id and peaks:
                    signal_results.append((signal_id, peaks))
    except _PARSE_ERRORS:
        pass

    by_injection = {}
    for signal_id, peaks in signal_results:
        signal = signals.get(signal_id)
        if not signal or not signal.get("d_name"):
            continue
        by_injection.setdefault(signal["d_name"], []).append({
            "signal": signal.get("name"),
            "wavelength": signal.get("wavelength"),
            "description": signal.get("description"),
            "channel_file": signal.get("channel_file"),
            "peaks": peaks,
        })
    return by_injection


def _signal_info(element):
    """Injection, channel, and wavelength from a <Signal> definition."""
    data_path = None
    for node in element.iter():
        if _local(node.tag) == "Path" and node.text:
            data_path = node.text
            break
    description = _child_text(element, "Description")
    name = _child_text(element, "Name")
    if data_path is None and name is None:
        return None

    d_name = channel_file = None
    if data_path:
        parts = data_path.replace("/", "\\").split("\\")
        d_name = parts[0]
        channel_file = parts[-1] if len(parts) > 1 else None

    wavelength = None
    if description:
        match = _WAVELENGTH_RE.search(description)
        if match:
            wavelength = float(match.group(1))

    return {"d_name": d_name, "channel_file": channel_file,
            "name": name, "wavelength": wavelength, "description": description}


def _peak(element):
    """The kept measures of a single <Peak>."""
    values = {}
    for child in element:
        values[_local(child.tag)] = child
    peak = {}
    for key, tag in _PEAK_MEASURES.items():
        child = values.get(tag)
        peak[key] = _value(child) if child is not None else None
    return peak


def _value(element):
    """A measure's numeric ``val`` attribute, falling back to text."""
    raw = element.get("val")
    if raw is None:
        return element.text
    try:
        return float(raw)
    except ValueError:
        return raw


def _instrument(element):
    """The instrument and its modules from an <Instrument> element."""
    modules = []
    for child in element:
        if _local(child.tag) != "Module":
            continue
        modules.append({
            "name": _child_text(child, "Name"),
            "type": _child_text(child, "Type"),
            "part_no": _child_text(child, "PartNo"),
            "serial_no": _child_text(child, "SerialNo"),
            "firmware": _child_text(child, "FirmwareRevision"),
        })
    return {
        "name": _child_text(element, "Name"),
        "technique": _child_text(element, "Technique"),
        "modules": modules,
    }
