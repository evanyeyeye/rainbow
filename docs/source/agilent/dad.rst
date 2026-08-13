.. _dad:

Agilent MassHunter DAD File Structure
=====================================

This file format contains diode-array detector data acquired under MassHunter
rather than Chemstation. It holds the same two views of a run that Chemstation
splits into :ref:`.ch <ch_other>` and :ref:`.uv <uv>` files, one chromatogram
per signal and the spectra, in an unrelated binary layout.

The files sit in the AcqData subdirectory and are named after the detector that
wrote them. They come in descriptor/data pairs.

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - File
     - Type tag
     - Information
   * - ``DAD1.cd``
     - 0x0200
     - Describes the signals stored in ``DAD1.cg``
   * - ``DAD1.cg``
     - 0x0201
     - One chromatogram per signal
   * - ``DAD1.sd``
     - 0x0202
     - Describes the spectra stored in ``DAD1.sp``
   * - ``DAD1.sp``
     - 0x0203
     - The spectra

A type tag names the kind of file, not the detector that wrote it. Pumps,
autosamplers and column compartments write ``.cd``/``.cg`` pairs under the same
two tags, so **rainbow** finds the absorbance data by device name rather than
by tag. Only the ``.sd``/``.sp`` spectra are unique to a detector.

Each descriptor gives the byte offset of every record in its data file, along
with the record's length in bytes (``.sd``) or in points (``.cd``). Records are
therefore located rather than assumed to be evenly spaced. Assume
little-endianness. Absorbances are plain doubles: unlike the Chemstation
formats there is no delta encoding and no scaling factor.

All four files open with the same 68-byte header, whose only populated field is
a 16-bit type tag at offset 0x00 identifying which file it is.

**DAD1.cd** stores the number of signals at 0x4C and its first signal record at
0x50. A record interleaves length-prefixed strings with fixed-width fields, so
records vary in width and are read in sequence. The strings are UTF-8, since a
detector reports temperatures in degrees Celsius.

.. list-table::
   :widths: 40 60
   :header-rows: 1

   * - Field (in order)
     - Example
   * - Signal letter (length-prefixed)
     - A
   * - Description (length-prefixed)
     - :code:`Sig=254.0,4.0  Ref=360.0,100.0`
   * - Kind: 1 for absorbance, 2 for telemetry
     - 1
   * - Byte offset of this signal's data in ``DAD1.cg``
     - 68
   * - Always zero, perhaps the high half of that offset
     - 0
   * - Number of points
     - 3525
   * - Unit (length-prefixed), after further fields not decoded here
     - mAU

A description names the band the signal integrates and the band subtracted from
it: 254 nm over a 4 nm bandwidth, referenced to 360 nm over 100 nm. A
chromatogram is therefore **not** a slice of the spectra; it is a band average,
less a reference. A detector also records telemetry here (lamp voltage, board
and optical unit temperature), sampled four times as often as its absorbance
signals and carrying its own units. **rainbow** separates the two by unit and
description rather than by the kind field, which the other devices do not use
as consistently.

**DAD1.sd** stores the byte offset of its first spectrum record at 0x4C, the
number of spectra at 0x50, and the wavelength range at 0x54 and 0x5C. Its
records are a fixed 80 bytes.

.. list-table::
   :widths: 25 45 30
   :header-rows: 1

   * - Record Offset
     - Purpose
     - Example
   * - 0x04
     - Retention time in minutes (double)
     - 0.0029167
   * - 0x20
     - Byte offset of this spectrum in ``DAD1.sp``
     - 68
   * - 0x28
     - Its length in bytes
     - 1464
   * - 0x2C
     - Number of wavelengths
     - 181
   * - 0x30
     - First wavelength (double)
     - 190.0
   * - 0x38
     - Last wavelength (double)
     - 550.0

The remaining fields hold the same values in every run available here, so their
meaning could not be determined and **rainbow** does not read them.

**DAD1.cg** and **DAD1.sp** store each record as an axis prefix followed by its
values, at the offset the descriptor gives.

.. code-block:: text

   .cg, per signal:
   +------------------+------------------+--------------------------+
   | first time (dbl) | time step  (dbl) | num_points x double      |
   +------------------+------------------+--------------------------+

   .sp, per spectrum:
   +------------------+------------------+--------------------------+
   | first wavelength | wavelength step  | num_wavelengths x double |
   +------------------+------------------+--------------------------+

.. note::

   Because the wavelength axis is repeated per spectrum, an acquisition may in
   principle vary it during a run. Such spectra do not share a grid and cannot
   form a dense two-dimensional array, so **rainbow** checks every spectrum's
   axis and declines them with a warning rather than reshaping mismatched rows.
   The axis is also stated as a range in the ``.sd``, and the two statements are
   checked against each other.

   DAD parsing needs no flag, as the Chemstation UV formats need none. The
   detector's telemetry traces are returned as analog data only under
   :code:`telemetry=True`, or when named in :code:`requested_files`.
