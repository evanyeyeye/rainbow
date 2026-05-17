# Changelog

All notable changes to this project will be documented in this file.

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

### Fixed

- `test_pink` and `test_yellow` now use approximate float comparison
  (`places=10`) to handle last-ULP differences in newer numpy versions.
  These were pre-existing failures on clean `main` unrelated to the
  `MSPeak.bin` parser.