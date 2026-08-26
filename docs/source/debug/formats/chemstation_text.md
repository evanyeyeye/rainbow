# ChemStation / MassHunter text and report sidecars

Reference for the human-readable text and report files an Agilent `.D` run
directory ships and rainbow's data parsers never read. Parser:
`rainbow/debug/chemstation_text.py`.

Unlike the INI and XML families these files share no single grammar: each is a
different report with its own encoding and layout. The parser therefore
**dispatches on the file name** to a sub-parser, and `parse()` returns a
`kind`-tagged dict. `canonical()` then promotes the identifier-bearing fields.
The instrument-parameter bodies are overwhelmingly numeric settings (flows,
pressures, temperatures); per the project rule we do not mine numeric data, so
those are preserved for losslessness but only the identifying header feeds the
canonical record.

## Sub-formats at a glance

| file (basename) | `kind` | encoding | canonical contribution |
|---|---|---|---|
| `runstart.txt` | `runstart` | UTF-8 (BOM) | method, data_file, vialpos, sample |
| `acq.txt` | `instrument_report` | UTF-16 | data_file, method |
| `acqmeth.txt` | `instrument_report` | UTF-16 | method, instrument, method_save_time |
| `rtlrep.txt` | `rtl_report` | UTF-8 (BOM) | method, operator, instrument |
| `RUN.LOG` | `run_log` | UTF-16 | serials, devices, vialpos |
| `Audit.txt` | `audit` | UTF-8 | none (inspect-only) |
| `method.txt` | `method_info` | UTF-8 | method |
| `MSPARMS.txt` | `msparms` | UTF-8 | data_file, operator, acquired, instrument, sample |
| `report.txt` | `report_text` | UTF-8 | data_file, sample, operator, instrument, acquired, vialpos |
| `report*.csv` | `report_csv` | UTF-8 | sample, data_file, instrument, method, operator, acquired |
| `acq_methhist.txt` | `methhist` | UTF-8 | data_file, method |
| `scstate.txt` | `scstate` | UTF-8 | serials, devices, instrument |
| `tic_*.csv` / `tic_*.tsv` | `tic_header` | UTF-8 (BOM) | data_file, acquired |
| `rpthead.txt` | `report_header_template` | ASCII | none (inspect-only) |

`ACQ.TXT` (upper-case, inside `ACQ.M/`) and `acq.txt` are the same format; the
name match is case-insensitive. `tic_front.csv`/`.tsv` is matched by the `tic`
prefix; `report*.csv` (e.g. `report00.csv`..`report03.csv`) by the `report`
prefix. The `report` match is restricted to `.csv` because the reader is
comma-delimited; rainbow's own exported `.csv` files (no `tic`/`report` prefix)
are not picked up.

### Encoding note

The `acq.txt`, `acqmeth.txt`, and `RUN.LOG` files are UTF-16 (LE, with BOM). When
you `head`/`cat` one, the interleaved NUL bytes render as spaces, so a banner
(a rule line of repeated `=` or `-` that separates report sections)
that is really `=================` looks like `= = = = =` and a `key: value` with
one space looks like it has several. Decode first (the shared
`rainbow/debug/_util.decode_text` handles BOM and NUL-sniffing); reason about the
decoded string, not the raw dump. The single-space-after-colon reality is why the
`key : value` matcher requires only one space after the colon.

## `runstart` - `runstart.txt`

ChemStation's "Critical RunStart CP Variables" dump: free prose interleaved with
ChemStation `CP` (Command Processor) variable assignments of the form

```
      Methfile (_methfile$) = FAKE-METHOD-0001_da_100-300_simscan.M
      Datafile(,_datafile$) = sample_mix .D
   Sample Name (_dataname$) =
       Alsbottle (_alsbottle) = 15
```

`parse` captures every `Label (_var$) = value` pair into
`variables[var] = {'label': ..., 'value': ...}` (keyed by the CP variable name,
human label kept alongside). Lines that are not CP assignments (the `_overlap`
colon notes, `_maxvial[]` arrays, section banners) are not promoted.

Canonical mapping (empty values are dropped):

| CP variable | canonical |
|---|---|
| `_methfile$` | `method` (method file name) |
| `_datafile$` | `data_file` (data file name) |
| `_alsbottle` | `vialpos` (ALS bottle number) |
| `_dataname$` | `sample` (sample name, often blank) |

## `instrument_report` - `acq.txt` and `acqmeth.txt`

Two reports of acquisition instrument parameters. They share a body grammar -
`=`/`-` rule-underlined section titles followed by aligned `key : value`
parameter lines and the occasional timetable - but different headers.

`parse` returns `{'header': {...}, 'sections': {section: {key: value}}}`:

