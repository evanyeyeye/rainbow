# ChemStation `.ch` / `.uv` / `.ms` binary headers

Reference for the text fields in the **headers** of ChemStation binary data
files. Parser: `rainbow/debug/chemstation_header.py`.

These are the same `.ch` (FID/CAD/ELSD/UV channel), `.uv` (UV spectra), and
`.ms` (MS/SIM) files rainbow's data parsers read for their signal arrays
(`rainbow/agilent/chemstation.py`). rainbow already lifts a few header strings
into `DataFile.metadata` (notebook, date, method, instrument, unit, signal,
vialpos). This module exists for the identifiers it does **not** surface -
chiefly the **operator** and the acquisition **workstation** name - plus the
technique and file-type markers. It reads only the header window
(`_HEADER_BYTES = 0x1900`), never the - potentially multi-megabyte - data block.

## How the header is laid out

A version marker at offset 0 selects the layout:

- `.ch` / `.uv`: a length-prefixed version string (`130`, `179`, `181`, `131`,
  and the legacy `30`, `31`).
- `.ms`: the 4-byte magic `0x01320000` (no version string).

Every header string is length-prefixed: a one-byte length `N`, then `N`
characters at stride `gap`. `gap` is **1** for the legacy DOS-ChemStation layout
(`30`/`31`/`.ms`) and **2** for the newer layout (`130`/`131`/`179`/`181`), where
each character is followed by a `0x00`. The reader returns None for an empty or
unreadable slot, so a header missing a given field simply omits it.

If the version marker is unrecognized (e.g. a MassHunter `.ms` with no
`0x01320000` magic, or a MassHunter `acq.ms`), `parse` returns
`head: None, fields: {}` and contributes nothing - it never guesses.

## Offset tables

`parse` returns `{'parser', 'ext', 'head', 'gap', 'fields': {name: value}}`.
`fields` carries every header string found. The tables (in the parser) mirror
`chemstation.py` and add the dropped fields.

### Newer layout, `gap = 2`

| field | `.ch` 130/179/181 | `.uv` 131 | notes |
|---|---|---|---|
| `data_marker` | `0x15B` | `0x15B` | technique banner, e.g. `LC DATA FILE` / `GC DATA FILE` |
| `notebook` | `0x35A` | `0x35A` | free-text notebook/sample tag |
| `operator` | `0x758` | `0x758` | **dropped by rainbow** |
| `date` | `0x957` | `0x957` | acquisition timestamp |
| `file_type` | `0x9E5` | `0x9E5` | `LC` / `GC` / `OL` |
| `method` | `0xA0E` | `0xA0E` | method file name |
| `workstation` | `0xC11` | - | PC name + ` ChemStation`, **dropped by rainbow** |
| `unit` | `0x104C` | `0xC15` | signal unit (`mAU`, `pA`) |
| `signal` | `0x1075` | `0xC40` | detector signal descriptor |
| `vialpos` | - | `0xFD7` | vial position |

(`181` is FID double-delta and has no `signal` slot.)

### Legacy layout, `gap = 1`

| field | `.ch` 30 | `.uv` 31 | `.ms` (magic) |
|---|---|---|---|
| `data_marker` | `0x4` | `0x4` | `0x4` (e.g. `MSD Spectral File`) |
| `notebook` | `0x18` | `0x18` | - |
| `operator` | `0x94` | `0x94` | `0x94` **(dropped by rainbow)** |
| `inlet` | - | - | `0xD0` (instrument id, e.g. `LCMS_<n>`) |
| `date` | `0xB2` | `0xB2` | `0xB2` |
| `file_type` | `0xDA` | `0xDA` | `0xDA` |
| `method` | `0xE4` | `0xE4` | `0xE4` |
| `workstation` | `0x142` | - | - |
| `unit` | `0x244` | `0x146` | - |
| `signal` | `0x254` | - | - |

Note a quirk worth recording: rainbow's own head-`30` offset table labels
`0xDA` "instrument", but `0xDA` actually holds the `LC`/`GC` **file-type** token;
the real workstation name sits at `0x142`. This parser labels them correctly
(`file_type` and `workstation`).

## Canonical mapping

| header field | canonical | notes |
|---|---|---|
| `operator` | `operator` | the headline addition |
| `method` | `method` | method file name |
| `date` | `acquired` | timestamp format varies by layout |
| `vialpos` | `vialpos` | `.uv` 131 only |
| `workstation` | `computers` (list) | the `<host> ChemStation` workstation name |
| `inlet` | `instrument` (scalar) | `.ms` instrument id |
| `signal` | `signal_optics` (list) | detector signal descriptor |

`data_marker`, `file_type`, `notebook`, and `unit` are kept in `fields` for
context but not promoted - they are technique/format markers, not identifiers.

The `workstation` value (`<host> ChemStation`) and an XML audit-trail
`ComputerName` (a bare host like a lab PC tag) both land in `computers`; they
share the meaning "acquisition workstation" even though one carries the trailing
` ChemStation`. This mixing is intentional and documented here.

## Open questions / future depth

- `notebook` (`0x35A` / `0x18`) often holds a short sample/notebook tag. It is
  left in `fields` but not promoted, because its meaning is inconsistent across
  sites (sometimes a sample name, sometimes a batch label). Promote to `sample`
  only if a clear convention emerges.
- `acquired` here is the per-file header timestamp; it may differ in format from
  the INI/XML `acquired`. The merge takes the first non-empty value, so the
  winning source depends on file ordering. All are valid acquisition times.
- MassHunter `.ms` variants (no `0x01320000` magic) and `acq.ms` carry no
  length-prefixed header strings in this window, so they yield nothing here;
  their metadata lives in the AcqData XML/INI sidecars instead.
- The data-file path and any embedded account/person names are not present in
  these headers (unlike the `acq.txt` reports); the header carries only the
  method file **name**, not its full path.
