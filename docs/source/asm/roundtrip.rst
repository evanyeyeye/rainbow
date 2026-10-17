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

Each chromatogram cube becomes a ``DataFile`` again: retention time converts
back from seconds to minutes, and the measure array reshapes back into the data
grid. The device system document becomes the instrument metadata, and any
processed-data peak list becomes the channel's peaks. Peaks are read from every
measurement, whether or not its trace could be rebuilt, so an index document
whose cubes carry no values still yields its integrations.
:code:`rb.peaks_from_asm(measurement)` reads one measurement document's peaks
the same way, for a caller walking a document itself.

Documents from other tools are read a little more generously than rainbow's own
need. Three habits of an Agilent OpenLab or Empower export are worth knowing
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
* **The optics may only be in the cube label.** rainbow reads the device
  control document's settings first (:code:`detector wavelength setting`,
  :code:`detector bandwidth setting`, the reference and excitation settings),
  then what the cube label names (:code:`"DAD.0.0, DAD: Signal A, 246.0
  nm/Bw:4.0 nm Ref 360.0 nm/Bw:100.0 nm"`, :code:`"DAD1A,Sig=254,4 Ref=off"`,
  :code:`"PDA Ch1 280nm@4.8nm"`, :code:`"ACQUITY FLR ChA Ex280,Em340 nm"`),
  then the processed data's description of the signal. They land in the
  channel's metadata under the keys the vendor readers use:
  :code:`wavelength`, :code:`bandwidth`, :code:`reference_wavelength` and
  :code:`reference_bandwidth`, plus :code:`excitation_wavelength` and
  :code:`emission_wavelength` for a fluorescence channel. :code:`Ref=off`
  reads as a :code:`reference_wavelength` of :code:`None`, present. The label
  is kept whole as the channel's and the peak group's :code:`description`.
* **A peak records the baseline it was integrated from.** Empower writes the
  integration type at each edge, read into :code:`baseline_start_code` and
  :code:`baseline_end_code` (:code:`B`, :code:`V`, :code:`S`, :code:`T`, ...,
  lowercase for an edge moved by hand, and a group's :code:`Gp` split into
  :code:`G` and :code:`p`). Its Start and End Height, how far the trace sits
  above the baseline at each edge, are read into :code:`start_height` and
  :code:`end_height` in the peak height's unit, so the line runs from
  :code:`(start_time, trace -
  start_height)` to :code:`(end_time, trace - end_height)`. Empower fills
  :code:`baseline value at start of peak` (and :code:`end`) with the time the
  baseline under the peak's cluster begins (and ends), read into
  :code:`baseline_start_time` and :code:`baseline_end_time` in minutes when
  the unit is ``s`` or ``min``. The schema defines neither the codes nor these
  times, so rainbow writes them as the peak's custom information, under the
  same labels, and reads them from either place. All are :code:`None` when the
  document does not carry them.
* **A peak's height and area are in the detector's unit.** An absorbance in
  AU, mAU or Empower's µV is converted to mAU (mAU.s for an area); any other
  unit, a fluorescence channel's RFU or an FID's pA, is kept as written. The
  unit is in the peak's :code:`height_unit` and :code:`area_unit`, which are
  :code:`None` only when the document wrote none. The peak's own
  :code:`identifier` and :code:`index` (its :code:`@index`) are read too, and
  each integration's :code:`processing` records its :code:`description`
  beside its identifier, group identifier, time and method.

Every chromatogram cube is reconstructed, whatever it measures, with its unit as
the document writes it in the channel's :code:`metadata["unit"]` and the
measure concept in :code:`metadata["measure"]`. The detector is named from the
device type (:code:`metadata["device_type"]`, as written), then from the cube
label or the measurement identifier, then from the measure: a diode-array or
ultraviolet detector is ``UV``, a refractive-index detector ``RID``, a
fluorescence detector ``FLD``, an evaporative light scattering detector
``ELSD``, a flame ionization detector ``FID``, and a charged-aerosol detector or
the analog input Chemstation brings one in on ``CAD``. A channel rainbow has no
detector name for (a conductivity detector, an electric current from a detector
it cannot name) has detector :code:`None` and joins the directory's
:code:`analog` traces rather than being given a name it would be guessing at.
The DAD spectrum cube is reconstructed as UV. The mass chromatograms (SIM or
extracted ions) are export-only.

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
     - mass chromatograms
     - A SIM or extracted-ion mass chromatogram is written but not read back:
       one ion's trace has no m/z axis to give a ``DataFile``.
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

A run that carries MS channels does **not** re-export identically: the mass
chromatograms are export-only, so the second document is missing them. Nor
does a channel with peaks but no rebuilt trace: a peak list rides the
measurement of its channel, so peaks read from an index document (whose cubes
carry no values) or on an analog channel (detector :code:`None`) have nowhere
to go on export, and :code:`to_asm` warns once for each such group rather than
drop it in silence. Compare the cubes you care about rather than the whole
document.

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

The same document supplies the vial position, the ``well plate identifier``
(``metadata["well_plate_id"]``) and the ``sample role type``
(``metadata["sample_role"]``, as written, ``"unknown sample role"`` included),
and the last two are written back on export. REC/2026/06 has no sample document
property for the plate, so rainbow writes it as the sample's custom information
under the label ``well plate identifier``, and reads it from either place into
``well_plate_id`` (not into ``sample_custom``).

One thing this gives up, deliberately. A document whose channels split the
fields between them -- the identifier on one, the custom fields on another --
yields only the chosen one's, because a mixture is the thing being avoided.
``description`` and ``blank`` are still dropped.

Peaks without an exported channel
---------------------------------

:func:`rainbow.from_asm` reads every measurement's peaks, but :code:`to_asm`
can write a peak list only on a measurement it writes. Two kinds of group read
from ASM therefore do not survive a re-export, and each is warned about once:

* peaks of a measurement whose cube carried no values (an index document),
  since no trace was rebuilt to export;
* peaks on a channel rainbow has no detector name for (a conductivity
  detector, an unnamed current), which joins :code:`analog` and is not
  exported.

The rest of the envelope
------------------------

A measurement's ``injection time`` is read into ``metadata["injection_time"]``,
beside the ``measurement time`` in ``metadata["date"]``, and its device
control's ``device acquisition method`` into ``metadata["acq_method"]`` (a gas
chromatography document's ``device method identifier`` too). The records a
document carries once, beside the device system, are read field by field as
written: the ``data system document`` (which software wrote the data, and
which converter made the ASM) into ``metadata["data_system"]``, the ``analysis
sequence document`` (the sample set) into ``metadata["analysis_sequence"]``,
and the ``electronic project record`` into ``metadata["project"]``. For
:func:`rainbow.sequence_from_asm` they are the sequence's metadata. A custom
field's ``scalar integer datum``, which converters write for a count though the
schema does not list it, reads as an ``int``.
