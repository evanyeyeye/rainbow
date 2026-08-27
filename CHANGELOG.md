# Changelog

All notable changes to `rainbow-api` are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [1.5.0] - 2026-08-25

### Added
- **`rainbow.debug` metadata-inspection subsystem.** A new opt-in module with
  two entry points, `rb.debug.inspect(path)` and `rb.debug.fields(path)`, that
  decode the many vendor sidecar files a run directory ships (ChemStation
  registers and INIs, .NET and XML blobs, mzXML and Waters headers, method and
  macro dumps, audit trails) into structured fields on demand. It is never run
  by the normal `rb.read` path, and is imported only on first use, so it adds
  no overhead unless called. A catalogue of the formats it decodes is part of
  the documentation.
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
  (`docs/source/asm.rst`). Documents target Allotrope revision `REC/2026/06`,
  the current one, and an opt-in test suite validates rainbow's own output
  against the published liquid- and gas-chromatography schemas.
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
- **The ASM export options are keyword-only.** `to_asm`, `export_asm`, their
  sequence equivalents and the `DataDirectory` / `DataSequence` methods take
  their run or file positionally and everything else by name, so no caller has
  to remember an order and the list stays free to grow. Nothing here shipped
  before 1.5.0, so no existing call changes meaning.
- **Controls for ASM document size.** `to_asm` / `export_asm` accept
  `export_dad_cube=False` to omit the large diode-array spectrum cube,
  `wavelengths=[...]` to keep only chosen wavelengths, and `decimal_places=N` to
  round emitted numbers. `export_asm` streams one injection document at a time,
  so even a long sequence of large spectra never has to fit in memory at once.
- **`rb.mz_resolution(path)`** reports the finest m/z spacing a run actually
  records, the practical ceiling on `bin_width`. It is opt-in and never runs
  during an ordinary `rb.read`.
- **`lxml`-accelerated sequence parsing.** The large `sequence.acaml` is read
  with a tag-filtered iterparse, with the same output as the standard-library
  fallback.
- **Refractive index detector (RID) support** for Agilent data.
- **More `.dx` archive manifest metadata** surfaced from the OpenLab `.dx`
  manifest.
- **Opt-in ASM conformance tests** against a pinned Allotrope schema and the
  Allotrope Foundation Ontology (AFO), enabled with `RAINBOW_TEST_ASM_SCHEMA=1`.
- **ASM export covers the Agilent MassHunter DAD support added in 1.4.0.**
  Export routes on the detector rather than the file format, so a MassHunter
  run's signals and spectra map as a Chemstation `.ch`/`.uv` pair does: one
  chromatogram cube per single-wavelength signal and one 3D spectrum cube for
  the wavelength grid, both honouring `export_dad_cube` and `wavelengths`. A
  DAD's telemetry stays analog data and is never exported as a detector
  channel.
- **`rb.iso_timestamp(value)`** converts a vendor timestamp to ISO 8601, or
  returns `None` for a spelling rainbow cannot read. The vendors write
  day-first wall clock and name the month, so `metadata['date']` does not sort
  chronologically as text; this is the conversion the ASM export uses, and what
  it returns does sort. The "Sequences" guide uses it to recover acquisition
  order.
- **`DataDirectory.path`**, the path the run was read from, alongside the
  `name` it already carried. `DataSequence` has had both all along.

### Changed
- **A diode-array channel in a 179/181 `.ch` container is now read as UV, not
  FID. Breaking:** the container version says how the data is encoded, not what
  measured it, and Chemstation writes both kinds into the same one. The
  detector now comes from the channel's own signal string, so a channel
  reporting `DAD1A,Sig=210,4 Ref=off` in mAU is ultraviolet absorbance at
  210 nm rather than a flame ionization trace in pA. `DataDirectory.detectors`
  and `by_detector` change accordingly for such a run, and
  `get_detector('FID')` on one now raises where it previously returned the
  diode-array channels. Those channels also gain a `wavelength` ylabel and
  their optics in metadata. Reading the detector from the version byte was also
  what sent whole liquid chromatography runs out as gas chromatography
  documents measuring picoamps.
- **A binned Waters function's ylabels are `float64` rather than `float32`.**
  The values are unchanged; the array they are handed back in is wider. This
  is the binning change above reaching the axis, so it applies to the formats
  that bin: a function whose labels come from `_FUNCTNS.INF` rather than from
  the data (the 2- and 4-byte formats, which include every single-wavelength
  UV function) is still `float32`. Code that concatenates axes across vendors
  should keep widening rather than assume one dtype.
