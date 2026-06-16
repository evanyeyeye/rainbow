# cython: boundscheck=False, wraparound=False, cdivision=True, language_level=3
"""
Compiled accelerator for the Agilent ``.uv`` LC-delta decode loop.

The pure-Python decoders in :mod:`rainbow.agilent.chemstation` spend almost all
of their time in a per-sample loop over the absorbance "cube" (retention times
x wavelengths). For large diode-array (DAD) files this dominates parsing -- on
the order of 100ms per file. The encoding is inherently sequential (a running
accumulator with a sentinel that resets it) and its record stride is
data-dependent, so it cannot be vectorized with NumPy; only a compiled inner
loop removes the interpreter overhead. This module is that loop, written to
produce output bit-identical to the pure-Python reference.

It is imported opportunistically by ``chemstation.py``. If the extension was
not built (no compiler or no Cython at install time), the package falls back to
the pure-Python implementation transparently.

Format
------
Each retention time is stored as a 22-byte header (the 32-bit time sits 4 bytes
in) followed by ``nwl`` little-endian samples. Each sample is a 16-bit delta
added to a running accumulator, *unless* it equals ``-0x8000`` (the sentinel),
in which case the following 32-bit little-endian integer is the new absolute
accumulator value. The ``.uv`` fields are little-endian, which matches every
platform NumPy ships wheels for, so values are read with a native ``memcpy``.
"""

import numpy as np
from libc.string cimport memcpy

# 16-bit sentinel: the next sample is an absolute 32-bit value, not a delta.
cdef short _SENTINEL = -0x8000
# Per-record header: 4 pad bytes, 4-byte time, 14 pad bytes.
cdef Py_ssize_t _HEADER = 22


cdef inline Py_ssize_t _decode_row(const unsigned char[::1] buf, Py_ssize_t off,
                                   Py_ssize_t n, int nwl,
                                   long long[:, ::1] data,
                                   Py_ssize_t row) except -1:
    """Decode one row of ``nwl`` samples into ``data[row]``; return new offset.

    Raises ``ValueError`` if the buffer ends mid-row -- mirroring the exception
    the pure-Python path would raise on a short read, rather than reading out of
    bounds (this module disables Cython's automatic bounds checks for speed).
    """
    cdef int j
    cdef long long acc = 0
    cdef short ci
    cdef int v
    for j in range(nwl):
        if off + 2 > n:
            raise ValueError("truncated Agilent .uv delta stream")
        memcpy(&ci, &buf[off], 2)
        off += 2
        if ci == _SENTINEL:
            if off + 4 > n:
                raise ValueError("truncated Agilent .uv delta stream")
            memcpy(&v, &buf[off], 4)
            off += 4
            acc = v
        else:
            acc += ci
        data[row, j] = acc
    return off


cdef inline Py_ssize_t _scan_row(const unsigned char[::1] buf, Py_ssize_t off,
                                 Py_ssize_t n, int nwl):
    """Return the offset just past a complete row, or -1 if it would overrun.

    Used to count rows in a variable-length (partial) stream without decoding.
    """
    cdef int j
    cdef short ci
    for j in range(nwl):
        if off + 2 > n:
            return -1
        memcpy(&ci, &buf[off], 2)
        off += 2
        if ci == _SENTINEL:
            if off + 4 > n:
                return -1
            off += 4
    return off


def decode_uv_delta(const unsigned char[::1] buf, Py_ssize_t data_start,
                    int num_times, int nwl):
    """Decode a fixed-length ``.uv`` delta stream with a known row count.

    Args:
        buf: The whole file as a bytes-like buffer.
        data_start: Offset of the first record.
        num_times: Number of retention times (rows) to decode.
        nwl: Number of wavelengths (samples) per row.

    Returns:
        ``(times, data)`` where ``times`` is a ``uint32`` array of raw times and
        ``data`` is an ``(num_times, nwl)`` ``int64`` array of accumulated values.
    """
    times_arr = np.empty(num_times, dtype=np.uint32)
    data_arr = np.empty((num_times, nwl), dtype=np.int64)
    cdef unsigned int[::1] times = times_arr
    cdef long long[:, ::1] data = data_arr

    cdef Py_ssize_t n = buf.shape[0]
    cdef Py_ssize_t off = data_start
    cdef Py_ssize_t i
    cdef unsigned int t

    for i in range(num_times):
        if off + _HEADER > n:
            raise ValueError("truncated Agilent .uv delta stream")
        memcpy(&t, &buf[off + 4], 4)
        times[i] = t
        off = _decode_row(buf, off + _HEADER, n, nwl, data, i)
    return times_arr, data_arr


def decode_uv_delta_stream(const unsigned char[::1] buf, Py_ssize_t data_start,
                           int nwl):
    """Decode a partial ``.uv`` delta stream of unknown length (read to EOF).

    Partial files do not record the number of retention times, so this makes two
    passes: first count the complete rows that fit before the end of the buffer,
    then decode exactly that many. A row is complete only if its header and all
    ``nwl`` samples fit -- matching the pure-Python try/except loop, which stops
    at the first short read.

    Args:
        buf: The whole file as a bytes-like buffer.
        data_start: Offset of the first record.
        nwl: Number of wavelengths (samples) per row.

    Returns:
        ``(times, data)`` as in :func:`decode_uv_delta`.
    """
    cdef Py_ssize_t n = buf.shape[0]
    cdef Py_ssize_t off = data_start
    cdef Py_ssize_t probe
    cdef int rows = 0

    # Pass 1: count complete rows.
    while off + _HEADER <= n:
        probe = _scan_row(buf, off + _HEADER, n, nwl)
        if probe < 0:
            break
        rows += 1
        off = probe

    times_arr = np.empty(rows, dtype=np.uint32)
    data_arr = np.empty((rows, nwl), dtype=np.int64)
    cdef unsigned int[::1] times = times_arr
    cdef long long[:, ::1] data = data_arr

    cdef Py_ssize_t i
    cdef unsigned int t

    # Pass 2: decode the rows counted above (none will overrun).
    off = data_start
    for i in range(rows):
        memcpy(&t, &buf[off + 4], 4)
        times[i] = t
        off = _decode_row(buf, off + _HEADER, n, nwl, data, i)
    return times_arr, data_arr
