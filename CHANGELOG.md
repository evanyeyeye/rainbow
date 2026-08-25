# Changelog

All notable changes to `rainbow-api` are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [1.5.0] - Unreleased

### Added
- **`rainbow.debug` metadata-inspection subsystem.** A new opt-in module with
  two entry points, `rb.debug.inspect(path)` and `rb.debug.fields(path)`, that
  decode the many vendor sidecar files a run directory ships (ChemStation
  registers and INIs, .NET and XML blobs, mzXML and Waters headers, method and
  macro dumps, audit trails) into structured fields on demand. It is never run
  by the normal `rb.read` path, so it adds no overhead unless called. New
  documentation under `docs/debug/`.
- **Allotrope Simple Model (ASM) export and import.** Any `DataDirectory`
  exports to one open, JSON-based ASM document with `datadir.to_asm()` (a dict)
  or `datadir.export_asm(path)` (a file); `rb.from_asm(document)` reconstructs a
  `DataDirectory`. Export is detector-driven and covers UV (a chromatogram cube
  per single-wavelength trace and a 3D spectrum cube per diode-array
  acquisition), charged-aerosol, evaporative-light-scattering, and
  refractive-index channels, mass spectrometry (every monitored ion of a SIM
  acquisition automatically, and chosen ions of a full scan via
  `to_asm(ions=[...])`), and flame-ionization channels, which route to a
  gas-chromatography document. Integrated peaks become processed data. New
  documentation page, "Open data: the Allotrope Simple Model"
  (`docs/source/asm.rst`).
