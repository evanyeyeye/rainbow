.. _asm:

Allotrope Simple Model (ASM)
============================

The `Allotrope Simple Model
<https://www.allotrope.org/asm>`_ (ASM) is an open, JSON-based community
standard for analytical data, published by the Allotrope Foundation. Where
*rainbow* frees data from a vendor's binary format, ASM frees it from *rainbow*:
a document that any ASM-aware tool can read.

*rainbow* can both write ASM and read it back. The conversion is direct, because
rainbow's data model already is an ASM *data cube*: the retention-time axis, the
wavelength axis, and the intensity grid map straight onto a cube's dimensions and
measure.

Exporting
---------

Any :class:`~rainbow.datadirectory.DataDirectory` can produce an ASM
liquid-chromatography document:

.. code-block:: python

    import rainbow as rb

    datadir = rb.read("mydata.D")

    document = datadir.to_asm()          # a plain dict, ready for json.dump
    datadir.export_asm("mydata.asm.json")  # or write it straight to a file

Each single-wavelength UV channel becomes a ``chromatogram data cube`` and each
multi-wavelength DAD spectrum becomes a ``three-dimensional ultraviolet spectrum
data cube``. The spectrum is optional:

.. code-block:: python

    datadir.export_asm("mydata.asm.json", spectra=False)  # channels only

Importing
---------

The reverse conversion reconstructs rainbow objects from an ASM document:

.. code-block:: python

    import json
    import rainbow as rb

    with open("mydata.asm.json") as f:
        document = json.load(f)

    datadir = rb.from_asm(document)
    datafile = datadir.get_file("DAD1A.ch")
    datafile.xlabels  # retention times, back in minutes
    datafile.data     # the absorbances

``to_asm`` and ``from_asm`` round-trip: exporting a directory and importing the
result reproduces the same retention times, decoded values, and metadata.

What is covered
---------------

The same vendor-agnostic converter handles both Agilent ``.D`` directories and
``.dx`` archives. UV detectors are mapped today: the DAD spectrum and the
single-wavelength channels, together with the surrounding envelope drawn from the
parsed metadata (analyst, sample identifier, measurement time, and the detector
wavelength setting). Retention time is emitted in seconds (rainbow stores
minutes), wavelength in nm, and absorbance in mAU.

Conformance
-----------

The emitted documents are checked two ways, both as opt-in tests (network
dependent, skipped in continuous integration):

- against the published Allotrope liquid-chromatography **JSON schema**, which
  defines the required structure, and
- against the Allotrope Foundation **Ontology** (AFO), which defines the
  controlled vocabulary the schema leaves open. Every concept and device-type
  term *rainbow* emits is a real AFO class (for example ``retention time``
  AFR_0001089 and ``ultraviolet detector`` AFE_0000711).

See ``tests/test_asm_schema.py`` and ``tests/test_asm_ontology.py`` for how to
run them.
