.. _asm-the-standard:

The standard, and how we check it
=================================

Where ASM comes from
--------------------

The **Allotrope Simple Model** (ASM) is published by the `Allotrope Foundation
<https://www.allotrope.org/>`_, a consortium of pharmaceutical and biotech
organizations building open, vendor-neutral formats for analytical data. ASM is
the JSON-based, human-readable layer of that work. It rests on two things the
Foundation also maintains:

- **Allotrope Data Models (ADMs).** One model per technique: a JSON schema that
  says what a valid document for that technique looks like. rainbow targets the
  **liquid chromatography** ADM.
- **The Allotrope Foundation Ontology (AFO).** A controlled vocabulary of terms,
  each with a stable accession (for example ``absorbance`` is ``AFR_0001157``,
  ``pump`` is ``AFE_0000499``). Where a document names a measured quantity or a
  device, it names an AFO class, not free text.

A unit is the third leg: quantities carry **QUDT** units (``nm``, ``s``,
``mAU``), so a value is never ambiguous about its scale.

What rainbow declares
---------------------

Every document rainbow emits opens with a manifest that pins the exact schema
version it conforms to. A liquid-chromatography run declares:

.. code-block:: json

   {
     "$asm.manifest": "http://purl.allotrope.org/manifests/liquid-chromatography/REC/2026/03/liquid-chromatography.manifest",
     "liquid chromatography aggregate document": { "...": "..." }
   }

and a gas-chromatography run (any run with an FID channel) declares the
gas-chromatography manifest instead. The corresponding schemas, the ones this
output is meant to validate against, are the published ADMs at ``REC/2026/03``:

   http://purl.allotrope.org/json-schemas/adm/liquid-chromatography/REC/2026/03/

   http://purl.allotrope.org/json-schemas/adm/gas-chromatography/REC/2026/03/

``REC`` is the maturity stage (a recommendation), and ``2026/03`` is the
release. rainbow targets ``2026/03`` because, unlike the earlier ``2023/09``,
its gas-chromatography ADM carries the FID, MS, and UV cubes together, so a
gas-chromatography run exports losslessly. The manifests and the target schema
URLs all live in :code:`rainbow/asm.py`, so there is a single place that says
which version of the standard a document claims to be.

Licensing
---------

The Allotrope schemas and ontology are published by the Foundation under
Creative Commons terms (the schemas as CC-BY-NC, the ontology as CC-BY). rainbow
**references** the schema by its URI; it does not bundle, vendor, or modify the
schema files. To validate against them you fetch them yourself from
``purl.allotrope.org`` (the conformance tests below do exactly that, then cache
the result locally). Nothing under a no-derivatives or non-commercial term is
copied into this repository.

How conformance is checked
--------------------------

A document can be well-formed JSON and still be wrong: a misspelled term, a unit
the schema does not allow, a required field left out. rainbow guards against that
with two opt-in tests. They are opt-in because they reach the network (to fetch
the schema and to query the ontology), so they do not run in ordinary CI; you
turn them on with one environment variable.

.. code-block:: bash

   pip install -e .[validate]
   RAINBOW_TEST_ASM_SCHEMA=1 pytest tests/test_asm_schema.py tests/test_asm_ontology.py

**Schema conformance** (:code:`tests/test_asm_schema.py`). Validates emitted
documents against the published JSON schemas with ``jsonschema``. It checks the
official Allotrope ``REC/2026/03`` liquid- and gas-chromatography schemas the
manifests declare, across an Agilent ``.dx``, a Waters ``.raw``, a metadata-rich
LC envelope (instrument, injection, peaks), and gas-chromatography runs (an FID
chromatogram and a GC-MS run). This catches a wrong structure, a missing
required field, or a disallowed unit, such as emitting absorbance in ``AU``
where the schema pins ``mAU``.

**Ontology conformance** (:code:`tests/test_asm_ontology.py`). The schema leaves
the controlled-vocabulary fields (a cube's ``concept``, a device's ``device
type``) free-form, so a made-up label would pass schema validation. This test
collects every such term rainbow emits and confirms each is a real AFO class by
querying the EBI Ontology Lookup Service. It is the layer that stops a typo or an
invented term.

Validating your own document
----------------------------

Conformance is not limited to the test suite. Any document rainbow writes can be
checked against the published schema with the same tooling:

.. code-block:: python

   import json, urllib.request
   from jsonschema import Draft202012Validator

   import rainbow as rb

   document = rb.read("caffeine.dx").to_asm()

   url = ("http://purl.allotrope.org/json-schemas/adm/liquid-chromatography/"
          "REC/2026/03/liquid-chromatography.tabular.embed.schema.json")
   schema = json.load(urllib.request.urlopen(url))

   errors = list(Draft202012Validator(schema).iter_errors(document))
   assert not errors, errors

The ``.tabular.embed`` schema is self-contained (it resolves its own internal
references), so it is the simplest validation target: no registry of supporting
files is needed. A gas-chromatography run validates the same way against the
``gas-chromatography`` schema at the same revision.
