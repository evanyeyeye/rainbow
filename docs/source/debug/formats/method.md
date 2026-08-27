# ChemStation / MassHunter method and macro files

Reference for the method and macro files in a `.M` method directory: `.mth`,
`.e`, `.p`, `.val`, `.mac`. Parser: `rainbow/debug/method.py`.

## The family

Heterogeneous, in three shapes:

- **Macro / script** (most `.mac`, `.e`, `.p`, `.val`, and some `.mth`): a small
  command script, `NAME <macroname>` then indented `KEYWORD args` or
  `KEY$ = "value"` lines. ASCII, UTF-8-BOM, or UTF-16 (the shared
  `rainbow/debug/_util.decode_text` handles the encoding).
- **INI-style `.mth`** (e.g. `smpl_pur.mth`): `[Section]` / `key=value`, like the
  INI sidecars but with a `.mth` extension.
- **Binary `.mth`** (e.g. `qdb.mth`): a numeric method database, no text.

## Depth decision: extract identifiers, skip the templates

Across every method/macro fixture, the content is overwhelmingly **invariant
method-template** material - integration parameters, event tables, quant
settings, macro command bodies. It is the same from run to run and carries no
acquisition identity, so per the subsystem rule it is not surfaced (it is exactly
the "format internals that do not change meaningfully between instances").

A survey of all 35 method/macro fixtures finds **one** identifier-bearing value:
a `LastDataFile` macro that records the last processed data file as quoted
values, e.g.

```
Name LastDataFile
  LastDataPath$ = "D:\MassHunter\Data\<batch folder>\"
  LastDataFile$ = "<sample>.d"
  LastDataSize  = 3495420
```

So `parse` classifies the file and extracts only the **path / data-file
references** from its quoted values - it does not dump the script body:

```
{'parser': 'method', 'kind': 'macro' | 'ini' | 'binary', 'paths': [...]}
```

`paths` keeps quoted values that look like a filesystem path (a drive `X:\`, a
UNC `\\`) or a data/method file name (`.d`/`.m`). Binary `.mth` files yield no
paths.

## Canonical mapping

| source | canonical |
|---|---|
| a quoted `.d` path, or a drive directory joined with a `.d` file name | `data_file` |

`canonical` joins the `LastDataPath$` directory with the `LastDataFile$` name into
the full `data_file` path. Files with no path references - the vast majority -
contribute nothing.

## Open questions / future depth

- The macro `NAME` and the method-parameter bodies are intentionally not
  surfaced; they are invariant template content. If a specific method parameter
  is ever wanted, the macro/INI body is structured enough to extract on demand.
- INI-style `.mth` files share the INI grammar but are not routed through
  `ini.py` (which matches only `.ini`); if their sections ever prove to carry
  identifiers, either extension this parser or broaden the INI matcher.
- Binary `.mth` databases (e.g. `qdb.mth`) are left unparsed beyond the `binary`
  classification; they are numeric method tables with no observed identifiers.
