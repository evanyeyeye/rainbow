# Agilent/Waters XML sidecars

Reference for the XML metadata files rainbow's data parsers do not read. Parser:
`rainbow/debug/xml.py`. Unlike INI there is no single schema: each file is a
different Agilent or Waters XML vocabulary. The parser therefore has two layers,
and this document records the structure of each schema as it is reverse
engineered.

## Two layers

1. **Generic structure** (`parse`, surfaced by `inspect`) - a faithful, lossless
   nested dict of the *entire* document, schema-agnostic. Works for every file,
   including ones with no canonical extractor yet.
2. **Canonical projection** (`canonical`, surfaced by `fields`) - dispatched on
   the root element to a schema-aware extractor. Schemas without an extractor
   contribute nothing to `fields` but are still fully present in `inspect`.

### `parse` dict shape

Element -> dict. Attributes are stored under `@name` keys; element text under
`#text` (or as the bare string value for a pure leaf); a child tag repeated
within its parent becomes a **list**. Namespaces are stripped from tag names
(the namespace is reported separately as `parsed['namespace']`).

### Encoding and recovery

UTF-8/UTF-16 with optional BOM (BOM stripped before parsing). Malformed
documents are recovered: `Limsinf.xml` declares an invalid namespace URI
(`xmlns:xsi='http:\\www.w3.org\2001\XMLSchema-instance'`, backslashes), which
fails a strict parse; the parser retries with `recover=True`. A document that
fails even recovery yields `{'parser': 'xml', 'error': 'unparseable XML'}`
rather than raising.

Some sidecars are **UTF-16LE with no BOM and no encoding declaration** (the
`.tune` files), which lxml cannot detect from the raw bytes. When the raw parse
fails, the parser falls back to decoding via the shared `decode_text`, strips a
leading declaration/BOM, re-encodes to UTF-8, and parses that; so these are
handled without a special case per format.

An **empty or whitespace-only** file is reported distinctly as
`{'parser': 'xml', 'error': 'empty file'}`, not conflated with a malformed
document. Agilent writes a 0-byte `TimeStamp.xml` into many MassHunter `.D` runs
(74 of them in the test corpus, all empty); these are benign placeholders, so
the cleaner marker keeps them from reading as corruption in an `inspect()` sweep.
Either way `fields()` is unaffected - an error entry contributes nothing.

## Schemas

### SampleInfo - `sample_info.xml`  (canonical: yes)

A table of `<Field>` records, each `<Name>` / `<DisplayName>` / `<Value>` /
`<DataType>`. `canonical` flattens to a `Name -> Value` map and promotes:

| Field `Name` | canonical |
|---|---|
| `Sample Name` | `sample` |
| `Sample ID` | `sample_id` |
| `Operator` | `operator` |
| `Sample Position` | `vialpos` |
| `Method` | `method` (full path, e.g. `D:\MassHunter\Methods\...M`) |
| `Data File` | `data_file` (full path, e.g. `D:\MassHunter\Data\...D`) |
| `Inj Vol (µl)` | `injection_volume` |
| `Acquired Time` | `acquired` |

Other `Name`s (Dilution, Wt/Vol, Sample Type, Level Name, Comment, Balance
Override, ...) are kept in `inspect` but not promoted. `DataType` `8` = string.

### Devices - `Devices.xml`  (canonical: yes)

One record per instrument module: `Name`, `ModelNumber`, `SerialNumber`,
`FirmwareVersion`, `DriverVersion`, `Type`, `StoredDataType`, `Delay`, `Vendor`.
The authoritative serial/model source. `canonical` emits:

- `serials` - every `SerialNumber` except the placeholder `"1"` (e.g. an FID
  reports serial `1`).
- `devices` - a structured list of `{Name, ModelNumber, SerialNumber,
  FirmwareVersion, DriverVersion}` per module.

### Sample - `SAMPLE.XML`  (canonical: yes)

Flat acquisition fields: `Version`, `Amount`, `Multiplier`, `Dilution`, `ISTD`,
`RefDataFilePath`, `ACQMethodPath`. `canonical`:

- `method` <- `ACQMethodPath`
- `data_file` <- `RefDataFilePath`

`ACQMethodPath` frequently embeds a Windows user path
(`C:\Users\<account>\Documents\<Full Name>\...M`); the account/name are not
split out into separate canonical fields (left inside the path).

