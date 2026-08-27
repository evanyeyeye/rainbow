# Agilent INI sidecars

Reference for the `[section]` / `key=value` configuration files Agilent
ChemStation and MassHunter write alongside a run. rainbow's data parsers do not
read them. Parser: `rainbow/debug/ini.py`. This document records the structure
of the format and of each specific file, including everything reverse-engineered
from the fixtures.

## Encoding

No single encoding. Observed: UTF-8, UTF-16LE, and UTF-16BE, sometimes with a
BOM, sometimes only detectable from interleaved NUL bytes. The parser decodes
with `rainbow/debug/_util.decode_text`, which sniffs in this order: BOM (`FF FE`
/ `FE FF`) -> declared `encoding=` -> a NUL byte in the first 64 -> UTF-8 BOM ->
UTF-8, falling back to latin-1. Never raises.

## Grammar

Standard INI, with these specifics seen in the wild:

- `[section]` header lines. A key may appear before any section header (rare);
  the parser collects those under the `""` section.
- `key=value`, split on the first `=` only (values may contain `=`).
- Blank lines and lines beginning with `;` or `#` are ignored.
- A key repeated within one section is kept as a **list** (e.g. the two `CS=`
  lines in `CSlbk.ini`).
- Values are kept verbatim as strings. No type coercion. Some values are
  themselves structured (CSV or hex); those sub-formats are documented below but
  left verbatim in `parse()` and interpreted only in `canonical()`.
- Keys are frequently **dotted namespaces**, e.g. `gc.sn`, `gc.fw`,
  `ALS.fr.present`, `ALS.fr.syringe`. The dotting is a flat convention, not a
  nested structure; the parser keeps the literal dotted key.

`parse()` returns the lossless section -> key -> value structure under a
`'parser'` tag (synthetic values):

```python
{'parser': 'ini',
 'sections': {'Acquisition': {'gc.sn': 'DEAA900001',
                              'gc.fw': 'A.01.05',
                              'InjVolume': '1.0'},
              'Method':      {'MethSaveWHO': 'labuser'}}}
```

`canonical()` then lifts the well-known keys (`gc.sn` -> `serials`,
`InjVolume` -> `injection_volume`, `MethSaveWHO` -> `operator`, ...); see the
mapping table below.

## The files

### `GC.ini`  (instrument driver state)

One section per module driver, e.g. `[7890 DriverItem]`. ~275 keys, dotted by
subsystem. High-value keys:

| key | meaning |
|---|---|
| `gc.sn` | GC serial number (e.g. `SN00000011`) |
| `gc.fw` | GC firmware revision |
| `gc.ready`, `gc.status` | run-state enums |
| `ALS.<inlet>.*` | autosampler config (present, syringe size, ...) |

Most of the remaining keys are live instrument state (temperatures, flows,
ready flags) - kept losslessly in `inspect`, not promoted.

### `PRE_POST.INI`  (pre/post-run snapshot, MS)

~11 sections incl. `[POSTRUN]`, `[TuneValues]`, `[MS_Faults]`. High-value keys
(seen under `[MS_Faults]`):

| key | meaning |
|---|---|
| `SmartCard` | MS identity CSV, see sub-formats below (model + serial + fw) |
| `Application` | acquisition software build string |
| `Date` | run timestamp (`Tue Dec 17 10:13:33 2019`) |
| `SampleAmount`, `Multiplier` | quantitation scalars |
| `[TuneValues]` | MS tune parameters (numeric) |

### `method.ini`  (MassHunter method, GC/MS)

~5 sections incl. `[global]`, `[Compliance]`, `[rtlock_<inlet>]`. High-value:

| key | meaning |
|---|---|
| `MethSaveWHO` | user who saved the method (operator login, e.g. `labuser`) |
| `MethSaveTime` | when the method was saved (`Tue Dec 17 10:02:51 2019`) |
| `AcqVersion` | acquisition software build string |
| `locked_inlet`, `MHRTLmasses` | retention-time-lock config |

### `EZXSMETH.INI`  (ChemStation acq/DA method info)

Single `[MethInfo]` section. Small but useful:

| key | meaning |
|---|---|
| `InjVolume`, `MaxInjVol` | injection volume (uL) |
| `UVASig` | DAD signal/optics CSV, see sub-formats below |

### `CSlbk.ini`  (ChemStation logbook marker)

Two sections: an empty `[RUN.LOG]` and `[CSlbk.ini]` with:

| key | meaning |
|---|---|
| `MDT` | method-modified datetime, **hex-encoded UTF-16LE** (decoded below) |
| `CS` | checksum integers (repeats -> list) |

### `tgtmass.ini`

`[TgtMass]` -> `TargetMass` (empty in the fixture). No run metadata.

## Sub-value formats

Several values are structured. Documented here; decoded in `canonical()`.

### `SmartCard` (CSV)

```
SmartCard=AGILENT TECHNOLOGIES,5977,SN00000012,6.00.34
          vendor              ,model,serial    ,firmware
```
Comma-separated, 4 fields. Field 2 -> `instrument` (model), field 3 -> a
`serials` entry.

### `UVASig` (CSV)

```
UVASig=210,8,360,100,1
       │   │ │   │   └─ reference-enabled flag (1/0)
       │   │ │   └───── reference bandwidth (nm)
       │   │ └───────── reference wavelength (nm)
       │   └─────────── signal bandwidth (nm)
       └─────────────── signal wavelength (nm)
```
Matches the `Sig=`/`Ref=` optics convention used elsewhere in Agilent (see
`openlab.py`). Promoted verbatim to `signal_optics`; the field split is
documented but not yet parsed into separate canonical fields.

### `MDT` (hex-encoded UTF-16LE datetime)

The `MDT` value is an ASCII-hex string whose bytes are a UTF-16LE datetime,
padded with trailing NULs and a 1-byte tail. Decode = unhex -> `utf-16-le`
-> strip NULs. Verified:

| fixture | raw `MDT` (head) | decoded |
|---|---|---|
| green.D | `33002F0032002F00...` | `3/2/2022 11:22:18` |
| red.D | `320037002F00...` | `27/2/2018 10:26:5` |

A candidate for promotion to a canonical timestamp; currently left verbatim
pending a decision on which timestamp field it maps to.

## Canonical mapping

See `rainbow/debug/ini.py::canonical`. Current promotions: `serials` (`gc.sn` +
`SmartCard` field 3), `instrument` (`SmartCard` field 2), `operator`
(`MethSaveWHO`), `method_save_time` (`MethSaveTime`), `software_version`
(`AcqVersion` else `Application`), `injection_volume` (`InjVolume`),
`signal_optics` (`UVASig`), `acquired` (`Date`).

## Open questions

- `UVASig` trailing flag semantics (assumed reference-enabled) unconfirmed.
- `MDT` canonical target (method-modified vs method-save) undecided; `CSlbk.ini`
  pairs it with checksums, suggesting a logbook entry time.
- `[TuneValues]` keys are not individually documented (numeric MS tune state).