- **Chemstation header strings are decoded as UTF-16 rather than by taking
  every other byte.** The two agree while the text is ASCII; for anything else
  the mangled bytes were not valid UTF-8, so the field was dropped and came
  back empty. Headers written in any other script now read correctly, which
  can add `notebook`, `method`, and similar fields to `DataFile.metadata` for
  runs where they were previously missing.
- **`import rainbow` is about five times faster** (roughly 165 ms to 35 ms on
  the machine this was measured on). `pandas`, needed only for the Waters
  transition table, was imported at module load and was by a wide margin the
  largest cost of importing the package. It is now imported where it is used,
  as `matplotlib` already was, and `rainbow.debug`, the next largest cost, is
  imported on first use.
- **Declared `requires-python = ">=3.8"`.** rainbow already needed 3.8, but
  said so nowhere pip could see, so an older interpreter would install this and
  fail at import instead of resolving an older rainbow. No upper bound.
- **`matplotlib` and `pandas` are no longer installed by default. Breaking:**
  neither is needed to read a file. `DataFile.plot` is the only thing that
  draws, and one Waters helper is the only thing that returns a DataFrame, so
  a default install no longer carries either. Both now say which extra to
  install if called without it: `pip install rainbow-api[plot]` and
  `pip install rainbow-api[waters]`. `lxml` stays a default dependency, since
  without it `rb.read_metadata` is about 2.5 times slower.
- **rainbow reads without `lxml` if it has to.** The vendor XML paths that used
  lxml-only XPath were rewritten against the standard library, and the parsers
  fall back to it when lxml is absent; every bundled fixture parses to an
  identical result either way. This is a robustness fallback, not the intended
  configuration, and `rainbow.debug` still needs lxml outright: recovering
  structure from malformed and mis-encoded sidecars is exactly what its
  recovering parser is for.
- **m/z binning split into `display_precision` and `bin_width`. Breaking:** the
  `precision` argument to `rb.read` (and the vendor parsers) is replaced by two
  independent controls. `display_precision` (default `'auto'`) is cosmetic and
  rounds only the displayed m/z labels; `bin_width` is the lossy step that sums
  intensities into a shared m/z grid, and applies to MS channels only.
  `bin_width` defaults to nominal mass (1 Da) for unit-resolution data, and for
  HRMS profile data defaults to the per-scan axis (no shared grid at all), so
  binned output is unchanged by default. A `display_precision` too coarse to
  label a `bin_width`'s bins distinctly is raised to fit, so labels always name
  the columns one to one, and a per-scan centroid is left unrounded because its
  labels are its data. Use `rb.mz_resolution(path)` to see how fine a
  `bin_width` a run can actually support. Code passing `precision=` must now
  pass `display_precision=`, or `bin_width=` to control the binning step.
  `display_precision` no longer applies to a per-scan channel at all: on an
  HRMS profile or a centroid, `mass_labels(i)` is the m/z axis itself rather
  than a display of it, so rounding it discarded measured precision. A
  calibrated TOF centroid kept only 4 decimals on read, and an HRMS profile at
  the vendor default of 0 decimals returned 105,152 points under 2,398 distinct
  labels. `ProfileDataFile.mz_decimals` now defaults to `None` and can still be
  set on the returned file.
- **`rb.read(path, centroid=True)` returns a `CentroidDataFile`. Breaking:** a
  MassHunter `MSPeak.bin` holds a separate peak list per scan, so there is no
  one m/z axis to put them on. The returned object exposes `scan(i)` and
  `mass_labels(i)` and deliberately refuses the shared-axis operations
  (`ylabels`, `data`, `extract_traces`, `to_csvstr`, `plot`), each with an
  explanation, rather than inventing a grid. Pass a `bin_width` to opt into one.
- **`ProfileDataFile.tof` is renamed `flight_times`. Breaking:** the attribute
  holds the shared flight-time axis, and the old name read as though it were the
  instrument rather than the quantity.
- **`display_precision` is bounded above as well as below.** Past about 306
  decimals numpy's rounding overflows and every m/z label becomes NaN, which
  breaks the rule that the labels name their columns one to one. The read entry
  points now refuse a `display_precision` above 17, the point at which a float64
  label stops carrying more information.
- **A `bin_width` of infinity or NaN is refused.** Infinity is greater than
  zero, and then divides every m/z into one bin, so a run came back as a single
  column labelled NaN that matched any ion asked for. NaN lost every comparison
  and reached the parser's overflow guard, which reported a width that was too
  small.
