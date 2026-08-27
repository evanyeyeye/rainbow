.. _sequences:

Sequences
=========

A chromatography run rarely produces a single injection. It produces a
**sequence**: dozens or hundreds of injections acquired back to back on one
instrument, with one shared method. The vendor stores all of it in a directory
tree, with the data in one place, the method in another, and the integrated
peaks in a third.

This guide shows how rainbow reads a whole sequence into one object, what that
object gives you that a single read cannot, and how to move the whole run into
(and back out of) the open Allotrope Simple Model. Sequence reading is
currently implemented for Agilent ChemStation and OpenLab.

A run is more than a single injection
-------------------------------------

With :code:`rb.read` you read one :code:`.D` directory. A sequence directory
holds many of those, plus the run-level files that describe the instrument, the
method, and the data-analysis results.

.. code-block:: text

   Caffeine_Stability/                 <- the sequence directory
   |
   |-- 008-D1F-A1-..._01.D/           <- injection 1
   |     |-- DAD1A.ch  DAD1B.ch ...     the UV channels (the data)
   |     |-- acq.macaml                 method: injection volume, flow, modules
   |     +-- SAMPLE.XML                 sample: name, dilution
   |-- 009-D1F-A2-..._02.D/           <- injection 2
   |-- ...                            <- 384 injections in all
   |
   |-- sequence.acaml                 <- instrument serials, operator, peaks
   +-- Caffeine_Stability.M/       <- the shared method

Reading each :code:`.D` on its own would recover the traces, but it would leave
the instrument, the operator, and every integrated peak locked in the
sidecars. :code:`rb.read_sequence` reads the whole thing at once.

.. code-block:: python

   import rainbow as rb

   sequence = rb.read_sequence("Caffeine_Stability")
   print(sequence)            # Caffeine_Stability: 384 injections

The shape of a sequence in rainbow
----------------------------------

The result is a **DataSequence**. The key idea: a DataSequence is a *container*,
not a new kind of DataDirectory and not a superset of :code:`rb.read`. Each
injection inside it is an ordinary DataDirectory, exactly what :code:`rb.read`
returns for that :code:`.D`. The sequence simply holds them all and adds the
run-level information.

.. code-block:: text

   DataSequence                         rb.read_sequence(path)
   |
   |-- .injections : list of DataDirectory   each one == rb.read(injection)
   |     |-- .datafiles : list of DataFile     the traces and spectra
   |     |-- .metadata  : dict                 sample, operator, volume, ...
   |     +-- .peaks     : list                 only with peaks=True (below)
   |
   |-- .metadata : dict                  instrument, operator, injection_count
   +-- .to_asm() / .export_asm()         the whole run as one ASM document

Because each injection is a DataDirectory, everything you already know still
works, one injection at a time:

.. code-block:: python

   for injection in sequence:               # each is a DataDirectory
       print(injection.name, injection.detectors)
       trace = injection.get_file("DAD1A.ch")

Reading a sequence
------------------

Injections come back in sorted-name order. ChemStation prefixes each injection
directory with its sequence line number, so for the names it writes by default
that is acquisition order; rainbow sorts the names rather than reading a
timestamp, so hand-renamed directories sort by their new names. Reach them by
position, by name, or
by iterating:

.. code-block:: python

   first = sequence.injections[0]
   count = len(sequence)
   named = sequence.get_injection("008-D1F-A1-caffeine_5min_01.D")
   named = sequence["008-D1F-A1-caffeine_5min_01.D"]   # the same
   if "008-D1F-A1-caffeine_5min_01.D" in sequence:
       ...

If the directories were renamed and you want the order the instrument ran them
in, sort on each injection's own timestamp. rainbow does not do this for you,
because an injection whose date is missing or unreadable has no place in such
an ordering and silently dropping it would be worse than name order.

Sort on the parsed instant, not on the string. The vendors write wall clock in
their own spellings (:code:`'27-Feb-18, 10:11:50'`, :code:`'3 Feb 22 11:22 am
-0500'`), which are day-first and name the month, so comparing them as text
returns an order that is not chronological at all:

.. code-block:: python

   timed = sorted(
       (i for i in sequence if rb.iso_timestamp(i.metadata.get("date"))),
       key=lambda i: rb.iso_timestamp(i.metadata["date"]))

