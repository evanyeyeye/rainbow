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
   * - MSTS.xml
     - Number of retention times
   * - MSScan.xsd
     - File structure of MSScan.bin
   * - MSScan.bin 
     - Offsets and compression info for MSProfile.bin
   * - MSMassCal.bin
     - Calibration info for masses
   * - MSProfile.bin 
     - Mz and intensity values 

**MSTS.xml** is an XML document that contains several :code:`NumOfScans` elements, whose values summed together give the total number of retention times. This is useful for parsing subsequent files. 

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

**MSScan.bin** is a binary that contains a data segment in the format defined by :code:`ScanRecordType` for each retention time. These data segments begin at offset 0x58. 

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

**MSProfile.bin** is a binary that has been compressed using the `LZF algorithm <http://home.schmorp.de/marc/liblzf.html>`_. The length of the decompressed data is required for LZF decompression. 

This file format is comprised of a data segment for each retention time. Assume little-endianness. 

Each data segment begins with 2 doubles that hold the smallest mz value and the mz delta value, before calibration. The resulting mz range may be unusable without calibration because the values can be very large. 

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