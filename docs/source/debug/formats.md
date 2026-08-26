# Debug metadata: format catalog

Index of the vendor metadata formats the debug subsystem decodes. Each format
has a **deep structural reference** under `formats/` documenting everything
reverse-engineered about it (layout, encoding, sub-value formats, field
semantics, open questions). This page is the at-a-glance status and the
canonical-field summary; the per-format files are the real documentation.

Add a `formats/<name>.md` reference when you add a parser, and document
everything you learn about the format there as you learn it. Follow the same
section skeleton the existing references use, so the set stays usable as a
template (`dotnet.md` and `reg.md` are the cleanest models):

1. **Format** - the on-disk layout, encoding, magic/version markers.
2. **Matching** - which file names/extensions this parser claims.
3. **What `parse` returns** - the lossless dict shape, with an example.
4. **Depth decision** - what you surface vs skip, and *why* (the cost of going
   deeper). This is where the "extract per-instance identifiers, skip invariant
   format internals" principle gets applied to this format.
5. **Canonical mapping** - the source-key -> canonical-field table.
6. **Open questions / future depth** - where the next contributor picks up.

Legend: **Depth** = full / partial / best-effort. **Status** = done / in
progress / planned.

## Status

| format | reference | parser | depth | status |
|---|---|---|---|---|
| Agilent INI | [`formats/ini.md`](formats/ini.md) | `rainbow/debug/ini.py` | full / lossless | done |
| Agilent/Waters XML | [`formats/xml.md`](formats/xml.md) | `rainbow/debug/xml.py` | full structure; canonical for SampleInfo/Devices/Sample/AuditTrail/ACAML/SampleContainerInfo/`.tune` (Limsinf inspect-only) | done (canonical growing) |
| ChemStation report/text | [`formats/chemstation_text.md`](formats/chemstation_text.md) | `rainbow/debug/chemstation_text.py` | header/identity canonical; instrument-parameter bodies lossless but not mined (numeric); `Audit.txt` trail inspect-only, `method.txt` -> method, `MSPARMS.txt`/`report.txt`/`report*.csv` -> operator/sample/data_file/instrument/..., `acq_methhist.txt` -> method, `scstate.txt` -> instrument serial | done |
| Extended `.ch/.uv/.ms` headers | [`formats/chemstation_header.md`](formats/chemstation_header.md) | `rainbow/debug/chemstation_header.py` | header text only (no data); adds operator + workstation rainbow drops | done |
| Methods / macros (`.mth/.e/.p/.val/.mac`) | [`formats/method.md`](formats/method.md) | `rainbow/debug/method.py` | classify + extract path/data-file refs only; invariant template bodies not surfaced | done |
| `.NET` `QualResult.bin` (MS-NRBF) | [`formats/dotnet.md`](formats/dotnet.md) | `rainbow/debug/dotnet.py` | string-table summary (assemblies + paths), not full graph - internals are invariant boilerplate | done |
| `.REG` registers (MFC CArchive) | [`formats/reg.md`](formats/reg.md) | `rainbow/debug/reg.py` | best-effort: format + record-type inventory only (proprietary CHP* payloads, no identifiers) | done |
| Waters `_HEADER.TXT` | [`formats/waters_header.md`](formats/waters_header.md) | `rainbow/debug/waters_header.py` | full / lossless `$$ Key: Value`; canonical identity for the whole `.raw` run | done |
| Waters `_INLET.INF` / `inlet.inf` / `_extern.inf` | [`formats/waters_inf.md`](formats/waters_inf.md) | `rainbow/debug/waters_inf.py` | method/inlet file path or GC method name (project identity); parameter body lossless but not mined | done |
| mzXML (open format) | [`formats/mzxml.md`](formats/mzxml.md) | `rainbow/debug/mzxml.py` | header only (streams, stops at first `<scan>`); instrument + software + source-file provenance | done |

### Container archives (not a parser)

An Agilent OpenLab `.dx` is an OPC (zip) package, not a flat sidecar. The walker
in `rainbow/debug/__init__.py` (`_ARCHIVE_EXTS`/`_iter_archive`) transparently
**descends** into a `.dx` - whether passed directly or found inside a scanned
directory - and runs the existing parsers over its members, reporting member
relpaths as `<archive>!<member>`. The identity comes out via the parsers already
listed: the GUID-named `.CH`/`.UV` signal payloads carry full ChemStation headers
(operator, full method path, signal optics), decoded by `chemstation_header`.

This is split cleanly from `rb.read` to avoid duplication: `rb.read` decodes the
`.dx` signal **data** and reads `injection.acmd` (the manifest) for its lean
metadata, so debug leaves the manifest alone and only mines the per-signal
**headers** `rb.read` drops. The numeric `.IT` traces and the manifest dispatch
to no parser; the OPC packaging parts (`[Content_Types].xml` and the `_rels`
relationship files) are skipped explicitly. None are extracted.

## Canonical field vocabulary

The shared field names `canonical()`/`fields()` produce. Grows as formats land.
The last column names a **primary** source for orientation, not the exhaustive
list - several fields are emitted by more than one parser (e.g. `operator` and
`acquired` also come from ACAML and the ChemStation text/header parsers; on
Waters the whole identity set comes from `_HEADER.TXT`). The per-format
references list every emitter.

