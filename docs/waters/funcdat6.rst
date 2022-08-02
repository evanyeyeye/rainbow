.. _funcdat6:

Waters FUNC .DAT File Structure (6-byte)
========================================

This format stores the data pairs for UV and MS data. A data pair refers to a pair of wavelength-absorbance or mz-intensity values.

MS data can also be stored in the FUNC .DAT :doc:`2-byte <funcdat2>` and :doc:`8-byte <funcdat8>` formats.

These files are named something like _FUNC001.DAT. 

Each FUNC .DAT file is paired by number with a :doc:`FUNC .IDX <funcidx>` file. For example, _FUNC001.DAT is paired with _FUNC001.IDX. The paired FUNC .IDX file stores the retention times and the number of data pairs recorded at each time. 

This format is comprised entirely of contiguous 6-byte segments, one for each data pair. This is the reason why this format is referred to as the 6-byte format.

Each data pair is encoded into the bits of a 6-byte segment. Assume little-endianness. Starting from the most significant bit, the 48 bits are broken down as such:

.. list-table::
   :header-rows: 1

   * - Data Type
     - Purpose 
   * - 23 bits
     - Base for the wavelength or mz value (:code:`basekey`)
   * - 5 bits
     - Power for the wavelength or mz value (:code:`powerkey`)
   * - 4 bits
     - Power for the absorbance or intensity (:code:`powerval`)
   * - 1 signed short
     - Base for the absorbance or intensity (:code:`baseval`)

The wavelength or mz value is calculated with the formula :code:`basekey * 2^(powerkey - 23)`. The raw power value is adjusted by 23 because the range of powers is -23 to 8 rather than 0 to 31. 

The absorbance or intensity is calculated with the formula :code:`baseval * 4^powerval`. The base is signed to accomodate negative absorbance values. 

For example, the mz-intensity pair 141.932 = 4650831 * 2^(8-23) and 1229 = 1229 * 4^0 would be represented as such:

.. code-block:: text 

                           4650831                        8  
       |----------------------^----------------------|----^----|
   MSB  1 0 0 0 1 1 0 1 1 1 1 0 1 1 1 0 1 0 0 1 1 1 1 0 1 0 0 0 
       |--------------------------------------------------------
        
           0                 1229
       |---^---|---------------^---------------|
        0 0 0 0 0 0 0 0 0 1 0 0 1 1 0 0 1 1 0 1  LSB 
       ----------------------------------------|

If calibration is available for mz values, the calibration numbers will be stored in the plaintext header.txt file. For example: 

.. code-block:: text 

   $$ Cal Function 1: -2.393264994225831e-1,1.000527680028696e0,-5.302357490118866e-7,2.335328783599209e-10,-4.220307033458315e-14,T0

Let :code:`x` be the mz value and :code:`c_1`, :code:`c_2`, :code:`...`, :code:`c_n` be the calibration numbers. The calibration formula is :code:`c_1 * x^0 + c_2 * x^1 + ... + c_n * x^(n-1)`. 

We compute an example using the mz value and 5 calibration numbers from above. The calibrated mz value is 141.7576 = -2.393e-1 + 1.000 * 141.932 + -5.302e-7 * 141.932^2 + 2.335e-10 * 141.932^3 + -4.220e-14 * 141.932^4. Note that the calibration numbers are truncated to 3 decimal places for readability, but the computation uses the full precision. 