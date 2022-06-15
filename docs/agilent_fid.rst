======================
Agilent FID Data (.ch)
======================

Agilent FID data is stored in .ch files. 

The binary file is often named FID1A.ch. 

.. _agilent_fid:

Agilent .ch File Structure (FID)
================================

Note that this section pertains only to .ch files that contain FID data, which are not the same as .ch files that contain :doc:`UV data <agilent_uv>`. 

The .ch files are comprised of a file header and data body. 

File header
-----------

The file header contains file metadata and information about x-axis labels. The header is 0x1800 bytes long.

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
     - cedrol_mix_01
   * - 0x758
     - Parent directory (?)
     - mcminns
   * - 0x957
     - Date & time
     - 17 Dec 19  10:04 am
   * - 0x9BC
     - UNKNOWN (?)
     - 7890
   * - 0x9E5
     - UNKNOWN (?)
     - GC 
   * - 0xA0E
     - Method 
     - Rt-bDEX-SE_mcminn.M
   * - 0xC11
     - Instrument 
     - Mustang ChemStation 
   * - 0x104C
     - Y-axis units
     - pA 
   * - 0x1075
     - Signal
     - Front Signal

There are also several groups of unreadable bytes at fixed offsets in the header. The purpose of most of these bytes are currently unknown. But there are a few known values that provide useful information.

.. list-table::
   :header-rows: 1

   * - File Offset
     - Purpose 
     - Data Type 
     - Endianness
     - Example Value
   * - 0x116
     - Number of data values 
     - Unsigned int 
     - Big
     - 54285
   * - 0x11A
     - First x-axis time (ms)
     - Float 
     - Big 
     - 49.562
   * - 0x11E
     - Last x-axis time (ms)
     - Float 
     - Big 
     - 2714249.5

Data body
---------

The rest of the file contains the data values. The structure of the data body is relatively straightforward: little-endian doubles that each represent a single data value. These doubles are in ascending order with respect to time, so the first double corresponds to the first x-axis time. 

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