| field | type | meaning | primary source |
|---|---|---|---|
| `serials` | list | instrument / module serial numbers | INI (`gc.sn`, `SmartCard`), XML (Devices) |
| `instrument` | scalar | instrument model | INI (`SmartCard`) |
| `devices` | list | per-module record (name/model/serial/firmware/driver) | XML (Devices) |
| `operator` | scalar | acquisition / method-save user | INI (`MethSaveWHO`), XML (SampleInfo) |
| `software_version` | scalar | acquisition software build | INI (`AcqVersion`/`Application`) |
| `method_save_time` | scalar | method last-saved time | INI (`MethSaveTime`) |
| `acquired` | scalar | acquisition timestamp | INI (`Date`), XML (SampleInfo) |
| `injection_volume` | scalar | injection volume | INI (`InjVolume`), XML (SampleInfo) |
| `signal_optics` | list | detector signal/optics descriptor(s) | INI (`UVASig`) |
| `sample` | scalar | sample name | XML (SampleInfo) |
| `sample_id` | scalar | sample ID | XML (SampleInfo) |
| `vialpos` | scalar | sample / vial position | XML (SampleInfo) |
| `method` | scalar | method path | XML (SampleInfo, Sample) |
| `data_file` | scalar | data file path | XML (SampleInfo, Sample) |
| `computers` | list | acquisition workstation host name(s) | XML (AuditTrail) |
| `users` | list | audit-trail user(s) | XML (AuditTrail) |

## Where each format's fields live

The formats were drawn from a parse-coverage audit: rainbow's data parsers leave
the metadata sidecars untouched, concentrated in `yellow.D` (58/66 files),
`orange.D` (35/38), and `red.D` (16/21). A later scan over the full data corpus
added the Waters `.INF`, mzXML, `.drvml`, and `.dx`-descent coverage. This is the
provenance map of which file carries what.

- **Unparsed XML** (canonical for SampleInfo/Devices/Sample/AuditTrail/ACAML/
  SampleContainerInfo/`.tune`; Limsinf still inspect-only) - `sample_info.xml`,
  `Devices.xml`, audit trails, ACAML (`.acaml`/`.macaml`/`.acam_`), `.scml`,
  `.drvml`, `.tune` (MS tune, instrument serial), `limsinf.xml`. Operator/sample/
  method/instrument/serials/timestamps.
- **ChemStation report/text** - `runstart.txt`, `tic_front.csv/tsv`,
  `acqmeth.txt`, `acq.txt`, `rtlrep.txt`, `RUN.LOG`, `Audit.txt`, `method.txt`,
  `MSPARMS.txt`, `report.txt`, `report*.csv`, `acq_methhist.txt`, `scstate.txt`,
  `rpthead.txt`. See
  [`formats/chemstation_text.md`](formats/chemstation_text.md). Notably RUN.LOG
  is the only serial source for ChemStation LC `.D` runs (no Devices.xml there);
  the `report.txt`/`report*.csv` pair is the ChemStation acquisition report (rich
  operator/sample/method identity), and `scstate.txt`/`.tune` carry the MS
  instrument serial.
- **Extended detector headers** - the `.ch/.uv/.ms` header fields rainbow
  drops, chiefly **operator** and the acquisition **workstation** name. See
  [`formats/chemstation_header.md`](formats/chemstation_header.md).
- **Methods / macros** - `*.mth`, `*.e`, `*.p`, `*.val`, `*.mac`.
  Classify + extract path/data-file refs only (one `LastDataFile` macro carries a
  data path); invariant template bodies not surfaced. See
  [`formats/method.md`](formats/method.md).
- **`.NET` BinaryFormatter** - `QualResult.bin` (MS-NRBF, the .NET Remoting
  Binary Format the BinaryFormatter serializer emits). String-table
  summary: assembly/software stack + path values, not the full graph (the graph
  internals are invariant boilerplate). See
  [`formats/dotnet.md`](formats/dotnet.md).
- **`.REG` registers** - `ACQRES`, `DAMETHOD`, `lcdiag`, ... MFC CArchive;
  proprietary `CHP*` layouts never published and payloads are numeric with no
  identifiers, so the parser reports the format + record-type inventory only and
  contributes nothing to `fields()`. See [`formats/reg.md`](formats/reg.md).
- **Waters `_HEADER.TXT`** - the one metadata file in a MassLynx `.raw` run.
  The Agilent sidecars above never appear in a `.raw`, so without this parser a
  Waters run yields nothing. A flat `$$ Key: Value` text file carrying the
  instrument (model + serial), the acquired data-file name/date/time, sample
  description/id, acquiring user, bottle (vial) position, and inlet/MS/tune
  method paths. See [`formats/waters_header.md`](formats/waters_header.md).
- **Waters `_INLET.INF` / `inlet.inf` / `_extern.inf`** - the MassLynx method
  records next to `_HEADER.TXT`; they add the inlet/MS method file path (or, for
  the GC run-log `inlet.inf`, a bare method name) under its named
  `...PRO\ACQUDB\` project tree. See
  [`formats/waters_inf.md`](formats/waters_inf.md).
- **Agilent `.dx` (OpenLab OPC archive)** - not a sidecar but a container; the
  walker descends into it and the GUID-named `.CH`/`.UV` signal payloads yield
  full ChemStation headers (operator, method path, signal optics). The manifest
  is left to `rb.read`. See the "Container archives" note above.
- **mzXML** - the open interchange format, not a vendor sidecar. The header
  (read streaming, stopping before the megabytes of base64 scan data) gives the
  instrument, the acquisition/conversion software, and `parentFile` references
  back to the source vendor run. See [`formats/mzxml.md`](formats/mzxml.md).

The parsers here are the structured, canonical answer to those formats: each
decodes what the format actually carries rather than dumping its text.
