# Changelog

All notable changes to `rainbow-api` are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-06-17

### Fixed
- **MassHunter HRMS profile data is parsed when scans also store centroids.**
  When an acquisition writes `MSPeak.bin` alongside `MSProfile.bin`, each
  `MSScan.bin` record carries two `SpectrumParamValues` blocks (a profile and a
  centroid block; the schema element is `maxOccurs="unbounded"`) instead of one.
  The reader assumed exactly one block, so after the first scan it mis-parsed
  the centroid block as the next scan's fields and crashed (`struct.error`).
  `rainbow` now reads each record at its true stride - taken from the MSTS.xml
  scan count when consistent, otherwise inferred from the record geometry - and
  reads the profile block. Validated on real Agilent Q-TOF (issue #27) and
  TOF-MS datasets.
- **HRMS calibration without `MSMassCal.bin`.** Some Q-TOF/TOF acquisitions omit
  the per-scan `MSMassCal.bin` and keep only the default calibration in
  `DefaultMassCal.xml`; the parser raised `FileNotFoundError` opening the former.
  `rainbow` now falls back to reconstructing each scan's calibration row from
  `DefaultMassCal.xml` (by `CalibrationID`). The per-scan refinement is sub-ppm,
  so the m/z reproduce the per-scan values to <0.0001 Da (checked against the
  `magenta`/`cyan` fixtures, which carry both files).
- **Interrupted acquisitions no longer fail.** When `MSScan.bin` describes more
  scans than `MSProfile.bin` actually contains (an aborted run, sometimes with a
  stale `MSTS.xml` scan count), `rainbow` keeps the complete leading scans
  instead of raising on the truncated segment.

### Added
- **Agilent MassHunter centroid (`MSPeak.bin`) support (issue #37).** `MSPeak.bin`
  stores the peak-picked (centroid) spectrum of each scan - the counterpart to
  the dense profile trace in `MSProfile.bin`. `rb.read(..., centroid=True)` now
  parses it (off by default, like `hrms`). GC-quadrupole centroids are stored as
  m/z directly (validated to 7e-5 relative agreement against the same
  acquisition's `data.ms`); Q-TOF/TOF centroids are stored as time-of-flight and
  are calibrated with the same `DefaultMassCal.xml`/`MSMassCal.bin` path as the
  profile. When a `.D` contains `MSPeak.bin` but is read without the flag,
  `centroid_available` is set in the directory metadata so the option is
  discoverable. The centroid decoding was contributed by denisshragin.
- `tests/test_masshunter.py::TestMasshunterMultiBlock` and
  `TestMasshunterCentroid`: trimmed real TOF-MS fixtures (`gold.D`, a 3-scan
  profile+centroid slice; `copper.D`, the same with a truncated `MSProfile.bin`)
  covering the two-block record stride, the `DefaultMassCal.xml` calibration
  fallback, geometry-based stride inference, incomplete-acquisition recovery, and
  the centroid path (block selection, GC-quad and calibrated-TOF axes, the
  `centroid=True` flag, and the metadata note).

## [1.0.16] - 2026-06-17

### Added
- **Agilent MassHunter HRMS Q-TOF profile support (issue #27).** Q-TOF
  acquisitions store `MSProfile.bin` intensities with a run-length encoding
  rather than LZF compression, which made the parser raise `ValueError: error
  in compressed data`. `rainbow` now detects the encoding from each scan
  segment's own header and decodes it (`decompress_inten_list`). The decode is
  validated against two real datasets (474 and 1256 scans): every scan's
  decoded maximum intensity matches the `MaxY` value stored independently in
  `MSScan.bin`.
- Support for the newer MassHunter `MSScan.xsd` variant, whose complex-type
  references are qualified with the schema's target-namespace prefix (e.g.
  `mstns:ScanRecordType`). These previously raised `KeyError` while reading
  `MSScan.bin`.
- **Polynomial m/z calibration for HRMS.** When `DefaultMassCal.xml` provides a
  polynomial `ValueUseFlags`, `rainbow` now applies the polynomial correction
  (`MSMassCal.bin` stores `[coeff, base, left, right, c0..c5]` per scan) on top
  of the traditional calibration. Validated to <0.0001 Da against m/z that
  Agilent MassHunter BioConfirm exports for the reporter's spectra; the
  traditional calibration alone is ~1-2 ppm off. Files without
  `DefaultMassCal.xml` keep the traditional calibration.
- **Optional compiled accelerator for the MSProfile.bin run-length decode**
  (`rainbow/agilent/_msprofile.pyx`). The decode is an inherently sequential,
  variable-width byte loop; the Cython version is ~100x faster than the
  pure-Python loop and bit-identical. Like the `.uv` accelerator it is optional
  — without a compiler or Cython, `rainbow` falls back to pure Python.
- `tests/test_masshunter.py`: parses trimmed real Q-TOF profile fixtures
  (`magenta.D`, `cyan.D`) end to end without `python-lzf`, cross-checking the
  decoded intensities and validating the calibrated m/z against BioConfirm.
  `tests/test_accelerator.py` adds parity tests for the `_msprofile` extension.

### Changed
- **MassHunter HRMS no longer requires `MSTS.xml`.** The number of retention
  times is now recovered by reading `MSScan.bin` to EOF instead of from
  `MSTS.xml`, which is absent from Agilent OpenLab `.rslt`/`.sirslt` result
  folders. Validated against the `yellow` fixture (centroided) and two real
  HRMS profile datasets, where the recovered count matches `MSTS.xml` exactly.
- The `python-lzf` import is now lazy and only happens when an LZF-compressed
  `MSProfile.bin` segment is actually encountered, so the rest of the
  MassHunter module - including the run-length-encoded Q-TOF profile path -
  imports and runs without `python-lzf` installed.
- **Faster HRMS profile parsing (~8x end to end** on large files; e.g. a 185 MB
  `MSProfile.bin` went from ~35 s to ~4.5 s). The compiled decoder removes the
  decode bottleneck, the per-scan m/z arrays are concatenated instead of routed
  through a ~100M-element Python list, and the (retention time x m/z) grid is
  binned with integer keys in a single pass instead of a global sort (with a
  memory-bounded fallback to the sort-based path). Output is unchanged.

## [1.0.15] - 2026-06-17

### Added
- **Agilent OpenLab CDS (`.dx`) support.** OpenLab 2.x exports a single OPC
  (zip) archive rather than a `.D` directory. `rb.read` now accepts a `.dx`
  path and parses its payloads with the existing Chemstation decoders: the DAD
  spectrum (`.UV`), single-wavelength signals (`.CH`), and—opt-in—instrument
  telemetry (`.IT`). Trace names, units, and detector roles are recovered from
  the `injection.acmd` manifest, since the payload files are named by GUID. The
  DAD spectrum's absorbance is corrected by a `2**-17` fixed-point shift unique
  to this format, validated against the file's own single-wavelength channels.
  Decoding and test data were contributed by an anonymous collaborator.
- `rb.read(..., telemetry=True)` parses `.dx` instrument-telemetry traces
  (pressure, temperature, flow, etc.) as analog data. Off by default, since
  most users only want the detector signals; a telemetry trace named in
  `requested_files` is parsed regardless of the flag.
- `tests/test_agilent.py::test_teal` and `test_teal_telemetry_off`: a `.dx`
  fixture (DAD spectrum, two wavelength channels, two telemetry traces)
  verified end-to-end, plus coverage of the telemetry opt-in behavior.

### Changed
- The `OL` `.uv` decoder (`decode_uv_array`) now reads its raw-double data
  with a single strided NumPy view instead of a per-value Python loop, decoding
  roughly **30× faster** with bit-identical output. This speeds up both `.dx`
  spectra and the existing `131 OL` `.uv` files.

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
