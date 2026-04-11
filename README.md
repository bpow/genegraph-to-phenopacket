# ClinGen GCI to Phenopacket Pipeline

This pipeline reads a ClinGen GCI snapshot (JSONL format) and produces **GA4GH Phenopacket v2** JSON files — one per qualifying individual.

## Project Structure

```
src/gci_phenopacket/
  cli.py               # Click CLI entry point and JSONL processing loop
  transformer.py       # All GCI → Phenopacket field mapping logic
  utils/
    ontologies.py      # OntologyManager: HP and Mondo via pronto (cached)
    logger.py          # Stdout logging setup
    paths.py           # Platform cache directory via platformdirs

tests/
  test_gci_transformer.py  # Unit tests for transformation logic
  test_cli.py              # CLI integration tests
  test_logger.py           # Logger setup tests
  test_ontologies.py       # Ontology caching and lookup tests

data/
  gci/                 # Input JSONL snapshots
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

Output files are named after their Phenopacket ID:

```
{record_uuid}_{annotation_uuid}_{gene_symbol}_{mondo_id}_{pmid}_{individual_label}_{tag}.json
```

For example: `edf01b6b-af07-4c70-b807-4bbec8830d8a_07090d6b-ef0a-404b-8621-ca9a4a309f4f_DSG2_MONDO_0016587_16505173_Patient_1_individual.json`

The `tag` indicates how the individual was nested in the GCI record: `individual` (direct), `family`, or `group`.

## Ontology Cache

Ontologies (HP and Mondo) are downloaded on first run and cached locally so subsequent runs are fast:

| Platform | Cache location |
|---|---|
| macOS | `~/Library/Caches/gci-phenopacket/ontologies/` |
| Linux | `~/.cache/gci-phenopacket/ontologies/` |
| Windows | `%LOCALAPPDATA%\gci-phenopacket\Cache\ontologies\` |

GENO zygosity terms are hardcoded in `transformer.py` and do not require a download.

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