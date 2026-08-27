.. _asm-waters:

Waters to ASM
=============

Waters export goes through the same detector-driven machinery as Agilent: the UV
channels of a ``.raw`` run become an ASM document. The difference is scope. A
Waters run is a single acquisition with a leaner metadata envelope, so the
document is correspondingly simpler.

Format
------

rainbow reads the MassLynx ``.raw`` directory.

.. code-block:: python

   import rainbow as rb

   datadir = rb.read("Caffeine.raw")
   datadir.export_asm("Caffeine.asm.json")

There is **no sequence reader** for Waters: :code:`rb.read_sequence` is
Agilent-only, so Waters export is single-run only. A multi-injection MassLynx
project is read one ``.raw`` at a time.

A Waters diode-array run carries a full spectrum cube too; drop or thin it, or
round the numbers, to shrink the document. See :ref:`asm-size`.

Detectors
---------

A Waters ``.raw`` commonly carries UV, CAD, ELSD, and MS channels. Export covers
**UV, CAD, and ELSD** faithfully, each under its own measure (see
:ref:`asm-detectors`). **MS**
follows the same detector rules as Agilent (see :ref:`asm-detectors`): every
monitored ion of a SIM channel exports as a mass chromatogram, and any ion of a
full scan exports on request via ``ions=[...]``. SIM and scan are told apart by
the function type recorded in ``_FUNCTNS.INF`` (Waters calls SIM "SIR",
Selected Ion Recording), surfaced as each MS channel's ``acquisition_mode``.
Waters splits UV into two kinds of file, and rainbow exports both:

- diode-array spectrum files (a retention time by wavelength grid), and
- extracted single-wavelength chromatograms.

One Waters-specific detail matters here. The single-wavelength UV chromatograms
report absorbance in **AU**, but the Allotrope model pins the absorbance measure
to **mAU**. rainbow converts on the way out (1 AU = 1000 mAU), so the exported
values and unit are schema-correct. The diode-array files already use mAU and
pass through unchanged. This is exactly the kind of unit mismatch the
:ref:`conformance tests <asm-the-standard>` exist to catch, and one of them
validates a Waters UV export specifically.

Metadata mapping
----------------

A Waters run fills the same envelope fields as Agilent, where the data is
available:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - rainbow metadata
     - ASM field
   * - ``vendor`` (``Waters``)
     - each device's ``product manufacturer``
   * - ``sample``
     - the measurement's ``sample identifier``
   * - ``date``
     - the measurement time, converted from ``_HEADER.TXT``'s spelling to
       ISO 8601 (see :ref:`asm-timestamps`)
   * - ``wavelength`` (per channel)
     - the detector control's wavelength setting

Limits compared to Agilent
--------------------------

The Waters envelope is thinner than Agilent's, so some fields are simply absent:

- **No sequence document.** Single runs only; there is no shared device system
  document across injections.
- **Less instrument detail.** Waters runs do not carry the per-module model,
  serial, and firmware that Agilent sequences do, so the device system document
  is sparser (often the generic ``liquid chromatograph`` fallback).
- **No injection document** unless an injection volume is present, which Waters
  single-run reads typically do not carry.

None of this affects the signal: the data cubes are identical to Agilent's. Only
the surrounding context is thinner.

A worked example
----------------

.. code-block:: python

   import rainbow as rb

   # A measurement holds exactly one of these, chosen by what the channel is.
   CUBE_KEYS = ("chromatogram data cube",
                "mass chromatogram data cube",
                "three-dimensional ultraviolet spectrum data cube")

   datadir = rb.read("Caffeine.raw")
   document = datadir.to_asm()

   aggregate = document["liquid chromatography aggregate document"]
   lc_document = aggregate["liquid chromatography document"][0]
   measurements = lc_document["measurement aggregate document"]["measurement document"]

   for measurement in measurements:
       cube = next(measurement[key] for key in CUBE_KEYS if key in measurement)
       unit = cube["cube-structure"]["measures"][0]["unit"]
       print(measurement["measurement identifier"], "->", unit)

The unit is the channel's own, not one unit for the whole run: a UV channel
reports :code:`mAU`, an ELSD :code:`RLU`, a CAD :code:`mV`, and an MS channel
:code:`counts`. See :ref:`asm-detectors` for which measure each detector is
published under.

Read the document back with :code:`rb.from_asm`; see :ref:`asm-roundtrip`.