- **`sections`** is the lossless body. A line is a **section title** when it sits
  next to a rule banner (a line of only `=` or only `-`, length >= 3, no `|` so
  timetable rules are excluded) and looks like a title (has a letter, no aligned
  2-space gap, so columnar data rows are excluded). Pre-banner header lines land
  under the `""` section.
- **`header`** holds the identifying fields, recognized regardless of position:

| source line | header key |
|---|---|
| `Data File : <path>` | `data_file` |
| `Acq. Method : <name-or-path>` | `method` |
| `INSTRUMENT CONTROL PARAMETERS: <model>` (acqmeth banner) | `instrument` |
| a bare `X:\...\*.M` path line (acqmeth lists the method this way) | `method` |
| a trailing weekday-stamped date line (`Tue Dec 17 10:02:51 2019`) | `save_time` |

`acq.txt` (ChemStation LC) supplies `data_file` (a full
`C:\Chem32\...\<sample folder>\<run>.D` path) and `method` (a method file name).
`acqmeth.txt` (MassHunter GC/MS) supplies the instrument **model** from its
banner (`5977B GCMS`), the method full path, and the method **save time**.

`canonical`: `data_file`, `method`, `instrument` from `header`; `save_time` ->
`method_save_time`.

## `rtl_report` - `rtlrep.txt`

The Retention Time Locking data report. A small `Field: value` header block over
a numeric RT calibration table (which is ignored as numeric data):

```
  Retention Locked Method: D:\MassHunter\Methods\FAKE_METHOD_NAME_FID_MS_Hydrogen_ISTD.M
Retention Locked Cal Date:
               Instrument:
                 Operator:
Compound: Analyte
```

`parse` returns `{'header': {...}, 'extra': {...}}` where `header` keeps the
four identity fields and `extra` keeps `Compound`, `RTL Curve`, and
`Maximum Deviation`. Canonical: `Retention Locked Method` -> `method`,
`Operator` -> `operator`, `Instrument` -> `instrument` (any blank field is
dropped, so a report with an empty Operator contributes nothing for it).

## `run_log` - `RUN.LOG`

The instrument event log, and the richest serial source for ChemStation LC runs.
Each event is two lines: a hex framing line (`443 41e2 5a957510 cdb4`) followed
by a message line ending in a `HH:MM:SS MM/DD/YY` stamp:

```
 Method        Method started:  line# 3 ... inj# 1            10:11:12 02/27/18
 G4212A    1   G4212A:DEAA900001 - Detector : Prepare         10:11:16 02/27/18
```

`parse` keeps one record per message line:
`{'module', 'message', 'time', 'date'[, 'module_serial']}`. Hex framing lines
are skipped. The `MODULE:SERIAL` token (module = `G####`/`G####A`, serial = the
on-instrument hardware serial) is the authoritative serial source: ChemStation
LC `.D` runs carry no Devices.xml, so without RUN.LOG these serials are invisible.

Canonical:

- `serials` - every unique `SERIAL` from the `MODULE:SERIAL` tokens.
- `devices` - a `{Name: module, SerialNumber: serial}` per module.
- `vialpos` - from a `vial# N` mention in a "Method started" message, if present.

Acquisition time is **not** promoted from RUN.LOG: its `MM/DD/YY` stamps are
locale-ambiguous, and cleaner sources (`tic_*` header, SampleInfo) supply
`acquired`.

## `audit` - `Audit.txt`

The audit trail of a MassHunter method folder (`<method>.M/Audit.txt`). A header
line naming the audit file's own path, an optional `Created` line, then a run of
`Key : Value` records:

```
D:\MassHunter\GCMS\1\methods\default.m\Audit.txt
Created Tue Sep 20 19:17:52 2016
 Modified : Tue Sep 20 19:17:52 2016
 Event    : Save Method
 Message  : Save Method to D:\MassHunter\GCMS\1\methods\INCH\IC_Default.m
 Why      : Instrument Control method save
 Severity : 1
 Modified : ...
```

`parse` returns `{'path': ..., 'created': ..., 'events': [...]}`; a new event
begins at each `Modified`, and each event keeps
`modified`/`event`/`message`/`why`/`severity`. This is the plain-text counterpart
of the XML `CumulativeAuditTrail.xml` (which the XML parser handles separately):
a different file, a different grammar, so they do not overlap.

**Inspect-only.** The events carry method-save *paths* (which can embed account
or project folders) and timestamps - per-instance forensic context - but no
single clean canonical identifier (no operator/sample field in this fixture's
records), so `canonical` promotes nothing. The point of parsing it is that the
trail is now visible in `inspect()`, where before the whole file was opaque.

