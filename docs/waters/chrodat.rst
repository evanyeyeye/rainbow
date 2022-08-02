.. _chrodat:

Waters CHRO .DAT File Structure
===============================

This format stores UV, CAD, and ELSD channel data. It also stores miscellaneous data like system pressure that MassLynx classifies as analog.

These files are named something like _CHRO001.DAT. 

The file begins with a short 0x80 byte header that contains string labels for the data axes. These are frequently Time and Intensity. 

The rest of the file contains the data values. This is structured as contiguous pairs of little-endian floats, one corresponding to each axis. 

The entire file can be visualized by the following diagram. The segments are not drawn to scale. 

.. code-block:: text 

   +---------------------------------+
   |           file header           |
   +--------+-------+--------+-------+
   | time 1 | value | time 2 | value |
   +--------+-------+--------+-------+
   | time 2 | value | time 3 | value |
   +--------+-------+--------+-------+
   | time 4 | value | time 5 | value |
   +--------+-------+--------+-------+
   |     continues for all scans     |
   +---------------------------------+

A description for each CHRO .DAT file is stored as plaintext in the _CHROMS.INF binary file. In newer versions it also includes the units for the data. 