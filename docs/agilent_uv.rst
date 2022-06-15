==========================
Agilent UV Data (.ch, .uv)
==========================

Agilent UV data is stored in .ch and .uv binary files. 

These binary files are often named DAD1A.ch and DAD1.uv. 

The .ch files contain data for a single wavelength after a user-specified bandwidth, reference wavelength, and reference bandwith has been applied (to correct for drift). We do not currently know the calculation formula. 

The .uv files contain raw data collected across a larger spectrum. 

.. _agilent_uv:

Agilent .ch File Structure (UV)
===============================

Note that this section pertains only to .ch files that contain UV data, which are not the same as .ch files that contain :doc:`FID data <agilent_fid>`. The file headers are very similar, however. 

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
     - 130
   * - 0x15B
     - File type (name)
     - LC DATA FILE
   * - 0x35A
     - Notebook name
     - 0416044-0032
   * - 0x758
     - Parent directory (?)
     - varab
   * - 0x957
     - Date & time
     - 10-May-18, 17:43:49
   * - 0x9BC
     - UNKNOWN (?)
     - GCI
   * - 0x9E5
     - UNKNOWN (?)
     - LC 
   * - 0xA0E
     - Method 
     - RM_HPLC.M
   * - 0xC11
     - Instrument 
     - Asterix ChemStation 
   * - 0xE11
     - UNKNOWN (?) 
     - B.07.01 [0005]
   * - 0xEDA
     - UNKNOWN (?)
     - Rev. B.04.03 [16] C 
   * - 0x104C
     - Y-axis units
     - mAU
   * - 0x1075
     - Signal
     - DAD1A, Sig=215.0,16.0  Ref=off

There are also several groups of unreadable bytes at fixed offsets in the header. The purpose of most of these bytes are currently unknown. But there are a few known values that provide useful information about the x-axis labels.

.. list-table::
   :header-rows: 1

   * - File Offset
     - Purpose 
     - Data Type 
     - Endianness
   * - 0x11A
     - First x-axis time (ms)
     - Unsigned int
     - Big 
   * - 0x11E
     - Last x-axis time (ms)
     - Unsigned int 
     - Big 

Data body
---------

The rest of the file contains the data values. All known values in the body are big-endian. 

The data body contains an arbitrary number of data segments. Each data segment also contains an arbitrary number of data values. We know which x-axis time each value corresponds to because the values are stored in ascending order with respect to time. 

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

This obscure storage pattern was most likely used to reduce storage space. 

Finally, the file ends with 2 null bytes.

Agilent .uv File Structure
==========================

The .uv files are comprised of a file header, data body, and footer. 

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
     - 131
   * - 0x15B
     - File type (name)
     - LC DATA FILE
   * - 0x35A
     - Notebook name
     - 0394783-1156_caffeine
   * - 0x758
     - Parent directory (?)
     - SYSTEM
   * - 0x957
     - Date & time
     - 30-Jan-19, 14:03:46
   * - 0x9BC
     - UNKNOWN (?)
     - DAD1
   * - 0x9E5
     - UNKNOWN (?)
     - LC 
   * - 0xA0E
     - Method 
     - FFP_UPLC_SHORT.M
   * - 0xC15
     - Y-axis units
     - mAU
   * - 0xC40
     - UNKNOWN (?)
     - DAD1I, DAD: Spectrum
   * - 0xFD7
     - Drawer & position 
     - D1B-A4

There are also several groups of unreadable bytes at fixed offsets in the header. The purpose of most of these bytes are currently unknown. But there are a few known values that provide useful information about the data.

.. list-table::
   :header-rows: 1

   * - File Offset
     - Purpose 
     - Data Type 
     - Endianness
   * - 0x104
     - Footer offset 
     - Unsigned int
     - Big 
   * - 0x116
     - Number of x-axis labels
     - Unsigned int 
     - Big 

Data body
---------

The rest of the file contains the data values. All known values in the body are little-endian. 

The data body contains a data segment for each retention time (x-axis label). Each segment begins with a 22-byte header. All known values in the headers are unsigned. In order from start to end:

.. list-table::
   :header-rows: 1

   * - Data Type
     - Purpose 
   * - 1 short
     - Data segment label, always 67 
   * - 1 short
     - Length of the segment (in bytes)
   * - 1 int 
     - X-axis time 
   * - 3 shorts 
     - Low, high, and step for wavelengths
   * - 8 bytes 
     - <UNKNOWN>

The values of the wavelength shorts are the result of multiplying the raw wavelengths by 20. For example, the shorts 3800, 8000, and 40 represent the range of 190, 400, and 2. This would describe the wavelengths 190, 192, 194, ..., 398, 400. 

The fact that each data segment header contains a wavelength range implies that the wavelengths for each retention time may not be constant throughout the file. However, we have yet to find an example where that is the case. 

Next, there is a data value for each wavelength. Each data value is represented by one of two ways:

- 6 bytes: This is differentiated by the first 2 bytes being -0x8000 (signed). This denotes the following 4 bytes as a signed integer, which is the data value. 
- 2 bytes: Otherwise, the 2 bytes form a signed short. This value is a delta that is accumulated onto the most recent signed integer to get the next data value. 

For example, the consecutive values 251658240, 16777216, 16777218, and 16777221 might be stored as such: 

.. code-block:: text 

   | -0x8000 |     251658240     | -0x8000 |      16777216     |    2    |    3    |
   +----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
   | 80 | 00 | 0f | 00 | 00 | 00 | 80 | 00 | 01 | 00 | 00 | 00 | 00 | 02 | 00 | 03 |
   +----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+

This obscure storage pattern was most likely used to reduce storage space. 

A data segment for a single retention time can be visualized by the following diagram. The inner segments are not drawn to scale. 

.. code-block:: text 

   +----+----+----------------+----------------+-----------------------------+
   | 43 | 00 | segment length | retention time | wavelength low, high, step  |
   +----+----+----------------+----------------+-----------------------------+
   |                              rest of header                             |
   +----+----+-------------+---------------+---------------+-----------------+
   | 80 | 00 | int (value) | short (delta) | short (delta) |  short (delta)  |
   +----+----+-----+-------+----+----+-----+-------+-------+-------+----+----+
   | 80 | 00 | int (value) | 80 | 00 | int (value) | short (delta) | 80 | 00 |
   +----+----+-------------+----+----+-------------+---------------+----+----+
   |                      repeats for the # of wavelengths                   |
   +-------------------------------------------------------------------------+

Footer 
------

Finally, the file ends with 4 null bytes.