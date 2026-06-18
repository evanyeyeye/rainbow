.. _performance:

Performance
===========

Reading a file is cheap; the time goes into the *decode loops* that turn an
encoded byte stream into numbers. A few strategies come up again and again
across the parsers. Here they are, with the places they are used.

Read the file once, then view it as arrays
------------------------------------------

Binary formats usually store their records at a fixed stride, so a field at a
fixed offset across every record is just a strided NumPy view, with no Python
loop and no per-record ``struct.unpack``. *rainbow* reads the whole file (or the
whole data block) once and lays a ``numpy.ndarray`` over the bytes with an
explicit ``strides`` argument, then decodes bit-fields with array shifts and
masks.

- The Agilent ``OL`` ``.uv`` decoder (``decode_uv_array``) reads its
  retention-time by wavelength block of doubles as one strided view instead of
  looping value by value.
- The ``.ms`` decoder (``parse_ms``) views the *m/z* and intensity halves of
  each pair as two strided ``uint16`` arrays over the raw bytes.
- The Waters ``_FUNC.DAT`` decoders read their 6- and 8-byte segments the same
  way, unpacking the packed *m/z* and intensity fields with ``>>`` and ``&``.

Bin with an integer histogram, not a sort
-----------------------------------------

A scan's spectrum is a flat list of ``(label, value)`` pairs that has to become
a ``(retention time, label)`` matrix, summing duplicate labels within a scan.
The obvious ``numpy.unique`` + ``searchsorted`` + ``numpy.add.at`` sorts every
data point, and that sort dominates on large files. When the labels are already
quantized (rounded *m/z*, integer wavelengths) the sort is avoidable: map each
label to an integer bin, mark the bins that occur, and scatter-add into the
dense grid in one pass.

This came up often enough to factor out. ``rainbow._binning.bin_datapairs`` is
shared by the Waters ``_FUNC.DAT`` decoders and the Agilent ``.ms`` decoders
(``parse_ms`` and ``parse_ms_partial``), and the MassHunter ``MSProfile.bin``
grid is built the same way.

Precompute tiny bit-field math into a lookup table
--------------------------------------------------

When a per-value computation depends only on a small bit-field, there are just a
handful of distinct results, so compute them once into a small array and index
it rather than running ``numpy.power`` over the whole column.

- The ``.ms`` intensity scale is ``8 ** head``, where ``head`` is a 2-bit field
  (four possible values): a four-element table.
- The Waters 6-byte ``_FUNC.DAT`` decode scales *m/z* by ``2 ** e`` and
  intensities by ``4 ** e`` from 5- and 4-bit exponent fields, using two small
  tables (``_FUNC6_KEY_POW2`` and ``_FUNC6_VAL_POW4``).

Compile the loops you cannot vectorize
--------------------------------------

Some decoders are irreducibly sequential: a running accumulator whose state
carries from one value to the next, with a data-dependent stride (a sentinel
value means "the next few bytes are an absolute reset, not a delta"). Each step
needs the previous one, so there is no array form. The only lever left is to
take the Python interpreter out of the inner loop with a small compiled
extension.

This is the one *rainbow* reaches for most: three times so far, all in Cython,
each roughly **100x faster** than its pure-Python twin.

- ``_uvdelta.pyx``: the Agilent diode-array ``.uv`` delta decode.
- ``_chdelta.pyx``: the Agilent ``.ch`` channel (CAD/ELSD/UV) delta decode.
- ``_msprofile.pyx``: the MassHunter ``MSProfile.bin`` run-length decode.

Each follows the same shape. It is **optional**: the build compiles it when a C
compiler and Cython are present and silently skips it otherwise, so a missing
extension never breaks an install (prebuilt PyPI wheels include them). It has a
**pure-Python twin** that runs when the extension is absent, with identical
output; check which path is live with, e.g.,
``rainbow.agilent.chemstation._chdelta_fast is not None``. And it is held to
**bit-identical output** by ``tests/test_accelerator.py``, which compares the
two paths on every fixture and checks the compiled path fails safely on
truncated input rather than reading out of bounds.

One measurement note, since these loops are where it bites: ``cProfile``'s
per-call overhead makes a million-iteration byte loop look far heavier than it
runs in practice, so confirm a hotspot against wall-clock before deciding it is
worth compiling.