- **`rb.from_asm` also reads ASM documents rainbow did not write** (for example
  a third-party converter's richer envelope): it reconstructs the UV traces it
  recognizes, ignores unfamiliar fields, and skips cubes it cannot represent
  rather than failing.
- **`rb.read_sequence(path)` and the `DataSequence` container** for Agilent
  multi-injection sequences: a container of per-injection `DataDirectory`
  objects, with the shared instrument, operator, and injection count as
  metadata. `rb.read_sequence(path, peaks=True)` attaches each injection's
  integrated peaks. A whole sequence exports to one ASM document with
  `sequence.to_asm()` / `sequence.export_asm(path)`, or to one document per
  injection with `export_asm(directory, per_injection=True)`, and
  `rb.sequence_from_asm` reconstructs it. `DataSequence` is exported at the
  package level. The sequence workflow is Agilent-only. New "Sequences"
  documentation guide (`docs/source/sequences.rst`).
- **Per-injection method and sample metadata** read from the Agilent `acq.macaml`
  and `SAMPLE.XML` sidecars (injection volume, column temperature, flow rate,
  modules, dilution, operator), merged onto each injection. This also enriches
  the metadata returned by a single `rb.read`.
- **MS acquisition-mode tagging.** Each MS `DataFile` carries a
  `metadata['acquisition_mode']` of `'SIM'` or `'Scan'`, read from authoritative
  vendor metadata (Agilent `acqmeth.txt`, Waters `_FUNCTNS.INF` function types)
  rather than guessed from the data.
- **Controls for ASM document size.** `to_asm` / `export_asm` accept
  `export_dad_cube=False` to omit the large diode-array spectrum cube,
  `wavelengths=[...]` to keep only chosen wavelengths, and `decimal_places=N` to
  round emitted numbers. `export_asm` streams one injection document at a time,
  so even a long sequence of large spectra never has to fit in memory at once.
- **`rb.mz_resolution(path)`** reports the finest m/z spacing a run actually
  records, the practical ceiling on `bin_width`. It is opt-in and never runs
  during an ordinary `rb.read`.
- **`lxml`-accelerated sequence parsing**, installed with
  `pip install rainbow-api[speed]`. The large `sequence.acaml` is read with a
  tag-filtered iterparse, with the same output as the standard-library
  fallback.
- **Refractive index detector (RID) support** for Agilent data.
- **More `.dx` archive manifest metadata** surfaced from the OpenLab `.dx`
  manifest.
- **Opt-in ASM conformance tests** against a pinned Allotrope schema and the
  Allotrope Foundation Ontology (AFO), enabled with `RAINBOW_TEST_ASM_SCHEMA=1`.
- **ASM export covers Agilent MassHunter DAD data**, added in 1.4.0. Export
  routes on the detector rather than the file format, so a MassHunter run's
  signals and spectra map exactly as a Chemstation `.ch`/`.uv` pair does: one
  chromatogram cube per single-wavelength signal and one 3D spectrum cube for
  the wavelength grid, both honouring `export_dad_cube` and `wavelengths`. A
  DAD's telemetry stays analog data and is never exported as a detector
  channel.

### Changed
- **`import rainbow` is about four times faster** (roughly 160 ms to 40 ms on
  the machine this was measured on). `pandas`, needed only for the Waters
  transition table, was imported at module load and was by a wide margin the
  largest cost of importing the package. It is now imported where it is used,
  as `matplotlib` already was. Both remain required, so calling either still
  works on a plain install.
- **`lxml` is now optional. Breaking for `rainbow.debug` only:** reading data
  no longer needs it. The vendor XML paths that used lxml-only XPath were
  rewritten against the standard library, and every bundled fixture parses to
  an identical result with and without lxml, so a plain install reads the same
  files it always did. `rainbow.debug` is the exception: it recovers structure
  from malformed and mis-encoded sidecars, which needs lxml's recovering
  parser, and now raises a message naming
  `pip install rainbow-api[debug]` rather than failing at import. Install
  `rainbow-api[speed]` to keep the faster XML path.
- **m/z binning split into `display_precision` and `bin_width`. Breaking:** the
  `precision` argument to `rb.read` (and the vendor parsers) is replaced by two
  independent controls. `display_precision` (default `'auto'`) is cosmetic and
  rounds only the displayed m/z labels; `bin_width` is the lossy step that sums
  intensities into a shared m/z grid. `bin_width` defaults to the grid the
  binary records (about 0.1 Da for Agilent quadrupole MS, 0.05 Da for Waters,
  and the per-scan axis for HRMS profile data), so binned output is unchanged by
  default. Code passing `precision=` must now pass `display_precision=`, or
  `bin_width=` to control the binning step.

### Fixed
- **A non-ultraviolet detector module is no longer reported as an ultraviolet
  one** in a document's instrument inventory. Any module whose type was
  `detector`, or whose name merely contained the word, was filed under the
  generic ultraviolet class, so an FID, RID, ELSD, or charged-aerosol module
  contradicted the very cube it described. Each now maps to the AFO class its
  cube already uses. The acronyms are matched as whole words with an optional
  module index (`FID1`, `RID1A`), so `hybrid` and `cascade` are not mistaken
  for detectors.
- **`rb.from_asm` no longer raises on a third-party document that omits the
  measurement keys**, or that carries a single measurement object where the
  schema also allows a list. It reads what is present, in keeping with the rest
  of its handling of documents rainbow did not write.
- **The `sequence.acaml` reader closes its file deterministically.** The parse
  stops as soon as it has the instrument, which abandons the iterator
  mid-document and left the handle to be closed whenever the interpreter got
  round to it. It is now closed as the reader unwinds.
- **An Agilent MassHunter DAD signal now reports its optics.** The `.cd`
  descriptor gives each signal the same `Sig=`/`Ref=` description Chemstation
  writes, but it was left unparsed, so a `.cg` channel carried no `wavelength`,
  `bandwidth`, or reference band in its metadata while the equivalent `.ch`
  channel did. They are now read with the parser the `.ch` and `.dx` readers
  already share. An ASM export of a MassHunter DAD consequently records each
  channel's detector wavelength setting, and a document that had lost the
  wavelength on the way back through `rb.from_asm` now round-trips intact.

## [1.4.0] - 2026-08-13

### Added
- **Agilent MassHunter DAD support.** A MassHunter `.d` stores its DAD data in
  four files that the Chemstation decoders do not read, so until now a `.d`
  acquired with a diode-array detector returned no UV data at all - silently,
  since MassHunter parsing is opt-in and an unread detector looks the same as
  an absent one. `rb.read` now parses them: `DAD1.cd` describes the signals in
  `DAD1.cg` (one chromatogram each), and `DAD1.sd` describes the spectra in
  `DAD1.sp` - the same two views the Chemstation format splits into `.ch` and
  `.uv` files.

  The spectra become a single (retention time x wavelength) `DataFile` named
  after the `.sp`, and each signal its own, carrying the Chemstation signal
  letter (`DAD1A.cg`, `DAD1B.cg`, ...) since here they share one file. Both
  descriptors give the byte offset of every record they describe, so the data
  files are indexed rather than walked at an assumed stride - signals sampled at
  different rates, and spectra that are not evenly spaced, are read correctly.
  Unlike the Chemstation `.uv`/`.ch` formats there is no delta encoding and no
  scaling factor: the values are plain little-endian float64.

  Spectra whose wavelength axis changes during a run cannot form one grid, and
  are declined with a warning rather than reshaped.
- `rb.read(..., telemetry=True)` also parses the traces a DAD records beside
  its signals (lamp voltage, board and optical-unit temperature). Off by
  default and returned as analog data, matching `.dx` telemetry — including
  that naming one in `requested_files` parses it regardless of the flag.
- `tests/test_masshunter.py::test_dad_*` and the `bronze.D` fixture: a
  four-retention-time slice of a real QQQ+DAD acquisition keeping all five
  absorbance signals, all three telemetry traces, and the full 190-550 nm axis,
  with the telemetry deliberately at a different point count from the signals.

### Changed
- **The MassHunter parser is now always consulted for a `.d`, not only under
  `hrms`/`centroid`.** DAD data is parsed unconditionally, as the Chemstation
  UV formats are; the MS parsing inside remains gated on those flags. A `.d`
  that holds DAD data therefore yields UV `DataFile`s where it previously
  yielded none.

### Fixed
- **`rb.read_metadata()` now reports a MassHunter run's DAD files** alongside
  its MS ones. The MassHunter branch returned as soon as it had found
  `MSProfile.bin`/`MSPeak.bin`, so a run carrying both came back as MS-only
  while `rb.read()` returned its chromatograms and spectra.

## [1.3.1] - 2026-07-22

### Added
- **`hrms` optional-dependency extra** (`pip install rainbow-api[hrms]`), which
  installs `python-lzf` for LZF-compressed Agilent MassHunter `MSProfile.bin`
  segments. The extra was referenced in the docs but never declared, so the
  install warned the extra did not exist and silently installed nothing.
- **`hrms_available` metadata hint** on `rb.read(path)` and
  `rb.read_metadata(path)`, mirroring `centroid_available`: a MassHunter `.D`
  whose `MSProfile.bin` was not parsed now advertises that profile data is
  present and needs `hrms=True`.

### Fixed
- **`rb.read_metadata()` on Agilent MassHunter `.D` folders** now reports the
  `MSProfile.bin`/`MSPeak.bin` datafiles (plus the `hrms_available` /
  `centroid_available` hints) instead of returning an empty datafile list.

## [1.3.0] - 2026-06-24

### Changed
- **Agilent HRMS profile data is now per-scan by default. Breaking:**
  `rb.read(path, hrms=True)` returns the faithful per-scan representation (a
  `rainbow.agilent.masshunter.ProfileDataFile` per flight-time grid) instead of
  the shared-grid `DataFile`. A Q-TOF/TOF `MSProfile.bin` has a per-scan m/z
  axis (the flight-time-to-m/z calibration drifts between scans), so projecting
  every scan onto one shared grid inserts zeros and merges peaks. Pass a
  `bin_width` to opt into the shared grid.
- **`prec` renamed to `precision`** on `rb.read` (and the vendor parsers).
  **Breaking:** code passing `prec=` must now pass `precision=`.
- **`precision` now defaults to `'auto'` and is resolved per file from the
  actual data type:** 4 decimals for high-resolution data (the HRMS profile and
  TOF centroids) and 0 (whole numbers) for unit-resolution data (UV,
  GC/quadrupole MS, ICP-MS, Waters). Previously the default was a flat `0`,
  which silently reduced high-resolution m/z to nominal mass. Pass an explicit
  integer to override (including `0`).

### Added
- **Per-scan (unbinned) HRMS profile representation** (now the default; see
  Changed). `ProfileDataFile` exposes `scan(i)`, `mass_labels(i)`, the shared
  `tof` axis, and the raw `data` matrix. It has no single `ylabels`, and the
  `DataFile` operations that need one shared m/z axis (`ylabels`,
  `extract_traces`, `to_csvstr`, `export_csv`, `plot`) raise a clear error
  pointing at `scan(i)`/`mass_labels(i)` and the documentation. New
  documentation page, "HRMS Profile Data"
  (`docs/source/agilent/hrms_data_model.rst`).
- **`bin_width` argument on `rb.read`** is the single switch for HRMS
  shared-grid binning: omit it for the per-scan representation, pass a width (in
  daltons) to project onto one shared grid. It is fully independent of
  `precision` (which only rounds the reported m/z labels and has no effect on the
  grid). A `bin_width` finer than `10**-precision` is allowed but warns, since
  two bins may then round to the same m/z label.

### Fixed
- **`MSProfile.bin` RLE segments whose first scan opens with a literal run
  (#27).** The run-length-encoded intensity stream is `[point-count word]
  [negated leading-zero count][token stream]`, with the token stream opening at
  4-byte width. The reader instead read a second int32 as a "width flag", which
  happened to decode correctly only when the first token was a width switch
  (the common case) but raised `Malformed MSProfile.bin RLE segment` on
  high-signal scans that open with a literal 4-byte intensity. Fixed in both the
  pure-Python `decompress_inten_list` and the Cython accelerator
  (`_msprofile.pyx`); validated on two real Agilent Q-TOF datasets (every scan's
  decoded maximum matches the independently stored `MaxY`, 0 mismatches across
  all 1256 scans of each).
- **Shared-grid binning no longer emits all-zero columns.** A column of the
  shared grid is meant to be a bin some scan actually filled (empty bins are
  dropped), but the sparse-path branch of `bin_to_grid` keyed its columns off
  point presence rather than nonzero intensity, so points whose recorded
  intensity is `0` produced phantom all-zero columns (about 90 of ~315,000 on
  the default fine grid). The sparse path now drops zero-sum columns, matching
  the dense path.

## [1.2.0] - 2026-06-22

### Added
- **Agilent MassHunter ICP-MS support (issue #25).** ICP-MS `.D` directories
  (e.g. Agilent 7700 / 8900) now parse via a new `parse_icpmsdata`, detected by
  the presence of `MSScan_XSpecific.bin`. Single tune mode and one measurement
  per isotope. Contributed by Jeremy Hourigan (UC Santa Cruz).
- **`format` argument on `rb.read` and `rb.read_metadata`** to force the vendor
  parser (`'agilent'` or `'waters'`), bypassing detection.
- **Content-based vendor detection.** A directory whose name lacks a
  `.D`/`.raw`/`.dx` suffix is identified from its contents; suffixed paths are
  unaffected.
- **Optional Cython accelerator for the Agilent `.ch` decode**
  (`rainbow/agilent/_chdelta.pyx`) - ~11x faster, bit-identical, with a
  transparent pure-Python fallback.

### Changed
- **Faster MS spectrum parsing.** Vectorized binning (shared
  `rainbow/_binning.py`) and lookup-table exponentials replace the per-scan
  loops in the Waters `_FUNC.DAT` and Agilent `.ms` decoders. Output unchanged;
  ~2-3x faster.
- **Test suite migrated to pytest** (added a `test` extra; run with `pytest`).

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
