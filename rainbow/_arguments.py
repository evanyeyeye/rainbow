"""
Shared handling for keyword arguments that earlier releases accepted.

A renamed argument that simply disappears leaves the caller with "unexpected
keyword argument" and no idea what to write instead, so every public read entry
point routes removed names through here and answers with the replacement. The
rules live in one place because rb.read, rb.read_sequence and the vendor read
functions are all documented as entry points, and a caller who finds the
migration message on one and not the others learns the wrong thing.
"""

_REMOVED_ARGUMENTS = {
    'precision': (
        "precision was split in 1.5.0 into bin_width (the lossy m/z grid, in "
        "daltons) and display_precision (label rounding, in decimals). "
        "precision=N behaved like bin_width=10**-N; pass that for the same "
        "data, or display_precision=N to only round the labels. See "
        "rb.mz_resolution(path) for how fine a bin_width a run supports."),
    'prec': (
        "prec was renamed to precision in 1.3.0 and split in 1.5.0 into "
        "bin_width and display_precision; prec=N behaved like "
        "bin_width=10**-N."),
}


def reject_removed_arguments(function, removed):
    """Raises for a removed keyword argument, naming what replaced it."""
    for name in removed:
        explanation = _REMOVED_ARGUMENTS.get(name)
        if explanation:
            raise TypeError(
                "{}() no longer takes {}. {}".format(
                    function, name, explanation))
    raise TypeError("{}() got an unexpected keyword argument {!r}".format(
        function, sorted(removed)[0]))
