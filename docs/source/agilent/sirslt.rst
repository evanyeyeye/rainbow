.. _sirslt:

Agilent OpenLab CDS (.sirslt) Folder Structure
==============================================

OpenLab CDS 2.x stores each single-injection result set as a :code:`.sirslt`
folder. The detector signals are in a :ref:`.dx archive <dx>` inside it, and
the MS binaries are written beside it. The same layout is used for LC and GC
instruments. Every file in the folder shares the folder's name:

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - File
     - Information
   * - ``<name>.dx``
     - The :ref:`.dx archive <dx>`: DAD spectrum, single-wavelength and FID
       signals, and instrument telemetry. For an MS run it also carries the MS
       sidecars under ``MSData/``: ``MSScan.xsd``, ``MSTS.xml``,
       ``Contents.xml`` and ``Devices.xml``.
   * - ``<name>.MSScan.bin``, ``<name>.MSPeak.bin``
     - The MassHunter scan index and centroid spectra, in the same formats as
       a .D's ``AcqData`` folder (see :ref:`MSPeak.bin <mspeak>`). The
       archive's manifest names them in the MS signal's
       ``<ExternalElementPaths>``.
   * - ``<name>.acaml``
     - The result-set document: the instrument (its name, modules, and
       separation technique), the sample, and the method.
   * - ``<name>.rx``
     - Processing results, an archive holding an injection ACAML (not read).
   * - ``<name>.mfx``
     - MD5 checksums of the files above (not read).
   * - ``*.amx``
     - The :ref:`acquisition method <amx>`: what each module was set to.
   * - ``*.pmx``, ``*.sqx``, ``*.scml``
     - Processing method, sequence, and sampler configuration (not read).

**rainbow** reads the archive with the :ref:`.dx <dx>` reader, so a folder
returns exactly the signals its archive would. The MS binaries are read by the
MassHunter decoders, from an ``AcqData`` folder assembled in a temporary
directory out of the archive's ``MSData/`` sidecars and the binaries beside
it. As for a .D, the centroid spectrum is read under :code:`centroid=True`; a
run whose MS data was not asked for says so with
:code:`metadata['centroid_available']`::

    import rainbow as rb
    datadir = rb.read("path/to/run.sirslt", centroid=True)
    datadir.metadata['technique']      # 'LC' or 'GC'
    datadir.get_file("MSPeak.bin")     # per-scan centroid peak lists

The binaries are found by the names ``<ExternalElementPaths>`` gives, matched
by file name alone and without regard to case, so a name written with a
directory still finds the file beside the archive. If those names find no
``MSScan.bin``, the folder is searched for ``*.MS*.bin`` files instead, and
binaries kept under the archive's ``MSData/`` are read too. MS data that is
present but cannot be decoded (no ``MSScan.bin``, or no ``MSData/MSScan.xsd``
to decode it with) is not reported as available, and reading the folder warns
why.

An OpenLab single-quadrupole LC/MS writes version 2.1 of ``MSScan.xsd``, whose
scan record ends in an optional ``Padding`` element with no fixed size. No pad
bytes are stored: the records tile ``MSScan.bin`` exactly without it. Its
centroid abundances are fractional, and are returned as float64; each scan's
peaks sum to the TIC the instrument recorded for it.

Like a .D's centroid, a ``.sirslt``'s is returned per scan by default: a
:class:`~rainbow.agilent.masshunter.CentroidDataFile` of peak lists with no
``ylabels`` (see :ref:`hrms-data-model`). Unlike a Chemstation ``.ms`` file,
which ``rb.read`` bins to 1 Da by default (see :ref:`ms`), it is not binned
unless asked. Pass :code:`bin_width=1` for the same nominal-mass grid a single
quadrupole's ``.ms`` gives::

    datadir = rb.read("path/to/run.sirslt", centroid=True, bin_width=1)
    datadir.get_file("MSPeak.bin").ylabels   # whole-dalton m/z

LC or GC
--------

The run's separation technique is recorded as :code:`metadata['technique']`
(``'LC'`` or ``'GC'``), and :func:`rainbow.agilent.sirslt.technique` returns it
for a folder without reading its data. It is taken, in order of authority,
from:

1. the instrument's ``<Technique>`` in the ``.acaml``
   (``LiquidChromatography`` or ``GasChromatography``);
2. the ``<SeparationTechnique>`` of ``MSData/Contents.xml`` in the archive,
   for an MS run (``2`` is GC, ``3`` is LC);
3. the manifest: a "GC" injection source, or a detector only a gas
   chromatograph has (FID, TCD, NPD, FPD, SCD, NCD). An ECD is not counted:
   the name is used for a GC electron-capture detector and an HPLC
   electrochemical detector alike.

A run that recorded no detector signal, such as a column flush whose archive
holds only telemetry, is still read: it returns its metadata and no
datafiles. Integrated peaks are not read from a .sirslt; asking for them warns.

Acquisition method
------------------

The folder's acquisition method (the ``.amx`` named after the folder, else
its only one; none when it holds several and none is named after it) is read
as :ref:`amx` describes, by :code:`rb.read` and :code:`rb.read_metadata`
alike, and its settings are stated in the run's metadata in the keys a .D's
``acq.macaml`` gives. What the result-set document already states (the
technique, above all) stays.
