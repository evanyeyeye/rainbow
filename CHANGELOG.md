# Changelog

All notable changes to `rainbow-api` are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## Unreleased

### Added

- `parse_mspeak_data()`: parses `MSPeak.bin`, the centroided peak format
  produced by Agilent MassHunter on single-quadrupole and some QTOF
  GC-MS instruments. Returns a `DataFile` with the same
  `xlabels`/`ylabels`/`data` interface as `parse_msdata()`.
  Supports three peak encodings: `bpp=8` (float32 pairs), `bpp=12`
  (float64 mz + float32 intensity), `bpp=16` (split-block float64).

### Changed

- `rb.read()` now returns an additional `MSPeak.bin` `DataFile`
  automatically when `MSPeak.bin` is present in `AcqData/`, without
  requiring `hrms=True`. This is a behaviour change for `.D` directories
  that contain `MSPeak.bin`.
- `MSScan.bin` records are now parsed using the XSD-driven
  `read_complextype()`/`read_type()` helpers, matching `parse_msdata()`
  framing. This handles layout differences across instrument types and
  MassHunter versions without hardcoded field offsets.

## [1.0.14] - 2026-06-16

### Fixed
- **Cross-platform determinism in directory parsing.** `parse_allfiles` now
  iterates the `.D` directory in sorted order instead of raw `os.listdir`
  order. Directory-level metadata (date, vial position) is chosen by
  `Counter.most_common`, whose tie-break follows insertion order; with an
  unsorted listing this made the chosen value depend on the filesystem's
  ordering, so a `.D` containing files with differently-formatted date strings
  could yield different metadata on macOS vs. Linux. Parsing is now identical
  on every platform.

### Added
- Pre-merge CI (`.github/workflows/ci.yml`): runs the test suite on Python 3.8
  and 3.13 and builds a wheel + sdist on every pull request, so packaging and
  test regressions are caught before merge rather than at release time.

## [1.0.13] - 2026-06-16

### Added
- **Optional compiled accelerator for Agilent `.uv` (DAD) decoding.** The
  retention-time × wavelength absorbance "cube" is delta-encoded and inherently
  sequential, so it cannot be vectorized with NumPy. A new Cython extension
  (`rainbow/agilent/_uvdelta.pyx`) runs this inner loop in C, decoding large
  diode-array files roughly **100× faster** while producing **bit-identical**
  results. See the Performance section of the README.
- `tests/test_accelerator.py`: parity tests asserting the compiled path matches
  the pure-Python fallback across all `.uv` decode paths (delta, partial,
  array), plus a truncated-input safety test.

### Changed
- Releases now build **cross-platform binary wheels** with `cibuildwheel`
  (Linux/macOS/Windows, CPython 3.8–3.13) alongside a source distribution, so
  `pip install rainbow-api` ships the accelerator with no compiler required.
- Unit tests compare decoded absorbance arrays with a floating-point tolerance
  instead of exact text equality, fixing pre-existing 1-ULP failures from
  retention-time accumulation (`test_yellow`, `test_orange`).

### Fixed
- The accelerator is fully optional and transparent: if the extension is not
  built (no compiler or no Cython), `rainbow` falls back to a pure-Python
  decoder with identical output.
- Truncated or corrupt `.uv` streams now raise `ValueError` from the compiled
  path instead of risking an out-of-bounds read (the extension disables Cython
  bounds checks for speed, so the bounds are guarded explicitly).
- The source distribution now includes `_uvdelta.pyx`, so installs on platforms
  without a prebuilt wheel compile the accelerator from source instead of
  failing the build.