### AuditTrailDataSet - `*CumulativeAuditTrail.xml`  (canonical: yes)

Namespace `http://tempuri.org/AuditTrailDataSet.xsd`. A list of event records:
`ID`, `ComputerName`, `User`, `TimeStamp`, `Comment`
(e.g. "Data collection has been initiated."). `canonical`:

- `computers` - unique `ComputerName`s (the acquisition workstation host).
- `users` - unique `User`s.

### SampleLimsInfo - `Limsinf.xml`  (canonical: no, planned)

Malformed namespace (see Recovery above). Recovered to the `SampleLimsInfo`
root; LIMS sample fields. Currently inspect-only.

### ACAML - `*.acaml` / `*.macaml` / `*.acam_`  (canonical: yes)

ACAML (Agilent Common Analytical Markup Language), namespace
`urn:schemas-agilent-com:acaml15`. The richest Agilent metadata container:
method, sequence, sample, and instrument context. The document is `ACAML > Doc`,
with `Doc/DocInfo` (provenance) and `Doc/Content` (the data).

**It reuses the generic key `Name` in hundreds of unrelated method-parameter
sections**, so the extractor navigates by explicit path (`_dig`), never by key
search. The paths it reads:

| path | canonical | example |
|---|---|---|
| `Doc/DocInfo/CreatedByUser` | `users` | a `DOMAIN\account` login |
| `Doc/DocInfo/ClientName` | `computers` | the workstation host name |
| `Doc/DocInfo/CreatedByApplication/AgilentApp/{Name,Version}` | `software_version` | `ChemStation 2.183.0.0` |
| `Doc/Content/Resources/Instrument/Name` | `instrument` | the instrument display name |
| `Doc/Content/Resources/Instrument/Module[]` | `serials`, `devices` | per-module `Name`/`PartNo`/`SerialNo`/`FirmwareRevision` |
| `Doc/Content/SampleParams/IdentParam/Name` | `sample` | the sample name |
| `Doc/Content/SampleParams/AcqParam/VialNumber` | `vialpos` | the vial number |
| `Doc/Content/SampleParams/AcqParam/InjectionVolume/@val` | `injection_volume` | injection volume |
| `Doc/Content/Samples/MeasData/Info/CreatedBy/Username` | `operator` | the acquisition operator |
| `Doc/Content/Samples/MeasData/Info/CreatedDate` | `acquired` | acquisition timestamp |

