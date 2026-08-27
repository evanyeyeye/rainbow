.. _api:

.. currentmodule:: rainbow

rainbow API 
===========

The :code:`read` method, :code:`DataFile` class, and :code:`DataDirectory` class are most useful to the end user.

.. autosummary::
   :nosignatures:
   :toctree: api

   read
   read_metadata
   datafile.DataFile
   datadirectory.DataDirectory

To inspect what m/z grid a run actually records, which is the practical ceiling
on :code:`read`'s :code:`bin_width`:

.. autosummary::
   :nosignatures:
   :toctree: api

   mz_resolution

:code:`mz_resolution` reads the run to answer for that run. Two module
constants answer more cheaply, without reading anything:

.. code-block:: python

   >>> rb.VENDORS
   ('agilent', 'waters')
   >>> rb.MZ_FLOORS
   {'agilent': 0.05, 'waters': 0.03}

:code:`MZ_FLOORS` is the finest grid each vendor's unit-resolution MS format
can express, in daltons, and is what :code:`read` warns against when a
:code:`bin_width` is finer than the data supports. It is a floor for the
vendor, not for a particular run: a high-resolution MassHunter profile resolves
far below its entry, and a calibrated centroid has no lattice at all. Use it to
pick a starting :code:`bin_width` without opening a file, and
:code:`mz_resolution` when the run itself matters.

To read a whole multi-injection sequence, and to convert to and from the
Allotrope Simple Model (ASM), use the following. See the :ref:`sequences`
guide for an overview.

.. autosummary::
   :nosignatures:
   :toctree: api

   read_sequence
   datasequence.DataSequence
   from_asm
   sequence_from_asm
   iso_timestamp

Those interested in directly parsing specific files should also view the following:

.. autosummary::
   :nosignatures:
   :toctree: api

   agilent.read
   agilent.read_metadata
   agilent.chemstation
   agilent.masshunter
   waters.read
   waters.read_metadata
   waters.masslynx

Vendor sidecar metadata
-----------------------

A vendor run directory ships far more metadata than the read path surfaces:
registers, INIs, audit trails, method dumps. :code:`rainbow.debug` decodes those
sidecars on demand, and is read-only. It is off the normal path: the subsystem
is imported on first use, so a program that never calls it does not pay for it.

.. autosummary::
   :nosignatures:
   :toctree: api

   debug.inspect
   debug.fields

A catalogue of every sidecar format rainbow decodes, with the layout of each,
is in :doc:`debug/overview`.