## `method_info` - `method.txt`

The MassHunter "Additional Information" method summary (also in `<method>.M/`):

```
Additional Information for IC_Default.m
File created Tue Sep 20 19:17:52 2016
Method : D:\MassHunter\GCMS\1\methods\default.m
Renamed: D:\MassHunter\Methods\FAKE-METHOD-0001.M
```

`parse` returns `{'info': {key: value}, 'lines': [...]}` - the `Key : Value`
pairs plus every non-blank line verbatim. `canonical` lifts the method path:
`Method` if present, else `Renamed`. (When the run's `runstart.txt`/`acqmeth.txt`
already supply `method`, this is a corroborating source; in a bare method folder
it may be the only one.)

## `msparms` - `MSPARMS.txt`

The MSD parameter report that an Agilent LC/MS `.D` writes from the msdiag
register. A
short labeled identity header sits over a long numeric body of MS tune parameters
(skimmer/lens voltages, mass-axis calibration points, EM/HED settings). Example
header (values synthetic):

```
File          :   C:\Chem32\1\DATA\DEMO 2019-11-14 15-07-42\002-0101.D
Operator      :   Alex Sampleton
Date acquired :   Thu Nov 14 15:11:33 2019
Instrument    :   LCMS_0-001A
Tune File     :   C:\Chem32\1\6140ATUN\atunes.tun
Sample name   :   blank
...
MS parameters - Positive
----------------------------------
Skim1         :    35 V
...
```

`parse` returns `{'header': {...}, 'lines': [...]}`: the header keyed already by
canonical name (`File`->`data_file`, `Operator`->`operator`, `Date acquired`->
`acquired`, `Instrument`->`instrument`, `Sample name`->`sample`; first value
wins) plus every non-blank line verbatim. The numeric MS-parameter body is kept
for losslessness but, like the other report bodies here, is not mined - only the
labeled header feeds `canonical`, which returns the header as-is.

This usually **corroborates** the run's other sidecars (`runstart.txt` / `tic_*`
also carry `data_file` and `acquired`), so the merge's first-non-empty rule keeps
one value. Its distinct contribution is `operator` (a clean personal-name field,
which the LC/MS `runstart` lacks) and the `Instrument` host name. `Tune File` is a
path but a fixed instrument-tune reference, so it is left in `lines`, not
promoted.

## `report_text` - `report.txt`

The ChemStation acquisition / area-percent report. A fixed-width header (two
right-aligned `Label : value` columns) names the run, followed by method/sequence
prose and a numeric peak table. Example header (values synthetic):

```
Data File C:\...\Data\DEMO\023-D3F-B11-sample-23.D
Sample Name: DEMO-SAMPLE-23
1290UHPLC 1/26/2024 7:42:22 PM SYSTEM
=====================================================================
Acq. Operator   : Alex Sampleton                  Seq. Line :  23
Acq. Instrument : 1290UHPLC                         Location :   D3F-B11
Injection Date  : 1/26/2024 7:36:13 PM                  Inj :   1
Method          : C:\...\DEMO_isocratic.M (Sequence Method)
=====================================================================
                         Area Percent Report
...
```

`parse` returns `{'header': {...}, 'lines': [...]}`. The data-file line has no
colon (`Data File <path>`), so its path is taken as the rest of the line; the
remaining identity labels are read by a cell matcher that stops each value at the
next 2-space gap (the start of the second column). The wrapped Method/Sequence
paths and the entire numeric peak table are kept verbatim in `lines` but not
mined; `canonical` returns the header (`data_file`, `sample`, `operator`,
`instrument`, `acquired` from `Injection Date`, `vialpos` from `Location`).

## `report_csv` - `report00.csv` .. `report03.csv`

The same report exported as a quoted CSV, one `"Key","Value",""` row per field:

```
"Sample Name","DEMO HTE Screen 89",""
"Data File","C:\...\Data\DEMO\",
"Acq. Instrument","LCMS",""
"Acq. Method","4min FFP MS.M",""
"Acq. Operator","Alex Sampleton",""
"Injection Date","23-Jun-23, 03:57:09",""
```

`parse` returns `{'header': {...}, 'rows': [[...], ...]}` (a leading BOM is
stripped so the first key matches). The identity keys map directly to canonical
names (`Sample Name`->`sample`, `Data File`->`data_file`, `Acq. Instrument`->
`instrument`, `Acq. Method`->`method`, `Acq. Operator`->`operator`, `Injection
Date`->`acquired`); the numeric rows (peak areas, `Location` as a float) are kept
in `rows` but not promoted. `canonical` returns the header.

## `methhist` - `acq_methhist.txt`

