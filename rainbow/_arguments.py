"""
Shared handling for the keyword arguments every read entry point takes.

A renamed argument that simply disappears leaves the caller with "unexpected
keyword argument" and no idea what to write instead, so every public read entry
point routes removed names through here and answers with the replacement. The
rules live in one place because rb.read, rb.read_sequence and the vendor read
functions are all documented as entry points, and a caller who finds the
migration message on one and not the others learns the wrong thing.

The same argument applies to the two m/z controls, which is why validating them
lives here too rather than in rb.read alone: an unchecked bin_width does not
raise further down, it silently returns a grid whose labels no longer name its
columns.
"""
import math

from rainbow._binning import _MAX_LABEL_DECIMALS as MAX_DISPLAY_PRECISION

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


def validate_bin_width(bin_width):
    """Rejects a ``bin_width`` that is not a finite positive number.

    Infinity passes a ``> 0`` test and then divides every m/z to zero, so the
    run comes back as one column labelled NaN, holding the whole signal and
    matching any ion asked for. NaN fails every comparison instead, and reaches
    the parser's overflow guard, which then reports a width that is too small.
    Both are the collapse that guard exists to refuse, so both are refused here.
    """
    if bin_width is None:
        return
    if (isinstance(bin_width, bool)
            or not isinstance(bin_width, (int, float))
            or not math.isfinite(bin_width) or bin_width <= 0):
        raise Exception(f"Invalid bin_width: {bin_width}.")


def validate_display_precision(display_precision):
    """Rejects a ``display_precision`` that is not 'auto' or a whole count.

    Bounded above as well as below. Past about 306 decimals numpy's rounding
    overflows and every label becomes NaN, which quietly breaks the one thing
    the labels are for: naming their columns one to one. The bound is set at
    the point a float64 label stops carrying more information rather than at
    the point it breaks, since the decimals between the two say nothing.
    """
    if display_precision == 'auto':
        return
    if (isinstance(display_precision, bool)
            or not isinstance(display_precision, int)
            or display_precision < 0):
        raise Exception(
            f"Invalid display_precision: {display_precision!r}. Use 'auto' or "
            f"a non-negative integer.")
    if display_precision > MAX_DISPLAY_PRECISION:
        raise Exception(
            f"Invalid display_precision: {display_precision!r}. A float64 m/z "
            f"label carries no more than {MAX_DISPLAY_PRECISION} decimals.")


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
