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