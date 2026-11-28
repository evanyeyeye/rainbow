# OpenLab CDS `.sirslt` test folders

Three real single-injection result folders from Agilent OpenLab CDS 2.x, kept
for the `.sirslt` reader's tests (`tests/test_sirslt.py`, and `lime` in
`tests/test_agilent.py`). A fourth, `fig.sirslt`, and three lone acquisition
methods are described at the end.

| Folder | Instrument | Holds |
| --- | --- | --- |
| `olive.sirslt` | UHPLC DAD with an LC/MSD iQ single quadrupole | DAD spectrum (`DAD1I`, 200-400 nm), one DAD signal (`DAD1A`, 220 nm), 237 MS centroid scans (`MSPeak.bin`), 22 telemetry traces. Manifest `<ScaleFactor>` for the spectrum: `1000 * 2**-27`. |
| `plum.sirslt` | HPLC with a DAD | DAD spectrum (`DAD1I`, 190-400 nm), one DAD signal (`DAD1A`, 220 nm), 11 telemetry traces. No MS. Manifest `<ScaleFactor>` for the spectrum: `1000 * 2**-21`. |
| `lime.sirslt` | HPLC with a DAD | One DAD signal (`DAD1A`, 220 nm), 9 telemetry traces. No spectrum and no MS. |

## How they were anonymised

Only the files rainbow reads were kept: the `.dx` archive, the `.acaml`
result-set document and, for `olive`, the `MSScan.bin` / `MSPeak.bin`
binaries. The processing results (`.rx`), checksums (`.mfx`), methods
(`.amx`, `.pmx`), sequence (`.sqx`), sampler configuration (`.scml`) and
report files were dropped. Without the `.mfx`, OpenLab itself will no longer
open these folders.

Inside the `.dx` archive:

- the embedded report members (`.grd`) and their manifest signals were removed;
- in `injection.acmd` and `MSData/*.xml`, the method path, sample name (for
  `lime`), instrument name and spectrometer serial number were replaced;
- in the headers of the `.UV`, `.UVD`, `.CH` and `.IT` payloads, the
  length-prefixed sample-name and method-path strings were rewritten in place,
  each in its own fixed slot. No data bytes were touched.

The `.acaml` was cut down to the instrument block rainbow reads (name,
technique, and each module's name, type, part number, serial number and
firmware) plus the document's description, creating user and date. The audit
trail, custom fields, sample, method and injection sections were removed.
Instrument names are now `LCMS1`, `HPLC1` and `HPLC2`, and module serial numbers are
placeholders (`DE00000001`, `SG00000001`, ...). The folders and their files
were renamed after the colour, and `<ExternalElementPaths>` was updated to
match.

Every detector signal, telemetry trace and centroid scan reads identically
before and after.

## `fig.sirslt`, the single-quad runs and the lone acquisition methods (`.amx`)

| File | Was | Holds |
| --- | --- | --- |
| `fig.sirslt` | `openlab.sirslt` | HPLC with a DAD: DAD spectrum (`DAD1I`), four DAD signals (`DAD1A`-`D`: 229, 200, 260, 360 nm), its acquisition method `fig.amx` (was `flow_rate_simple_test.amx`). |
| `date.amx` | `flow_rate_example.amx` | A gradient whose timetable changes the flow. |
| `pear.amx` | `Glucosinolates-XDB5.amx` | A gradient at one flow, 40 °C, 5 µL. |
| `kiwi.amx` | `column_storage_ACN100.amx` | No timetable, oven not controlled, one DAD signal, no spectrum. |
| `mango.amx` | `example_DAD_only.amx` | UHPLC with a DAD and an LC/MSD iQ single quad, set to Scan alone (m/z 100-1000). |
| `jade.sirslt` | | The same LC/MS: one SIM/Scan time segment, a scan of m/z 100-1000 and the SIM ion m/z 295; its method `example_MS_with_SIM.amx`. |
| `ochre.sirslt` | | Two SIM/Scan time segments (from 0 and 2 min), each its own SIM ion (m/z 195, 230); `example_MS_with_time_segments.amx`. |
| `rose.sirslt` | | Positive and negative scans, the negative on a fragmentor ramp; `example_MS_pos_and_neg.amx`. |
| `coral.sirslt` | | A UHPLC with a DAD alone: signal A at 220 nm with a 360 nm reference; `example_DAD_ref.amx`. |

The first four methods are from one HPLC. They are by Ethan Bass, released under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/), from
[chromConverterExtraTests](https://github.com/ethanbass/chromConverterExtraTests)
(`inst/`), and are read by `tests/test_amx.py`.

How they were anonymised:

- Only the `.dx`, `.acaml` and `.amx` of `openlab.sirslt` were taken; its
  `.rx`, `.mfx` and fraction collector `.scml` were not.
- The `.acaml` was cut down as `olive`'s was: the description, creating user
  and date, and the instrument block (name, technique, and each module's
  name, type, part number, serial number and firmware). The PC name, the
  injection metadata, project, audit trail, custom fields (lamp and flow
  cell serials among them), sample, method and injection sections were
  removed. The instrument is now `HPLC3`.
- In the `.dx` archive, the result path (`C:\CDSProjects\<project>\Results\
  <instrument>-<date>.sirslt\<method>.amx`) is now `D:\Results\fig.sirslt\
  fig.amx`: in `injection.acmd`'s `<AcquisitionMethod>`, and in each `.UV`,
  `.UVD`, `.CH` and `.IT` header, where it is a length-prefixed UTF-16 string
  at 0xA0E, rewritten in its own slot and zero-filled. No data bytes were
  touched.
- In each `.amx`: the module serial numbers in the driver parts'
  configuration are `DE00000001`-`DE00000006` (the same placeholder for a
  module in every file, the `.acaml` too), their IP address is `192.0.2.1`,
  the report's "Last Saved As" is `D:\Methods\<name>.amx` and the core
  properties' title is the new name. Each changed part's `.chk` holds its new
  SHA-1, so the packages stay self-consistent.
- The files were renamed after a fruit.

Kept as they were in the first four: the generic `SYSTEM (SYSTEM)` account
(creator, modifier and run operator), dates, document and method GUIDs, part numbers and
firmware. Every detector signal and every setting `tests/test_amx.py` checks
reads identically before and after; only the method name (`fig.amx`,
`date.amx`, ...) and the instrument name changed.

`mango.amx` and the four runs were shared by p3bm in #82 for rainbow's tests,
already anonymised: made on an OpenLab system's default account, the
instruments named `LCMS1` and `UHPLC1`, their serial numbers placeholders
(`DE000000..`, `SG00000001`), the result paths `C:\Data\<run>.sirslt\`. They
are byte for byte as shared; only `mango.amx` was renamed, so it still states
the name it was last saved as (`BEH_Acidic_6min.amx`) as `acq_method`.
