.. _asm-detectors:

Detectors
=========

rainbow tags every channel it reads with a detector kind: ``UV``, ``MS``,
``FID``, ``CAD``, ``ELSD``, or ``RID``. Export is driven by that tag, not by the
vendor.

Most detectors export faithfully under their own measure (see the table below).
RID is the one interim: it rides the absorbance cube because the schema has no
refractive-index measure. Full-scan MS is exported only ion by ion, on request.
And an FID routes the whole run to a gas-chromatography document, which changes
the technique the file declares.

Status at a glance
------------------

.. list-table::
   :header-rows: 1
   :widths: 14 22 18 16 18 12

   * - Detector
     - AFO device type
     - Cube
     - Measure / unit
     - Target model
     - Status
   * - UV (chromatogram)
     - ultraviolet detector
     - 1D chromatogram
     - absorbance / mAU
     - liquid chromatography
     - supported
   * - UV (DAD spectrum)
     - diode array detector
     - 2D spectrum
     - absorbance / mAU
     - liquid chromatography
     - supported
   * - CAD
     - liquid chromatography detector
     - 1D chromatogram
     - electric current / pA
     - liquid chromatography
     - supported
   * - ELSD
     - evaporative light scattering detector
     - 1D chromatogram
     - intensity / RLU
     - liquid chromatography
     - supported
   * - RID
     - refractive index detector
     - 1D chromatogram
     - absorbance / mAU [#interim]_
     - liquid chromatography
     - interim
   * - MS (SIM)
     - mass spectrometer
     - 1D mass chromatogram (per ion)
     - count / Counts
     - liquid chromatography
     - supported
   * - MS (scan)
     - mass spectrometer
     - 1D mass chromatogram (per requested ion)
     - count / Counts
     - liquid chromatography
     - on request
   * - FID
     - flame ionization detector
     - 1D chromatogram
     - electric current / pA
     - gas chromatography
     - supported
   * - HRMS (per-scan profile)
     - mass spectrometer
     - (ragged)
     - per-scan m/z
     - n/a
     - out of scope

The device types are AFO classes, confirmed against the ontology. See
:ref:`asm-the-standard` for how that check works.

.. [#interim] **Interim.** The schema has no refractive-index measure, so a RID
   alone rides the absorbance cube: its measure reads ``absorbance``/``mAU``
   though the values are not absorbance. The device type stays truthful. The
   alternative is to drop the channel; rainbow keeps it under an imprecise label.

UV
--

A single-wavelength channel ``(N, 1)`` becomes a 1D chromatogram cube (retention
time to absorbance); a diode-array acquisition ``(N, W)`` becomes a 2D spectrum
cube (retention time by wavelength). Absorbance is pinned to ``mAU`` by the
model, so a source in ``AU`` is converted on the way out. See :ref:`asm-concepts`
for the cube structure.

CAD, ELSD, and RID
------------------

**CAD and ELSD are faithful; RID is an interim.** Each is a single ``(N, 1)``
chromatogram. A charged-aerosol detector measures a current, so CAD exports as
``electric current`` in ``pA`` (its AFO class is the generic ``liquid
chromatography detector``, as AFO has no charged-aerosol class); an ELSD exports
as light ``intensity`` in ``RLU``. Both use the generic detector cubes the
chromatography ADM provides, so the measure concept is truthful and the values
are the vendor's own, unscaled.

RID has no refractive-index measure in the published schema, so it alone still
rides the absorbance cube [#interim]_.

A subtlety, where peaks meet measures: the schema attaches a processed-data peak
list only to an *absorbance* measurement. So when a CAD, ELSD, or FID channel
carries integrated peaks, rainbow relabels its measure to ``absorbance``/``mAU``
to keep them, rather than emit the peaks against a measure the schema forbids and
fail validation. The device type stays truthful, and a measurement note records
the real quantity, so nothing is silently lost. A channel without peaks keeps its
faithful measure; UV and RID are never affected.

MS
--

**SIM is exported in full; full-scan MS ion by ion on request; HRMS profile is
out of scope.** rainbow stores unit-resolution MS as a rectangular grid (the
binning happened at read time). SIM or scan is read from the acquisition
metadata (Agilent's ``Acquisition Mode`` in ``acqmeth.txt``; Waters' function
type in ``_FUNCTNS.INF``, where SIM is called SIR), surfaced as each channel's
``acquisition_mode``; absent that, a single-ion channel is taken as SIM.

- **SIM** is the set of monitored ions, ``(N, M)``. **Every** ion is exported
  faithfully as its own ``mass chromatogram data cube`` (retention time to
  ``count`` in ``Counts``); the monitored m/z, which the cube has no dimension
  for, is recorded in the label.
- **Scan** is ``(N, M)`` over a contiguous m/z range. The published schema has
  no cube for that retention-by-m/z surface, so the scan is exported **only on
  request**: pass ``ions=[...]`` and each m/z is pulled from the grid as its own
  mass chromatogram, like a SIM ion. An m/z with no match within half a dalton
  is skipped with a warning.

In a gas-chromatography run (one with an FID channel) these mass chromatograms
ride the gas-chromatography document instead, so a GC-MS run exports whole; see
**FID** below for how an FID sets the technique.

**HRMS per-scan profile data is out of scope.** A time-of-flight acquisition
samples every scan on its own m/z grid, so it is irreducibly ragged and does not
fit a single rectangular cube. Exporting it would mean one document per scan, so
it is left out; see the HRMS access model in the :ref:`API <api>`.

FID
---

**Supported, as gas chromatography.** A flame ionization detector is a single
``(N, 1)`` chromatogram, and the gas-chromatography ADM models its real quantity,
so it exports faithfully as a ``chromatogram data cube`` measuring ``electric
current`` in ``pA``, with the device named a ``flame ionization detector``.

Because FID is a gas-chromatography detector, a run that has one is exported as a
gas chromatography document, which on ``REC/2026/03`` admits the run's UV and MS
cubes too, so a GC-MS or UV-plus-FID run exports losslessly. The technique is
read from the method (ChemStation's ``Sample Inlet : GC``), with an FID-presence
fallback; force it with ``to_asm(technique="GC")`` or ``"LC"``.

One caveat: the gas-chromatography schema requires an injection document with a
volume on every measurement, so a run that records no injection volume cannot
fully satisfy the schema. rainbow emits what the source carries rather than
fabricating a volume.
