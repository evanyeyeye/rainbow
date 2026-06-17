.. _hrms:

Agilent MSProfile.bin File Structure
====================================

This file format contains Agilent HRMS data. 

The HRMS data is encoded across several files in a subdirectory named AcqData:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - File
     - Information
   * - MSScan.xsd
     - File structure of MSScan.bin
   * - MSScan.bin
     - Offsets, compression info, and the number of retention times
   * - MSMassCal.bin
     - Calibration info for masses
   * - MSProfile.bin
     - Mz and intensity values

The number of retention times is obtained from **MSScan.bin** itself by reading its scan records until the end of the file (see below). Some acquisitions also include an **MSTS.xml** document whose :code:`NumOfScans` elements sum to the same total, but **rainbow** does not require it. This matters because OpenLab :code:`.rslt`/:code:`.sirslt` result folders omit MSTS.xml.

.. code-block:: xml

   <TimeSegment TimeSegmentID="2">
       <StartTime>1.04351666666667</StartTime>
       <EndTime>7.99746666666667</EndTime>
       <NumOfScans>2095</NumOfScans>
       <FixedCycleLength>0</FixedCycleLength>
   </TimeSegment>

**MSScan.xsd** is an XML document that defines the structure of the MSScan.bin binary using elements that are assigned simple and complex types. 

A simple type translates directly into a little-endian number type. For example:

.. code-block:: xml 

   <xs:element name="TIC" type="xs:double"/>

A complex type is comprised of simple types and other complex types. The following example shows a heavily simplified version of a complex type that contains another complex type.

.. code-block:: xml 

   <xs:complexType name="ScanRecordType">
       <xs:sequence>
           <xs:element name="ScanTime" type="xs:double"/>
           <xs:element name="SpectrumParamValues" type="SpectrumParamsType"/>
       </xs:sequence>
   </xs:complexType>
   <xs:complexType name="SpectrumParamsType">
       <xs:sequence>
           <xs:element name="SpectrumOffset" type="xs:long"/>
           <xs:element name="ByteCount" type="xs:int"/>
           <xs:element name="PointCount" type="xs:int"/>
           <xs:element name="UncompressedByteCount" type="xs:int"/>
       </xs:sequence>
   </xs:complexType>

The root type is the complex type :code:`ScanRecordType`. 

**MSScan.bin** is a binary that contains a data segment in the format defined by :code:`ScanRecordType` for each retention time. A little-endian 4-byte offset at 0x58 points to the first data segment. The segments are contiguous and the file ends exactly on a segment boundary, so reading them until EOF gives the total number of retention times.

The simplified example above would correspond to the following data segment structure:

.. list-table::
   :widths: 75 25
   :header-rows: 1

   * - Purpose 
     - Data Type 
   * - Retention time
     - Double
   * - Offset of data in MSProfile.bin
     - Unsigned long
   * - Length of compressed data segment
     - Unsigned int 
   * - Number of mz-intensity pairs
     - Unsigned int
   * - Length of decompressed data segment
     - Unsigned int

Although it is a simplified example, the table above contains the key information about a MSProfile.bin binary that is stored in MSScan.bin.

**MSMassCal.bin** is a binary that contains a data segment of 10 little-endian doubles for each retention time. The first 2 doubles are used as calibration numbers for the mz values recorded at the corresponding retention time. The purpose of the other 8 doubles is currently unknown. The data segments begin at offset 0x4c. 

**MSProfile.bin** stores a data segment for each retention time. Assume little-endianness.

Each data segment begins with 2 doubles that hold the smallest mz value and the mz delta value, before calibration. The resulting mz range may be unusable without calibration because the values can be very large.

The intensities that follow the 2-double header are stored in one of two ways, depending on the instrument:

- **LZF compression.** The whole segment, header included, is compressed with the `LZF algorithm <http://home.schmorp.de/marc/liblzf.html>`_. The decompressed length (``UncompressedByteCount`` in MSScan.bin) is required for decompression. This path needs the optional ``python-lzf`` dependency.
- **Run-length encoding (RLE).** Q-TOF profile acquisitions leave the 2-double header raw and follow it with an RLE intensity stream. The stream starts with a 4-byte word whose low 3 bytes are the point count and whose high byte is a fixed ``0x90`` marker; **rainbow** uses this signature to recognize the format. Two little-endian ``int32`` values follow (both stored negated): an initial run of zero intensities, and a width flag (1, 2, 3, or 4, mapping to a 1-, 2-, 4-, or 8-byte signed integer) for the values that come next. Each subsequent value is read at the current width: a non-negative value is a literal intensity, while a negative value ``-v`` encodes ``divmod(v, 4)`` — the quotient is a run of zero intensities and the remainder is the new width flag to switch to. Trailing zero intensities are not stored. This path does not require ``python-lzf``.

Let the corresponding 2 calibration numbers from MSMassCal.bin be :code:`coeff` and :code:`base`. The calibration formula for each :code:`mz` is :code:`(coeff * (mz - base))^2`. 

The rest of the data segment consists of the intensities as unsigned integers. Recall that the number of intensities is stored in MSScan.bin. 

The entirety of the file can be visualized by the following diagram. The inner segments are not drawn to scale.

.. code-block:: text 

   +-------------+----------+-----------+-----------+-----------+-----------+-----------+
   | smallest mz | mz delta | intensity | intensity | intensity | intensity | intensity |
   +-------------+----------+-----------+-----------+-----------+-----------+-----------+
   | smallest mz | mz delta | intensity | intensity | intensity | intensity | intensity |
   +-------------+----------+-----------+-----------+-----------+-----------+-----------+
   | smallest mz | mz delta | intensity | intensity | intensity | intensity | intensity |
   +-------------+----------+-----------+-----------+-----------+-----------+-----------+
   |                          repeats for every retention time                          |
   +------------------------------------------------------------------------------------+