- **`rb.agilent.read` and `rb.waters.read` validate their arguments.** They are
  documented entry points, but only `rb.read` checked `display_precision` and
  `bin_width`, so a negative width silently produced duplicate m/z labels there
  and a non-integer precision raised a `TypeError` from inside the parser.
- **`MZ_FLOORS['agilent']` is 0.05, not 0.1.** A Chemstation `.ms` stores each
  m/z as a big-endian short over 20, a 0.05 Da lattice. Chemstation usually
  writes one decimal place, so a run resolves 0.1 and every bundled fixture
  does, but warning that 0.05 is too fine would be false of a file that
  resolves it. `rb.mz_resolution` still answers per file.
- **Injections are looked up without regard to case**, the way
  `DataDirectory.get_file` already matched a channel: `sequence["RUN.D"]`,
  `"run.d" in sequence` and `get_injection` all agree. `by_name` still spells
  each name the way its directory does.

### Fixed
- **The instrument module inventory is read from the `acq.macaml` Agilent
  actually writes.** It looked for section headers spelled `DAD (G7117B)`;
  ChemStation names the section for the module and puts the model in the
  section ID, so the inventory was empty for every real acquisition method and
  `metadata['modules']` was absent. The ASM device system fell back to the bare
  chromatograph entry as a result.
- **`rainbow.debug.fields` returns the same answer on every filesystem.** The
  walk sorted names within a directory but took sibling directories in
  `readdir` order, which is creation order on APFS and a hash order on ext4.
  Since a scalar field keeps the first value seen, the reported instrument and
  method depended on the machine. The whole stream is now sorted by relpath,
  which is what the walk already claimed.
- **UTF-16 method and macro files are parsed rather than called binary.** The
  text-or-binary test counted non-printable bytes in the raw file, and UTF-16
  is about half NUL, so every UTF-16 member of that family was classified
  binary and skipped. Seven of the nine committed `.MTH`/`.MAC` fixtures are
  UTF-16.
- **`rainbow.debug` decodes BOM-less UTF-16BE.** The byte order is now inferred
  from where the NULs fall rather than assumed little endian, which turned
  every big-endian sidecar into mojibake.
- **`rainbow.debug.xml.canonical` no longer raises on an empty root.** A
  document like `<Sample/>` converts to a bare string rather than a mapping,
  and the handlers read fields off a mapping. `fields` hid the `AttributeError`
  behind a blanket except; the documented `canonical(parse(path))` call did not.
- **The lxml sequence parser no longer drops peaks from a nested document.** It
  pruned earlier siblings unconditionally after each matched element, so a
  `Signal` inside a `SignalResult` destroyed the `Signal_ID` and `Peak`
  siblings that `SignalResult` had not been read for yet. Agilent's own exports
  do not nest that way, but the reader is pointed at documents rainbow did not
  write, and the two backends are documented to agree.
- **The m/z probe reaches partial `.ms` files.** `_labels_only` was not passed
  to the partial reader, so `rb.mz_resolution` built the full intensity grid for
  those channels to read nothing but the axis off it.
- **ASM export refuses a non-finite value instead of writing `NaN`.** Bare
  `NaN` and `Infinity` are not JSON, and a document holding one is rejected by
  any strict reader outside Python.
- **`export_asm` no longer truncates a file on a handle that cannot hold
  Unicode.** It forced characters through as themselves, so a handle the caller
  opened as cp1252 or latin-1 raised `UnicodeEncodeError` partway through and
  left a file that looked complete. Such a handle now gets escaped JSON, which
  says the same thing; a UTF handle is unchanged.
- **ASM export says when it emits a timestamp with no UTC offset.** That is the
  single reason a default export of most ChemStation and Waters runs does not
  validate, and only the changelog and the concepts page said so. Warned once
  per document, and not at all when the source recorded an offset or
  `utc_offset=` supplied one.
- **A Waters sequence directory is told why it cannot be read.** It was told it
  holds no injection subdirectories, which was untrue of a directory full of
  `.raw` injections; the reason is that sequence reading is implemented for
  Agilent.
- **`pip install rainbow-api[test]` installs `python-lzf`,** so CI runs the two
  LZF `MSProfile.bin` decode tests instead of skipping them.
