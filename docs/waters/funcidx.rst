.. _funcidx:

Waters FUNC .IDX File Structure
===============================

This format stores information about UV and MS spectra. 

These files are named something like _FUNC001.IDX. 

Each FUNC .IDX file is paired by number with a FUNC .DAT file (which may be in the :doc:`2-byte <funcdat2>`, :doc:`6-byte <funcdat6>`, or :doc:`8-byte <funcdat8>` format). For example, _FUNC001.IDX is paired with _FUNC001.DAT. 

FUNC .IDX files store the retention times as well as the number of data pairs recorded at each retention time. A data pair refers to a pair of mz-intensity or wavelength-absorbance values. 

A FUNC .IDX file is comprised of contiguous 22-byte segments, one for each retention time. All known values in this file format are little-endian and unsigned. In order from start to end:

.. list-table::
   :header-rows: 1

   * - Data Type
     - Purpose 
   * - 1 int
     - Offset of data in the paired FUNC .DAT  
   * - 22 bits
     - Number of data pairs in the paired FUNC .DAT
   * - 10 bits + 4 bytes 
     - UNKNOWN 
   * - 1 float 
     - Retention time (in min)
   * - 6 bytes 
     - UNKNOWN

The entire file can be visualized by the following diagram. The segments are not drawn to scale. 

.. code-block:: text 

   +---------------------+--------------+---------+--------+---------+
   | offset in FUNC .DAT | # data pairs | UNKNOWN | time 1 | UNKNOWN |
   +---------------------+--------------+---------+--------+---------+
   | offset in FUNC .DAT | # data pairs | UNKNOWN | time 2 | UNKNOWN |
   +---------------------+--------------+---------+--------+---------+
   | offset in FUNC .DAT | # data pairs | UNKNOWN | time 3 | UNKNOWN |
   +---------------------+--------------+---------+--------+---------+
   |              continues for every retention time                 |
   +-----------------------------------------------------------------+

NOTE: FUNC .IDX files for Waters HRMS data have a different file structure. This is not documented because it is not yet understood. 