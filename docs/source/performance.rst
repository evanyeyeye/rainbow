.. _performance:

Performance
===========

Most of what *rainbow* does is cheap: find the right files, read them, and
reshape bytes into NumPy arrays. Parsing time is dominated by a handful of
*decode loops* — the inner loops that turn an encoded byte stream into numbers.
This page collects the strategies *rainbow* uses to keep those fast, and the
considerations worth weighing when you optimize an existing decoder or add a
new file format. It is not a record of specific changes (that is the
changelog); it is the reasoning behind them.

The golden rule
---------------

**An optimization must not change the output.** Every fast path in *rainbow* is
bit-identical to a straightforward reference implementation — or, where
floating-point accumulation order legitimately varies, identical within a
tight, stated tolerance. So before optimizing, write the obvious correct
decoder and keep it: it becomes both the fallback and the oracle your tests
compare against. Speed that you cannot prove is faithful is not worth shipping.

Profile before you optimize
---------------------------

Measure where time actually goes; intuition is unreliable here.

- Prefer **wall-clock timing of a representative corpus** over micro-benchmarks.
- ``cProfile`` is good for *attribution*, but read it with care: it adds
  per-call overhead, so a loop that makes millions of tiny calls (``f.read``,
  ``struct.unpack``, ``list.append``) looks far heavier under the profiler than
  it is in reality. Confirm a suspected hotspot against unprofiled wall-clock
  before committing to a rewrite.
- A flat profile — no single dominant function — is a signal to stop. The
  remaining wins are diminishing, and each adds risk for a few percent.

Reach for NumPy first
---------------------

Most binary formats store their records at a fixed stride. When they do, you
rarely need a Python loop at all:

- **Read the whole file once** (``f.read()``) and view it, rather than issuing
  thousands of small ``f.read``/``struct.unpack`` calls — the call overhead
  alone often dominates. A ``numpy.ndarray`` with an explicit ``strides``
  argument, or ``numpy.frombuffer``, exposes one field at a fixed offset across
  every record as a single array.
- **Decode bit-fields with vectorized operations.** Shifts and masks (``>>``,
  ``&``) applied to a whole array replace a per-value unpack.

Binning without sorting
-----------------------

Mass spectra arrive as a flat list of ``(label, value)`` pairs that must be
laid out as a ``(retention time × label)`` matrix, summing duplicate labels
within a scan. The obvious approach — ``numpy.unique`` to find the columns,
``searchsorted`` to place each pair, ``numpy.add.at`` to accumulate — sorts
every data point, and that sort is the bottleneck on large files. When the
labels are already quantized (rounded *m/z*, integer wavelengths), an **integer
histogram** does the same job in one pass with no sort: map each label to a
bin, mark the bins that occur, and scatter-add into the dense grid. The shared
helper ``rainbow._binning`` does this for both vendors; note that it
deliberately preserves the labels' dtype so the output is identical to the
sort-based path.

Lookup tables for tiny fields
-----------------------------

If a per-value computation depends only on a small bit-field — say a 2- to
5-bit exponent — there are only a handful of distinct results. Precompute them
once into a small array and index it, rather than calling ``numpy.power`` over
the whole column. *rainbow* uses this for the Agilent ``.ms`` and Waters
``_FUNC.DAT`` intensity scales, where the exponent is a 2- or 4-bit field.

When you cannot vectorize: compile the loop
-------------------------------------------

Some decoders are inherently sequential: a **running accumulator** whose state
carries from one value to the next, usually with a **data-dependent stride** (a
sentinel value means "the next few bytes are an absolute reset, not a delta").
These cannot be expressed as array operations — each step depends on the last.
The remaining lever is to take the Python interpreter out of the inner loop
with a small compiled extension.

*rainbow* ships a few such accelerators, written in Cython
(``rainbow/agilent/_uvdelta.pyx`` for the ``.uv`` decode, ``_chdelta.pyx`` for
the ``.ch`` channel decode, and ``rainbow/agilent/_msprofile.pyx`` for the
MassHunter ``MSProfile.bin`` run-length decode), each roughly **100× faster**
than its pure-Python counterpart. They follow a deliberate pattern worth
copying:

- **Optional.** The build compiles them when a C compiler and Cython are
  present and silently skips them otherwise — a missing extension never breaks
  an install. Prebuilt PyPI wheels include them.
- **Transparent fallback.** When an extension is absent the pure-Python decoder
  runs instead, with identical output. You can check which path is active, e.g.
  ``rainbow.agilent.chemstation._chdelta_fast is not None`` (likewise
  ``_uvdelta_fast`` and ``rainbow.agilent.masshunter._msprofile_fast``).
- **Bit-identical and tested.** ``tests/test_accelerator.py`` asserts the
  compiled and pure-Python paths agree on every fixture, and that the compiled
  path fails safely on truncated input rather than reading out of bounds.

Reserve this tool for loops that genuinely cannot be vectorized: a compiled
extension is more to build, ship, and maintain than an array expression.

Adding a new format
-------------------

A rough order of operations that keeps you both fast and correct:

1. **Get it right first.** Write the clear pure-Python decoder and validate it
   against ground truth — an instrument export, a vendor tool, a known sample.
   Add a small fixture and a test.
2. **Profile a real file.** Find the loop that actually dominates; don't guess.
3. **Try to vectorize it.** Is the record stride fixed? Can the hot computation
   run over whole arrays — strided views, shifts and masks, an integer
   histogram, a lookup table? This handles the large majority of cases.
4. **Only if it is inherently sequential, compile it.** Add a Cython inner loop
   beside the pure-Python one, keep the latter as the fallback, and wire the
   extension into the optional build.
5. **Lock it down.** A parity test comparing the fast and reference paths, on a
   fixture small enough to live in the repository, is what lets the next person
   optimize without fear.
