.. _uv:

Agilent .uv File Structure
==========================

This file format contains UV spectra data.

Files in this format are named something like DAD1.uv. 

The absorbances are stored in these files are unmodified, unlike in :ref:`.ch files <ch_other>`.

These files are comprised of a file header, data body, and footer. 

File header
-----------

The file header contains file metadata and information about the data. The header is 0x1000 bytes long.

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
     - 131
   * - 0x15B
     - File type (name)
     - LC DATA FILE
   * - 0x35A
     - Notebook name
     - 0394783-1156_caffeine
   * - 0x758
     - Parent directory 
     - SYSTEM
   * - 0x957
     - Date 
     - 30-Jan-19, 14:03:46
   * - 0x9BC
     - UNKNOWN 
     - DAD1
   * - 0x9E5
     - UNKNOWN 
     - LC 
   * - 0xA0E
     - Method 
     - FFP_UPLC_SHORT.M
   * - 0xC15
     - Units
     - mAU
   * - 0xC40
     - UNKNOWN
     - DAD1I, DAD: Spectrum
   * - 0xFD7
     - Vial position 
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
   * - 0x127C
     - Scaling factor
     - Double
     - Big

Data body
---------

The rest of the file contains the data values. All known values in the body are little-endian. 

The data body contains a data segment for each retention time. Each segment begins with a 22-byte header. All known values in the headers are unsigned. In order from start to end:

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
     - UNKNOWN

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

This storage pattern was most likely used to reduce storage space. 

These values must be scaled with the factor from the file header to acquire the actual data values. 

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

Finally, the file ends with 4 null bytes.