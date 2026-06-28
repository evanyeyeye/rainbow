.. _asm-roundtrip:

Reading ASM back in
===================

rainbow reads ASM back too. :code:`rb.from_asm` reverses :code:`to_asm`;
:code:`rb.sequence_from_asm` reverses :code:`sequence.to_asm`. Each rebuilds
rainbow objects from a document, so an ASM file written anywhere reads back into
a DataDirectory or DataSequence.

.. code-block:: python

   import json
   import rainbow as rb

   document = json.load(open("Caffeine.asm.json"))
   datadir = rb.from_asm(document)                 # a DataDirectory

   document = json.load(open("Caffeine_Stability.asm.json"))
   sequence = rb.sequence_from_asm(document)       # a DataSequence

Each UV cube becomes a ``DataFile`` again: retention time converts back from
seconds to minutes, and the measure array reshapes back into the data grid. The
device system document becomes the instrument metadata, and any processed-data
peak list becomes the channel's peaks. A measurement from some other tool that
rainbow's exporter would not have written is skipped rather than guessed at.

Import is narrower than export: only the absorbance (UV) cubes are reconstructed,
both the single-wavelength chromatogram and the DAD spectrum, as a ``DataFile``
(RID too, since it rides the absorbance cube). Everything else is export-only and
skipped on the way back: the generic detector cubes (CAD, ELSD, FID) and the mass
chromatograms (SIM or extracted ions). The one exception is a CAD, ELSD, or FID
channel that carried integrated peaks: on export it is relabeled to absorbance so
the schema can hold its peak list, so on import it returns as a UV ``DataFile``
(its faithful detector kind is lost). A
gas-chromatography document is still read for its UV channels, if any. So the
round trip is exact for UV; the other cubes are a one-way, open-format export.

What survives the round trip
----------------------------

A round trip is ``.D`` to objects to ASM and back to objects. Three tiers of
fidelity:

.. list-table::
   :header-rows: 1
   :widths: 22 18 60

   * - Fidelity
     - What
     - Detail
   * - **Exact**
     - data cubes, peaks
     - The signal values and axes, and every integrated peak (retention, area,
       height, symmetry), come back identical.
   * - **Conditional**
     - instrument, operator
     - Recovered when the document carried that identity, which for a sequence
       means the source had a top-level ``sequence.acaml``. Without it, the
       device system is sparse and there is nothing to rebuild.
   * - **Lossy**
     - ``.D`` folder name, unexported method fields
     - ASM does not store the original ``.D`` directory name (a run is renamed
       from its sample identifier), nor the method values rainbow reads but does
       not export, such as column temperature, flow rate, and dilution.

The lossy fields are lost at export, not at import: they are simply not part of
what :code:`to_asm` writes, so no reader could recover them. Everything ASM does
carry comes back faithfully.

Idempotence
-----------

Because import is the clean inverse of export over the fields ASM stores, a
second export reproduces the first. The one thing to supply is the run name:
the run identifier in the document is the original ``.D`` folder name, which
import otherwise replaces with its default, so pass the same name back to get an
identical document.

.. code-block:: python

   first = datadir.to_asm()
   again = rb.from_asm(first, name=datadir.name).to_asm()
   assert again == first

Re-exporting does not degrade the data; only the first export off the vendor
binary drops the lossy fields. One caveat: retention times can differ in their
last floating-point digit, because the seconds-to-minutes conversion is not
always exactly reversible. The values themselves are unchanged.
