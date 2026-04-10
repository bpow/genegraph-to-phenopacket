# ClinGen GCI to Phenopacket Pipeline

This pipeline reads a ClinGen GCI snapshot (JSONL format) and produces **GA4GH Phenopacket v2** JSON files — one per qualifying proband individual.

## Project Structure

```
src/gci_phenopacket/
  cli.py               # Click CLI entry point and JSONL processing loop
  transformer.py       # All GCI → Phenopacket field mapping logic
  utils/
    ontologies.py      # OntologyManager: HP, Mondo, GENO via pronto (cached)
    logger.py          # Stdout logging setup
    paths.py           # Platform cache directory via platformdirs

tests/
  test_gci_transformer.py  # Unit tests for transformation logic

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
gci-transform
# Path to input JSONL file: /path/to/snapshot.jsonl
```

**Provide input explicitly (output defaults to `./gci_phenopackets/` in the current directory):**

```bash
gci-transform --input /path/to/gci_snapshot.jsonl
```

**Custom output directory:**

```bash
gci-transform --input /path/to/gci_snapshot.jsonl --output /path/to/output/
```

**Process a single record by 0-based line index (useful for testing):**

```bash
gci-transform --input /path/to/gci_snapshot.jsonl --record 0
```

**Pipe logs to a file:**

```bash
gci-transform --input /path/to/gci_snapshot.jsonl > run.log
```

Output files are named after their Phenopacket ID:

```
{file_index}_{annotation_index}_{gene_symbol}_{mondo_id}_{pmid}_{individual_label}_{tag}.json
```

For example: `0_0_DSG2_MONDO_0016587_16505173_Patient_1_g.json`

## Ontology Cache

Ontologies (HP, Mondo, GENO) are downloaded on first run and cached locally so subsequent runs are fast:

| Platform | Cache location |
|---|---|
| macOS | `~/Library/Caches/gci-phenopacket/ontologies/` |
| Linux | `~/.cache/gci-phenopacket/ontologies/` |
| Windows | `%LOCALAPPDATA%\gci-phenopacket\Cache\ontologies\` |

## Individual Filtering

Only proband individuals with at least one HPO term are converted. An individual is processed if:

1. `is_proband == "Yes"`
2. At least one of `hpoIdInDiagnosis` or `hpoIdInElimination` is non-empty

All others are skipped.

## Running Tests

```bash
pixi run test
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
