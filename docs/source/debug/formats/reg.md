# ChemStation `.REG` register files (MFC CArchive)

Reference for the ChemStation `.REG` register files. Parser:
`rainbow/debug/reg.py`. This is a **best-effort** parser at the
readable-complete ceiling - see the depth note below.

Examples in the fixtures: `ACQRES.REG`, `LCDIAG.REG`, `MSDIAG.REG`,
`DiagResults.REG`, `MSACQINF.REG`, `DAMETHOD.REG`, and the per-module method
registers (`LPMP1.REG`, `LDAD1.REG`, `LWLS1.REG`, `LTHM1.REG`, `FIA.REG`).

## Format

A `.REG` is an **MFC `CArchive`** stream (the binary serialization format the
Microsoft Foundation Classes C++ library writes objects to):

```
02  '32'  00  0D 'REGISTER FILE'  ... 07 'notused' ...  <serialized CHP* objects>
```

- byte `0x02` then a 2-char CArchive version tag (`32`),
- the `REGISTER FILE` magic (a 1-byte-length-prefixed string),
- then a tree of serialized `CHP*` objects. MFC writes each object's class once
  with a new-class tag and a 2-byte-length-prefixed class name
  (`CHPUserObject`, `CHPList`, `CHPTable`, `CHPNdrDouble`, `CHPNdrString`,
  `CHPNdrObject`, `CObArray`, and in diagnostic files `CHPDatDoubleRow`,
  `CHPDatDoubleSliced`, `CHPAnnText`), and references it thereafter by index.

## What `parse` returns

```
{'parser': 'reg', 'format': 'mfc-carchive', 'magic': 'REGISTER FILE',
 'version': '32', 'record_types': {class_name: count}}
```

`record_types` is the structural inventory: which `CHP*` object classes the
archive contains and how many of each. It is a compact fingerprint of what kind
of register file this is - e.g. a method module register holds one of each NDR
type, while `lcdiag.reg` holds a dozen `CHPNdrDouble` plus several
`CHPDatDoubleRow`/`CHPDatDoubleSliced` diagnostic tables. A file without the
magic returns `format: None`.

## Depth decision: the proprietary ceiling

The `CHP*` record layouts are Agilent-proprietary and were never published, and
their payloads are **numeric** instrument register values (calibration,
diagnostics, module configuration). Two reasons this parser stops at the
structural inventory:

1. **Proprietary.** Without the published `CHP*` layouts, decoding the payloads
   reliably is not possible - only a brittle guess.
2. **No identifiers, and numeric anyway.** An exhaustive survey of every `.REG`
   fixture (20 files) finds no operator, method, sample, or path identifier in
   them; the payloads are register numbers, which the subsystem does not mine.

So `canonical` returns `{}`. The parser still exists so the format is
**recognized** (its inventory is reported, not silently skipped) and its ceiling
is documented here rather than rediscovered each time.

## Canonical mapping

None. `.REG` files contribute nothing to the merged `fields()` record.

## Open questions / future depth

- Decoding the `CHP*` payloads would require the proprietary record layouts. If
  they are ever reverse-engineered, the per-record numeric values could be
  surfaced - but they are instrument register data, not run identity, so the
  value would be low for this subsystem.
- The `CHPNdrString` records can in principle hold text; in the fixtures they
  carry no identifier strings, but if a future file does, that record type is
  where to look.
