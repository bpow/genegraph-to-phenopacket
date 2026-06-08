# Variant Description Enrichment — Implementation Plan

**Date:** 2026-06-08
**Branch:** `variant_description_2026-06-08`
**Goal:** Enrich `VariationDescriptor` in each phenopacket's genomic interpretation by calling the ClinGen Allele Registry (CAID) API when a `carId` is present, with a persistent JSON cache to avoid redundant API calls across pipeline runs.

---

## Background

The existing pipeline populated `VariationDescriptor` with only four fields: `id` (caid:/clinvar: prefix), `label` (clinvarVariantTitle), `gene_context` (via fragile string-match on title), and `allelic_state` (from recessiveZygosity). Many richer fields were left empty.

The ClinGen Allele Registry API (`https://reg.clinicalgenome.org/allele/{carId}`) returns:
- Genomic HGVS (GRCh38, GRCh37) and transcript HGVS (MANE Select preferred)
- GRCh38 VCF-style coordinates (chromosome, position, ref, alt)
- Cross-references: dbSNP rsID, ClinVar allele ID
- Gene symbol list — used to replace the old `gene_symbol in clinvarVariantTitle` heuristic

---

## Design Decisions

### Caching strategy
- **Persistent JSON cache** at `data/cache/caid_cache.json`, committed to the repo
- Cache is loaded at startup, checked before every API call, written to disk at the end of each run
- CAID data is **immutable** (a canonical allele ID maps to fixed coordinates forever), so cached entries never expire
- Committing the cache means collaborators and CI skip API calls for already-seen variants

### Three-layer lookup per variant
1. Has `carId` **and** cache hit → use cached data
2. Has `carId` **and** cache miss → call API, store in cache, use data
3. No `carId` **or** API failure → fall back to GCI record data (`hgvsNames`, `dbSNPIds`)

### Gene context confirmation
- Old approach: `if gene_symbol in clinvarVariantTitle` — fragile string match
- New approach: `if gene_symbol in caid_data["gene_symbols"]` — structured list from API
- Fallback (no CAID data): old string-match preserved for backward compatibility

### HGVS expression selection
- Genomic: GRCh38 and GRCh37 only (NCBI36 excluded)
- Transcript: MANE Select transcript(s) preferred; falls back to first transcript if no MANE
- Protein: from the MANE Select (or first) transcript's `proteinEffect.hgvs`

### VCF position
- API uses 0-based interbase coordinates; VCF is 1-based → `pos = start + 1`

---

## Files Changed

| Action | File | Change |
|---|---|---|
| Create | `src/gci_phenopacket/caid_client.py` | `CaidClient` class: load/save JSON cache, `_fetch`, `_parse` |
| Create | `tests/test_caid_client.py` | 17 tests covering parse, cache hit/miss, save/reload |
| Modify | `src/gci_phenopacket/transformer.py` | Add `caid_client` param to `GCITransformer` and `build_genomic_interpretations`; add `_build_expressions_from_gci`, `_build_xrefs_from_gci` helpers |
| Modify | `src/gci_phenopacket/cli.py` | Add `--caid-cache` option; initialize `CaidClient`; call `save()` after run |
| Modify | `tests/test_gci_transformer.py` | 12 new tests for CAID path and GCI fallback path |
| Create | `data/cache/caid_cache.json` | Empty cache seed file (committed to repo) |
| Modify | `README.md` | Document `caid_client.py`, `--caid-cache` option, CAID Variant Cache section |
| Modify | `CLAUDE.md` | Update Key Files table and Key Design Decisions |

---

## What Was NOT Implemented (Future Work)

### ClinVar API for `acmg_pathogenicity_classification`

For variants with a `clinvarVariantId` but no `carId`, the ClinVar E-utilities API
(`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=clinvar&id={clinvarVariantId}`)
returns the clinical significance (Pathogenic / Likely Pathogenic / VUS / Benign / etc.) and
submitter review status.

This could populate `VariantInterpretation.acmg_pathogenicity_classification`, which is currently
hardcoded to `NOT_PROVIDED`. A persistent JSON cache (same pattern as `data/cache/caid_cache.json`)
should be used. **Do not implement until the CAID enrichment is validated in production.**

---

## Test Coverage

All 106 tests pass. New tests added in this branch:

- `tests/test_caid_client.py` — 17 tests
- `tests/test_gci_transformer.py` — 12 new tests (CAID path + GCI fallback helpers)
