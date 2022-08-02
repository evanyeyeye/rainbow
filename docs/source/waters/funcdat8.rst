.. _funcdat8:

Waters FUNC .DAT File Structure (8-byte)
========================================

This format stores the mz-intensity pairs for MS data. 

MS data can also be stored in the FUNC .DAT :doc:`2-byte <funcdat2>` and :doc:`6-byte <funcdat6>` formats.

These files are named something like _FUNC001.DAT. 

Each FUNC .DAT file is paired by number with a :doc:`FUNC .IDX <funcidx>` file. For example, _FUNC001.DAT is paired with _FUNC001.IDX. The paired FUNC .IDX file stores the retention times and the number of mz-intensity pairs recorded at each time. 

This format is comprised entirely of contiguous 8-byte segments, one for each mz-intensity pair. This is the reason why this format is referred to as the 8-byte format.

Each mz-intensity pair is encoded into the bits of a 8-byte segment. Assume little-endianness. Starting from the most significant bit, the 64 bits are broken down as such:

.. list-table::
   :header-rows: 1

   * - Data Type
     - Purpose 
   * - 5 bits
     - Number of bits used for the mz value integer (call this :code:`x`)
   * - :code:`x` bits 
     - Integer part of the mz value 
   * - 31 - :code:`x` bits
     - Fractional part of the mz value
   * - 6 bits
     - Number of bits used for the intensity integer (call this :code:`y`)
   * - 1 bit 
     - UNKNOWN
   * - :code:`max(y, 21)` bits  
     - Integer part of the intensity
   * - 21 - :code:`max(y, 21)` bits
     - Fractional part of the intensity

This is a lot to take in. There are 36 bits encoding the mz value and 28 bits encoding the intensity, but the number of bits encoding the integer and fractional parts of both values is variable. The fractional part of a value refers to the numbers right of the decimal point. 

The encoding of the intensity is particularly interesting. You may have noticed that 6 bits has a maximum value of 63, which is far greater than the 21 bits allocated for the intensity. If :code:`y` is greater than 21, the 21 bits are treated as the most significant bits of a number that is :code:`y` bits long. This allows much larger intensities to be stored than 28 bits would normally allow. 

How are the fractional parts encoded? The most significant bit represents 2^(-1), and the power decreases for each successive bit. For example, 0101 (in base 2) would encode 0.3125 = 2^(-2) + 2^(-4). **rainbow** exploits the similarities between this encoding scheme and the `standard double-precision floating point format <https://en.wikipedia.org/wiki/Double-precision_floating-point_format>`_ to skip the costly computation of decoding the fractions. 

The mz and intensity are acquired by summing the integer and fractional parts of both values. Note that there may be precision loss due to the nature of floating point arithmetic. **rainbow** reports values with a maximum error of .0002. 

As an example, consider the mz-intensity pair 163.367 and 142528.375. It would be represented by the following 8 bytes:

.. code-block:: text 

            8           163                           0.367
       |----^----|-------^-------|----------------------^----------------------|
   MSB  0 1 0 0 0 1 0 1 0 0 0 1 1 0 1 0 1 1 1 0 1 1 1 1 1 1 1 1 1 0 0 0 0 0 0 0 
       |------------------------------------------------------------------------

            18                      142528                0.375
       |-----^-----|-|-----------------^-----------------|--^--|
        0 1 0 0 1 0 0 1 0 0 0 1 0 1 1 0 0 1 1 0 0 0 0 0 0 0 1 1  LSB
       --------------------------------------------------------|

If calibration is available for mz values, the calibration numbers will be stored in the plaintext header.txt file. For example: 

.. code-block:: text 

   $$ Cal Function 1: -3.924445963614183e-1,1.000252977448459e0,-2.429571643077414e-7,1.123763027703513e-10,-1.751552988608531e-14,T0

Let :code:`x` be the mz value and :code:`c_1`, :code:`c_2`, :code:`...`, :code:`c_n` be the calibration numbers. The calibration formula is :code:`c_1 * x^0 + c_2 * x^1 + ... + c_n * x^(n-1)`. 

We compute an example using the mz value and 5 calibration numbers from above. The calibrated mz value is 163.0100 = -3.924e-1 + 1.000 * 163.367 + -2.429e-7 * 163.367^2 + 1.123e-10 * 163.367^3 + -1.751e-14 * 163.367^4. Note that the calibration numbers are truncated to 3 decimal places for readability, but the computation uses the full precision. 