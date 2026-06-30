# ClinGen GCI to Phenopacket Pipeline

This pipeline reads a ClinGen GCI snapshot (JSONL format) and produces **GA4GH Phenopacket v2** JSON files — one per qualifying individual.

## Project Structure

```
src/gci_phenopacket/
  cli.py               # Click CLI entry point and JSONL processing loop
  transformer.py       # All GCI → Phenopacket field mapping logic
  ontologies.py        # OntologyManager: HP and Mondo via oaklib sqlite adapter
  allele_registry_client.py  # AlleleRegistryClient: ClinGen Allele Registry API fetch + persistent gzip-compressed JSON cache

tests/
  test_gci_transformer.py  # Unit tests for transformation logic
  test_cli.py              # CLI integration tests
  test_ontologies.py       # Ontology caching and lookup tests
  test_allele_registry_client.py  # Allele Registry client parse, cache, and API tests

data/
  gci/                 # Input JSONL snapshots
  cache/
    allele_registry_cache.json.gz # Persistent allele registry variant info cache (gzip-compressed JSON)
```

## Requirements

- [Pixi](https://pixi.sh) for environment management, **or**
- `pip install .` to install as a standalone package

## Getting Started

**Option 1 — Pixi (development):**

```bash
pixi install
pixi run gci_transform
```

**Option 2 — pip (install globally, run from any directory):**

```bash
pip install .
gci-transform
```

## Running the Pipeline

**Prompt for input path if not supplied:**

```bash
pixi run gci_transform
# Path to input JSONL file: /path/to/snapshot.jsonl
```

**Provide input explicitly (output defaults to `./gci_phenopackets/` in the current directory):**

```bash
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl
```

**Custom output directory:**

```bash
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --output /path/to/output/
```

**Process a single record by 0-based line index (jumps directly to that line — no full file scan):**

```bash
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --record 0
```

**Pipe logs to a file:**

```bash
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl > run.log
```

**Control logging verbosity:**

```bash
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --log-level DEBUG
```

**Preserve freetext disease terms instead of replacing with fallback "human disease":**

```bash
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --preserve-freetext
```

**Write all output files flat into the output directory (no per-gene subdirectories):**

```bash
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --no-subdirs
```

**Use a custom allele registry cache location (defaults to `./data/cache/allele_registry_cache.json.gz`):**

```bash
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --allele-registry-cache /path/to/allele_registry_cache.json.gz
```

By default, output files are written to gene-name subdirectories under the output directory, named after their Phenopacket ID:

```
{output}/{gene_symbol}/{gene_symbol}_{mondo_id}_{pmid}_{label_sanitized}_{individual_uuid}_{record_uuid}_{gdm_uuid}_{annotation_uuid}.json
```

If a file already exists at the target path, it is overwritten and a `WARNING` is logged.

For example: `gci_phenopackets/DSG2/DSG2_MONDO_0016587_16505173_Patient_1_abc12345-0000-0000-0000-000000000000_edf01b6b-af07-4c70-b807-4bbec8830d8a_07090d6b-ef0a-404b-8621-ca9a4a309f4f_8a1b2c3d-ef01-2345-6789-abcdef012345.json`

## Ontology Cache

Ontologies (HP and Mondo) are downloaded on first run via oaklib's sqlite adapter and cached automatically by oaklib. Subsequent runs reuse the cached databases. GENO zygosity terms are hardcoded in `transformer.py` and do not require a download.

## Allele Registry Variant Cache

The pipeline calls the [ClinGen Allele Registry](https://reg.genome.network) to enrich the `VariationDescriptor` with:

- **HGVS expressions** — GRCh38/GRCh37 genomic (`hgvs.g`), MANE Select transcript (`hgvs.c`), and protein (`hgvs.p`)
- **VCF record** — GRCh38 chromosome, position, ref/alt alleles (from the gnomAD v4 id)
- **Cross-references** — dbSNP rsID and ClinVar allele ID
- **Gene confirmation** — gene symbol matched against the API's gene list (replaces fragile title string-match)

The lookup is attempted in three tiers per variant:

1. **Has `carId`** → `GET reg.genome.network/allele/{carId}`
2. **Has `clinvarVariantId`** (no carId) → `GET reg.genome.network/alleles?ClinVar.variationId={id}`
3. **Neither** → falls back to HGVS and dbSNP data already present in the GCI record (`hgvsNames`, `dbSNPIds`)

Responses are cached in `data/cache/allele_registry_cache.json.gz` (gzip-compressed JSON). The cache is checked before every API call — on subsequent runs, variants already in the cache require no network access. The cache is written to disk at the end of each run (via `try/finally`, so entries are preserved even if the run is interrupted).

## Individual Filtering

An individual is converted to a phenopacket if they have at least one HPO term:

- `hpoIdInDiagnosis` or `hpoIdInElimination` is non-empty

All others are skipped, regardless of proband status.

## Running Tests

```bash
pixi run test
```

## Input Format

The pipeline expects a newline-delimited JSON (JSONL) file — one GDM record per line — with the following structure:

```
uuid                                    → record UUID (used in phenopacket ID)
resourceParent.gdm.gene.symbol          → gene symbol
resourceParent.gdm.gene.hgncId          → HGNC ID
resourceParent.gdm.annotations[]
  .uuid                                 → annotation UUID (used in phenopacket ID)
  .article.pmid                         → PubMed ID
  .article.title                        → article title
  .individuals[]                        → direct individuals (tag: individual)
  .families[].individualIncluded[]      → family individuals (tag: family)
  .groups[].individualIncluded[]        → group individuals (tag: group)
  .groups[].familyIncluded[]
      .individualIncluded[]             → group-family individuals (tag: group)
```

## Field Resolution

### Disease

Resolved from `individual.diagnosis[0]` in priority order:

1. `diseaseId` — preferred (e.g. `MONDO_0016587`)
2. `PK` — fallback primary key when `diseaseId` is absent
3. If neither is present, or the value is a `FREETEXT_` prefix, defaults to `MONDO:0700096` ("human disease")

`MONDO_XXXXXXX` format is normalised to `MONDO:XXXXXXX` before lookup.

### Variants

Resolved from the individual in priority order:

1. `variants[]` — used directly when present
2. `variantScores[].variantScored` — fallback when `variants` is empty; each entry's nested `variantScored` dict is treated as a variant
3. If neither is present, no genomic interpretations are emitted

For each variant, `carId` is preferred for the ID (`caid:CA...`), falling back to `clinvarVariantId` (`clinvar:...`).

The Allele Registry API is called (or cache checked) to populate `expressions`, `vcf_record`, and `xrefs` on the `VariationDescriptor` — first via `carId`, then via `clinvarVariantId` if no `carId` is present. See [Allele Registry Variant Cache](#allele-registry-variant-cache).

### Pathogenicity Classification

`VariantInterpretation.acmg_pathogenicity_classification` is always set to `NOT_PROVIDED`, and this is intentional and must not be changed. Although ClinVar exposes reports of clinical significance for many variants, the current Phenopacket v2 spec provides no way to record the *provenance* of a pathogenicity classification. A classification reported to ClinVar was asserted by some other group — populating this field would make the phenopacket appear to assert pathogenicity ourselves, which would be incorrect and misleading. Leave it `NOT_PROVIDED` until the Phenopacket spec supports provenance metadata for this field.

### Zygosity

Read from `individual.recessiveZygosity`. Mapped to GENO terms:

| GCI value | GENO term |
|---|---|
| `Homozygous` | `GENO:0000136` |
| `Heterozygous` | `GENO:0000135` |
| `Hemizygous` | `GENO:0001059` |
| `Unknown` / unrecognised | `GENO:0000137` (unspecified) |

If `recessiveZygosity` is absent, allelic state is omitted from the phenopacket.

### Metadata External References

`metadata.external_references` always includes the source article as `PMID:{pmid}` (with the article title as `description`). When the individual has a resolvable provenance path through the GCI data model, a second entry is appended in the form `gdm:{gdm_id}-[group:{group_id}-][family:{family_id}-]individual:{individual_id}`.