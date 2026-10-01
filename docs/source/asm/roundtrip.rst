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

Documents from other tools are read a little more generously than rainbow's own
need. Two habits of an Agilent OpenLab or Empower export are worth knowing
about:

* **A channel can carry more than one integration.** Those exporters write one
  processed data document per result version, so the same run arrives
  integrated several times, under different processing methods and at different
  dates, and the peak lists differ: a reintegration finds or loses whole peaks.
  The first is the group's :code:`peaks` and the rest are in its
  :code:`alternates`; :code:`group["processing"]` says which integration the
  default peaks came from. Document order is not processing order, so reading
  such a channel warns. Pick a different one by its
  :code:`processing["identifier"]`, :code:`["group_identifier"]`, or
  :code:`["time"]`.
* **The wavelength may only be in the cube label.** rainbow reads the device
  control document's :code:`detector wavelength setting` first, then falls back
  to the wavelength named in the cube label (:code:`"DAD.0.0, DAD: Signal A,
  246.0 nm/Bw:4.0 nm"`). The label is kept whole as the channel's and the peak
  group's :code:`description`.

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
       height, symmetry), come back identical, in the units the document
       states. One conversion is one-way: absorbance is pinned to ``mAU`` by
       the model, so a Waters channel read in ``AU`` is scaled by 1000 on
       export and returns as the ``mAU`` it now is. The numbers therefore
       differ from the originals by that factor, and nothing in the document
       records that they were once ``AU``. A second round trip changes
       nothing further.
   * - **Conditional**
     - instrument, operator
     - Recovered when the document carried that identity, which for a sequence
       means the source had a top-level ``sequence.acaml``. Without it, the
       device system is sparse and there is nothing to rebuild.
   * - **Conditional**
     - sample name, custom fields
     - A sample document's ``written name`` and its *custom information
       aggregate document* are read into ``metadata["sample_name"]`` and
       ``metadata["sample_custom"]``, and written back when present. Normally
       only a foreign document carries them -- see :ref:`asm-custom-fields`.
   * - **Export-only**
     - non-absorbance cubes
     - Import rebuilds absorbance channels. A CAD, ELSD, or FID cube, and a
       mass chromatogram, are written but not read back, so they survive the
       export and are dropped at import. RID is not among them: it rides the
       absorbance cube, so it returns (as a UV ``DataFile``, per above).
   * - **Lossy**
     - run name, unexported method fields
     - :func:`rainbow.from_asm` names a run ``asm`` unless you pass ``name=``.
       :func:`rainbow.sequence_from_asm` does recover each injection's ``.D``
       name, from the ``injection identifier`` in its injection document, so
       ``seq.get_injection("001-A1_01.D")`` works after a round trip. A liquid
       chromatography run that recorded no injection volume is the exception:
       the model requires the volume beside the identifier, so such a run has
       no injection document at all and falls back to its sample identifier.
       Also not recovered are the method values rainbow reads but does not
       export, such as column temperature, flow rate, and dilution.

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

.. _asm-custom-fields:

Sample name and custom fields
-----------------------------

rainbow's own writer has one slot for a sample and puts it in the ``sample
identifier``, so reading only that was enough to round trip its own output. A
document from another writer distinguishes the two, and hangs the fields the
schema has no place for off a *custom information aggregate document*:

.. code-block:: json

   {"sample document": {
      "sample identifier": "133872",
      "written name": "NB5-P1A11",
      "custom information aggregate document": {
        "custom information document": [
          {"@index": 1, "datum label": "MaterialIdentifier",
           "scalar string datum": "Vax-033898"},
          {"@index": 2, "datum label": "SampleWeight",
           "scalar double datum": 1.0, "unit": "mg"}]}}}

Both come back as metadata, and are written again on export:

.. code-block:: python

   datadir = rb.from_asm(document)
   datadir.metadata["sample"]         # '133872'   -- the identifier
   datadir.metadata["sample_name"]    # 'NB5-P1A11'
   datadir.metadata["sample_custom"]  # {'MaterialIdentifier': 'Vax-033898', ...}

These are not decoration. An Empower export carries the registered sample's id
in ``MaterialIdentifier``, and that is what matches an injection to the sample
downstream, so dropping the custom document loses the only key that join has.
Setting either key before an export writes it, so a run read from a vendor file
can be given a sample name and custom fields it never recorded.

The keys are absent rather than empty when the document carries nothing, so test
for the key rather than for an empty mapping.

A mapping records only the Python type, so that is what picks the datum type on
the way out, and what each is read back as:

.. list-table::
   :header-rows: 1
   :widths: 34 22 44

   * - Datum type
     - Python
     - Note
   * - ``scalar string datum``
     - ``str``
     -
   * - ``scalar double datum``
     - ``int`` or ``float``
     - An ``int`` read as one stays one, so a count comes back a count. Passing
       ``decimal_places=`` rounds it like every other emitted number, which
       makes it a float.
   * - ``scalar double datum`` + ``unit``
     - ``{"value", "unit"}``
     - Only when the document carried a unit, so read a numeric field as
       ``v["value"] if isinstance(v, dict) else v``.
   * - ``scalar boolean datum``
     - ``bool``
     -
   * - ``scalar timestamp datum``
     - ``datetime``
     - Written through the same gate as ``measurement time``: a naive one takes
       ``utc_offset=`` and warns once without it, since the schema's
       ``date-time`` requires an offset. A plain ``date`` is dropped.

Either spelling of a value is read: the bare scalar, or the
``{"@type", "value"}`` object form the schema also permits.

Anything rainbow cannot carry faithfully is warned about and dropped, one field
at a time, rather than coerced -- an unreadable or ambiguous datum type, a value
of no type above, a number JSON cannot carry, an integer too large for a float,
a duplicate or unusable ``datum label``, a ``unit`` beside anything but a
double. The docstrings of ``_custom_fields`` and ``_custom_datum_entry`` give
the reasoning for each. A write-side complaint is made once per document, not
once per channel.

``@index`` orders the fields when the document declares one for every entry;
otherwise its own order stands, since mixing declared indices with document
positions would place an unindexed field among someone else's indices. On export
``@index`` is renumbered 1..n.

One sample per run
~~~~~~~~~~~~~~~~~~

:func:`rainbow.from_asm` merges every injection in a document into one
directory, so the three fields are taken from a single sample document,
together. They are never composed across injections: an identifier from one
beside a ``MaterialIdentifier`` from another would be a join key silently
attached to the wrong sample, which is worse than the absent one it replaces.

The document read is the first carrying a ``sample identifier``, since that is
what everything downstream falls back to, else the first supplying any of the
three. The choice is made across every injection the directory will hold, so an
opening injection that records only a name does not suppress the identifier a
later one carries. :func:`rainbow.sequence_from_asm` builds one directory per
injection and so keeps each sample with its own.

Two things this gives up, both deliberate. A document whose channels split the
fields between them -- the identifier on one, the custom fields on another --
yields only the chosen one's, because a mixture is the thing being avoided. And
``description``, ``sample role type`` and ``blank`` are still dropped: rainbow
has no concept of any of them, so reading one would create a key a re-export
discards. All three are present on every sample document an Empower export
writes, so a sample document does not round trip whole -- only the identifier,
the name, the vial position and the custom fields do.
