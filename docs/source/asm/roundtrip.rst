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
   * - **Export-only**
     - non-absorbance cubes
     - Import rebuilds absorbance channels. A CAD, ELSD, or FID cube, and a
       mass chromatogram, are written but not read back, so they survive the
       export and are dropped at import. RID is not among them: it rides the
       absorbance cube, so it returns (as a UV ``DataFile``, per above).
   * - **Lossy**
     - run name, unexported method fields
     - The ``.D`` directory name is not recovered: import names a run ``asm``
       unless you pass ``name=``, even though the name may appear in the
       document as an injection identifier. Nor are the method values rainbow
       reads but does not export, such as column temperature, flow rate, and
       dilution.

The lossy fields are lost at export: they are not part of what :code:`to_asm`
writes, so no reader could recover them. The export-only cubes are the other
way round, present in the document but outside what :code:`from_asm` rebuilds.

Idempotence
-----------

Over the channels import rebuilds, a second export reproduces the first: the
same measurements, carrying the same measure values. The one thing to supply is
the run name, which import otherwise replaces with its default:

.. code-block:: python

   first = datadir.to_asm()
   again = rb.from_asm(first, name=datadir.name).to_asm()

Two caveats keep this from being ``again == first`` in general.

A run that carries a non-absorbance detector does **not** re-export identically:
those cubes are export-only, so the second document is missing them. A run with
UV and CAD channels comes back with its absorbance channels and without its CAD
channel. Compare the cubes you care about rather than the whole document.

Retention times can also differ in their last floating-point digit, because the
seconds-to-minutes conversion is not always exactly reversible. Whether any
given run trips over this depends on its times: an all-absorbance Waters run
whose times survive the conversion exactly does compare equal, and one whose
times do not still differs by a few ulp in the retention dimension. So compare
retention times with a tolerance:

.. code-block:: python

   import numpy as np

   def measurements(document):
       aggregate, = (v for k, v in document.items() if k.endswith("aggregate document"))
       injections, = (v for k, v in aggregate.items() if k.endswith("chromatography document"))
       for injection in injections:
           yield from injection["measurement aggregate document"]["measurement document"]

   def cube(measurement):
       key, = (k for k in measurement if k.endswith("data cube"))
       return measurement[key]["data"]

   # Key by identifier rather than position: an export-only channel is absent
   # from the second document, so the two are not aligned pairwise.
   rebuilt = {m["measurement identifier"]: m for m in measurements(again)}
   for before in measurements(first):
       after = rebuilt.get(before["measurement identifier"])
       if after is None:
           continue                      # export-only, as described above
       # measures survive exactly; the retention dimension may drift by ulps
       assert cube(before)["measures"] == cube(after)["measures"]
       assert np.allclose(cube(before)["dimensions"][0],
                          cube(after)["dimensions"][0])

Re-exporting does not degrade the measure values themselves; only the retention
dimension is subject to the drift above.