The `Module[]` records are the authoritative instrument-serial source for an LC
run (they agree with `RUN.LOG`'s `MODULE:SERIAL` and the `.scml` sampler), and
they carry `PartNo` (model) and `FirmwareRevision` on top. `DocInfo` is where the
person/workstation identifiers live (a `DOMAIN\account` and the host name).

### SampleContainerInfo - `*.scml`  (canonical: yes)

The autosampler container file, namespace `file://SampleContainerInfo.xsd`.
`canonical` reads the **outer** document:

| path | canonical |
|---|---|
| `ContainerDeviceInfo/SerialNumber` | `serials` |
| `ContainerDeviceInfo/{DisplayName,PartNumber,SerialNumber,Vendor}` | `devices` |
| `ActiveSampleLocation/@LocationString` | `vialpos` |

The sampler serial here matches the corresponding module in ACAML / RUN.LOG.

The `XmlContent` elements hold **gzip+base64 sub-documents**, but decoding them
(they are UTF-16) shows they are tray **rendering geometry** - a
`SampleContainerDevice` with an identifier, a display name, location counts, and
an escaped rendering `XML` - with no sample or person identifiers. Expanding them
would add tens of KB of geometry to `inspect` for no identifier gain, so they are
deliberately left as the verbatim base64 string, which a caller who does want
the geometry can decode themselves.

### AnalyticalResultsModuleData - `*.drvml`  (canonical: yes)

Agilent driver-results markup, namespace `file://GenericAnalyticalResultData.xsd`.
One file per instrument module (e.g. `PMP1.AnalyticalResults.drvml` for the
binary pump), written by the MassHunter acquisition drivers. The `ModuleInfo`
block carries that module's identity:

| path | canonical |
|---|---|
| `ModuleInfo/SerialNumber` | `serials` (excl. placeholder `1`) |
| `ModuleInfo/{DisplayName,PartNumber,SerialNumber,FirmwareRevision,Vendor}` | `devices` |

`fields()` accumulates the per-module records across the run's several `.drvml`
files, the same way it does for `Devices.xml`/ACAML modules (`serials` dedupes by
value). The `DataChannels` body is numeric result data and is left in `inspect`
only.

Note on coverage: `.drvml` was a *matching* gap, not a parse gap - `parse()`
already produced the faithful tree, but `.drvml` was absent from `_EXTS` so the
file was never claimed and `canonical()` was never reached. In the corpus every
`.drvml` run also ships `Devices.xml`/ACAML, so these serials are corroborating
rather than the sole source; the value is provenance completeness (the driver
file now contributes to `_sources`) plus the per-module firmware/model detail.

### Root - `*.tune`  (canonical: yes)

The Agilent MS tune file (`tunefilexml_1.tune` and similar in an MS `.D`),
UTF-16LE with no BOM. Its root element is the generic `<Root>`, so the handler
extracts only when the tune-specific `SerialNumber` is present (any other
`<Root>` document falls through to `{}`):

| path | canonical |
|---|---|
| `.../SerialNumber` | `serials` (every distinct value) |
| `.../{InternalModel,ExternalModel}` | `instrument` (the model); `devices` pairs it with the first serial |

The bulk of the file is numeric tune parameters, left in `inspect` only. The
instrument serial here can be the sole source for an MS `.D` whose serial is not
in a `.REG`/`Devices.xml`/`scstate.txt`.

### Method / automation / calibration XML  (canonical: no)

Inspect-only; mostly method parameters or numeric calibration, low identifier
content:

- `GCMSAcqMethod` (`method.xml`), `MSAcqMethod` (`qqqacqmethod.xml`),
  `RTPInfo`/`GCInfo`/`UIelements` (`Acq.RTP*.xml`, `Acq.Monitors.xml`) - method
  parameters.
- `Contents` (`Contents.xml`) - acquisition file inventory.
- `Checksum` (`checksum.xml`) - integrity hashes, no metadata.
- `AutomationInfo` (`info.xml`) - program registry key + exe path, no PII.
- `DefaultMassCalibration`, `TimeSegments` (`MSTS.xml`), `IonRecords`,
  `ArrayOfMSTS_XAddition` - numeric calibration/segment data (rainbow already
  parses some of these for its own purposes).

## Canonical mapping summary

One row per field, listing every schema that emits it (the source column pairs
the schemas in order):

| canonical field | schema(s) | source |
|---|---|---|
| `serials` | Devices, ACAML, SampleContainerInfo, AnalyticalResultsModuleData, Root | `SerialNumber` (excl. `1`) / module serials / `.tune` `SerialNumber` |
| `devices` | Devices, ACAML, SampleContainerInfo, AnalyticalResultsModuleData, Root | per-module record / `.tune` model + serial |
| `instrument` | ACAML, Root | `Resources/Instrument/Name` / `.tune` model |
| `sample` | SampleInfo, ACAML | `Sample Name` / `IdentParam/Name` |
| `sample_id` | SampleInfo | `Sample ID` |
| `operator` | SampleInfo, ACAML | `Operator` / `MeasData CreatedBy` |
| `vialpos` | SampleInfo, ACAML, SampleContainerInfo | `Sample Position` / vial position |
| `method` | SampleInfo, Sample | `Method` / `ACQMethodPath` |
| `data_file` | SampleInfo, Sample | `Data File` / `RefDataFilePath` |
| `injection_volume` | SampleInfo | `Inj Vol (µl)` |
| `acquired` | SampleInfo | `Acquired Time` |
| `software_version` | ACAML | `CreatedByApplication/AgilentApp` |
| `computers` | AuditTrailDataSet, ACAML | `ComputerName` / `DocInfo/ClientName` |
| `users` | AuditTrailDataSet, ACAML | `User` / `DocInfo/CreatedByUser` |

## Open questions

- SampleInfo `Operator` / `Acquired Time` fields are not present in every file;
  promotion is best-effort on what exists.
- Windows account / person names embedded in path values (`ACQMethodPath`,
  `Data File`) are kept inside the path, not extracted as separate fields.
- ACAML `devices` (rich: model + firmware) and the leaner `RUN.LOG` device
  records are not merged into one per the shared serial - both shapes survive in
  the merged `devices` list. The `serials` list does dedupe by value.
- `.scml` gzip+base64 inner documents are tray geometry and are left unexpanded
  (see the SampleContainerInfo section); revisit only if the geometry is wanted.