The acquisition method-history summary: a `Data File` / `Acq. Method` head over a
repeating `Operator` / `Date` / `Change Info` method audit trail.

```
Data File  : C:\...\Data\DEMO\013-...D
Acq. Method: DEMO-long-005.M
The Acq. Method's Audit Trail at the end of the Run :
Operator   : SYSTEM
Date       : 2/3/2025 7:52:10 AM
Change Info: This method was created ... based on method 'C:\...\DEMO-006.M'
...
```

`parse` returns `{'header': {...}, 'lines': [...]}` - the audit trail is kept
verbatim in `lines`; `canonical` lifts `data_file` and `method` (the `Acq.
Method`). This corroborates the run's other sidecars; in a folder where only the
history survives it is the source.

## `scstate` - `scstate.txt`

The SmartCard "SC State Report", blocks of `Key = Value` instrument
configuration. Most of it is numeric instrument state; the identity is the
instrument model and serial:

```
                          SC State Report (Rev. 2.01)
Instrument Configuration:
  Instrument Model          = G6120B
  Serial Number             = DEMO00001
  Mass Range Low/High[Res]  = 0.15 / 3276.00 [0.050]
...
```

`parse` returns `{'info': {key: value}, 'serials': [...], 'lines': [...]}` - the
`info` map and verbatim `lines` are lossless; `serials` collects every distinct
`Serial Number` value. `canonical` promotes `serials`, a `devices` entry pairing
the first serial with the `Instrument Model`, and `instrument` (the model). For
an MS `.D` whose serial appears nowhere else, this is the only source.

## `tic_header` - `tic_front.csv` / `.tsv`

A total-ion-chromatogram dump. Only the first line is metadata; everything after
`Start of data points` is numeric and ignored:

```
D:\MassHunter\Data\sample_mix .D Tue Dec 17 10:13:57 2019
Start of data points
0.09353,11398
...
```

`parse` returns `{'header': {'data_file': ..., 'acquired': ...}}`, splitting the
first line at the `.D` path boundary from the trailing weekday timestamp. If the
first line does not match that shape it is kept verbatim under `header['line']`.
Canonical promotes `data_file` and `acquired` directly.

## `report_header_template` - `rpthead.txt`

The customizable page printed atop method reports. Its own text says it "can be
used to identify the laboratory which uses the method," so a site that customized
it would put a lab name here - but the fixtures carry only the default Agilent
ASCII-art logo with no parseable field. This is therefore **inspect-only**:
`parse` keeps the non-blank lines verbatim under `lines`, and `canonical`
promotes nothing. (If a customized header with a real lab line turns up, this is
where to add extraction.)

## Canonical mapping summary

| canonical field | sub-format(s) | source |
|---|---|---|
| `method` | runstart, instrument_report, rtl_report, method_info, report_csv, methhist | `_methfile$` / `Acq. Method` / `*.M` path / `Retention Locked Method` / `method.txt` `Method` / `Acq. Method` |
| `data_file` | runstart, instrument_report, tic_header, msparms, report_text, report_csv, methhist | `_datafile$` / `Data File` / first-line path / `File` |
| `instrument` | instrument_report, rtl_report, msparms, report_text, report_csv, scstate | acqmeth banner / `Instrument` / `Acq. Instrument` / `Instrument Model` |
| `method_save_time` | instrument_report | acqmeth weekday date line |
| `acquired` | tic_header, msparms, report_text, report_csv | first-line timestamp / `Date acquired` / `Injection Date` |
| `operator` | rtl_report, msparms, report_text, report_csv | `Operator` / `Acq. Operator` |
| `serials` | run_log, scstate | `MODULE:SERIAL` / `Serial Number` |
| `devices` | run_log, scstate | `MODULE:SERIAL` / model + `Serial Number` |
| `vialpos` | runstart, run_log, report_text | `_alsbottle` / `vial# N` / `Location` |
| `sample` | runstart, msparms, report_text, report_csv | `_dataname$` / `Sample name` |

## Open questions / future depth

- The instrument-parameter bodies (`sections`) are captured losslessly but not
  canonicalized; they are numeric instrument settings, intentionally left as
  structure. If a specific parameter is ever wanted as a field, it is already in
  `sections` for promotion.
- `rpthead.txt` customized-lab-name extraction is unimplemented (no fixture).
- RUN.LOG message classification is coarse (module + free text). The per-module
  message vocabulary (Prepare/Idle/Run, pressure, temperature) could be parsed
  into typed events if a use case appears.
- The data-file paths embed a sample-folder name and the method paths embed a
  Windows account / person folder; as with the XML parser these are kept inside
  the path string, not split into separate identity fields.
