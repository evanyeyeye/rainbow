.. _funcdat2:

Waters FUNC .DAT File Structure (2-byte)
========================================

This format stores the intensity values for some MS data. MS data can also be stored in the FUNC .DAT :ref:`6-byte <funcdat6>` and ref:`8-byte <funcdat8>` formats.

These files are named something like _FUNC001.DAT. 

Each FUNC .DAT file is paired by number with a :ref:`FUNC .IDX <funcidx>` file. For example, _FUNC001.DAT is paired with _FUNC001.IDX. The paired FUNC .IDX file stores the retention times. 

The file is comprised entirely of contiguous 2-byte segments, one for each intensity. This is the reason why this format is referred to as the 2-byte format.

The value of each intensity is encoded into the bits of each 2-byte segment. Assume little-endianness. The least significant 3 bits represent a :code:`power` of four. The most significant 13 bits represent a :code:`base` value. The intensity is calculated with the formula: :code:`base * 4^power`.

For example, the intensity 13924 = 3481 * 4^1 would be represented by the following 2 bytes:

.. code-block:: text 

                   3481             1
       |------------^------------|--^--|
   MSB  0 1 1 0 1 1 0 0 1 1 0 0 1 0 0 1  LSB 
       |-------------------------------|   

Note that this encoding scheme sacrifices precision for storage space.

But where are the mz values? For this format, they are stored in a contiguous segment in a different file named _FUNCTNS.INF. We describe that file format below. 

Waters _FUNCTNS.INF File Structure 
----------------------------------

This format stores the mz values for 2-byte FUNC .DAT files.

There is a 416 byte segment allocated in this file for each FUNC .IDX/.DAT pair. The purpose of most of these bytes is unknown. Each segment seems to be broken down as follows:

.. list-table::
   :header-rows: 1

   * - Segment Length
     - Purpose 
   * - 32 bytes
     - UNKNOWN
   * - 128 bytes
     - UNKNOWN
   * - 32 little-endian floats
     - mz values
   * - 128 bytes
     - UNKNOWN

This means that there are at most 32 unique mz values recorded for MS data in the 2-byte FUNC .DAT format. Accordingly, we only found instances of this format for SIM data. 

It is assumed that intensities were recorded for all mz values at each retention time.

Note that the layout of the unknown bytes means that they could contain mz values for an undiscovered format. 