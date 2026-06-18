# cython: boundscheck=False, wraparound=False, cdivision=True, language_level=3
"""
Compiled accelerator for the Agilent ``.ch`` delta decode loop.

The pure-Python ``decode_delta`` in :mod:`rainbow.agilent.chemstation` spends
almost all of its time in a per-sample loop that reads the channel signal
(CAD/ELSD/UV ``.ch`` files) one struct at a time. The encoding is inherently
sequential (a running accumulator with a sentinel that resets it) and its
record stride is data-dependent, so it cannot be vectorized with NumPy; only a
compiled inner loop removes the interpreter overhead. This module is that loop,
written to produce output bit-identical to the pure-Python reference.

It is imported opportunistically by ``chemstation.py``. If the extension was
not built (no compiler or no Cython at install time), the package falls back to
the pure-Python implementation transparently.

Format
------
The signal is a sequence of segments. Each segment is a 2-byte header - the
byte ``0x10`` then a one-byte sample count - followed by that many samples; a
header byte other than ``0x10`` (or the end of the buffer) terminates the
stream. Each sample is a big-endian 16-bit delta added to a running
accumulator, *unless* it equals ``-0x8000`` (the sentinel), in which case the
following big-endian 32-bit integer is the new absolute accumulator value. The
``.ch`` fields are big-endian, so the multi-byte values are assembled from
individual bytes rather than copied.
"""

import numpy as np

# 16-bit sentinel: the next sample is an absolute 32-bit value, not a delta.
cdef short _SENTINEL = -0x8000
# Segment header marker; any other leading byte ends the stream.
cdef unsigned char _SEGMENT = 0x10


def decode_delta(const unsigned char[::1] buf, Py_ssize_t offset):
    """Decode an Agilent ``.ch`` delta stream into accumulated signal values.

    Args:
        buf: The whole file as a bytes-like buffer.
        offset: Offset of the first segment header.

    Returns:
        An ``int64`` array of the accumulated values (one per sample), matching
        ``np.array(decode_delta(...))`` from the pure-Python path.
    """
    cdef Py_ssize_t n = buf.shape[0]
    cdef Py_ssize_t off = offset

    # Each sample is at least two bytes, so the sample count cannot exceed half
    # the remaining bytes; allocate that upper bound once and slice at the end.
    cdef Py_ssize_t ub = (n - offset) // 2
    if ub < 0:
        ub = 0
    out_arr = np.empty(ub, dtype=np.int64)
    cdef long long[::1] out = out_arr

    cdef Py_ssize_t k = 0
    cdef long long acc = 0
    cdef int count, j
    cdef short delta
    cdef int absolute

    while off < n:
        if buf[off] != _SEGMENT:
            break
        off += 1
        if off >= n:
            break
        count = buf[off]
        off += 1
        for j in range(count):
            if off + 2 > n:
                break
            delta = <short>((buf[off] << 8) | buf[off + 1])
            off += 2
            if delta == _SENTINEL:
                if off + 4 > n:
                    break
                absolute = <int>((buf[off] << 24) | (buf[off + 1] << 16)
                                 | (buf[off + 2] << 8) | buf[off + 3])
                off += 4
                acc = absolute
            else:
                acc += delta
            out[k] = acc
            k += 1

    return out_arr[:k]
