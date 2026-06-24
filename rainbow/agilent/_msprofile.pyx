# cython: boundscheck=False, wraparound=False, cdivision=True, language_level=3
"""
Compiled accelerator for the Agilent MassHunter Q-TOF ``MSProfile.bin`` decode.

Q-TOF "profile" acquisitions store each scan's intensities with a run-length
encoding (see :func:`rainbow.agilent.masshunter.decompress_inten_list` for the
reference implementation and a full description of the format). The decode is
an inherently sequential, variable-width byte loop -- a literal value advances
the output by one, a control value emits a run of zeros and may switch the
integer width of the values that follow -- so it cannot be vectorized with
NumPy, and the pure-Python loop dominates parsing of large profile files (tens
of seconds, with hundreds of millions of per-token ``struct.unpack`` calls).
This module is that loop in C, producing output bit-identical to the reference.

It is imported opportunistically by ``masshunter.py``. If the extension was not
built (no compiler or no Cython at install time), the package falls back to the
pure-Python implementation transparently. The ``MSProfile.bin`` fields are
little-endian, which matches every platform NumPy ships wheels for, so values
are read with a native ``memcpy``.
"""

import numpy as np
from libc.string cimport memcpy


cdef inline int _width_size(int flag) except -1:
    """Bytes for an RLE width flag (1/2/3/4 -> 1/2/4/8); raise on anything else.

    A zero or out-of-range flag means a corrupt stream; raising here mirrors
    the ValueError the pure-Python reference reports rather than reading at a
    bogus width (this module disables Cython's automatic bounds checks).
    """
    if flag == 1:
        return 1
    elif flag == 2:
        return 2
    elif flag == 3:
        return 4
    elif flag == 4:
        return 8
    raise ValueError("Malformed MSProfile.bin RLE segment.")


def decompress_inten_list(const unsigned char[::1] comp_view, int num_mz):
    """Decode one run-length-encoded intensity stream.

    Args:
        comp_view: The segment bytes after its 16-byte (smallest mz, mz delta)
            header -- i.e. the 4-byte point-count word, the negated int32
            leading-zero count, and the token stream (which opens at 4-byte
            width).
        num_mz: The number of mz-intensity pairs (output length).

    Returns:
        A ``num_mz``-length ``uint32`` NumPy array of intensities.

    Raises:
        ValueError: If the stream is malformed (bad width flag, runs past the
            point count, an initial index that would start negative, or a
            truncated tail).
    """
    cdef Py_ssize_t n = comp_view.shape[0]
    cdef int init_zero_repeat
    cdef int width_flag

    # A negated little-endian int32 (the leading-zero count) follows the 4-byte
    # point-count word; the token stream begins right after it.
    if n < 8:
        raise ValueError("Malformed MSProfile.bin RLE segment.")
    memcpy(&init_zero_repeat, &comp_view[4], 4)

    cdef Py_ssize_t cur_idx = -init_zero_repeat
    # cur_idx only ever advances, so once it starts non-negative it stays in
    # range; a positive init_zero_repeat would start it negative, so reject it.
    if cur_idx < 0:
        raise ValueError(
            "Malformed MSProfile.bin RLE segment: negative initial index.")

    data_arr = np.zeros(num_mz, dtype=np.uint32)
    cdef unsigned int[::1] inten = data_arr

    # The token stream opens at an initial width of 4 bytes (width flag 3); a
    # control value switches it thereafter.
    cdef Py_ssize_t off = 8
    cdef int cur_size = _width_size(3)
    cdef long long value
    cdef Py_ssize_t num_zeros
    cdef signed char v1
    cdef short v2
    cdef int v4
    cdef long long v8

    while off < n:
        if off + cur_size > n:
            raise ValueError("Malformed MSProfile.bin RLE segment.")
        if cur_size == 1:
            memcpy(&v1, &comp_view[off], 1)
            value = v1
        elif cur_size == 2:
            memcpy(&v2, &comp_view[off], 2)
            value = v2
        elif cur_size == 4:
            memcpy(&v4, &comp_view[off], 4)
            value = v4
        else:
            memcpy(&v8, &comp_view[off], 8)
            value = v8
        off += cur_size

        if value >= 0:
            if cur_idx >= num_mz:
                raise ValueError("Malformed MSProfile.bin RLE segment.")
            inten[cur_idx] = <unsigned int>value
            cur_idx += 1
        else:
            value = -value
            num_zeros = <Py_ssize_t>(value // 4)
            width_flag = <int>(value % 4)
            cur_idx += num_zeros
            cur_size = _width_size(width_flag)
    return data_arr