:code:`rb.iso_timestamp` returns the ISO 8601 form, which does sort as text,
and :code:`None` for a spelling rainbow cannot read (which is what the filter
drops). It is the same conversion the ASM export uses, so an exported document
orders the same way.

Internally :code:`rb.read_sequence` just calls :code:`rb.read` on each injection
subdirectory and layers the run-level metadata on top, so the per-injection
data is identical to reading each :code:`.D` by hand.

What the run knows that one injection does not
----------------------------------------------

The :code:`metadata` attribute carries what is shared across the run. When the
sequence has a top-level :code:`sequence.acaml`, that includes the instrument
and its modules, with part numbers, serial numbers, and firmware:

.. code-block:: python

   sequence.metadata["operator"]
   instrument = sequence.metadata["instrument"]
   for module in instrument["modules"]:
       print(module["name"], module["part_no"], module["serial_no"])

Each value comes from a specific file. rainbow reads them so you do not have to:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Information
     - Source file
     - Where it lands
   * - UV / DAD traces and spectra
     - ``DAD1*.ch``, ``DAD1.UV``
     - ``injection.datafiles``
   * - Injection volume, flow, column temperature, module models
     - ``acq.macaml``
     - ``injection.metadata``
   * - Sample name, dilution, multiplier
     - ``SAMPLE.XML``
     - ``injection.metadata``
   * - Instrument modules (serial, firmware), operator
     - ``sequence.acaml``
     - ``sequence.metadata``
   * - Integrated peaks
     - ``sequence.acaml`` or ``sequence.acam_``
     - ``injection.peaks``

The operator is also copied onto each injection, so per-injection reads carry it
too.

Integrated peaks
----------------

The peaks ChemStation integrated during data analysis are stored separately
from the traces. Pass :code:`peaks=True` to read them and attach them to each
injection.

.. code-block:: python

   sequence = rb.read_sequence("Caffeine_Stability", peaks=True)

   injection = sequence.injections[0]
   for group in injection.peaks:            # one group per detector channel
       print(group["signal"], group["wavelength"])
       for peak in group["peaks"]:
           print(peak["retention_time"], peak["area"], peak["height"])

Each injection's :code:`peaks` is a list of per-channel groups. A group records
the signal name and wavelength and a list of peaks; each peak carries its
retention time (in minutes), area, area percent, height, height percent, start
and end times, and symmetry.

Peaks come from the run's :code:`sequence.acaml`, or, for any injection that
file does not cover, that injection's own :code:`sequence.acam_`. They are off
by default, like the :code:`hrms` and :code:`centroid` flags, because reading
them parses the full result document.

Exporting a sequence to ASM
---------------------------

A whole sequence moves into the open **Allotrope Simple Model** in one step: one
ASM document with a single device system document for the shared instrument and
one liquid chromatography document per injection, in the same order
:code:`sequence.injections` gives them. Peaks
read with :code:`peaks=True` become each injection's processed data.

.. code-block:: python

   sequence.export_asm("Caffeine_Stability.asm.json")
   document = sequence.to_asm()              # the same document, as a dict

A diode-array sequence can be very large (every injection's spectrum cube is
text); drop or thin the cube, round the numbers, or write one file per injection
with :code:`per_injection=True`. See :ref:`asm-size`.

:code:`rb.sequence_from_asm` reads it back into a DataSequence. For the whole ASM
story, where the standard comes from and how it is validated, what the document
and its data cubes mean, the Agilent specifics, and the fidelity of the round
trip, see the :ref:`ASM guide <asm>`, in particular the :ref:`Agilent page
<asm-agilent>` and :ref:`asm-roundtrip`.

Quick reference
---------------

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Call
     - Result
   * - ``rb.read(injection)``
     - one DataDirectory (one injection)
   * - ``rb.read_sequence(path)``
     - a DataSequence (many injections)
   * - ``rb.read_sequence(path, peaks=True)``
     - the same, with integrated peaks attached
   * - ``sequence.injections``
     - the injections, in sorted-name order
   * - ``sequence.metadata``
     - instrument, operator, injection count
   * - ``sequence.to_asm()`` / ``.export_asm(path)``
     - the run as one ASM document
   * - ``rb.sequence_from_asm(document)``
     - a DataSequence rebuilt from ASM

For the full list of options, see the :ref:`API <api>` documentation for the
DataSequence class.
