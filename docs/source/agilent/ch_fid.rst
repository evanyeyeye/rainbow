.. _ch_fid:

Agilent .ch File Structure (179/181)
====================================

This file format usually contains FID channel data, and is named something like
FID1A.ch.

The version at the head of the file says how the data is encoded, not what
measured it. Chemstation also writes single-wavelength diode-array channels
into this container, named something like DAD1A.ch, and rainbow reads the
detector from the channel's own signal string: a ``Sig=`` clause makes it an
ultraviolet channel at that wavelength, and anything else is taken as FID. The
181 layout has no signal offset, so a 181 file is always read as FID.

Note that this is not the same as the :ref:`130/30 container <ch_other>`, which
also holds UV, CAD, and ELSD data in a different layout.

These files are comprised of a file header and data body. 

File header
-----------

The file header contains metadata and information about the data. The header is 0x1800 bytes long.

The metadata is stored as plaintext strings that begin at fixed offsets. These strings adhere to a common pattern: a single byte specifying the length of the string, followed by the characters in the string separated by single null bytes. For example, the string "hello" would be stored as such:

.. code-block:: text

    len   "h"       "e"       "l"       "l"       "o"
   +----+----+----+----+----+----+----+----+----+----+----+
   | 05 | 68 | 00 | 65 | 00 | 6C | 00 | 6C | 00 | 6F | 00 |
   +----+----+----+----+----+----+----+----+----+----+----+

The strings are separated by large blocks of null bytes, which are likely used to reserve space for longer strings. 

.. list-table:: 
   :header-rows: 1
   
   * - File Offset 
     - Purpose 
     - Example String
   * - 0x146
     - File type (number)
     - 179
   * - 0x15B
     - File type (name)
     - GC DATA FILE
   * - 0x35A
     - Notebook name
     - example_mix01
   * - 0x758
     - Parent directory
     - jdoe
   * - 0x957
     - Date
     - 17 Dec 19  10:04 am
   * - 0x9BC
     - UNKNOWN
     - 7890
   * - 0x9E5
     - UNKNOWN
     - GC 
   * - 0xA0E
     - Method 
     - Rt-bDEX-SE_jdoe.M
   * - 0xC11
     - Instrument 
     - FAKEPC2 ChemStation 
   * - 0x104C
     - Units
     - pA 
   * - 0x1075
     - Signal
     - Front Signal

There are also several groups of unreadable bytes at fixed offsets in the header. The purpose of most of these bytes are currently unknown. But there are a few known values that provide useful information about the data.

.. list-table::
   :header-rows: 1

   * - File Offset
     - Purpose 
     - Data Type 
     - Endianness
   * - 0x116
     - Number of data values 
     - Unsigned int 
     - Big
   * - 0x11A
     - First retention time (ms)
     - Float 
     - Big 
   * - 0x11E
     - Last retention time (ms)
     - Float 
     - Big 
   * - 0x127C
     - Scaling factor
     - Double
     - Big

Data body
---------

The rest of the file contains the data values. The structure of the data body is relatively straightforward: little-endian doubles that each represent a single data value. These doubles are in ascending order with respect to time, so the first double corresponds to the first retention time. 

These values must be scaled with the factor from the file header to acquire the actual data values. 

The entire file can be visualized by the following diagram, where each double represents a data value. The segments are not drawn to scale. 

.. code-block:: text 

   +-----------------------------------+
   |            file header            |
   +--------+--------+--------+--------+
   | double | double | double | double |
   +--------+--------+--------+--------+
   | double | double | double | double |
   +--------+--------+--------+--------+
   | double | double | double | double |
   +--------+--------+--------+--------+
   |     repeats for all data values   |
   +-----------------------------------+