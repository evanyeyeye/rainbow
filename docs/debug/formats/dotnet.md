# .NET BinaryFormatter (MS-NRBF) sidecars

Reference for the .NET `BinaryFormatter` serialized files an Agilent run can
ship - in these fixtures, `Results/Qual/Version3/QualResult.bin`, the MassHunter
Qualitative-analysis result/settings object graph. Parser:
`rainbow/debug/dotnet.py`.

## Format

The stream is **MS-NRBF** (`[MS-NRBF]`, the .NET Remoting Binary Format): a
self-describing object graph where a one-byte record type tags each record and
strings are length-prefixed with a **7-bit-varint** length followed by UTF-8
bytes. It opens with a `SerializationHeaderRecord`: byte `0x00`, then four
little-endian int32s (RootId, HeaderId, MajorVersion = 1, MinorVersion, which is
typically 0; the parser accepts 0 or 1).

`parse` validates that header (`_is_nrbf`) from the first 17 bytes before reading
the rest, so a non-NRBF `.bin` costs nothing.

## Matching

`matches` claims `.bin` files **except** the MassHunter `MS*.bin` numeric data
files (`MSScan.bin`, `MSProfile.bin`, `MSPeak.bin`, `MSMassCal.bin`,
`MSScan_XSpecific.bin`), which are signal data, not serialized objects. Any other
`.bin` that is not actually NRBF (e.g. `7890Method.bin`, which is UTF-16 XML)
fails the header check and contributes nothing.

## Depth decision: summary, not full graph

A faithful MS-NRBF object-graph reconstruction needs the full record grammar -
class metadata, member-type tables, primitive and array value decoding - several
hundred lines. For `QualResult.bin` that work would surface, on top of the few
identifiers, the serialization **internals**: ~1000 .NET member names (`m_value`,
`m_displayName`, `m_scaleFactor`, ...) and ~200 generic type constructions
(`Dictionary\`2[[...]]`). Those are format boilerplate - identical between
instances - and carry no acquisition identity. The subsystem's rule is to surface
structured identifiers, not piles of invariant internals, so this parser does
**not** reconstruct the graph.

Instead it validates the header and walks the length-prefixed **string table**,
then returns a bounded summary:

```
{
  'parser': 'dotnet',
  'format': 'ms-nrbf',
  'header': {'root_id', 'major_version', 'minor_version'},
  'assemblies': [ ... ],     # the .NET assembly identities (the software stack)
  'paths':      [ ... ],     # file-path value strings (the identifiers)
  'string_count': N,         # total strings seen, so inspect can report the
                             #   table size honestly without dumping it
}
```

- **`assemblies`** keeps only **bare assembly identities** -
  `Name, Version=..., Culture=..., PublicKeyToken=...` - anchored and
  bracket-free, so the generic type constructions that merely embed an assembly
  reference are excluded. These vary per install and pin the **software version**
  that produced the file (e.g. the MassHunter `QualAppLogic` / `CoreDefinitions`
  build, `System.Drawing`, `mscorlib`).
- **`paths`** keeps strings that look like filesystem paths (a drive `X:\`, a UNC
  `\\`, or a ChemStation template root like `#CUSTOMERHOME#`). This is where the
  identifiers are: the analyzed data-file path and any database/library paths.

The string-table walk is a scan over the format's own length-prefix convention
(not a full record walk), validating every candidate strictly and jumping past
accepted strings. The NRBF string framing is distinctive enough that this
recovers the table cleanly; it was verified against the known content of
`QualResult.bin`.

## Canonical mapping

| source | canonical |
|---|---|
| a `paths` entry that is an absolute path ending in a `.d` run directory | `data_file` |

`canonical` promotes only `data_file` - the analyzed run, e.g.
`D:\MassHunter\Data\<sample>.d`. The assembly versions are kept in `parse` for
context but **not** promoted to `software_version`: they describe the
data-analysis tool stack, a different notion from the acquisition software
version that the INI/ACAML sources report.

## Open questions / future depth

- `software_version` from the Qual assembly stack is deliberately not promoted
  (it is an analysis-tool version, not the acquisition version). Revisit if a
  distinct "analysis software" field is ever wanted.
- Database / library paths (e.g. a PCDL `.csv`) are surfaced in `paths` but not
  canonicalized; they are configuration, not run identity.
- If a future file needs actual graph values (named result records, per-compound
  hits), that is when a full MS-NRBF record parser would be justified; the string
  table alone does not preserve the object structure.
