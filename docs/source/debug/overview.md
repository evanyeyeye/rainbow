# Debug metadata subsystem

Start here for the design and the two entry points, then see
[`formats.md`](formats.md) for the at-a-glance catalog and canonical-field
table, and `formats/<name>.md` for the deep reverse-engineering reference on each
format.

## Why

rainbow's normal read path surfaces a deliberately lean set of metadata to keep
overhead low. But a vendor run directory ships many sidecar files that rainbow's
data parsers never touch - registers, INIs, audit trails, method dumps, manifest
XML - and those carry the real acquisition context: instrument module serials,
firmware/software versions, the operator, method-save details, injection volume,
signal optics, vial position, timestamps, and more.

The debug subsystem decodes those sidecars into **structured fields on demand**,
without adding any cost to the default read path. The goal is to parse as much of
each format into typed fields as the format allows - not to dump piles of text.

## API

```python
from rainbow import debug

debug.inspect(path)   # {relpath: structured metadata}  - faithful, per file
debug.fields(path)    # one merged canonical run-metadata record
```

- `inspect` returns each recognized sidecar's **full, lossless** structure
  (every section/key/element), keyed by path relative to the run.
- `fields` merges the recognized sidecars into **one canonical record** using
  the shared field vocabulary below, with a `_sources` map recording which
  file supplied each value.

Read-only. Nothing is ever written back. A sidecar that fails to parse is
reported (`{'parser': ..., 'error': ...}` in `inspect`) rather than aborting the
run or being silently dropped. Either entry point accepts a run directory, a
single sidecar file, or an Agilent `.dx` archive (which is descended into,
treating each member like a file in a sub-directory); anything else raises.

### A worked example

`fields` gives you the merged run record. Scalars are single values; list fields
(`serials`, `devices`, `users`, `computers`, `signal_optics`) accumulate across
files. `_sources` records where each value came from - a single relpath for a
scalar, a list of relpaths for a list field (synthetic values shown):

```python
>>> from rainbow import debug
>>> debug.fields("example.D")
{
    'operator': 'labuser',
    'method': r'C:\Chem32\1\METHODS\GENERIC.M',
    'acquired': '2024-03-11T09:42:17',
    'serials': ['DEAA900001', 'DEAA900002'],
    'signal_optics': ['DAD1 A, Sig=254,4 Ref=360,100'],
    '_sources': {
        'operator': 'acq.txt',
        'method': 'SAMPLE.XML',
        'acquired': 'SAMPLE.XML',
        'serials': ['RUN.LOG', 'RUN.LOG'],
        'signal_optics': ['DAD1.UV'],
    },
}
```

`inspect` keeps every recognized sidecar's full structure, keyed by relpath, so
you can see the lossless half the canonical record was projected from:

```python
>>> debug.inspect("example.D")["SAMPLE.XML"]
{'parser': 'xml', 'root': 'Sample', 'namespace': '',
 'tree': {'Name': 'sample-07', 'Amount': '1', 'Dilution': '1',
          'ACQMethodPath': r'C:\Chem32\1\METHODS\GENERIC.M', ...}}
```

Every parser's `parse` output carries a `'parser'` tag and then its own
lossless structure; the `canonical` step is what lifts the well-known keys
(here `Name` and `ACQMethodPath`) into the shared `sample` / `method` vocabulary
seen in the `fields` record above. Reach for `inspect` when you need a key the
canonical vocabulary does not (yet) promote.

## Architecture

Each format is a parser module under `rainbow/debug/` exposing three callables:

| callable | contract |
|---|---|
| `matches(name)` | True if this module handles a file named `name`. |
| `parse(path)` | Full, lossless structure as a dict (`{'parser': NAME, ...}`). |
| `canonical(parsed)` | The well-known keys promoted to canonical field names; keys not present are omitted. |

`rainbow/debug/__init__.py` holds the parser registry, the file walker, the
dispatcher, and the merge policy. The merge policy:

- **List fields** (`_LIST_FIELDS`, e.g. `serials`, `signal_optics`) accumulate
  unique values across all files in the run.
- **Scalar fields** take the first non-empty value seen.
- Every merged value's origin is recorded in `_sources`.

Files are walked in sorted relpath order (`_iter_files`), so "first non-empty"
for a scalar is deterministic but order-dependent: when two sidecars disagree on,
say, `acquired`, the one earlier in sorted order wins. `inspect` shows every
contributor if you need to see the conflict.

Adding a format = add a module + register it. No other code changes.

## Canonical field vocabulary

The shared field names grow as formats are added. The authoritative table
(field, type, meaning, source) lives in
[`formats.md`](formats.md#canonical-field-vocabulary) - that page is the single
source of truth, kept in sync with what the `canonical` functions emit. It spans
identity (`operator`, `sample`, `vialpos`), instrument (`serials`, `devices`,
`instrument`), and provenance (`method`, `data_file`, `acquired`) fields. The
list-valued fields - `serials`, `devices`, `computers`, `users`, `signal_optics`
- accumulate across files; every other field is a scalar that takes the first
non-empty value.

## Cost, and what to expect of it

Nothing here runs on the normal read path. `rainbow.debug` is imported on first
use, so a program that never calls it does not pay to have it installed, and
`rb.read` and `rb.read_metadata` surface the same lean metadata they always did.

It does need `lxml`, which is a default dependency but is otherwise optional for
reading: recovering structure from malformed and mis-encoded sidecars is exactly
what a recovering parser is for, so this subsystem requires it outright.

Two entry points are the stable surface. The canonical vocabulary grows as
formats are added, so treat a field's absence as "not promoted yet" rather than
"not in the file", and reach for `inspect` when you need a key `fields` does not
carry.

```{toctree}
:hidden:
:titlesonly:

formats
formats/chemstation_header
formats/chemstation_text
formats/dotnet
formats/ini
formats/method
formats/mzxml
formats/reg
formats/waters_header
formats/waters_inf
formats/xml
```
