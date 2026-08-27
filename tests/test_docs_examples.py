"""
Runs the worked examples out of the ASM documentation pages.

A snippet on a documentation page is code a user will paste, so it is held to
the same standard as the code it demonstrates. Both worked examples were wrong:
they reached for one of two cube keys and raised KeyError on the third (every
MS channel), and the Agilent one hard-coded the liquid chromatography aggregate
three lines below recommending ``technique="GC"``. Extracting the block from the
page rather than copying it here means the test fails when the page drifts,
which is the only way a documentation test is worth anything.
"""
import re
import warnings

import pytest

import rainbow as rb


def _worked_example(page):
    """The python code-block on ``page`` that walks the exported document."""
    text = open("docs/source/asm/{}.rst".format(page), encoding="utf-8").read()
    blocks = re.findall(r"\.\. code-block:: python\n\n((?:(?:   .*)?\n)+)",
                        text)
    walking = [b for b in blocks if "measurement document" in b]
    assert len(walking) == 1, (
        "expected one document-walking example on {}.rst, found {}".format(
            page, len(walking)))
    return "\n".join(line[3:] for line in walking[0].splitlines())


@pytest.mark.parametrize("page,placeholder,fixture", [
    # A UV-only run, an MS run whose channel exports as a mass chromatogram,
    # and a run that lands in the gas chromatography aggregate.
    ("agilent", '"Caffeine.D"', "tests/inputs/red.D"),
    ("agilent", '"Caffeine.D"', "tests/inputs/green.D"),
    ("agilent", '"Caffeine.D"', "tests/inputs/yellow.D"),
    ("agilent", '"Caffeine.D"', "tests/inputs/pink.D"),
    ("waters", '"Caffeine.raw"', "tests/inputs/blue.raw"),
    ("waters", '"Caffeine.raw"', "tests/inputs/violet.raw"),
    ("waters", '"Caffeine.raw"', "tests/inputs/indigo.raw"),
])
def test_the_worked_example_runs(page, placeholder, fixture, capsys):
    source = _worked_example(page)
    assert placeholder in source
    source = source.replace(placeholder, repr(fixture))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        exec(compile(source, "docs/source/asm/{}.rst".format(page), "exec"),
             {"__name__": "__doc_example__"})

    # It is a worked example, so it has to produce the answer it advertises.
    assert capsys.readouterr().out.strip()


def test_the_documented_cube_keys_are_all_of_them():
    """ The examples pick a cube by name, so the list has to be complete.

    A measurement holds exactly one cube, under a key chosen by what the
    channel is. An example that knows only some of the keys raises KeyError on
    a run that happens to hold another, which is how both pages were broken.
    """
    import rainbow.asm

    emitted = set(re.findall(r'"([a-z -]*data cube)"',
                             open(rainbow.asm.__file__,
                                  encoding="utf-8").read()))
    assert emitted, "no cube keys found in the exporter"
    for page in ("agilent", "waters"):
        documented = set(re.findall(r'"([a-z -]*data cube)"',
                                    _worked_example(page)))
        assert documented == emitted, (
            "{}.rst knows {} but the exporter emits {}".format(
                page, sorted(documented), sorted(emitted)))


def test_the_sequence_sorting_recipe_orders_by_instant_not_by_text():
    """ The one place the guide says how to recover acquisition order.

    The vendors write day-first wall clock and name the month, so sorting the
    strings rainbow puts in metadata['date'] returns an order that is not
    chronological. The recipe on the page sorts the parsed instant instead.
    """
    # The day leads, so the text order is the day-of-month order.
    dates = ["01-Feb-22, 09:00:00",   # 2022, sorts first as text
             "31-Jan-06, 09:00:00"]   # 2006, sorts last as text

    assert sorted(dates) == dates
    assert sorted(dates, key=rb.iso_timestamp) == list(reversed(dates))


def test_iso_timestamp_is_the_documented_public_name():
    # sequences.rst tells the reader to call it, so it is API.
    assert "iso_timestamp" in rb.__all__
    assert rb.iso_timestamp("gibberish") is None
    assert rb.iso_timestamp(None) is None
    assert rb.iso_timestamp("27-Feb-18, 10:11:50") == "2018-02-27T10:11:50"
    # A recorded offset is kept; a supplied one only fills a missing zone.
    assert rb.iso_timestamp("3 Feb 22 11:22 am -0500", "+01:00") == \
        "2022-02-03T11:22:00-05:00"
    assert rb.iso_timestamp("27-Feb-18, 10:11:50", "Z") == \
        "2018-02-27T10:11:50+00:00"
    with pytest.raises(Exception, match="utc_offset"):
        rb.iso_timestamp("27-Feb-18, 10:11:50", "not an offset")
