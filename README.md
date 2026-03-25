# ClinGen GCI to Phenopacket Pipeline

This pipeline reads a ClinGen GCI snapshot (JSONL format) and produces **GA4GH Phenopacket v2** JSON files — one per qualifying proband individual.

## Project Structure

```
src/
  gci_main.py          # CLI entry point and JSONL processing loop
  gci_transformer.py   # All GCI → Phenopacket field mapping logic
  utils/
    ontologies.py      # OntologyManager: HPO and Mondo label lookups
    logger.py          # Logging setup
    paths.py           # Project root resolution

tests/
  test_gci_transformer.py  # Unit tests for transformation logic

data/
  gci/                 # Input JSONL snapshots
  output/              # Generated Phenopacket JSON files
```

## Requirements

- [Pixi](https://pixi.sh) for environment management

## Getting Started

Install dependencies:

```bash
pixi install
```

## Running the Pipeline

**Process the full JSONL snapshot:**

```bash
pixi run gci_transform
```

**Process a single record by 0-based line index (useful for testing):**

```bash
pixi run gci_transform --record 0
```

**Specify custom input/output paths:**

```bash
pixi run gci_transform --input data/gci/gci_snapshot_2026-03-11.jsonl --output data/output/
```

Output files are written to `data/output/` by default. Each file is named after its Phenopacket ID:

```
{file_index}_{annotation_index}_{gene_symbol}_{mondo_id}_{pmid}_{individual_label}_{tag}.json
```

For example: `0_0_DSG2_MONDO_0016587_16505173_Patient_1_g.json`

## Individual Filtering

Only proband individuals with at least one HPO term are converted. An individual is processed if:

1. `is_proband == "Yes"`
2. At least one of `hpoIdInDiagnosis` or `hpoIdInElimination` is non-empty

All others are silently skipped.

## Running Tests

```bash
pixi run python -m pytest tests/ -v
```

## Input Format

The pipeline expects a newline-delimited JSON (JSONL) file — one GDM record per line — with the following structure:

```
resourceParent.gdm.gene.symbol          → gene symbol
resourceParent.gdm.gene.hgncId          → HGNC ID
resourceParent.gdm.annotations[]
  .article.pmid                         → PubMed ID
  .article.title                        → article title
  .individuals[]                        → direct individuals
  .families[].individualIncluded[]      → family individuals
  .groups[].individualIncluded[]        → group individuals
  .groups[].familyIncluded[]
      .individualIncluded[]             → group-family individuals
```