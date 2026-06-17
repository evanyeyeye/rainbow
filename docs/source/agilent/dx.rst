.. _dx:

Agilent OpenLab CDS (.dx) File Structure
========================================

A :code:`.dx` file is an Agilent OpenLab CDS 2.x export. Unlike the older
:code:`.D` directory, it is a single Open Packaging Conventions (OPC) archive,
which is an ordinary zip file. Its binary payloads share their encodings with
the Chemstation formats, so **rainbow** reuses the existing decoders and only
adds a thin layer to read the archive and recover the names that the payloads
themselves do not carry.

The archive contains:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - File
     - Information
   * - injection.acmd
     - Manifest mapping each payload to its device, description, and units
   * - ``*.UV``
     - DAD spectrum (the :code:`OL` variant of the :ref:`.uv format <uv>`)
   * - ``*.CH``
     - Single-wavelength signals (the :code:`179` :ref:`.ch format <ch_fid>`)
   * - ``*.IT``
     - Instrument telemetry (same :code:`179` container as ``*.CH``)
   * - ``[Content_Types].xml``, ``_rels/``
     - OPC packaging metadata

Payload filenames are GUIDs, so the human-readable names and detector roles
come from the manifest rather than the binaries.

**injection.acmd** is an XML manifest. Each :code:`Signal` element maps a trace
GUID (:code:`TraceId`) to its :code:`DeviceName`, :code:`Description`,
:code:`Units`, and :code:`Encoding`. The leading token of the description (e.g.
:code:`DAD1A`) is used as the trace name, and the encoding distinguishes
detector signals from instrument telemetry. The :code:`InjectionInfo` element
provides the directory-level date, method, sample name, and vial position.

.. code-block:: xml

   <Signal>
       <Encoding>Agilent.OpenLab.Rawdata/Spectra131</Encoding>
       <TraceId>7aa3654a-9e49-4a53-9acb-47d9731bbe50</TraceId>
       <DeviceName>DAD</DeviceName>
       <Description>DAD1I,DAD: Spectrum</Description>
       <Units>mAU</Units>
   </Signal>

**The .UV spectrum** uses the same :code:`131` / :code:`OL` layout as the
older :ref:`.uv format <uv>` (raw little-endian doubles), but the OpenLab
values carry an additional 17-bit fixed-point shift. **rainbow** therefore
scales :obj:`parse_uv`'s output by :code:`2**-17` to recover the physical
absorbance in mAU. This was confirmed against the ``.CH`` single-wavelength
channels, which sample the same run and are already correctly scaled.

**The .CH and .IT traces** are single-channel :code:`179` files, decoded by the
existing :ref:`.ch parser <ch_fid>` with no scaling change. The ``.CH`` files
are extracted detector signals (e.g. a 210 nm chromatogram) and become
:code:`UV` DataFiles; the ``.IT`` files are instrument telemetry (pressure,
temperature, flow, solvent ratios) and become analog data.

.. note::

   Telemetry (``.IT``) is skipped by default, since most users only want the
   detector signals. Pass :code:`telemetry=True` to include it as analog data::

       import rainbow as rb
       datadir = rb.read("path/to/data.dx", telemetry=True)
       datadir.analog   # the instrument telemetry traces

   A telemetry trace named explicitly in :code:`requested_files` is always
   parsed, regardless of the flag.

The decoding of the OpenLab ``.dx`` format, and the test data used to validate
it, were contributed by an anonymous collaborator.