- **ASM timestamps are ISO 8601.** `measurement time` and `injection time`
  passed the vendor's own spelling straight through, so an exported document
  carried values like `27-Feb-18, 10:11:50` where the Allotrope core schema
  types an ISO 8601 timestamp ("All timestamps MUST be in ISO8601 date/time
  format"). Every vendor path was affected except OpenLab `.dx`, which already
  stores ISO. The ChemStation, Waters, and Agilent sequence spellings are now
  converted; one rainbow cannot parse is omitted rather than passed through,
  since a vendor-format string there is a value no ASM reader can read.

  Most of those formats record local wall clock with no UTC offset, and rainbow
  will not invent one: a fabricated offset would move the recorded instant by
  up to a day. So the default output is ISO 8601 without an offset, which is
  not strict RFC 3339 (what `format: date-time` means). Pass the new
  `utc_offset=` argument to `to_asm`, `export_asm`, and their sequence
  equivalents to supply the offset and get a fully conforming document; an
  offset the source did record is never overridden. See the ASM documentation.
- **The ASM conformance test now checks string formats.** It built its
  validator without a format checker, and jsonschema treats `format` as an
  annotation unless you supply one, so the suite validated structure and never
  checked a single timestamp. That is why the non-ISO timestamps above passed
  it. The `validate` extra now also installs `rfc3339-validator`, without which
  jsonschema silently skips `date-time` even when a checker is supplied, and
  the test skips loudly rather than passing vacuously if it is missing.
- **A non-ultraviolet detector module is no longer reported as an ultraviolet
  one** in a document's instrument inventory. Any module whose type was
  `detector`, or whose name merely contained the word, was filed under the
  ultraviolet class, so an FID, RID, ELSD, mass-spectrometer, or
  charged-aerosol module contradicted the very cube it described. Each now maps
  to the AFO class its cube already uses, matched as whole words with an
  optional module index (`FID1`, `RID1A`, `FID_2`) so `hybrid` and `cascade`
  are not mistaken for detectors. Thermal-conductivity, electron-capture, and
  fluorescence modules get their own AFO classes, and the spelled-out
  ultraviolet names (`Variable Wavelength Detector`, `TUV`, `PDA`) are
  recognized alongside the acronyms.
- **A detector in a gas chromatography document is no longer typed as a liquid
  chromatography one.** AFO makes `liquid chromatography detector` and `gas
  chromatography detector` disjoint siblings, so the generic class used for a
  detector AFO cannot name (a charged-aerosol detector, an analog input) has to
  follow the document it rides in; it was fixed at the liquid one. This applies
  to both the instrument inventory and the per-channel device control document.
  A run with no module inventory at all likewise now declares itself a
  `gas chromatograph` rather than a `liquid chromatograph` when exported as GC.
- **`rb.from_asm` no longer raises on documents rainbow did not write.** It
  tolerated one shape and crashed on the rest: a missing measurement aggregate,
  a lone object where a list is declared, an empty device-control list, and a
  cube described without its `data` member, which the published cube structure
  does not require. It also no longer raises when a field holds something other
  than its declared type: a cube, injection document, or device system that is
  not an object, a device document that is not a list, a name or analyst that is
  not a string, a timestamp written in the `{"value": ...}` form the core schema
  also permits, or cube values that are not the numbers the cube declares.
  Anything it cannot represent is skipped, as an unrepresentable cube always
  was, and an unreadable field costs only itself: the channel still comes back.
  Verified by mutating every field of five documents, rainbow's own and two
  third-party, to each of eleven wrong shapes (10,362 reads, no exception).
- **`rb.read(path, centroid=True, bin_width=...)` no longer warns falsely.** The
  m/z floors describe unit-resolution data, but were applied to calibrated
  MassHunter TOF centroids, which resolve far below them, so a perfectly
  sensible bin was reported as too fine.
- **`rb.mz_resolution(path, centroid=True)`** can inspect a centroid run. MS
  data in an `MSPeak.bin` is parsed only under that flag, so such a run
  previously came back as though it had no MS at all. A quantized centroid
  (an uncalibrated quadrupole, whose peak m/z sit near nominal mass) reports
  its quantization. A calibrated TOF centroid is parsed but reports nothing:
  its peaks carry continuous m/z, so there is no lattice to state, and the
  channel is absent from the result rather than given an invented number.
- **`DataDirectory.list_analog()` no longer raises on a MassHunter DAD's
  telemetry.** It read a trace's description from a key MassHunter does not
  use, so listing the analog traces of a run acquired with a DAD raised
  `KeyError` instead of printing them.
- **`rainbow.debug` reports a missing `lxml` instead of hiding it.**
  `inspect()` recorded the failure per file and `fields()` returned an empty
  record, so an environment without `lxml` looked like a run with no metadata.
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
