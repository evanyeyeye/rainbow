=====================
Agilent MS Data (.ms)
=====================

Agilent MS data is stored in .ms files. 

The raw data is often found in a file named data.ms. If SIM was performed, there will be a second file named dataSim.ms containing data for the user-specified masses with a smoothing function applied. The exact smoothing function is currently unknown.

.. _agilent_ms:

Agilent .ms File Structure
==========================

There are two different .ms file structures that differ in file header length, available metadata, and storage of the number of x-axis labels. On the other hand, they both have the same data body structure. 

We will differentiate them based on the plaintext string at the start of both kinds of file: GC / MS Data File and MSD Spectral File. 

Both types of .ms file are comprised of a file header and data body. 

There is also a footer in some .ms files of both types, but they are not currently understood and so are not described here. They do not appear to contain critical information related to the data. 

File header
-----------

The file headers contain file metadata and the number of x-axis labels. The lengths of the file headers are not constant and are stored at the same fixed offset for both file types (see below).  

In the MSD Spectral Files, the metadata is stored as plaintext strings that begin at fixed offsets. These strings adhere to a common pattern: a single byte specifying the length of the string, followed by the entire string. Unlike other Agilent data files, the characters are not separated by null bytes. For example, the string "hello" would be stored as such:

.. code-block:: text

    len   "h"  "e"  "l"  "l"  "o"
   +----+----+----+----+----+----+
   | 05 | 68 | 65 | 6C | 6C | 6F | 
   +----+----+----+----+----+----+

In the GC / MS Data Files, the metadata is stored in the same way as the MSD Spectral Files in the first part of the file header. 

.. list-table:: 
   :header-rows: 1
   
   * - File Offset 
     - Purpose 
     - Example String (MSD Spectral File)
     - Example String (GC / MS Data File)
   * - 0x4
     - File type
     - MSD Spectral File
     - GC / MS Data File
   * - 0x18
     - Notebook name (?)
     - 0416044-0032
     - cedrol_mix_01
   * - 0x94
     - UNKNOWN (?)
     - varab 
     - mcminns
   * - 0xB2
     - Date & time
     - 10 May 18   5:43 pm -0500
     - 14 Jan 22  01:29 pm
   * - 0xD0
     - UNKNOWN (?)
     - LCMS_3-30
     - 5977B GCM
   * - 0xE4
     - Method (?)
     - RM_HPLC.M
     - Rt-bDEX-SE_mcminn.M
   * - 0x140
     - Scan range 
     - MSD1, Initial Scan Range=170.0-1000.0
     - <NO STRING>

Note that the last offset in the table above is not used in GC / MS Data Files.

The rest of the file header for GC / MS Data Files contains null-byte separated strings that do not have a preceding byte specifying their length. Here, the string "hello" would be stored as such:

.. code-block:: text

     "h"       "e"       "l"       "l"       "o"
   +----+----+----+----+----+----+----+----+----+----+
   | 68 | 00 | 65 | 00 | 6C | 00 | 6C | 00 | 6F | 00 |
   +----+----+----+----+----+----+----+----+----+----+

The strings are separated by large blocks of null bytes, which are likely used to reserve space for longer strings. Some of these strings contain repeat metadata from the first part of the header. 

.. list-table:: 
   :header-rows: 1
   
   * - File Offset 
     - Purpose 
     - Example String 
   * - 0x1C0
     - UNKNOWN (?)
     - 5977B GCM
   * - 0x268
     - Directory 1 (?)
     - D:\\MassHunter\\Methods\\
   * - 0x466
     - Method (?)
     - Rt-bDEX-SE_mcminn.M 
   * - 0x664
     - Directory 2 (?)
     - D:\\MassHunter\\GCMS\\1\\5977\\
   * - 0x862
     - UNKNOWN (?)
     - f2_hes_atune.u

In both types of file, there are also several groups of unreadable bytes at fixed offsets in the header. These offsets are not always the same for both types. The purpose of most of these bytes are currently unknown. But there are a few known values that provide useful information about the data.  

.. list-table::
   :header-rows: 1

   * - File Offset
     - Purpose 
     - Data Type 
     - Endianness
   * - 0x10A
     - File header length (in shorts)
     - Short
     - Big
   * - 0x118
     - Number of x-axis labels (MSD Spectral File)
     - Short 
     - Big 
   * - 0x142
     - Number of x-axis labels (GC / MS Data File)
     - Short
     - Little

Note that the numerical value for the file header length counts the number of shorts, rather than bytes. 

Data body
---------

The next part of the file contains the data values. Unlike the file header, the structure of the data body is the same for both types of file. 

The file body contains a data segment for each retention time (x-axis label). Each segment begins with a 16-byte header. All known values in the headers are unsigned and big-endian. In order from start to end:

.. list-table::
   :header-rows: 1

   * - Data Type
     - Purpose 
   * - 1 int
     - X-axis time
   * - 6 bytes
     - <UNKNOWN>
   * - 1 short
     - Number of data values
   * - 4 bytes 
     - <UNKNOWN>

Next, there are two big-endian unsigned shorts for each data value. The first short represents the mass (y-axis label) and the second short represents the corresponding count. 

The value of the first short is the result of multiplying the raw mass by 20. The masses usually have a decimal component. For example, a short with the value 19796 represents the mass 989.8. This mass would be treated as 990 by some programs, including *rainbow*. Although uncommon, there may be multiple data values that correspond to a single mass. For example, there could be a data value for 989.8 as well as 990.1. Since both masses would be treated as 990, the counts for both would be summed together.

Interestingly, a data value for each mass is not necessarily recorded for each retention time. For example, one data segment may have values for masses 100, 200, and 300, while another might have values for 200 and 400. This could be troublesome with regards to parsing the file efficiently. 

The value of the second short is encoded using its bits. The most significant two bits represent a :code:`power` of eight. Note that there are four possible powers: 0, 1, 2, 3 (since there are only two bits). The remaining 14 bits represent a :code:`base` value. The count is calculated with the formula: :code:`base * 8^power`.

For example, the count 574016 = 8969 * 8^2 would be represented by the short 41737:

.. code-block:: text 

         2              8969  
       |-^-|-------------^-------------|
   MSB  1 0 1 0 0 0 1 1 0 0 0 0 1 0 0 1  LSB 
       |---------------v---------------|
                     41737

Note that this encoding scheme sacrifices precision to minimize storage space. 

As a side note, it appears that the data values may be stored in descending order by mass, but we are currently unsure of whether this is always the case. 

A data segment for a single retention time can be visualized by the following diagram. The inner segments are not drawn to scale.

.. code-block:: text 

   +--------------------------------------------------+
   |    header (retention time and # of data values)  |
   +--------+-------+--------+-------+--------+-------+
   | mass 1 | count | mass 2 | count | mass 3 | count |
   +--------+-------+--------+-------+--------+-------+
   | mass 4 | count | mass 5 | count | mass 6 | count |
   +--------+-------+--------+-------+--------+-------+
   |         repeats for the # of data values         |
   +--------------------------------------------------+
   |                     footer                       |
   +--------------------------------------------------+