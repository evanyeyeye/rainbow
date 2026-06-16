# cython: boundscheck=False, wraparound=False, cdivision=True, language_level=3
"""
Compiled accelerator for the Agilent .uv LC-delta decode loop.

This mirrors the pure-Python ``decode_uv_delta`` / partial loop in
``chemstation.py`` exactly, but runs the per-sample inner loop in C. It is
imported opportunistically; if the extension is not built, the package falls
back to the pure-Python implementation with identical results.

The .uv fields are little-endian, which matches every platform NumPy ships
wheels for, so the values are read with native ``memcpy``.
"""

import numpy as np
from libc.string cimport memcpy

DEF SENTINEL = -0x8000


def decode_uv_delta(const unsigned char[::1] buf, Py_ssize_t data_start,
                    int num_times, int nwl):
    """Decode a fixed-length .uv delta stream (known ``num_times``)."""
    times_arr = np.empty(num_times, dtype=np.uint32)
    data_arr = np.empty((num_times, nwl), dtype=np.int64)
    cdef unsigned int[::1] times = times_arr
    cdef long long[:, ::1] data = data_arr

    cdef Py_ssize_t off = data_start
    cdef Py_ssize_t n = buf.shape[0]
    cdef int i, j
    cdef long long acc
    cdef short ci
    cdef int v
    cdef unsigned int t

    for i in range(num_times):
        memcpy(&t, &buf[off + 4], 4)
        times[i] = t
        off += 22
        acc = 0
        for j in range(nwl):
            memcpy(&ci, &buf[off], 2)
            off += 2
            if ci == SENTINEL:
                memcpy(&v, &buf[off], 4)
                off += 4
                acc = v
            else:
                acc += ci
            data[i, j] = acc
    return times_arr, data_arr


def decode_uv_delta_stream(const unsigned char[::1] buf, Py_ssize_t data_start,
                           int nwl):
    """Decode a partial .uv delta stream (unknown length: read until EOF).

    Two passes: count complete rows, then fill. A row is complete only if all
    of its header (22 bytes) and ``nwl`` samples (each 2 or 6 bytes) fit before
    the end of the buffer -- matching the pure-Python try/except loop.
    """
    cdef Py_ssize_t n = buf.shape[0]
    cdef Py_ssize_t off = data_start
    cdef Py_ssize_t probe
    cdef int j, rows = 0
    cdef short ci
    cdef bint ok

    # pass 1: count complete rows
    while True:
        if off + 22 > n:
            break
        probe = off + 22
        ok = True
        for j in range(nwl):
            if probe + 2 > n:
                ok = False
                break
            memcpy(&ci, &buf[probe], 2)
            probe += 2
            if ci == SENTINEL:
                if probe + 4 > n:
                    ok = False
                    break
                probe += 4
        if not ok:
            break
        rows += 1
        off = probe

    times_arr = np.empty(rows, dtype=np.uint32)
    data_arr = np.empty((rows, nwl), dtype=np.int64)
    cdef unsigned int[::1] times = times_arr
    cdef long long[:, ::1] data = data_arr

    cdef int i
    cdef long long acc
    cdef int v
    cdef unsigned int t

    # pass 2: fill
    off = data_start
    for i in range(rows):
        memcpy(&t, &buf[off + 4], 4)
        times[i] = t
        off += 22
        acc = 0
        for j in range(nwl):
            memcpy(&ci, &buf[off], 2)
            off += 2
            if ci == SENTINEL:
                memcpy(&v, &buf[off], 4)
                off += 4
                acc = v
            else:
                acc += ci
            data[i, j] = acc
    return times_arr, data_arr
