# JSON-LD → Phenopacket Transformer Rewrite Plan

## Background

This branch (`data-transformation-script`) processes individual ClinGen GCI JSON-LD files
(one per gene-disease curation) and converts proband data into GA4GH Phenopackets v2.

The other branch (`gci-to-phenopacket-2026-03-cc`) works from a different input format
(a single JSONL snapshot file) so its transformer cannot be directly reused here.

---

## Problem with the Current Code

`data_transformer.py` uses `pyld.jsonld.frame(doc, PROBAND_FRAME)` to extract probands.
This returns an empty graph (`@graph: []`) on all files because:

- `pyld.jsonld.frame()` operates on a flat graph internally, but the Proband nodes are
  **deeply nested** inside `evidence` arrays (3–4 levels deep)
- Framing was tested with the correct context from `config.py` and also with the
  document's own `@context` — both return 0 results
- This is a pyld limitation, not a context mismatch

**Root cause confirmed by:** expanding the document shows
`https://genegraph.clinicalgenome.org/terms/Proband` exists, but `frame()` cannot find it.

---

## What the Data Looks Like

Each JSON-LD file is an `EvidenceStrengthAssertion` with:

```
EvidenceStrengthAssertion
  subject → GeneValidityProposition
              disease: "obo:MONDO_0007606"
              gene: "hgnc:171"
  evidence[] → EvidenceLine
                 evidence[] → EvidenceLine
                                evidence[] → VariantObservation   ← zygosity + allele ref
                                             Proband              ← deeply nested
                                               phenotypes: ["obo:HP_XXXXXXX", ...]
                                               variant: { id: "..." }  ← reference only
                                               sex: "Female"
                                               dc:source: "https://pubmed.ncbi.nlm.nih.gov/PMID"
```

Key finding: `pyld.jsonld.flatten(doc, ctx)` produces a flat list of 77 nodes
with all types present. An ID index built from this lets us resolve all references:

- `proband.variant.id` → `VariantObservation` node (has `zygosity`, `allele`)
- `variantObservation.allele.id` → `VariationDescriptor` node (has `skos:prefLabel`, `CanonicalReference`)

---

## Fix: Replace frame() with flatten() + ID Index

```python
flattened = pyld.jsonld.flatten(doc, ctx)
graph = flattened.get('@graph', [])
index = {n['id']: n for n in graph if 'id' in n}
```

Then resolve references via `index.get(ref['id'])`.

---

## Planned Changes (File by File)

### `src/data_transformer.py` — Major rewrite

- Replace `pyld.jsonld.frame()` with `pyld.jsonld.flatten()` + ID index
- Add `_build_index(graph)` and `_resolve(index, ref_dict)` helpers
- Extract `GeneValidityProposition` from flat graph → get `gene` (HGNC ID) and `pmid`
- **Filter probands**: skip any proband where `phenotypes` is empty or missing
- Resolve variant chain:
  - `proband.variant` → `VariantObservation` → get `zygosity` (e.g., `cg:Heterozygous`)
  - `variantObservation.allele` → `VariationDescriptor` → get:
    - CAR ID from `https://terms.ga4gh.org/CanonicalReference.id` (strip to `CA128036`)
    - Label from `http://www.w3.org/2004/02/skos/core#prefLabel`
  - Only hit `http://reg.genome.network/allele/{CAID}` API if **both** CAR ID and label are missing
- Build variant with: `caid:{CAR_ID}` as ID, skos label as label, allelic_state from zygosity, gene_context from HGNC
- **Disease**: always hardcode `MONDO:0700096 / human disease` (do not resolve from proposition)
- Return `(gene_symbol, pmid, proband_label, phenopacket)` tuple

### `src/utils/ontologies.py` — Add HGNC

- Download HGNC complete dataset as TSV (bulk download URL), cache locally
- Build `{hgnc_numeric_id: symbol}` lookup dict
- Add `hgnc_to_symbol(hgnc_id: str) -> str` — strips `hgnc:` prefix, looks up in dict
- Returns `UNKNOWN` with a warning if not found

### `src/main.py` — Update output naming

- Update output filename to:
  `{file_stem}_{gene_symbol}_{mondo_id}_{pmid}_{proband_label}.json`
  e.g., `gg_3e60939f_ACVR1_MONDO_0700096_16642017_A_II_I.json`
- Unpack new tuple from `transform_file`

### `src/config.py` — Cleanup

- Remove `PROBAND_FRAME` (no longer used)
- Keep `RESOURCE_METADATA`
- Add ECO resource entry (was missing, needed for evidence construction)

---

## Proband Filter Rule

A proband is only converted to a phenopacket if:
- `phenotypes` field exists AND has at least one entry

Probands without phenotypes are logged at DEBUG level and counted in the summary.

---

## Output Filename Convention

`{file_stem}_{gene_symbol}_{disease_id}_{pmid}_{proband_label_sanitized}.json`

- `gene_symbol`: from HGNC lookup of `GeneValidityProposition.gene`
- `disease_id`: always `MONDO_0700096`
- `pmid`: extracted from `dc:source` URL
- `proband_label`: `rdfs:label` with spaces/special chars replaced by `_`

---

## What We Are NOT Doing (Scope Decisions)

- Not resolving disease from `GeneValidityProposition` — always use `MONDO:0700096 / human disease`
- Not supporting the CC branch's JSONL snapshot input format
- Not adding tests yet (separate task)

---

## Future Work / To Discuss

### PubMed API — Batch Fetching

**Current state:** One HTTP call per PMID cache miss, with a `0.4s` sleep to stay under
NCBI's 3 req/sec rate limit (no API key). This is safe but slow at scale.

**Proposed improvement:** NCBI esummary supports multiple PMIDs in a single request:
```
?db=pubmed&id=12345,67890,11111&retmode=json
```

**Approach (single-pass, no double iteration):**
1. During the existing graph iteration, collect valid proband nodes + unique PMIDs into a list
   (this replaces the current per-proband fetch)
2. After the loop, batch-fetch all uncached PMIDs in one API call (or in chunks of ~200)
3. Populate the in-memory cache
4. Iterate the collected proband list (already filtered — much smaller than the full graph)
   and build phenopackets using now-cached titles

This avoids iterating the full graph twice — the second pass is only over the
already-filtered proband list, not the raw graph.

**Pros:**
- Drastically fewer API calls (one per file instead of one per proband)
- Eliminates rate-limit pressure — no need for sleep
- Faster overall pipeline

**Cons:**
- Slightly more complex flow in `transform_file`
- Need to handle chunking if a file has >200 unique PMIDs (unlikely but possible)

**Decision pending.** Currently using `time.sleep(0.4)` as a temporary measure.