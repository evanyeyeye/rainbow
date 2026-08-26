# mzXML (open format)

Reference for mzXML files. Parser: `rainbow/debug/mzxml.py`. mzXML is the open
HUPO-PSI interchange format that acquisition and conversion tools export to - the
kind of liberated, documented format rainbow exists to encourage, in contrast to
the proprietary vendor sidecars the other debug parsers reverse-engineer. The
header still carries provenance worth surfacing.

## Format

XML, namespace `http://sashimi.sourceforge.net/schema_revision/mzXML_3.2` (the
revision varies). The document is `mzXML > msRun`, whose header children are:

- `parentFile` (one or more) - `fileName` references back to the source vendor
  files, e.g. `file:///D:/.../SAMPLE-001.d/AcqData/MSProfile.bin`.
- `msInstrument` - `msManufacturer`, `msModel`, `msIonisation`,
  `msMassAnalyzer`, `msDetector` (each carries the description in a `value`
  attribute) and a `software` element.
- `dataProcessing` - the conversion `software` and `processingOperation` (only
  the `software` entries are captured; the `processingOperation` is not).

After the header come the `<scan>` elements: one per spectrum, each inlining its
peak list as base64. These dominate the file (10k+ scans, megabytes); a real
file here is ~7 MB.

## Matching

Files ending `.mzXML` (case-insensitive). Note `.mzXML` also ends with `.xml`, so
the generic `xml` parser **explicitly declines it** (see `xml.matches`); routing
it to the full-tree XML parser would build the entire multi-MB scan tree in
memory. This dedicated parser reads only the header instead.

## What `parse` returns

A streaming `iterparse` pass over **start** events that **breaks at the first
`<scan>`**, so the peak data is never read. The returned header (synthetic
example):

```python
{'parser': 'mzxml',
 'msRun': {'scanCount': '13811', 'startTime': 'PT0.107S', 'endTime': 'PT1410.06S'},
 'parent_files': ['file:///D:/.../RUN_047.d/AcqData/MSProfile.bin',
                  'file:///D:/.../RUN_047.d/AcqData/MSScan.bin'],
 'instrument': {'msManufacturer': 'Agilent', 'msModel': '6470 QQQ',
                'msIonisation': 'Esi', 'msMassAnalyzer': 'Quadrupole',
                'msDetector': 'EMT'},
 'software': [{'type': 'acquisition', 'name': 'MassHunter Data Acquisition', 'version': '8.0'},
              {'type': 'conversion', 'name': 'MassHunter Qualitative Analysis', 'version': '12.0.430.0'}]}
```

## Depth decision

Header only; the per-scan peak arrays are the bulk numeric payload and carry no
identity, so the streaming read stops before them. `startTime`/`endTime` are
acquisition *durations* (ISO-8601 `PT...S`), not wall-clock timestamps, so there
is no `acquired` field to promote. Everything surfaced is run-level provenance.

## Canonical mapping

See `rainbow/debug/mzxml.py::canonical`.

| header source | canonical | notes |
|---|---|---|
| `msInstrument/msModel` else `msManufacturer` | `instrument` | Agilent's exporter often writes a generic placeholder (`"Agilent instrument model"`); surfaced verbatim |
| acquisition `software` (else first) | `software_version` | `name` + `version` joined, e.g. `MassHunter Data Acquisition 8.0` |
| first `parentFile` | `data_file` | the source run dir: the `://` scheme is stripped and the path trimmed to its `.d`/`.raw` component |

## Open questions / future depth

- `parentFile` paths embed a Windows project tree and frequently an operator or
  project name (`.../Data/<operator>/...`). As with the Agilent `ACQMethodPath`,
  the embedded name is left inside the path rather than promoted to `operator`.
- The instrument `value`s in the observed Agilent exports are generic
  placeholders; a real, specific model from another converter would flow through
  unchanged. Not yet seen in the corpus.
- `dataProcessing` records the full conversion chain (multiple `software`
  entries); only the acquisition entry feeds `software_version` today. The
  conversion history is kept in `parse()`/`inspect`.
- A second `parentFile` may point at a different source component; only the
  first is used for `data_file` (they share the run dir in every observed file).
