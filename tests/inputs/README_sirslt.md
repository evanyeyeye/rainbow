# OpenLab CDS `.sirslt` test folders

Three real single-injection result folders from Agilent OpenLab CDS 2.x, kept
for the `.sirslt` reader's tests (`tests/test_sirslt.py`, and `lime` in
`tests/test_agilent.py`).

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
