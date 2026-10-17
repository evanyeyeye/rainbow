"""
The excitation and emission a fluorescence channel's description names.

Every reader that types a fluorescence channel asks the same question of a
vendor's text, in each vendor's spelling: ChemStation and OpenLab write
"FLD1 A, Ex=230, Em=310", Empower "ACQUITY FLR ChA Ex280,Em340 nm". One parser
answers it for all of them, so no two readers can disagree about which
channel is a fluorescence one, or about its wavelengths.
"""
import re

_NUMBER = r"(\d+(?:\.\d+)?)"

EXCITATION_EMISSION_RE = re.compile(
    r"\bEx\s*[:=]?\s*" + _NUMBER + r"\s*(?:nm)?\s*[,/ ]\s*Em\s*[:=]?\s*"
    + _NUMBER, re.IGNORECASE)


def excitation_emission(text):
    """
    The ``(excitation, emission)`` wavelengths ``text`` names, in nm, or None.

    Args:
        text (str): A signal description, channel name, or cube label.

    Returns:
        tuple: Two floats, or None when the text names no Ex/Em pair.

    """
    match = EXCITATION_EMISSION_RE.search(text) if text else None
    if match is None:
        return None
    return float(match.group(1)), float(match.group(2))
