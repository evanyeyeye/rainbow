# Waters `_HEADER.TXT`

Reference for the metadata header MassLynx writes into every Waters `.raw` run
directory. Parser: `rainbow/debug/waters_header.py`. This is the only structured
metadata file in a `.raw`: the Agilent sidecars the other debug parsers read
(INI, XML, ChemStation text, `.REG`, ...) never appear there, so without this
parser `fields()` returns nothing for a Waters run.

rainbow's own Waters reader (`rainbow/waters/masslynx.py`) opens `_HEADER.TXT`
but only to recover the m/z calibration coefficients (the `$$ Cal MS1 ...`
lines); it ignores every identity field below.

## Format

Flat line-oriented text, ASCII with CRLF line endings. Every content line is

```
$$ Key: Value
```

A leading `$$ ` marker, a key, a colon, then the value (which may be empty).
Keys are fixed MassLynx labels and appear in a stable order; the file is a flat
namespace, not sectioned. There is no encoding ambiguity in the fixtures (plain
ASCII), but the parser still decodes through the shared
`rainbow/debug/_util.decode_text` so a UTF-16 export would not break it.

The same key set appears across instruments (SQD, QDA, SCN/ScanWave); values
differ. Besides the identity fields below, the file carries large blocks of
acquisition state that are **not** promoted: `$$ Cal MS1/MS2 ...` calibration
coefficients (numeric, and already read by `masslynx.py` for its own use),
`$$ Analog Channel N Offset`, `$$ Spare1..5`, `$$ Mux Stream`, tune/solvent
parameters. These are instrument state, not per-instance identifiers.

## Matching

Exactly the basename `_HEADER.TXT` (case-insensitive). It is **not** matched by
the ChemStation text parser, whose `.txt` set is a fixed list of Agilent report
names; `_HEADER.TXT` is a different vendor and a different grammar.

## What `parse` returns

The lossless flat key/value map under a `'parser'` tag. Every `$$` line is
preserved verbatim, including blank values (synthetic example):

```python
{'parser': 'waters_header',
 'header': {'Version': '01.00',
            'Acquired Name': 'sample_p1_07',
            'Acquired Date': '26-Jan-2024',
            'Acquired Time': '00:11:45',
            'Job Code': 'screening-p1',
            'User Name': '',
            'Instrument': 'ACQ-SQD2#XXX0000',
            'Sample Description': 'sample_p1_07',
            'SampleID': 'sample_p1_07',
            'Bottle Number': '4:G,2',
            'Inlet Method': r'C:\MassLynx\Default.PRO\ACQUDB\8min_polar',
            'MS Method': r'C:\MassLynx\Default.PRO\ACQUDB\8min.EXP',
            ...}}
```

The key is split on the **first** `:` only, so a clock value (`00:11:45`) or a
Windows path (`C:\MassLynx\...`) in the value survives intact.

## Depth decision

Surface the per-instance identifiers; leave the acquisition-state blocks in the
lossless `parse()` view but do not promote them. The calibration/analog/tune
lines are numeric instrument state that changes every run without identifying
anything, the same "skip invariant or non-identifying internals" line the
Agilent parsers draw. Everything is still present in `inspect()` for anyone who
wants it.

## Canonical mapping

See `rainbow/debug/waters_header.py::canonical`.

| `$$` key | canonical | notes |
|---|---|---|
| `Instrument` (model before `#`) | `instrument` | `ACQ-SQD2#XXX0000` -> model `ACQ-SQD2` |
| `Instrument` (serial after `#`) | `serials` (list) | `-> XXX0000`; the placeholder `#NotSet` (e.g. `ACQ-QDA#NotSet`) is treated as absent |
| `Acquired Date` + `Acquired Time` | `acquired` | joined with a space; either may be blank |
| `Acquired Name` | `data_file` | the run/data-file basename (mirrors the Agilent data_file) |
| `Sample Description` | `sample` | the human sample label |
| `SampleID` | `sample_id` | |
| `User Name` | `operator` | frequently blank in the fixtures; emitted only when present |
| `Bottle Number` | `vialpos` | e.g. `4:G,2`, `1:2` |
| `MS Method` else `Inlet Method` | `method` | full Windows path; MS method preferred |

Blank values are omitted, so `fields()`' "first non-empty wins" merge is not
polluted by the keys MassLynx leaves empty (`User Name`, `Submitter`,
`Conditions`, ...).

## Open questions / future depth

- `Bottle Number` encodes plate:position (`4:G,2`); the sub-syntax is not parsed
  into structured plate/row/column, kept verbatim like the Agilent `vialpos`.
- `Job Code`, `Submitter`, `Laboratory Name`, `Task Code`, `Conditions` are
  per-instance but have no canonical home in the current vocabulary; they stay in
  the lossless `parse()` view. Promote if a Waters-oriented field set is added.
- `Inlet/MS/Tune Method` paths embed a MassLynx project tree (`...PRO\ACQUDB\`)
  and sometimes a user/project name; like the Agilent path handling, the
  embedded names are left inside the path, not split out.
- The numeric `$$ Cal ...` blocks are calibration, already consumed by
  `masslynx.py`; not surfaced here to avoid duplicating that responsibility.
