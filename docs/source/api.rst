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
lives in ``docs/debug/`` in the `repository
<https://github.com/evanyeyeye/rainbow/tree/main/docs/debug>`_. It is reference
material for the formats themselves rather than for the API, so it is not part
of this manual.
