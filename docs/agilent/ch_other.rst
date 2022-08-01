.. _ch_other:

Agilent .ch File Structure (other)
==================================

This file format contains UV, CAD, or ELSD channel data.

Note that this is not the same as :ref:`.ch files <ch_fid>` that contain FID data.

Files in this format are often named something like DAD1A.ch or ADC1A.ch. 

A UV .ch file contains data for a single wavelength after a user-specified bandwidth, reference wavelength, and reference bandwith has been applied (to correct for drift). The exact calculation formula is unknown. Note that this is different from the unmodified raw UV data in a :ref:`.uv file <uv>`.

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

The strings are separated by large blocks of null bytes, which are used to reserve space for longer strings. 

.. list-table:: 
   :header-rows: 1
   
   * - File Offset 
     - Purpose 
     - Example String
   * - 0x146
     - File type (number)
     - 130
   * - 0x15B
     - File type (name)
     - LC DATA FILE
   * - 0x35A
     - Notebook name
     - 0416044-0032
   * - 0x758
     - Parent directory
     - varab
   * - 0x957
     - Date
     - 10-May-18, 17:43:49
   * - 0x9BC
     - UNKNOWN
     - GCI
   * - 0x9E5
     - UNKNOWN
     - LC 
   * - 0xA0E
     - Method 
     - RM_HPLC.M
   * - 0xC11
     - Instrument 
     - Asterix ChemStation 
   * - 0xE11
     - UNKNOWN
     - B.07.01 [0005]
   * - 0xEDA
     - UNKNOWN
     - Rev. B.04.03 [16] C 
   * - 0x104C
     - Units
     - mAU
   * - 0x1075
     - Signal
     - DAD1A, Sig=215.0,16.0  Ref=off

There are also several groups of unreadable bytes at fixed offsets in the header. The purpose of most of these bytes are currently unknown. But there are a few known values that provide useful information about the data.

.. list-table::
   :header-rows: 1

   * - File Offset
     - Purpose 
     - Data Type 
     - Endianness
   * - 0x11A
     - First retention time (ms)
     - Unsigned int
     - Big 
   * - 0x11E
     - Last retention time (ms)
     - Unsigned int 
     - Big 
   * - 0x127C
     - Scaling factor
     - Double
     - Big

Data body
---------

The rest of the file contains the data values. All known values in the body are big-endian. 

The data body contains an arbitrary number of data segments. Each data segment also contains an arbitrary number of data values. We know which retention time each value corresponds to because the values are stored in ascending order with respect to time. 

Each segment begins with a 2-byte header. All values in the headers are unsigned.

.. list-table::
   :header-rows: 1

   * - Data Type
     - Purpose 
   * - 1 byte
     - Data segment label, always 16  
   * - 1 byte
     - Number of data values

Next, each data value is represented by one of two ways:

- 6 bytes: This is differentiated by the first 2 bytes being -0x8000 (signed). This denotes the following 4 bytes as a signed integer, which is the data value. 
- 2 bytes: Otherwise, the 2 bytes form a signed short. This value is a delta that is accumulated onto the most recent signed integer to get the next data value. 

For example, the 4 values 251658240, 16777216, 16777218, and 16777221 might be stored in one data segment as such: 

.. code-block:: text 

   | 16 |  4 | -0x8000 |     251658240     | -0x8000 |      16777216     |    2    |    3    |
   +----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
   | 10 | 04 | 80 | 00 | 0f | 00 | 00 | 00 | 80 | 00 | 01 | 00 | 00 | 00 | 00 | 02 | 00 | 03 |
   +----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+---------+

These values must be scaled with the factor from the file header to acquire the actual data values. 

Finally, the file ends with 2 null bytes.