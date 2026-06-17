.. _icpms:

Agilent ICP-MS MSProfile.bin File Structure
============================================

This file format contains Agilent ICP-MS data (for example, from an Agilent
7700 single-quadrupole or an Agilent 8900 triple-quadrupole instrument). It
shares its container and several index files with the :ref:`HRMS format <hrms>`,
but the MSProfile.bin payload is laid out differently and is **not compressed**.

ICP-MS data is distinguished from HRMS data by the presence of a
:code:`MSScan_XSpecific.bin` file in the AcqData subdirectory.

The data is encoded across several files:

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - File
     - Information
   * - MSTS.xml
     - Number of retention times
   * - MSTS_XSpecific.xml
     - Number of isotope channels (masses)
   * - MSScan.xsd
     - File structure of MSScan.bin
   * - MSScan.bin
     - Per-scan retention time, data offset, and point count
   * - MSScan_XSpecific.bin
     - Presence flags the directory as ICP-MS data
   * - MSProfile.bin
     - Intensity values (uncompressed)
   * - MSTS_XAddition.xml
     - Real isotope m/z labels (located one level above AcqData)

**MSTS.xml** and **MSScan.xsd** are read exactly as in the
:ref:`HRMS format <hrms>`: the summed :code:`NumOfScans` gives the number of
retention times, and the XSD defines the :code:`ScanRecordType` records that
make up MSScan.bin (beginning at offset 0x58). For ICP-MS, only the scan's
retention time, :code:`SpectrumOffset`, and :code:`PointCount` are needed —
the data is uncompressed, so the uncompressed byte count is not used.

**MSTS_XSpecific.xml** lists one :code:`Masses` element per isotope channel.
Counting them gives the number of channels recorded at every retention time.

**MSTS_XAddition.xml** (one directory above AcqData) maps each channel index to
its real isotope m/z through :code:`ProductIonMZ`. These become the m/z labels.
If the file is absent, the per-channel :code:`XValue` from MSScan_XSpecific.bin
is used as a fallback.

.. code-block:: xml

   <MSTS_XAddition_IndexedMasses>
       <Index>1</Index>
       <PrecursorIonMZ>12</PrecursorIonMZ>
       <ProductIonMZ>12</ProductIonMZ>
   </MSTS_XAddition_IndexedMasses>

**MSProfile.bin** stores, for each retention time, four parallel blocks of
:code:`PointCount` values. Assume little-endianness.

.. list-table::
   :widths: 60 40
   :header-rows: 1

   * - Block
     - Data Type
   * - Channel index
     - Float (4 bytes each)
   * - Reported value (the reported intensity)
     - Double (8 bytes each)
   * - Raw pulse count
     - Double (8 bytes each)
   * - Analog value
     - Double (8 bytes each)

**rainbow** keeps the reported values, which are the intensities that
MassHunter writes to its CSV export. The raw pulse and analog blocks (used for
secondary-electron-multiplier detector cross-calibration) are skipped.

A single data segment can be visualized as follows. The inner blocks are not
drawn to scale, and each block holds :code:`PointCount` entries.

.. code-block:: text

   +---------+---------++----------+----------++-------+-------++--------+--------+
   | index 1 | index 2 || reported | reported || pulse | pulse || analog | analog |
   +---------+---------++----------+----------++-------+-------++--------+--------+
   |                            repeats for every retention time                  |
   +------------------------------------------------------------------------------+

.. note::

   ICP-MS parsing is reached through the MassHunter path, so it requires
   :code:`hrms=True`::

       import rainbow as rb
       datadir = rb.read("path/to/data.d", hrms=True)

   Unlike the HRMS format, ICP-MS data is uncompressed and does **not** require
   the optional ``python-lzf`` dependency.

   This parser currently supports time-resolved acquisitions with a single tune
   mode and one measurement per isotope. Files with multiple tune modes (e.g.
   several collision/reaction gas settings) or multiple measurements per isotope
   are not yet handled.

The decoding of this format was contributed by Jeremy Hourigan (UC Santa Cruz);
see `issue #25 <https://github.com/evanyeyeye/rainbow/issues/25>`_.
