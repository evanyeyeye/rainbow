# Waters `_INLET.INF` / `inlet.inf` / `_extern.inf`

Reference for the human-readable method sidecars MassLynx writes into a Waters
`.raw` run directory. Parser: `rainbow/debug/waters_inf.py`. These sit alongside
`_HEADER.TXT` (see [`waters_header.md`](waters_header.md)) but carry a different
thing: the **method reference** the run was acquired with. Usually that is a
method file path (which inlet/MS method under which named MassLynx project,
`...\<project>.PRO\ACQUDB\...`); for the GC run-log `inlet.inf` it is instead a
bare method name. Either way it is per-instance identity.

rainbow's own Waters reader (`rainbow/waters/masslynx.py`) never opens any of
them. It reads `_HEADER.TXT` (calibration) and the numeric `_FUNCTNS.INF`
(function definitions); the method records here are untouched, so the method
reference they carry is identity the normal read path drops.

## Format

Line-oriented text. The encoding varies across instruments and is not knowable
up front, so the bytes go through the shared `rainbow/debug/_util.decode_text`
(ASCII, UTF-16, and the occasional short binary stub all decode without raising).

- **`_INLET.INF`** - an "ACE Experimental Record". The identity line is
  `Inlet Method File: <path>`; the rest is a per-module run-method dump (pump
  solvents and gradient table, autosampler, column, ...), overwhelmingly numeric
  instrument settings.
- **`inlet.inf`** (no leading underscore) - a GC run-log variant. The identity
  line is `Method File: <name>` (a bare method name, not a path), followed by GC
  inlet parameters (oven, injector, carrier, split). Example:

  ```
  GC Run Log
  Instrument: GCMS
  Method File: DEMO_METHOD_SLOW
  Last Saved : 11/10/2025 7:03:36 PM
  Total GC Run Time: 40.3 minutes
  ...
  ```
- **`_extern.inf`** (also matched as `extern.inf`) - begins
  `Parameters for <method path or label>`, followed by tune / data-processing
  parameters (often `Key<TAB>Value`). The "Parameters for" target is sometimes a
  full method path (`C:\MassLynx\PROJECT02.PRO\ACQUDB\MS_POS.EXP`) and sometimes a
  bare label (`Parameters for test`).

## Matching

The basenames `_INLET.INF`, `inlet.inf`, `_extern.inf`, and `extern.inf`
(case-insensitive). The leading underscore is sometimes dropped (the GC run-log
`inlet.inf` above), so both the underscored and bare spelling of each is claimed.
MassLynx also writes a parenthesized copy (`_extern(1).inf`, `_inlet(2).inf`)
when a `.raw` is re-acquired or re-processed in place; the trailing `(N)` is
stripped so the copy matches its base name and contributes the same method
reference.

Deliberately **not** matched:

- `_HEADER.TXT` - owned by `waters_header.py` (richer identity; different
  grammar).
- `_FUNCTNS.INF`, `_CHROMS.INF` - numeric/binary, no readable identity (and
  `_FUNCTNS.INF` is already read by `masslynx.py` for function definitions).
- `_HISTORY.INF` - a binary structure in the fixtures, not the textual
  processing log some MassLynx versions write; decoding it yields noise, so it is
  left alone rather than surfaced as garbage.

## What `parse` returns

The decoded non-blank lines, verbatim, under a `kind` tag (lossless for
`inspect`; the full parameter body is preserved even though `canonical` lifts
only the path):

```python
{'parser': 'waters_inf',
 'kind': 'inlet',                       # or 'extern'
 'lines': ['ACE Experimental Record',
           r'Inlet Method File: c:\masslynx\PROJECT01.pro\acqudb\screen_5min',
           '---------------------   Run method parameters   ----------------',
           '-- PUMP --',
           'Waters GI Pump',
           ...]}
```

## Depth decision

Surface the method path; leave everything else in the lossless `lines`. The
pump/gradient/tune parameters are per-run instrument *settings*, not
identifiers - the same "extract per-instance identifiers, skip non-identifying
instrument state" line drawn for `_HEADER.TXT` and the ChemStation parsers. They
remain fully visible in `inspect()`.

The path promotion is conservative: an `_extern.inf` target is taken as a method
only when it looks like a path (carries `\`, `/`, or `:`). A bare label such as
`Parameters for test` stays in `lines` and is not mis-promoted to `method`.

## Canonical mapping

See `rainbow/debug/waters_inf.py::canonical`.

| source line | canonical | notes |
|---|---|---|
| `_INLET.INF`: `Inlet Method File: <path>` | `method` | the LC/inlet method path |
| `inlet.inf`: `Method File: <name>` | `method` | the GC method name (bare, taken as-is) |
| `_extern.inf`: `Parameters for <path>` | `method` | the MS/tune method path; only when path-like |

`method` is a scalar field. When a run also has a `_HEADER.TXT` with an `MS
Method`/`Inlet Method`, that value wins the `fields()` merge (registry order, and
"first non-empty wins"), so the `_INLET.INF`/`_extern.inf` path may be *shadowed*
in the merged record - but it is always present in `inspect()`. In a method-only
context where `_HEADER.TXT` carries no method, these files become the sole
`method` source.

## Open questions / future depth

- `_INLET.INF` names instrument modules in prose (`Waters GI Pump`, `Waters
  ACQUITY QSM`); they are left in `lines`, not promoted to `devices`, because
  detecting them reliably across module vocabularies is brittle and they carry no
  serial.
- `_extern.inf` carries `Tune method name: <name>` (a label, not a path); no
  canonical home today, kept in `lines`.
- The method paths embed a MassLynx project tree (`...\<project>.PRO\ACQUDB\`)
  and can carry a project/user name; like the Agilent path handling, the embedded
  names are left inside the path, not split out.
